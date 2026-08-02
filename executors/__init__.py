mkdir -p executors
cat > executors/__init__.py << 'EOF'
# executors/__init__.py
"""
执行器模块
提供 Shell、UI 自动化、高权限操作等执行能力
"""

from .shell_executor import SafeShellExecutor
from .ui_automation import UIAutomationExecutor
from .high_privilege import HighPrivilegeExecutor

__all__ = [
    "SafeShellExecutor",
    "UIAutomationExecutor",
    "HighPrivilegeExecutor",
]
EOF