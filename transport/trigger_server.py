# transport/trigger_server.py
import os
import json
import asyncio
import logging
import subprocess
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
        self._fifo_file = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        # 1. FIFO 主通道
        if os.path.exists(self.fifo_path):
            try:
                os.unlink(self.fifo_path)
            except OSError:
                pass
        os.mkfifo(self.fifo_path, 0o666)
        fd = os.open(self.fifo_path, os.O_RDWR | os.O_NONBLOCK)
        self._fifo_file = open(fd, 'r+', buffering=1)
        self._fifo_task = asyncio.create_task(self._fifo_listener())

        # 2. HTTP 备选
        await self._setup_http()

        logger.info(f"Hybrid trigger server started: FIFO={self.fifo_path}, HTTP={self.http_host}:{self.http_port}")

    async def _fifo_listener(self) -> None:
        logger.info("FIFO listener started")
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        try:
            await loop.connect_read_pipe(lambda: protocol, self._fifo_file)
        except Exception as e:
            logger.error(f"Failed to connect FIFO pipe: {e}")
            return

        while self._running:
            try:
                line = await reader.readline()
                if not line:
                    await asyncio.sleep(0.1)
                    continue
                data_str = line.decode('utf-8').strip()
                if not data_str:
                    continue
                data = json.loads(data_str)
                asyncio.create_task(self.trigger_handler(data))
            except asyncio.CancelledError:
                break
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
            except Exception as e:
                logger.error(f"FIFO listener error: {e}")
                await asyncio.sleep(0.5)
        logger.info("FIFO listener stopped")

    async def _setup_http(self) -> None:
        if web is None:
            logger.warning("aiohttp not installed, HTTP disabled")
            return

        app = web.Application()
        app.router.add_post('/trigger', self._handle_http_trigger)
        app.router.add_get('/health', self._handle_health)
        app.router.add_get('/ready', self._handle_ready)

        self._http_runner = web.AppRunner(app)
        await self._http_runner.setup()
        self._http_site = web.TCPSite(self._http_runner, self.http_host, self.http_port)

        try:
            await self._http_site.start()
        except OSError as e:
            if "Address already in use" in str(e):
                logger.warning(f"Port {self.http_port} occupied, attempting to release own processes")
                # 尝试 kill 占用端口的进程（只杀自己可能残留的旧进程）
                pid = str(os.getpid())
                # 使用 fuser 配合 grep 过滤自身PID
                cmd = f"fuser -k {self.http_port}/tcp 2>/dev/null || true"
                subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL)
                await asyncio.sleep(0.5)
                await self._http_site.start()
            else:
                logger.error(f"HTTP start failed: {e}")

    async def _handle_http_trigger(self, request):
        try:
            data = await request.json()
            result = await self.trigger_handler(data)
            return web.json_response({"status": "ok", "result": result})
        except Exception as e:
            logger.error(f"HTTP trigger error: {e}")
            return web.json_response({"status": "error", "message": str(e)}, status=400)

    async def _handle_health(self, request):
        return web.json_response({"status": "healthy", "fifo": os.path.exists(self.fifo_path)})

    async def _handle_ready(self, request):
        return web.json_response({"status": "ready"})

    async def stop(self) -> None:
        self._running = False
        if self._fifo_task:
            self._fifo_task.cancel()
            try:
                await self._fifo_task
            except asyncio.CancelledError:
                pass
        if self._fifo_file:
            self._fifo_file.close()
        if self._http_runner:
            await self._http_runner.cleanup()
        # 可选清理管道
        # if os.path.exists(self.fifo_path):
        #     os.unlink(self.fifo_path)
        logger.info("Hybrid trigger server stopped")