#!/usr/bin/env python3
# runtime/app.py
"""
Atlas Runtime v9.0 — 主入口（Samsung One UI 8.5 + Termux 适配版）

改进：
- 启动时自动检测平台（Samsung / One UI / Termux）
- 集成 HealthChecker 运行状态监控
- 适配 Android asyncio 事件循环策略
- 信号处理器支持 Termux 环境（SIGTERM via termux-services/runit）
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
from core.platform import PlatformInfo
from core.health_checker import HealthChecker

logger = logging.getLogger("Atlas.Runtime")


class AtlasApp:
    """
    Atlas 运行时主应用。

    生命周期: __init__ → start() → [running] → stop() → [exit]
    在三星 One UI 8.5 + Termux 环境中测试通过。
    """

    def __init__(self, config_path: str = "config/runtime.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self.bootstrap: Optional[Bootstrap] = None
        self.health_checker: Optional[HealthChecker] = None
        self.platform_info: Optional[PlatformInfo] = None
        self._shutdown_event = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_stopping = False
        self._services: List[Any] = []

    def _load_config(self) -> dict:
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    async def start(self) -> None:
        """启动 Atlas 运行时"""
        # ---- 1. 日志初始化 ----
        log_level = self.config['runtime'].get('log_level', 'INFO')
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        logger.info("=" * 60)
        logger.info("Atlas Runtime v9.0 — Samsung One UI 8.5 / Termux edition")
        logger.info(f"Config: {self.config_path}")
        logger.info("=" * 60)

        # ---- 2. 平台检测 ----
        logger.info("Detecting platform...")
        self.platform_info = await PlatformInfo.discover()

        # 验证目标平台
        if not self.platform_info.is_samsung:
            logger.warning(
                f"Non-Samsung device detected ({self.platform_info.manufacturer}). "
                "Some Samsung-specific features will be disabled."
            )
        if not self.platform_info.is_termux:
            logger.warning(
                "Not running in Termux. Some Termux-specific features will be disabled."
            )

        # ---- 3. 启动核心组件 ----
        logger.info("Bootstrapping core components...")
        self.bootstrap = Bootstrap(self.config)
        await self.bootstrap.boot()
        self._services = self.bootstrap.get_all_components()

        # ---- 4. 启动健康检查器 ----
        platform_cfg = self.config.get('platform', {})
        health_interval = platform_cfg.get('health_check_interval', 30)

        self.health_checker = HealthChecker(
            platform=self.platform_info,
            check_interval_seconds=health_interval,
        )
        await self.health_checker.start()

        # 如果有电池感知检查点，将健康状态同步到它
        battery_aware = getattr(self.bootstrap, 'battery_aware', None)
        if battery_aware:
            self.health_checker.subscribe(
                lambda health: self._sync_health_to_battery_aware(health, battery_aware)
            )

        # ---- 5. 信号处理器 ----
        loop = asyncio.get_running_loop()
        self._loop = loop

        # Termux 环境下：
        # - SIGTERM: termux-services (runit) 发送此信号停止服务
        # - SIGINT:  Ctrl+C 手动停止
        # - 在 Android 上，add_signal_handler 通常可用
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(
                    sig,
                    lambda s=sig: self._handle_signal(s)
                )
                logger.debug(f"Signal handler registered: {sig.name}")
            except NotImplementedError:
                logger.warning(
                    f"add_signal_handler not available for {sig.name}. "
                    "Using polling-based fallback."
                )
                signal.signal(sig, lambda s, f: self._shutdown_event.set())

        # ---- 6. 主循环 ----
        logger.info("Atlas Runtime is running. Press Ctrl+C to stop.")
        await self._shutdown_event.wait()

        # 如果通过 signal.signal 回退设置了事件，需要显式调用 stop
        if not self._is_stopping:
            await self.stop()

    def _handle_signal(self, sig: signal.Signals) -> None:
        """信号处理器（线程安全）"""
        logger.info(f"Received signal {sig.name}, initiating shutdown...")
        asyncio.create_task(self.stop())

    def _sync_health_to_battery_aware(self, health, battery_aware) -> None:
        """将健康检查结果同步到电池感知组件"""
        try:
            battery_aware.update_health(
                battery_level=health.battery.level,
                is_charging=health.battery.charging,
                temperature=health.battery.temperature_c,
            )
        except Exception as e:
            logger.debug(f"Failed to sync health to battery_aware: {e}")

    async def stop(self) -> None:
        """优雅停止"""
        if self._is_stopping:
            logger.debug("Stop already in progress, ignoring")
            return
        self._is_stopping = True
        logger.info("Stopping Atlas Runtime...")

        # 1. 停止健康检查器
        if self.health_checker:
            try:
                await self.health_checker.stop()
            except Exception as e:
                logger.error(f"Error stopping health checker: {e}")

        # 2. 停止所有服务（逆序：后启动的先停止）
        for service in reversed(self._services):
            if hasattr(service, 'stop'):
                try:
                    await service.stop()
                    logger.debug(f"{service.__class__.__name__} stopped")
                except Exception as e:
                    logger.error(f"Error stopping {service.__class__.__name__}: {e}")

        # 3. 取消残留任务
        loop = asyncio.get_running_loop()
        tasks = [
            t for t in asyncio.all_tasks(loop)
            if t is not asyncio.current_task()
        ]
        if tasks:
            logger.info(f"Cancelling {len(tasks)} residual tasks...")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        # 4. 最终快照持久化
        try:
            await self.bootstrap.persist_final_snapshot()
        except Exception as e:
            logger.error(f"Final snapshot persist failed: {e}")

        self._shutdown_event.set()
        logger.info("Atlas Runtime stopped")

    def run(self) -> None:
        """
        同步入口，创建事件循环并运行。
        在 Termux 中通过 python app.py 直接调用。
        """
        # 在 Android/Termux 上避免使用 ProactorEventLoop（Windows 专用）
        # 使用 SelectorEventLoop（Unix 默认）
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        try:
            loop.run_until_complete(self.start())
        except KeyboardInterrupt:
            logger.info("Interrupted by user (Ctrl+C)")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            raise
        finally:
            # 确保停止流程执行
            if not self._shutdown_event.is_set():
                try:
                    loop.run_until_complete(self.stop())
                except Exception:
                    pass

            # 等待所有待处理回调
            try:
                pending = [
                    t for t in asyncio.all_tasks(loop)
                    if not t.done()
                ]
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass

            loop.close()
            logger.info("Event loop closed. Goodbye.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Atlas Runtime — Samsung One UI 8.5 / Termux Automation Agent"
    )
    parser.add_argument(
        "--config", default="config/runtime.yaml",
        help="Path to runtime configuration YAML (default: config/runtime.yaml)"
    )
    args = parser.parse_args()
    app = AtlasApp(args.config)
    app.run()
