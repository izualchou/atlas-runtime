"""
pytest fixtures for atlas-runtime unit and integration tests.

Provides shared resources:
- In-memory SQLite database (avoids filesystem dependencies)
- Temporary directories for snapshot/rotation tests
- Mock subprocess harness for executor tests
- Async event loop policies compatible with Windows and Linux
"""

import asyncio
import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import yaml


# ---------------------------------------------------------------------------
# Async event loop
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop_policy():
    """Use the default asyncio event loop policy for cross-platform compat."""
    return asyncio.get_event_loop_policy()


# ---------------------------------------------------------------------------
# Temporary filesystem fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_dir():
    """A temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def db_path(temp_dir):
    """Path for an in-memory / temp SQLite database."""
    p = temp_dir / "test_atlas.db"
    return str(p)


# ---------------------------------------------------------------------------
# Config fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_config_dict():
    """Minimal valid config dict matching runtime.yaml structure."""
    return {
        "runtime": {
            "log_level": "DEBUG",
            "snapshot_interval": 5,
            "command_timeout": 3,
            "circuit_breaker_threshold": 3,
            "dedup_ttl": 10,
            "max_pending": 100,
        },
        "storage": {
            "db_path": ":memory:",
            "busy_timeout": 2000,
            "snapshot_dir": "test_snapshots",
            "max_events": 1000,
            "rotate_interval_hours": 1,
            "battery_check_interval": 10,
        },
        "memory": {
            "soft_limit_mb": 150,
            "hard_limit_mb": 200,
        },
        "transport": {
            "fifo_path": "/tmp/test_atlas_trigger.fifo",
            "http_port": 18787,
        },
        "executors": {
            "shell_timeout": 3,
            "ui_timeout": 3,
        },
    }


@pytest.fixture
def sample_config_path(temp_dir, sample_config_dict):
    """Write sample config to a temp YAML file and return its path."""
    p = temp_dir / "runtime.yaml"
    with open(p, "w", encoding="utf-8") as fh:
        yaml.safe_dump(sample_config_dict, fh)
    return str(p)


# ---------------------------------------------------------------------------
# Mock subprocess for executor tests
# ---------------------------------------------------------------------------

@dataclass
class MockProcessResult:
    """Simulates asyncio.subprocess.Process returned values."""
    returncode: int = 0
    stdout: bytes = b""
    stderr: bytes = b""


class MockAsyncProcess:
    """Mock for asyncio.create_subprocess_exec."""

    def __init__(
        self,
        returncode: int = 0,
        stdout_data: bytes = b"",
        stderr_data: bytes = b"",
        pid: int = 12345,
    ):
        self._returncode = returncode
        self._stdout = stdout_data
        self._stderr = stderr_data
        self.pid = pid
        self._killed = False
        self._waited = False

    async def communicate(self) -> tuple:
        self._waited = True
        return self._stdout, self._stderr

    async def wait(self) -> int:
        self._waited = True
        return self._returncode

    def kill(self):
        self._killed = True

    def terminate(self):
        self._killed = True

    @property
    def returncode(self) -> Optional[int]:
        if self._waited:
            return self._returncode
        return None


@pytest.fixture
def mock_subprocess_success():
    """Return a factory that produces successful MockAsyncProcess instances."""
    def _factory(stdout: bytes = b"ok\n", stderr: bytes = b"") -> MockAsyncProcess:
        return MockAsyncProcess(returncode=0, stdout_data=stdout, stderr_data=stderr)
    return _factory


@pytest.fixture
def mock_subprocess_failure():
    """Return a factory that produces failed MockAsyncProcess instances."""
    def _factory(stderr: bytes = b"error\n") -> MockAsyncProcess:
        return MockAsyncProcess(returncode=1, stdout_data=b"", stderr_data=stderr)
    return _factory


# ---------------------------------------------------------------------------
# In-memory SQLite database for storage tests
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mem_db_path(temp_dir):
    """Path to a temporary file: SQLite database for storage tests."""
    return str(temp_dir / "test_store.db")


async def _init_schema(db_path: str):
    """Create all required tables for integration tests."""
    import aiosqlite

    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'PENDING',
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                scheduled_at TEXT,
                started_at TEXT,
                completed_at TEXT,
                error_message TEXT,
                worker_id TEXT
            );

            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                event_type TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (task_id) REFERENCES tasks(task_id)
            );

            CREATE TABLE IF NOT EXISTS state_snapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                checksum TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS resource_locks (
                lock_key TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                acquired_at TEXT NOT NULL DEFAULT (datetime('now')),
                expires_at TEXT,
                version INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(state);
            CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
            CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
            CREATE INDEX IF NOT EXISTS idx_events_time ON events(created_at);
        """)
        await conn.commit()


# ---------------------------------------------------------------------------
# Helper: create a simple task payload
# ---------------------------------------------------------------------------

def make_task_payload(
    task_id: str = "task-001",
    command: str = "echo hello",
    task_type: str = "shell",
    timeout: int = 5,
    **extra,
) -> dict:
    """Create a valid task payload dict."""
    return {
        "task_id": task_id,
        "command": command,
        "type": task_type,
        "timeout": timeout,
        **extra,
    }
