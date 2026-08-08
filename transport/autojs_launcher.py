# transport/autojs_launcher.py
"""
AutoJS6 启动器（AutoJS6 Launcher）。

通过 Android `am startservice` / `am start` 命令启动 AutoJS6 自动化脚本。
参数经文件传递（写入 /sdcard/atlas_shared/），Intent 仅传递文件路径，
避免 Intent extras 大小限制（1MB）和 Shell 注入风险。

设计原则:
- 双包名回退: 先尝试 org.autojs.autoxjs.v6，失败后尝试 org.autojs.autojs
- 文件参数传递: JSON 参数写入文件 → Intent 仅传文件路径 → AutoJS6 侧读取
- Knox 兼容: Samsung Knox 可能拦截 am startservice，提供文件标记备选方案
- 超时保护: 30 秒超时防止僵尸进程

v9.1: 新增 autojs_fallback 标记模式，用于 Knox 拦截时的降级启动。
"""

import json
import logging
import os
import uuid
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Atlas.AutoJS6Launcher")

# 默认共享目录（与 result_callback.py 一致）
DEFAULT_SHARED_DIR = "/sdcard/atlas_shared"

# AutoJS6 包名列表（按优先顺序尝试）
AUTOJS6_PACKAGES = [
    "org.autojs.autoxjs.v6",   # AutoX.js (AutoJS6 主分支)
    "org.autojs.autojs",        # Auto.js 原版
]

# AutoJS6 服务/Activity
AUTOJS6_SERVICE = "org.autojs.autojs.ui.settings.SettingsActivity"


@dataclass
class LaunchConfig:
    """AutoJS6 启动配置"""
    shared_dir: str = DEFAULT_SHARED_DIR
    enable_fallback_file: bool = True   # Knox 拦截时启用文件标记备选
    fallback_timeout: float = 60.0      # 文件标记模式的等待超时（秒）
    command_timeout: float = 15.0       # am 命令超时（秒）
    auto_retry: bool = True             # 第一个包名失败时自动重试


@dataclass
class LaunchResult:
    """启动结果"""
    success: bool
    script_name: str
    package_used: Optional[str] = None
    params_file: Optional[str] = None
    error: Optional[str] = None
    fallback_used: bool = False
    pid: Optional[int] = None


class AutoJS6Launcher:
    """
    AutoJS6 脚本启动器。

    典型用法:
        from executors.shell_executor import SafeShellExecutor
        executor = SafeShellExecutor()
        launcher = AutoJS6Launcher(executor)

        result = await launcher.launch(
            script_name="sim_switch_verify.js",
            params={"slot": 0, "expected_operator": "中国移动"},
        )
    """

    def __init__(self, executor):
        """
        Args:
            executor: 实现 BaseExecutor 协议的执行器实例（如 SafeShellExecutor）
        """
        self.executor = executor
        self.config = LaunchConfig()

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    async def launch(
        self,
        script_name: str,
        params: Optional[Dict[str, Any]] = None,
        package_index: int = 0,
    ) -> LaunchResult:
        """
        启动 AutoJS6 脚本。

        Args:
            script_name: 脚本文件名 (e.g., "sim_switch_verify.js")
            params: 脚本参数字典 (写入 JSON 文件传递)
            package_index: AutoJS6 包名列表的起始索引 (用于重试)

        Returns:
            LaunchResult: 启动结果
        """
        params = params or {}

        # 1. 写入参数文件
        params_file = await self._write_params_file(script_name, params)

        # 2. 尝试所有包名
        last_error = None
        for i in range(package_index, len(AUTOJS6_PACKAGES)):
            pkg = AUTOJS6_PACKAGES[i]
            result = await self._launch_with_package(script_name, pkg, params_file)

            if result.success:
                logger.info(
                    f"AutoJS6: launched {script_name} via {pkg}"
                )
                return result

            last_error = result.error

            if not self.config.auto_retry:
                break

            logger.warning(
                f"AutoJS6: {pkg} failed ({result.error}), trying next package..."
            )

        # 3. 全部包名失败 → 降级到文件标记模式
        if self.config.enable_fallback_file:
            logger.warning(
                f"AutoJS6: all packages failed, enabling fallback file marker mode"
            )
            return await self._launch_fallback(script_name, params_file)

        return LaunchResult(
            success=False,
            script_name=script_name,
            params_file=params_file,
            error=f"All packages failed: {last_error}",
        )

    # ------------------------------------------------------------------
    # 内部方法：启动
    # ------------------------------------------------------------------

    async def _launch_with_package(
        self, script_name: str, package: str, params_file: str
    ) -> LaunchResult:
        """尝试通过指定包名启动 AutoJS6。"""
        try:
            # 构建 am start 命令
            # 注意：AutoJS6 通过 Intent extras 传递参数文件路径
            cmd = (
                f"am startservice -a org.autojs.autojs.action.START_SCRIPT "
                f"-n {package}/org.autojs.autojs.script.ScriptExecutionService "
                f"--es script_path \"{params_file}\" "
                f"--es script_name \"{script_name}\" "
                f"--ei launch_mode 1"
            )

            result = await self.executor.execute(
                cmd=cmd,
                timeout=self.config.command_timeout,
            )

            if result.success:
                return LaunchResult(
                    success=True,
                    script_name=script_name,
                    package_used=package,
                    params_file=params_file,
                    fallback_used=False,
                )

            # 尝试备选启动方式：am start + extras bundle
            logger.debug(
                f"AutoJS6: startservice failed for {package}, trying am start..."
            )
            cmd_alt = (
                f"am start -a android.intent.action.VIEW "
                f"-d \"autojs://script/{script_name}?params={params_file}\" "
                f"-n {package}/{AUTOJS6_SERVICE}"
            )

            result_alt = await self.executor.execute(
                cmd=cmd_alt,
                timeout=self.config.command_timeout,
            )

            if result_alt.success:
                return LaunchResult(
                    success=True,
                    script_name=script_name,
                    package_used=package,
                    params_file=params_file,
                    fallback_used=False,
                )

            return LaunchResult(
                success=False,
                script_name=script_name,
                params_file=params_file,
                error=f"Package {package}: both methods failed",
            )

        except Exception as e:
            return LaunchResult(
                success=False,
                script_name=script_name,
                params_file=params_file,
                error=f"Exception with {package}: {e}",
            )

    async def _launch_fallback(
        self, script_name: str, params_file: str
    ) -> LaunchResult:
        """
        Knox 降级方案：写入启动标记文件。

        AutoJS6 侧运行定时检测脚本 (e.g., 每 30 秒)，
        检测到 /sdcard/atlas_shared/autojs_fallback_*.json 后自启动对应脚本。
        """
        shared_dir = Path(self.config.shared_dir)
        shared_dir.mkdir(parents=True, exist_ok=True)

        fallback_id = str(uuid.uuid4())[:8]
        fallback_file = shared_dir / f"autojs_fallback_{fallback_id}.json"

        payload = {
            "type": "launch_request",
            "script_name": script_name,
            "params_file": params_file,
            "requested_at": __import__('time').time(),
            "fallback_id": fallback_id,
        }

        with open(fallback_file, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        logger.info(
            f"AutoJS6: fallback file written: {fallback_file} "
            f"(script={script_name})"
        )

        return LaunchResult(
            success=True,  # 文件写入成功，视作请求已发出
            script_name=script_name,
            params_file=params_file,
            fallback_used=True,
            error=None,
        )

    # ------------------------------------------------------------------
    # 内部方法：参数文件
    # ------------------------------------------------------------------

    async def _write_params_file(
        self, script_name: str, params: Dict[str, Any]
    ) -> str:
        """
        将脚本参数写入 JSON 文件。

        文件名: autojs_params_<uuid>.json
        内容: {"script_name": "...", "params": {...}, "timestamp": ...}
        """
        import asyncio
        return await asyncio.to_thread(self._write_params_file_sync, script_name, params)

    def _write_params_file_sync(
        self, script_name: str, params: Dict[str, Any]
    ) -> str:
        """参数文件写入的同步实现。"""
        shared_dir = Path(self.config.shared_dir)
        shared_dir.mkdir(parents=True, exist_ok=True)

        file_id = str(uuid.uuid4())[:8]
        params_file = shared_dir / f"autojs_params_{file_id}.json"

        payload = {
            "script_name": script_name,
            "params": params,
            "timestamp": __import__('time').time(),
            "version": "1.0",
        }

        with open(params_file, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        logger.debug(
            f"AutoJS6: params file written: {params_file} "
            f"(script={script_name}, keys={list(params.keys())})"
        )

        return str(params_file)

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    async def check_autojs_installed(self) -> List[str]:
        """
        检测已安装的 AutoJS6 包名。

        Returns:
            已安装的 AutoJS6 包名列表
        """
        try:
            result = await self.executor.execute(
                cmd="pm list packages | grep -E 'autojs|autoxjs'",
                timeout=5.0,
            )
            if not result.success:
                return []

            installed = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("package:"):
                    pkg = line.split("package:")[1]
                    if any(p in pkg for p in ["autojs", "autoxjs"]):
                        installed.append(pkg)
            return installed
        except Exception as e:
            logger.debug(f"AutoJS6: package check failed: {e}")
            return []
