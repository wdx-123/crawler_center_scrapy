"""LeetCode spider 公共基类与工具函数。

职责：
- 统一 URL 拼装规则（主页、GraphQL、根路径）。
- 统一 CSRF 提取逻辑与 GraphQL 请求构造。
- 统一注入 ``meta["target_site"]``，保障代理中间件行为一致。

设计动机：
- 把重复样板从具体 spider 中抽离，降低维护成本。
- 在站点接口波动时，尽量只改一个公共点。
"""

from __future__ import annotations

import json
from http.cookies import SimpleCookie
from typing import Any, Dict

import scrapy
from scrapy.http import Response

from crawler_center.services.proxy_service import TargetSite


class LeetCodeSpiderBase(scrapy.Spider):
    """LeetCode 抓取基类。

    参数约定：
    - ``base_url``: 目标站点基础地址，会做 ``rstrip("/")`` 归一化。
    - ``username``: LeetCode 用户名（大多数查询都依赖此字段）。
    - ``sleep_sec``: 预留节流参数，当前仅透传，便于后续扩展限速策略。
    """

    target_site = TargetSite.LEETCODE.value

    def __init__(self, base_url: str, username: str, sleep_sec: float = 0.0, **kwargs: Any) -> None:
        """保存运行参数，供子类构造请求时复用。"""
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.sleep_sec = sleep_sec

    def profile_url(self) -> str:
        """返回用户主页 URL。"""
        return f"{self.base_url}/u/{self.username}/"

    def graphql_noj_url(self) -> str:
        """返回 recent_ac 使用的 GraphQL 入口。"""
        return f"{self.base_url}/graphql/noj-go/"

    def graphql_url(self) -> str:
        """返回通用 GraphQL 入口。"""
        return f"{self.base_url}/graphql"

    def root_url(self) -> str:
        """返回站点根路径，用于预取 cookie / csrf。"""
        return f"{self.base_url}/"

    def extract_csrf_from_response(self, response: Response) -> str:
        """从响应头 ``Set-Cookie`` 中提取 ``csrftoken``。

        返回空串表示未拿到 token；调用方应按“尽力而为”策略继续请求。
        """
        headers = response.headers.getlist("Set-Cookie")
        for cookie_bytes in headers:
            text = cookie_bytes.decode("utf-8", errors="ignore")
            jar = SimpleCookie()
            jar.load(text)
            if "csrftoken" in jar:
                return str(jar["csrftoken"].value)
        return ""
def build_graphql_request(
    self,
    *,  # 下面这些参数必须用关键字传入（可读性更强，避免位置参数传错）
    url: str,  # GraphQL endpoint 地址（例如 https://leetcode.com/graphql 或 /graphql/noj-go/）
    operation_name: str,  # GraphQL 的 operationName（便于服务端识别/路由/日志；有些接口要求必须带）
    query: str,  # GraphQL 查询文本（query/mutation 字符串）
    variables: Dict[str, Any],  # GraphQL variables（会被序列化成 JSON）
    referer: str,  # Referer 头（常用于反爬/风控校验，模拟从页面发起请求）
    csrf_token: str,  # CSRF token（从 Set-Cookie 解析得到的 csrftoken；非空则附带到请求头）
    callback: Any,  # Scrapy 回调函数（响应返回后执行；通常是 self.parse_xxx）
) -> scrapy.Request:
    """构造标准化 GraphQL POST 请求。

    统一行为：
    - 设置 Referer / Origin / JSON Content-Type。
    - 仅当 token 非空时附带 ``x-csrftoken``。
    - 始终写入 ``meta["target_site"]``，用于代理健康回传。
    """

    # 构造请求头：尽量贴近浏览器/前端发 GraphQL 的常见头部，降低被风控概率
    headers: Dict[str, str] = {
        "Referer": referer,  # 告诉服务端请求来源页面（部分站点会校验）
        "Content-Type": "application/json",  # POST body 是 JSON（GraphQL 常用方式）
        "Origin": self.base_url,  # 浏览器跨域相关头；一些站点会校验 Origin 是否匹配域名
        "Accept": "application/json",  # 声明客户端期望 JSON 响应（GraphQL 返回 JSON）
    }

    # 仅当拿到了 csrf_token 才加 x-csrftoken 头（尽力而为；避免空值污染请求头）
    if csrf_token:
        headers["x-csrftoken"] = csrf_token  # LeetCode 常见 CSRF 校验方式：header + cookie 配对

    # 构造 GraphQL 请求体（标准三件套：operationName / query / variables）
    payload = {
        "operationName": operation_name,  # 操作名（服务端/日志/路由常用）
        "query": query.strip(),  # 去掉首尾空白，减少无意义差异（更干净、也方便日志比对）
        "variables": variables,  # 变量对象（会被 JSON 序列化传给服务端）
    }

    # 返回一个 Scrapy Request：交给 Scrapy 下载器发请求，响应回来后交给 callback 处理
    return scrapy.Request(
        url=url,  # 请求地址：GraphQL endpoint
        method="POST",  # GraphQL 请求通常用 POST
        body=json.dumps(payload),  # dict -> JSON 字符串作为请求体（Scrapy 会按 bytes/str 发送）
        headers=headers,  # 上面构造的请求头（含可选 CSRF 头）
        callback=callback,  # 响应回调：解析 JSON 并产出 items/后续请求
        dont_filter=True,  # 禁用去重：GraphQL 常用同一 URL 多次 POST（body 不同），避免被 Scrapy 过滤
        meta={"target_site": self.target_site},  # 写入站点标识：供代理中间件按站点分配/统计/健康回传
    )