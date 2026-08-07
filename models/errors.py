# models/errors.py
"""
通用异常类型。

跨模块共享的异常定义，避免 executors 与 storage 之间的跨层直接依赖。
所有模块均可安全引用本文件中的异常类型。
"""


class AtlasError(Exception):
    """Atlas Runtime 基础异常"""
    pass


class StorageFullError(AtlasError):
    """存储已满，无法写入"""
    pass


class StorageError(AtlasError):
    """存储通用错误"""
    pass


class BackpressureError(AtlasError):
    """
    背压异常。

    当系统过载（存储满、队列满、或前序背压未恢复）时抛出，
    通知调用方稍后重试。
    """
    pass
