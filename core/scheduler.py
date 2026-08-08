# core/scheduler.py
"""
任务调度器。

v9.0 架构优化：
- Task / TaskStatus 已迁移至 models/task.py（纯数据契约）
- executor 参数改用 BaseExecutor 协议，调用 executor.execute(cmd, timeout)
  代替原来的函数调用 executor(cmd, timeout)
"""

import asyncio
import time
import logging
import uuid
from typing import Dict, Optional, Any, Callable, Awaitable

from models.task import Task, TaskStatus
from executors.base import BaseExecutor

logger = logging.getLogger("Atlas.Scheduler")


class Scheduler:
    def __init__(
        self,
        executor: BaseExecutor,
        resource_lock,
        max_pending: int = 5000,
    ):
        """
        Args:
            executor: 实现 BaseExecutor 协议的执行器实例（如 SafeShellExecutor）
            resource_lock: ResourceLock 实例
            max_pending: pending 队列最大长度
        """
        self.executor = executor
        self.resource_lock = resource_lock
        self.max_pending = max_pending

        self._pending: asyncio.Queue = asyncio.Queue(maxsize=max_pending)
        self._delay: Dict[str, Task] = {}
        self._active: Dict[str, Task] = {}
        self._all_tasks: Dict[str, Task] = {}

        self._running = False
        self._schedule_task: Optional[asyncio.Task] = None
        self._worker_task: Optional[asyncio.Task] = None

        self.on_task_complete: Optional[Callable[[Task], Awaitable[None]]] = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._schedule_task = asyncio.create_task(self._schedule_loop())
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Scheduler started")

    async def submit(self, action: Dict[str, Any], delay: float = 0.0) -> str:
        if self._pending.qsize() >= self.max_pending:
            raise RuntimeError("Pending queue full")

        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            action=action,
            status=TaskStatus.PENDING,
            scheduled_at=time.time() + delay if delay > 0 else None,
        )
        self._all_tasks[task_id] = task

        if delay > 0:
            self._delay[task_id] = task
            logger.debug(f"Task {task_id} delayed for {delay}s")
        else:
            await self._pending.put(task)
            logger.debug(f"Task {task_id} enqueued")

        return task_id

    async def _schedule_loop(self) -> None:
        while self._running:
            try:
                now = time.time()
                to_move = []
                for task_id, task in list(self._delay.items()):
                    if task.scheduled_at and task.scheduled_at <= now:
                        to_move.append(task_id)

                for task_id in to_move:
                    task = self._delay.pop(task_id)
                    task.status = TaskStatus.PENDING
                    await self._pending.put(task)
                    logger.debug(f"Delayed task {task_id} moved to pending")

                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Schedule loop error: {e}")

    async def _worker_loop(self) -> None:
        while self._running:
            task = None
            try:
                task = await self._pending.get()
                if not self._running:
                    self._pending.task_done()
                    break

                if task.resource:
                    acquired = await self.resource_lock.try_acquire(
                        task.resource,
                        task.id,
                        ttl=60,
                    )
                    if not acquired:
                        self._pending.task_done()
                        task.scheduled_at = time.time() + 5
                        self._delay[task.id] = task
                        continue

                task.status = TaskStatus.EXECUTING
                task.started_at = time.time()
                self._active[task.id] = task

                try:
                    await self._execute_task(task)
                except asyncio.CancelledError:
                    logger.warning(f"Task {task.id} cancelled")
                    if task.resource:
                        await self.resource_lock.release(task.resource, task.id)
                    self._active.pop(task.id, None)
                    raise
                finally:
                    self._pending.task_done()

            except asyncio.CancelledError:
                if task and task.id in self._active:
                    self._active.pop(task.id, None)
                    if task.resource:
                        await self.resource_lock.release(task.resource, task.id)
                    self._pending.task_done()
                break
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                if task:
                    self._pending.task_done()

    async def _execute_task(self, task: Task) -> None:
        """补丁 A：提取命令字符串，而不是传递整个 Task 对象"""
        # 从 action 中提取命令
        cmd = task.action.get("command") or task.action.get("cmd")
        if not cmd and isinstance(task.action, str):
            cmd = task.action
        elif not cmd:
            task.status = TaskStatus.FAILED
            task.error = "No command in task action"
            task.completed_at = time.time()
            logger.error(f"Task {task.id} has no command")
            self._active.pop(task.id, None)
            if task.resource:
                await self.resource_lock.release(task.resource, task.id)
            return

        # 确保是字符串
        if not isinstance(cmd, str):
            cmd = str(cmd)
        cmd = cmd.strip()
        if not cmd:
            task.status = TaskStatus.FAILED
            task.error = "Empty command"
            task.completed_at = time.time()
            logger.error(f"Task {task.id} has empty command")
            self._active.pop(task.id, None)
            if task.resource:
                await self.resource_lock.release(task.resource, task.id)
            return

        timeout = task.action.get("timeout", 5.0)

        try:
            # 通过 BaseExecutor 协议调用 execute()，返回 ExecutorResult
            result = await self.executor.execute(cmd=cmd, timeout=timeout)
            if result.success:
                task.status = TaskStatus.SUCCESS
                task.result = result
                task.completed_at = time.time()
                logger.info(f"Task {task.id} completed successfully")
            else:
                # 执行器报告失败（非零退出码等），这是正常的命令执行结果，
                # 不应触发重试机制。重试仅适用于 TimeoutError 等异常情况。
                task.status = TaskStatus.FAILED
                task.error = result.error or "Execution returned failure"
                task.result = result
                task.completed_at = time.time()
                logger.error(f"Task {task.id} failed: {task.error}")
                # 释放资源锁（如果有），但不重试
                if task.resource:
                    await self.resource_lock.release(task.resource, task.id)
        except asyncio.TimeoutError:
            task.status = TaskStatus.TIMEOUT
            task.error = "Execution timeout"
            task.completed_at = time.time()
            logger.warning(f"Task {task.id} timed out")
            await self._release_lock_and_retry(task)
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = time.time()
            logger.error(f"Task {task.id} failed: {e}")
            await self._release_lock_and_retry(task)
        finally:
            self._active.pop(task.id, None)
            if self.on_task_complete:
                # 使用 fire-and-forget + 异常保护，确保回调异常不会丢失
                asyncio.create_task(
                    self._safe_on_task_complete(task)
                )

    async def _safe_on_task_complete(self, task: Task) -> None:
        """安全地调用 on_task_complete 回调，捕获并记录异常。"""
        try:
            await self.on_task_complete(task)
        except Exception as e:
            logger.error(f"on_task_complete callback failed for task {task.id}: {e}", exc_info=True)

    async def _release_lock_and_retry(self, task: Task) -> None:
        if task.resource:
            await self.resource_lock.release(task.resource, task.id)

        if task.retries < task.max_retries:
            task.retries += 1
            task.status = TaskStatus.PENDING
            delay = 2 ** (task.retries - 1)
            task.scheduled_at = time.time() + delay
            self._delay[task.id] = task
            logger.info(f"Task {task.id} scheduled for retry #{task.retries} in {delay}s")
        else:
            task.status = TaskStatus.DEAD
            task.completed_at = time.time()
            logger.error(f"Task {task.id} reached max retries, marked DEAD")

    async def get_task(self, task_id: str) -> Optional[Task]:
        return self._all_tasks.get(task_id)

    async def stop(self) -> None:
        self._running = False
        if self._schedule_task:
            self._schedule_task.cancel()
            try:
                await self._schedule_task
            except asyncio.CancelledError:
                pass
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")