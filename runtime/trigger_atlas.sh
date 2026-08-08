#!/data/data/com.termux/files/usr/bin/bash
# ============================================================================
# trigger_atlas.sh — Tasker → Atlas Runtime FIFO/HTTP 双通道触发桥接
# ============================================================================
#
# 用途: 由 Tasker (Termux:Tasker 插件) 调用，将触发事件发送到 Atlas Runtime。
#       优先使用 FIFO (named pipe) 通道以获取最低延迟，
#       FIFO 不可用时自动回退到 HTTP POST 通道。
#
# 用法: trigger_atlas.sh <action_json>
#   action_json: 单行 JSON 字符串，形如:
#     {"action":"sim_switch","params":{"slot":0},"correlation_id":"tasker_001"}
#
# 环境变量 (Termux:Tasker 自动注入):
#   PREFIX  — Termux 安装路径 (e.g., /data/data/com.termux/files/usr)
#   HOME    — Termux 用户目录
#
# 出口码:
#   0  — 触发成功 (FIFO 写入成功 或 HTTP 200/201)
#   1  — 用法错误 (缺少参数)
#   2  — FIFO 不可用 & HTTP 失败 (最终失败)
#   3  — HTTP 返回非 2xx 状态码
#   4  — 网络错误 (curl 连接失败)
#
# 三星 One UI 8.5 约束:
#   - $PREFIX/tmp/ 在 Termux 内稳定可写
#   - 非 root 模式下 FIFO 可由 Termux 进程创建和读写
#   - Knox 不会拦截本地回环 HTTP (127.0.0.1)
# ============================================================================

set -euo pipefail

# ---- 配置 ----
FIFO_PATH="${PREFIX}/tmp/atlas_trigger.fifo"
HTTP_PORT="${ATLAS_HTTP_PORT:-8787}"
HTTP_HOST="${ATLAS_HTTP_HOST:-127.0.0.1}"
HTTP_TIMEOUT="${ATLAS_HTTP_TIMEOUT:-5}"
LOG_TAG="[Atlas.Trigger]"

# ---- 输入验证 ----
if [ $# -lt 1 ]; then
    echo "${LOG_TAG} ERROR: missing action_json argument" >&2
    echo "Usage: trigger_atlas.sh <action_json>" >&2
    exit 1
fi

ACTION_JSON="$1"

# 基础 JSON 格式验证
if ! echo "$ACTION_JSON" | grep -qE '^\s*\{.*\}\s*$'; then
    echo "${LOG_TAG} WARNING: action_json does not look like a JSON object: ${ACTION_JSON:0:80}..." >&2
fi

# ---- 通道 1: FIFO (Named Pipe) ----
# 检测 FIFO 是否存在且可写
if [ -p "$FIFO_PATH" ] && [ -w "$FIFO_PATH" ]; then
    # 使用 timeout 防止 FIFO 写入阻塞 (FIFO 的读端可能暂时不活跃)
    if echo "${ACTION_JSON}" | timeout 2 cat > "$FIFO_PATH" 2>/dev/null; then
        echo "${LOG_TAG} SUCCESS: FIFO write to ${FIFO_PATH}" >&2
        exit 0
    else
        echo "${LOG_TAG} WARNING: FIFO write timed out or failed, falling back to HTTP" >&2
    fi
else
    echo "${LOG_TAG} INFO: FIFO not available (${FIFO_PATH}), falling back to HTTP" >&2
fi

# ---- 通道 2: HTTP POST ----
HTTP_URL="http://${HTTP_HOST}:${HTTP_PORT}/trigger"

# 发送 HTTP POST 请求
HTTP_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "$HTTP_URL" \
    -H "Content-Type: application/json" \
    -H "X-Trigger-Source: tasker" \
    --max-time "$HTTP_TIMEOUT" \
    --connect-timeout 3 \
    -d "$ACTION_JSON" 2>/dev/null) || {
    echo "${LOG_TAG} ERROR: curl request failed (connection error to ${HTTP_URL})" >&2
    exit 4
}

# 从响应中分离 HTTP 状态码
HTTP_CODE=$(echo "$HTTP_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$HTTP_RESPONSE" | sed '$d')

case "$HTTP_CODE" in
    200|201|202)
        echo "${LOG_TAG} SUCCESS: HTTP ${HTTP_CODE}" >&2
        exit 0
        ;;
    429)
        echo "${LOG_TAG} ERROR: HTTP 429 — server backpressure active" >&2
        exit 3
        ;;
    503)
        echo "${LOG_TAG} ERROR: HTTP 503 — server under memory pressure" >&2
        exit 3
        ;;
    4*)
        echo "${LOG_TAG} ERROR: HTTP ${HTTP_CODE} — client error: ${RESPONSE_BODY:0:200}" >&2
        exit 3
        ;;
    5*)
        echo "${LOG_TAG} ERROR: HTTP ${HTTP_CODE} — server error: ${RESPONSE_BODY:0:200}" >&2
        exit 3
        ;;
    *)
        echo "${LOG_TAG} ERROR: unexpected HTTP code ${HTTP_CODE}" >&2
        exit 3
        ;;
esac
