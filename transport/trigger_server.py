# transport/trigger_server.py
"""
双模触发器服务器（FIFO 主 + HTTP 备）

修复要点：
1. FIFO 使用 asyncio 原生事件驱动（loop.add_reader）替代阻塞线程读取
2. HTTP 端口冲突时启用 SO_REUSEADDR，避免误杀自身进程
3. 完善生命周期管理（start/stop）
4. 完整的错误处理与日志记录

关联修复：R1, R6, R9, 端口冲突安全处理
"""

import os
import json
import asyncio
import logging
import signal
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
        """
        Args:
            trigger_handler: 异步回调函数，接收触发数据字典
            fifo_path: FIFO 管道路径
            http_port: HTTP 服务端口
            http_host: HTTP 服务绑定地址
        """
        self.trigger_handler = trigger_handler
        self.fifo_path = fifo_path
        self.http_port = http_port
        self.http_host = http_host

        self._running = False
        self._fifo_task: Optional[asyncio.Task] = None
        self._http_runner = None
        self._http_site = None

        # FIFO 相关
        self._fifo_fd: Optional[int] = None
        self._read_buffer = b""

    async def start(self) -> None:
        """启动双模服务器"""
        if self._running:
            return
        self._running = True

        # 1. 启动 FIFO 主通道
        await self._setup_fifo()
        self._fifo_task = asyncio.create_task(self._fifo_event_loop())

        # 2. 启动 HTTP 备选通道
        await self._setup_http()

        logger.info(
            f"Hybrid trigger server started: FIFO={self.fifo_path}, "
            f"HTTP={self.http_host}:{self.http_port}"
        )

    # ---------- FIFO 主通道 ----------
    async def _setup_fifo(self) -> None:
        """创建并配置 FIFO 管道"""
        if os.path.exists(self.fifo_path):
            try:
                os.unlink(self.fifo_path)
            except OSError as e:
                logger.warning(f"Failed to remove old FIFO: {e}")

        os.mkfifo(self.fifo_path, 0o666)
        self._fifo_fd = os.open(self.fifo_path, os.O_RDWR | os.O_NONBLOCK)
        logger.info(f"FIFO ready: {self.fifo_path}")

    async def _fifo_event_loop(self) -> None:
        """异步事件循环：使用 loop.add_reader 监听 FIFO 可读事件"""
        logger.info("FIFO event loop started")
        loop = asyncio.get_running_loop()
        self._read_buffer = b""

        loop.add_reader(self._fifo_fd, self._on_fifo_readable)

        try:
            while self._running:
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
        finally:
            loop.remove_reader(self._fifo_fd)
            logger.info("FIFO event loop stopped")

    def _on_fifo_readable(self) -> None:
        """FIFO 可读回调（事件循环中执行）"""
        if not self._running:
            return

        try:
            data = os.read(self._fifo_fd, 4096)
            if not data:
                # O_RDWR 模式下不会出现 EOF，但保留防护
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
        """处理一行 JSON 数据"""
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

    async def _reopen_fifo(self) -> None:
        """重新打开 FIFO（当管道损坏时）"""
        if self._fifo_fd is not None:
            try:
                os.close(self._fifo_fd)
            except OSError:
                pass
        await self._setup_fifo()
        loop = asyncio.get_running_loop()
        loop.add_reader(self._fifo_fd, self._on_fifo_readable)
        logger.info("FIFO reconnected")

    # ---------- HTTP 备选通道 ----------
    async def _setup_http(self) -> None:
        """启动 HTTP 服务（备选），启用 SO_REUSEADDR 避免端口冲突"""
        if web is None:
            logger.warning("aiohttp not installed, HTTP server disabled")
            return

        app = web.Application()
        app.router.add_post('/trigger', self._handle_http_trigger)
        app.router.add_get('/health', self._handle_health)
        app.router.add_get('/ready', self._handle_ready)

        self._http_runner = web.AppRunner(app)
        await self._http_runner.setup()

        # 关键修复：启用地址复用，避免 “Address already in use”
        self._http_site = web.TCPSite(
            self._http_runner,
            host=self.http_host,
            port=self.http_port,
            reuse_address=True,   # 允许端口复用
            reuse_port=False,     # 不建议开启端口复用，仅地址复用即可
        )

        try:
            await self._http_site.start()
        except OSError as e:
            if "Address already in use" in str(e):
                logger.error(
                    f"Port {self.http_port} still in use. "
                    f"Please ensure no other process is using it. "
                    f"You may try: fuser -k {self.http_port}/tcp"
                )
                raise RuntimeError(f"Port {self.http_port} already in use") from e
            else:
                logger.error(f"HTTP server start failed: {e}")
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

    # ---------- 生命周期管理 ----------
    async def stop(self) -> None:
        """停止服务器，释放资源"""
        self._running = False

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