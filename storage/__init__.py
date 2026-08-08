# storage/__init__.py
# 注意：StorageFullError 和 StorageError 已迁移至 models/errors.py（v9.0 架构优化）。
# 此处保留从 storage.driver 的重新导出以保持向后兼容。
# 新代码应使用 from models import StorageFullError, StorageError 作为规范路径。

from .driver import SingleWriterStorage, StorageFullError, StorageError
from .snapshot import SnapshotManager
from .rotator import EventRotator
from .battery_aware import BatteryAwareCheckpoint

__all__ = [
    "SingleWriterStorage",
    "StorageFullError",      # 弃用导出路径，规范路径见 models.errors.StorageFullError
    "StorageError",           # 弃用导出路径，规范路径见 models.errors.StorageError
    "SnapshotManager",
    "EventRotator",
    "BatteryAwareCheckpoint",
]