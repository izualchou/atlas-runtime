# core/bootstrap.py
"""
启动编排（Bootstrap）
职责：按依赖顺序初始化所有组件，恢复快照，清理孤儿锁，启动服务
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger("Atlas.Bootstrap")


class Bootstrap:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.components: Dict[str, Any] = {}
        self._component_order: List[str] = []

    async def boot(self) -> None:
        logger.info("Starting Atlas Runtime bootstrap...")

        # 1. Storage
        from storage.driver import SingleWriterStorage
        storage = SingleWriterStorage(
            db_path=self.config['storage']['db_path'],
            busy_timeout=self.config['storage']['busy_timeout'],
        )
        await storage.start()
        self.components['storage'] = storage
        self._component_order.append('storage')
        logger.info("Storage initialized")

        # 2. SnapshotManager
        from storage.snapshot import SnapshotManager
        snapshot = SnapshotManager(
            snapshot_dir=self.config['storage'].get('snapshot_dir', 'data/snapshots')
        )
        self.components['snapshot'] = snapshot

        # 3. StateManager
        from core.state_manager import StateManager
        state_manager = StateManager(
            snapshot_mgr=snapshot,
            snapshot_interval=self.config['runtime']['snapshot_interval']
        )
        await state_manager.start()
        self.components['state_manager'] = state_manager
        self._component_order.append('state_manager')
        logger.info("StateManager initialized")

        # 4. ResourceLock
        from core.resource_lock import ResourceLock
        resource_lock = ResourceLock(storage)
        await resource_lock.clean_expired()
        self.components['resource_lock'] = resource_lock
        self._component_order.append('resource_lock')
        logger.info("ResourceLock initialized")

        # 5. ShellExecutor
        from executors.shell_executor import SafeShellExecutor
        executor = SafeShellExecutor(
            default_timeout=self.config['executors']['shell_timeout']
        )
        self.components['executor'] = executor

        # 6. Scheduler
        from core.scheduler import Scheduler
        scheduler = Scheduler(
            executor=executor.run_command,
            resource_lock=resource_lock,
            max_pending=self.config['runtime'].get('max_pending', 5000)
        )
        await scheduler.start()
        self.components['scheduler'] = scheduler
        self._component_order.append('scheduler')
        logger.info("Scheduler started")

        # 7. TriggerHandler
        from core.trigger_handler import TriggerHandler
        trigger_handler = TriggerHandler(scheduler, storage)
        self.components['trigger_handler'] = trigger_handler

        # 8. TriggerServer
        from transport.trigger_server import HybridTriggerServer
        trigger_server = HybridTriggerServer(
            trigger_handler=trigger_handler.handle,
            fifo_path=self.config['transport']['fifo_path'],
            http_port=self.config['transport']['http_port'],
        )
        await trigger_server.start()
        self.components['trigger_server'] = trigger_server
        self._component_order.append('trigger_server')
        logger.info("TriggerServer started")

        # 9. Rotator
        from storage.rotator import EventRotator
        rotator = EventRotator(
            storage=storage,
            max_rows=self.config['storage'].get('max_events', 10000),
            check_interval_hours=self.config['storage'].get('rotate_interval_hours', 6)
        )
        await rotator.start()
        self.components['rotator'] = rotator
        self._component_order.append('rotator')

        # 10. BatteryAware
        from storage.battery_aware import BatteryAwareCheckpoint
        battery = BatteryAwareCheckpoint(
            storage=storage,
            check_interval_seconds=self.config['storage'].get('battery_check_interval', 30)
        )
        await battery.start()
        self.components['battery_aware'] = battery
        self._component_order.append('battery_aware')

        logger.info("All components initialized successfully")
        logger.info("Atlas Runtime is ready!")

    def get_component(self, name: str) -> Any:
        return self.components.get(name)

    def get_all_components(self) -> List[Any]:
        """按启动顺序返回所有组件，用于关机倒序停止"""
        return [self.components[name] for name in self._component_order if name in self.components]