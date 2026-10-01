"""列类型推断库：逐格判型、列级定类型、冲突证据收集。"""

from .core import (
    TYPE_PRIORITY,
    classify,
    column_type,
    dominant_type,
)

__all__ = ["TYPE_PRIORITY", "classify", "column_type", "dominant_type"]
