# platform/detector.py
"""
平台检测与能力发现模块（Samsung One UI 8.5 + Termux 适配）

职责：
- 检测设备制造商、型号、One UI 版本、Android API 级别
- 发现可用的 Termux 工具链（termux-api, termux-battery-status 等）
- 发现可用的 Android 系统命令（svc, input, uiautomator, service call 等）
- 提供能力标志位供其他模块决策使用
- 内存/存储容量评估

使用方式：
    from platform import PlatformInfo
    info = await PlatformInfo.discover()
    if info.has_termux_api:
        # 使用 termux-api 路径

已从 core/platform.py 迁移至 platform/detector.py（v9.0 架构优化）。
"""

import asyncio
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("Atlas.Platform")

# ---------------------------------------------------------------------------
# Termux 路径常量
# ---------------------------------------------------------------------------
TERMUX_PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
TERMUX_HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")
TERMUX_TMP = os.path.join(TERMUX_PREFIX, "tmp")


@dataclass
class PlatformInfo:
    """设备平台完整信息"""

    # ---- 基本标识 ----
    manufacturer: str = "unknown"
    model: str = "unknown"
    device: str = "unknown"
    android_version: str = "unknown"
    android_sdk: int = 0
    one_ui_version: str = "unknown"

    # ---- 硬件 ----
    cpu_arch: str = "unknown"
    cpu_cores: int = 0
    total_ram_mb: int = 0
    available_ram_mb: int = 0
    total_storage_mb: int = 0
    free_storage_mb: int = 0

    # ---- Termux 环境 ----
    is_termux: bool = False
    termux_prefix: str = ""
    termux_home: str = ""
    has_termux_api: bool = False
    has_termux_battery: bool = False
    has_termux_wifi: bool = False
    has_termux_telephony: bool = False
    has_termux_services: bool = False
    python_version: str = "unknown"

    # ---- Android 命令可用性 ----
    has_svc: bool = False       # svc wifi/data/...
    has_input: bool = False     # input tap/swipe/keyevent
    has_uiautomator: bool = False  # uiautomator dump
    has_settings: bool = False  # settings put/get
    has_service_call: bool = False  # service call (Samsung 事务码可能不同)
    has_cmd: bool = False       # cmd (Android 服务管理)
    has_dumpsys: bool = False   # dumpsys
    has_getprop: bool = False   # getprop

    # ---- 能力标志 ----
    is_samsung: bool = False
    is_one_ui: bool = False
    one_ui_major: int = 0
    has_dual_sim: bool = False
    has_root: bool = False
    fifo_writable_path: str = ""        # FIFO 可写路径
    temp_writable_path: str = ""        # Termux 内可写临时路径
    system_temp_writable: bool = False  # /data/local/tmp 是否可写

    # ---- 诊断信息 ----
    detection_errors: List[str] = field(default_factory=list)

    @staticmethod
    async def discover() -> "PlatformInfo":
        """
        异步发现平台能力。
        在后台线程中运行 shell 命令探测，避免阻塞事件循环。
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _discover_sync)


def _discover_sync() -> PlatformInfo:
    """同步执行平台探测（在 run_in_executor 中运行）"""
    info = PlatformInfo()

    # ---- 1. 检测 Termux 环境 ----
    info.is_termux = os.path.isdir(TERMUX_PREFIX) and "com.termux" in str(os.environ.get("PREFIX", ""))
    info.termux_prefix = TERMUX_PREFIX
    info.termux_home = TERMUX_HOME

    if info.is_termux:
        # Termux 内可写路径
        info.fifo_writable_path = TERMUX_TMP
        info.temp_writable_path = TERMUX_TMP
    else:
        info.fifo_writable_path = "/tmp"
        info.temp_writable_path = "/tmp"

    # ---- 2. 检测 Python 版本 ----
    info.python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    # ---- 3. getprop 探测（设备信息） ----
    _detect_device_props(info)

    # ---- 4. 检测 Android 命令可用性 ----
    _detect_android_commands(info)

    # ---- 5. 检测 Termux 工具链 ----
    if info.is_termux:
        _detect_termux_tools(info)

    # ---- 6. 检测硬件资源 ----
    _detect_hardware_resources(info)

    # ---- 7. 检测特殊能力 ----
    _detect_capabilities(info)

    # ---- 8. 生成平台摘要日志 ----
    _log_platform_summary(info)

    return info


def _run_shell(cmd: str, timeout: float = 3.0) -> Tuple[int, str, str]:
    """运行简单 shell 命令，返回 (returncode, stdout, stderr)"""
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return -1, "", str(e)


def _check_command(cmd: str) -> bool:
    """检查命令是否可用（在 PATH 中且可执行）"""
    return shutil.which(cmd) is not None


def _detect_device_props(info: PlatformInfo) -> None:
    """通过 getprop 获取设备属性"""
    # 制造商
    rc, out, _ = _run_shell("getprop ro.product.manufacturer")
    if rc == 0 and out:
        info.manufacturer = out.lower()
        info.is_samsung = "samsung" in info.manufacturer

    # 型号
    rc, out, _ = _run_shell("getprop ro.product.model")
    if rc == 0 and out:
        info.model = out

    # 设备代号
    rc, out, _ = _run_shell("getprop ro.product.device")
    if rc == 0 and out:
        info.device = out

    # Android 版本
    rc, out, _ = _run_shell("getprop ro.build.version.release")
    if rc == 0 and out:
        info.android_version = out

    # SDK 版本
    rc, out, _ = _run_shell("getprop ro.build.version.sdk")
    if rc == 0 and out:
        try:
            info.android_sdk = int(out)
        except ValueError:
            info.android_sdk = 0

    # 三星 One UI 版本检测
    if info.is_samsung:
        # 方法1：从 samsung framework 属性读取
        rc, out, _ = _run_shell("getprop ro.build.version.oneui")
        if rc == 0 and out:
            info.one_ui_version = out
            info.is_one_ui = True
        else:
            # 方法2：从 build fingerprint 推断
            rc, out, _ = _run_shell("getprop ro.build.PDA")
            if rc == 0 and out:
                # 三星固件格式通常包含 One UI 版本信息
                info.one_ui_version = f"detected_from_pda:{out}"
                info.is_one_ui = True
            else:
                # 方法3：从 SDK 和已知映射推断
                sdk_ui_map = {
                    36: "8.5",  # Android 16 → One UI 8.5
                    35: "8.0",  # Android 15 → One UI 8.0
                    34: "7.0",  # Android 14 → One UI 7.0
                    33: "6.0",  # Android 13 → One UI 6.0
                }
                info.one_ui_version = sdk_ui_map.get(info.android_sdk, "unknown")
                info.is_one_ui = info.one_ui_version != "unknown"

        # 提取主版本号
        try:
            if info.one_ui_version and info.one_ui_version[0].isdigit():
                info.one_ui_major = int(info.one_ui_version.split(".")[0])
        except (ValueError, IndexError):
            info.one_ui_major = 0

    # CPU 架构
    rc, out, _ = _run_shell("getprop ro.product.cpu.abi")
    if rc == 0 and out:
        info.cpu_arch = out
    else:
        # Python 回退
        import platform
        info.cpu_arch = platform.machine()


def _detect_android_commands(info: PlatformInfo) -> None:
    """检测 Android 系统命令可用性"""
    # 注意：Termux 中这些命令可能不在标准 PATH 中，需要完整路径
    android_bins = [
        "/system/bin/svc",
        "/system/bin/input",
        "/system/bin/uiautomator",
        "/system/bin/settings",
        "/system/bin/service",
        "/system/bin/cmd",
        "/system/bin/dumpsys",
        "/system/bin/getprop",
    ]

    for bin_path in android_bins:
        cmd_name = os.path.basename(bin_path)
        exists = os.path.isfile(bin_path) and os.access(bin_path, os.X_OK)

        if cmd_name == "svc":
            info.has_svc = exists
        elif cmd_name == "input":
            info.has_input = exists
        elif cmd_name == "uiautomator":
            info.has_uiautomator = exists
        elif cmd_name == "settings":
            info.has_settings = exists
        elif cmd_name == "service":
            info.has_service_call = exists
        elif cmd_name == "cmd":
            info.has_cmd = exists
        elif cmd_name == "dumpsys":
            info.has_dumpsys = exists
        elif cmd_name == "getprop":
            info.has_getprop = exists

    # 如果不在 /system/bin，尝试 PATH 查找
    if not info.has_svc and _check_command("svc"):
        info.has_svc = True
    if not info.has_input and _check_command("input"):
        info.has_input = True
    if not info.has_uiautomator and _check_command("uiautomator"):
        info.has_uiautomator = True
    if not info.has_settings and _check_command("settings"):
        info.has_settings = True
    if not info.has_service_call and _check_command("service"):
        info.has_service_call = True
    if not info.has_cmd and _check_command("cmd"):
        info.has_cmd = True


def _detect_termux_tools(info: PlatformInfo) -> None:
    """检测 Termux 工具链可用性"""
    # termux-api
    info.has_termux_api = _check_command("termux-battery-status")  # 探测性检查

    # 逐个检查 termux-api 子命令
    info.has_termux_battery = _check_command("termux-battery-status")
    info.has_termux_wifi = _check_command("termux-wifi-enable")
    info.has_termux_telephony = _check_command("termux-telephony-deviceinfo")
    info.has_termux_services = os.path.isdir(
        os.path.join(TERMUX_PREFIX, "var", "service")
    )


def _detect_hardware_resources(info: PlatformInfo) -> None:
    """检测硬件资源限制"""
    # CPU 核心数
    try:
        info.cpu_cores = os.cpu_count() or 0
    except Exception:
        info.cpu_cores = 0

    # 内存（通过 /proc/meminfo）
    try:
        with open("/proc/meminfo", "r") as f:
            meminfo = f.read()
            for line in meminfo.split("\n"):
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    info.total_ram_mb = kb // 1024
                elif line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    info.available_ram_mb = kb // 1024
    except (FileNotFoundError, PermissionError, IndexError, ValueError):
        info.detection_errors.append("Failed to read /proc/meminfo")

    # 存储空间
    try:
        stat = shutil.disk_usage(TERMUX_HOME if info.is_termux else "/")
        info.total_storage_mb = stat.total // (1024 * 1024)
        info.free_storage_mb = stat.free // (1024 * 1024)
    except Exception:
        info.detection_errors.append("Failed to get disk usage")

    # 检测 /data/local/tmp 是否可写
    try:
        test_path = "/data/local/tmp/.atlas_write_test"
        with open(test_path, "w") as f:
            f.write("test")
        os.unlink(test_path)
        info.system_temp_writable = True
    except (PermissionError, OSError):
        info.system_temp_writable = False


def _detect_capabilities(info: PlatformInfo) -> None:
    """检测特殊能力"""
    # 双 SIM 检测（三星设备通常支持）
    rc, out, _ = _run_shell("getprop persist.radio.multisim.config")
    if rc == 0 and out and out.lower() != "none":
        info.has_dual_sim = True
    elif info.is_samsung:
        # 三星大多数现代设备支持双 SIM
        info.has_dual_sim = True

    # Root 检测
    info.has_root = os.path.exists("/system/bin/su") or os.path.exists("/system/xbin/su")
    # 注意：三星 One UI 设备通常没有 root，除非用户主动获取


def _log_platform_summary(info: PlatformInfo) -> None:
    """输出平台信息摘要日志"""
    parts = [
        f"Device: {info.manufacturer}/{info.model} ({info.device})",
    ]
    if info.is_samsung:
        parts.append(f"One UI {info.one_ui_version} (detected)" if info.is_one_ui else "Samsung (non-One UI)")
    parts.append(f"Android {info.android_version} (SDK {info.android_sdk})")
    parts.append(f"CPU: {info.cpu_arch}, {info.cpu_cores} cores")
    parts.append(f"RAM: {info.total_ram_mb}MB total, {info.available_ram_mb}MB available")
    parts.append(f"Storage: {info.free_storage_mb}MB free / {info.total_storage_mb}MB total")
    parts.append(f"Termux: {'yes' if info.is_termux else 'no'}")
    if info.is_termux:
        parts.append(f"Termux-API: {'yes' if info.has_termux_api else 'no'}")
        parts.append(f"termux-battery: {'yes' if info.has_termux_battery else 'no'}")
        parts.append(f"termux-services: {'yes' if info.has_termux_services else 'no'}")
    parts.append(f"Dual SIM: {'yes' if info.has_dual_sim else 'no'}")
    parts.append(f"Root: {'yes' if info.has_root else 'no'}")
    parts.append(f"system_temp writable: {'yes' if info.system_temp_writable else 'no'}")
    parts.append(f"FIFO path: {info.fifo_writable_path}")
    parts.append(f"Python: {info.python_version}")

    logger.info(" | ".join(parts))

    if info.detection_errors:
        logger.warning(f"Detection warnings: {'; '.join(info.detection_errors)}")
