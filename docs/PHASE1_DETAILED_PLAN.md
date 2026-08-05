# Atlas Runtime v8.0 — 第一阶段（生产加固）详细实施计划

> 制定日期：2026-08-05
> 基准文档：docs/IMPLEMENTATION_PLAN.md, docs/PROGRESS_REPORT.md
> 阶段范围：第 1-2 周（里程碑 M1：2026-08-19）
> 核心目标：在引入外部触发器之前，先建立核心引擎的内存安全护栏

---

## 一、第一阶段目标总览

第一阶段的使命可以用一句话概括：**让 Atlas Runtime 在 Termux 内存受限环境中具备自我感知和自我约束能力**。

当前核心引擎（scheduler、trigger_server、state_manager、resource_lock、storage 等）已经全部实现并通过 mock 测试，但缺失一个关键的内生防御机制——MemoryController。`config/runtime.yaml` 中 `memory.soft_limit_mb: 150` 和 `memory.hard_limit_mb: 200` 已配置，但没有任何代码使用它们。这意味着当 Termux 进程因内存压力被 Samsung One UI 的激进进程回收策略杀死时，Atlas 将没有任何预警和反抗机会。

MemoryController 的设计必须严格遵循 Atlas 的五大设计原则：不影响现有组件的高可用性（runit 守护不变），不破坏资源安全（持锁不变），遵循有界资源原则（背压不变），支持状态可恢复（快照中记录内存事件），以及不增加功耗开销（被动检查而非主动轮询）。

---

## 二、任务分解

第一阶段共有 5 个子任务，严格按依赖顺序排列：

| 任务编号 | 任务名称 | 预估人天 | 前置依赖 | 交付物 |
|:---|:---|:---|:---|:---|
| T1.1 | MemoryController 核心模块实现 | 1.5 天 | 无 | `core/memory_controller.py` |
| T1.2 | 组件集成点改造 | 1.0 天 | T1.1 | 修改 `bootstrap.py`, `scheduler.py`, `trigger_server.py`, `app.py` |
| T1.3 | 单元测试 | 0.5 天 | T1.1 | `tests/test_memory_controller.py` |
| T1.4 | 回归测试 + 集成验证 | 0.5 天 | T1.2, T1.3 | 全部 16 项测试通过 |
| T1.5 | 阶段评估 + 调整 | 0.5 天 | T1.4 | 评估报告 + 第二阶段调整建议 |

**总人天：4.0 天**（从 IMPLEMENTATION_PLAN.md 预留的 5 天缩减至 4 天）

---

## 三、各任务详细设计

### T1.1：MemoryController 核心模块实现（1.5 天）

#### 模块定位

`core/memory_controller.py` 是一个**被动门控组件**，只在被询问时才评估内存状态。它不启动后台循环，不进行主动轮询，因此对 CPU 零占用、对电池零消耗。其他组件在关键决策点调用它的 `can_accept()` 方法获取当前门控状态。

#### 三级内存探测策略（与 HealthChecker 设计一致）

```
psutil.Process().memory_info().rss (优先)
  → /proc/self/status VmRSS (回退)
    → platform.total_ram_mb / 2 估计 (最终兜底)
```

psutil 在 Termux 中需要 `pkg install python-psutil`，如果未安装或导入失败，`/proc/self/status` 的 VmRSS 字段提供相同信息。如果 `/proc` 也读不了（极端情况），使用 PlatformInfo 探测到的总内存的一半作为估算值，配置警告但系统继续运行——这是"优雅降级"的核心。

#### 三种门控状态

| 状态 | 条件 | 行为 |
|:---|:---|:---|
| `ACCEPT` (绿灯) | RSS < soft_limit | 所有操作正常 |
| `SOFT_THROTTLE` (黄灯) | soft_limit <= RSS < hard_limit | 日志告警，scheduler 拒绝新任务提交，trigger_server HTTP 返回 429，但已入队任务继续执行 |
| `HARD_REJECT` (红灯) | RSS >= hard_limit | 在上述基础上额外触发 `gc.collect()`，并拒绝所有写操作（包括 FIFO 缓冲清空） |

状态转换有防抖机制：必须连续 3 次检查结果相同才真正切换状态，避免因瞬时 GC 波动导致状态抖动。

#### 关键 API

```python
class MemoryController:
    def __init__(self, soft_limit_mb, hard_limit_mb, check_stability=3)
    async def can_accept(self) -> MemoryGate
    async def current_rss_mb(self) -> int
    async def stats(self) -> MemoryStats
    def on_state_change(self, callback: Callable)
```

`can_accept()` 是同步方法，在 `asyncio.to_thread()` 或 `loop.run_in_executor()` 中运行探测逻辑，避免阻塞事件循环。

#### 数据结构

```python
@dataclass
class MemoryGate:
    state: GateState  # ACCEPT / SOFT_THROTTLE / HARD_REJECT
    rss_mb: int
    soft_limit_mb: int
    hard_limit_mb: int
    reason: str       # 人类可读的状态描述

@dataclass  
class MemoryStats:
    current_rss_mb: int
    peak_rss_mb: int      # 进程历史峰值
    state_history: list   # 最近 10 次状态变化记录
    rejection_count: int  # 累计拒绝次数
```

#### 异常安全

如果 MemoryController 自身的探测方法抛出异常（如 `/proc/self/status` 被 selinux 阻止），`can_accept()` 不会向上传播异常，而是返回 `ACCEPT` 状态并记录错误日志。这一设计遵循"宁可放行也不阻塞"的保守策略，确保 MemoryController 的故障不会导致系统完全不可用。

---

### T1.2：组件集成点改造（1.0 天）

MemoryController 需要在以下四个位置接入：

#### 集成点 A：Bootstrap 启动编排

在 `core/bootstrap.py` 的 `boot()` 方法中，在 Storage（步骤 1）之后、Scheduler（步骤 6）之前初始化和启动 MemoryController：

```
1. Storage
+  MemoryController ← 新增（夹在 1 和 2 之间）
2. SnapshotManager
3. StateManager
...
```

选择这个位置的依据：MemoryController 不依赖任何其他核心组件，仅需要 config 中的 memory 配置段。放在 Storage 之后是因为后续组件（如 Scheduler）在创建时需要传入 MemoryController 引用。它不属于 _component_order 关闭序列（无持久状态、无后台循环、无 stop() 方法），与 ShellExecutor 同级处理。

具体改动：在 `bootstrap.py` 中新增 8 行代码，创建一个 `MemoryController` 实例并保存到 `self.components['memory_controller']`。

#### 集成点 B：Scheduler 提交门控

在 `core/scheduler.py` 的 `submit()` 方法开头插入门控检查。这是所有任务进入系统的唯一入口，也是最关键的集成点。改动只需 6 行：

```python
async def submit(self, action, delay=0.0):
    if self._memory_gate:
        gate = await self._memory_gate.can_accept()
        if gate.state == GateState.HARD_REJECT:
            raise RuntimeError("Memory hard limit reached")
        if gate.state == GateState.SOFT_THROTTLE:
            if self._pending.qsize() >= self.max_pending * 0.5:
                raise RuntimeError("Pending queue congested under memory pressure")
    # ... 原有逻辑
```

需要注意：Scheduler 初始化时接收一个可选的 `memory_controller` 参数（默认为 None），这样现有测试不需要修改——它们创建 Scheduler 时不传此参数，门控逻辑自动跳过。

#### 集成点 C：TriggerServer 背压信号

在 `transport/trigger_server.py` 中：
- HTTP 通道：`_handle_http_trigger()` 方法中，在调用 `trigger_handler` 之前检查 MemoryController 状态。如果 `HARD_REJECT`，返回 HTTP 503（而不是当前的 429）并附带内存压力说明。
- FIFO 通道：`_on_fifo_readable()` 方法中，如果处于 `HARD_REJECT` 状态，将缓冲中的新数据直接丢弃（与当前背压逻辑一致），但附加内存状态日志。

这两处改动都很小，FIFO 侧复用现有的背压丢弃逻辑，HTTP 侧新增一个状态分支。

#### 集成点 D：HealthChecker 内存告警增强

`core/health_checker.py` 已经通过 `/proc/meminfo` 监控系统级内存（`memory.usage_percent`）。MemoryController 与之互补——监控进程级内存（PS RSS）。在 `app.py` 中，将 MemoryController 的状态变化回调注册到 HealthChecker 的订阅机制中。当 MemoryController 从绿灯切到黄灯时，HealthChecker 增加一条进程内存告警。

#### config/runtime.yaml 无需改动

`memory.soft_limit_mb: 150` 和 `memory.hard_limit_mb: 200` 已经存在，MemoryController 直接从 Bootstrap 传入的 config dict 中读取。

---

### T1.3：单元测试（0.5 天）

新增测试文件 `tests/test_memory_controller.py`，覆盖以下场景：

**测试用例矩阵（共 8 项）**：

| 测试用例 | 覆盖目标 | 预期结果 |
|:---|:---|:---|
| `test_init_defaults` | 构造函数参数正确存储 | soft_limit=150, hard_limit=200 |
| `test_can_accept_when_normal` | 模拟低内存（RSS=50MB） | gate.state == ACCEPT |
| `test_can_accept_soft_throttle` | 模拟中等内存（RSS=160MB） | gate.state == SOFT_THROTTLE |
| `test_can_accept_hard_reject` | 模拟高内存（RSS=210MB） | gate.state == HARD_REJECT |
| `test_state_stability` | 内存波动但未达连续 3 次阈值 | 状态不切换（防抖） |
| `test_proc_fallback` | psutil 不可用，回退 /proc/self/status | 仍可探测 RSS |
| `test_full_degradation` | psutil 和 /proc 均不可用 | 返回 ACCEPT，记录错误日志 |
| `test_scheduler_integration` | Scheduler submit 被 HARD_REJECT 阻塞 | 抛出 RuntimeError |

测试实现策略：
- 使用 `unittest.mock.patch` 替换 MemoryController 内部的 `_read_rss()` 方法，注入模拟的 RSS 值，避免依赖真实系统状态。
- `test_scheduler_integration` 创建真实的 Scheduler + MemoryController 组合，验证门控逻辑的端到端行为。
- `conftest.py` 中的 `sample_config_dict` 已经包含 `memory` 段（soft_limit=150, hard_limit=200），无需修改。

---

### T1.4：回归测试 + 集成验证（0.5 天）

本任务确保 MemoryController 的引入不会破坏现有功能。

**执行步骤**：

1. 运行全部 15 个现有测试文件：`python -m pytest tests/ -v`。预期全部通过（MemoryController 在所有集成点都是可选参数，不会影响现有测试的 mock 环境）。

2. 运行新增的 `test_memory_controller.py`：`python -m pytest tests/test_memory_controller.py -v`。预期 8 项全部通过。

3. 验证 Bootstrap 集成：修改 `test_bootstrap.py` 中的测试配置，确认 `memory_controller` 组件出现在 `bootstrap.get_all_components()` 返回的列表之外（即不在关闭序列中，与 SnapshotManager 同级）。

4. 验证 TriggerServer 集成：使用 `test_trigger_server.py` 中的现有 fixture，模拟 MemoryController 返回 HARD_REJECT，确认 HTTP 返回 503 而非 200。

**门禁标准**：全部测试（15 + 1 + 8 = 24 个测试文件中的约 90 个测试用例）必须通过，且无 DeprecationWarning 或 ResourceWarning。

---

### T1.5：阶段评估 + 调整（0.5 天）

在第一阶段结束时执行以下评估流程：

**评估维度**：

1. **工时偏差**：实际工时 vs 计划 4 天。如果偏差超过 20%（0.8 天），分析原因并调整后续阶段估算。

2. **代码质量**：检查新增代码是否遵循项目约定——docstring 完整、类型注解（TYPE_CHECKING 兼容）、日志级别正确（debug/info/warning/error 使用恰当）。

3. **集成风险回顾**：MemoryController 在四个集成点是否有遗漏？是否有需要但未实现的状态暴露接口（如 `/health` 端点中的内存字段）？

4. **测试覆盖缺口**：是否有边界条件未测试（如 `can_accept()` 在 MemoryController 异常时返回什么）？

**产出**：生成一份阶段评估报告（`docs/PHASE1_REVIEW.md`），包含：
- 实际进度与计划的偏差
- 发现的问题及修复情况
- 对第二阶段计划的调整建议（如是否需要增加 MemoryController 的调优参数暴露）
- 当前代码库的健康评分

---

## 四、风险与应急措施

| 风险 | 概率 | 影响 | 缓解措施 |
|:---|:---|:---|:---|
| psutil 在 Termux 上不可用 | 中（40%） | 低 | `/proc/self/status` 回退方案已在设计中，与 psutil 功能等价 |
| Scheduler 集成导致现有测试失败 | 低（15%） | 中 | MemoryController 参数默认为 None，现有 Scheduler 实例化不需要修改 |
| 三星 One UI 限制 /proc 访问 | 低（10%） | 中 | PlatformInfo 兜底估算 + "宁可放行"策略 |
| 防抖逻辑过于保守导致内存溢出后才切换状态 | 低（20%） | 高 | 硬限触发时额外执行 `gc.collect()`，不等待防抖 |
| Bootstrap 组件顺序调整导致启动失败 | 低（10%） | 中 | MemoryController 放在 Storage 之后，不依赖其他组件 |

---

## 五、日级时间表

| 日期 | 任务 | 产出 |
|:---|:---|:---|
| Day 1 上午 | 创建 `core/memory_controller.py`，实现 `MemoryGate`、`MemoryStats` 数据结构 | 数据结构就绪 |
| Day 1 下午 | 实现三级探测策略、`can_accept()`、防抖逻辑 | 核心逻辑就绪 |
| Day 2 上午 | 实现集成点 A（bootstrap）和 B（scheduler） | 调度门控就绪 |
| Day 2 下午 | 实现集成点 C（trigger_server）和 D（app.py health sync） | 全链路集成就绪 |
| Day 3 上午 | 编写 `test_memory_controller.py` 全部 8 个用例 | 测试就绪 |
| Day 3 下午 | 执行 T1.4 回归测试 + 集成验证，修复发现的问题 | 全部测试通过 |
| Day 4 上午 | 修复回归测试中发现的问题（如有） | — |
| Day 4 下午 | 执行 T1.5 阶段评估，撰写评估报告 | `docs/PHASE1_REVIEW.md` |

---

## 六、验收标准

第一阶段完成的门禁条件：

1. `core/memory_controller.py` 文件存在且包含 MemoryController、MemoryGate、MemoryStats 三个类
2. `core/bootstrap.py` 中初始化 MemoryController
3. `core/scheduler.py` 的 `submit()` 方法在硬限时拒绝新任务
4. `transport/trigger_server.py` 的 HTTP 通道在硬限时返回 503
5. `tests/test_memory_controller.py` 中 8 个测试用例全部通过
6. 全部 24 个测试文件通过 `pytest tests/ -v`
7. psutil 不可用时系统优雅降级（不崩溃、不阻塞）
8. `docs/PHASE1_REVIEW.md` 已生成

---

## 七、文件变更清单

| 操作 | 文件 | 行数变化（估计） |
|:---|:---|:---|
| 新建 | `core/memory_controller.py` | +180 |
| 新建 | `tests/test_memory_controller.py` | +150 |
| 修改 | `core/bootstrap.py` | +8 |
| 修改 | `core/scheduler.py` | +10 |
| 修改 | `transport/trigger_server.py` | +12 |
| 修改 | `runtime/app.py` | +6 |
| 修改 | `core/health_checker.py` | +4 |
| 新建 | `docs/PHASE1_REVIEW.md` | +100 |

**总新增代码行数**：约 470 行（含测试和文档），在 4 天工时内合理。
