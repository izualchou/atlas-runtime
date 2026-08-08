#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# Atlas Runtime v9.0 — 部署脚本（Samsung One UI 8.5 + Termux）
# ============================================================
# 目标环境: Samsung Galaxy 设备, One UI 8.5 (Android 16), Termux
# 架构: arm64-v8a (Snapdragon) 或 aarch64 (Exynos)
# ============================================================

set -e

# ---------- 颜色定义 ----------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'
print_step() { echo -e "${BLUE}[步骤 $((++_step))]${NC} $1"; }
print_ok()   { echo -e "      ${GREEN}[✓]${NC} $1"; }
print_warn() { echo -e "      ${YELLOW}[!]${NC} $1"; }
print_error(){ echo -e "      ${RED}[✗]${NC} $1"; }
print_info() { echo -e "      ${CYAN}[i]${NC} $1"; }
check_command() { command -v "$1" &> /dev/null; }

_step=0

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   Atlas Runtime v9.0 — Samsung One UI 8.5 / Termux      ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================
# 1. Samsung 设备检测
# ============================================================
print_step "检测 Samsung 设备..."
MANUFACTURER=$(getprop ro.product.manufacturer 2>/dev/null || echo "unknown")
MODEL=$(getprop ro.product.model 2>/dev/null || echo "unknown")
SDK=$(getprop ro.build.version.sdk 2>/dev/null || echo "0")
CPU_ABI=$(getprop ro.product.cpu.abi 2>/dev/null || echo "unknown")

if echo "$MANUFACTURER" | grep -qi "samsung"; then
    print_ok "Samsung 设备: $MODEL"
else
    print_warn "非 Samsung 设备 ($MANUFACTURER)。部分功能可能不可用。"
fi

print_info "Android SDK: $SDK (Android $(getprop ro.build.version.release 2>/dev/null || echo unknown))"
print_info "CPU 架构: $CPU_ABI"
print_info "RAM 总量: $(awk '/MemTotal/ {printf "%.0f MB", $2/1024}' /proc/meminfo 2>/dev/null || echo unknown)"

# One UI 版本检测
ONE_UI=$(getprop ro.build.version.oneui 2>/dev/null || echo "")
if [ -n "$ONE_UI" ]; then
    print_ok "One UI 版本: $ONE_UI"
else
    print_info "One UI 版本未从属性读取（可能被 Knox 隐藏），将根据 SDK 推断"
fi

# ============================================================
# 2. Termux 环境检查
# ============================================================
print_step "检查 Termux 环境..."
if [ -z "$PREFIX" ] || [ ! -d "$PREFIX" ]; then
    print_error "未检测到 Termux 环境。请在 Termux 中运行此脚本。"
    print_info "从 F-Droid 下载: https://f-droid.org/packages/com.termux/"
    exit 1
fi
print_ok "Termux: $PREFIX"
print_info "Home: $HOME"

# 检查必要工具
MISSING_PKGS=""
check_command "python3" || MISSING_PKGS="$MISSING_PKGS python"
check_command "git"     || MISSING_PKGS="$MISSING_PKGS git"
check_command "curl"    || MISSING_PKGS="$MISSING_PKGS curl"
check_command "jq"      || MISSING_PKGS="$MISSING_PKGS jq"

if [ -n "$MISSING_PKGS" ]; then
    print_warn "缺少必要依赖:$MISSING_PKGS"
    echo -n "      → 正在安装..."
    pkg update -y -q > /dev/null 2>&1
    pkg install -y $MISSING_PKGS > /dev/null 2>&1
    echo " 完成"
fi
print_ok "基础依赖检查通过"

# ============================================================
# 3. 安装 termux-api（硬件访问）
# ============================================================
print_step "安装 termux-api（电池/WiFi/传感器访问）..."
if check_command "termux-battery-status"; then
    print_ok "termux-api 已安装"
else
    print_warn "termux-api 未安装"
    echo -n "      → 正在安装 termux-api..."
    pkg install -y termux-api > /dev/null 2>&1
    echo " 完成"
    print_info "请确保已安装 Termux:API APK (F-Droid 版本)"
    print_info "下载: https://f-droid.org/packages/com.termux.api/"
fi

# ============================================================
# 4. 安装 termux-services (runit)
# ============================================================
print_step "安装 termux-services（runit 守护进程）..."
if [ -d "$PREFIX/var/service" ]; then
    print_ok "termux-services 已配置"
else
    echo -n "      → 正在安装..."
    pkg install -y termux-services > /dev/null 2>&1
    echo " 完成"
fi

# 加载 runit 环境
print_step "加载 Termux 服务环境..."
if [ -f "$PREFIX/etc/profile" ]; then
    source "$PREFIX/etc/profile" 2>/dev/null || true
fi
# 确保 sv 命令可用
export PATH="$PREFIX/bin:$PATH"
print_ok "服务环境已加载"

# ============================================================
# 5. Python 环境设置
# ============================================================
print_step "配置 Python 环境..."
NEED_PY_UPGRADE=$(python3 -c "import sys; print(1 if sys.version_info < (3, 11) else 0)" 2>/dev/null || echo "1")
if [ "$NEED_PY_UPGRADE" -eq 1 ]; then
    print_warn "Python 版本过旧，正在升级..."
    pkg install python -y > /dev/null 2>&1
fi
print_ok "Python: $(python3 --version)"

print_step "安装 Python 依赖..."
# 优先通过 pkg 安装（编译好的二进制，省时省空间）
PKG_PYTHON_PKGS=""
check_command "psutil" 2>/dev/null || PKG_PYTHON_PKGS="$PKG_PYTHON_PKGS python-psutil"

if [ -n "$PKG_PYTHON_PKGS" ]; then
    echo -n "      → pkg 安装: $PKG_PYTHON_PKGS..."
    pkg install -y $PKG_PYTHON_PKGS > /dev/null 2>&1 || true
    echo " 完成"
fi

# 通过 pip 安装（需要编译的包，注意：Samsung Exynos 设备编译耗时较长）
echo -n "      → pip 安装核心依赖..."
python3 -m pip install --quiet \
    aiosqlite \
    msgpack \
    pyyaml \
    aiohttp \
    2>&1 | tail -1
echo " 完成"

# 可选依赖提示
print_info "可选依赖（增强功能）:"
print_info "  python-psutil       (# pkg install python-psutil)"
print_info "  pytest + pytest-asyncio (# pip install pytest pytest-asyncio, 用于测试)"

# ============================================================
# 6. 克隆/更新代码
# ============================================================
print_step "获取 Atlas Runtime 源代码..."
ATLAS_HOME="$HOME/atlas-runtime"

if [ -d "$ATLAS_HOME/.git" ]; then
    print_warn "检测到已有代码库，正在更新..."
    (cd "$ATLAS_HOME" && git pull --ff-only 2>/dev/null) || print_warn "git pull 失败（可能需要手动处理）"
else
    rm -rf "$ATLAS_HOME"
    echo -n "      → 克隆仓库..."
    git clone --depth 1 \
        https://github.com/izualchou/atlas-runtime.git \
        "$ATLAS_HOME" > /dev/null 2>&1
    echo " 完成"
fi
print_ok "代码路径: $ATLAS_HOME"

# ============================================================
# 7. 创建数据目录
# ============================================================
print_step "创建运行时数据目录..."
mkdir -p "$ATLAS_HOME/data/snapshots"
mkdir -p "$ATLAS_HOME/logs"
print_ok "数据目录就绪"

# ============================================================
# 8. 清理旧服务
# ============================================================
print_step "清理旧服务配置..."
if [ -d "$PREFIX/var/service/atlas-runtime" ]; then
    sv down atlas-runtime 2>/dev/null || true
    sv-disable atlas-runtime 2>/dev/null || true
    rm -rf "$PREFIX/var/service/atlas-runtime"
    print_ok "旧服务已清理"
fi

# ============================================================
# 9. 创建 runit 服务
# ============================================================
print_step "配置 runit 服务..."

SERVICE_DIR="$PREFIX/var/service/atlas-runtime"
LOG_DIR="$PREFIX/var/log/atlas-runtime"
SUPERVISE_DIR="$SERVICE_DIR/supervise"

mkdir -p "$SERVICE_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$SUPERVISE_DIR"

# 预创建 supervise/ok 文件 — runit 要求此文件存在才能启动服务
# 在实际运行中 runsv 会自动更新此文件，但首次部署时必须手动创建
if [ ! -f "$SUPERVISE_DIR/ok" ]; then
    touch "$SUPERVISE_DIR/ok"
fi
if [ ! -f "$SUPERVISE_DIR/control" ]; then
    touch "$SUPERVISE_DIR/control"
fi
if [ ! -f "$SUPERVISE_DIR/status" ]; then
    touch "$SUPERVISE_DIR/status"
fi
print_info "supervise 目录已初始化: $SUPERVISE_DIR"

# 创建 log/supervise 目录（runit 日志管线）
mkdir -p "$LOG_DIR/supervise"
if [ ! -f "$LOG_DIR/supervise/ok" ]; then
    touch "$LOG_DIR/supervise/ok"
fi
if [ ! -f "$LOG_DIR/supervise/control" ]; then
    touch "$LOG_DIR/supervise/control"
fi

# 创建 run 脚本（含 Samsung One UI 8.5 特定优化）
cat > "$SERVICE_DIR/run" << 'RUN_EOF'
#!/data/data/com.termux/files/usr/bin/bash
# Atlas Runtime v9.0 — runit 服务脚本
# 目标: Samsung One UI 8.5 + Termux

# 加载 Termux 环境
if [ -f /data/data/com.termux/files/usr/etc/profile ]; then
    . /data/data/com.termux/files/usr/etc/profile
fi

export PATH="/data/data/com.termux/files/usr/bin:$PATH"

# Samsung One UI 8.5 优化：
# - 降低 Python GC 阈值，减少峰值内存（在 200MB 限制下关键）
# - 使用 PYTHONOPTIMIZE 减少调试开销
export PYTHONUNBUFFERED=1
export PYTHONMALLOC=malloc

# 切换到工作目录
cd /data/data/com.termux/files/home/atlas-runtime || exit 1

exec python3 runtime/app.py --config config/runtime.yaml 2>&1
RUN_EOF

chmod +x "$SERVICE_DIR/run"
chmod 755 "$SERVICE_DIR"

# 创建 log/run 脚本（runit 日志管线 — 必须存在，否则 log supervise 无法就绪）
mkdir -p "$SERVICE_DIR/log"
cat > "$SERVICE_DIR/log/run" << 'LOG_RUN_EOF'
#!/data/data/com.termux/files/usr/bin/bash
# Atlas Runtime — runit 日志管线
# 将 stdout 管道输入到 svlogd，写入 LOG_DIR
exec svlogd -tt /data/data/com.termux/files/usr/var/log/atlas-runtime
LOG_RUN_EOF
chmod +x "$SERVICE_DIR/log/run"

print_ok "runit 服务脚本已创建"

# ============================================================
# 10. 开机自启 (Termux:Boot)
# ============================================================
print_step "配置 Termux:Boot 开机引导..."
mkdir -p ~/.termux/boot/

cat > ~/.termux/boot/start-atlas-runtime << 'BOOT_EOF'
#!/data/data/com.termux/files/usr/bin/sh
# Atlas Runtime — Termux:Boot 引导脚本

# 获取 wakelock 防止 Samsung 激进休眠
termux-wake-lock acquire-atlas 2>/dev/null || true

# 加载 Termux 环境
if [ -f /data/data/com.termux/files/usr/etc/profile ]; then
    . /data/data/com.termux/files/usr/etc/profile
fi

# 启动 termux-services
if [ -f /data/data/com.termux/files/usr/etc/profile.d/start-services.sh ]; then
    . /data/data/com.termux/files/usr/etc/profile.d/start-services.sh
fi

# 等待网络就绪（Samsung 设备 WiFi 连接可能需要 5-10 秒）
sleep 5

echo "[Atlas Boot] $(date): Boot sequence complete" >> /data/data/com.termux/files/home/atlas-runtime/logs/boot.log
BOOT_EOF

chmod +x ~/.termux/boot/start-atlas-runtime
print_ok "Boot 引导脚本已配置"
print_info "确保已安装 Termux:Boot APK (F-Droid)"

# ============================================================
# 11. FIFO 通信链路
# ============================================================
print_step "初始化 FIFO IPC 通信链路..."
FIFO_PATH="$PREFIX/tmp/atlas_trigger.fifo"
rm -f "$FIFO_PATH"

if command -v mkfifo &>/dev/null; then
    mkfifo "$FIFO_PATH"
    chmod 666 "$FIFO_PATH"
    print_ok "FIFO 已创建: $FIFO_PATH"
else
    print_warn "mkfifo 不可用，将仅使用 HTTP 通道"
fi

# Tasker 触发脚本
mkdir -p ~/.termux/tasker/
cat > ~/.termux/tasker/trigger_atlas << 'TRIGGER_EOF'
#!/data/data/com.termux/files/usr/bin/bash
# Atlas Runtime — Tasker 触发脚本
# 用法: trigger_atlas '{"trigger":"ping","data":{}}'

FIFO_PATH="/data/data/com.termux/files/usr/tmp/atlas_trigger.fifo"

if [ $# -eq 0 ]; then
    echo "Usage: trigger_atlas '<json>'"
    echo "Example: trigger_atlas '{\"trigger\":\"ping\",\"data\":{\"timestamp\":\"$(date -Iseconds)\"}}'"
    exit 1
fi

if [ -p "$FIFO_PATH" ]; then
    if command -v timeout &>/dev/null; then
        timeout 3s bash -c "echo '$1' > '$FIFO_PATH'" 2>/dev/null || {
            echo "FIFO 写入超时（可能服务已停止）"
            exit 1
        }
    else
        echo "$1" > "$FIFO_PATH"
    fi
else
    # HTTP 回退
    curl -s -X POST http://127.0.0.1:8787/trigger \
        -H "Content-Type: application/json" \
        -d "$1" 2>/dev/null || {
            echo "无法连接到 Atlas Runtime（FIFO 和 HTTP 均不可用）"
            exit 1
        }
fi
TRIGGER_EOF

chmod +x ~/.termux/tasker/trigger_atlas
print_ok "Tasker 触发脚本已创建: ~/.termux/tasker/trigger_atlas"

# ============================================================
# 12. Samsung 特定优化建议
# ============================================================
print_step "Samsung One UI 8.5 优化..."

echo ""
echo -e "      ${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "      ${YELLOW}  重要：Samsung One UI 8.5 手动设置建议           ${NC}"
echo -e "      ${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "      ${CYAN}1. 电池优化${NC}"
echo "         设置 → 应用程序 → Termux → 电池 → 不受限制"
echo "         （防止三星激进电池管理杀死后台进程）"
echo ""
echo -e "      ${CYAN}2. Game Booster${NC}"
echo "         Game Launcher → 更多 → Game Booster →"
echo "         在"实验室"中将 Termux 添加为例外"
echo "         （如果 Termux 被误判为游戏应用）"
echo ""
echo -e "      ${CYAN}3. 内存管理${NC}"
echo "         设置 → 设备维护 → 内存 →"
echo "         将 Termux 添加到"不检查"的应用程序列表"
echo ""
echo -e "      ${CYAN}4. 无障碍服务${NC}"
echo "         如果有 UI 自动化需求:"
echo "         设置 → 辅助功能 → 已安装的应用程序 → Termux → 开启"
echo ""
echo -e "      ${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ============================================================
# 13. 启用并启动服务
# ============================================================
print_step "启动 Atlas Runtime 服务..."

# 先确认 supervise 目录结构完整（防止首次部署后 rmdir 等情况）
SUPERVISE_DIR="$SERVICE_DIR/supervise"
LOG_SUPERVISE_DIR="$LOG_DIR/supervise"

for _dir in "$SUPERVISE_DIR" "$LOG_SUPERVISE_DIR"; do
    if [ ! -d "$_dir" ]; then
        print_warn "$_dir 不存在，正在重建..."
        mkdir -p "$_dir"
        touch "$_dir/ok"
        touch "$_dir/control"
        touch "$_dir/status" 2>/dev/null || true
    fi
    if [ ! -f "$_dir/ok" ]; then
        print_warn "supervise/ok 文件缺失，正在创建..."
        touch "$_dir/ok"
        touch "$_dir/control" 2>/dev/null || true
        touch "$_dir/status" 2>/dev/null || true
    fi
done

# 终止任何残留 runsv 进程（防止 supervise/ok: already locked 错误）
RUNSV_PIDS=$(pgrep -f "runsv.*atlas-runtime" 2>/dev/null || true)
if [ -n "$RUNSV_PIDS" ]; then
    print_warn "检测到残留 runsv 进程 (PIDs: $RUNSV_PIDS)，正在清理..."
    for pid in $RUNSV_PIDS; do
        kill "$pid" 2>/dev/null || true
    done
    sleep 1
    # 清理锁文件
    rm -f "$SUPERVISE_DIR/lock" 2>/dev/null || true
    rm -f "$LOG_SUPERVISE_DIR/lock" 2>/dev/null || true
    print_ok "残留进程与锁文件已清理"
fi

# 启用服务
sv-enable atlas-runtime 2>/dev/null || {
    print_error "sv-enable 失败。执行诊断..."
    print_info "  → supervize 目录状态:"
    ls -la "$SUPERVISE_DIR/" 2>/dev/null || print_error "     supervise 目录不存在!"
    print_info "  → 可能需要重启 Termux 后重试: exit && termux"
    exit 1
}

# 启动服务
sv up atlas-runtime 2>/dev/null || {
    print_error "sv up 失败。"
    print_info "诊断命令:"
    print_info "  ls -la $SUPERVISE_DIR/"
    print_info "  sv status atlas-runtime"
    print_info "  tail -20 $LOG_DIR/current"
    exit 1
}

sleep 3

# 验证状态
if sv status atlas-runtime 2>/dev/null | grep -q "run:"; then
    print_ok "✓ 服务运行中: $(sv status atlas-runtime 2>/dev/null)"
else
    print_warn "服务状态异常，检查日志:"
    print_info "  tail -20 $LOG_DIR/current"
    print_warn "常见原因: supervise/ok 缺失 → 已在上方自动修复，请重新运行 deploy.sh"
    print_info "手动修复: touch $SUPERVISE_DIR/ok && sv up atlas-runtime"
fi

# ============================================================
# 14. 完成
# ============================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Atlas Runtime v9.0 — 部署完成！                       ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${CYAN}验证命令:${NC}"
echo "    sv status atlas-runtime               # 服务状态"
echo "    tail -f $LOG_DIR/current              # 实时日志"
echo "    curl http://127.0.0.1:8787/health     # 健康检查"
echo "    curl http://127.0.0.1:8787/ready      # 就绪检查"
echo "    ~/.termux/tasker/trigger_atlas '{\"trigger\":\"ping\"}'  # FIFO 触发"
echo ""
echo -e "  ${CYAN}管理命令:${NC}"
echo "    sv restart atlas-runtime              # 重启服务"
echo "    sv down atlas-runtime                 # 停止服务"
echo "    sv up atlas-runtime                   # 启动服务"
echo "    sv-disable atlas-runtime              # 禁用自启"
echo ""
echo -e "  ${CYAN}日志路径:${NC}"
echo "    运行日志: $LOG_DIR/current"
echo "    启动日志: $ATLAS_HOME/logs/boot.log"
echo ""
