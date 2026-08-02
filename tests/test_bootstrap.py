"""
Integration tests for core.bootstrap — component initialization.

Actual API:
  Bootstrap(config: dict)
  - boot() -> None  (NOT returns Scheduler)
  - get_component(name) -> Optional[Any]
  - get_all_components() -> List[Any]
  - components dict
  - _component_order list

BUG IDENTIFICATION:
  B-060: config uses direct indexing; missing keys → KeyError
  B-061: no error isolation between components — one failure blocks all
"""

import pytest

from core.bootstrap import Bootstrap


@pytest.fixture
def minimal_config(temp_dir):
    return {
        "runtime": {
            "log_level": "DEBUG",
            "snapshot_interval": 5,
            "command_timeout": 3,
            "circuit_breaker_threshold": 3,
            "dedup_ttl": 10,
            "max_pending": 50,
        },
        "storage": {
            "db_path": f"{temp_dir}/atlas.db",
            "busy_timeout": 2000,
            "snapshot_dir": f"{temp_dir}/snapshots",
            "max_events": 100,
            "rotate_interval_hours": 1,
            "battery_check_interval": 10,
        },
        "memory": {
            "soft_limit_mb": 150,
            "hard_limit_mb": 200,
        },
        "transport": {
            "fifo_path": f"{temp_dir}/trigger.fifo",
            "http_port": 18793,
        },
        "executors": {
            "shell_timeout": 3,
            "ui_timeout": 3,
        },
    }


class TestBootstrapBoot:

    @pytest.mark.asyncio
    async def test_boot_succeeds(self, minimal_config):
        boot = Bootstrap(minimal_config)
        await boot.boot()
        # boot() returns None; scheduler is in components
        assert boot.components["scheduler"] is not None

    @pytest.mark.asyncio
    async def test_components_present(self, minimal_config):
        boot = Bootstrap(minimal_config)
        await boot.boot()
        assert "storage" in boot.components
        assert "scheduler" in boot.components
        assert "state_manager" in boot.components
        assert "executor" in boot.components
        assert "snapshot" in boot.components
        assert "trigger_handler" in boot.components
        assert "trigger_server" in boot.components

    @pytest.mark.asyncio
    async def test_component_order(self, minimal_config):
        boot = Bootstrap(minimal_config)
        await boot.boot()
        order = boot._component_order
        # Storage must be first
        assert order[0] == "storage"
        # Stateless components NOT in order
        assert "snapshot" not in order
        assert "trigger_handler" not in order
        assert "executor" not in order

    @pytest.mark.asyncio
    async def test_get_component(self, minimal_config):
        boot = Bootstrap(minimal_config)
        await boot.boot()
        s = boot.get_component("storage")
        assert s is not None
        assert boot.get_component("nonexistent") is None

    @pytest.mark.asyncio
    async def test_get_all_components(self, minimal_config):
        boot = Bootstrap(minimal_config)
        await boot.boot()
        all_comp = boot.get_all_components()
        names = [type(c).__name__ for c in all_comp]
        # Stateless: SnapshotManager not in ordered components
        assert "SnapshotManager" not in names
        assert "TriggerHandler" not in names
        assert "SafeShellExecutor" not in names


class TestBootstrapConfigErrors:

    @pytest.mark.asyncio
    async def test_missing_storage(self, minimal_config):
        """BUG B-060: KeyError."""
        cfg = dict(minimal_config)
        del cfg["storage"]
        boot = Bootstrap(cfg)
        with pytest.raises(KeyError):
            await boot.boot()

    @pytest.mark.asyncio
    async def test_missing_transport(self, minimal_config):
        """BUG B-060: KeyError."""
        cfg = dict(minimal_config)
        del cfg["transport"]
        boot = Bootstrap(cfg)
        with pytest.raises(KeyError):
            await boot.boot()

    @pytest.mark.asyncio
    async def test_invalid_db_path(self, minimal_config):
        cfg = dict(minimal_config)
        cfg["storage"]["db_path"] = "/invalid/path/that/does/not/exist/db.sqlite"
        boot = Bootstrap(cfg)
        try:
            await boot.boot()
        except Exception:
            pass


class TestBootstrapShutdown:

    @pytest.mark.asyncio
    async def test_ordered_components_have_stop(self, minimal_config):
        boot = Bootstrap(minimal_config)
        await boot.boot()

        for name in boot._component_order:
            comp = boot.components.get(name)
            if comp is not None:
                assert hasattr(comp, "stop") or hasattr(comp, "close"), \
                    f"{name}: {type(comp).__name__} missing stop()/close()"
