# transport/trigger_server.py
"""
双模触发器 - 修复版
增加并发限制，防止 FIFO 高流量时任务堆积
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

from core.trigger_handler import BackpressureError

logger = logging.getLogger("Atlas.TriggerTransport")


class HybridTriggerServer:
    def __init__(
        self,
        trigger_handler: Callable[[dict], Awaitable[Any]],
        fifo_path: str = "/data/data/com.termux/files/usr/tmp/atlas_trigger.fifo",
        http_port: int = 8787,
        http_host: str = "127.0.0.1",
        max_concurrent_tasks: int = 100,
    ):
        self.trigger_handler = trigger_handler
        self.fifo_path = fifo_path
        self.http_port = http_port
        self.http_host = http_host
        self.max_concurrent_tasks = max_concurrent_tasks

        self._running = False
        self._fifo_task: Optional[asyncio.Task] = None
        self._http_runner = None
        self._http_site = None

        self._fifo_fd: Optional[int] = None
        self._read_buffer = b""
        self._fifo_reader_registered = False
        self._semaphore = asyncio.Semaphore(max_concurrent_tasks)

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

        os.mkfifo(self.fifo_path, 0o666)
        self._fifo_fd = os.open(self.fifo_path, os.O_RDWR | os.O_NONBLOCK)
        logger.info(f"FIFO ready: {self.fifo_path}")

    async def _fifo_event_loop(self) -> None:
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

        # 若并发数已达上限，暂时不读取，等待任务释放
        if self._semaphore.locked():
            return

        try:
            data = os.read(self._fifo_fd, 4096)
            if not data:
                return

            self._read_buffer += data
            while b'\n' in self._read_buffer:
                line, self._read_buffer = self._read_buffer.split(b'\n', 1)
                if line:
                    # 使用信号量控制并发
                    asyncio.create_task(self._process_line_with_semaphore(line))
        except BlockingIOError:
            pass
        except Exception as e:
            logger.error(f"FIFO read error: {e}")

    async def _process_line_with_semaphore(self, line: bytes) -> None:
        """使用信号量限制并发处理数"""
        async with self._semaphore:
            await self._process_line(line)

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
        return web.json_response({
            "status": "healthy",
            "fifo": os.path.exists(self.fifo_path),
            "fifo_fd": self._fifo_fd is not None
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