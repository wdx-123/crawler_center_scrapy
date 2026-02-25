"""FastAPI 依赖注入函数集合。

设计约定：
- 依赖对象在应用启动阶段（`api.main._lifespan`）完成初始化并挂载到 `app.state`。
- 请求阶段只做读取，不在依赖函数内创建对象，确保依赖行为稳定且可预测。
- 返回对象通常为进程内共享实例（配置、runner、service），不是每请求新建。

故障语义：
- 若应用未按约定完成启动初始化，这些函数会在访问 `request.app.state.xxx`
  时抛出 `AttributeError`。这通常意味着启动流程被绕过（如测试装配不完整）。
"""

from __future__ import annotations

from fastapi import Request

from crawler_center.core.config import AppSettings
from crawler_center.crawler.runner import ScrapyRunnerService
from crawler_center.services.lanqiao_service import LanqiaoService
from crawler_center.services.leetcode_service import LeetCodeService
from crawler_center.services.luogu_service import LuoguService
from crawler_center.services.proxy_service import ProxyService


def get_settings(request: Request) -> AppSettings:
    """获取全局应用配置对象。
    参数：
    - request: FastAPI 请求对象，用于访问 `request.app.state`。
    返回：
    - `AppSettings`：启动时加载后的不可变配置快照。
    """
    return request.app.state.settings


def get_runner(request: Request) -> ScrapyRunnerService:
    """获取 Scrapy 运行器服务。

    返回的 runner 在进程内复用，避免重复创建调度器带来的资源竞争。
    """
    return request.app.state.runner


def get_proxy_service(request: Request) -> ProxyService:
    """获取代理池服务。

    该对象维护运行期可变状态（代理健康度/探测任务等），因此必须通过共享实例访问。
    """
    return request.app.state.proxy_service


def get_leetcode_service(request: Request) -> LeetCodeService:
    """获取 LeetCode 业务服务。"""
    return request.app.state.leetcode_service


def get_luogu_service(request: Request) -> LuoguService:
    """获取 Luogu 业务服务。"""
    return request.app.state.luogu_service


def get_lanqiao_service(request: Request) -> LanqiaoService:
    """获取 Lanqiao 业务服务。"""
    return request.app.state.lanqiao_service
