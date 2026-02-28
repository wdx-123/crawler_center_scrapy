from __future__ import annotations  
# 允许在类型注解里使用前向引用（例如返回类型/类名字符串）

from scrapy.settings import Settings 
 # Scrapy 的配置对象（类似 dict，但支持优先级与类型处理）

from crawler_center.core.config import AppSettings  
# 你们项目的统一配置来源（超时/并发/UA 等）


def build_scrapy_settings(app_settings: AppSettings) -> Settings:
    """
    构建并返回 Scrapy Settings（生产环境可复用）。

    作用：
    - 把业务侧 AppSettings（你们项目配置）映射成 Scrapy 可识别的 Settings。
    - 用于初始化 CrawlerRunner/CrawlerProcess，决定爬虫的网络行为、并发策略、中间件与管道等。

    注意：
    - Scrapy Settings 是“运行级配置”，影响整个爬虫执行期间的默认行为。
    """
    settings = Settings()  # 创建一个空的 Scrapy Settings 容器

    # -------------------------
    # 网络请求基础配置（生产常用）
    # -------------------------

    # User-Agent：用于模拟浏览器/客户端身份，降低被目标站点拦截概率
    settings.set("USER_AGENT", app_settings.default_user_agent)

    # 下载超时：单个 HTTP 请求在该秒数内未完成则判定超时（触发 retry/失败处理）
    settings.set("DOWNLOAD_TIMEOUT", app_settings.default_timeout_sec)

    # 重试次数：请求超时/连接错误/部分状态码等情况下的最大重试次数
    settings.set("RETRY_TIMES", app_settings.crawler_retry_times)

    # 全局并发：同一时间 Scrapy 发起的最大请求数（影响吞吐与被封风险）
    settings.set("CONCURRENT_REQUESTS", app_settings.crawler_concurrent_requests)

    # robots.txt：是否遵守目标站点 robots 协议
    # 生产爬虫通常按业务需求选择；此处设 False 表示不受 robots 限制（注意合规性）
    settings.set("ROBOTSTXT_OBEY", False)

    # Cookie：开启后会维护会话（适合需要登录态/分布式会话/反爬依赖 cookie 的站点）
    settings.set("COOKIES_ENABLED", True)

    # Telnet Console：Scrapy 自带远程调试入口，生产环境通常关闭（安全与噪声）
    settings.set("TELNETCONSOLE_ENABLED", False)

    # 日志开关：这里关闭 LOG，适合“由外部系统统一收敛日志”的场景
    # 若需要排查问题，建议在环境变量或配置中按需打开
    settings.set("LOG_ENABLED", False)

    # -------------------------
    # 中间件（Downloader Middlewares）
    # -------------------------
    # Downloader Middleware：请求发出前、响应返回后都会经过的钩子机制
    # 常用于：代理设置/UA 轮换/失败重试增强/请求签名/反爬处理等
    settings.set(
        "DOWNLOADER_MIDDLEWARES",
        {
            # 代理健康中间件（示例用途：为请求注入代理、统计失败率、熔断不可用代理等）
            # 数值为优先级（越小越先执行）；543 表示该中间件的执行顺序在 Scrapy 中间件链中的位置
            "crawler_center.crawler.middlewares.ProxyHealthMiddleware": 543,
        },
    )

    # -------------------------
    # 管道（Item Pipelines）
    # -------------------------
    # Item Pipeline：Spider yield 出 item 后的处理链
    # 常用于：清洗/去重/结构化/校验/落库/写队列/写文件等
    settings.set(
        "ITEM_PIPELINES",
        {
            # 内存管道（示例用途：将 item 暂存到内存供上层服务收集；或做轻量清洗）
            # 优先级越小越先执行；100 表示相对靠前
            "crawler_center.crawler.pipelines.MemoryItemPipeline": 100,
        },
    )

    # 返回给上层 Runner 使用（例如 CrawlerRunner(settings=...)）
    return settings