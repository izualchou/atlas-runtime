# executors/shell_executor.py
"""
安全 Shell 执行器（Safe Shell Executor）—— Samsung One UI 8.5 + Termux 适配版

职责：执行 Shell 命令，超时控制，进程组隔离，管道清理。

Termux 适配要点：
- Android 系统命令（svc, settings, input 等）在 /system/bin/，Termux 默认 PATH 不含此路径
- 自动补充 ANDROID_ROOT 和系统 bin 路径到 PATH
- Termux 的 bash 位于 $PREFIX/bin/bash，subprocess_shell 默认使用 /bin/sh（兼容）
- 三星 One UI 8.5 的 signal 行为可能与标准 Linux 不同
- 进程组清理使用 SIGTERM + SIGKILL 双重策略
"""

import asyncio
import logging
import os
import signal
import time
from typing import Tuple

from executors.base import BaseExecutor, ExecutorResult
from device import TERMUX_PREFIX

logger = logging.getLogger("Atlas.ShellExecutor")

_ANDROID_ROOT = os.environ.get("ANDROID_ROOT", "/system")


class SafeShellExecutor(BaseExecutor):
    """
    安全 Shell 命令执行器。

    在 Termux 环境中，确保 Android 系统命令路径被包含在 PATH 中。
    使用进程组隔离（start_new_session）确保子进程及其后代可被完全终止。
    """

    def __init__(self, default_timeout: float = 15.0):
        """
        Args:
            default_timeout: 默认超时（秒），移动设备上建议 10-15s
        """
        self.default_timeout = default_timeout
        self._env = self._build_env()

    def _build_env(self) -> dict:
        """
        构建子进程环境变量。

        Termux 关键路径：
        - /system/bin  → Android 系统命令 (svc, input, settings, cmd, service)
        - $PREFIX/bin   → Termux 用户命令 (bash, python, termux-*)
        - /system/xbin  → 扩展系统命令
        - /apex/com.android.runtime/bin → Android Runtime 命令
        """
        env = os.environ.copy()

        # 构建完整的 PATH
        system_paths = [
            f"{_ANDROID_ROOT}/bin",           # /system/bin
            f"{_ANDROID_ROOT}/xbin",          # /system/xbin
            "/apex/com.android.runtime/bin",  # Android Runtime
        ]

        # 收集已存在的路径
        existing_path = env.get("PATH", "")
        paths = set(existing_path.split(":") if existing_path else [])

        # 添加系统路径（去重后前置）
        for sp in system_paths:
            if os.path.isdir(sp):
                paths.add(sp)

        env["PATH"] = ":".join(sorted(paths))
        return env

    async def run_command(
        self, cmd: str, timeout: float = None
    ) -> Tuple[int, str, str]:
        """
        执行 Shell 命令，返回 (returncode, stdout, stderr)。

        超时后先发送 SIGTERM，再发送 SIGKILL 到整个进程组。

        Args:
            cmd: 要执行的 Shell 命令
            timeout: 超时秒数（None = 使用 default_timeout）
        """
        exec_timeout = timeout or self.default_timeout

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env,
                start_new_session=True,  # 进程组隔离：防止孤儿进程
            )
        except OSError as e:
            logger.error(f"Failed to spawn subprocess for cmd '{cmd[:100]}...': {e}")
            return -1, "", f"Process spawn error: {e}"

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=exec_timeout
            )
            return (
                proc.returncode or 0,
                stdout.decode(errors="replace"),
                stderr.decode(errors="replace"),
            )
        except asyncio.TimeoutError:
            logger.warning(f"Command timed out ({exec_timeout}s): {cmd[:120]}...")
            return await self._kill_process_tree(proc, cmd)
        except Exception as e:
            logger.error(f"Command execution error: {e}")
            try:
                proc.kill()
            except Exception:
                pass
            return -1, "", str(e)

    async def _kill_process_tree(
        self, proc: asyncio.subprocess.Process, cmd: str
    ) -> Tuple[int, str, str]:
        """
        终止进程树。

        使用 SIGTERM → 等待 → SIGKILL 的递进策略。
        在三星 One UI 8.5 上，部分 signal 可能被 Knox 拦截，
        因此直接对进程调用 kill() 作为回退。
        """
        pid = proc.pid

        # 步骤 1：SIGTERM 给进程组
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            # 进程可能已退出，或 Samsung Knox 阻止了 killpg
            try:
                proc.terminate()
            except Exception:
                pass

        # 步骤 2：等待 1 秒
        try:
            await asyncio.wait_for(proc.wait(), timeout=1.0)
            # 成功终止
            return (-1, "", f"Execution timed out after {self.default_timeout}s (gracefully terminated)")
        except asyncio.TimeoutError:
            pass

        # 步骤 3：SIGKILL 强制终止
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except Exception:
                pass

        # 步骤 4：最终等待
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            logger.error(f"Process {pid} survived SIGKILL, may be a zombie on Samsung device")

        # 清理管道
        if proc.stdout:
            try:
                proc.stdout.close()
            except Exception:
                pass
        if proc.stderr:
            try:
                proc.stderr.close()
            except Exception:
                pass

        return -1, "", f"Execution timed out after {self.default_timeout}s"
