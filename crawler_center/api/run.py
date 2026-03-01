"""Windows 开发环境启动入口。

用途：
- 在进入 uvicorn 事件循环前，先把 asyncio policy 设置为 Selector 版本（仅 Windows）
- 规避 ProactorEventLoop 与 Twisted AsyncioSelectorReactor 的兼容问题
"""

from __future__ import annotations

import asyncio
import sys

import uvicorn


def _configure_windows_asyncio_policy() -> None:
    if sys.platform != "win32":
        return
    if isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsSelectorEventLoopPolicy):
        return
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def main() -> None:
    _configure_windows_asyncio_policy()
    from crawler_center.api.main import app

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
