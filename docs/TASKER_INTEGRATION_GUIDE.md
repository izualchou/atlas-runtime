# Tasker 集成配置指南

版本: v1.0 | 日期: 2026-08-08

本文档指导用户将 Atlas Runtime 的 Tasker 配置文件导入并部署到 Android 设备。

---

## 前置条件

1. **Tasker v5.15+** 已安装并激活
2. **Termux** 已安装，Python 3.11+ 环境就绪
3. **Termux:Tasker 插件** 已安装（从 F-Droid 或 Google Play 获取）
4. Atlas Runtime 已部署到 Termux 的 `~/atlas-runtime/`
5. 共享目录 `/sdcard/atlas_shared/` 已创建（Termux 中执行 `termux-setup-storage` 后 `mkdir -p /sdcard/atlas_shared/`）

---

## 快速开始

### 第一步：导入项目文件

1. 打开 Tasker，进入 "任务" 标签
2. 长按底部 "任务" 按钮 → "导入项目"
3. 选择 `atlas-runtime/config/tasker/atlas_trigger.prj.xml`
4. 确认导入，项目 "Atlas Trigger" 应出现在列表中

项目包含：
- 3 个 Profile（时间、事件、状态触发）
- 4 个 Task（SIM 切换、WiFi 切换、通用触发、结果处理）

### 第二步：调整路径配置

打开任意 Task，编辑 Termux:Tasker Action：
- **Workdir**: `/data/data/com.termux/files/home/atlas-runtime`
- **Executable**: `/data/data/com.termux/files/usr/bin/bash`
- **Arguments**: `runtime/trigger_atlas.sh <your_json>`

### 第三步：授予 Tasker 必要权限

- 无障碍服务
- 通知监听（用于事件触发 Profile）
- 后台运行权限

### 第四步：测试触发链

在 Tasker 中手动执行 "ATLAS: SIM切换" Task，观察是否：
1. Termux 收到执行请求
2. Atlas 日志中出现任务记录
3. `/sdcard/atlas_shared/last_result.json` 文件更新

---

## 配置文件说明

### Profile：定时触发 (profile_time.xml)

每日 08:55 自动执行 SIM 切换。可在 Tasker 中修改时间：编辑 Profile → 点击时间条件 → 调整。

### Profile：事件触发 (profile_event.xml)

收到来自 Messages/SMS 应用的通知时触发。配置 AutoNotification 插件后，可自定义监听的应用和文本过滤器。

### Profile：状态触发 (profile_state.xml)

电量降到 20% 以下时触发 WiFi 关闭以节省电量。电量恢复时自动重新开启 WiFi。

### Task：SIM 切换 (task_sim_switch.tsk.xml)

7 步操作序列：
1. 构建 JSON `{"action":"sim_switch","params":{"slot":0},"correlation_id":"tasker_sim_%TIMES"}`
2. 通过 Termux:Tasker 调用 `trigger_atlas.sh`
3. 等待 5 秒
4. 读取 `last_result.json`
5. 检查结果是否就绪
6. 解析 status 字段
7. 显示通知

### Task：WiFi 切换 (task_wifi_toggle.tsk.xml)

6 步操作序列：
1. 构建 JSON
2. 检查当前 WiFi 状态
3. 根据状态设置 toggle 值
4. 调用 trigger_atlas.sh
5. 等待 3 秒
6. 显示通知

### Task：通用触发 (task_trigger_universal.tsk.xml)

可复用的模板 Task。通过 `%par1` 传递 action 名称、`%par2` 传递 JSON 参数。

用法示例：
```
Perform Task "ATLAS: 通用触发"
  %par1 = "shell_command"
  %par2 = {"cmd":"echo hello"}
```

### Task：结果处理 (task_result_handler.tsk.xml)

从共享目录读取最新结果并展示通知。8 步操作序列包括 JSON 解析和条件分支。

---

## 故障排除

| 问题 | 可能原因 | 解决 |
|------|----------|------|
| Termux:Tasker 提示 "Plugin not found" | 插件未安装 | 安装 Termux:Tasker |
| trigger_atlas.sh 返回 exit 4 | curl 连接失败 | 确保 Atlas HTTP 服务运行中 |
| trigger_atlas.sh 返回 exit 2 | FIFO 和 HTTP 都失败 | 检查 Atlas 是否启动 |
| Tasker 无法读取 last_result.json | 共享存储未授权 | 执行 `termux-setup-storage` |
| task_sim_switch 执行无效果 | Atlas 引擎未处理 | 查看日志 `logs/*.log` |

---

## 三星 One UI 8.5 特别说明

- Termux:Tasker 通过 `am startservice` 与 Termux 通信，三星 Knox 通常不会拦截此调用
- 如果任务执行"无响应"，检查 Tasker → 偏好设置 → "保持服务运行" 是否已开启
- 三星的 "自动优化" 功能可能杀死后台 Atlas 进程，建议在设备维护中将 Termux 添加到 "不优化的应用" 列表
