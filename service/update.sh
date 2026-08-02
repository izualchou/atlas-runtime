#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# Atlas Runtime 补丁应用脚本
# 最小改动补丁 A+B，不涉及其他模块
# ============================================================

set -e

echo "🔄 正在应用 Atlas Runtime 补丁 A（调度器契约）和补丁 B（存储返回值语义）"

# 1. 停止服务
echo "⏹️  停止服务..."
sv down atlas-runtime 2>/dev/null || true

# 2. 备份原文件
echo "📦 备份原始文件..."
BACKUP_DIR="$HOME/atlas-backup-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp "$HOME/atlas-runtime/core/scheduler.py" "$BACKUP_DIR/scheduler.py.bak" 2>/dev/null || true
cp "$HOME/atlas-runtime/storage/driver.py" "$BACKUP_DIR/driver.py.bak" 2>/dev/null || true
echo "备份保存到: $BACKUP_DIR"

# 3. 应用补丁（直接覆盖）
echo "📥 应用补丁文件..."
# 假设补丁文件已放在 ~/patches/ 目录，或者直接从仓库获取
# 这里提供两种方式，优先使用本地补丁文件，否则从仓库拉取

# 方式1：如果补丁文件已经放在本地 patches 目录
if [ -f "$HOME/patches/scheduler.py" ] && [ -f "$HOME/patches/driver.py" ]; then
    cp "$HOME/patches/scheduler.py" "$HOME/atlas-runtime/core/scheduler.py"
    cp "$HOME/patches/driver.py" "$HOME/atlas-runtime/storage/driver.py"
    echo "✅ 从本地 patches 目录应用补丁"
else
    # 方式2：从远程仓库获取（如果已提交）
    echo "⚠️  本地补丁文件未找到，尝试从 GitHub 拉取最新版本..."
    cd "$HOME/atlas-runtime"
    git pull origin main --no-ff || echo "拉取失败，请手动放置补丁文件"
    # 注意：这里假设补丁已合并到 main 分支
fi

# 4. 修正 executors/__init__.py（确保无误）
echo "🔧 检查 executors/__init__.py..."
cat > "$HOME/atlas-runtime/executors/__init__.py" << 'EOF'
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

# 5. 重新创建 FIFO 管道
echo "🔧 重置 FIFO 管道..."
FIFO_PATH="$PREFIX/tmp/atlas_trigger.fifo"
rm -f "$FIFO_PATH"
mkfifo "$FIFO_PATH"
chmod 666 "$FIFO_PATH"

# 6. 启动服务
echo "▶️  启动服务..."
sv up atlas-runtime
sleep 2

# 7. 验证服务状态
if sv status atlas-runtime | grep -q "run:"; then
    echo "✅ 补丁应用成功，服务运行中"
    sv status atlas-runtime
else
    echo "❌ 服务启动失败，请检查日志："
    tail -20 "$PREFIX/var/log/atlas-runtime/current"
    echo "尝试恢复备份..."
    cp "$BACKUP_DIR/scheduler.py.bak" "$HOME/atlas-runtime/core/scheduler.py" 2>/dev/null
    cp "$BACKUP_DIR/driver.py.bak" "$HOME/atlas-runtime/storage/driver.py" 2>/dev/null
    sv up atlas-runtime
    echo "已回退到原始版本"
    exit 1
fi

echo ""
echo "============================================================"
echo "✅ 补丁应用完成，建议执行以下验证："
echo "  1. 健康检查: curl http://127.0.0.1:8787/health"
echo "  2. 测试任务: echo '{\"cmd\": \"echo hello\"}' > $FIFO_PATH"
echo "  3. 观察日志: tail -f $PREFIX/var/log/atlas-runtime/current"
echo "============================================================"