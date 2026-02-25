"""FastAPI 应用入口与生命周期管理。

该模块负责：
- 创建并配置 FastAPI 实例
- 在 lifespan 中初始化 Service/Runner/Proxy 等核心依赖
- 统一异常到标准错误响应的映射

生产约束：
- 路由层不直接 new 业务对象，统一通过 `app.state` 注入，便于测试替换与生命周期管理。
- 所有异常最终收敛为稳定的 JSON 错误结构：`{ok:false,error,code}`。
- 后台代理探测循环必须随服务启动/停止而显式启停，避免悬挂任务与资源泄露。
"""

from __future__ import annotations

# 标准库：
# - logging: 记录结构化运行日志
# - asynccontextmanager: 定义 FastAPI 生命周期上下文
# - typing: 提供类型标注，提升可读性与静态检查能力
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

# FastAPI 核心对象：
# - FastAPI: 应用实例
# - HTTPException: 主动抛出的 HTTP 错误
# - Request: 请求上下文（可访问 app.state）
from fastapi import FastAPI, HTTPException, Request
# 参数校验异常（Pydantic/请求体校验失败时触发）
from fastapi.exceptions import RequestValidationError
# 手动返回 JSON 响应体（用于统一错误格式）
from fastapi.responses import JSONResponse

# API 契约层：统一错误响应模型
from crawler_center.api.schemas.common import ErrorResponse
# 路由集合：按业务域拆分的 endpoint 入口
from crawler_center.api.routers import (
    healthz_router,  # 健康检查路由
    internal_proxies_router,  # 内部代理池管理路由（需 token）
    lanqiao_router,  # 蓝桥业务路由（当前骨架）
    leetcode_router,  # LeetCode 业务路由
    luogu_router,  # Luogu 业务路由
)
# 核心配置：配置对象与加载函数（YAML + 环境变量）
from crawler_center.core.config import AppSettings, load_settings
# 核心错误体系：统一异常类型与错误码提取
from crawler_center.core.errors import (
    CrawlerCenterError,  # 项目基础异常
    CrawlerExecutionError,  # 爬虫执行失败
    CrawlerTimeoutError,  # 爬虫超时
    ProxyUnavailableError,  # 无可用代理
    UpstreamRequestError,  # 上游站点请求失败
    pick_error_code,  # 异常对象 -> 机器可读错误码
)
# 核心日志能力：日志初始化与业务事件打点
from crawler_center.core.logging import configure_logging, log_event
# Scrapy 运行器：统一调度 spider 执行
from crawler_center.crawler.runner import ScrapyRunnerService
# 业务服务层：封装各站点抓取编排逻辑
from crawler_center.services.lanqiao_service import LanqiaoService
from crawler_center.services.leetcode_service import LeetCodeService
from crawler_center.services.luogu_service import LuoguService
# 代理池服务：代理维护、健康状态更新、主动探测
from crawler_center.services.proxy_service import ProxyService

# 当前模块日志器（logger name = crawler_center.api.main）
logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """管理应用启动与关闭阶段的资源生命周期。

    启动阶段按顺序完成：
    1) 读取 `app.state.settings`
    2) 构建代理池服务与 Scrapy 运行器
    3) 构建业务 service 并挂到 `app.state`
    4) 启动代理主动探测后台任务

    关闭阶段保证：
    - 主动探测任务被停止
    - 生命周期事件被记录到结构化日志
    """
    settings: AppSettings = app.state.settings
    # ProxyService 是运行期共享的可变状态对象，必须全局单例使用。
    proxy_service = ProxyService(
        probe_urls=settings.probe_urls,
        user_agent=settings.default_user_agent,
        request_timeout_sec=settings.default_timeout_sec,
    )
    # Runner 使用单例，避免多实例争用 reactor / 调度资源。
    runner = ScrapyRunnerService.get_instance(app_settings=settings, proxy_service=proxy_service)

    # 统一通过 app.state 暴露依赖，供 FastAPI Depends 在请求内获取。
    app.state.proxy_service = proxy_service
    app.state.runner = runner
    app.state.leetcode_service = LeetCodeService(runner=runner, settings=settings)
    app.state.luogu_service = LuoguService(runner=runner, settings=settings)
    app.state.lanqiao_service = LanqiaoService(runner=runner, settings=settings)

    # 启动代理池主动健康探测循环；异常不会中断服务启动。
    await proxy_service.start_probe_loop(interval_sec=settings.proxy_active_probe_interval_sec)

    log_event(
        logger,
        logging.INFO,
        "service_started",
        target="app",
        endpoint="startup",
        status_code=200,
        version=settings.api_version,
        config_path=str(settings.config_path),
    )

    try:
        yield
    finally:
        # 退出时显式停止后台任务，避免进程退出前残留异步任务。
        await proxy_service.stop_probe_loop()
        log_event(
            logger,
            logging.INFO,
            "service_stopped",
            target="app",
            endpoint="shutdown",
            status_code=200,
        )


def _error_response(status_code: int, error: str, code: Optional[str] = None) -> JSONResponse:
    """构造统一错误响应体。

    参数：
    - status_code: HTTP 状态码
    - error: 面向调用方的错误信息
    - code: 机器可读错误码，供客户端分支处理
    """
    payload = ErrorResponse(error=error, code=code).model_dump()
    return JSONResponse(status_code=status_code, content=payload)


def create_app(app_settings: Optional[AppSettings] = None) -> FastAPI:
    """创建应用实例并注册路由、异常处理器。

    参数：
    - app_settings: 可选注入配置。测试环境通常传入该参数以隔离真实配置文件。
    """
    # 测试可传入定制配置；生产默认从 config.yaml + 环境变量加载。
    settings = app_settings or load_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title=settings.api_title, version=settings.api_version, lifespan=_lifespan)
    app.state.settings = settings

    # 路由注册顺序不影响匹配结果，但按业务域分组便于维护。
    app.include_router(healthz_router)
    app.include_router(leetcode_router)
    app.include_router(luogu_router)
    app.include_router(lanqiao_router)
    app.include_router(internal_proxies_router)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        """处理显式抛出的 HTTP 异常（如 401/404/503）。"""
        detail = str(exc.detail)
        return _error_response(status_code=exc.status_code, error=detail, code="http_error")

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        """处理请求参数校验失败（FastAPI/Pydantic 触发）。"""
        return _error_response(status_code=422, error=str(exc), code="validation_error")

    @app.exception_handler(CrawlerTimeoutError)
    async def crawler_timeout_handler(_: Request, exc: CrawlerTimeoutError) -> JSONResponse:
        """爬虫执行超时，映射为 504。"""
        return _error_response(status_code=504, error=str(exc), code=exc.code)

    @app.exception_handler(ProxyUnavailableError)
    async def proxy_unavailable_handler(_: Request, exc: ProxyUnavailableError) -> JSONResponse:
        """代理不可用，映射为 503。"""
        return _error_response(status_code=503, error=str(exc), code=exc.code)

    @app.exception_handler(UpstreamRequestError)
    async def upstream_error_handler(_: Request, exc: UpstreamRequestError) -> JSONResponse:
        """上游站点请求失败，映射为 502。"""
        return _error_response(status_code=502, error=str(exc), code=exc.code)

    @app.exception_handler(CrawlerExecutionError)
    async def crawler_execution_handler(_: Request, exc: CrawlerExecutionError) -> JSONResponse:
        """爬虫执行期非超时错误，映射为 502。"""
        return _error_response(status_code=502, error=str(exc), code=exc.code)

    @app.exception_handler(CrawlerCenterError)
    async def crawler_center_error_handler(_: Request, exc: CrawlerCenterError) -> JSONResponse:
        """兜底处理项目内自定义异常，默认映射为 500。"""
        return _error_response(status_code=500, error=str(exc), code=pick_error_code(exc))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        """最终兜底，拦截未预期异常，避免泄露默认 HTML 错误页。"""
        return _error_response(status_code=500, error=str(exc), code="internal_error")

    return app


app = create_app()
