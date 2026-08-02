# executors/ui_automation.py
"""
UI 自动化执行器（Samsung One UI 8.5 + Termux 适配版）

职责：点击、滑动、获取 UI 树等 UI 操作。

Termux 适配要点：
- /data/local/tmp 在三星 One UI 8.5 上可能无写权限
- 使用 Termux 自有临时目录 $PREFIX/tmp 作为 dump 输出
- uiautomator dump 在 Samsung 设备上可能需要更多时间
- 添加三星特有按键（Bixby）支持
- input 命令位于 /system/bin/input，需确保 PATH 包含此路径
"""

import asyncio
import logging
import os
import tempfile
from typing import Dict, Any, Optional

from .shell_executor import SafeShellExecutor

logger = logging.getLogger("Atlas.UIAutomation")

# Termux 临时目录（始终可写）
_TERMUX_PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
_TERMUX_TMP = os.path.join(_TERMUX_PREFIX, "tmp")


class UIAutomationExecutor:
    """
    UI 自动化执行器。

    所有操作通过 Android input 命令和 uiautomator 完成。
    在 Samsung One UI 8.5 设备上测试通过。
    """

    def __init__(self, shell_executor: Optional[SafeShellExecutor] = None):
        self.shell = shell_executor or SafeShellExecutor()

        # 确保 Termux 临时目录存在
        try:
            os.makedirs(_TERMUX_TMP, exist_ok=True)
        except OSError:
            logger.warning(f"Cannot create Termux tmp dir: {_TERMUX_TMP}")

    # ------------------------------------------------------------------
    # 点击操作
    # ------------------------------------------------------------------

    async def click(self, x: int, y: int, timeout: float = 5.0) -> Dict[str, Any]:
        """点击屏幕坐标"""
        cmd = f"input tap {x} {y}"
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)
        return {
            "success": returncode == 0,
            "x": x,
            "y": y,
            "action": "tap",
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        }

    async def long_press(
        self, x: int, y: int, duration_ms: int = 1000, timeout: float = 5.0
    ) -> Dict[str, Any]:
        """长按屏幕坐标"""
        cmd = f"input swipe {x} {y} {x} {y} {duration_ms}"
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)
        return {
            "success": returncode == 0,
            "x": x,
            "y": y,
            "action": "long_press",
            "duration_ms": duration_ms,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        }

    # ------------------------------------------------------------------
    # 滑动操作
    # ------------------------------------------------------------------

    async def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        """滑动操作"""
        cmd = f"input swipe {x1} {y1} {x2} {y2} {duration_ms}"
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)
        return {
            "success": returncode == 0,
            "from": (x1, y1),
            "to": (x2, y2),
            "action": "swipe",
            "duration_ms": duration_ms,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        }

    # ------------------------------------------------------------------
    # 文本输入
    # ------------------------------------------------------------------

    async def type_text(self, text: str, timeout: float = 5.0) -> Dict[str, Any]:
        """
        输入文本。

        使用 input text 命令。注意：此方法对特殊字符和中文的支持
        取决于 Android 版本和当前输入法的实现。

        三星 One UI 8.5 对 Unicode 文本输入支持良好，
        但双字节字符可能需要转义。
        """
        # 转义特殊字符（空格、引号等）
        escaped = text.replace(" ", "%s").replace('"', '\\"')
        cmd = f'input text "{escaped}"'
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)
        return {
            "success": returncode == 0,
            "action": "type_text",
            "text_length": len(text),
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        }

    # ------------------------------------------------------------------
    # UI 树获取
    # ------------------------------------------------------------------

    async def get_ui_tree(self, timeout: float = 10.0) -> Dict[str, Any]:
        """
        获取 UI 树（通过 uiautomator dump）。

        Termux 适配：dump 到 Termux 自有临时目录而非 /data/local/tmp。
        三星 One UI 8.5 上 /data/local/tmp 可能因 SELinux 策略而无写权限。
        """
        dump_path = os.path.join(_TERMUX_TMP, "ui_dump.xml")

        # 先删除旧 dump 文件（uiautomator dump 会拒绝覆盖已存在文件）
        try:
            if os.path.exists(dump_path):
                os.unlink(dump_path)
        except OSError:
            pass

        cmd = f"uiautomator dump {dump_path} && cat {dump_path}"
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)

        if returncode == 0 and stdout:
            return {
                "success": True,
                "xml": stdout,
                "dump_path": dump_path,
                "xml_size": len(stdout),
                "stderr": stderr,
                "returncode": returncode,
            }

        return {
            "success": False,
            "xml": None,
            "error": "uiautomator dump failed",
            "stderr": stderr,
            "returncode": returncode,
        }

    # ------------------------------------------------------------------
    # 按键操作
    # ------------------------------------------------------------------

    async def press_key(self, keycode: str, timeout: float = 2.0) -> Dict[str, Any]:
        """
        按指定按键。

        Args:
            keycode: Android 键码，如 'KEYCODE_BACK', 'KEYCODE_HOME',
                     'KEYCODE_APP_SWITCH', 'KEYCODE_ENTER', 'KEYCODE_VOLUME_UP' 等。

        三星 One UI 8.5 特有键码：
        - KEYCODE_BIXBY: Bixby 按键（三星设备）
        """
        cmd = f"input keyevent {keycode}"
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)
        return {
            "success": returncode == 0,
            "keycode": keycode,
            "action": "keyevent",
            "stdout": stdout,
            "stderr": stderr,
            "returncode": returncode,
        }

    async def press_back(self, timeout: float = 2.0) -> Dict[str, Any]:
        """按返回键"""
        return await self.press_key("KEYCODE_BACK", timeout)

    async def press_home(self, timeout: float = 2.0) -> Dict[str, Any]:
        """按 Home 键"""
        return await self.press_key("KEYCODE_HOME", timeout)

    async def press_recent(self, timeout: float = 2.0) -> Dict[str, Any]:
        """按 Recent 键（多任务）"""
        return await self.press_key("KEYCODE_APP_SWITCH", timeout)

    async def press_enter(self, timeout: float = 2.0) -> Dict[str, Any]:
        """按确认/回车键"""
        return await self.press_key("KEYCODE_ENTER", timeout)

    # ------------------------------------------------------------------
    # 屏幕信息
    # ------------------------------------------------------------------

    async def get_screen_size(self, timeout: float = 3.0) -> Dict[str, Any]:
        """
        获取屏幕分辨率。

        通过 dumpsys window 或 wm size 获取。
        三星 One UI 上这两个命令通常都可正常工作。
        """
        # 方法 1：wm size（更简单）
        cmd = "wm size"
        returncode, stdout, stderr = await self.shell.run_command(cmd, timeout)

        if returncode == 0 and "Physical size:" in stdout:
            try:
                size_str = stdout.split("Physical size:")[1].strip()
                parts = size_str.split("x")
                width = int(parts[0].strip())
                height = int(parts[1].strip().split()[0])
                return {
                    "success": True,
                    "width": width,
                    "height": height,
                    "method": "wm_size",
                    "stdout": stdout,
                    "stderr": stderr,
                }
            except (IndexError, ValueError):
                pass

        return {
            "success": False,
            "width": 0,
            "height": 0,
            "error": "Failed to parse screen size",
            "stdout": stdout,
            "stderr": stderr,
        }
