# Atlas Runtime v8.0 LTS 架构设计文档

> 版本：v8.0 LTS | 最后更新：2026-08-02

## 设计原则

1. **Termux First**: 所有核心逻辑运行在 Termux 中，利用 termux-services (runit) 实现服务保活与自动重启
2. **事件驱动**: FIFO 命名管道接收触发信号，完全免疫 Android Doze 模式的网络限制
3. **进程安全**: Shell 子进程通过独立进程组 (`start_new_session=True`) 隔离，超时通过 `os.killpg()` 安全清理
4. **端到端背压控制**: SQLite 写入队列有界（maxsize=1000），`asyncio.QueueFull` 触发背压退避
5. **原子快照**: 深拷贝冻结状态 + 临时文件 + `os.replace()` 原子重命名 + SHA256 校验和

## 模块分层

```
┌─────────────────────────────────────────────┐
│  runtime/app.py         主入口 + 信号管理    │
├─────────────────────────────────────────────┤
│  transport/             通信层               │
│    trigger_server.py    FIFO(主) + HTTP(备)  │
├─────────────────────────────────────────────┤
│  core/                  微内核（不可变）      │
│    bootstrap.py         启动编排（拓扑排序）  │
│    scheduler.py         双队列调度            │
│    state_manager.py     状态 + 深拷贝快照     │
│    resource_lock.py     持久化互斥锁 + CAS    │
│    trigger_handler.py   背压控制 + 死信管理   │
├─────────────────────────────────────────────┤
│  executors/             执行器               │
│    shell_executor.py    安全 Shell（进程组）  │
│    ui_automation.py     UI 自动化             │
│    high_privilege.py    高权限操作            │
├─────────────────────────────────────────────┤
│  storage/               存储层               │
│    driver.py            单写者队列 SQLite     │
│    snapshot.py          原子快照              │
│    rotator.py           自动轮转归档          │
│    battery_aware.py     电量感知 Checkpoint   │
└─────────────────────────────────────────────┘
```

## 任务状态机

```
PENDING → SCHEDULED → EXECUTING → SUCCESS
                                → TIMEOUT → RETRY（最多3次，指数退避）
                                → FAILED → RETRY → DEAD（写死信）
```

## 故障自愈

| 故障场景 | 检测方式 | 恢复动作 |
| :--- | :--- | :--- |
| Runtime 进程崩溃 | runit 监控 PID | 即时重启（< 2 秒） |
| HTTP 端口冲突 | OSError 捕获 | `fuser -k` 释放 → 重试 |
| Shell 命令超时 | `asyncio.wait_for(5s)` | `killpg` → 重试 |
| SQLite 队列满 | `asyncio.QueueFull` | 背压退避 1 秒 → HTTP 429 |
| 存储空间不足 | 写入前预检（< 50MB） | 拒绝写入 → 只读模式 |
| FIFO 管道阻塞 | `O_RDWR | O_NONBLOCK` | `open` 永不阻塞 |
| 孤儿锁残留 | 启动时清理 | 检查 `expires_at <= now` 删除 |

## 组件定位

| 组件 | 定位 | 必须 | 通信方式 |
| :--- | :--- | :--- | :--- |
| Termux + Python Runtime | 核心大脑 | ✅ | — |
| Tasker | 轻量触发器 | ✅ 推荐 | FIFO（主）/ HTTP（备） |
| Auto.js6 | 复杂 UI 执行器 | ❌ 可选 | HTTP / UDS |

## 部署脚本

| 脚本 | 用途 |
| :--- | :--- |
| `service/deploy.sh` | 一键部署 |
| `service/update.sh` | 增量补丁应用（含自动备份与回退） |
| `service/run` | runit 服务启动脚本 |
