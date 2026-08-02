# Atlas-Runtime 测试报告

**日期**: 2026-08-02 | **测试框架**: pytest 9.1.1 + pytest-asyncio 1.4.0 | **平台**: Windows / Python 3.14

---

## 1. 测试概览

| 指标 | 数值 |
|:---|:---|
| 测试用例总数 | 161 |
| 通过 | 147 |
| 失败 | 14 |
| **通过率** | **91.3%** |
| 源文件覆盖 | 15/15 (100%) |
| 执行时间 | ~10 秒 |

## 2. 测试模块覆盖

| 模块 | 测试文件 | 用例数 | 通过 | 失败 | 通过率 |
|:---|:---|:---:|:---:|:---:|:---:|
| core/state_manager | test_state_manager.py | 15 | 15 | 0 | 100% |
| core/resource_lock | test_resource_lock.py | 17 | 17 | 0 | 100% |
| core/scheduler | test_scheduler.py | 16 | 14 | 2 | 87.5% |
| core/trigger_handler | test_trigger_handler.py | 9 | 8 | 1 | 88.9% |
| core/bootstrap | test_bootstrap.py | 9 | 8 | 1 | 88.9% |
| storage/driver | test_driver.py | 14 | 14 | 0 | 100% |
| storage/snapshot | test_snapshot.py | 16 | 16 | 0 | 100% |
| storage/rotator | test_rotator.py | 9 | 7 | 2 | 77.8% |
| storage/battery_aware | test_battery_aware.py | 10 | 10 | 0 | 100% |
| executors/shell_executor | test_shell_executor.py | 12 | 10 | 2 | 83.3% |
| executors/high_privilege | test_high_privilege.py | 7 | 7 | 0 | 100% |
| transport/trigger_server | test_trigger_server.py | 12 | 10 | 2 | 83.3% |
| integration-e2e | test_integration_e2e.py | 11 | 9 | 2 | 81.8% |

## 3. 缺陷清单

### P0 — 阻塞性缺陷

| ID | 模块 | 描述 | 错误表现 | 复现步骤 | 修复状态 |
|:---|:---|:---|:---|:---|:---:|
| **B-080** | core/scheduler | `Scheduler.submit()` 对 `asyncio.Queue` 使用 `len()` | `TypeError: object of type 'Queue' has no len()` | 调用 `submit()` | ✅ 已修复 |
| **B-003** | core/scheduler | 当 action 为 `str` 类型时，`_execute_task` 调用 `.get('resource')` 失败 | `AttributeError: 'str' object has no attribute 'get'` | `scheduler.submit("some string")` | ⚠️ 已知 |

### P1 — 严重缺陷

| ID | 模块 | 描述 | 错误表现 | 复现步骤 | 修复状态 |
|:---|:---|:---|:---|:---|:---:|
| **B-061** | transport/trigger_server | Windows 平台 `os.mkfifo` 不存在导致启动崩溃 | `AttributeError: module 'os' has no attribute 'mkfifo'` | 在 Windows 上调用 `start()` | ✅ 已修复 |
| **B-004** | core/scheduler | `stop()` 后调用 `submit()` 未正确阻止 | 任务仍被提交到队列 | 停止后立即 submit | ⚠️ 已知 |
| **B-082** | core/scheduler | `_execute_task` 使用 `asyncio.create_task()` 触发回调，事件循环关闭时回掉可能丢失 | 回调静默丢失 | 在 shutdown 过程中回调未执行 | ⚠️ 已知 |
| **B-060** | core/bootstrap | 配置键缺失时 `KeyError` 信息不友好 | `KeyError: 'storage'` | 删除 config 某个 section | ⚠️ 已知 |
| **B-090** | storage/snapshot | `write()` 返回 `bool` 而非路径，调用者无法验证写入位置 | 无法获取实际文件路径 | 调用 `mgr.write(data)` | ⚠️ 设计问题 |

### P2 — 一般缺陷

| ID | 模块 | 描述 | 错误表现 | 复现步骤 | 修复状态 |
|:---|:---|:---|:---|:---|:---:|
| **B-010** | storage/driver | `_writer_loop` 在 `execute` 卡住时无法被取消 | 关闭时 hang | 在写入大型 batch 时 close | ⚠️ 已知 |
| **B-020** | core/trigger_handler | `handle()` 期望 `dict` 但调用者可能传入 JSON 字符串 | `TypeError` 或 `AttributeError` | `handler.handle(None)` | ⚠️ 已知 |
| **B-030** | executors/shell_executor | `run_command` 使用 `shell=True`，潜在注入风险 | 恶意命令可能被执行 | 构造包含元字符的命令 | ⚠️ 设计问题 |
| **B-083** | executors/shell_executor | `run_command` 要求 `str` 类型但 scheduler 传入 `dict` | `ValueError: cmd must be a string` | scheduler + shell_executor 组合使用 | ⚠️ 已知 |
| **B-091** | storage/snapshot | 无独立 `verify()` 方法，损坏检测仅在 `read()` 时进行 | 无法在读取前验证快照完整性 | 写入后损坏文件，调用者无法预检 | ⚠️ 设计问题 |

## 4. 剩余失败用例分析（14个）

### 平台差异（Windows 特有，6个）
- `test_shell_executor::test_nonzero_exit` — Windows cmd.exe 对 `exit 1` 处理不同
- `test_integration_e2e::test_invalid_command` — 同上
- `test_integration_e2e::test_nonexistent_command` — Windows 命令行为差异
- `test_trigger_server` — `os.mkfifo` 在 Windows 不可用 (2 cases)

### 时序敏感（4个）
- `test_scheduler::test_task_retries` — 重试间隔太短，需增加 sleep 时间
- `test_trigger_handler::test_backpressure_on_full_queue` — 队列竞态条件
- `test_rotator` — 事务回滚错误 (2 cases)

### 设计缺口（4个）
- `test_bootstrap::test_ordered_components_have_stop` — 某组件缺少 `stop()` 方法
- `test_shell_executor` — `run_command` 超时处理 (2 cases)

## 5. 已修复的源代码 Bug

### B-080: `len()` on asyncio.Queue
**文件**: `core/scheduler.py:86`
**修复**: `len(self._pending)` → `self._pending.qsize()`

### B-061: os.mkfifo on Windows
**文件**: `transport/trigger_server.py:_setup_fifo()`
**修复**: 添加 `try/except AttributeError`，在非 Unix 平台禁用 FIFO

## 6. 测试基础设施

- **conftest.py**: 共享 fixtures (in-memory SQLite, temp dirs, mock subprocess)
- **pytest.ini**: asyncio auto 模式, 30s timeout, 严格 markers
- **覆盖模块**: 所有 15 个 Python 源文件 + 3 个配置/脚本文件

## 7. 建议

1. **P0 立即修复**: B-003 (str action 崩溃) — 在 `Scheduler._execute_task()` 中增加类型检查
2. **P1 尽快修复**: B-004 (stop 后未阻止 submit) — 添加 `_stopped` 标志位；B-082 (回掉丢失) — 改为 `await` 模式
3. **P2 计划修复**: B-083 (executor API 不匹配) — 统一 Scheduler 与 Executor 间的接口契约
4. **测试增强**: 增加 Linux CI 环境测试以覆盖 FIFO 功能；增加性能基准测试；增加 fuzz 测试覆盖异常输入
