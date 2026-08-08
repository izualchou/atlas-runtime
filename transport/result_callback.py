# transport/result_callback.py
"""
结果回写模块（Result Callback）。

通过 Scheduler.on_task_complete 回调钩子，将任务执行结果异步写入
/sdcard/atlas_shared/ 共享目录，供 Tasker 读取和处理。

设计原则:
- 原子写入: tempfile + os.replace() 原子重命名，防止 Tasker 读到半写入的 JSON
- 磁盘空间检查: 写入前检查可用空间 < 10MB 时记录 WARNING 但不阻塞
- JSON 校验: 写入后立即读取并验证 JSON 合法性
- Termux 兼容: /sdcard/ 对应 Android 共享存储，Termux 通过 termux-setup-storage 授权后可用

v9.1: 新增 last_result.json（总是覆盖最新）和带 correlation_id 的历史文件双轨写入。
"""

import json
import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("Atlas.ResultCallback")

# 默认共享目录
DEFAULT_SHARED_DIR = "/sdcard/atlas_shared"


@dataclass
class ResultCallbackConfig:
    """结果回写配置"""
    shared_dir: str = DEFAULT_SHARED_DIR
    max_history_files: int = 100       # 历史结果文件最大保留数
    min_free_space_mb: int = 10        # 最小空闲空间（MB），低于此值仅告警
    enable_history: bool = True        # 是否写入带时间戳的历史文件
    enable_latest: bool = True         # 是否覆盖写入 last_result.json


@dataclass
class CallbackResult:
    """单次回写结果"""
    success: bool
    path: Optional[str] = None
    error: Optional[str] = None
    size_bytes: int = 0


class ResultCallback:
    """
    任务结果回写器。

    典型用法:
        rc = ResultCallback()
        scheduler.register_callback(rc.on_task_complete)
    """

    def __init__(self, config: Optional[ResultCallbackConfig] = None):
        self.config = config or ResultCallbackConfig()
        self._stats = {
            "total_writes": 0,
            "failed_writes": 0,
            "last_write_time": None,
        }

    # ------------------------------------------------------------------
    # Scheduler 回调钩子
    # ------------------------------------------------------------------

    async def on_task_complete(self, task) -> None:
        """
        Scheduler 回调: 任务完成时自动写入结果。

        Args:
            task: models.task.Task 实例
        """
        try:
            payload = self._build_payload(task)
            results: List[CallbackResult] = []

            # 1. 写入最新结果 (last_result.json)
            if self.config.enable_latest:
                result = await self._write_atomic("last_result.json", payload)
                results.append(result)

            # 2. 写入历史文件 (result_<timestamp>_<correlation_id>.json)
            if self.config.enable_history:
                ts = int(time.time())
                cid = getattr(task, 'correlation_id', None) or task.id
                # 文件名安全处理
                safe_cid = "".join(c if c.isalnum() or c in "-_" else "_" for c in cid[:30])
                filename = f"result_{ts}_{safe_cid}.json"
                result = await self._write_atomic(filename, payload)
                results.append(result)

            # 3. 统计数据
            successes = sum(1 for r in results if r.success)
            failures = sum(1 for r in results if not r.success)
            self._stats["total_writes"] += successes
            self._stats["failed_writes"] += failures
            self._stats["last_write_time"] = time.time()

            if failures > 0:
                logger.warning(
                    f"ResultCallback: {successes}/{len(results)} writes succeeded "
                    f"(task={task.id}, status={task.status.value})"
                )

            # 4. 清理旧历史文件 (异步，不阻塞)
            if self.config.enable_history:
                await self._prune_old_files()

        except Exception as e:
            logger.error(
                f"ResultCallback: unhandled error in on_task_complete: {e}",
                exc_info=True,
            )
            self._stats["failed_writes"] += 1

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _build_payload(self, task) -> Dict[str, Any]:
        """从 Task 对象构建输出载荷。"""
        payload = {
            "version": "1.0",
            "task_id": task.id,
            "status": task.status.value,
            "action": task.action,
            "created_at": task.created_at,
            "completed_at": getattr(task, 'completed_at', None),
        }

        # 添加 correlation_id (如果有)
        cid = getattr(task, 'correlation_id', None)
        if cid:
            payload["correlation_id"] = cid

        # 添加结果或错误
        if hasattr(task, 'result') and task.result is not None:
            payload["result"] = {
                "exit_code": getattr(task.result, 'exit_code', None),
                "stdout": getattr(task.result, 'stdout', "")[:4096],
                "stderr": getattr(task.result, 'stderr', "")[:4096],
            }
        if hasattr(task, 'error') and task.error:
            payload["error"] = str(task.error)[:4096]

        return payload

    async def _write_atomic(self, filename: str, payload: Dict[str, Any]) -> CallbackResult:
        """
        原子写入 JSON 文件到共享目录。

        步骤:
        1. 检查共享目录是否存在/可创建
        2. 检查磁盘空间
        3. 写入临时文件
        4. os.replace() 原子重命名
        5. 验证 JSON 合法性
        """
        import asyncio
        return await asyncio.to_thread(self._write_atomic_sync, filename, payload)

    def _write_atomic_sync(self, filename: str, payload: Dict[str, Any]) -> CallbackResult:
        """原子写入的同步实现（在 asyncio.to_thread 中执行）。"""
        shared_dir = Path(self.config.shared_dir)

        try:
            # 1. 确保目录存在
            shared_dir.mkdir(parents=True, exist_ok=True)

            # 2. 磁盘空间检查
            self._check_disk_space(shared_dir)

            # 3. 序列化 JSON
            json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')

            # 4. 写入临时文件
            target = shared_dir / filename
            tmp_suffix = f".tmp.{os.getpid()}"
            fd, tmp_path = tempfile.mkstemp(
                suffix=tmp_suffix,
                prefix=f".{filename}.",
                dir=str(shared_dir),
            )
            try:
                with os.fdopen(fd, 'wb') as f:
                    f.write(json_bytes)
                    f.flush()
                    os.fsync(f.fileno())
            except Exception:
                os.close(fd)
                raise

            # 5. 原子重命名
            os.replace(tmp_path, target)

            # 6. 验证写入
            self._verify_write(target)

            return CallbackResult(
                success=True,
                path=str(target),
                size_bytes=len(json_bytes),
            )

        except Exception as e:
            logger.error(f"ResultCallback: atomic write failed for {filename}: {e}")
            return CallbackResult(
                success=False,
                error=str(e),
            )

    def _check_disk_space(self, directory: Path) -> None:
        """检查磁盘可用空间，不足时记录警告。"""
        try:
            usage = shutil.disk_usage(directory)
            free_mb = usage.free // (1024 * 1024)
            if free_mb < self.config.min_free_space_mb:
                logger.warning(
                    f"ResultCallback: low disk space: {free_mb}MB free "
                    f"(threshold: {self.config.min_free_space_mb}MB)"
                )
        except Exception as e:
            logger.debug(f"ResultCallback: disk space check skipped: {e}")

    def _verify_write(self, target: Path) -> None:
        """验证 JSON 文件合法性（读取并解析）。"""
        try:
            with open(target, 'r', encoding='utf-8') as f:
                json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"ResultCallback: JSON verification failed for {target}: {e}")
            raise

    async def _prune_old_files(self) -> None:
        """清理旧的历史结果文件，保持目录整洁。"""
        import asyncio
        await asyncio.to_thread(self._prune_old_files_sync)

    def _prune_old_files_sync(self) -> None:
        """同步实现：删除超过 max_history_files 数量的旧 result_*.json。"""
        try:
            shared_dir = Path(self.config.shared_dir)
            if not shared_dir.exists():
                return

            # 收集所有 result_*.json 历史文件（排除 last_result.json）
            pattern_files = sorted(
                shared_dir.glob("result_*.json"),
                key=lambda p: p.stat().st_mtime,
            )

            excess = len(pattern_files) - self.config.max_history_files
            if excess > 0:
                for f in pattern_files[:excess]:
                    try:
                        f.unlink()
                        logger.debug(f"ResultCallback: pruned old file {f.name}")
                    except OSError as e:
                        logger.debug(f"ResultCallback: prune failed {f.name}: {e}")

        except Exception as e:
            logger.debug(f"ResultCallback: prune skipped: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取回写统计。"""
        return dict(self._stats)
