"""LadybugDB: One substrate. All operations. Zero copies."""

from .core.unified_engine import LadybugEngine, connect

__version__ = "0.1.0"
__all__ = ["LadybugEngine", "connect"]
