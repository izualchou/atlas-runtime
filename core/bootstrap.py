# core/bootstrap.py
"""
启动编排（Bootstrap）— Samsung One UI 8.5 + Termux 适配版

职责：
- 按依赖顺序初始化所有组件
- 恢复快照、清理孤儿锁
- 启动服务并管理组件生命周期
- 提供 persist_final_snapshot 供优雅关闭时最终持久化
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("Atlas.Bootstrap")


class Bootstrap:
    """
    启动编排器。

    组件初始化顺序（严格依赖链）：
    1. Storage (SingleWriterStorage)
    2. SnapshotManager (无状态)
    3. MemoryController (无状态/同步部件，尽早初始化供 Scheduler 引用)
    4. CircuitBreaker (无状态部件)
    5. DedupFilter (无状态部件)
    6. StateManager
    7. ResourceLock
    8. SafeShellExecutor (无状态)
    9. Scheduler
    10. ResultCallback (无状态；注册到 scheduler.on_task_complete)
    11. AutoJS6Launcher (无状态；注入 executor)
    12. TriggerHandler (无状态)
    13. HybridTriggerServer (注入 circuit_breaker + dedup_filter 用于 /health)
    14. EventRotator
    15. BatteryAwareCheckpoint
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.components: Dict[str, Any] = {}
        self._component_order: List[str] = []

        # 直接属性引用（方便 app.py 访问）
        self.battery_aware = None
        self.state_manager = None
        self.scheduler = None
        self.memory_controller = None
        self.circuit_breaker = None
        self.dedup_filter = None
        self.result_callback = None
        self.autojs_launcher = None

    async def boot(self) -> None:
        """按序启动所有组件"""
        logger.info("Starting Atlas Runtime bootstrap...")

        # ---- 1. Storage ----
        from storage.driver import SingleWriterStorage
        storage = SingleWriterStorage(
            db_path=self.config['storage']['db_path'],
            busy_timeout=self.config['storage']['busy_timeout'],
        )
        await storage.start()
        self.components['storage'] = storage
        self._component_order.append('storage')
        logger.info("Storage initialized")

        # ---- 2. SnapshotManager ----
        from storage.snapshot import SnapshotManager
        snapshot = SnapshotManager(
            snapshot_dir=self.config['storage'].get('snapshot_dir', 'data/snapshots')
        )
        self.components['snapshot'] = snapshot
        # 注意：SnapshotManager 无状态、无 stop()，不加入 _component_order

        # ---- 3. MemoryController ----
        mem_cfg = self.config.get('memory', {})
        from core.memory_controller import MemoryController
        memory_controller = MemoryController(
            soft_limit_mb=mem_cfg.get('soft_limit_mb', 150),
            hard_limit_mb=mem_cfg.get('hard_limit_mb', 200),
        )
        self.components['memory_controller'] = memory_controller
        self.memory_controller = memory_controller
        logger.info(
            f"MemoryController initialized "
            f"(soft={memory_controller.soft_limit_mb}MB, "
            f"hard={memory_controller.hard_limit_mb}MB)"
        )

        # ---- 4. CircuitBreaker ----
        cb_cfg = self.config.get('circuit_breaker', {})
        from core.circuit_breaker import CircuitBreaker
        circuit_breaker = CircuitBreaker(
            failure_threshold=cb_cfg.get('failure_threshold',
                self.config['runtime'].get('circuit_breaker_threshold', 5)),
            recovery_timeout=cb_cfg.get('recovery_timeout', 30.0),
        )
        self.components['circuit_breaker'] = circuit_breaker
        self.circuit_breaker = circuit_breaker
        logger.info(
            f"CircuitBreaker initialized "
            f"(threshold={circuit_breaker.failure_threshold}, "
            f"timeout={circuit_breaker.recovery_timeout}s)"
        )

        # ---- 5. DedupFilter ----
        dd_cfg = self.config.get('dedup', {})
        from core.dedup import DedupFilter
        dedup_filter = DedupFilter(
            ttl=dd_cfg.get('ttl',
                self.config['runtime'].get('dedup_ttl', 60)),
            max_entries=dd_cfg.get('max_entries', 10000),
        )
        self.components['dedup_filter'] = dedup_filter
        self.dedup_filter = dedup_filter
        logger.info(
            f"DedupFilter initialized "
            f"(ttl={dedup_filter.ttl}s, max={dedup_filter.max_entries})"
        )

        # ---- 6. StateManager ----
        from core.state_manager import StateManager
        state_manager = StateManager(
            snapshot_mgr=snapshot,
            snapshot_interval=self.config['runtime']['snapshot_interval']
        )
        await state_manager.start()
        self.components['state_manager'] = state_manager
        self._component_order.append('state_manager')
        self.state_manager = state_manager
        logger.info("StateManager initialized")

        # ---- 7. ResourceLock ----
        from core.resource_lock import ResourceLock
        resource_lock = ResourceLock(storage)
        await resource_lock.clean_expired()
        self.components['resource_lock'] = resource_lock
        self._component_order.append('resource_lock')
        logger.info("ResourceLock initialized (expired locks cleaned)")

        # ---- 8. ShellExecutor ----
        from executors.shell_executor import SafeShellExecutor
        executor = SafeShellExecutor(
            default_timeout=self.config['executors']['shell_timeout']
        )
        self.components['executor'] = executor
        # 注意：SafeShellExecutor 无状态、无 stop()，不加入 _component_order

        # ---- 9. Scheduler ----
        from core.scheduler import Scheduler
        scheduler = Scheduler(
            executor=executor,
            resource_lock=resource_lock,
            max_pending=self.config['runtime'].get('max_pending', 500),
            memory_controller=memory_controller,
            circuit_breaker=circuit_breaker,
            dedup_filter=dedup_filter,
        )
        await scheduler.start()
        self.components['scheduler'] = scheduler
        self._component_order.append('scheduler')
        self.scheduler = scheduler
        logger.info("Scheduler started")

        # ---- 10. ResultCallback ----
        from transport.result_callback import ResultCallback
        result_callback = ResultCallback()
        scheduler.on_task_complete = result_callback.on_task_complete
        self.components['result_callback'] = result_callback
        self.result_callback = result_callback
        logger.info("ResultCallback registered on scheduler.on_task_complete")

        # ---- 11. AutoJS6Launcher ----
        from transport.autojs_launcher import AutoJS6Launcher
        autojs_launcher = AutoJS6Launcher(executor)
        self.components['autojs_launcher'] = autojs_launcher
        self.autojs_launcher = autojs_launcher
        logger.info("AutoJS6Launcher initialized")

        # ---- 12. TriggerHandler ----
        from core.trigger_handler import TriggerHandler
        trigger_handler = TriggerHandler(scheduler, storage)
        self.components['trigger_handler'] = trigger_handler
        # 注意：TriggerHandler 无持久状态、无 stop()，不加入 _component_order

        # ---- 13. TriggerServer ----
        from transport.trigger_server import HybridTriggerServer
        trigger_server = HybridTriggerServer(
            trigger_handler=trigger_handler.handle,
            fifo_path=self.config['transport']['fifo_path'],
            http_port=self.config['transport']['http_port'],
            memory_controller=memory_controller,
            circuit_breaker=circuit_breaker,
            dedup_filter=dedup_filter,
        )
        await trigger_server.start()
        self.components['trigger_server'] = trigger_server
        self._component_order.append('trigger_server')
        logger.info("TriggerServer started")

        # ---- 12. Rotator ----
        from storage.rotator import EventRotator
        rotator = EventRotator(
            storage=storage,
            max_rows=self.config['storage'].get('max_events', 10000),
            check_interval_hours=self.config['storage'].get('rotate_interval_hours', 6)
        )
        await rotator.start()
        self.components['rotator'] = rotator
        self._component_order.append('rotator')
        logger.info("EventRotator started")

        # ---- 13. BatteryAwareCheckpoint ----
        from storage.battery_aware import BatteryAwareCheckpoint
        battery = BatteryAwareCheckpoint(
            storage=storage,
            check_interval_seconds=self.config['storage'].get('battery_check_interval', 15)
        )
        await battery.start()
        self.components['battery_aware'] = battery
        self._component_order.append('battery_aware')
        self.battery_aware = battery
        logger.info("BatteryAwareCheckpoint started")

        logger.info("All components initialized successfully")
        logger.info("Atlas Runtime is ready!")

    def get_component(self, name: str) -> Any:
        """按名称获取已初始化的组件"""
        return self.components.get(name)

    def get_all_components(self) -> List[Any]:
        """
        按启动顺序返回需要有序关闭的组件列表。

        用于关机时倒序停止。注意：executor、snapshot、trigger_handler
        不在此列表中，因为它们无持久状态且无 stop() 方法。
        """
        return [
            self.components[name]
            for name in self._component_order
            if name in self.components
        ]

    async def persist_final_snapshot(self) -> None:
        """
        在优雅关闭时持久化最终快照。

        确保状态管理器的最新状态被写入磁盘，避免重启后数据丢失。
        在 Samsung One UI 的激进进程回收策略下尤为重要。
        """
        state_mgr = self.components.get('state_manager')
        snapshot_mgr = self.components.get('snapshot')
        if state_mgr is None or snapshot_mgr is None:
            logger.warning("Cannot persist final snapshot: missing components")
            return

        try:
            data = await state_mgr.get_all()
            versions = {
                key: await state_mgr.get_version(key)
                for key in data.keys()
            }
            frozen = {"data": data, "versions": versions}
            await snapshot_mgr.write(frozen)
            logger.info("Final snapshot persisted successfully")
        except Exception as e:
            logger.error(f"Failed to persist final snapshot: {e}")
