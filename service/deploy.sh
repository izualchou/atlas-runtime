#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# Atlas Runtime v8.0 LTS - 一键部署脚本
# 适用平台: Android 12+ (Termux)
# ============================================================

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
print_step() { echo -e "${BLUE}[步骤]${NC} $1"; }
print_ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[警告]${NC} $1"; }
print_error(){ echo -e "${RED}[错误]${NC} $1"; }
check_command() { command -v "$1" &> /dev/null; }

# 1. 环境检查
print_step "检查 Termux 环境..."
if [ -z "$PREFIX" ] || [ ! -d "$PREFIX" ]; then
    print_error "未检测到 Termux 环境，请在 Termux 中运行此脚本。"
    exit 1
fi
print_ok "Termux 环境检测通过 (PREFIX=$PREFIX)"

MISSING_PKGS=""
check_command "python3" || MISSING_PKGS="$MISSING_PKGS python"
check_command "sv"      || MISSING_PKGS="$MISSING_PKGS termux-services"
check_command "termux-wake-lock" || MISSING_PKGS="$MISSING_PKGS termux-tools"
check_command "curl"    || MISSING_PKGS="$MISSING_PKGS curl"

if [ -n "$MISSING_PKGS" ]; then
    print_warn "缺少必要依赖:$MISSING_PKGS，正在自动安装..."
    pkg update -y
    pkg install -y $MISSING_PKGS
fi

NEED_PY_UPGRADE=$(python3 -c "import sys; print(1 if sys.version_info < (3, 11) else 0)" 2>/dev/null || echo "1")
if [ "$NEED_PY_UPGRADE" -eq 1 ]; then
    print_warn "Python 版本过旧，正在升级..."
    pkg install python -y
fi
print_ok "Python 环境: $(python3 --version)"

# 2. Python 依赖
print_step "安装 Python 依赖..."
python3 -m pip install --upgrade pip
python3 -m pip install aiosqlite msgpack psutil pyyaml aiohttp
print_ok "依赖安装完成"

# 3. 克隆/更新代码
print_step "获取 Atlas Runtime 源代码..."
ATLAS_HOME="$HOME/atlas-runtime"
if [ -d "$ATLAS_HOME/.git" ]; then
    print_warn "检测到已有代码，正在更新..."
    (cd "$ATLAS_HOME" && git pull)
else
    rm -rf "$ATLAS_HOME"
    git clone https://github.com/izualchou/atlas-runtime.git "$ATLAS_HOME"
fi

# 4. 清理旧服务
print_step "清理旧服务配置..."
if [ -d "$PREFIX/var/service/atlas-runtime" ]; then
    sv down atlas-runtime 2>/dev/null || true
    sv-disable atlas-runtime 2>/dev/null || true
    rm -rf "$PREFIX/var/service/atlas-runtime"
fi

# 5. 创建 runit 服务
print_step "配置 runit 服务引擎..."
mkdir -p "$PREFIX/var/service/atlas-runtime"
mkdir -p "$PREFIX/var/log/atlas-runtime"
cp "$ATLAS_HOME/service/run" "$PREFIX/var/service/atlas-runtime/run"
chmod +x "$PREFIX/var/service/atlas-runtime/run"

# 6. 开机自启
print_step "配置 Boot 开机引导..."
mkdir -p ~/.termux/boot/
cat > ~/.termux/boot/start-atlas-runtime << 'BOOT_EOF'
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
if [ -f /data/data/com.termux/files/usr/etc/profile ]; then
    . /data/data/com.termux/files/usr/etc/profile
fi
if [ -f /data/data/com.termux/files/usr/etc/profile.d/start-services.sh ]; then
    . /data/data/com.termux/files/usr/etc/profile.d/start-services.sh
fi
BOOT_EOF
chmod +x ~/.termux/boot/start-atlas-runtime

# 7. FIFO 与 Tasker 脚本
print_step "初始化 IPC 通信链路..."
FIFO_PATH="$PREFIX/tmp/atlas_trigger.fifo"
rm -f "$FIFO_PATH"
mkfifo "$FIFO_PATH"
chmod 666 "$FIFO_PATH"

mkdir -p ~/.termux/tasker/
cat > ~/.termux/tasker/trigger_atlas << 'TRIGGER_EOF'
#!/data/data/com.termux/files/usr/bin/bash
FIFO_PATH="/data/data/com.termux/files/usr/tmp/atlas_trigger.fifo"
if [ $# -eq 0 ]; then
    echo "Usage: trigger_atlas '{\"trigger\":\"xxx\"}'"
    exit 1
fi
if command -v timeout &>/dev/null; then
    timeout 3s bash -c "echo '$1' > '$FIFO_PATH'" 2>/dev/null || { echo "FIFO 写入超时"; exit 1; }
else
    echo "$1" > "$FIFO_PATH"
fi
TRIGGER_EOF
chmod +x ~/.termux/tasker/trigger_atlas

# 8. 启动服务
print_step "启动 Atlas Runtime 服务..."
sv-enable atlas-runtime 2>/dev/null || true
sv up atlas-runtime
sleep 2

if sv status atlas-runtime | grep -q "run:"; then
    print_ok "服务运行成功: $(sv status atlas-runtime)"
else
    print_warn "服务启动中，请稍后通过 sv status atlas-runtime 确认"
fi

echo ""
echo "============================================================"
echo -e "${GREEN}🎉 Atlas Runtime v8.0 LTS 部署完成！${NC}"
echo "============================================================"
echo "验证命令:"
echo "  服务状态: sv status atlas-runtime"
echo "  实时日志: tail -f $PREFIX/var/log/atlas-runtime/current"
echo "  健康检查: curl http://127.0.0.1:8787/health"
echo "  FIFO触发: echo '{\"trigger\":\"ping\"}' > $PREFIX/tmp/atlas_trigger.fifo"
echo "============================================================"
