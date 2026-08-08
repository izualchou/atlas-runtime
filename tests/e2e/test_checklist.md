# Atlas Runtime — 端到端 (E2E) 测试清单

版本: v1.0 | 日期: 2026-08-08

本文档定义了 Atlas Runtime 的端到端集成测试场景，覆盖从 Tasker/AutoJS6 触发到 Python 引擎执行再到结果回读的完整链路。

---

## 测试环境要求

| 项目 | 要求 |
|------|------|
| 设备 | Samsung Android 设备 (One UI 8.5+) |
| Termux | v0.118+，已安装 Python 3.11+、termux-api |
| Tasker | v5.15+，已安装 Termux:Tasker 插件 |
| AutoJS6 | v6.5+，已开启无障碍服务 |
| Atlas | 已通过 `service/deploy.sh` 部署，FIFO+HTTP 通道就绪 |
| 共享目录 | `/sdcard/atlas_shared/` 已创建且可读写 |

---

## 场景 1: SIM 切换 E2E

**描述**: 从 Tasker 定时触发 → Atlas 执行 SIM 切换 → AutoJS6 验证运营商 → 结果回读通知。

| 序号 | 步骤 | 预期结果 | 验证方法 |
|------|------|----------|----------|
| 1.1 | `python -m runtime.app --config config/runtime.yaml` 启动 Atlas | 日志显示 MemoryController/CircuitBreaker/DedupFilter 已初始化 | 检查 stdout |
| 1.2 | `bash runtime/trigger_atlas.sh '{"action":"sim_switch","params":{"slot":0},"correlation_id":"e2e_sim_001"}'` | 脚本返回 exit 0，FIFO 写入成功 | 检查 exit code |
| 1.3 | 查看 Atlas 日志 | 任务被 accepted，进入 pending 队列，executed 成功 | `grep "e2e_sim_001" logs/*.log` |
| 1.4 | 检查 `/sdcard/atlas_shared/last_result.json` | 文件存在，status 为 success | `cat /sdcard/atlas_shared/last_result.json` |
| 1.5 | AutoJS6 执行 `sim_switch_verify.js` | 日志显示运营商读取结果 | AutoJS6 控制台 |
| 1.6 | 验证 SIM 运营商已切换 | getprop 显示新运营商 | `getprop gsm.operator.alpha` |

**验收标准**: 全部 6 步通过。

---

## 场景 2: UI 自动化 E2E

**描述**: 从 HTTP 触发 → Atlas 调度 AutoJS6 → UI 点击序列 → 结果回写。

| 序号 | 步骤 | 预期结果 | 验证方法 |
|------|------|----------|----------|
| 2.1 | Atlas HTTP 服务运行中 | `curl http://127.0.0.1:8787/health` 返回 200 | curl |
| 2.2 | POST 触发 `app_launcher.js` | `curl -X POST http://127.0.0.1:8787/trigger -H 'Content-Type: application/json' -d '{"action":"launch_autojs","params":{"script_name":"app_launcher.js","app_name":"设置"},"correlation_id":"e2e_ui_001"}'` 返回 200 | curl |
| 2.3 | Atlas 调度 autojs_launcher.py | 日志显示 `AutoJS6: params file written` | 检查日志 |
| 2.4 | AutoJS6 启动 "设置" APP | 屏幕上显示设置界面 | 目视确认 |
| 2.5 | AutoJS6 HTTP 回调结果 | Atlas 日志显示 callback received | 检查日志 |
| 2.6 | `/sdcard/atlas_shared/last_result.json` 更新 | status = success | 文件读取 |

**验收标准**: 全部 6 步通过。

---

## 场景 3: 崩溃恢复 E2E

**描述**: 模拟 Atlas 进程被 kill，验证重新启动后从快照恢复。

| 序号 | 步骤 | 预期结果 | 验证方法 |
|------|------|----------|----------|
| 3.1 | 启动 Atlas，提交 3 个任务 | 任务进入 pending/executed | 日志 |
| 3.2 | `kill -9 <atlas_pid>` 强制终止 | 进程消失 | `ps aux | grep python` |
| 3.3 | 重新启动 Atlas | Bootstrap 显示 "recovering from snapshot" | 日志 |
| 3.4 | 检查 pending 任务被恢复 | 日志显示任务 resumed | 日志 |
| 3.5 | 新任务正常提交 | submit 成功 | curl POST |
| 3.6 | CircuitBreaker 状态正常 | 日志显示 circuit_breaker state = closed | 日志 |

**验收标准**: 全部 6 步通过。

---

## 场景 4: 快照冷恢复 E2E

**描述**: 设备重启后 Atlas 从存储快照恢复状态。

| 序号 | 步骤 | 预期结果 | 验证方法 |
|------|------|----------|----------|
| 4.1 | 运行 Atlas 至少 5 分钟，任务已持久化 | storage 目录有数据文件 | `ls storage/*.json` |
| 4.2 | `reboot` 重启设备 | 设备重启 | - |
| 4.3 | 启动 Termux，重新部署 Atlas | deploy.sh 成功 | 脚本输出 |
| 4.4 | 启动 Atlas | 日志显示 "recovered N snapshots" | 日志 |
| 4.5 | 历史任务状态可查询 | stats 接口返回正确计数值 | curl GET /stats |
| 4.6 | 新任务正常调度 | submit 成功 | curl POST |

**验收标准**: 全部 6 步通过。

---

## 场景 5: 内存压力场景

**描述**: 模拟高内存压力，验证 MemoryController 门控和熔断。

| 序号 | 步骤 | 预期结果 | 验证方法 |
|------|------|----------|----------|
| 5.1 | 正常启动 Atlas | MemoryController state = ACCEPT | 日志 |
| 5.2 | 提交大量任务挤压内存 | 日志出现 SOFT_THROTTLE | 日志 |
| 5.3 | 持续提交任务 | 日志出现 HARD_REJECT，HTTP 返回 503 | curl |
| 5.4 | 停止提交，等待 GC | 状态恢复到 ACCEPT | 日志 |
| 5.5 | CircuitBreaker 在连续超时后触发 | state = OPEN | 日志 |
| 5.6 | 冷却后恢复 | HALF_OPEN → CLOSED | 日志 |

**验收标准**: 全部 6 步通过。

---

## 测试通过总结

| 场景 | 步骤数 | 状态 |
|------|--------|------|
| SIM 切换 E2E | 6 | [ ] 待测试 |
| UI 自动化 E2E | 6 | [ ] 待测试 |
| 崩溃恢复 E2E | 6 | [ ] 待测试 |
| 快照冷恢复 E2E | 6 | [ ] 待测试 |
| 内存压力场景 | 6 | [ ] 待测试 |
| **总计** | **30** | **0/30** |
