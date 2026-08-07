# core/shell_executor.py（兼容性存根）
"""
已合并至 executors/shell_executor.py（v9.0 架构优化）。

本文件保留以维护向后兼容性——所有通过 `from core.shell_executor import ...`
的导入路径仍然有效。新代码请使用 `from executors import SafeShellExecutor`。

旧版本是 executors 版本的一个功能不完整副本（缺少 Termux PATH 处理）。
推荐始终使用 executors 版本以获得完整的 PATH 构建和 Android 环境适配。
"""

from executors.shell_executor import SafeShellExecutor  # noqa: F401

# 保持旧 Logger 名称不变，避免日志分析工具失效
# 注意：改用 executors 版本的 Logger，旧路径无影响
