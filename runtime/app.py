#!/usr/bin/env python3
# runtime/app.py
"""
Atlas Runtime v8.0 LTS - 主入口
统一信号管理，幂等停止，优雅关闭
"""

import asyncio
import logging
import sys
import yaml
import signal
from pathlib import Path
from typing import Optional, List, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.bootstrap import Bootstrap

logger = logging.getLogger("Atlas.Runtime")


class AtlasApp:
    def __init__(self, config_path: str = "config/runtime.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self.bootstrap: Optional[Bootstrap] = None
        self._shutdown_event = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_stopping = False
        self._services: List[Any] = []

    def _load_config(self) -> dict:
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    async def start(self) -> None:
        """启动应用，注册信号处理器"""
        log_level = self.config['runtime'].get('log_level', 'INFO')
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        logger.info("Atlas Runtime v8.0 LTS starting...")
        logger.info(f"Config: {self.config_path}")

        # 初始化所有组件
        self.bootstrap = Bootstrap(self.config)
        await self.bootstrap.boot()
        self._services = self.bootstrap.get_all_components()

        # 使用 asyncio 原生信号处理器（避免跨 Loop 问题）
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:
                # Windows 回退方案
                signal.signal(sig, lambda s, f: asyncio.create_task(self.stop()))

        logger.info("Atlas Runtime is running. Press Ctrl+C to stop.")
        await self._shutdown_event.wait()

    async def stop(self) -> None:
        """幂等停止：多次调用安全，不会重复关闭组件"""
        if self._is_stopping:
            logger.debug("Stop already in progress, ignoring")
            return
        self._is_stopping = True
        logger.info("Stopping Atlas Runtime...")

        # 按逆序停止所有组件
        for service in reversed(self._services):
            if hasattr(service, 'stop'):
                try:
                    await service.stop()
                    logger.debug(f"{service.__class__.__name__} stopped")
                except Exception as e:
                    logger.error(f"Error stopping {service.__class__.__name__}: {e}")

        # 取消所有残余后台任务
        loop = asyncio.get_running_loop()
        tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
        if tasks:
            logger.info(f"Cancelling {len(tasks)} residual tasks...")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        self._shutdown_event.set()
        logger.info("Atlas Runtime stopped")

    def run(self) -> None:
        """同步入口"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        try:
            loop.run_until_complete(self.start())
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            raise
        finally:
            if not self._shutdown_event.is_set():
                loop.run_until_complete(self.stop())
            # 清理残留任务
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
            logger.info("Event loop closed")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/runtime.yaml")
    args = parser.parse_args()
    app = AtlasApp(args.config)
    app.run()