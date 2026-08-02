# core/shell_executor.py
"""
安全 Shell 执行器（Safe Shell Executor）—— 兼容性存根
职责：执行 Shell 命令，超时控制，进程组隔离，管道清理

注意：主实现已迁移至 executors/shell_executor.py。
此文件保留用于向后兼容，功能与 executors 版本完全相同。
新代码请直接从 executors.shell_executor 导入。
"""

import asyncio
import os
import signal
import logging
from typing import Tuple

logger = logging.getLogger("Atlas.ShellExecutor")


class SafeShellExecutor:
    def __init__(self, default_timeout: float = 5.0):
        self.default_timeout = default_timeout

    async def run_command(self, cmd: str, timeout: float = None) -> Tuple[int, str, str]:
        exec_timeout = timeout or self.default_timeout

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=exec_timeout)
            return proc.returncode, stdout.decode(), stderr.decode()

        except asyncio.TimeoutError:
            logger.error(f"Command timed out: {cmd[:100]}...")

            # 强制杀死进程组
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGKILL)
            except Exception:
                proc.kill()

            # 清理管道，避免残留
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()

            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning(f"Process {proc.pid} wait timed out after kill")

            return -1, "", f"Execution timed out after {exec_timeout}s"

        except Exception as e:
            try:
                proc.kill()
            except Exception:
                pass
            # 清理管道
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
            return -1, "", str(e)