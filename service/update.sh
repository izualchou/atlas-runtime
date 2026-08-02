#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# Atlas Runtime v9.0 — 补丁/更新脚本
# Samsung One UI 8.5 + Termux
# ============================================================

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   Atlas Runtime v9.0 — 更新/补丁工具                   ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ---- 1. 停止服务 ----
echo -e "${YELLOW}[1/6]${NC} 停止当前服务..."
sv down atlas-runtime 2>/dev/null || true
sleep 1
echo "      ✓ 服务已停止"

# ---- 2. 备份 ----
echo -e "${YELLOW}[2/6]${NC} 创建备份..."
BACKUP_DIR="$HOME/atlas-backup-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 备份关键文件
for f in \
    core/scheduler.py \
    core/bootstrap.py \
    core/state_manager.py \
    storage/driver.py \
    storage/battery_aware.py \
    executors/shell_executor.py \
    executors/high_privilege.py \
    executors/ui_automation.py \
    config/runtime.yaml \
    ; do
    if [ -f "$HOME/atlas-runtime/$f" ]; then
        mkdir -p "$(dirname "$BACKUP_DIR/$f")"
        cp "$HOME/atlas-runtime/$f" "$BACKUP_DIR/$f"
    fi
done

echo "      ✓ 备份保存到: $BACKUP_DIR"

# ---- 3. 应用补丁 ----
echo -e "${YELLOW}[3/6]${NC} 检查补丁文件..."

APPLIED=0
if [ -d "$HOME/patches" ]; then
    for patch_file in "$HOME/patches"/*.py; do
        if [ -f "$patch_file" ]; then
            fname=$(basename "$patch_file")
            # 查找目标文件
            target=$(find "$HOME/atlas-runtime" -name "$fname" -not -path "*/tests/*" -not -path "*/backup/*" 2>/dev/null | head -1)
            if [ -n "$target" ]; then
                cp "$patch_file" "$target"
                echo "      ✓ 应用补丁: $fname → $(dirname "$target" | sed "s|$HOME/atlas-runtime/||")"
                APPLIED=$((APPLIED + 1))
            fi
        fi
    done
fi

if [ $APPLIED -eq 0 ]; then
    # 从 GitHub 拉取最新代码
    echo "      未找到本地补丁，从 GitHub 拉取..."
    cd "$HOME/atlas-runtime"
    git fetch origin main 2>/dev/null && git reset --hard origin/main 2>/dev/null || {
        echo -e "      ${RED}✗${NC} GitHub 拉取失败，请手动更新"
    }
fi

# ---- 4. 恢复关键配置 ----
echo -e "${YELLOW}[4/6]${NC} 恢复本地配置..."
# 恢复 config（如果备份中存在）
if [ -f "$BACKUP_DIR/config/runtime.yaml" ]; then
    cp "$BACKUP_DIR/config/runtime.yaml" "$HOME/atlas-runtime/config/runtime.yaml"
    echo "      ✓ 配置已恢复"
fi

# ---- 5. 重建 FIFO ----
echo -e "${YELLOW}[5/6]${NC} 重建 FIFO 管道..."
FIFO_PATH="/data/data/com.termux/files/usr/tmp/atlas_trigger.fifo"
rm -f "$FIFO_PATH"
mkfifo "$FIFO_PATH" 2>/dev/null && chmod 666 "$FIFO_PATH"
echo "      ✓ FIFO 就绪: $FIFO_PATH"

# ---- 6. 启动服务 ----
echo -e "${YELLOW}[6/6]${NC} 启动服务..."
sv up atlas-runtime 2>/dev/null || true
sleep 3

# ---- 验证 ----
echo ""
if sv status atlas-runtime 2>/dev/null | grep -q "run:"; then
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   ✓ 更新完成，服务运行中                                ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "  验证:"
    echo "    sv status atlas-runtime     # $(sv status atlas-runtime 2>/dev/null)"
    echo "    curl http://127.0.0.1:8787/health"
    echo ""
else
    echo -e "${RED}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║   ✗ 服务启动失败                                        ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "  日志:"
    tail -20 "/data/data/com.termux/files/usr/var/log/atlas-runtime/current" 2>/dev/null || echo "    无法读取日志"
    echo ""
    echo "  恢复备份:"
    echo "    cp -r $BACKUP_DIR/* $HOME/atlas-runtime/"
    echo "    sv up atlas-runtime"
    exit 1
fi
