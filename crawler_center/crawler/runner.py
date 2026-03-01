from __future__ import annotations  # 让类型注解支持“前向引用”，比如 Optional["ScrapyRunnerService"]

import asyncio  # asyncio：Python 原生异步框架，用来 await、超时控制等
import threading  # 线程相关：这里用于单例加锁，保证线程安全
from typing import Any, ClassVar, Dict, List, Optional, Type  # 类型提示：让代码更易读、更可维护

from scrapy.utils.reactor import install_reactor  # 安装 Twisted reactor（Scrapy 底层用 Twisted）

# 尝试把 Scrapy/Twisted 的事件循环切到 asyncio 上
# 这样你就能在 async def 里用 await 来等待 Scrapy 运行完成
_REACTOR_INSTALL_ERROR: Exception | None = None
try:
    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
except Exception as exc:
    # uvicorn 可能在已启动的 ProactorEventLoop 中 import 应用，导致安装 AsyncioSelectorReactor 失败。
    # 这里记录原始异常，在 run() 时返回明确指引，避免只看到模糊的 deferred_to_future 报错。
    _REACTOR_INSTALL_ERROR = exc

from scrapy import Spider, signals  # Spider：爬虫基类；signals：Scrapy 信号（事件）系统
from scrapy.crawler import CrawlerRunner  # CrawlerRunner：在代码中启动/管理爬虫（不自动退出进程）
from scrapy.utils.defer import deferred_to_future  # 把 Twisted Deferred 转成 asyncio Future，才能 await
from twisted.internet import reactor

from crawler_center.core.config import AppSettings  # 你们项目的配置类
from crawler_center.core.errors import CrawlerExecutionError, CrawlerTimeoutError  # 自定义异常：执行失败/超时
from crawler_center.crawler.middlewares import set_proxy_service  # 设置代理服务（给中间件用）
from crawler_center.crawler.settings import build_scrapy_settings  # 构建 Scrapy settings 配置
from crawler_center.services.proxy_service import ProxyService  # 代理服务类

# is_asyncio_selector_reactor 和 _build_reactor_hint_message 这两个函数
# 是为了检查当前的 Twisted reactor 是否是 AsyncioSelectorReactor，
def _is_asyncio_selector_reactor() -> bool:
    return reactor.__class__.__name__ == "AsyncioSelectorReactor"


def _build_reactor_hint_message() -> str:
    current_reactor = reactor.__class__.__name__
    install_error = (
        f"; install_error={type(_REACTOR_INSTALL_ERROR).__name__}: {_REACTOR_INSTALL_ERROR}"
        if _REACTOR_INSTALL_ERROR
        else ""
    )
    return (
        "scrapy runner requires AsyncioSelectorReactor, "
        f"current_reactor={current_reactor}{install_error}. "
        "On Windows, start with: .\\.venv\\Scripts\\python.exe -m crawler_center.api.run"
    )


class ScrapyRunnerService:
    # 单例：全局只创建一个 ScrapyRunnerService 实例
    _instance: ClassVar[Optional["ScrapyRunnerService"]] = None

    # 单例锁：防止多线程环境下同时创建多个实例
    _instance_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def get_instance(cls, app_settings: AppSettings, proxy_service: ProxyService) -> "ScrapyRunnerService":
        # 加锁，确保线程安全
        with cls._instance_lock:
            # 第一次调用才创建实例
            if cls._instance is None:
                cls._instance = cls(app_settings=app_settings, proxy_service=proxy_service)
            # 之后都复用同一个实例
            return cls._instance

    @classmethod
    def reset_instance_for_tests(cls) -> None:
        # 测试用：把单例清空，让每个测试可以重新初始化
        with cls._instance_lock:
            cls._instance = None

    def __init__(self, app_settings: AppSettings, proxy_service: ProxyService) -> None:
        # 默认运行超时时间（从配置读）
        self._run_timeout = app_settings.crawler_run_timeout_sec

        # 保存配置对象（可能后续还会用到）
        self._app_settings = app_settings

        # 根据配置构建 Scrapy settings（并发、UA、middleware、pipeline 等）
        scrapy_settings = build_scrapy_settings(app_settings)

        # 创建 CrawlerRunner：负责在当前进程中启动/运行爬虫
        self._runner = CrawlerRunner(settings=scrapy_settings)

        # 设置代理服务：一般是让 downloader middleware 能拿到 proxy_service
        set_proxy_service(proxy_service)

    async def run(
        self,
        spider_cls: Type[Spider],  # 传入一个 Spider 类（注意是类，不是实例）
        run_timeout_sec: Optional[int] = None,  # 可选：本次运行的超时时间
        **spider_kwargs: Any,  # 传给 spider 的参数，比如 start_urls、keyword 等
    ) -> List[Dict[str, Any]]:
        if not _is_asyncio_selector_reactor():
            raise CrawlerExecutionError(_build_reactor_hint_message())

        # CrawlerRunner 依赖已运行的 reactor；若未启动会出现请求悬挂直至超时。
        if not reactor.running:
            reactor.startRunning(installSignalHandlers=False)

        try:
            running_loop = asyncio.get_running_loop()
            reactor_loop = getattr(reactor, "_asyncioEventloop", None)
            # Uvicorn/TestClient 会创建新的 asyncio loop，导致 reactor 绑定旧 loop 而请求悬挂。
            # 这里在运行前把 reactor 绑定到当前 loop。
            if reactor_loop is not None and reactor_loop is not running_loop:
                reactor._asyncioEventloop = running_loop  # type: ignore[attr-defined]
        except RuntimeError:
            pass

        # 用来收集爬虫产出的 items（最终返回这个 list）
        collected_items: List[Dict[str, Any]] = []

        # 由 runner 创建 crawler（相当于 spider 的“运行实例/容器”）
        crawler = self._runner.create_crawler(spider_cls)

        # Scrapy 每产出一个 item，会触发 signals.item_scraped 信号
        # 我们定义一个回调函数来接住 item，并塞进 collected_items
        def _on_item_scraped(item: Any, response: Any, spider: Spider) -> None:
            # item 可能是 dict，也可能是 Item（类似 dict 的对象）
            if isinstance(item, dict):
                collected_items.append(item)  # 如果本身就是 dict，直接放进去
            else:
                collected_items.append(dict(item))  # 如果是 Item，转成 dict 再放进去

        # 把回调函数绑定到 crawler 的 item_scraped 信号上
        crawler.signals.connect(_on_item_scraped, signal=signals.item_scraped)

        # 开始运行爬虫；返回 Twisted 的 Deferred（不是 asyncio Future）
        deferred = self._runner.crawl(crawler, **spider_kwargs)

        # 本次运行的超时：优先用参数 run_timeout_sec，否则用默认配置
        timeout = run_timeout_sec if run_timeout_sec is not None else self._run_timeout

        try:
            # deferred_to_future：把 Twisted Deferred 转成 asyncio Future
            # asyncio.wait_for：加超时控制，如果超时会抛 asyncio.TimeoutError
            await asyncio.wait_for(deferred_to_future(deferred), timeout=timeout)

        except asyncio.TimeoutError as exc:
            # 超时：抛你们项目自定义的超时异常
            raise CrawlerTimeoutError(f"crawler run timed out after {timeout}s") from exc

        except Exception as exc:
            # 其他任何异常：统一包装成执行异常
            raise CrawlerExecutionError(str(exc)) from exc

        # 爬虫跑完：返回收集到的 items
        return collected_items
