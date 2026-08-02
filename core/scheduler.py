# core/scheduler.py
"""
任务调度器（Scheduler）
职责：双队列调度、资源锁协调、重试与超时管理
"""

import asyncio
import time
import logging
import uuid
from typing import Dict, Optional, Any, Callable, Awaitable
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger("Atlas.Scheduler")


class TaskStatus(Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    EXECUTING = "executing"
    SUCCESS = "success"
    TIMEOUT = "timeout"
    FAILED = "failed"
    DEAD = "dead"


@dataclass
class Task:
    id: str
    action: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 5
    retries: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)
    scheduled_at: Optional[float] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    result: Any = None
    correlation_id: Optional[str] = None


class Scheduler:
    def __init__(
        self,
        executor: Callable[[Task], Awaitable[Any]],
        resource_lock,
        max_pending: int = 5000,
    ):
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
        if len(self._pending) >= self.max_pending:
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
            try:
                task = await self._pending.get()
                if not self._running:
                    break

                resource = task.action.get("resource")
                if resource:
                    acquired = await self.resource_lock.try_acquire(
                        resource,
                        task.id,
                        ttl=60,
                    )
                    if not acquired:
                        # 资源被占用，重新放入延迟队列
                        task.scheduled_at = time.time() + 5
                        self._delay[task.id] = task
                        self._pending.task_done()
                        continue

                task.status = TaskStatus.EXECUTING
                task.started_at = time.time()
                self._active[task.id] = task

                asyncio.create_task(self._execute_task(task))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker loop error: {e}")

    async def _execute_task(self, task: Task) -> None:
        try:
            result = await self.executor(task)
            task.status = TaskStatus.SUCCESS
            task.result = result
            task.completed_at = time.time()
            logger.info(f"Task {task.id} completed successfully")

            resource = task.action.get("resource")
            if resource:
                await self.resource_lock.release(resource, task.id)

        except asyncio.TimeoutError:
            task.status = TaskStatus.TIMEOUT
            task.error = "Execution timeout"
            logger.warning(f"Task {task.id} timed out")
            # 超时后锁未释放，在重试前强制释放
            resource = task.action.get("resource")
            if resource:
                await self.resource_lock.release(resource, task.id)
            await self._handle_retry(task)

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            logger.error(f"Task {task.id} failed: {e}")
            resource = task.action.get("resource")
            if resource:
                await self.resource_lock.release(resource, task.id)
            await self._handle_retry(task)

        finally:
            self._active.pop(task.id, None)
            self._pending.task_done()
            if self.on_task_complete:
                asyncio.create_task(self.on_task_complete(task))

    async def _handle_retry(self, task: Task) -> None:
        # 重试前确保锁已释放（安全兜底）
        resource = task.action.get("resource")
        if resource:
            await self.resource_lock.release(resource, task.id)

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