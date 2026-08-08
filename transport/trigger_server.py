# transport/trigger_server.py
"""
双模触发器 - 修复版（P1 F3）
背压计数 + HTTP 429 响应，避免静默丢消息
"""

import os
import json
import asyncio
import logging
from typing import Callable, Awaitable, Optional, Any

try:
    from aiohttp import web
except ImportError:
    web = None

from models.errors import BackpressureError

logger = logging.getLogger("Atlas.TriggerTransport")


class HybridTriggerServer:
    def __init__(
        self,
        trigger_handler: Callable[[dict], Awaitable[Any]],
        fifo_path: str = "/data/data/com.termux/files/usr/tmp/atlas_trigger.fifo",
        http_port: int = 8787,
        http_host: str = "127.0.0.1",
        max_concurrent_tasks: int = 100,
        memory_controller=None,
        circuit_breaker=None,
        dedup_filter=None,
    ):
        self.trigger_handler = trigger_handler
        self.fifo_path = fifo_path
        self.http_port = http_port
        self.http_host = http_host
        self.max_concurrent_tasks = max_concurrent_tasks
        self.memory_controller = memory_controller  # v9.1 内存门控
        self.circuit_breaker = circuit_breaker      # v9.1 熔断器
        self.dedup_filter = dedup_filter            # v9.1 去重

        self._running = False
        self._fifo_task: Optional[asyncio.Task] = None
        self._http_runner = None
        self._http_site = None

        self._fifo_fd: Optional[int] = None
        self._read_buffer = b""
        self._fifo_reader_registered = False
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._active_task_count = 0  # 显式计数器，避免访问 Semaphore 私有属性
        self._backlog_count = 0

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        await self._setup_fifo()
        self._fifo_task = asyncio.create_task(self._fifo_event_loop())
        await self._setup_http()

        logger.info(
            f"Hybrid trigger server started: FIFO={self.fifo_path}, "
            f"HTTP={self.http_host}:{self.http_port}, "
            f"max_concurrent={self.max_concurrent_tasks}"
        )

    # ---------- FIFO 主通道 ----------
    async def _setup_fifo(self) -> None:
        if os.path.exists(self.fifo_path):
            try:
                os.unlink(self.fifo_path)
            except OSError as e:
                logger.warning(f"Failed to remove old FIFO: {e}")

        try:
            os.mkfifo(self.fifo_path, 0o666)
        except AttributeError:
            logger.warning("os.mkfifo not available (non-Unix platform); FIFO disabled")
            self._fifo_fd = None
            self._fifo_task = None
            return

        self._fifo_fd = os.open(self.fifo_path, os.O_RDWR | os.O_NONBLOCK)
        logger.info(f"FIFO ready: {self.fifo_path}")

    async def _fifo_event_loop(self) -> None:
        if self._fifo_fd is None:
            logger.info("FIFO disabled; event loop skipped")
            while self._running:
                await asyncio.sleep(1.0)
            return

        logger.info("FIFO event loop started")
        loop = asyncio.get_running_loop()
        self._read_buffer = b""

        loop.add_reader(self._fifo_fd, self._on_fifo_readable)
        self._fifo_reader_registered = True

        try:
            while self._running:
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
        finally:
            loop.remove_reader(self._fifo_fd)
            self._fifo_reader_registered = False
            logger.info("FIFO event loop stopped")

    def _on_fifo_readable(self) -> None:
        if not self._running:
            return

        try:
            data = os.read(self._fifo_fd, 4096)
            if not data:
                return

            self._read_buffer += data

            # 背压：如果并发已满，将缓冲中的完整行丢弃并记录积压
            if self._semaphore.locked():
                while b'\n' in self._read_buffer:
                    line, self._read_buffer = self._read_buffer.split(b'\n', 1)
                    if line:
                        self._backlog_count += 1
                # 缓冲区超过安全阈值时强制截断，防止内存无限增长
                if len(self._read_buffer) > 65536:  # 64KB 上限
                    logger.critical(
                        f"FIFO buffer overflow under backpressure, "
                        f"discarding {len(self._read_buffer)} bytes, "
                        f"backlog={self._backlog_count}"
                    )
                    self._read_buffer = b""
                if self._backlog_count > 0 and self._backlog_count % 50 == 0:
                    logger.warning(f"FIFO backlog: {self._backlog_count} messages dropped")
                return

            # 正常路径：解析换行并提交处理
            while b'\n' in self._read_buffer:
                line, self._read_buffer = self._read_buffer.split(b'\n', 1)
                if line:
                    asyncio.create_task(self._process_line_with_semaphore(line))
        except BlockingIOError:
            pass
        except Exception as e:
            logger.error(f"FIFO read error: {e}")

    async def _process_line_with_semaphore(self, line: bytes) -> None:
        self._active_task_count += 1
        try:
            async with self._semaphore:
                # 处理前检查积压计数（在信号量释放时清理）
                if self._backlog_count > 0:
                    self._backlog_count -= 1
                await self._process_line(line)
        finally:
            self._active_task_count -= 1

    async def _process_line(self, line: bytes) -> None:
        try:
            line_str = line.decode('utf-8').strip()
            if not line_str:
                return
            data = json.loads(line_str)
            await self.trigger_handler(data)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from FIFO: {line[:100]}... ({e})")
        except Exception as e:
            logger.error(f"Trigger handler error: {e}")

    # ---------- HTTP 备选通道 ----------
    async def _setup_http(self) -> None:
        if web is None:
            logger.warning("aiohttp not installed, HTTP server disabled")
            return

        app = web.Application()
        app.router.add_post('/trigger', self._handle_http_trigger)
        app.router.add_get('/health', self._handle_health)
        app.router.add_get('/ready', self._handle_ready)

        self._http_runner = web.AppRunner(app)
        await self._http_runner.setup()

        self._http_site = web.TCPSite(
            self._http_runner,
            host=self.http_host,
            port=self.http_port,
            reuse_address=True,
        )

        try:
            await self._http_site.start()
        except OSError as e:
            if "Address already in use" in str(e):
                logger.error(
                    f"Port {self.http_port} already in use. "
                    f"Please free the port with: fuser -k {self.http_port}/tcp"
                )
                raise RuntimeError(f"Port {self.http_port} already in use") from e
            raise

    async def _handle_http_trigger(self, request: web.Request) -> web.Response:
        # v9.1: 内存门控 — 内存压力大时返回 503
        if self.memory_controller is not None:
            gate = await self.memory_controller.can_accept()
            if gate.state.name == "HARD_REJECT":
                logger.warning(
                    f"HTTP trigger rejected: {gate.reason}"
                )
                return web.json_response(
                    {"status": "error", "message": "Service unavailable due to memory pressure"},
                    status=503
                )

        # 检查背压
        if self._semaphore.locked():
            return web.json_response(
                {"status": "error", "message": "Too many requests, backpressure active"},
                status=429
            )

        try:
            data = await request.json()
            result = await self.trigger_handler(data)
            return web.json_response({"status": "ok", "result": result})
        except BackpressureError as e:
            logger.warning(f"Backpressure triggered: {e}")
            return web.json_response(
                {"status": "error", "message": str(e)},
                status=429
            )
        except json.JSONDecodeError:
            return web.json_response({"status": "error", "message": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"HTTP trigger error: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def _handle_health(self, request: web.Request) -> web.Response:
        # v9.1: 上报内存门控、熔断器、去重状态
        memory_gate = "unavailable"
        if self.memory_controller is not None:
            try:
                memory_gate = self.memory_controller.state.name
            except Exception:
                pass

        circuit_state = "unavailable"
        if self.circuit_breaker is not None:
            try:
                circuit_state = self.circuit_breaker.get_state()
            except Exception:
                pass

        dedup_stats = "unavailable"
        if self.dedup_filter is not None:
            try:
                dedup_stats = {
                    "size": len(self.dedup_filter._entries),
                    "duplicates_found": self.dedup_filter._duplicates_found,
                }
            except Exception:
                pass

        return web.json_response({
            "status": "healthy",
            "fifo": os.path.exists(self.fifo_path),
            "fifo_fd": self._fifo_fd is not None,
            "concurrent_tasks": self._active_task_count,
            "max_concurrent": self.max_concurrent_tasks,
            "backlog": self._backlog_count,
            "memory_gate": memory_gate,
            "circuit_breaker": circuit_state,
            "dedup": dedup_stats,
        })

    async def _handle_ready(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ready"})

    # ---------- 生命周期管理 ----------
    async def stop(self) -> None:
        self._running = False

        if self._fifo_fd is not None:
            try:
                loop = asyncio.get_running_loop()
                if self._fifo_reader_registered:
                    loop.remove_reader(self._fifo_fd)
                    self._fifo_reader_registered = False
            except Exception as e:
                logger.debug(f"Failed to remove_reader on stop: {e}")

        if self._fifo_task and not self._fifo_task.done():
            self._fifo_task.cancel()
            try:
                await self._fifo_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error stopping FIFO task: {e}")

        if self._fifo_fd is not None:
            try:
                os.close(self._fifo_fd)
            except OSError:
                pass
            self._fifo_fd = None

        if os.path.exists(self.fifo_path):
            try:
                os.unlink(self.fifo_path)
            except OSError:
                pass

        if self._http_runner:
            try:
                await self._http_runner.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning HTTP runner: {e}")

        logger.info("Hybrid trigger server stopped")