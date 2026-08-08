---
name: architecture-gap-analysis-optimization
overview: 对 atlas-runtime v9.0 架构设计与代码实现进行全面差距分析，识别出 11 个偏离点，按 P0/P1/P2 三级优先级提出优化方案，包括修复 BaseExecutor 未被继承、transport→core 跨层依赖、Task 数据模型错位、runtime 使用弃用导入、Termux 路径硬编码重复等问题，并补齐新包测试覆盖。
todos:
  - id: fix-transport-backpressure
    content: "P0-2: 修复 transport/trigger_server.py 跨层依赖——将 BackpressureError 导入路径从 core.trigger_handler 改为 models.errors"
    status: completed
  - id: adopt-base-executor-shell
    content: "P0-1a: SafeShellExecutor 继承 BaseExecutor——添加 execute() 方法包装 run_command() 返回 ExecutorResult"
    status: completed
  - id: update-scheduler-base-executor
    content: "P0-1b: Scheduler 改为接受 BaseExecutor 协议——executor 类型变更 + 调用 execute() 方法"
    status: completed
    dependencies:
      - adopt-base-executor-shell
  - id: update-bootstrap-and-tests
    content: "P0-1c: Bootstrap 传入 executor 实例而非方法引用 + 更新 test_scheduler 和 test_shell_executor"
    status: completed
    dependencies:
      - update-scheduler-base-executor
  - id: migrate-task-to-models
    content: "P1-1: 创建 models/task.py 并迁移 Task/TaskStatus——从 core/scheduler.py 提取数据类到 models/task.py"
    status: completed
  - id: fix-old-imports-and-docstrings
    content: "P1-2+P1-3: 更新 runtime/app.py 导入为 device/ 路径 + 修正 device/detector.py 文档字符串"
    status: completed
  - id: add-new-package-tests
    content: "P1-4: 新增 test_models.py、test_device.py、test_executor_base.py、test_sim_switch.py（每个至少 3 个测试用例）"
    status: completed
    dependencies:
      - migrate-task-to-models
  - id: cleanup-tech-debt
    content: "P2-1+P2-2: 消除 Termux 路径重复定义 + storage/__init__.py 添加弃用注释"
    status: completed
    dependencies:
      - fix-old-imports-and-docstrings
  - id: regression-and-doc-sync
    content: 全量回归测试 + 更新 ARCHITECTURE.md 中 BaseExecutor 状态说明（从计划变为已实现）
    status: completed
    dependencies:
      - update-bootstrap-and-tests
      - add-new-package-tests
      - cleanup-tech-debt
---

## 产品概述

针对 atlas-runtime v9.0 架构设计文档与当前代码实现之间的差距，执行一项面向架构一致性的优化计划。目标是在不影响现有功能稳定性的前提下，使代码实现与六层架构设计文档完全对齐。

## 核心优化目标

按优先级划分为三类：

**P0（关键差距，阻塞性）**：BaseExecutor ABC 未被任何执行器继承——`executors/base.py` 定义了统一接口但三个执行器均不遵循它，Scheduler 将执行器视为 `Callable` 函数签名而非 `BaseExecutor` 协议。transport 层跨层依赖 core 层——`trigger_server.py` 从 `core.trigger_handler` 导入 `BackpressureError`，违反 v9.0 的 transport → models 单向依赖规则。

**P1（架构一致性）**：`core/scheduler.py` 中的 `Task` 和 `TaskStatus` 数据类应迁移到 `models/task.py`——它们是纯数据契约，当前导致 `trigger_handler.py` 需要 TYPE_CHECKING 延迟导入。`runtime/app.py` 的升级路径仍使用弃用的兼容性存根（`from core.platform import ...` 应改为 `from device import ...`）。`device/detector.py` 的文档字符串仍引用旧 `platform/` 路径。四个新包（`models/`、`device/`、`executors/base.py`、`executors/sim_switch.py`）缺少独立测试文件。

**P2（技术债务清理）**：`TERMUX_PREFIX` 在 `device/detector.py`、`executors/shell_executor.py`、`executors/ui_automation.py` 三处重复定义。`storage/__init__.py` 提供了 `StorageFullError` 和 `StorageError` 的双重导出路径（从 storage 和从 models），可能引起混淆。


## 技术栈

- Python 3.10+、asyncio 异步架构
- pytest 测试框架（现有 194 个测试项）
- 所有改动需通过现有 35+ 项 high_privilege 测试和 11 项 shell_executor 测试

## 实施策略

采用**多层渐进式优化**策略：P0 项强制执行以修复设计-实现差距；P1 项逐步对齐架构一致性；P2 项在完成 P0 和 P1 后作为技术债务清理执行。每完成一个 P0 项立即运行回归测试。

### P0-1：BaseExecutor ABC 与执行器统一协议

**改进目标**：使三个执行器继承 `BaseExecutor` ABC，并统一返回 `ExecutorResult` 格式。Scheduler 从接受 `Callable[[str, float], Awaitable[Any]]` 改为接受 `BaseExecutor` 实例。

**影响范围**：`executors/shell_executor.py`（添加 `execute()` 方法包装）、`core/scheduler.py`（类型变更为 `BaseExecutor`，调用 `executor.execute()` 而非 `executor(cmd, timeout)`）、`core/bootstrap.py`（传入 executor 实例而非方法引用）、`tests/test_scheduler.py`（mock 适配 `execute()` 接口）、`tests/test_shell_executor.py`（测试新增 `execute()` 方法）。

**实施步骤**：
1. 在 `SafeShellExecutor` 中添加 `async def execute(self, **kwargs) -> ExecutorResult` 方法，内部调用现有 `run_command()` 并包装返回值为 `ExecutorResult`
2. 在 `core/scheduler.py` 中导入 `BaseExecutor`、`ExecutorResult`；将 `__init__` 的 `executor` 类型改为 `BaseExecutor`
3. `_execute_task` 方法中将调用方式从 `result = await self.executor(cmd, timeout=timeout)` 改为 `result = await self.executor.execute(cmd=cmd, timeout=timeout)`
4. 在 `core/bootstrap.py` 中将 `executor=executor.run_command` 改为 `executor=executor`
5. 更新测试文件适配新接口

**验收标准**：`issubclass(SafeShellExecutor, BaseExecutor)` 为 True；`SafeShellExecutor().execute(cmd='echo hello')` 返回 `ExecutorResult(success=True)`；35 项 high_privilege 测试通过；11 项 shell_executor 测试通过；Scheduler 测试通过（排除已知 flaky 项）

### P0-2：transport 层跨层依赖修复

**改进目标**：`transport/trigger_server.py` 直接从 `models.errors` 导入 `BackpressureError`，而非经过 `core.trigger_handler`

**影响范围**：仅 `transport/trigger_server.py` 第 18 行

**实施步骤**：将 `from core.trigger_handler import BackpressureError` 改为 `from models.errors import BackpressureError`

### P1-1：Task/TaskStatus 迁移到 models/

**改进目标**：将 `Task` dataclass 和 `TaskStatus` Enum 从 `core/scheduler.py` 迁移到新建的 `models/task.py`

**影响范围**：新增 `models/task.py`、`models/__init__.py`、`core/scheduler.py`（删除定义改导入）、`core/trigger_handler.py`（移除 TYPE_CHECKING）、`tests/test_scheduler.py`（更新导入路径）

### P1-2：runtime/app.py 更新导入路径

**改进目标**：将 `from core.platform import PlatformInfo` 和 `from core.health_checker import HealthChecker` 改为 `from device import PlatformInfo, HealthChecker`

**影响范围**：仅 `runtime/app.py` 第 28-29 行

### P1-3：device/detector.py 文档字符串修正

**改进目标**：将 3 处引用旧 `platform/detector.py` 路径的文档字符串改为 `device/detector.py`

### P1-4：新包测试覆盖

**改进目标**：新增 `tests/test_models.py`（至少 3 项测试）、`tests/test_device.py`（至少 3 项测试）、`tests/test_executor_base.py`（至少 3 项测试）、`tests/test_sim_switch.py`（至少 3 项测试）

每个测试文件至少覆盖：导入验证、核心字段/方法的行为验证、边界条件检查

### P2-1：消除 Termux 路径重复定义

**改进目标**：`executors/shell_executor.py` 和 `executors/ui_automation.py` 的 `_TERMUX_PREFIX`/`_TERMUX_TMP` 改为 `from device import TERMUX_PREFIX, TERMUX_TMP`

### P2-2：storage/__init__.py 弃用注释

**改进目标**：在 `storage/__init__.py` 中添加批注，标记 `StorageFullError`/`StorageError` 的 storage 路径为弃用，引导新代码使用 `from models import ...`


## Agent Extensions

### Skill
- **atlas-synergy-agent**
  - Purpose: 提供 Android 自动化运行时的设备端验证上下文——确保架构优化不会破坏 Termux + Samsung One UI 8.5 环境中的实际部署行为。用于审查执行器接口变更对 Tasker-FIFO 触发链的潜在影响。
  - Expected outcome: 确认 P0-1 的 Scheduler 接口变更与现有的 FIFO/HTTP 触发流程兼容，不会导致 Tasker 端触发失效。

### SubAgent
- **code-explorer**
  - Purpose: 在实施过程中快速搜索各模块之间的导入依赖变化，验证优化后无遗漏的跨层依赖违规。
  - Expected outcome: 在每个 P0/P1 优化步骤完成后提供全域导入验证报告，确保所有导入路径遵循 v9.0 依赖规则。
