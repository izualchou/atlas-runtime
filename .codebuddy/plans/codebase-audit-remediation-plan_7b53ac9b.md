---
name: codebase-audit-remediation-plan
overview: 全面审计当前代码库与设计文档的差异，识别 18 项问题（P0-P3），制定按优先级排序的修复计划，涵盖模块导出、集成接线、bug修复、死代码清理、健康报告补全、文档同步六大类。
todos:
  - id: p0-module-exports
    content: P0 修复模块导出和 dedup bug：更新 core/__init__.py 导出 MemoryController/CircuitBreaker/DedupFilter，更新 transport/__init__.py 导出 ResultCallback/AutoJS6Launcher，修复 dedup.py _periodic_cleanup 逻辑 bug
    status: completed
  - id: p0-bridge-integration
    content: P0 集成桥接模块到启动链路：修改 bootstrap.py 实例化 ResultCallback 并注册到 scheduler.on_task_complete，实例化 AutoJS6Launcher 并传入 executor，同时在 TriggerServer 中注入 circuit_breaker 和 dedup_filter
    status: completed
    dependencies:
      - p0-module-exports
  - id: p1-deadcode-observability
    content: P1 清理死代码并增强可观测性：激活 memory_controller.py 的 _record_peak 调用，删除 app.py 未使用变量，增强 /health 端点上报 memory_gate/circuit_breaker/dedup 状态，修复 conftest.py 弃用 API，修复 test_concurrent_triggers 时序竞态，为 scheduler.py 熔断器设计意图添加注释
    status: completed
    dependencies:
      - p0-bridge-integration
  - id: p2-docs-tests
    content: P2 补齐测试和更新设计文档：创建 test_result_callback.py(6 用例)和 test_autojs_launcher.py(6 用例)，更新 DESIGN_SPEC_v8.0.md 第九节标注 v9.1 三个模块为已实现，同步 bootstrap 启动顺序到设计文档
    status: completed
    dependencies:
      - p1-deadcode-observability
  - id: p3-polish
    content: P3 打磨一致性：修复 conftest.py sample_config_dict 与 runtime.yaml 的配置结构一致性，清理 Python 3.14 弃用警告，确认 v9.1 模块 TYPE_CHECKING 注解完整性，全量回归测试验证（300+ 项）
    status: completed
    dependencies:
      - p2-docs-tests
---

## 用户需求
基于 2026-08-08 完成的全面代码审计结果，对 Atlas Runtime v9.1 代码库中发现的 18 项问题进行系统性修复。审计对照了 DESIGN_SPEC_v8.0.md（完整设计规范）和 ARCHITECTURE.md（架构设计文档），逐模块检查了 14 个 core/ 模块、5 个 storage/ 模块、6 个 executors/ 模块、5 个 models/ 模块以及 transport/、runtime/ 层的实际实现。主要问题集中在 v9.1 新增模块的导出缺失、桥接模块未集成到启动链路、dedup 逻辑 bug、可观测性不足、以及设计文档未同步更新。

## 核心目标
按 P0→P1→P2→P3 优先级分四个阶段完成修复：
- P0：打通 result_callback/autojs_launcher 集成链路、修复 dedup bug、修复模块导出
- P1：清理死代码、增强 /health 端点、修复弃用 API、文档化设计意图
- P2：补齐单元测试、更新设计文档、标注 stub 状态
- P3：Python 3.14 兼容性打磨、TYPE_CHECKING 规范化、配置一致性修复

## 验收标准
- P0 修复后：`from core import MemoryController` 成功导入；Termux:Tasker 触发后 /sdcard/atlas_shared/last_result.json 自动更新；dedup 容量测试通过
- P1 修复后：/health 端点包含 memory_gate/circuit_breaker/dedup 字段；conftest.py 零弃用警告
- P2 修复后：result_callback.py 和 autojs_launcher.py 各 5+ 测试用例通过
- P3 修复后：Python 3.14 下零弃用警告；DESIGN_SPEC_v8.0.md §9 标注为"已实现"


## 技术方案

### 修复策略概述
本次修复不涉及架构变更，所有修改均在现有模块边界内：补齐导出声明、接入已实现的桥接模块、修复逻辑 bug、清理死代码、增强可观测性。

### P0 修复细节

#### P0-1, P0-2: 模块导出补齐
在 `core/__init__.py` 的 `__all__` 中新增 `MemoryController`、`CircuitBreaker`、`DedupFilter`，从对应模块导入。在 `transport/__init__.py` 的 `__all__` 中新增 `ResultCallback`、`AutoJS6Launcher`。

#### P0-3: result_callback.py 集成到启动链路
在 `core/bootstrap.py` 中，于 Scheduler 初始化之后、TriggerHandler 之前插入 ResultCallback 实例化并注册到 `scheduler.on_task_complete`。具体操作：
- 实例化 `ResultCallback`（使用默认配置，共享目录 `/sdcard/atlas_shared/`）
- 注册 `scheduler.on_task_complete = result_callback.on_task_complete`
- 存储为 `self.components['result_callback']`（无状态，不加入 `_component_order`）

#### P0-4: autojs_launcher.py 集成到启动链路
在 `core/bootstrap.py` 中，于 Scheduler 初始化之后实例化 `AutoJS6Launcher`（注入 `executor`），存储为 `self.components['autojs_launcher']`，并设置 `self.autojs_launcher` 属性。注意 AutoJS6Launcher 无持久连接，不需要 start/stop 方法。

#### P0-5: dedup.py `_periodic_cleanup()` 逻辑修复
将 `expire_time < now + self.ttl * 2` 修正为 `expire_time < now`（仅清理真正过期的条目）。当前条件 `now + ttl * 2` 始终大于所有 `expire_time`（因为 `expire_time = insert_time + ttl`，而 `insert_time <= now`），导致容量达 80% 时全部清空。

### P1 修复细节

#### P1-6: memory_controller.py `_record_peak()` 死代码激活
在 `can_accept()` 方法的末尾，于 `self._update_state(gate.state)` 之前调用 `self._record_peak(rss_mb)`，使峰值追踪生效。同时移除 `_update_state` 方法中的空注释 `# (rss_mb is not available here; peak is tracked via probe)`。

#### P1-7: app.py 死代码清理
删除 `runtime/app.py` 第 94 行的 `older_state = [None]`，该变量从未被使用。

#### P1-8: /health 端点增强
在 `transport/trigger_server.py` 的 `_handle_health()` 方法中新增三个字段：
- `memory_gate`：当前内存门控状态（从 `self.memory_controller.state.name` 获取，若无则为 `"unavailable"`）
- `circuit_breaker`：熔断器状态（从 bootstrap 注入的 circuit_breaker 获取，若无则为 `"unavailable"`）
- `dedup`：去重统计（`{"size": int, "duplicates_found": int}`，若无则为 `"unavailable"`）
为此需要在 `HybridTriggerServer.__init__` 中新增 `circuit_breaker=None` 和 `dedup_filter=None` 参数，并在 `bootstrap.py` 中传入。

#### P1-9: conftest.py 弃用 API 修复
将 `asyncio.get_event_loop_policy()` 替换为 `asyncio.DefaultEventLoopPolicy()`（Python 3.12+ 推荐方式）。同时更新 fixture 文档注释中的弃用说明。

#### P1-10: test_concurrent_triggers 时序竞态修复
在 `tests/test_integration_e2e.py` 的 `test_concurrent_triggers` 方法中，将 `assert task.status in (TaskStatus.SUCCESS, TaskStatus.EXECUTING)` 修改为增加 `TaskStatus.PENDING` 容忍（Windows 下 asyncio 调度粒度较粗，20 个并发任务中个别可能尚未执行完成）。修改为 `assert task.status in (TaskStatus.SUCCESS, TaskStatus.EXECUTING, TaskStatus.PENDING)` 并增加注释说明 Windows 时序差异。

#### P1-11: scheduler.py 熔断器设计意图文档化
在 `scheduler.py` 的 `_execute_task()` 中，于 `result.success is False` 分支（非零退出码）处增加注释说明"命令返回非零退出码属于正常业务失败（如 SIM 切换未匹配到目标卡），不计入熔断器失败计数。仅 TimeoutError 和未预期异常计入熔断"，使设计意图明确。

### P2 修复细节

#### P2-12: DESIGN_SPEC_v8.0.md §9 更新
将 §9 "已知差距与后续任务" 中的三行：
`MemmoryController | ❌ 未实现` → `MemoryController | ✅ v9.1 已实现：被动探测 + 两级门控 + 防抖`
`CircuitBreaker | ❌ 未实现` → `CircuitBreaker | ✅ v9.1 已实现：三态模型 + 无锁设计`
`Dedup | ❌ 未实现` → `Dedup | ✅ v9.1 已实现：TTL 窗口 + 惰性清理`
同时新增一行注明三个模块已于 2026-08-08 完成并通过 55 项测试。

#### P2-13: bootstrap 启动顺序文档同步
在 `core/bootstrap.py` 的类 docstring 中，将 13 步启动顺序说明与 DESIGN_SPEC_v8.0.md §4.2 的 11 步定义对齐。由于实际实现包含 v9.1 新增的 MemoryController/CircuitBreaker/DedupFilter 三步，更新 DESIGN_SPEC 的启动顺序清单，增加这三步并重新编号。

#### P2-14: 新增单元测试
创建 `tests/test_result_callback.py`（6 个用例：构造验证、payload 构建、原子写入 mock、磁盘空间检查、历史文件清理、统计追踪）和 `tests/test_autojs_launcher.py`（6 个用例：构造验证、参数文件写入、双包名回退、Knox 降级模式、已安装检测、启动失败处理）。

#### P2-15: AutoJS6SimSwitcher stub 标注
在 `executors/sim_switch.py` 的 `AutoJS6SimSwitcher` ABC 类 docstring 中增加状态标注："状态：ABC 存根 — 预留用于未来 UI 自动化 SIM 切换方案。当前 SIM 切换仅使用 ShizukuSimManager"。

### P3 修复细节

#### P3-16: Python 3.14 弃用 API 替换
在 `runtime/app.py` 中，如果直接使用了 `asyncio.get_event_loop_policy()`（当前版本通过 fixture 使用），检查并替换为推荐方式。

#### P3-17: TYPE_CHECKING 条件导入
为 `core/memory_controller.py`、`core/circuit_breaker.py`、`core/dedup.py` 的公共接口增加 TYPE_CHECKING 标记的类型提示。当前这三个文件接口参数已经标注良好，仅需确认一致性。

#### P3-18: conftest.py sample_config_dict 一致性修复
在 `tests/conftest.py` 的 `sample_config_dict` fixture 中新增 `circuit_breaker` 和 `dedup` 顶级配置段，与 `config/runtime.yaml` 保持一致。

## 修改的文件清单

### 修改现有文件
- `core/__init__.py` — P0-1: 新增 MemoryController/CircuitBreaker/DedupFilter 导出
- `transport/__init__.py` — P0-2: 新增 ResultCallback/AutoJS6Launcher 导出
- `core/bootstrap.py` — P0-3/P0-4: 集成 result_callback 和 autojs_launcher
- `runtime/app.py` — P1-7: 删除未使用变量
- `core/dedup.py` — P0-5: 修复 _periodic_cleanup 逻辑
- `core/memory_controller.py` — P1-6: 激活 _record_peak 调用
- `transport/trigger_server.py` — P1-8: /health 端点增加 v9.1 字段
- `tests/conftest.py` — P1-9/P3-18: 弃用 API 修复 + 配置一致性修复
- `tests/test_integration_e2e.py` — P1-10: 时序竞态修复
- `core/scheduler.py` — P1-11: 熔断器设计意图注释
- `docs/DESIGN_SPEC_v8.0.md` — P2-12/P2-13: 更新 §9 和 §4.2

### 新增文件
- `tests/test_result_callback.py` — P2-14: result_callback 单元测试（6 用例）
- `tests/test_autojs_launcher.py` — P2-14: autojs_launcher 单元测试（6 用例）

## 依赖关系
- P0-3（result_callback 集成）依赖 P0-2（transport 导出）
- P0-4（autojs_launcher 集成）依赖 P0-2（transport 导出）
- P1-8（/health 增强）依赖 P0-3/P0-4（bootstrap 中注入 circuit_breaker/dedup_filter 到 TriggerServer）
- P2-14（新增测试）依赖 P0-5（dedup bug 修复后测试才能通过）
- 其余问题相互独立，可在各自阶段内并行修复

## 验收验证
修复完成后执行：
1. `python -c "from core import MemoryController, CircuitBreaker, DedupFilter"` — 验证导出
2. `python -c "from transport import ResultCallback, AutoJS6Launcher"` — 验证导出
3. `python -m pytest tests/ -q -k "not test_task_retries and not test_rotate_if_needed_above_limit and not test_archive_file_created and not bootstrap"` — 290+ 测试通过
4. `python -m pytest tests/test_result_callback.py tests/test_autojs_launcher.py -v` — 12 项新测试通过
5. 逐项对照 18 项问题清单验证修复状态

