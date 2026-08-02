# executors/ui_automation.py
"""
UI 自动化执行器
职责：点击、滑动、获取 UI 树等 UI 操作
优先使用 Android 原生命令 (input / uiautomator)
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from .shell_executor import SafeShellExecutor

logger = logging.getLogger("Atlas.UIAutomation")

class UIAutomationExecutor:
    def __init__(self, shell_executor: Optional[SafeShellExecutor] = None):
        self.shell = shell_executor or SafeShellExecutor()

    async def click(self, x: int, y: int, timeout: float = 5.0) -> Dict[str, Any]:
        """点击屏幕坐标"""
        cmd = f"input tap {x} {y}"
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)
        return {
            "success": returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        }

    async def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300,
                    timeout: float = 5.0) -> Dict[str, Any]:
        """滑动操作"""
        cmd = f"input swipe {x1} {y1} {x2} {y2} {duration_ms}"
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)
        return {
            "success": returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        }

    async def get_ui_tree(self, timeout: float = 5.0) -> Dict[str, Any]:
        """获取 UI 树 (通过 uiautomator dump)"""
        # 将输出 dump 到临时文件，再读取内容
        temp_file = "/data/local/tmp/ui_dump.xml"
        cmd = f"uiautomator dump {temp_file} && cat {temp_file}"
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)
        return {
            "success": returncode == 0,
            "xml": stdout if returncode == 0 else None,
            "stderr": stderr,
            "returncode": returncode,
        }

    async def press_back(self, timeout: float = 2.0) -> Dict[str, Any]:
        """按返回键"""
        cmd = "input keyevent KEYCODE_BACK"
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)
        return {
            "success": returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        }

    async def press_home(self, timeout: float = 2.0) -> Dict[str, Any]:
        """按 Home 键"""
        cmd = "input keyevent KEYCODE_HOME"
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)
        return {
            "success": returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        }

    async def press_recent(self, timeout: float = 2.0) -> Dict[str, Any]:
        """按 Recent 键 (多任务)"""
        cmd = "input keyevent KEYCODE_APP_SWITCH"
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)
        return {
            "success": returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        }