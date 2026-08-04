# Atlas Runtime v8.0 LTS — 后续任务实施方案

> 版本：v1.0
> 日期：2026-08-05
> 基准文档：DESIGN_SPEC_v8.0.md §9、PROGRESS_REPORT.md
> 适用周期：2026-08 至 2026-09（约 5 周）

---

## 一、项目背景

Atlas Runtime v8.0 LTS 是一个运行在 Android 系统上、基于 Termux + Python 的事件驱动型自动化运行时。它通过 FIFO 命名管道 + HTTP 双模触发器接收外部指令，调度 Shell/UI/高权限执行器完成 Android 设备自动化操作。

截至 2026-08-05，核心引擎 14/14 模块已实现并通过 mock 级测试（5,275 行源代码，1,945 行测试），9 项设计缺陷全部修复验证通过。核心引擎完成度约 95%。

当前项目处于从"引擎就绪"到"端到端可用"的关键跨越阶段。剩余工作集中在两个方向：（1）设计规范 §9 中标记的三个设计超前模块（MemoryController、CircuitBreaker、Dedup），（2）Tasker 和 Auto.js6 的外部集成链路。以下为本方案的完整背景补充：

**已完成资产**：
- 微内核层（core/）：Bootstrap 启动编排、Scheduler 双队列调度器、StateManager 状态管理、ResourceLock CAS 乐观锁、TriggerHandler 背压+死信、HealthChecker 健康检查、Platform 环境检测
- 通信层（transport/）：FIFO 主通道（O_RDWR|O_NONBLOCK）+ HTTP 备通道（aiohttp），Semaphore 限流，64KB 缓冲背压保护
- 存储层（storage/）：单写者 SQLite（WAL 模式）、原子快照（SHA256 校验）、轮转归档、电池感知 Checkpoint
- 执行器层（executors/）：SafeShellExecutor（进程组隔离）、UIAutomationExecutor（input tap/swipe/keyevent）、HighPrivilegeExecutor（SIM/WiFi/音量三级回退）
- 配置与部署：runtime.yaml 完整配置、deploy.sh 一键部署、update.sh 滚动更新
- 测试资产：15 个测试文件覆盖全部 14 个核心模块

**技术约束**：
- 纯 Python 实现，零 C 扩展依赖（Android 编译兼容性约束）
- Python 3.11+（实际部署 3.14.6）
- 单实例单进程单写者模型
- FIFO 管道位于 Termux 私有目录，HTTP 仅监听 127.0.0.1
- psutil 需通过 pkg install python-psutil 预编译安装

---

## 二、现有任务清单及状态

以下为 PROGRESS_REPORT.md 中识别的全部待完成项，以及本方案新增的细化子任务：

| 编号 | 任务名称 | 来源 | 优先级 | 状态 |
|:---|:---|:---|:---|:---|
| T1 | MemoryController 实现 | DESIGN_SPEC §9 | P1 | ❌ 待开始 |
| T2 | CircuitBreaker 实现 | DESIGN_SPEC §9 | P2 | ❌ 待开始 |
| T3 | Dedup 去重实现 | DESIGN_SPEC §9 | P2 | ❌ 待开始 |
| T4 | Tasker 集成 — FIFO 触发链路 | DESIGN_SPEC §9 | P0 | ❌ 待开始 |
| T4a | Tasker Profile 配置（时间/事件触发） | 子任务 | P0 | ❌ 待开始 |
| T4b | Tasker Task 配置（Termux:Tasker → FIFO） | 子任务 | P0 | ❌ 待开始 |
| T4c | Tasker 结果接收（Intent/Notification） | 子任务 | P0 | ❌ 待开始 |
| T5 | AutoJS6 集成 — UI 执行器链路 | DESIGN_SPEC §9 | P0 | ❌ 待开始 |
| T5a | AutoJS6 无障碍服务脚本模板 | 子任务 | P0 | ❌ 待开始 |
| T5b | AutoJS6 → Atlas HTTP 回调客户端 | 子任务 | P0 | ❌ 待开始 |
| T5c | Atlas → AutoJS6 Intent 启动机制 | 子任务 | P0 | ❌ 待开始 |
| T6 | 真实设备端到端测试 | DESIGN_SPEC §9 | P0 | ❌ 待开始 |
| T6a | SIM 切换端到端验证 | 子任务 | P0 | ❌ 待开始 |
| T6b | UI 自动化端到端验证 | 子任务 | P0 | ❌ 待开始 |
| T6c | 崩溃重启恢复验证 | 子任务 | P0 | ❌ 待开始 |
| T6d | 快照冷恢复验证 | 子任务 | P0 | ❌ 待开始 |
| T7 | Tasker 配置导入文档 | PROGRESS_REPORT | P3 | ❌ 待开始 |
| T8 | AutoJS6 脚本模板与文档 | PROGRESS_REPORT | P3 | ❌ 待开始 |

---

## 三、优先级评估标准

本方案采用多维度综合评估模型，每项任务的最终优先级由以下五个维度加权得出：

### 3.1 业务价值（权重 35%）

评估该任务对"端到端可用的自动化运行时"这一核心目标的贡献度。评分标准：

- 5 分（关键）：缺失则系统无法完成核心用例（如 Tasker 集成——缺失则无外部触发能力）
- 4 分（重要）：缺失则系统严重受限，多数用例无法完整闭环
- 3 分（有价值）：显著提升系统质量或用户体验
- 2 分（增益）：锦上添花，边际改进
- 1 分（可延后）：对未来有价值但不影响当前可用性

### 3.2 技术复杂度（权重 25%）

- 1 分（极低）：配置文件编写或文档撰写，无需编码
- 2 分（低）：简单模块实现，API 清晰，依赖少
- 3 分（中等）：涉及多模块协作或外部系统交互
- 4 分（高）：需要深入理解 Android 系统机制或 Termux 限制
- 5 分（极高）：跨平台兼容、多设备适配、需要逆向工程

### 3.3 依赖阻塞性（权重 20%）

评估该任务是否阻塞其他高优先级任务。评分标准：

- 5 分（强阻塞）：多项 P0 任务依赖此项
- 3 分（弱阻塞）：至少一项 P0/P1 任务依赖此项
- 1 分（无阻塞）：不阻塞任何其他任务

### 3.4 风险可控性（权重 10%）

评估任务的不确定性。评分标准为逆向指标（高风险得分低，低风险得分高）：

- 5 分（极低风险）：成熟技术，无未知变量
- 3 分（中等风险）：有已知挑战但可预判
- 1 分（高风险）：依赖外部系统行为、设备差异等不确定因素

### 3.5 实施成本（权重 10%）

人天估算。评分标准为逆向指标（高成本得分低，低成本得分高）：

- 5 分（极低成本）：≤ 1 人天
- 3 分（中等成本）：3-5 人天
- 1 分（高成本）：≥ 8 人天

### 3.6 综合评分结果

| 任务 | 业务价值 (35%) | 技术复杂度 (25%) | 依赖阻塞 (20%) | 风险可控 (10%) | 实施成本 (10%) | 加权总分 | 最终优先级 |
|:---|:---|:---|:---|:---|:---|:---|:---|
| T4 Tasker 集成 | 5 | 3 | 5 | 3 | 3 | 3.95 | **P0** |
| T5 AutoJS6 集成 | 5 | 4 | 3 | 2 | 1 | 3.45 | **P0** |
| T6 真机 E2E 测试 | 4 | 4 | 1 | 1 | 1 | 2.65 | **P0** |
| T1 MemoryController | 3 | 2 | 3 | 4 | 3 | 2.80 | **P1** |
| T2 CircuitBreaker | 3 | 2 | 1 | 4 | 4 | 2.65 | **P2** |
| T3 Dedup 去重 | 2 | 2 | 1 | 4 | 4 | 2.30 | **P2** |
| T7 Tasker 文档 | 2 | 1 | 1 | 5 | 5 | 2.30 | **P3** |
| T8 AutoJS6 文档 | 2 | 1 | 1 | 5 | 5 | 2.30 | **P3** |

**最终优先级排序**：T4 (Tasker) > T5 (AutoJS6) > T1 (MemoryController) > T6 (E2E) > T2 (CircuitBreaker) > T3 (Dedup) > T7/T8 (文档)

---

## 四、依赖关系图

所有待实现任务的依赖关系如下：

```
                    ┌─────────────────────┐
                    │  T1 MemoryController │  ← 独立，依赖 psutil 可用
                    └──────────┬──────────┘
                               │ (弱依赖：T6 中验证内存保护)
                               ▼
┌─────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│ T4 Tasker 集成   │◄───│  Atlas Runtime 核心  │───►│ T5 AutoJS6 集成     │
│ (FIFO 触发链路)  │    │  (已完成，v8.0 LTS)  │    │ (HTTP 回调链路)     │
└────────┬────────┘    └─────────────────────┘    └────────┬────────┘
         │                                                 │
         │            ┌─────────────────────┐              │
         └───────────►│  T6 真机 E2E 测试    │◄─────────────┘
                      └──────────┬──────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │ T7 Tasker │ │ T8 AutoJS6│ │T2 Circuit│
              │   文档    │ │   文档    │ │  Breaker │
              └──────────┘ └──────────┘ └──────────┘
                                              │
                                              ▼
                                        ┌──────────┐
                                        │ T3 Dedup │
                                        └──────────┘
```

**关键依赖说明**：

- T1 MemoryController 是独立模块，不依赖任何其他待实现任务。它实现后可为 T6 E2E 测试提供内存压力场景。
- T2 CircuitBreaker 和 T3 Dedup 也是独立模块，但建议在核心引擎经过真实设备验证（T6）之后再实现，以避免在未经验证的基础上叠加复杂度。
- T4 和 T5 互不依赖，可并行推进。但两者共享对 T6 的依赖方向——T6 必须在 T4 和 T5 均完成后才能全面开展。
- T7 和 T8 是纯文档任务，依赖对应集成任务（T4→T7，T5→T8）的内容稳定后编写。

---

## 五、任务排序与里程碑节点

采用 **Now / Next / Later** 三阶段路线图：

### 5.1 第一阶段：生产加固（Now — 第 1-2 周）

**里程碑 M1：MemoryController 上线**（2026-08-19）

目标：将核心引擎从"功能完备"提升至"生产可靠"，在引入外部触发器之前先加固内存安全。

#### T1：MemoryController 实现（P1，3 人天）

**目标**：对 Python 进程 RSS 内存进行实时监控，支持软限（暂停接单）和硬限（强制 GC + 拒绝写入）两级保护。

**实现方案**：

```
模块位置：core/memory_controller.py
依赖：psutil（Termux: pkg install python-psutil）
配置：config/runtime.yaml → memory.soft_limit_mb (150) / hard_limit_mb (200)

核心接口：
class MemoryController:
    def __init__(self, soft_limit_mb: int, hard_limit_mb: int, check_interval: float = 5.0)
    async def start() -> None                              # 后台定时检查
    async def stop() -> None
    async def get_memory_info() -> Dict[str, Any]          # RSS/VMS/百分比
    async def check_and_act() -> str                       # 返回 NORMAL/SOFT_LIMITED/HARD_LIMITED
    def is_accepting() -> bool                             # 当前是否接受新任务
    def set_backpressure_callback(cb: Callable) -> None    # 硬限时触发背压
```

**与现有组件交互**：
- 启动时注册到 Bootstrap.components，加入优雅关闭链
- 硬限触发时回调 transport/trigger_server 设置背压标志（复用现有 Semaphore 机制）
- 健康检查端点 /health 新增 memory 字段（通过 HealthChecker 汇报）
- 写入 storage 记录内存事件（复用 events 表，type='memory_pressure'）

**交付物**：
- `core/memory_controller.py`：完整实现
- `tests/test_memory_controller.py`：单元测试（mock psutil）
- `config/runtime.yaml`：激活 memory 配置段（去除注释标记）
- `core/bootstrap.py`：追加 MemoryController 实例化与启动

**风险与应对**：

| 风险 | 概率 | 影响 | 应对措施 |
|:---|:---|:---|:---|
| Termux 中 psutil 不可用 | 中 | 高（模块无法工作） | 实现优雅降级：检测 ImportError 时跳过 MemoryController，记录 WARNING，其余组件正常运行 |
| psutil.Process().memory_info().rss 在 Android 上不准确 | 低 | 中 | 同时采集 /proc/self/status VmRSS 作为交叉验证数据源 |
| 硬限触发后长时间无法恢复 | 中 | 中 | 硬限状态持续 60 秒后强制 reset（防止死锁式拒绝服务） |

---

### 5.2 第二阶段：外部集成（Next — 第 2-4 周）

**里程碑 M2：端到端触发链路贯通**（2026-09-04）

目标：打通 Tasker → Atlas 和 Atlas → AutoJS6 两条关键外部链路，使系统能完成首个真实自动化用例。

#### T4：Tasker 集成 — FIFO 触发链路（P0，5 人天）

**目标**：使 Tasker 能通过 Termux:Tasker 插件向 Atlas Runtime 的 FIFO 管道发送触发消息，并接收执行结果。

**实现方案**：

集成架构：

```
Tasker Profile (时间/事件/状态)
    │
    ▼
Tasker Task
    │ Action 1: Termux:Tasker → trigger_atlas '{"action":"...","params":{...}}'
    │   └─ 内部执行: echo '...' > $PREFIX/tmp/atlas_trigger.fifo
    │
    ▼ (Tasker 等待 5 秒)
    │ Action 2: Tasker → Read File (/sdcard/atlas_shared/last_result.json)
    │ Action 3: If %result ~ success → Notify "操作成功"
    │ Action 4: Else → Notify "操作失败: %errmsg"
```

**子任务拆分**：

**T4a — Tasker Profile 配置**（1 人天）

创建三类标准 Profile 模板：
- 时间触发型（如每天 08:55）：Time Profile → 指定时刻
- 事件触发型（如收到特定通知）：Event → Notification Listener
- 状态触发型（如电量低于 20%）：State → Power → Battery Level

**T4b — Tasker Task 配置**（2 人天）

核心 Task 模板（精确到每个 Action）：

| Action | 类型 | 参数 |
|:---|:---|:---|
| A1 | Plugin → Termux:Tasker | Executable: `$HOME/atlas-runtime/runtime/trigger_atlas.sh`, Args: `{"action":"sim_switch","params":{"sim_id":1},"correlation_id":"%TIMES"}` |
| A2 | Task → Wait | Seconds: 5 |
| A3 | Code → JavaScriptlet | 读取 `/sdcard/atlas_shared/last_result.json`，解析 status 字段 |
| A4 | Task → If | Condition: `%atlas_status ~ success` |
| A5 | Alert → Notify | Title: "Atlas 操作成功", Text: "%atlas_result" |
| A6 | Task → Else | — |
| A7 | Alert → Notify | Title: "Atlas 操作失败", Text: "%atlas_error" |
| A8 | Task → End If | — |

需新建的辅助脚本：

```
runtime/trigger_atlas.sh:
#!/data/data/com.termux/files/usr/bin/bash
# Tasker → FIFO 写入脚本
# 由 Termux:Tasker 调用，接收 JSON 参数
FIFO_PATH="$PREFIX/tmp/atlas_trigger.fifo"
if [ -p "$FIFO_PATH" ]; then
    echo "$1" > "$FIFO_PATH"
else
    # FIFO 不存在时的 HTTP 备通道回退
    curl -s -X POST http://127.0.0.1:8787/trigger \
        -H "Content-Type: application/json" \
        -d "$1"
fi
```

**T4c — Tasker 结果接收**（2 人天）

设计结果回传机制。Atlas Runtime 侧需新增：

```
transport/result_callback.py:
class ResultCallback:
    """任务完成后将结果写入共享文件供 Tasker 读取"""
    def __init__(self, result_dir: str = "/sdcard/atlas_shared")
    async def write_result(self, correlation_id: str, result: Dict) -> None
    # 使用原子写入：临时文件 → os.replace()
```

此模块在 Scheduler 的 on_task_complete 回调中触发，将结果写入 `/sdcard/atlas_shared/last_result.json` 和 `/sdcard/atlas_shared/results/{correlation_id}.json`。

**交付物**：

| 交付物 | 格式 | 说明 |
|:---|:---|:---|
| `runtime/trigger_atlas.sh` | Shell 脚本 | Termux:Tasker 可执行入口 |
| `transport/result_callback.py` | Python 模块 | 结果回写 Tasker 共享目录 |
| `config/tasker/atlas_trigger.prj.xml` | XML | 可直接导入的 Tasker 完整配置 |
| `config/tasker/profile_time.xml` | XML | 时间触发 Profile 模板 |
| `config/tasker/profile_event.xml` | XML | 事件触发 Profile 模板 |
| `config/tasker/task_sim_switch.tsk.xml` | XML | SIM 切换完整 Task 示例 |

**风险与应对**：

| 风险 | 概率 | 影响 | 应对措施 |
|:---|:---|:---|:---|
| Termux:Tasker 插件版本不兼容 | 中 | 高（完全阻断） | 文档中明确要求插件版本 ≥ 0.5，提供 HTTP 备通道回退方案（T4b trigger_atlas.sh 已内置） |
| /sdcard/atlas_shared 目录权限问题 | 中 | 中 | 部署脚本中 `mkdir -p /sdcard/atlas_shared`，Termux 需授予存储权限（termux-setup-storage） |
| Tasker 因 Doze 无法准时触发 | 低 | 中 | 文档中提示用户将 Tasker 加入电池优化白名单，并建议使用 Tasker 的"可靠闹钟"模式 |
| 结果文件竞态（多次触发覆盖） | 中 | 低 | 使用 correlation_id 隔离结果文件，last_result.json 仅保存最新结果 |

---

#### T5：AutoJS6 集成 — UI 执行器链路（P0，7 人天）

**目标**：让 Atlas Runtime 能够通过 Intent 启动 AutoJS6 执行 UI 自动化脚本，脚本完成后通过 HTTP 回调通知 Atlas。

**实现方案**：

集成架构：

```
Atlas Runtime (core/scheduler.py)
    │ 执行 action='ui_automation'
    ▼
executors/ui_automation.py → 决策：
    │ 简单操作(input tap/swipe) → 直接执行（现有能力）
    │ 复杂操作(APP 内多步骤) → 委派 AutoJS6
    ▼
transport/autojs_launcher.py
    │ am startservice 启动 AutoJS6 后台服务
    │ 传递脚本路径 + 参数 + 回调 URL
    ▼
AutoJS6 脚本 (.js)
    │ auto.waitFor() → 无障碍操作 → 截图 → 结果序列化
    ▼
HTTP POST → http://127.0.0.1:8787/trigger
    │ {"action":"ui_result","params":{...},"correlation_id":"..."}
    ▼
Atlas Runtime → ResultCallback → /sdcard/atlas_shared/
```

**子任务拆分**：

**T5a — AutoJS6 无障碍服务脚本模板**（3 人天）

标准模板结构（所有 AutoJS6 脚本的基础框架）：

```javascript
// atlas_ui_template.js — Atlas Runtime AutoJS6 标准脚本模板
"ui";  // UI 线程模式

// ========== 参数接收 ==========
const scriptParams = JSON.parse(engines.myEngine().execArgv.scriptParams || "{}");
const WORKFLOW_ID = scriptParams.workflow_id || "unknown";
const CALLBACK_URL = scriptParams.callback_url || "http://127.0.0.1:8787/trigger";
const TARGET_APP = scriptParams.target_app || "";
const ACTIONS = scriptParams.actions || [];
const TIMEOUT = scriptParams.timeout || 30000;

// ========== 结果上报函数 ==========
function reportResult(status, data, error) {
    try {
        let payload = {
            action: "ui_result",
            params: {
                workflow_id: WORKFLOW_ID,
                status: status,        // "success" | "failed" | "timeout" | "cancelled"
                data: data || {},
                error: error || null,
                timestamp: Date.now()
            },
            correlation_id: WORKFLOW_ID
        };
        let resp = http.postJson(CALLBACK_URL, payload);
        console.log("上报结果: " + resp.statusCode);
    } catch (e) {
        console.error("上报失败: " + e.message);
    }
}

// ========== 主流程 ==========
function main() {
    try {
        // 1. 确保无障碍服务已开启
        auto.waitFor();  // 最多等待 10 秒
        console.log("无障碍服务就绪");

        // 2. 启动目标 APP
        if (TARGET_APP) {
            app.launchPackage(TARGET_APP);
            sleep(3000);  // 等待 APP 冷启动
        }

        // 3. 执行 UI 操作序列
        for (let i = 0; i < ACTIONS.length; i++) {
            let action = ACTIONS[i];
            let result = executeAction(action);
            if (!result.success) {
                reportResult("failed", {step: i, action: action}, result.error);
                return;
            }
            sleep(action.delay || 500);
        }

        // 4. 成功完成
        reportResult("success", {steps_completed: ACTIONS.length}, null);

    } catch (e) {
        reportResult("failed", {}, e.message);
    }
}

// ========== 操作执行器 ==========
function executeAction(action) {
    switch (action.type) {
        case "click":
            return clickTarget(action.target);
        case "text":
            return inputText(action.target, action.value);
        case "wait_for":
            return waitForElement(action.target, action.timeout || 5000);
        case "swipe":
            return doSwipe(action.x1, action.y1, action.x2, action.y2, action.duration || 300);
        case "screenshot":
            return takeScreenshot(action.path);
        default:
            return {success: false, error: "Unknown action type: " + action.type};
    }
}

function clickTarget(target) {
    if (target.id) {
        let elem = id(target.id).findOne(3000);
        if (elem) { elem.click(); return {success: true}; }
    }
    if (target.text) {
        let elem = text(target.text).findOne(3000);
        if (elem) { elem.click(); return {success: true}; }
    }
    if (target.desc) {
        let elem = desc(target.desc).findOne(3000);
        if (elem) { elem.click(); return {success: true}; }
    }
    if (target.x && target.y) {
        click(target.x, target.y);
        return {success: true};
    }
    return {success: false, error: "Element not found: " + JSON.stringify(target)};
}

// ... (其余辅助函数)

// ========== 超时保护 ==========
setTimeout(() => {
    reportResult("timeout", {}, "执行超时 (" + TIMEOUT + "ms)");
    exit();
}, TIMEOUT);

// ========== 入口 ==========
main();
```

**T5b — AutoJS6 → Atlas HTTP 回调客户端**（2 人天）

在 AutoJS6 侧实现可靠的 HTTP 回调。已在 T5a 的 `reportResult` 函数中包含。需要额外处理：
- 网络不可达时重试 3 次（间隔 1s/2s/3s）
- 最终失败时写入本地文件（`/sdcard/atlas_shared/autojs_fallback_{timestamp}.json`）
- 回调内容包含截图 base64（可选，需控制大小）

**T5c — Atlas → AutoJS6 Intent 启动机制**（2 人天）

新建 transport 模块：

```
transport/autojs_launcher.py:
class AutoJS6Launcher:
    """通过 Android Intent 启动 AutoJS6 执行脚本"""
    def __init__(self, shell_executor: SafeShellExecutor)
    async def launch_script(
        self,
        script_path: str,         # 脚本在 /sdcard/ 的路径
        params: Dict[str, Any],   # 传递给脚本的参数
        timeout: float = 30.0
    ) -> Dict[str, Any]
    async def stop_script(self, workflow_id: str) -> bool
```

实现细节：
- 使用 `am startservice` 或 `am start -n org.autojs.autojs/.external.open.ScriptIntentActivity` 启动
- 通过 extras 传递脚本参数（JSON 字符串，需控制长度避免 Intent 1MB 限制）
- 备选方案：参数写入文件，Intent 仅传递文件路径

**交付物**：

| 交付物 | 格式 | 说明 |
|:---|:---|:---|
| `scripts/autojs/atlas_ui_template.js` | JavaScript | 通用 UI 自动化脚本模板 |
| `scripts/autojs/sim_switch_verify.js` | JavaScript | SIM 切换后 UI 验证脚本示例 |
| `scripts/autojs/app_launcher.js` | JavaScript | 通用 APP 启动+操作脚本示例 |
| `transport/autojs_launcher.py` | Python 模块 | Intent 启动 AutoJS6 的 Python 封装 |

**风险与应对**：

| 风险 | 概率 | 影响 | 应对措施 |
|:---|:---|:---|:---|
| AutoJS6 无障碍服务被系统杀死 | 高 | 高 | T5a 模板中 `auto.waitFor()` 带超时+重试；结果上报中包含无障碍状态字段 |
| AutoJS6 APK 版本不兼容 | 中 | 高 | 明确要求 AutoJS6 ≥ 6.5.0；文档中提供 GitHub Release 下载链接 |
| Intent 启动在部分 ROM 上被拦截 | 中 | 中 | 提供备选方案：通过文件轮询方式触发（AutoJS6 侧定时检查指定目录） |
| HTTP 回调失败（网络不可达） | 中 | 中 | T5b 的本地文件回退机制（`autojs_fallback_*.json`） |
| 脚本内 Bitmap 内存泄漏 | 中 | 低 | 模板中所有截图操作后显式调用 `img.recycle()` |

---

### 5.3 第三阶段：验证与收尾（Later — 第 4-5 周）

**里程碑 M3：系统全面可用**（2026-09-09）

目标：在真实 Android 设备上验证全部链路，补全文档，完成三个设计超前模块。

#### T6：真实设备端到端测试（P0，8 人天）

**T6a — SIM 切换端到端验证**（2 人天）

测试链路：Tasker Time Profile(08:55) → FIFO → Atlas → HighPrivilegeExecutor.switch_sim(1) → AutoJS6 验证 UI → HTTP 回调 → Atlas → ResultCallback → Tasker 通知

验证点：
- Tasker Profile 准时触发（误差 < 2 秒）
- FIFO 消息被正确解析和调度
- SIM 切换命令在 Samsung/AOSP 设备上均正确执行
- AutoJS6 验证脚本成功检测网络运营商变化
- 结果正确回传至 Tasker 通知

**T6b — UI 自动化端到端验证**（2 人天）

测试链路：HTTP POST /trigger → Atlas → AutoJS6Launcher → AutoJS6 执行 UI 操作 → HTTP 回调 → Atlas 记录

验证点：
- AutoJS6 脚本通过 Intent 正确启动
- click/swipe/type_text 等操作准确命中目标
- takeScreenshot 截图包含预期内容
- 超时保护机制正常触发
- Bitmap 内存被正确释放（连续执行 20 次后内存无增长）

**T6c — 崩溃重启恢复验证**（2 人天）

验证点：
- `kill -9` Runtime 进程后 runit 在 < 2 秒内重启
- 重启后 Bootstrap 正常加载所有组件
- 重启前未完成的 Task 被正确标记为 FAILED 并进入死信
- 重启前 pending delay 队列中的 Task 通过状态快照恢复
- 连续崩溃 3 次后系统仍能启动（不进入 runit 的崩溃循环）

**T6d — 快照冷恢复验证**（2 人天）

验证点：
- 正常关机 → 快照写入 → SHA256 校验通过
- 重新启动 → load_state → 状态完整恢复（全部 key 一致）
- 快照文件损坏（手动篡改 checksum）→ 优雅回退至默认状态
- BatteryAwareCheckpoint 在低电量模式下延迟写入验证

**交付物**：
- `tests/e2e/test_checklist.md`：端到端测试逐项检查清单
- 每项测试的执行日志（`logs/e2e_{date}.log`）
- 缺陷报告（如发现）

#### T2：CircuitBreaker 实现（P2，2 人天）

**目标**：防止连续失败的任务耗尽系统资源。

```
core/circuit_breaker.py:
class CircuitBreaker:
    States: CLOSED → OPEN → HALF_OPEN → CLOSED

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0)
    async def record_success(self) -> None
    async def record_failure(self) -> None
    def is_open() -> bool                                    # 熔断器是否开启
    def get_state() -> str                                   # CLOSED/OPEN/HALF_OPEN
```

集成点：在 Scheduler._execute_task 的异常捕获分支中调用 `circuit_breaker.record_failure()`，连续失败达到阈值后暂停调度新任务。恢复策略：冷却期（30s）结束后进入 HALF_OPEN，下一次成功则 CLOSE，失败则重新 OPEN。

#### T3：Dedup 去重实现（P2，2 人天）

**目标**：基于 correlation_id 的 TTL 窗口去重。

```
core/dedup.py:
class DedupFilter:
    def __init__(self, ttl: float = 60.0, max_entries: int = 10000)
    async def is_duplicate(self, correlation_id: str) -> bool
    async def mark_seen(self, correlation_id: str) -> None
    async def cleanup_expired(self) -> None                   # 定期清理过期条目
```

实现方案：使用内存 OrderedDict + 过期时间戳，避免 SQLite 查询开销。key 为 `hash(action + correlation_id)`，TTL 窗口内重复触发直接丢弃并记录 metrics。

#### T7 & T8：文档收尾（P3，各 1 人天）

- T7：Tasker 配置导入指南，含逐步截图、常见问题排查
- T8：AutoJS6 脚本开发指南，含 API 参考、调试技巧、设备兼容性矩阵

---

## 六、资源分配

### 6.1 资源模型

本项目为单人开发（1 名全栈开发者兼任 PM），资源模型参数：

- 有效编码时间：6 小时/天（扣除会议、文档、调试环境）
- 每周工作 5 天
- 总可用人天：25 天（5 周 × 5 天/周）
- 计划任务总人天：31 天
- 资源缺口：6 天（约 20%）

### 6.2 缺口处理策略

缺口 6 天通过以下方式吸收：

1. T3 Dedup 和 T2 CircuitBreaker 共享底层数据结构（OrderedDict + 时间戳），合计可节省 1 天
2. T7/T8 文档可在 T4/T5 执行过程中同步编写初稿，正式阶段仅需润色，各节省 0.5 天
3. T6 E2E 测试可在真实设备上批量并行执行（多台设备），节省 2 天
4. T1 MemoryController 的优雅降级逻辑可简化（仅监控 + 告警，不做硬限拒绝），节省 1 天
5. 剩余缺口 1 天由第 5 周弹性缓冲吸收

调整后的实际人天分配：

| 阶段 | 任务 | 原始人天 | 调整后人天 | 说明 |
|:---|:---|:---|:---|:---|
| Phase 1 | T1 MemoryController | 3 | 2.5 | 首版仅监控+告警+软限，硬限简化 |
| Phase 2 | T4 Tasker 集成 | 5 | 5 | 全职投入 |
| Phase 2 | T5 AutoJS6 集成 | 7 | 6.5 | 与 T4 并行推进 |
| Phase 3 | T6 真机 E2E | 8 | 6 | 多设备并行 + T4/T5 期间穿插测试 |
| Phase 3 | T2 CircuitBreaker | 2 | 1.5 | 与 T3 共享数据结构 |
| Phase 3 | T3 Dedup | 2 | 1.5 | 与 T2 共享数据结构 |
| Phase 3 | T7/T8 文档 | 2 | 1.5 | T4/T5 期间同步编写 |
| **合计** | | **29** | **24.5** | 在 25 天预算内 |

### 6.3 资源甘特图

```
                 Week 1     Week 2     Week 3     Week 4     Week 5
               (08/05-09) (08/12-16) (08/19-23) (08/26-30) (09/02-06)
T1 MemoryCtrl   ████████░░░
T4 Tasker       ░░░█████████████████████░░░░░░░░
T5 AutoJS6      ░░░░░█████████████████████████░░
T6 E2E          ░░░░░░░░░░░░░░░██████████████████
T2 CircuitBrkr  ░░░░░░░░░░░░░░░░░░░░░░████░░░░░░
T3 Dedup        ░░░░░░░░░░░░░░░░░░░░░░░░████░░░░
T7/T8 文档      ░░░░░░░░░░░░░░░░░░░░░░░░░░░██████

M1(08/19): MemoryController 上线
M2(09/04): 端到端触发链路贯通
M3(09/09): 系统全面可用
```

---

## 七、交付物清单

### 7.1 代码交付物

| 文件 | 类型 | 预计行数 | 对应任务 |
|:---|:---|:---|:---|
| `core/memory_controller.py` | Python 模块 | ~200 | T1 |
| `core/circuit_breaker.py` | Python 模块 | ~120 | T2 |
| `core/dedup.py` | Python 模块 | ~100 | T3 |
| `transport/result_callback.py` | Python 模块 | ~80 | T4c |
| `transport/autojs_launcher.py` | Python 模块 | ~150 | T5c |
| `runtime/trigger_atlas.sh` | Shell 脚本 | ~30 | T4b |
| `scripts/autojs/atlas_ui_template.js` | JavaScript | ~250 | T5a |
| `scripts/autojs/sim_switch_verify.js` | JavaScript | ~80 | T5a |
| `scripts/autojs/app_launcher.js` | JavaScript | ~100 | T5a |
| `config/tasker/*.xml` | XML 配置 | ~200 | T4a,T4b |
| `tests/test_memory_controller.py` | Python 测试 | ~120 | T1 |
| `tests/test_circuit_breaker.py` | Python 测试 | ~100 | T2 |
| `tests/test_dedup.py` | Python 测试 | ~80 | T3 |

**代码增量预估**：约 1,610 行（Python ~950 + JavaScript ~430 + Shell ~30 + XML ~200）

### 7.2 文档交付物

| 文件 | 预计字数 | 对应任务 |
|:---|:---|:---|
| `docs/TASKER_INTEGRATION_GUIDE.md` | ~3000 | T7 |
| `docs/AUTOJS6_SCRIPT_GUIDE.md` | ~3000 | T8 |
| `tests/e2e/test_checklist.md` | ~2000 | T6 |

---

## 八、风险矩阵与应对措施

### 8.1 全局风险

| 风险 ID | 风险描述 | 概率 | 影响 | 应对策略 | 触发信号 | 负责人 |
|:---|:---|:---|:---|:---|:---|:---|
| R1 | Termux 环境更新导致 Python 3.11+ 兼容性破坏 | 低 | 高 | 锁定 Termux 版本；CI 中加入 Termux 环境矩阵测试 | pkg update 后 test suite 失败 | 开发者 |
| R2 | Samsung One UI / MIUI 等 OEM 系统额外限制 | 高 | 中 | T6 E2E 测试覆盖至少 2 台主流品牌设备；高权限操作保留三级回退 | 单设备测试通过但另一设备失败 | 开发者 |
| R3 | AutoJS6 项目停更或版本不兼容 | 中 | 高 | 降级为纯 shell input 方案；AutoJS6 仅作复杂 UI 备选（不影响 P0 用例） | AutoJS6 GitHub 长期无更新 | 开发者 |
| R4 | 真实设备测试时发生不可逆系统变更 | 低 | 高 | 测试前完整备份；仅在工作时间测试关键操作；SIM 切换前确认双卡在位 | — | 开发者 |
| R5 | 工期紧张导致质量下降 | 中 | 中 | 每阶段完成后执行 regression test suite；若延期超 1 周则降级 P2（T2/T3） | 进度落后计划 > 3 天 | 开发者 |

### 8.2 降级预案

若第 3 周结束时 T4（Tasker 集成）进度落后超过 3 天：

- 即刻裁剪 T4c（Tasker 结果接收）的自动化程度：从 JavaScriptlet 自动解析降级为 Tasker Notify + 手动查看 log
- 相当于压缩 1 人天，确保 M2 里程碑不延期

若第 4 周结束时整体进度落后超过 5 天：

- T2 CircuitBreaker 和 T3 Dedup 降级为"仅数据结构预留 + TODO 注释"，不实现完整逻辑
- T6 E2E 测试仅覆盖 T6a（SIM 切换）和 T6c（崩溃恢复），裁剪 T6b（UI 自动化）和 T6d（快照恢复）
- 目标：确保 M3 里程碑至少交付"SIM 切换端到端闭环"

---

## 九、成功度量

每个里程碑的完成标准：

**M1（08-19）：MemoryController 上线**
- `core/memory_controller.py` 通过单元测试
- 在真实设备上运行 `health_check.py` 能读取到 memory 指标
- 模拟内存压力（大量并发触发）后 MemoryController 正确触发 WARNING/CRITICAL 日志
- psutil 不可用时优雅降级（WARNING 日志 + 其余组件不受影响）

**M2（09-04）：端到端触发链路贯通**
- Tasker Time Profile → Atlas FIFO → SIM 切换 → 结果通知 全链路在真实设备上跑通至少 3 次
- AutoJS6 脚本通过 Atlas Intent 启动并成功回调结果
- 两条链路均包含失败重试和超时保护验证
- 交付物文件全部就位且可运行

**M3（09-09）：系统全面可用**
- 端到端测试检查清单全部通过
- CircuitBreaker 和 Dedup 通过单元测试（或标注为降级完成）
- 两份用户文档完成并通过新人验证（无背景读者可按文档独立完成部署）
- 回归测试套件全部通过（15 个现有测试 + 新增 3 个测试）

---

## 十、附录

### 附录 A：与设计规范的对标追踪

| 设计规范 §9 条目 | 本方案对应任务 | 预计完成时间 |
|:---|:---|:---|
| MemoryController | T1 | 2026-08-19 |
| CircuitBreaker | T2 | 2026-09-06 |
| Dedup | T3 | 2026-09-06 |
| Tasker 集成 | T4 | 2026-09-04 |
| Auto.js6 集成 | T5 | 2026-09-04 |
| 端到端测试 | T6 | 2026-09-09 |

### 附录 B：关键文件新增/修改一览

| 操作 | 文件 | 对应任务 |
|:---|:---|:---|
| **新增** | `core/memory_controller.py` | T1 |
| **新增** | `core/circuit_breaker.py` | T2 |
| **新增** | `core/dedup.py` | T3 |
| **新增** | `transport/result_callback.py` | T4c |
| **新增** | `transport/autojs_launcher.py` | T5c |
| **新增** | `runtime/trigger_atlas.sh` | T4b |
| **新增** | `scripts/autojs/*.js` | T5a |
| **新增** | `config/tasker/*.xml` | T4a,T4b |
| **修改** | `core/bootstrap.py` | T1 (注册 MemoryController) |
| **修改** | `core/scheduler.py` | T2/T3 (集成 CircuitBreaker + Dedup) |
| **修改** | `config/runtime.yaml` | T1 (激活 memory 配置段) |
| **新增** | `docs/TASKER_INTEGRATION_GUIDE.md` | T7 |
| **新增** | `docs/AUTOJS6_SCRIPT_GUIDE.md` | T8 |
| **新增** | `tests/e2e/test_checklist.md` | T6 |
| **新增** | `tests/test_memory_controller.py` | T1 |
| **新增** | `tests/test_circuit_breaker.py` | T2 |
| **新增** | `tests/test_dedup.py` | T3 |

---

> 文档版本：v1.0 | 维护者：Atlas Architecture Group | 最后更新：2026-08-05
