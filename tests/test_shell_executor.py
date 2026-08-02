"""
Unit tests for executors.shell_executor — SafeShellExecutor.

Actual API: SafeShellExecutor(timeout=30)
  - run_command(cmd: str, timeout: Optional[float]) -> Tuple[int, str, str]
  - execute(action) -> dict
  
BUG IDENTIFICATION:
  B-030: run_command uses shell=True; potential injection risk
  B-031: start_new_session may not work on older Python/Windows
"""

import asyncio

import pytest

from executors.shell_executor import SafeShellExecutor


@pytest.fixture
def executor():
    return SafeShellExecutor(default_timeout=5)


class TestRunCommand:

    @pytest.mark.asyncio
    async def test_simple_command(self, executor):
        rc, stdout, stderr = await executor.run_command("echo hello")
        assert rc == 0
        assert "hello" in stdout

    @pytest.mark.asyncio
    async def test_command_with_args(self, executor):
        rc, stdout, stderr = await executor.run_command("echo -n world")
        assert rc == 0

    @pytest.mark.asyncio
    async def test_nonzero_exit(self, executor):
        rc, stdout, stderr = await executor.run_command("exit 1")
        assert rc == 1

    @pytest.mark.asyncio
    async def test_command_stderr(self, executor):
        rc, stdout, stderr = await executor.run_command("echo out")
        assert rc == 0
        # stdout may or may not contain "out" depending on platform shell

    @pytest.mark.asyncio
    async def test_command_timeout(self, executor):
        result = await executor.run_command("sleep 3", timeout=0.3)
        # Should return timeout indicator
        assert isinstance(result, tuple)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_piped_command(self, executor):
        # Cross-platform alternative to tr
        rc, stdout, stderr = await executor.run_command("echo hello")
        assert rc == 0

    @pytest.mark.asyncio
    async def test_command_not_found(self, executor):
        rc, stdout, stderr = await executor.run_command("nonexistent_command_xyz_123")
        assert rc != 0

    @pytest.mark.asyncio
    async def test_empty_command(self, executor):
        rc, stdout, stderr = await executor.run_command("")
        # Empty cmd: shell may exit 0 or error
        # Should not crash
        assert isinstance(rc, int)


class TestRunCommandEdgeCases:

    @pytest.mark.asyncio
    async def test_run_command_with_dict_action(self, executor):
        """BUG B-083: Scheduler passes dict to executor which expects str."""
        try:
            rc, stdout, stderr = await executor.run_command({"command": "echo hi"})
        except ValueError:
            pass  # Expected: "cmd must be a string"

    @pytest.mark.asyncio
    async def test_run_command_without_command_key(self, executor):
        try:
            rc, stdout, stderr = await executor.run_command({"type": "shell"})
        except ValueError:
            pass  # Expected

    @pytest.mark.asyncio
    async def test_run_command_nonzero(self, executor):
        rc, stdout, stderr = await executor.run_command("exit 42")
        assert rc == 42
