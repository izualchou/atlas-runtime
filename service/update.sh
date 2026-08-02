#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# Atlas Runtime v8.0 LTS - 一键更新脚本
# 应用所有修复补丁，无需重新部署
# ============================================================

set -e

echo "🔄 Atlas Runtime 更新开始..."

# 1. 停止服务
echo "⏹️  停止服务..."
sv down atlas-runtime 2>/dev/null || true

# 2. 更新代码（保留配置和数据）
echo "📥 更新代码..."
cd ~/atlas-runtime
git pull

# 3. 确保依赖完整
echo "📦 安装依赖..."
pkg install -y python-psutil 2>/dev/null || true
python3 -m pip install -r requirements.txt --no-deps 2>/dev/null || true

# 4. 修复已知的文件问题
echo "🔧 修复执行器 __init__.py..."
cat > executors/__init__.py << 'EOF'
# executors/__init__.py
"""
执行器模块
"""
from .shell_executor import SafeShellExecutor
from .ui_automation import UIAutomationExecutor
from .high_privilege import HighPrivilegeExecutor
__all__ = ["SafeShellExecutor", "UIAutomationExecutor", "HighPrivilegeExecutor"]
EOF

# 5. 重新创建 FIFO（确保权限）
echo "🔧 修复 FIFO 管道..."
FIFO_PATH="$PREFIX/tmp/atlas_trigger.fifo"
rm -f "$FIFO_PATH"
mkfifo "$FIFO_PATH"
chmod 666 "$FIFO_PATH"

# 6. 启动服务
echo "▶️  启动服务..."
sv up atlas-runtime
sleep 2

# 7. 验证
if sv status atlas-runtime | grep -q "run:"; then
    echo "✅ 更新完成，服务运行中"
    sv status atlas-runtime
else
    echo "⚠️  服务状态异常，请检查日志"
    tail -10 $PREFIX/var/log/atlas-runtime/current
    exit 1
fi

echo "🌐 健康检查: curl http://127.0.0.1:8787/health"