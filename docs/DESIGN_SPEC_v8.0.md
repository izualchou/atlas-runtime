# Atlas Runtime v8.0 LTS — 修复后项目设计文档（完整规范）

> **版本**：v8.0 LTS（Post-Fix）  
> **状态**：✅ 核心引擎已部署运行，待 Tasker/Auto.js6 集成  
> **最后更新**：2026-08-02  
> **文档类型**：架构设计 + 接口协议 + 缺陷修复记录  
> **维护者**：Atlas Architecture Group

---

## 一、文档导读

本文档基于已修复的代码库生成，覆盖：

1. 项目核心目标与设计哲学
2. 系统架构图与组件划分
3. 各模块职责、接口定义与模块间交互
4. 端到端数据流与任务状态机
5. **已修复设计缺陷**（每项含问题描述 / 修复方案 / 影响范围）
6. 数据库结构（含变更说明）
7. 修复后的接口协议（FIFO / HTTP / 配置）
8. 设计约束与假设条件

> 本文档与代码库保持同步。历史存根 `docs/ARCHITECTURE.md` 仅保留为快速索引，本文件为权威规范。

---

## 二、项目核心目标与设计哲学

### 2.1 核心目标

Atlas Runtime 是一个运行在 Android 系统上、基于 **Termux** 的事件驱动型自动化运行时。核心目标：

- **高可用**：利用 runit 实现崩溃即时重启（< 2 秒），无需人工介入。
- **Doze 免疫**：通过本地 FIFO 命名管道接收触发信号，完全绕过 TCP/IP 栈与 Android Doze 网络冻结。
- **资源安全**：Shell 子进程独立进程组隔离，超时清理绝不误杀父进程。
- **有界资源**：写入队列有界、内存可控，防止高并发场景下的 OOM。
- **状态可恢复**：原子快照 + 校验和，确保重启后状态一致。

### 2.2 设计哲学

| 原则 | 说明 |
| :--- | :--- |
| **Termux First** | 核心逻辑全部运行在 Termux 中，依赖 termux-services (runit) 保活 |
| **事件驱动** | FIFO 管道为主通道，HTTP 为备选通道 |
| **单写者存储** | SQLite 单写者队列消除锁冲突，独立连接只读不阻塞 |
| **进程组隔离** | 所有 Shell 执行 `start_new_session=True`，超时 `killpg` |
| **优雅退出** | 组件逆序停止 → 取消残留 Task → 关闭事件循环 |

---

## 三、系统架构图与组件划分

### 3.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Android 系统层                                  │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Termux:Boot（开机自启）→ 加载环境 → 启动 termux-services      │   │
│  └─────────────────────────────────┬───────────────────────────────┘   │
│                                    ▼                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  termux-services（runit 守护进程管理器）                        │   │
│  │  ┌───────────────────────────────────────────────────────────┐ │   │
│  │  │  服务: atlas-runtime (Python 3.11+)                      │ │   │
│  │  │  启动: source /etc/profile → termux-wake-unlock          │ │   │
│  │  │       → termux-wake-lock → exec python3 app.py           │ │   │
│  │  │  特性: 崩溃自动重启（即时）、开机自启                     │ │   │
│  │  └───────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────┬───────────────────────────────┘   │
│                                    ▼                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │              Atlas Python Runtime（微内核）                     │   │
│  │  ┌───────────────────────────────────────────────────────────┐ │   │
│  │  │  runtime/app.py (入口+信号)                               │ │   │
│  │  │  transport/trigger_server.py (FIFO主+HTTP备)             │ │   │
│  │  └───────────────────────────────────────────────────────────┘ │   │
│  │  ┌───────────────────────────────────────────────────────────┐ │   │
│  │  │  core/bootstrap.py (编排)                                │ │   │
│  │  │  core/scheduler.py (双队列)                              │ │   │
│  │  │  core/state_manager.py (状态+快照)                       │ │   │
│  │  │  core/resource_lock.py (持久化锁)                        │ │   │
│  │  │  core/trigger_handler.py (背压+死信)                     │ │   │
│  │  └───────────────────────────────────────────────────────────┘ │   │
│  │  ┌───────────────────────────────────────────────────────────┐ │   │
│  │  │  storage/driver.py (单写者SQLite)                        │ │   │
│  │  │  storage/snapshot.py (原子快照)                          │ │   │
│  │  │  storage/rotator.py (轮转归档)                           │ │   │
│  │  │  storage/battery_aware.py (电量感知Checkpoint)           │ │   │
│  │  └───────────────────────────────────────────────────────────┘ │   │
│  │  ┌───────────────────────────────────────────────────────────┐ │   │
│  │  │  executors/shell_executor.py (隔离执行)                  │ │   │
│  │  │  executors/ui_automation.py (UI自动化)                   │ │   │
│  │  │  executors/high_privilege.py (SIM/WiFi/音量)             │ │   │
│  │  └───────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                    │                                   │
│  ┌─────────────────────────────────┼───────────────────────────────┐   │
│  │                                 ▼                               │   │
│  │  ┌───────────────────────────────────────────────────────────┐ │   │
│  │  │  执行通道（按优先级）                                     │ │   │
│  │  │  • [首选] Termux Shell（input / service call / settings）│ │   │
│  │  │  • [备选] Auto.js6（复杂UI交互）                        │ │   │
│  │  └───────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Tasker（轻量触发器）                                           │   │
│  │  • 监听系统事件（时间、通知、电量等）                           │   │
│  │  • 通过 Termux:Tasker 插件执行: trigger_atlas '{"trigger":..}' │   │
│  │  • 完全绕过 TCP/IP 栈，免疫 Doze 网络冻结                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 组件划分与定位矩阵

| 组件 | 层级 | 定位 | 是否必须 | 常驻内存 | 通信方式 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `runtime/app.py` | 入口 | 主循环 + 信号处理 + 优雅关闭 | ✅ | 是 | — |
| `transport/` | 通信 | 双模触发器（FIFO 主 + HTTP 备） | ✅ | 是 | FIFO / HTTP |
| `core/` | 微内核 | 调度、状态、锁、触发处理 | ✅ | 是 | 内部 API |
| `storage/` | 存储 | 单写者 SQLite + 快照 + 轮转 | ✅ | 是 | 内部 API |
| `executors/` | 执行 | Shell / UI / 高权限操作 | ✅ | 是 | 内部 API |
| Tasker | 外部 | 轻量事件触发器 | ✅ 推荐 | 是（极低） | FIFO（主）/ HTTP（备） |
| Auto.js6 | 外部 | 复杂 UI 备选执行器 | ❌ 可选 | 否 | HTTP / UDS |

---

## 四、模块职责、接口与交互

### 4.1 `runtime/app.py` — 主入口与生命周期管理

**职责**：
- 加载 YAML 配置，编排 Bootstrap 启动顺序
- 注册信号处理器（`SIGTERM` / `SIGINT`）
- 维护 `_is_stopping` 幂等标志，执行优雅关闭
- 逆序停止组件 → 取消残留 Task → 关闭事件循环

**关键接口**：

```python
class AtlasRuntime:
    async def start() -> None
    async def stop() -> None          # 幂等，_is_stopping 防重入
    def _setup_signal_handlers() -> None
    def get_all_components() -> List[Any]
```

**优雅关闭顺序**（由 `bootstrap.get_all_components()` 提供，reverse 启动顺序）：

```
battery_aware → rotator → trigger_server → scheduler → resource_lock
→ state_manager → storage
```

（`executor`、`snapshot`、`trigger_handler` 无持久状态与 `stop()`，不在闭顺序中。）

### 4.2 `core/bootstrap.py` — 启动编排

**职责**：按依赖拓扑顺序实例化并启动所有组件，导出 `components` 字典与 `_component_order`。

**启动顺序**：

```
1. ConfigLoader (yaml)
2. SnapshotManager (无状态)
3. SingleWriterStorage (SQLite 单写者)
4. MemoryController (v9.1: 被动探测 + 两级门控 + 防抖)
5. CircuitBreaker (v9.1: 三态模型 + 无锁设计)
6. DedupFilter (v9.1: TTL 窗口 + 惰性清理)
7. StateManager (依赖 storage)
8. SafeShellExecutor (无状态)
9. ResourceLock (依赖 storage)
10. Scheduler (依赖 storage, resource_lock, executor, memory_controller, circuit_breaker, dedup_filter)
11. ResultCallback (v9.1: 注册到 scheduler.on_task_complete)
12. AutoJS6Launcher (v9.1: 注入 executor)
13. TriggerHandler (依赖 scheduler, storage)
14. Rotator (依赖 storage)
15. BatteryAwareCheckpoint (依赖 storage, snapshot)
16. TriggerServer (依赖 trigger_handler, memory_controller, circuit_breaker, dedup_filter)
```

> **v9.1 更新 (2026-08-08)**：新增步骤 4-6（内存门控/熔断/去重）和 11-12（结果回写/AutoJS6 启动器），原步骤编号后移。

**接口**：

```python
class Bootstrap:
    async def bootstrap() -> None
    def get_all_components() -> List[Any]   # 仅含需有序关闭的组件
    components: Dict[str, Any]
```

### 4.3 `core/scheduler.py` — 双队列调度器

**职责**：
- `pending` 队列（FIFO）：待执行任务
- `delay` 队列（按 `scheduled_at` 排序）：延迟 / 重试任务
- 指数退避重试（1s, 2s, 4s），最大 3 次
- 超时后释放资源锁，进入死信

**任务模型**：

```python
@dataclass
class Task:
    id: str
    action: str
    params: Dict[str, Any]
    priority: int = 5
    status: str = "PENDING"
    retry_count: int = 0
    scheduled_at: float = field(default_factory=time.time)
    correlation_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
```

**关键接口**：

```python
class Scheduler:
    async def submit(
        self, action: str, params: Dict, priority: int = 5,
        correlation_id: str = None, delay: float = 0
    ) -> str
    async def _execute_task(self, task: Task) -> None
    async def _safe_on_task_complete(self, task: Task) -> None  # 异常安全回调
    on_task_complete: Optional[Callable[[Task], Awaitable[None]]]
    executor: Callable[[str, float], Awaitable[Any]]   # 注入 SafeShellExecutor.run_command
```

**修复点（见第六节 D-3）**：`on_task_complete` 回调通过 `_safe_on_task_complete` 包裹，`try/except` 捕获并记录异常，避免 fire-and-forget 异常静默丢失。

### 4.4 `core/state_manager.py` — 状态管理

**职责**：
- 内存 `Dict[str, Any]` + 版本号
- `asyncio.Lock` 保护并发
- 深拷贝冻结状态，每 30 秒持久化（由上层调用 `save_state`）
- 启动时读取最新快照恢复

**接口**：

```python
class StateManager:
    async def get(self, key: str, default: Any = None) -> Any
    async def set(self, key: str, value: Any) -> None
    async def update(self, updates: Dict[str, Any]) -> None
    async def save_state(self) -> None          # 委托 SnapshotManager
    async def load_state(self) -> None          # 启动时恢复
    async def stop() -> None
```

### 4.5 `core/resource_lock.py` — 持久化资源锁

**职责**：
- SQLite `resource_locks` 表持久化
- 60 秒租约，支持续约
- 同 owner 可重入
- **CAS 乐观锁**：`UPDATE ... WHERE owner=? AND expires_at>?`，以 `rowcount` 校验避免假成功

**接口**：

```python
class ResourceLock:
    async def acquire(self, resource: str, owner: str, ttl: int = 60) -> bool
    async def release(self, resource: str, owner: str) -> bool
    async def renew(self, resource: str, owner: str, ttl: int = 60) -> bool
    async def cleanup_expired(self) -> int    # 启动时清理孤儿锁
    async def stop() -> None
```

### 4.6 `core/trigger_handler.py` — 背压控制与死信管理

**职责**：
- 将外部触发解析为内部 `Task` 并提交到 Scheduler
- 队列满时抛出 `BackpressureError`（HTTP 返回 429）
- 连续失败任务写死信表

**接口**（含修复后的类型注解）：

```python
class TriggerHandler:
    def __init__(
        self,
        scheduler: "Scheduler",
        storage: "AsyncSQLiteStorage",
        max_retries: int = 3,
    ) -> None

    async def handle(self, data: Dict[str, Any]) -> Dict[str, Any]
    # data 结构: {"action": str, "params": dict, "correlation_id": str, "priority": int}
```

### 4.7 `transport/trigger_server.py` — 双模触发器

**职责**：
- **FIFO 主通道**：`O_RDWR | O_NONBLOCK` 打开，`loop.add_reader` 事件驱动
- **HTTP 备通道**：aiohttp，`reuse_address=True`，端口冲突安全处理
- `asyncio.Semaphore(max_concurrent_tasks)` 限流（默认 100）
- 背压模式下安全丢弃缓冲行，防止内存无限增长

**修复点（见第六节 D-1、D-2）**：
- 背压分支解析 `\n` 并计入 `_backlog_count`，64KB 缓冲上限截断
- 使用显式 `_active_task_count` 替代 `Semaphore._value` 私有属性

**接口**：

```python
class TriggerServer:
    async def start() -> None
    async def stop() -> None
    async def trigger_handler(self, data: Dict[str, Any]) -> Dict[str, Any]
    # HTTP 端点：POST /trigger, GET /health, GET /ready
```

**HTTP 响应协议**：

| 端点 | 成功 | 背压 | 错误 |
| :--- | :--- | :--- | :--- |
| `POST /trigger` | `200 {"status":"ok","result":...}` | `429 {"status":"error",...}` | `400/500` |
| `GET /health` | `200 {"status":"healthy","concurrent_tasks":N,...}` | — | — |
| `GET /ready` | `200 {"status":"ready"}` | — | — |

### 4.8 `storage/` — 存储层

#### 4.8.1 `driver.py` — 单写者队列 SQLite 驱动

**职责**：
- `asyncio.Queue(maxsize=1000)` 有界写入队列
- 单 Worker 批量提交（`batch_size=100`, `batch_delay=50ms`）
- 独立连接并发读取，不阻塞写入
- 哨兵（`_SENTINEL`）平滑退出
- WAL：`synchronous=NORMAL`, `wal_autocheckpoint=1000`

**接口**：

```python
class SingleWriterStorage:
    async def start() -> None
    async def execute_write(self, sql: str, params: Tuple = ()) -> Any
    # 返回值按 SQL 类型区分: INSERT→lastrowid, UPDATE/DELETE→rowcount, 其他→True
    async def execute_write_many(self, sql: str, params_list: List) -> int
    async def execute_read(self, sql: str, params: Tuple = ()) -> List[Tuple]
    async def checkpoint(self, full: bool = False) -> None
    async def vacuum(self) -> None
    async def set_readonly_mode(self, enabled: bool) -> None
    async def get_disk_usage(self) -> Dict[str, int]
    async def stop() -> None
```

#### 4.8.2 `snapshot.py` — 原子快照

**职责**：
- 写入：临时文件 → `os.replace()` → SHA256 校验和
- 读取：校验和验证 → 反序列化 MessagePack
- 电池模式：延迟写入（≤ 60 秒），减少 I/O 唤醒
- `_pending_write_task` 跟踪，确保关机前完成

**接口**：

```python
class SnapshotManager:
    def __init__(self, snapshot_dir: str) -> None
    async def save(self, data: Any) -> bool
    async def load(self) -> Optional[Any]
    async def _do_save(self, data: Any) -> None
```

#### 4.8.3 `rotator.py` — 自动轮转归档

**职责**：
- 保留最多 `max_events`（10,000）行
- 归档格式：`events_{timestamp}.json.gz`
- 启动时 + 每 `rotate_interval_hours`（6h）检查
- 使用 `BEGIN IMMEDIATE` + `RETURNING` 保证归档与删除等价

**接口**：

```python
class Rotator:
    async def start() -> None
    async def stop() -> None
    async def rotate(self) -> bool
```

#### 4.8.4 `battery_aware.py` — 电量感知 Checkpoint

**职责**：
- 定时（`battery_check_interval`，30s）检查电量
- 低电量时延迟快照写入，减少电池消耗
- 支持外部 `HealthChecker` 插件（`set_health_checker`）

**接口**：

```python
class BatteryAwareCheckpoint:
    def __init__(self, storage, snapshot_manager, check_interval: int = 30) -> None
    async def start() -> None
    async def stop() -> None
    def set_health_checker(self, checker: Callable[[], Awaitable[bool]]) -> None
```

### 4.9 `executors/` — 执行器层

#### 4.9.1 `shell_executor.py`（规范实现）

**职责**：
- `start_new_session=True` 独立进程组
- 超时 `os.killpg(SIGKILL)` 安全清理
- 关闭 stdout/stderr 管道避免阻塞

**接口**：

```python
class SafeShellExecutor:
    def __init__(self, default_timeout: float = 5.0) -> None
    async def run_command(self, cmd: str, timeout: float = None) -> Tuple[int, str, str]
    # 返回 (returncode, stdout, stderr)
```

> **兼容性说明**：`core/shell_executor.py` 为兼容性存根，内容与本文件相同，新代码应从 `executors.shell_executor` 导入。

#### 4.9.2 `ui_automation.py` — UI 自动化

**接口**：

```python
class UIAutomationExecutor:
    def __init__(self, shell_executor: Optional[SafeShellExecutor] = None) -> None
    async def click(self, x, y, timeout=5.0) -> Dict[str, Any]
    async def swipe(self, x1, y1, x2, y2, duration_ms=300, timeout=5.0) -> Dict[str, Any]
    async def get_ui_tree(self, timeout=5.0) -> Dict[str, Any]
    async def press_back(self, timeout=2.0) -> Dict[str, Any]
    async def press_home(self, timeout=2.0) -> Dict[str, Any]
    async def press_recent(self, timeout=2.0) -> Dict[str, Any]
```

#### 4.9.3 `high_privilege.py` — 高权限操作

**接口**（含修复后的 SIM 切换语义，见第六节 D-5）：

```python
class HighPrivilegeExecutor:
    async def switch_sim(self, sim_id: int, timeout=5.0) -> Dict[str, Any]
    async def set_wifi_enabled(self, enabled: bool, timeout=3.0) -> Dict[str, Any]
    async def set_volume(self, stream: str, level: int, timeout=2.0) -> Dict[str, Any]
    async def get_sim_state(self, timeout=3.0) -> Dict[str, Any]
    async def check_state(self, resource: str, target: Any, timeout=3.0) -> bool
```

---

## 五、数据流与任务状态机

### 5.1 端到端触发数据流

```
[Tasker / HTTP 客户端]
        │
        ▼  (FIFO 管道 或 HTTP POST /trigger)
[transport/trigger_server.py]
        │  _process_line_with_semaphore (Semaphore 限流)
        ▼
[core/trigger_handler.py]
        │  handle() → 解析 → 提交 Task
        ▼  (BackpressureError → HTTP 429)
[core/scheduler.py]
        │  submit() → pending / delay 队列
        ▼
[core/scheduler._execute_task]
        │  1. ResourceLock.acquire()
        │  2. executor.run_command(cmd, timeout)
        │  3. on_task_complete (异常安全)
        │  4. ResourceLock.release()
        ▼
[executors/*] → Android Shell (input / svc / service call)
        │
        ▼
[storage/*] → 事件落库 / 状态快照 / 死信
```

### 5.2 任务状态机

```
PENDING → SCHEDULED → EXECUTING → SUCCESS
                                → TIMEOUT → RETRY（最多3次，指数退避 1/2/4s）
                                → FAILED → RETRY → DEAD（写死信 dead_letters 表）
```

### 5.3 故障自愈链路

| 故障场景 | 检测方式 | 恢复动作 |
| :--- | :--- | :--- |
| Runtime 进程崩溃 | runit 监控 PID | 即时重启（< 2 秒） |
| HTTP 端口冲突 | OSError 捕获 | 日志提示 `fuser -k {port}/tcp` |
| Shell 命令超时 | `asyncio.wait_for(5s)` | `killpg` → 重试 |
| SQLite 队列满 | `asyncio.QueueFull` | 背压退避 → HTTP 429 |
| 存储空间不足 | `get_disk_usage` 预检 | `set_readonly_mode(True)` |
| FIFO 管道阻塞 | `O_RDWR \| O_NONBLOCK` | `open` 永不阻塞 |
| 孤儿锁残留 | 启动时 `cleanup_expired` | 删除 `expires_at <= now` |
| **FIFO 高并发积压** | `_backlog_count` 计数 | **64KB 缓冲上限截断（修复 D-1）** |
| **信号无 add_signal_handler** | `NotImplementedError` | **事件标志 + 轮询回退（修复 D-4）** |

---

## 六、已修复设计缺陷（核心章节）

> 每项缺陷按 **问题描述 → 修复方案 → 影响范围** 三段式描述。

### D-0（P0）：`executors/` 四文件含 Shell heredoc 包装器

| 项 | 内容 |
| :--- | :--- |
| **问题描述** | `executors/__init__.py`、`shell_executor.py`、`ui_automation.py`、`high_privilege.py` 首行包含 `cat > ... << 'EOF'` 及末尾 `EOF` 残留。Python 解释器抛出 `SyntaxError`，导致 `bootstrap.py` 的 `from executors.shell_executor import SafeShellExecutor` 失败，**整个 Runtime 无法启动**。根因为部署流水线将 heredoc 内容误写入目标文件而非执行。 |
| **修复方案** | 剥离四个文件的 `cat > ... << 'EOF'` / `EOF` / `mkdir -p executors` 包装器，仅保留纯 Python 代码。同时为 `core/shell_executor.py` 与 `executors/shell_executor.py` 添加清晰的兼容性注释。 |
| **影响范围** | **阻断性修复**。修复前系统 100% 无法运行；修复后核心引擎启动正常。无 API 变更，无数据格式变更。 |

### D-1（P1）：FIFO 背压模式下缓冲数据不处理换行符 → 内存泄漏

| 项 | 内容 |
| :--- | :--- |
| **问题描述** | `transport/trigger_server.py` 的 `_on_fifo_readable` 在 `self._semaphore.locked()`（并发满）时，将 FIFO 数据追加到 `self._read_buffer` 但**从不解析 `\n` 分隔符来触发处理**。这些缓冲数据会无限累积在内存中，构成内存泄漏。 |
| **修复方案** | 背压分支中同样解析 `\n`，将完整行计入 `_backlog_count`；并添加 64KB 缓冲区上限截断保护（`len(self._read_buffer) > 65536` 时强制清空并 `logger.critical`）。正常路径逻辑不变。 |
| **影响范围** | 影响高并发 FIFO 触发场景（> 100 并发）下的内存稳定性。修复后内存有界，背压超限时安全丢弃并计数。仅修改 `trigger_server.py` 内部逻辑，无接口变更。 |

### D-2（P1）：`Semaphore._value` 私有属性访问 → 跨实现兼容性

| 项 | 内容 |
| :--- | :--- |
| **问题描述** | `_handle_health` 端点使用 `self.max_concurrent_tasks - self._semaphore._value` 计算并发任务数。`_value` 是 CPython 内部属性，在 PyPy / GraalPy 等替代实现上不存在，会导致健康检查接口 500。 |
| **修复方案** | 新增显式计数器 `self._active_task_count`，在 `_process_line_with_semaphore` 的 `try/finally` 中原子增减；健康检查端点改用 `self._active_task_count` 与 `self.max_concurrent_tasks`。 |
| **影响范围** | 提升运行时可移植性。仅 `trigger_server.py` 内部变更，HTTP `/health` 响应字段名保持兼容（`concurrent_tasks` 仍存在）。 |

### D-3（P1）：`Scheduler.on_task_complete` fire-and-forget → 异常静默丢失

| 项 | 内容 |
| :--- | :--- |
| **问题描述** | `core/scheduler.py` 的 `_execute_task` 在 `finally` 中调用 `asyncio.create_task(self.on_task_complete(task))`，但回调协程若抛出异常，异常会丢失且无法被任何地方捕获，导致状态持久化等后续逻辑静默失败。 |
| **修复方案** | 新增 `_safe_on_task_complete(task)` 方法，`try/except` 捕获并记录 `logger.error(exc_info=True)`；原 `create_task` 改为调用该安全包装。 |
| **影响范围** | 提升调度器可观测性。仅 `scheduler.py` 内部变更，回调契约（`on_task_complete: Callable[[Task], Awaitable[None]]`）不变。 |

### D-4（P1）：Signal 回退方案在无事件循环时崩溃

| 项 | 内容 |
| :--- | :--- |
| **问题描述** | `runtime/app.py` 在 `add_signal_handler` 抛 `NotImplementedError` 时回退到 `signal.signal(sig, lambda s, f: asyncio.create_task(self.stop()))`。信号回调在信号上下文运行，`asyncio.create_task` 可能因无运行中的事件循环而失败，导致关机信号丢失。 |
| **修复方案** | 回退方案改为直接 `self._shutdown_event.set()`（信号安全）；`start()` 中 `_shutdown_event.wait()` 返回后检测 `_is_stopping` 标志，若未停则显式调用 `self.stop()`。并将 `loop` 引用保存到 `self._loop`。 |
| **影响范围** | 增强在非常规 Python 构建（无 `add_signal_handler`）下的关机可靠性。仅 `app.py` 变更，对外信号行为（`SIGTERM`/`SIGINT` → 优雅关闭）不变。 |

### D-5（P1）：`HighPrivilegeExecutor.switch_sim` 备用命令语义错误

| 项 | 内容 |
| :--- | :--- |
| **问题描述** | 原备用命令 `settings put global preferred_network_mode {sim_id}` 设置的是**首选网络类型**（如 LTE/WCDMA 枚举值），而非切换默认数据 SIM 卡。语义错误可能导致误判 SIM 切换成功或执行无效操作。 |
| **修复方案** | 备用命令改为 `settings put global multi_sim_data_call {sim_id + 1}`（控制数据 SIM 槽位）；两种方法均失败时返回明确失败结果（`"success": False, "error": ...`）而非假成功。两种命令均标注 OEM / Android 版本差异警告。 |
| **影响范围** | 影响 SIM 切换功能的准确性（高危操作）。仅 `high_privilege.py` 逻辑变更，接口签名不变。需在目标设备验证实际可用命令。 |

### D-6（P2）：`trigger_handler.py` 缺少类型注解

| 项 | 内容 |
| :--- | :--- |
| **问题描述** | `__init__(self, scheduler, storage, max_retries=3)` 参数无类型注解，降低静态分析能力与可维护性。 |
| **修复方案** | 引入 `TYPE_CHECKING` 条件导入，添加 `scheduler: "Scheduler"`、`storage: "AsyncSQLiteStorage"`、`max_retries: int = 3` 注解与 `-> None` 返回注解。 |
| **影响范围** | 纯静态分析改进，无运行时影响。 |

### D-7（P2）：`Bootstrap` 未说明组件闭顺序排除项

| 项 | 内容 |
| :--- | :--- |
| **问题描述** | `executor`、`snapshot`、`trigger_handler` 未在 `_component_order` 中，代码无注释说明原因，易误导后续维护者。 |
| **修复方案** | 在三个组件的创建处及 `get_all_components()` 的 docstring 中明确注释："无状态、无 stop() 方法，不加入 `_component_order`"。 |
| **影响范围** | 文档性修复，无运行时影响。 |

### D-8（P2）：`docs/ARCHITECTURE.md` 存根 + `README.md` 特性缺失

| 项 | 内容 |
| :--- | :--- |
| **问题描述** | `docs/ARCHITECTURE.md` 仅 4 行存根（356 字节），与"架构设计文档"定位不符；`README.md` 核心特性缺少"原子快照"。 |
| **修复方案** | 扩展 `ARCHITECTURE.md` 为完整架构索引（模块分层图、状态机、故障自愈表、部署脚本表）；`README.md` 补充第 5 条特性"原子快照：深拷贝冻结状态 + SHA256 校验"。 |
| **影响范围** | 文档质量提升，无代码影响。 |

---

## 七、数据库结构

### 7.1 表结构（WAL 模式）

```sql
-- 事件表（审计 / 触发记录）
CREATE TABLE events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id    TEXT NOT NULL,
    source      TEXT NOT NULL,
    type        TEXT NOT NULL,
    payload     BLOB,
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX idx_events_trace    ON events(trace_id);
CREATE INDEX idx_events_created  ON events(created_at);

-- 状态表（Key-Value + 版本号）
CREATE TABLE state (
    key         TEXT PRIMARY KEY,
    value       BLOB,
    version     INTEGER DEFAULT 1,
    updated_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

-- 资源锁表（持久化互斥锁）
CREATE TABLE resource_locks (
    resource    TEXT PRIMARY KEY,
    owner       TEXT NOT NULL,
    acquired_at INTEGER NOT NULL,
    expires_at  INTEGER NOT NULL
);

-- 快照表（单例，id 固定为 1）
CREATE TABLE snapshot (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    data        BLOB NOT NULL,
    checksum    TEXT NOT NULL,
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

-- 死信表（最终失败任务）
CREATE TABLE dead_letters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_data   BLOB NOT NULL,
    error       TEXT,
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
```

### 7.2 数据库结构变更说明（本版）

| 变更 | 说明 | 兼容性 |
| :--- | :--- | :--- |
| `execute_write` 返回值语义（补丁 B） | `INSERT→lastrowid`, `UPDATE/DELETE→rowcount`, 其他→`True` | 内部约定，无需迁移 |
| `snapshot` 表 `CHECK (id = 1)` | 保证单例快照，避免多行冲突 | 新建表，无历史数据 |
| `resource_locks` 租约模型 | `expires_at` 字段支持 CAS 乐观锁 | 新建表，无历史数据 |

> **无破坏性迁移**：所有表通过 `CREATE TABLE IF NOT EXISTS` 创建，已部署实例重启后自动补全缺失表，无需手动迁移脚本。

### 7.3 写入语义约定

`SingleWriterStorage.execute_write` 的返回值按 SQL 前缀区分：

| SQL 前缀 | 返回 |
| :--- | :--- |
| `INSERT` | `cursor.lastrowid` |
| `UPDATE` / `DELETE` / `REPLACE` | `cursor.rowcount` |
| `PRAGMA` / `BEGIN` / `COMMIT` 等 | `True` |

调用方（如 `ResourceLock` 的 CAS 校验）依赖 `rowcount` 判断更新是否生效，避免假成功。

---

## 八、修复后的接口协议

### 8.1 触发协议（FIFO / HTTP 统一）

**入站消息格式**（JSON，单行 `\n` 分隔）：

```json
{
  "action": "sim_switch",
  "params": { "sim_id": 1 },
  "correlation_id": "uuid-optional",
  "priority": 5
}
```

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `action` | string | ✅ | 任务动作标识，映射到 `Scheduler` 执行逻辑 |
| `params` | object | ❌ | 动作参数，透传至执行器 |
| `correlation_id` | string | ❌ | 关联追踪 ID，写入 `events.trace_id` |
| `priority` | int | ❌ | 调度优先级，默认 5 |

**FIFO 写入约定**（Tasker 侧）：

```bash
echo '{"action":"sim_switch","params":{"sim_id":1}}' > $PREFIX/tmp/atlas_trigger.fifo
# 必须使用 O_RDWR|O_NONBLOCK 打开，避免 writer 阻塞
```

**HTTP 触发**：

```bash
curl -X POST http://127.0.0.1:8787/trigger \
  -H "Content-Type: application/json" \
  -d '{"action":"test"}'
```

### 8.2 HTTP API 协议（修复后）

| 端点 | 方法 | 请求 | 成功响应 | 错误响应 |
| :--- | :--- | :--- | :--- | :--- |
| `/trigger` | POST | JSON 触发消息 | `200 {"status":"ok","result":{...}}` | `429` 背压 / `400` 非法 JSON / `500` 内部 |
| `/health` | GET | — | `200 {"status":"healthy","fifo":bool,"fifo_fd":bool,"concurrent_tasks":int,"max_concurrent":int,"backlog":int}` | — |
| `/ready` | GET | — | `200 {"status":"ready"}` | — |

> **变更点**：`/health` 的 `concurrent_tasks` 字段现由 `_active_task_count` 显式计数器提供（修复 D-2），不再依赖私有属性。

### 8.3 配置协议（`config/runtime.yaml`）

```yaml
runtime:
  log_level: INFO
  snapshot_interval: 30        # 状态持久化间隔（秒）
  command_timeout: 5
  circuit_breaker_threshold: 5 # 预留：CircuitBreaker（待实现，见第九节）
  dedup_ttl: 60                # 预留：Dedup（待实现，见第九节）
  max_pending: 5000

storage:
  db_path: /data/data/com.termux/files/home/atlas-runtime/data/atlas.db
  busy_timeout: 5000
  snapshot_dir: data/snapshots
  max_events: 10000
  rotate_interval_hours: 6
  battery_check_interval: 30

memory:                        # 预留：MemoryController（待实现，见第九节）
  soft_limit_mb: 150
  hard_limit_mb: 200

transport:
  fifo_path: /data/data/com.termux/files/usr/tmp/atlas_trigger.fifo
  http_port: 8787

executors:
  shell_timeout: 5
  ui_timeout: 5
```

---

## 九、已实现差距项与后续任务

以下配置项已在 `runtime.yaml` 中预留，各模块已于 **v9.1 (2026-08-08)** 全部实现并通过 55 项专项测试：

| 模块 | 配置关联 | 状态 | 实现说明 |
| :--- | :--- | :--- | :--- |
| **MemoryController** | `memory.soft_limit_mb`, `hard_limit_mb` | ✅ v9.1 已实现 | 被动探测 + 两级门控（SOFT_THROTTLE/HARD_REJECT）+ 防抖切换 |
| **CircuitBreaker** | `circuit_breaker_threshold: 5` | ✅ v9.1 已实现 | 三态模型（CLOSED/OPEN/HALF_OPEN）+ 无锁原子设计 |
| **DedupFilter** | `dedup_ttl: 60` | ✅ v9.1 已实现 | TTL 窗口去重 + 惰性清理（容量 80% 触发） |

**集成状态（v9.1 — 2026-08-08）**：
- ResultCallback：已实现并接入 bootstrap 启动链路，注册到 `scheduler.on_task_complete`
- AutoJS6Launcher：已实现并接入 bootstrap 启动链路，注入 executor

**后续任务**：
- Tasker 集成：安装 Termux:Tasker → 配置 `trigger_atlas` → 验证触发链路
- Auto.js6 集成：安装 APK → 开启无障碍 → 验证 UI 操作
- 端到端测试：SIM 切换 / UI 点击 / 状态查询 / 崩溃重启 / 快照恢复

---

## 十、设计约束与假设条件

### 10.1 设计约束

1. **Android 平台约束**：仅支持 Android 7+（Nougat），依赖 `input`、`svc`、`service call` 等系统命令可用性。
2. **Termux 环境约束**：必须在 Termux 中运行，`$PREFIX` 为标准 Termux 路径；`termux-services` 必须已安装。
3. **Python 版本约束**：Python 3.11+（实际部署 3.14.6），使用 `asyncio.create_subprocess_shell`、`loop.add_signal_handler` 等特性。
4. **单实例约束**：Runtime 为单进程单写者模型，不支持多实例并发写同一 SQLite。
5. **无 C 扩展约束**：纯 Python 实现，零 C 扩展（避免 Android 编译失败，见修复记录 `psutil` 用预编译包）。
6. **FIFO 非持久约束**：FIFO 管道不持久化消息，Runtime 未运行时写入的消息会丢失（设计上由 Tasker 重试或 HTTP 备通道补充）。

### 10.2 假设条件

| 假设 | 影响 |
| :--- | :--- |
| Termux 拥有足够权限执行 `input` / `svc` 等命令 | 高权限操作依赖已 root 或已授权 `adb shell` 的 Termux |
| `psutil` 已通过 `pkg install python-psutil` 预编译安装 | MemoryController 实现依赖此包 |
| 设备支持双 SIM（`multi_sim_data_call` 属性存在） | `switch_sim` 仅在双卡设备有效 |
| `uiautomator` 二进制可用 | `get_ui_tree` 依赖此命令 |
| Android Doze 不限制本地 Unix 域 socket / FIFO | FIFO 主通道的 Doze 免疫假设成立 |
| runit 重启延迟 < 2 秒 | 故障自愈 SLA 的前提 |

### 10.3 安全假设

- FIFO 路径位于 Termux 私有 `$PREFIX/tmp`，其他应用不可写
- HTTP 端口仅监听 `127.0.0.1`（loopback），不暴露到外部网络
- 所有 Shell 命令由内部代码构造，不接受外部原始命令拼接（防命令注入）

---

## 十一、修复验证摘要

| 级别 | 修复项 | 验证方式 |
| :--- | :--- | :--- |
| P0 | D-0 executors heredoc | 导入测试通过，无 `SyntaxError` |
| P1 | D-1 FIFO 内存泄漏 | 64KB 截断 + 背压计数逻辑审查 |
| P1 | D-2 Semaphore 私有属性 | `_active_task_count` 替代，跨实现安全 |
| P1 | D-3 on_task_complete 异常 | `_safe_on_task_complete` 包裹 |
| P1 | D-4 Signal 回退 | 事件标志 + 轮询回退 |
| P1 | D-5 switch_sim 语义 | 命令更正 + 失败显式返回 |
| P2 | D-6 类型注解 | 静态检查通过 |
| P2 | D-7 Bootstrap 注释 | 代码审查 |
| P2 | D-8 文档缺失 | 文档补全 |

**Lint 状态**：所有修改文件 `read_lints` 零错误。

---

> **文档状态**：✅ 最新版，反映 v8.0 LTS 修复后状态  
> **维护者**：Atlas Architecture Group  
> **最后更新**：2026-08-02
