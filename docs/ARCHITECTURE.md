# Atlas Runtime v9.0 架构设计文档

> 版本：v9.1 | 最后更新：2026-08-08

## 设计原则

1. **Termux First**: 所有核心逻辑运行在 Termux 中，利用 termux-services (runit) 实现服务保活与自动重启
2. **事件驱动**: FIFO 命名管道接收触发信号，完全免疫 Android Doze 模式的网络限制
3. **进程安全**: Shell 子进程通过独立进程组 (`start_new_session=True`) 隔离，超时通过 `os.killpg()` 安全清理
4. **端到端背压控制**: SQLite 写入队列有界（maxsize=1000），`asyncio.QueueFull` 触发背压退避
5. **原子快照**: 深拷贝冻结状态 + 临时文件 + `os.replace()` 原子重命名 + SHA256 校验和
6. **分层依赖单向**: 上层可依赖下层，禁止反向依赖。数据模型层无依赖，被所有层安全引用

## 优化后模块分层

```
┌─────────────────────────────────────────────────────────┐
│  runtime/app.py            主入口 + 信号管理              │  Layer 6: 入口
├─────────────────────────────────────────────────────────┤
│  transport/                通信层                        │  Layer 5: 接口
│    trigger_server.py       FIFO(主) + HTTP(备)           │
├─────────────────────────────────────────────────────────┤
│  core/                     微内核（活动组件）             │  Layer 4: 内核
│    bootstrap.py            启动编排                       │
│    scheduler.py            双队列调度                     │
│    state_manager.py        状态 + 快照                    │
│    resource_lock.py        持久化互斥锁 + CAS             │
│    trigger_handler.py      背压控制 + 死信管理            │
├─────────────────────────────────────────────────────────┤
│  executors/                执行器                        │  Layer 3: 执行
│    base.py                 BaseExecutor ABC ✅            │
│    shell_executor.py       安全 Shell                     │
│    ui_automation.py        UI 自动化                      │
│    sim_switch.py           SIM 卡切换 ✨                  │
│    high_privilege.py       高权限操作（WiFi/Data/音量）    │
├─────────────────────────────────────────────────────────┤
│  device/                   设备平台层 ✨                  │  Layer 2: 平台
│    detector.py             PlatformInfo 平台检测          │
│    health.py               HealthChecker 健康检查         │
├─────────────────────────────────────────────────────────┤
│  storage/                  持久层                        │  Layer 1: 存储
│    driver.py               单写者队列 SQLite              │
│    snapshot.py             原子快照                       │
│    rotator.py              自动轮转归档                   │
│    battery_aware.py        电量感知 Checkpoint            │
├─────────────────────────────────────────────────────────┤
│  models/                   数据契约 ✅                   │  Layer 0: 模型
│    health.py               电池/内存/系统健康              │
│    sim.py                  SIM 信息/状态/结果              │
│    task.py                 Task / TaskStatus 任务模型 ✨   │
│    errors.py               统一异常类型                    │
├─────────────────────────────────────────────────────────┤
│  config/runtime.yaml       运行时配置                     │  Config
└─────────────────────────────────────────────────────────┘

✨ = v9.0 架构优化新增/重构
```

## 层间依赖规则

依赖方向严格自上而下，每层只能依赖其下层：

```
Layer 6 (runtime)  → Layer 5 (transport), Layer 4 (core), Layer 2 (device)
Layer 5 (transport) → Layer 0 (models)  # v9.1: 移除了对 core 的跨层依赖
Layer 4 (core)      → Layer 3 (executors), Layer 1 (storage), Layer 0 (models)
Layer 3 (executors) → Layer 0 (models)
Layer 2 (device)    → Layer 0 (models)
Layer 1 (storage)   → Layer 0 (models)
Layer 0 (models)    → 无依赖
```

禁止的依赖方向：
- core → device（微内核不应依赖平台层，通过兼容性存根间接引用属历史遗留）
- executors → storage（执行器不应直接操作存储）
- storage → executors（存储层不应感知执行器）

## 各模块职责

### Layer 0: models/ — 数据契约

跨所有层共享的纯数据结构，不包含业务逻辑、I/O 操作或外部依赖。

| 模块 | 职责 |
|:---|:---|
| `models/health.py` | BatteryStatus, MemoryStatus, SystemHealth — 健康状态数据类 |
| `models/sim.py` | SimInfo, SimStatus, SimSwitchResult — SIM 卡数据类 |
| `models/task.py` ✨ | Task, TaskStatus — 任务调度数据类。从 core/scheduler.py 迁移，消除 trigger_handler 的 TYPE_CHECKING 延迟导入 |
| `models/errors.py` | StorageFullError, StorageError, BackpressureError, AtlasError — 统一异常类型 |

设计理由：之前 BatteryStatus 等散落在 health_checker.py 中，SimInfo 等在 high_privilege.py 中，StorageFullError 定义在 storage/driver.py 中而被 core/trigger_handler.py 跨层引用。v9.0 集中到 models/ 后消除了跨层依赖，所有层均可安全引用。v9.1 新增 models/task.py，将 Task/TaskStatus 从 core/scheduler.py 提取为纯数据契约。

### Layer 1: storage/ — 持久层

SQLite WAL 模式 + 自定义单写者队列。职责：

| 模块 | 职责 |
|:---|:---|
| `storage/driver.py` | AsyncSQLiteStorage — 单写者队列驱动的 SQLite 存储（WAL 模式） |
| `storage/snapshot.py` | 原子快照 — 深拷贝 + 临时文件 + os.replace() + SHA256 校验 |
| `storage/rotator.py` | 自动轮转归档 — 日志文件大小/时间过期管理 |
| `storage/battery_aware.py` | BatteryAwareCheckpoint — 低电量时暂停写入以保护数据完整性 |

### Layer 2: device/ — 设备平台层

封装所有平台相关的 I/O 操作（Termux API、Android 命令行、/proc 文件系统）。v9.0 从 `core/` 中分离。

| 模块 | 职责 |
|:---|:---|
| `device/detector.py` | PlatformInfo — 设备制造商、One UI 版本、Android SDK、命令可用性、硬件资源、Termux 工具链探测 |
| `device/health.py` | HealthChecker — 周期性电池状态/温度/内存监控，termux-battery-status 优先，dumpsys battery 回退 |

迁移理由：platform.py 和 health_checker.py 属于平台适配层，与内核调度/状态管理职责不同。分离后 core/ 仅保留有生命周期的活动组件。

### Layer 3: executors/ — 执行器层

执行具体的 Shell 命令、UI 自动化、系统级操作。v9.0 新增 BaseExecutor ABC 和 sim_switch 独立模块。

| 模块 | 职责 |
|:---|:---|
| `executors/base.py` ✅ | BaseExecutor ABC + ExecutorResult 统一结果类型。v9.1：SafeShellExecutor 已继承 BaseExecutor，Scheduler 通过 executor.execute() 调用 |
| `executors/shell_executor.py` | SafeShellExecutor — 安全 Shell 执行（进程组隔离、Termux PATH 适配、超时 killpg） |
| `executors/ui_automation.py` | UIAutomationExecutor — UI 自动化（uiautomator dump + 点击/滑动/输入） |
| `executors/sim_switch.py` ✨ | ShizukuSimManager（Shizuku/Rish 方案） + AutoJS6SimSwitcher（ABC 预留） |
| `executors/high_privilege.py` | HighPrivilegeExecutor — WiFi/Data/Airplane/Volume 控制（多层回退）+ SIM 操作委托 |

拆分理由：high_privilege.py 原有 799 行，混合了 SIM 数据类、ABC 接口、ShizukuSimManager 和 WiFi/Data 控制。拆分后每个文件 ~400 行，职责单一。

### Layer 4: core/ — 微内核

仅包含有生命周期的活动组件（start/stop 生命周期），不包含数据模型或平台检测。

| 模块 | 职责 |
|:---|:---|
| `core/bootstrap.py` | Bootstrap — 启动编排，按拓扑顺序初始化各组件 |
| `core/scheduler.py` | Scheduler — 双队列调度器。v9.1：Task/TaskStatus 已迁移至 models/task.py；executor 参数改为 BaseExecutor 协议 |
| `core/state_manager.py` | StateManager — 状态管理 + 原子快照保存/恢复 |
| `core/resource_lock.py` | ResourceLock — 基于 SQLite CAS 的持久化分布式互斥锁 |
| `core/trigger_handler.py` | TriggerHandler — 背压控制（队列满时拒绝 + 退避）、死信管理 |
| `core/platform.py` | → 兼容性存根，re-export 至 device/detector.py |
| `core/health_checker.py` | → 兼容性存根，re-export 至 device/health.py |
| `core/shell_executor.py` | → 兼容性存根，re-export 至 executors/shell_executor.py |

兼容性存根说明：`core/platform.py`、`core/health_checker.py`、`core/shell_executor.py` 保留为 re-export 存根，确保 `from core.platform import PlatformInfo` 等旧导入路径仍可用。新代码请使用新路径（`from device import PlatformInfo`）。

### Layer 5: transport/ — 通信层

| 模块 | 职责 |
|:---|:---|
| `transport/trigger_server.py` | TriggerServer — FIFO 命名管道（主）+ HTTP 触发器（备用），双模信号接收 |

### Layer 6: runtime/ — 入口

| 模块 | 职责 |
|:---|:---|
| `runtime/app.py` | 主入口 — 命令行解析、信号管理、组件生命周期编排 |

## 数据流

```
Tasker/FIFO → TriggerServer → TriggerHandler → Scheduler → StateManager
                                   ↑ 背压              ↓
                            models.errors     executors.SafeShellExecutor
                                                     ↓
                                              HighPrivilegeExecutor
                                               ├── ShizukuSimManager → Rish → service call isub
                                               ├── set_wifi_enabled → svc/cmd/settings/service call
                                               ├── set_mobile_data_enabled → svc/settings/service call
                                               └── set_volume → media/cmd media_session
                                                     ↓
                                              StateManager.snapshot → storage
```

背压传导路径：SQLite 队列满 → StorageFullError → TriggerHandler 拒绝接收 → TriggerServer 返回 HTTP 429 / FIFO 写入延迟

## 目录结构（完整）

```
atlas-runtime/
├── config/
│   └── runtime.yaml                 # 运行时配置（含 shizuku_sim 段）
├── models/          ✨ v9.0 新增
│   ├── __init__.py                  # 导出全部数据模型
│   ├── health.py                    # BatteryStatus, MemoryStatus, SystemHealth
│   ├── sim.py                       # SimInfo, SimStatus, SimSwitchResult
│   └── errors.py                    # StorageFullError, StorageError, BackpressureError
├── device/          ✨ v9.0 新增（原 core/platform.py + core/health_checker.py）
│   ├── __init__.py                  # 导出 PlatformInfo, HealthChecker
│   ├── detector.py                  # PlatformInfo 平台检测
│   └── health.py                    # HealthChecker 健康检查
├── storage/
│   ├── __init__.py
│   ├── driver.py                    # SQLite 驱动
│   ├── snapshot.py                  # 原子快照
│   ├── rotator.py                   # 日志轮转
│   └── battery_aware.py             # 电量感知
├── executors/
│   ├── __init__.py
│   ├── base.py        ✨ v9.0 新增  # BaseExecutor ABC + ExecutorResult
│   ├── shell_executor.py            # SafeShellExecutor
│   ├── ui_automation.py             # UIAutomationExecutor
│   ├── sim_switch.py ✨ v9.0 新增   # ShizukuSimManager + AutoJS6SimSwitcher
│   └── high_privilege.py            # HighPrivilegeExecutor（精简后）
├── core/
│   ├── __init__.py
│   ├── bootstrap.py                 # 启动编排
│   ├── scheduler.py                 # 双队列调度
│   ├── state_manager.py             # 状态管理
│   ├── resource_lock.py             # 持久化互斥锁
│   ├── trigger_handler.py           # 背压 + 死信
│   ├── platform.py                  # → 兼容性存根 → device/detector.py
│   ├── health_checker.py            # → 兼容性存根 → device/health.py
│   └── shell_executor.py            # → 兼容性存根 → executors/shell_executor.py
├── transport/
│   ├── __init__.py
│   └── trigger_server.py            # FIFO + HTTP 触发器
├── runtime/
│   └── app.py                       # 主入口
├── tests/
│   ├── conftest.py
│   ├── test_models.py         ✨ v9.1   # models/ 层独立测试
│   ├── test_device.py         ✨ v9.1   # device/ 层独立测试
│   ├── test_executor_base.py  ✨ v9.1   # BaseExecutor ABC 测试
│   ├── test_sim_switch.py     ✨ v9.1   # SIM 切换执行器测试
│   ├── test_high_privilege.py
│   ├── test_shell_executor.py
│   ├── test_driver.py
│   └── ...                          # 其余测试文件
├── docs/
│   ├── ARCHITECTURE.md              # 本文档
│   ├── DESIGN_SPEC_v8.0.md
│   ├── IMPLEMENTATION_PLAN.md
│   └── ...
├── service/
│   ├── deploy.sh
│   ├── update.sh
│   └── run
└── config/
    └── runtime.yaml
```

## 关键设计决策

### 1. 为何新增 models/ 而非放入 core/

core/ 定位为微内核，包含有生命周期的活动组件（start/stop）。数据类是无状态的纯数据契约，逻辑上属于跨层共享基础设施。独立包避免循环导入问题，所有层都可以安全引用 models。

### 2. 为何分离 device/ 平台层

platform.py 和 health_checker.py 属于平台适配层，与内核调度/状态管理职责不同。分离后 core/ 仅保留 5 个微内核组件。未来可扩展更多平台能力（如不同厂商适配）。命名为 device/ 而非 platform/ 以避免与 Python 标准库 `platform` 模块命名冲突。

### 3. 为何拆分 SIM 切换到独立文件

high_privilege.py 原有 799 行，混合了 SIM 数据类、ABC 接口、ShizukuSimManager 和 WiFi/Data/Volume 控制。拆分后：

- SimInfo/SimStatus/SimSwitchResult → models/sim.py（数据契约）
- AutoJS6SimSwitcher + ShizukuSimManager → executors/sim_switch.py（实现）
- HighPrivilegeExecutor 仅保留 WiFi/Data/Airplane/Volume + SIM 委托调用

### 4. 为何新增 BaseExecutor ABC

统一执行器接口契约，标准化的 ExecutorResult 格式，便于未来扩展新的执行器类型（如 ADB Executor、MCP Executor），提供默认的 connect/disconnect 生命周期方法。

### 5. 跨层依赖解耦方案

StorageFullError 从 storage/driver.py 提升到 models/errors.py。storage 和 core 均从 models 导入，消除了 core → storage 的硬依赖。storage/driver.py 仍 re-export StorageFullError 以保持向后兼容。

### 6. 兼容性存根策略

`core/platform.py`、`core/health_checker.py`、`core/shell_executor.py` 保留为 `from xxx import *` 兼容性存根。旧代码无需修改即可继续工作。未来大版本移除。

### 7. Logger 名称不变

所有模块迁移后 Logger 名称保持原样（如 `Atlas.HealthChecker`、`Atlas.HighPrivilege`），避免日志分析工具和监控告警规则失效。

## 任务状态机

```
PENDING → SCHEDULED → EXECUTING → SUCCESS
                                → TIMEOUT → RETRY（最多3次，指数退避）
                                → FAILED → RETRY → DEAD（写死信）
```

## 故障自愈

| 故障场景 | 检测方式 | 恢复动作 |
|:---|:---|:---|
| Runtime 进程崩溃 | runit 监控 PID | 即时重启（< 2 秒） |
| HTTP 端口冲突 | OSError 捕获 | `fuser -k` 释放 → 重试 |
| Shell 命令超时 | `asyncio.wait_for(5s)` | `killpg` → 重试 |
| SQLite 队列满 | `asyncio.QueueFull` | 背压退避 1 秒 → HTTP 429 |
| 存储空间不足 | 写入前预检（< 50MB） | 拒绝写入 → 只读模式 |
| FIFO 管道阻塞 | `O_RDWR \| O_NONBLOCK` | `open` 永不阻塞 |
| 孤儿锁残留 | 启动时清理 | 检查 `expires_at <= now` 删除 |
| SIM 切换事务码失败 | 预设码无效 | 自愈扫描 (20-50) 找到正确事务码 |

## 组件定位

| 组件 | 定位 | 必须 | 通信方式 |
|:---|:---|:---|:---|
| Termux + Python Runtime | 核心大脑 | ✅ | — |
| Tasker | 轻量触发器 | ✅ 推荐 | FIFO（主）/ HTTP（备） |
| Shizuku + Rish | SIM 切换代理 | ✅ | shell 子进程 |
| Auto.js6 | 复杂 UI 执行器 | ❌ 可选 | Intent / HTTP |

## 部署脚本

| 脚本 | 用途 |
|:---|:---|
| `service/deploy.sh` | 一键部署 |
| `service/update.sh` | 增量补丁应用（含自动备份与回退） |
| `service/run` | runit 服务启动脚本 |
