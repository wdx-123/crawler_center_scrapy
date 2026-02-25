from __future__ import annotations

from typing import Any


class MemoryItemPipeline:
    def process_item(self, item: Any, spider: object = None) -> Any:
        return item
