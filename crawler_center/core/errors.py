"""统一错误模型与错误码定义。

约定：
- 业务内部抛出 `CrawlerCenterError` 子类
- API 层根据错误类型映射为稳定的 HTTP 状态码
- `code` 字段用于前端/调用方机器可读判断
"""

from __future__ import annotations

from typing import Optional


class CrawlerCenterError(Exception):
    """项目级基础异常，携带稳定错误码。"""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


class CrawlerTimeoutError(CrawlerCenterError):
    """爬虫执行超时。"""

    def __init__(self, message: str = "crawler run timed out") -> None:
        super().__init__(message=message, code="crawler_timeout")


class CrawlerExecutionError(CrawlerCenterError):
    """爬虫执行失败（非超时）。"""

    def __init__(self, message: str = "crawler execution failed") -> None:
        super().__init__(message=message, code="crawler_execution_error")


class UpstreamRequestError(CrawlerCenterError):
    """上游站点请求失败或返回不可用内容。"""

    def __init__(self, message: str = "upstream request failed") -> None:
        super().__init__(message=message, code="upstream_request_error")


class UpstreamAuthenticationError(CrawlerCenterError):
    """上游站点认证失败，例如账号或密码无效。"""

    def __init__(self, message: str = "upstream authentication failed") -> None:
        super().__init__(message=message, code="upstream_auth_failed")


class ProxyUnavailableError(CrawlerCenterError):
    """代理池中没有可用代理。"""

    def __init__(self, message: str = "no healthy proxy available") -> None:
        super().__init__(message=message, code="proxy_unavailable")


class InternalTokenUnavailableError(CrawlerCenterError):
    """内部鉴权 token 未配置。"""

    def __init__(self, message: str = "internal token not configured") -> None:
        super().__init__(message=message, code="internal_token_unavailable")


class ValidationError(CrawlerCenterError):
    """参数校验失败。"""

    def __init__(self, message: str = "request validation failed", code: str = "validation_error") -> None:
        super().__init__(message=message, code=code)


def pick_error_code(exc: Exception, fallback: str = "internal_error") -> str:
    """从异常中提取机器可读错误码。"""
    if isinstance(exc, CrawlerCenterError):
        return exc.code
    return fallback
