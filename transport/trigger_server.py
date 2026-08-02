# transport/trigger_server.py
import os
import json
import asyncio
import logging
from typing import Callable, Awaitable, Optional, Any

try:
    from aiohttp import web
except ImportError:
    web = None

logger = logging.getLogger("Atlas.TriggerTransport")


class HybridTriggerServer:
    def __init__(
        self,
        trigger_handler: Callable[[dict], Awaitable[Any]],
        fifo_path: str = "/data/data/com.termux/files/usr/tmp/atlas_trigger.fifo",
        http_port: int = 8787,
        http_host: str = "127.0.0.1",
    ):
        self.trigger_handler = trigger_handler
        self.fifo_path = fifo_path
        self.http_port = http_port
        self.http_host = http_host

        self._running = False
        self._fifo_task: Optional[asyncio.Task] = None
        self._http_runner = None
        self._http_site = None

        self._fifo_fd: Optional[int] = None
        self._read_buffer = b""
        # [FIX] 添加注册标志，避免停止时重复移除
        self._fifo_reader_registered = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        await self._setup_fifo()
        self._fifo_task = asyncio.create_task(self._fifo_event_loop())
        await self._setup_http()

        logger.info(
            f"Hybrid trigger server started: FIFO={self.fifo_path}, "
            f"HTTP={self.http_host}:{self.http_port}"
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
        self._fifo_reader_registered = True   # [FIX] 标记已注册

        try:
            while self._running:
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
        finally:
            # [FIX] 注销时重置标志
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
            while b'\n' in self._read_buffer:
                line, self._read_buffer = self._read_buffer.split(b'\n', 1)
                if line:
                    asyncio.create_task(self._process_line(line))
        except BlockingIOError:
            pass
        except Exception as e:
            logger.error(f"FIFO read error: {e}")

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

    # ---------- 生命周期管理（修复移除 reader 顺序） ----------
    async def stop(self) -> None:
        self._running = False

        # [FIX] 只有确认已注册才尝试移除，避免 KeyError
        if self._fifo_fd is not None:
            try:
                loop = asyncio.get_running_loop()
                if self._fifo_reader_registered:
                    loop.remove_reader(self._fifo_fd)
                    self._fifo_reader_registered = False
            except Exception as e:
                logger.debug(f"Failed to remove_reader on stop: {e}")

        # 取消并等待 FIFO Task
        if self._fifo_task and not self._fifo_task.done():
            self._fifo_task.cancel()
            try:
                await self._fifo_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error stopping FIFO task: {e}")

        # 安全关闭文件描述符
        if self._fifo_fd is not None:
            try:
                os.close(self._fifo_fd)
            except OSError:
                pass
            self._fifo_fd = None

        # 清理管道文件
        if os.path.exists(self.fifo_path):
            try:
                os.unlink(self.fifo_path)
            except OSError:
                pass

        # 清理 HTTP 服务
        if self._http_runner:
            try:
                await self._http_runner.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning HTTP runner: {e}")

        logger.info("Hybrid trigger server stopped")