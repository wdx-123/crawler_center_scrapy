from __future__ import annotations  # 允许类型注解使用前向引用（Python 3.7+ 常用；避免循环引用/定义顺序问题）

import time  # 用于高精度计时：统计每次请求通过代理的耗时（延迟）
from typing import Optional  # Optional[T] = T | None 的兼容写法（你这里也可以直接用 T | None）

from scrapy import Request  # Scrapy 的请求对象，Downloader Middleware 会在请求发送前/后拿到它
from scrapy.http import Response  # Scrapy 的响应对象（HTTP 状态码、body 等）

from crawler_center.services.proxy_service import ProxyService, normalize_target_name  # 代理服务 & 目标站点名规范化工具

# 全局单例引用：给 middleware 提供 ProxyService（因为此中间件没有用 from_crawler 注入依赖）
# 注意：这种“全局注入”方式在多 runner / 多进程场景要格外小心，但在单进程单 runner 下可用
_PROXY_SERVICE: Optional[ProxyService] = None


def set_proxy_service(proxy_service: ProxyService | None) -> None:
    """
    注入 ProxyService 到模块级全局变量中。

    生产级注意点：
    - Scrapy 通常推荐通过 Middleware 的 from_crawler 或 settings 注入依赖；
      这里使用全局变量属于“折中方案”，便于在外部服务启动 Scrapy（例如你们的 ScrapyRunnerService）。
    - 若同一进程中存在多个不同配置的 runner（或多租户），全局变量会被覆盖，需谨慎。
    """
    global _PROXY_SERVICE  # 声明修改模块级变量（否则会被当作局部变量）
    _PROXY_SERVICE = proxy_service  # 保存服务引用，供中间件运行时读取


def get_proxy_service() -> ProxyService | None:
    """
    获取当前注入的 ProxyService。

    返回 None 表示未启用代理系统或尚未注入（中间件会直接跳过，不影响正常抓取）。
    """
    return _PROXY_SERVICE  # 读取模块级服务引用


class ProxyHealthMiddleware:
    """
    Downloader Middleware：代理健康度监控与反馈。

    作用：
    1) 在请求发出前，从 ProxyService 申请一个代理，并写入 request.meta["proxy"]。
       Scrapy 的下载器会识别这个标准字段，从而让该请求走代理。
    2) 在拿到响应后，根据状态码判断代理是否“成功/失败”，并回报给 ProxyService。
       同时计算请求耗时 latency_ms，供代理池做质量评分/排序。
    3) 下载异常时也回报失败，帮助代理池快速剔除坏代理。

    生产级注意点：
    - 失败判定策略（哪些状态码算失败）是业务选择，不是 Scrapy 的硬规则；
      你们这里把 403/407/408/429/5xx 视为失败信号。
    - 该中间件只负责“设置 proxy + 回报结果”，并不负责重试/切换代理；
      重试通常由 Scrapy RetryMiddleware 或你们自定义逻辑处理。
    """

    def process_request(self, request: Request, spider: object = None) -> None:
        """
        在请求发送前执行。

        - 若启用代理：从 ProxyService 获取代理，写入 request.meta["proxy"]。
        - 同时写入内部字段 _proxy_target / _proxy_started_at，用于后续统计与回报。

        返回 None 表示“继续正常流程”，不拦截/不短路请求。
        """
        proxy_service = get_proxy_service()  # 读取已注入的代理服务
        if not proxy_service:  # 未注入/未启用代理服务：直接跳过，不影响抓取
            return

        # 允许单个请求显式禁用代理：meta["use_proxy"] = False
        # 注意：这里用 is False（严格判断），避免 None/缺省导致误判
        if request.meta.get("use_proxy") is False:
            return

        # 获取目标站点标识，用于“按站点”分配/统计代理
        # request.meta.get("target_site") 可能是 None；normalize_target_name 应该能处理 None（若不能会报错）
        target = normalize_target_name(request.meta.get("target_site"))

        # 从代理池申请一个代理（可能根据 target 做隔离：同站点维持会话、不同站点不同池等）
        proxy_url = proxy_service.acquire_proxy(target)
        if not proxy_url:  # 没拿到代理（池空/禁用/策略拒绝等）：直接走直连
            return

        # Scrapy 标准字段：Downloader 会用这个代理地址发请求（http/https/socks 取决于实现和格式）
        request.meta["proxy"] = proxy_url

        # 记录该代理对应的 target，便于在响应/异常阶段回报给代理池
        request.meta["_proxy_target"] = target

        # 记录请求开始时间（高精度计时器，适合测量延迟；不受系统时间调整影响）
        request.meta["_proxy_started_at"] = time.perf_counter()

    def process_response(self, request: Request, response: Response, spider: object = None) -> Response:
        """
        在响应返回后执行（即请求成功完成 HTTP 往返并得到 Response）。

        - 若该请求使用了代理：根据响应状态码回报 success/failure。
        - 计算代理请求耗时 latency_ms 并上报（仅对 success 上报延迟）。

        必须返回 Response（或返回新的 Response 来替换；这里保持原样返回）。
        """
        proxy_service = get_proxy_service()  # 读取代理服务（可能运行时被 reset/未注入）
        proxy_url = request.meta.get("proxy")  # Scrapy 标准字段：若存在表示该请求走了代理
        target = request.meta.get("_proxy_target")  # 我们自己写入的字段：该代理对应的目标站点
        started = request.meta.get("_proxy_started_at")  # 我们自己写入的字段：开始时间（perf_counter 的值）

        # 只有当：服务存在 + 本次确实用了代理 + target/started 完整，才进行健康回报
        if proxy_service and proxy_url and target and isinstance(started, (float, int)):
            # 计算耗时（毫秒）：当前 perf_counter - started
            latency_ms = (time.perf_counter() - float(started)) * 1000

            # 按状态码判定代理是否失败：
            # - 403：可能被目标站点拒绝/封禁（代理 IP 风控）
            # - 407：代理认证失败/代理需要鉴权
            # - 408：请求超时（链路不稳定）
            # - 429：被限流（IP 触发频控/风控）
            # - 5xx：服务端/网关错误（也可能由代理链路导致）
            if response.status in {403, 407, 408, 429, 500, 502, 503, 504}:
                # 回报失败：代理池可据此降权/拉黑/减少分配
                proxy_service.report_failure(proxy_url=str(proxy_url), target=str(target))
            else:
                # 回报成功：并带上延迟，代理池可据此做质量评分/排序
                proxy_service.report_success(proxy_url=str(proxy_url), target=str(target), latency_ms=latency_ms)

        # 必须把响应返回给后续流程（Spider 解析、其他中间件等）
        return response

    def process_exception(self, request: Request, exception: Exception, spider: object = None) -> None:
        """
        下载过程出现异常时执行（网络错误、连接失败、DNS/TLS 错误、超时等）。

        - 若该请求使用了代理：直接回报失败。
        - 返回 None 表示“不处理该异常”，让 Scrapy 继续按默认逻辑处理（如 RetryMiddleware 重试）。
        """
        proxy_service = get_proxy_service()  # 读取代理服务
        proxy_url = request.meta.get("proxy")  # 若存在表示该请求走了代理
        target = request.meta.get("_proxy_target")  # 目标站点标识（用于按站点统计/隔离）

        # 只要满足：服务存在 + 本次走了代理 + target 存在，就回报代理失败
        if proxy_service and proxy_url and target:
            proxy_service.report_failure(proxy_url=str(proxy_url), target=str(target))

        # 返回 None：Scrapy 将继续传播异常，交给其他中间件/重试机制处理
        return None