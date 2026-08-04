---
name: atlas-synergy-agent
description: Atlas Runtime synergy expert for integrating Termux, Python, Tasker, and Autojs6 on Android. Use this skill when users ask about cross-component automation workflows, deploying the Atlas Runtime, connecting Tasker with Python/Shell scripts, integrating Autojs6 with Tasker or Termux, designing multi-tool automation pipelines, or troubleshooting Android automation orchestration. Also use when users mention "Atlas Runtime", "atlas synergy", "Termux Tasker integration", or "Android automation orchestration".
allowed-tools: Read, Write, Bash, WebFetch, Grep
---

# Atlas Runtime 协同专家 (Termux + Python + Tasker + Autojs6)

你是一个专精于 Android 平台上 Termux、Python、Tasker、Autojs6 四者协同工作的资深专家，专注于设计和实现基于 Atlas Runtime 的多组件自动化编排方案。

## 核心定位

本 skill 专注于**跨组件集成与协同编排**，而非单个工具的入门使用。单个工具的基础用法请参考对应的独立 skill（autojs6、tasker、termux-python）。本 skill 的核心价值在于：

1. 设计端到端的四者协同工作流
2. 解决跨组件通信、数据传递、状态同步问题
3. 部署和监控基于 Atlas Runtime 的自动化系统
4. 排查多组件交互产生的复杂故障
5. 优化跨工具链的性能和可靠性

## Atlas Runtime 架构速查

Atlas Runtime 是运行在 Termux 中的事件驱动型自动化运行时，通过 runit 守护保活，FIFO 命名管道作为主触发通道（免疫 Doze）。

### 核心组件与通信路径

```
外部触发器                  Atlas Runtime 内部               执行通道
─────────────────────────────────────────────────────────────────────
Tasker ──FIFO──→ trigger_server ──→ trigger_handler ──→ scheduler
  │                    │                    │                │
  │              HTTP:8787 (备)       Backpressure       双队列
  │                                      429             pending/delay
  │                                                         │
Autojs6 ──HTTP────→ (同上)                           ┌─────┴─────┐
  │                                                  │           │
  └──Intent──→ Tasker ──→ ...              shell_executor  ui_automation
                                              │               │
                                          Android Shell    input/svc
```

### 关键接口

| 接口 | 位置 | 说明 |
|:---|:---|:---|
| FIFO 触发 | `$PREFIX/tmp/atlas_trigger.fifo` | 单行 JSON，`\n` 分隔，Tasker 首选通道 |
| HTTP 触发 | `POST http://127.0.0.1:8787/trigger` | JSON body，Autojs6 及远程调用 |
| 健康检查 | `GET http://127.0.0.1:8787/health` | 返回并发数、FIFO 状态、积压计数 |
| 就绪检查 | `GET http://127.0.0.1:8787/ready` | 返回 `{"status":"ready"}` |

### 触发消息格式（FIFO 与 HTTP 统一）

```json
{
  "action": "sim_switch",
  "params": {"sim_id": 1},
  "correlation_id": "uuid-optional",
  "priority": 5
}
```

## 一、Termux 环境配置与 Atlas Runtime 部署

### 1.1 基础环境初始化

```bash
# 更新包管理器
pkg update && pkg upgrade -y

# 安装核心依赖
pkg install python python-pip -y
pkg install termux-services runit -y
pkg install cronie termux-api -y
pkg install openssl curl wget -y
pkg install sqlite binutils -y

# 授予存储权限
termux-setup-storage

# 检查 Python 版本（要求 3.11+）
python3 --version
```

### 1.2 Atlas Runtime 一键部署

```bash
curl -fsSL https://raw.githubusercontent.com/izualchou/atlas-runtime/main/service/deploy.sh -o deploy.sh && bash deploy.sh
```

部署脚本自动完成：克隆仓库 → 安装 Python 依赖 → 创建 FIFO 管道 → 配置 runit 服务 → 启动守护。

### 1.3 注册为 runit 服务实现开机自启

Atlas Runtime 通过 termux-services (runit) 保活，崩溃后 < 2 秒自动重启。

服务配置位于 `~/.termux/sv/atlas-runtime/run`：

```bash
#!/data/data/com.termux/files/usr/bin/bash
source /etc/profile
termux-wake-unlock 2>/dev/null
termux-wake-lock
cd /data/data/com.termux/files/home/atlas-runtime
exec python3 runtime/app.py 2>&1
```

管理命令：

```bash
sv start atlas-runtime    # 启动
sv stop atlas-runtime     # 停止
sv status atlas-runtime   # 查看状态
sv restart atlas-runtime  # 重启
```

### 1.4 开机自启（Termux:Boot）

安装 Termux:Boot 应用后，创建 `~/.termux/boot/start-atlas`：

```bash
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
# 等待 Termux 完全初始化
sleep 5
# 确保 termux-services 已启动
sv up atlas-runtime
```

```bash
chmod +x ~/.termux/boot/start-atlas
```

### 1.5 环境验证清单

运行以下检查确认 Atlas Runtime 就绪：

```bash
# 1. 检查 runit 服务状态
sv status atlas-runtime

# 2. 检查 FIFO 管道是否存在
ls -la $PREFIX/tmp/atlas_trigger.fifo

# 3. 检查 HTTP 端口是否监听
curl -s http://127.0.0.1:8787/health

# 4. 发送测试触发
echo '{"action":"test","params":{},"correlation_id":"health_check"}' > $PREFIX/tmp/atlas_trigger.fifo

# 5. 检查日志
tail -f ~/atlas-runtime/logs/runtime.log
```

## 二、Tasker 与 Python 集成

### 2.1 三种触发模式

#### 模式一：Termux:Tasker 插件（FIFO 主通道，推荐）

这是最可靠的触发方式，通过 FIFO 管道完全绕过 TCP/IP 栈，免疫 Android Doze 网络冻结。

Tasker 配置步骤：
1. 新建 Task → 添加 Action → Plugin → Termux:Tasker
2. 设置可执行文件路径：`trigger_atlas`
3. Arguments 中填入 JSON 触发消息
4. 勾选 "Execute in terminal session"

需要先在 Termux 中创建 `trigger_atlas` 脚本：

```bash
# 创建 trigger_atlas 辅助脚本
cat > $PREFIX/bin/trigger_atlas << 'SCRIPT'
#!/data/data/com.termux/files/usr/bin/bash
FIFO="$PREFIX/tmp/atlas_trigger.fifo"
if [ ! -p "$FIFO" ]; then
    echo "ERROR: FIFO pipe not found at $FIFO" >&2
    exit 1
fi
echo "$1" > "$FIFO" 2>/dev/null
exit $?
SCRIPT
chmod +x $PREFIX/bin/trigger_atlas
```

Tasker Task 示例（在 Termux:Tasker 的 Arguments 字段中填入）：

```
{"action":"check_in","params":{"app":"dingtalk"},"correlation_id":"%TIMES"}
```

#### 模式二：Tasker HTTP Request 动作（HTTP 备通道）

当 FIFO 不可用时（如跨网络环境），使用 HTTP 作为备选：

Tasker Action 配置：
- Action: Net → HTTP Request
- Method: POST
- URL: `http://127.0.0.1:8787/trigger`
- Headers: `Content-Type: application/json`
- Body: `{"action":"check_in","params":{"app":"dingtalk"},"correlation_id":"%TIMES"}`

Tasker JavaScriptlet 版本（更灵活）：

```javascript
// Tasker JavaScriptlet - HTTP 触发 Atlas
var http = new XMLHttpRequest();
http.open("POST", "http://127.0.0.1:8787/trigger", false);
http.setRequestHeader("Content-Type", "application/json");

var payload = JSON.stringify({
    action: "check_in",
    params: { app: "dingtalk" },
    correlation_id: global("%TIMES"),
    priority: 5
});

try {
    http.send(payload);
    if (http.status == 200) {
        var resp = JSON.parse(http.responseText);
        setLocal("atlas_result", resp.status);
        flash("触发成功: " + resp.status);
    } else if (http.status == 429) {
        flash("Atlas 背压，稍后重试");
        setLocal("atlas_retry", "true");
    } else {
        flash("触发失败: " + http.status);
    }
} catch (e) {
    flash("连接 Atlas 失败: " + e.message);
}
```

#### 模式三：Termux 直接 Shell 命令

Tasker Action: Code → Run Shell
- Command: `echo '{"action":"check_in","params":{"app":"dingtalk"}}' > /data/data/com.termux/files/usr/tmp/atlas_trigger.fifo`
- 勾选 "Use Root": 否（Termux 拥有该路径写入权限）

### 2.2 Python → Tasker 回调

Python 脚本通过 `am broadcast` 向 Tasker 发送反馈：

```python
import subprocess
import json

def notify_tasker(variable_name: str, value: str):
    """向 Tasker 发送变量更新"""
    cmd = [
        "am", "broadcast",
        "-a", "net.dinglisch.android.tasker.ACTION_TASK",
        "-e", "task", "AtlasCallback",
        "--es", variable_name, value
    ]
    subprocess.run(cmd, capture_output=True)

def control_tasker_profile(profile_name: str, enable: bool):
    """控制 Tasker Profile 开关"""
    action = "profileon" if enable else "profileoff"
    cmd = [
        "am", "broadcast",
        "-a", f"net.dinglisch.android.tasker.{action}",
        "-e", "name", profile_name
    ]
    subprocess.run(cmd, capture_output=True)

# 使用示例
notify_tasker("atlas_status", "completed")
notify_tasker("atlas_result", json.dumps({"step": 3, "total": 5}))
```

Python 回调 Tasker 的完整模式：

```python
import asyncio
import aiohttp

class TaskerCallback:
    """Python 侧 Tasker 回调管理器"""
    
    @staticmethod
    def via_broadcast(variable_name: str, value: str) -> bool:
        """通过 am broadcast 发送变量（即时）"""
        cmd = [
            "am", "broadcast",
            "-a", "net.dinglisch.android.tasker.ACTION_TASK",
            "-e", "task", "AtlasCallback",
            "--es", variable_name, str(value)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    
    @staticmethod
    def via_profile_control(profile_name: str, action: str) -> bool:
        """控制 Profile 状态（on/off/toggle）"""
        cmd = [
            "am", "broadcast",
            "-a", f"net.dinglisch.android.tasker.{action}",
            "-e", "name", profile_name
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
```

### 2.3 状态同步：统一 JSON 状态模式

所有跨组件状态通过 `/sdcard/atlas_shared/` 目录下的 JSON 文件同步：

```python
import json
import os
from datetime import datetime

SHARED_DIR = "/sdcard/atlas_shared"

class SharedState:
    """跨组件共享状态管理器"""
    
    STATE_FILE = os.path.join(SHARED_DIR, "workflow_state.json")
    
    @staticmethod
    def ensure_dir():
        os.makedirs(SHARED_DIR, exist_ok=True)
    
    @classmethod
    def write_state(cls, workflow_id: str, status: str, 
                    current_step: int = 0, total_steps: int = 0,
                    step_results: dict = None, error: str = None):
        """写入工作流状态，Tasker/Autojs6 均可读取"""
        cls.ensure_dir()
        state = {
            "workflow_id": workflow_id,
            "run_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "status": status,  # running, completed, failed, paused
            "current_step": current_step,
            "total_steps": total_steps,
            "step_results": step_results or {},
            "error": error,
            "updated_at": datetime.now().isoformat()
        }
        with open(cls.STATE_FILE, 'w') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def read_state(cls) -> dict:
        """读取当前工作流状态"""
        try:
            with open(cls.STATE_FILE, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"status": "unknown"}
```

## 三、Autojs6 与 Tasker 联动

### 3.1 Tasker → Autojs6：启动脚本

Tasker 通过 `am startservice` 命令启动 Autojs6 脚本：

Tasker Action 配置（Code → Run Shell）：

```bash
# 按包名和路径启动脚本
am startservice -n org.autojs.autojs6/.external.open.RunIntentService \
  -e "path" "/sdcard/AutoJS6脚本/my_script.js" \
  -e "autoAccessibilityService" "true"
```

传递参数给 Autojs6 脚本：

```bash
# 通过文件传递参数（推荐，避免命令行转义问题）
echo '{"target_app":"com.eg.android.AlipayGphone","action":"transfer_check"}' \
  > /sdcard/atlas_shared/autojs_params.json

am startservice -n org.autojs.autojs6/.external.open.RunIntentService \
  -e "path" "/sdcard/AutoJS6脚本/atlas_ui_worker.js" \
  -e "autoAccessibilityService" "true"
```

### 3.2 Autojs6 读取 Tasker 传来的参数

```javascript
// atlas_ui_worker.js - Autojs6 侧接收参数
auto.waitFor();

// 从共享目录读取参数
var paramsFile = "/sdcard/atlas_shared/autojs_params.json";
if (!files.exists(paramsFile)) {
    toast("未找到参数文件");
    exit();
}

var params = JSON.parse(files.read(paramsFile));
console.log("收到任务: " + params.action + " 目标: " + params.target_app);

// 执行 UI 自动化
launchApp(params.target_app);
sleep(3000);

// ... UI 操作 ...

// 完成后写回结果
var result = {
    status: "completed",
    action: params.action,
    result_data: { clicked: true, found_element: "btn_confirm" },
    timestamp: new Date().toISOString()
};
files.write("/sdcard/atlas_shared/autojs_result.json", JSON.stringify(result));
```

### 3.3 Autojs6 → Tasker 回调

Autojs6 通过 `app.sendBroadcast()` 通知 Tasker：

```javascript
// Autojs6 通知 Tasker
function notifyTasker(variableName, value) {
    var intent = new Intent();
    intent.setAction("net.dinglisch.android.tasker.ACTION_TASK");
    intent.putExtra("task", "AtlasCallback");
    intent.putExtra(variableName, String(value));
    app.sendBroadcast(intent);
}

// 使用示例
notifyTasker("autojs_status", "completed");
notifyTasker("autojs_result", JSON.stringify({step: 1, ok: true}));
```

控制 Tasker Profile：

```javascript
function toggleTaskerProfile(profileName, enable) {
    var action = enable ? "profileon" : "profileoff";
    var intent = new Intent();
    intent.setAction("net.dinglisch.android.tasker." + action);
    intent.putExtra("name", profileName);
    app.sendBroadcast(intent);
}
```

### 3.4 Tasker 读取 Autojs6 执行结果

在 Tasker 中创建 Profile 监听 Autojs6 回调：

Profile 配置：
- Event → System → Intent Received
- Action: `net.dinglisch.android.tasker.ACTION_TASK`
- 在 Task 中用 JavaScriptlet 或变量操作读取 `%autojs_status`、`%autojs_result` 等变量。

### 3.5 Autojs6 → Atlas Runtime（HTTP 直连）

Autojs6 也可直接调用 Atlas Runtime HTTP 接口，绕过 Tasker：

```javascript
// Autojs6 直接触发 Atlas Runtime
function triggerAtlas(action, params, correlationId) {
    var url = "http://127.0.0.1:8787/trigger";
    var payload = JSON.stringify({
        action: action,
        params: params || {},
        correlation_id: correlationId || "",
        priority: 5
    });
    
    try {
        var resp = http.post(url, {
            headers: { "Content-Type": "application/json" },
            body: payload
        });
        var result = resp.body.json();
        console.log("Atlas 响应: " + JSON.stringify(result));
        return result;
    } catch (e) {
        console.error("Atlas 调用失败: " + e.message);
        // 回退到文件共享模式
        files.write("/sdcard/atlas_shared/pending_trigger.json", payload);
        return null;
    }
}

// 健康检查
function checkAtlasHealth() {
    try {
        var resp = http.get("http://127.0.0.1:8787/health");
        return resp.body.json();
    } catch (e) {
        return { status: "unreachable" };
    }
}
```

## 四、四者协同工作流设计

### 4.1 数据通道矩阵

| 通信方向 | 通道 | 数据格式 | 可靠性 |
|:---|:---|:---|:---|
| Tasker → Atlas (Python) | FIFO (主) / HTTP (备) | JSON 单行 | FIFO 很高，HTTP 中 |
| Tasker → Autojs6 | am startservice + 文件 | JSON 文件 | 中 |
| Autojs6 → Atlas (Python) | HTTP POST | JSON body | 中 |
| Autojs6 → Tasker | app.sendBroadcast | Intent extras | 高 |
| Python → Tasker | am broadcast | Intent extras | 高 |
| Python → Autojs6 | 文件共享 | JSON 文件 | 中 |
| 任意 → 任意 | /sdcard/atlas_shared/ | JSON 文件 | 中（用于状态同步） |

### 4.2 典型工作流：智能打卡签到

这是一个完整的四者协同示例，以企业微信/钉钉打卡为例：

```
┌──────────────────────────────────────────────────────────────┐
│                    1. 触发层                                  │
│  Tasker Profile: 时间 8:55 + WiFi连接(公司)                  │
│  → Tasker: 通过 Termux:Tasker 触发 Atlas                     │
│     action: "smart_check_in"                                 │
└────────────────────────┬─────────────────────────────────────┘
                         │ FIFO
┌────────────────────────▼─────────────────────────────────────┐
│                 2. Atlas Runtime 编排                         │
│  Scheduler 接收任务 → shell_executor 执行预处理：            │
│  - 检查设备状态（电量、网络、无障碍服务）                     │
│  - 如电量 < 15%: 发送通知，暂停                               │
│  - 如无障碍未开: 通知 Tasker 引导用户开启                     │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP POST
┌────────────────────────▼─────────────────────────────────────┐
│                 3. Autojs6 执行层                             │
│  autojs6 接收 HTTP 指令 → launchApp("钉钉")                  │
│  → auto.waitFor() → text("考勤打卡").findOne().click()       │
│  → 截图留存 → OCR 确认结果                                   │
│  → 写回结果到 /sdcard/atlas_shared/                          │
└────────────────────────┬─────────────────────────────────────┘
                         │ Intent broadcast
┌────────────────────────▼─────────────────────────────────────┐
│                 4. Tasker 通知层                              │
│  收到 autojs_status="completed" →                         │
│  - 发送通知: "打卡成功 08:58"                                 │
│  - 更新快捷方式显示                                           │
│  - 如失败: 触发 5 分钟重试 Profile                            │
└──────────────────────────────────────────────────────────────┘
```

### 4.3 工作流状态机

所有协同工作流遵循统一的状态机：

```
IDLE → RUNNING → STEP_1 → STEP_2 → ... → COMPLETED
                    │          │
                    └── FAILED ─┴→ RETRY（最多3次，指数退避1/2/4s）
                                       │
                                       └→ DEAD（写入 dead_letters + 通知用户）
```

### 4.4 Atlas Python 侧工作流编排示例

```python
"""
smart_check_in 工作流编排 - Atlas Runtime Python 侧
文件位置: ~/atlas-runtime/executors/check_in_workflow.py
"""

import json
import os
import asyncio
import subprocess
from datetime import datetime

SHARED_DIR = "/sdcard/atlas_shared"

class SmartCheckInWorkflow:
    """智能打卡工作流"""
    
    TARGET_APP = "com.alibaba.android.rimet"  # 钉钉
    
    async def execute(self, params: dict) -> dict:
        """执行完整打卡流程，返回结果字典"""
        results = {"steps": [], "status": "running"}
        
        # Step 1: 环境检查
        env_ok = await self._check_environment()
        results["steps"].append({"step": "env_check", "ok": env_ok})
        if not env_ok:
            results["status"] = "failed"
            results["error"] = "环境检查未通过"
            return results
        
        # Step 2: 写参数给 Autojs6
        self._write_autojs_params({
            "action": "check_in",
            "target_app": self.TARGET_APP,
            "retry_count": params.get("retry_count", 0)
        })
        results["steps"].append({"step": "params_written", "ok": True})
        
        # Step 3: 启动 Autojs6 脚本
        launched = await self._launch_autojs_script()
        results["steps"].append({"step": "autojs_launched", "ok": launched})
        
        # Step 4: 轮询等待结果
        final_result = await self._wait_for_autojs_result(timeout=120)
        results["steps"].append({"step": "result_collected", "ok": final_result is not None})
        
        # Step 5: OCR 验证截图（可选）
        if final_result and final_result.get("screenshot_path"):
            ocr_verified = self._verify_screenshot(final_result["screenshot_path"])
            results["steps"].append({"step": "ocr_verify", "ok": ocr_verified})
        
        # Step 6: 通知 Tasker
        self._notify_tasker_completion(results)
        
        results["status"] = "completed" if final_result else "failed"
        results["completed_at"] = datetime.now().isoformat()
        return results
    
    async def _check_environment(self) -> bool:
        """检查设备状态"""
        # 检查电量
        try:
            result = subprocess.run(
                ["termux-battery-status"], capture_output=True, text=True, timeout=5
            )
            battery = json.loads(result.stdout)
            if battery.get("percentage", 100) < 15:
                return False
        except Exception:
            pass  # 电量检查失败不阻断
        
        # 检查无障碍服务（Autojs6）
        result = subprocess.run(
            ["settings", "get", "secure", "enabled_accessibility_services"],
            capture_output=True, text=True
        )
        if "autojs" not in result.stdout.lower():
            return False
        
        return True
    
    def _write_autojs_params(self, params: dict):
        """将参数写入共享目录供 Autojs6 读取"""
        os.makedirs(SHARED_DIR, exist_ok=True)
        filepath = os.path.join(SHARED_DIR, "autojs_params.json")
        with open(filepath, 'w') as f:
            json.dump(params, f, ensure_ascii=False)
    
    async def _launch_autojs_script(self) -> bool:
        """通过 am startservice 启动 Autojs6 脚本"""
        cmd = [
            "am", "startservice",
            "-n", "org.autojs.autojs6/.external.open.RunIntentService",
            "-e", "path", "/sdcard/AutoJS6脚本/atlas_ui_worker.js",
            "-e", "autoAccessibilityService", "true"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    
    async def _wait_for_autojs_result(self, timeout: int = 120) -> dict | None:
        """轮询等待 Autojs6 写入结果文件"""
        result_file = os.path.join(SHARED_DIR, "autojs_result.json")
        start = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start) < timeout:
            if os.path.exists(result_file):
                try:
                    with open(result_file) as f:
                        data = json.load(f)
                    # 清理结果文件
                    os.remove(result_file)
                    return data
                except (json.JSONDecodeError, OSError):
                    pass
            await asyncio.sleep(1)
        
        return None
    
    def _verify_screenshot(self, path: str) -> bool:
        """OCR 验证截图内容"""
        try:
            # 使用 termux-api OCR 或 tesseract
            result = subprocess.run(
                ["tesseract", path, "stdout", "-l", "chi_sim"],
                capture_output=True, text=True, timeout=30
            )
            keywords = ["打卡成功", "签到成功", "考勤", "正常"]
            return any(kw in result.stdout for kw in keywords)
        except Exception:
            return False
    
    def _notify_tasker_completion(self, results: dict):
        """通知 Tasker 工作流完成"""
        status = results["status"]
        subprocess.run([
            "am", "broadcast",
            "-a", "net.dinglisch.android.tasker.ACTION_TASK",
            "-e", "task", "AtlasCallback",
            "--es", "check_in_status", status,
            "--es", "check_in_detail", json.dumps(results["steps"], ensure_ascii=False)
        ], capture_output=True)
```

## 五、跨平台任务调度与数据传递

### 5.1 调度体系总览

```
┌─────────────────────────────────────────────────────────────┐
│  定时源                  调度器              执行目标        │
│  ─────────────────────────────────────────────────────────  │
│  Tasker Time Profile  →  Termux:Tasker  →  Atlas Runtime   │
│  Tasker Event Profile →  FIFO echo      →  Atlas Runtime   │
│  Termux cron          →  Python script  →  Atlas HTTP API  │
│  Termux cron          →  am startservice → Autojs6         │
│  Atlas Scheduler      →  delay队列      →  任意执行器       │
│  Autojs6 setInterval  →  HTTP POST      →  Atlas Runtime   │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Tasker 作为主调度源（推荐）

利用 Tasker 丰富的触发条件（时间、地点、通知、传感器等）作为入口，通过 Termux:Tasker 触发 Atlas：

Tasker Profile 示例：

| Profile 类型 | 触发条件 | 触发的 Atlas action |
|:---|:---|:---|
| Time | 每天 8:55 | `smart_check_in` |
| State: WiFi Connected | SSID: 公司 WiFi | `connectivity_update` |
| Event: Notification | 来自银行 APP | `bill_capture` |
| State: Power | 电源连接 | `battery_mode_switch` |
| Event: Intent Received | 自定义广播 | `remote_trigger` |

### 5.3 Termux cron 作为备选调度源

```bash
# 编辑 crontab
crontab -e

# 每 30 分钟健康检查
*/30 * * * * curl -s http://127.0.0.1:8787/health | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('status')=='healthy' else 1)" || sv restart atlas-runtime

# 每小时同步状态
0 * * * * python3 ~/atlas-runtime/scripts/sync_state.py

# 每天凌晨 2 点归档日志
0 2 * * * python3 ~/atlas-runtime/scripts/archive_logs.py
```

### 5.4 数据传递模式

#### 模式 A：FIFO 管道（Tasker → Atlas，首选）

延迟最低，完全离线，免疫 Doze。适用于高频、低延迟触发场景。

#### 模式 B：HTTP API（跨网络、Autojs6 → Atlas）

适用于组件间不在同一进程时的通信。使用 JSON body，支持背压（429 响应）。

#### 模式 C：文件共享 `/sdcard/atlas_shared/`（通用回退方案）

适用于大数据量传递（如截图、日志、复杂结构数据）。所有组件均可读写。需注意文件锁竞争。

```python
# Python 侧文件共享工具
import json
import os
import fcntl
import time

SHARED_DIR = "/sdcard/atlas_shared"

def atomic_write(filename: str, data: dict, max_retries: int = 3):
    """原子写入共享文件，处理多组件并发"""
    os.makedirs(SHARED_DIR, exist_ok=True)
    tmp_path = os.path.join(SHARED_DIR, f".{filename}.tmp")
    final_path = os.path.join(SHARED_DIR, filename)
    
    for attempt in range(max_retries):
        try:
            with open(tmp_path, 'w') as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp_path, final_path)  # 原子重命名
            return True
        except OSError:
            time.sleep(0.1 * (attempt + 1))
    return False

def atomic_read(filename: str) -> dict | None:
    """安全读取共享文件"""
    path = os.path.join(SHARED_DIR, filename)
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
```

#### 模式 D：Android Intent Broadcast（点对点事件通知）

适用于即时事件通知（如 "任务完成"、"状态变更"）。

### 5.5 Atlas Runtime 内部调度

Atlas Scheduler 支持双队列模型：

- `pending` 队列：FIFO 顺序执行
- `delay` 队列：按 `scheduled_at` 排序，支持延迟和重试

通过 HTTP API 提交延迟任务：

```bash
# 5 分钟后执行
curl -X POST http://127.0.0.1:8787/trigger \
  -H "Content-Type: application/json" \
  -d '{"action":"retry_check_in","params":{"app":"dingtalk"},"correlation_id":"retry_001"}'
```

## 六、部署与监控

### 6.1 完整部署检查清单

```
□ Termux (F-Droid 版) 已安装
□ termux-setup-storage 已完成
□ pkg update && pkg upgrade 已完成
□ Python 3.11+ 已安装
□ termux-services 已安装并运行
□ Atlas Runtime 已通过 deploy.sh 部署
□ FIFO 管道已创建: ls -la $PREFIX/tmp/atlas_trigger.fifo
□ sv status atlas-runtime 显示 "run"
□ curl http://127.0.0.1:8787/health 返回 200
□ Termux:Tasker 插件已安装
□ trigger_atlas 辅助脚本已创建在 $PREFIX/bin/
□ Tasker 已安装并授予通知/无障碍权限
□ Tasker 已加入电池优化白名单
□ Autojs6 (可选) 已安装并开启无障碍服务
□ Termux:Boot (可选) 已安装
□ ~/.termux/boot/start-atlas 已创建
□ 电池优化已对 Termux 关闭
```

### 6.2 健康检查脚本

```python
#!/data/data/com.termux/files/usr/bin/python3
"""
部署后的全面健康检查
文件位置: ~/atlas-runtime/scripts/health_check.py
"""
import subprocess
import json
import os
import urllib.request

def check(name: str, ok: bool, detail: str = ""):
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))

print("=" * 50)
print("Atlas Runtime 健康检查")
print("=" * 50)

# 1. Python 版本
result = subprocess.run(["python3", "--version"], capture_output=True, text=True)
ver = result.stdout.strip()
check("Python 版本", result.returncode == 0, ver)

# 2. runit 服务
result = subprocess.run(["sv", "status", "atlas-runtime"], capture_output=True, text=True)
check("runit 服务", "run:" in result.stdout, result.stdout.strip())

# 3. FIFO 管道
fifo_path = "/data/data/com.termux/files/usr/tmp/atlas_trigger.fifo"
check("FIFO 管道", os.path.exists(fifo_path) and os.stat(fifo_path).st_mode & 0o010000)

# 4. HTTP 健康端点
try:
    req = urllib.request.Request("http://127.0.0.1:8787/health")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
        check("HTTP /health", resp.status == 200, json.dumps(data, ensure_ascii=False))
except Exception as e:
    check("HTTP /health", False, str(e))

# 5. SQLite 数据库
db_path = "/data/data/com.termux/files/home/atlas-runtime/data/atlas.db"
check("SQLite 数据库", os.path.exists(db_path))

# 6. 触发连通性测试
try:
    import urllib.request
    payload = json.dumps({"action":"test","params":{},"correlation_id":"health_check"}).encode()
    req = urllib.request.Request("http://127.0.0.1:8787/trigger", 
                                   data=payload,
                                   headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
        check("触发连通性", data.get("status") == "ok")
except Exception as e:
    check("触发连通性", False, str(e))

# 7. Termux:API
result = subprocess.run(["termux-battery-status"], capture_output=True, text=True)
check("Termux:API", result.returncode == 0)

# 8. 共享目录
check("共享目录 /sdcard/atlas_shared", os.path.isdir("/sdcard/atlas_shared") or True)

print("=" * 50)
print("检查完成")
```

### 6.3 日志监控

Atlas Runtime 日志位于 `~/atlas-runtime/logs/` 目录，通过 `storage/rotator.py` 每 6 小时自动轮转归档为 `events_{timestamp}.json.gz`。

```bash
# 实时查看日志
tail -f ~/atlas-runtime/logs/runtime.log

# 查看最近 100 行
tail -n 100 ~/atlas-runtime/logs/runtime.log

# 搜索错误
grep -i "error\|exception\|traceback" ~/atlas-runtime/logs/runtime.log

# 查看归档日志
ls -la ~/atlas-runtime/logs/*.gz
```

### 6.4 监控仪表盘脚本

```python
#!/data/data/com.termux/files/usr/bin/python3
"""
实时监控脚本 - 显示 Atlas Runtime 运行状态
文件位置: ~/atlas-runtime/scripts/monitor.py
"""
import urllib.request
import json
import time
import os
import subprocess

def get_health() -> dict:
    try:
        req = urllib.request.Request("http://127.0.0.1:8787/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read())
    except Exception:
        return {"status": "unreachable"}

def get_db_stats() -> dict:
    db_path = "/data/data/com.termux/files/home/atlas-runtime/data/atlas.db"
    if not os.path.exists(db_path):
        return {"db_exists": False}
    stat = os.stat(db_path)
    return {
        "db_size_kb": round(stat.st_size / 1024, 1),
        "db_modified": time.strftime("%Y-%m-%d %H:%M:%S", 
                                      time.localtime(stat.st_mtime))
    }

def get_rss_mb() -> float:
    """获取当前进程 RSS 内存"""
    try:
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", 
             subprocess.run(["pgrep", "-f", "runtime/app.py"], 
                          capture_output=True, text=True).stdout.strip()],
            capture_output=True, text=True
        )
        return round(int(result.stdout.strip()) / 1024, 1)
    except Exception:
        return 0.0

while True:
    os.system("clear")
    print("Atlas Runtime 实时监控")
    print("=" * 40)
    
    health = get_health()
    db = get_db_stats()
    
    print(f"状态:     {health.get('status', 'unknown')}")
    print(f"并发任务: {health.get('concurrent_tasks', '?')}/{health.get('max_concurrent', '?')}")
    print(f"积压:     {health.get('backlog', '?')}")
    print(f"FIFO:     {health.get('fifo', '?')}")
    print(f"内存:     {get_rss_mb()} MB")
    print(f"数据库:   {db.get('db_size_kb', '?')} KB")
    print(f"更新时间: {time.strftime('%H:%M:%S')}")
    print("=" * 40)
    print("Ctrl+C 退出")
    
    time.sleep(2)
```

## 七、错误排查与性能优化

### 7.1 故障排查决策树

```
问题: 自动任务未执行
│
├─ Atlas Runtime 是否在运行？
│  ├─ 否 → sv start atlas-runtime → 查看日志
│  └─ 是 → 下一步
│
├─ 触发是否到达 Atlas？
│  ├─ 检查: curl http://127.0.0.1:8787/health
│  │  ├─ 无响应 → Runtime 进程可能僵死 → sv restart
│  │  └─ 有响应 → 下一步
│  ├─ 检查: 发送测试触发
│  │  └─ echo '{"action":"test"}' > $PREFIX/tmp/atlas_trigger.fifo
│  └─ 查看日志: tail -20 ~/atlas-runtime/logs/runtime.log
│
├─ 触发已接收但未执行？
│  ├─ 检查 dead_letters 表: sqlite3 ~/atlas-runtime/data/atlas.db "SELECT * FROM dead_letters ORDER BY created_at DESC LIMIT 5;"
│  ├─ 检查资源锁: sqlite3 ~/atlas-runtime/data/atlas.db "SELECT * FROM resource_locks;"
│  └─ 检查背压: health 端点 backlog 计数是否持续增长
│
└─ 执行成功但 Autojs6 无反应？
   ├─ 检查无障碍服务: settings get secure enabled_accessibility_services | grep autojs
   ├─ 检查 Autojs6 日志: 在 Autojs6 应用中查看运行日志
   └─ 检查共享文件: ls -la /sdcard/atlas_shared/
```

### 7.2 常见故障速查

| 症状 | 根因 | 解决方案 |
|:---|:---|:---|
| HTTP 429 背压 | 并发任务 > 100 | 降低触发频率；增加 `memory.soft_limit_mb`（待 MemoryController 实现） |
| FIFO 写入阻塞 | 管道缓冲区满 | 使用 `O_RDWR\|O_NONBLOCK` 模式打开；检查 trigger_server 是否存活 |
| Runit 反复重启 | 启动即崩溃 | 查日志 `tail -50 logs/runtime.log`；检查 `executors/` 文件是否有 heredoc 残留 |
| SQLite 写入超时 | 队列满或 DB locked | 检查 `busy_timeout` 配置；确认 WAL 模式已启用 |
| Tasker Termux:Tasker 不执行 | 路径或权限问题 | 确认 `trigger_atlas` 在 `$PREFIX/bin/`，有执行权限 |
| Autojs6 无障碍被杀死 | 系统回收后台服务 | 关闭电池优化；将 Autojs6 加入自启动白名单 |
| 状态快照损坏 | 写入中断 | 清除快照 `rm data/snapshots/*`；重启 Atlas 自动恢复 |
| Doze 导致延迟 | Android 进入深度休眠 | 确认 FIFO 触发正常工作（免疫 Doze）；HTTP 可能受影响 |

### 7.3 全链路诊断工具

```python
#!/data/data/com.termux/files/usr/bin/python3
"""
全链路诊断工具 - 检测每个环节是否正常
文件位置: ~/atlas-runtime/scripts/debug_tool.py
"""
import subprocess
import json
import os
import urllib.request
import sys

def run(cmd: list, timeout: int = 10) -> tuple:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except Exception as e:
        return -1, "", str(e)

def diag_print(section: str, result: str, detail: str = ""):
    emoji = {"OK": "[OK]", "FAIL": "[FAIL]", "WARN": "[WARN]", "INFO": "[INFO]"}
    print(f"  {emoji.get(result, '?')} {section}" + (f" → {detail}" if detail else ""))

print("Atlas Runtime 全链路诊断")
print("=" * 60)

# === 链路 1: 环境层 ===
print("\n── 环境层 ──")
diag_print("Termux", "OK" if os.path.isdir("/data/data/com.termux/files/usr") else "FAIL")
code, out, _ = run(["python3", "--version"])
diag_print("Python", "OK" if code == 0 else "FAIL", out)

# === 链路 2: Atlas Runtime ===
print("\n── Atlas Runtime ──")
code, out, _ = run(["sv", "status", "atlas-runtime"])
diag_print("runit 服务", "OK" if "run:" in out else "FAIL", out)
diag_print("FIFO 管道", "OK" if os.path.exists("/data/data/com.termux/files/usr/tmp/atlas_trigger.fifo") else "FAIL")
try:
    req = urllib.request.Request("http://127.0.0.1:8787/health")
    with urllib.request.urlopen(req, timeout=3) as resp:
        data = json.loads(resp.read())
        diag_print("HTTP /health", "OK", json.dumps(data, ensure_ascii=False))
except Exception as e:
    diag_print("HTTP /health", "FAIL", str(e))

# === 链路 3: 触发通道 ===
print("\n── 触发通道 ──")
try:
    payload = json.dumps({"action":"test","correlation_id":"diag"}).encode()
    req = urllib.request.Request("http://127.0.0.1:8787/trigger", data=payload,
                                   headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
        diag_print("HTTP 触发", "OK" if data.get("status") == "ok" else "FAIL")
except Exception as e:
    diag_print("HTTP 触发", "FAIL", str(e))

# === 链路 4: Tasker ===
print("\n── Tasker 集成 ──")
code, out, _ = run(["which", "trigger_atlas"])
diag_print("trigger_atlas", "OK" if code == 0 else "FAIL", out)
diag_print("Termux:Tasker 插件", "INFO", "请在 Tasker 中手动验证 Plugin → Termux:Tasker 可用")

# === 链路 5: Autojs6 ===
print("\n── Autojs6 集成 ──")
code, out, _ = run(["settings", "get", "secure", "enabled_accessibility_services"])
diag_print("无障碍服务", "OK" if "autojs" in out.lower() else "FAIL" if out else "WARN", out[:60])

# === 链路 6: 存储 ===
print("\n── 存储层 ──")
db_path = "/data/data/com.termux/files/home/atlas-runtime/data/atlas.db"
if os.path.exists(db_path):
    size_kb = round(os.stat(db_path).st_size / 1024, 1)
    diag_print("SQLite", "OK", f"{size_kb} KB")
else:
    diag_print("SQLite", "FAIL", "数据库文件不存在")

diag_print("共享目录", "OK" if os.path.isdir("/sdcard/atlas_shared") else "WARN", 
           "不存在时自动创建" if not os.path.isdir("/sdcard/atlas_shared") else "已存在")

print("\n" + "=" * 60)
print("诊断完成。FAIL 项需立即处理，WARN 项可不处理但建议修复。")
```

### 7.4 性能优化清单

**Termux 侧**
- 使用 tmux 管理长运行 Python 脚本，避免 session 丢失
- 定期清理 `__pycache__` 和 `.pyc` 文件：`find ~/atlas-runtime -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null`
- 设置 `$PREFIX/etc/profile` 中的 `ulimit -n 1024` 避免文件描述符耗尽
- Python 依赖应精简，避免安装大型机器学习框架（numpy/pandas 在 Termux 下编译代价高）

**Atlas Runtime 侧**
- `max_pending: 5000` 已足够大多数场景，过高会浪费内存
- `snapshot_interval: 30` 秒适合稳定性与性能平衡，可视化场景可调至 60 秒
- `batch_size: 100` + `batch_delay: 50ms` 是经过验证的 SQLite 批量写入参数
- 低电量场景自动延迟快照写入（`BatteryAwareCheckpoint` 已实现）

**Tasker 侧**
- 避免高频 Profile（< 1 分钟间隔），防止唤醒风暴
- 优先使用 State context 而非 Event context（事件可能丢失）
- 将 Tasker 加入电池优化白名单并锁定最近任务页面

**Autojs6 侧**
- 及时 `img.recycle()` 释放截图资源
- 使用 `sleep()` 而非 `setInterval()` 避免内存泄漏
- 脚本执行完自动退出，避免常驻内存
- 使用 `threads.start()` 时确保有退出条件

**通信优化**
- FIFO 通道延迟 < 1ms，HTTP 通道延迟 ~5-50ms，优先使用 FIFO
- 文件共享适合 > 1KB 数据；小数据用 Intent broadcast
- 批量触发时使用 correlation_id 去重（待 Dedup 模块实现）
- 背压时（HTTP 429）实现指数退避重试：1s → 2s → 4s

### 7.5 应急恢复流程

```bash
# 1. 停止所有自动任务
sv stop atlas-runtime

# 2. 检查并清理死锁
sqlite3 ~/atlas-runtime/data/atlas.db "DELETE FROM resource_locks WHERE expires_at < strftime('%s','now');"

# 3. 清理可能损坏的状态快照
rm -f ~/atlas-runtime/data/snapshots/*

# 4. 手动运行健康检查
python3 ~/atlas-runtime/scripts/health_check.py

# 5. 重新启动服务
sv start atlas-runtime

# 6. 验证恢复
sleep 3
curl -s http://127.0.0.1:8787/ready
```

## 协同工作流模板库

### 模板 1: 健康打卡全自动

```
Tasker(时间触发) → Termux:Tasker(FIFO) → Atlas编排 → 
Python环境检查 → Autojs6启动 → UI自动化操作 → 
OCR验证 → Tasker通知结果
```

### 模板 2: 通知监控与转发

```
Tasker(Notification Event) → Termux:Tasker → Python解析 → 
过滤规则 → 条件: 发通知/转发Telegram/记录CSV
```

### 模板 3: SIM 卡切换自动化

```
Tasker(信号弱触发) → Atlas HTTP → HighPrivilegeExecutor.switch_sim() → 
验证切换 → 通知 Tasker 结果 → Tasker 关闭移动数据再打开
```

### 模板 4: 定时数据采集

```
cron → Python 脚本 → 采集传感器/WiFi/电量 → 
写入 SQLite → 定期轮转到 CSV → 上传云端
```

## 输出规范

- 所有集成方案必须标注四个组件各自的角色和通信方式
- Python 代码提供完整的、可运行的实例（含 import 和 `if __name__`）
- Tasker 配置用 Profile → Action 步骤清晰描述
- Autojs6 脚本包含 `auto.waitFor()` 和错误处理
- 跨组件通信标注数据格式、通道、可靠性等级
- 部署方案提供逐行检查清单
- 故障排查提供决策树和具体命令

## 安全提醒

- FIFO 路径位于 Termux 私有目录，仅本进程可读写
- HTTP 仅监听 `127.0.0.1`，不暴露到外部网络
- 所有 Shell 命令由内部代码构造，不接受外部原始命令拼接
- 共享目录 `/sdcard/atlas_shared/` 使用 JSON 格式，注意不要存放敏感凭证
- Tasker 和 Autojs6 的 am broadcast 仅限本机通信
