#!/usr/bin/env python3
# runtime/app.py
"""
Atlas Runtime v8.0 LTS - 主入口
统一信号管理，优雅关闭
"""

import asyncio
import logging
import sys
import yaml
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.bootstrap import Bootstrap

logger = logging.getLogger("Atlas.Runtime")


class AtlasApp:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self._load_config()
        self.bootstrap: Optional[Bootstrap] = None
        self._shutdown_event = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

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

        logger.info("Atlas Runtime is running. Press Ctrl+C to stop.")
        await self._shutdown_event.wait()

    async def stop(self) -> None:
        logger.info("Stopping Atlas Runtime...")
        if self.bootstrap:
            # 按逆序停止
            components = [
                'trigger_server',
                'scheduler',
                'rotator',
                'battery_aware',
                'state_manager',
                'storage',
            ]
            for name in components:
                comp = self.bootstrap.get_component(name)
                if comp and hasattr(comp, 'stop'):
                    try:
                        await comp.stop()
                        logger.debug(f"{name} stopped")
                    except Exception as e:
                        logger.error(f"Error stopping {name}: {e}")
        self._shutdown_event.set()
        logger.info("Atlas Runtime stopped")

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        # 统一信号处理
        def signal_handler():
            if loop.is_running():
                asyncio.create_task(self.stop())
            else:
                loop.run_until_complete(self.stop())

        signal.signal(signal.SIGTERM, lambda s, f: signal_handler())
        signal.signal(signal.SIGINT, lambda s, f: signal_handler())

        try:
            loop.run_until_complete(self.start())
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            if not self._shutdown_event.is_set():
                loop.run_until_complete(self.stop())
            loop.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/runtime.yaml")
    args = parser.parse_args()
    app = AtlasApp(args.config)
    app.run()