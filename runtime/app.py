#!/usr/bin/env python3
# runtime/app.py
"""
Atlas Runtime v8.0 LTS - 主入口（修复版 F6）
统一项目根目录路径，方便 import
"""

import sys
from pathlib import Path

# 将项目根目录加入 sys.path（确保所有模块可导入）
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
import logging
import signal
import yaml
from typing import Optional, List, Any

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
        log_level = self.config['runtime'].get('log_level', 'INFO')
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        logger.info("Atlas Runtime v8.0 LTS starting...")
        logger.info(f"Config: {self.config_path}")

        self.bootstrap = Bootstrap(self.config)
        await self.bootstrap.boot()
        self._services = self.bootstrap.get_all_components()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:
                signal.signal(sig, lambda s, f: asyncio.create_task(self.stop()))

        logger.info("Atlas Runtime is running. Press Ctrl+C to stop.")
        await self._shutdown_event.wait()

    async def stop(self) -> None:
        if self._is_stopping:
            logger.debug("Stop already in progress, ignoring")
            return
        self._is_stopping = True
        logger.info("Stopping Atlas Runtime...")

        for service in reversed(self._services):
            if hasattr(service, 'stop'):
                try:
                    await service.stop()
                    logger.debug(f"{service.__class__.__name__} stopped")
                except Exception as e:
                    logger.error(f"Error stopping {service.__class__.__name__}: {e}")

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