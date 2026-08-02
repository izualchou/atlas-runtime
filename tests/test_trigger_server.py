"""
Unit tests for transport.trigger_server — HybridTriggerServer (FIFO + HTTP).

Actual API: HybridTriggerServer(trigger_handler, fifo_path, http_host, http_port, max_concurrent_tasks)
  - start() / stop()
  - _process_line(line: bytes)
  - _process_line_with_semaphore(line: bytes)

Note: FIFO operations require Unix; tested on Windows will skip FIFO
  because os.mkfifo is not available.
"""

import asyncio
import json
import os
import sys

import pytest

from transport.trigger_server import HybridTriggerServer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeHandler:
    def __init__(self):
        self.handled: list = []

    async def handle(self, data: dict):
        self.handled.append(data)
        return {"status": "ok", "task_id": f"fake-{len(self.handled)}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def handler():
    return FakeHandler()


@pytest.fixture
def server(handler, temp_dir):
    fifo = str(temp_dir / "trigger.fifo")
    return HybridTriggerServer(
        trigger_handler=handler.handle,
        fifo_path=fifo,
        http_host="127.0.0.1",
        http_port=18792,
        max_concurrent_tasks=10,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestConstruction:

    def test_default_params(self, handler, temp_dir):
        srv = HybridTriggerServer(
            trigger_handler=handler.handle,
            fifo_path=str(temp_dir / "d.fifo"),
            http_host="0.0.0.0",
            http_port=8000,
        )
        assert srv.max_concurrent_tasks == 100
        assert srv.http_port == 8000

    def test_custom_concurrency(self, handler, temp_dir):
        srv = HybridTriggerServer(
            trigger_handler=handler.handle,
            fifo_path=str(temp_dir / "cc.fifo"),
            http_host="127.0.0.1",
            http_port=8001,
            max_concurrent_tasks=50,
        )
        assert srv.max_concurrent_tasks == 50


class TestLineProcessing:

    @pytest.mark.asyncio
    async def test_process_valid_json_line(self, server, handler):
        line = json.dumps({"command": "echo test"}).encode()
        await server._process_line(line)
        assert len(handler.handled) == 1
        assert handler.handled[0]["command"] == "echo test"

    @pytest.mark.asyncio
    async def test_process_invalid_json(self, server, handler):
        """Invalid JSON should be logged and skipped, not crash."""
        line = b"not valid json {{{"
        await server._process_line(line)
        # Should not add to handler
        assert len(handler.handled) == 0

    @pytest.mark.asyncio
    async def test_process_empty_line(self, server, handler):
        await server._process_line(b"")
        assert len(handler.handled) == 0

    @pytest.mark.asyncio
    async def test_process_whitespace_line(self, server, handler):
        await server._process_line(b"   \n\t  ")
        assert len(handler.handled) == 0

    @pytest.mark.asyncio
    async def test_process_line_with_semaphore(self, server, handler):
        line = json.dumps({"command": "echo sem"}).encode()
        await server._process_line_with_semaphore(line)
        assert len(handler.handled) == 1


class TestBackpressure:

    def test_backlog_count_start(self, server):
        assert server._backlog_count == 0

    def test_active_task_count_start(self, server):
        assert server._active_task_count == 0

    def test_semaphore_initial(self, server):
        assert server._semaphore.locked() is False


class TestLifecycle:

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, server):
        server._running = True
        await server.stop()
        await server.stop()  # second stop — should not crash

    @pytest.mark.asyncio
    async def test_stop_without_fifo(self, server):
        server._running = True
        server._fifo_fd = None
        await server.stop()

    @pytest.mark.asyncio
    async def test_start_on_windows_skips_fifo(self, server):
        """On Windows, mkfifo is unavailable. Start should handle gracefully."""
        if sys.platform == "win32":
            server._running = False
            try:
                await server.start()
                # FIFO should be skipped on Windows
                assert server._fifo_fd is None or server._fifo_task is None
            except AttributeError:
                pass  # Expected on Windows: os.mkfifo doesn't exist
            await server.stop()
        else:
            server._running = False
            await server.start()
            await server.stop()
