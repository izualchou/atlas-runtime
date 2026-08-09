# Tasker 集成配置指南

版本: v1.2 | 日期: 2026-08-09

本文档指导用户将 Atlas Runtime 的 Tasker 配置文件导入并部署到 Android 设备。
所有 XML 文件均已审计并符合 Tasker v6.6.20 导入规范。

---

## 配置文件清单

### 项目级完整导入（推荐）

| 文件 | 路径 | 说明 |
|------|------|------|
| **atlas_trigger.prj.xml** | `config/tasker/atlas_trigger.prj.xml` | 完整项目：3 Profile + 4 Task，主入口 |

### 独立 Profile/Task 导入（按需）

| 文件 | 路径 | 大小 | 说明 |
|------|------|------|------|
| `profile_time.xml` | `config/tasker/profile_time.xml` | ~1.2 KB | 定时触发 Profile |
| `profile_event.xml` | `config/tasker/profile_event.xml` | ~1.3 KB | 通知事件触发 Profile |
| `profile_state.xml` | `config/tasker/profile_state.xml` | ~1.2 KB | 电量状态触发 Profile |
| `task_sim_switch.tsk.xml` | `config/tasker/task_sim_switch.tsk.xml` | ~1.9 KB | SIM 切换 Task |
| `task_wifi_toggle.tsk.xml` | `config/tasker/task_wifi_toggle.tsk.xml` | ~1.7 KB | WiFi 切换 Task |
| `task_trigger_universal.tsk.xml` | `config/tasker/task_trigger_universal.tsk.xml` | ~1.4 KB | 通用触发模板 Task |
| `task_result_handler.tsk.xml` | `config/tasker/task_result_handler.tsk.xml` | ~1.8 KB | 结果处理 Task |

### 技能范例文件

| 文件 | 路径 | 说明 |
|------|------|------|
| `system-monitor.prj.xml` | `.codebuddy/skills/tasker/assets/` | 范例：系统监控自动化 |
| `wifi-manager.prj.xml` | `.codebuddy/skills/tasker/assets/` | 范例：WiFi 连接管理 |
| `http-api-caller.prj.xml` | `.codebuddy/skills/tasker/assets/` | 范例：HTTP API + JSON 解析 |
| `scene-panel.prj.xml` | `.codebuddy/skills/tasker/assets/` | 范例：Scene 弹窗界面 |
| `termux-python.prj.xml` | `.codebuddy/skills/tasker/assets/` | 范例：Termux:Tasker + Python |

### 用户项目文件（设备导出）

| 文件 | 路径 | 说明 |
|------|------|------|
| `obsidian_prj.xml` | 项目根目录 | 用户 Obsidian Tasker 项目 |
| `rho_prj.xml` | 项目根目录 | 用户 RHO Tasker 项目 |
| `termux_template.xml` | 项目根目录 | Termux 模板 Task（迁移自 v5.11.7） |

所有文件 `tv` 属性已统一为 `"6.6.20"`（Tasker 最新稳定版）。

---

## 前置条件

1. **Tasker v6.6+** 已安装并激活（需 6.6.20 以获得最佳兼容性）
2. **Termux** 已安装，Python 3.11+ 环境就绪
3. **Termux:Tasker 插件** 已安装（从 F-Droid 获取：`com.termux.tasker`）
4. Atlas Runtime 已部署到 Termux 的 `~/atlas-runtime/`
5. 共享目录 `/sdcard/atlas_shared/` 已创建（Termux 中执行 `termux-setup-storage` 后 `mkdir -p /sdcard/atlas_shared/`）

---

## 快速开始

### 第一步：导入项目文件

**方式一：完整项目导入（推荐）**

1. 打开 Tasker，长按底部 "任务" 标签按钮
2. 选择 "导入项目"
3. 定位到 `atlas-runtime/config/tasker/atlas_trigger.prj.xml`
4. 确认导入，项目 "Atlas Trigger" 应出现在列表中

项目包含：
- 3 个 Profile（时间定时、通知事件、电量状态）
- 4 个 Task（SIM 切换、WiFi 切换、通用触发、结果处理）

**方式二：独立 Profile/Task 导入**

1. 进入 Tasker "配置文件" 或 "任务" 标签
2. 长按标签按钮 → "导入"
3. 选择对应的 `.prf.xml` 或 `.tsk.xml` 文件
4. 导入后手动关联 Profile 与 Task（设置 Profile → 选择触发任务）

### 第二步：调整路径配置

打开任意 Task，编辑 Termux:Tasker Action（Action 类型为 "Termux:Tasker"）：
- **Workdir**: `/data/data/com.termux/files/home/atlas-runtime`
- **Executable**: `/data/data/com.termux/files/usr/bin/bash`
- **Arguments**: `runtime/trigger_atlas.sh <your_json>`

### 第三步：授予 Tasker 必要权限

#### 系统权限
1. 无障碍服务（Settings → Accessibility → Tasker）
2. 通知监听（Settings → Notification Access → Tasker）
3. 后台运行权限（Settings → Apps → Tasker → Battery → Unrestricted）

#### ADB 授权（推荐一次性执行）
```bash
# 启用 Tasker 外部存储访问
adb shell pm grant net.dinglisch.android.taskerm android.permission.WRITE_SECURE_SETTINGS

# 启用通知监听（如系统设置入口不可用）
adb shell cmd notification allow_listener net.dinglisch.android.taskerm

# 授予 READ_LOGS（用于 Logcat 事件触发）
adb shell pm grant net.dinglisch.android.taskerm android.permission.READ_LOGS

# 授予 PACKAGE_USAGE_STATS（用于 App 状态检测）
adb shell pm grant net.dinglisch.android.taskerm android.permission.PACKAGE_USAGE_STATS
```

### 第四步：测试触发链

在 Tasker 中手动执行 "ATLAS: SIM切换" Task，观察是否：
1. Termux 收到执行请求
2. Atlas 日志中出现任务记录
3. `/sdcard/atlas_shared/last_result.json` 文件更新

---

## 配置文件说明

### Profile：定时触发 (profile_time.xml)

每日 08:55 自动执行 SIM 切换。可在 Tasker 中修改时间：编辑 Profile → 点击时间条件 → 调整。

关键属性：
- `<Time sr="con0">` — 时间上下文，`sr="con0"` 表示第一个 context
- `<fromh>08</fromh><fromm>55</fromm>` — 触发时间 08:55
- `flags="40"` — 推荐值，启用 Profile 通知但限制重复

### Profile：事件触发 (profile_event.xml)

收到来自 Messages/SMS 应用的通知时触发，使用 Tasker 原生 Notification 事件 (code=222)。如需更高级的过滤器（正则文本匹配、多应用监听等），可在导入后通过 Tasker UI 替换为 AutoNotification 插件事件。

关键属性：
- `<Event sr="con0">` — 事件上下文，`code="222"` = Notification Event（Tasker 原生）
- `arg0` — 监听的应用包名（默认 "Messages"），可在 Tasker UI 中修改

### Profile：状态触发 (profile_state.xml)

电量降到 20% 以下时触发 WiFi 关闭以节省电量。电量恢复时自动重新开启 WiFi。

关键属性：
- `<State sr="con0">` — 状态上下文，`code="39"` = WiFi Connected
- 变量 `%caller1` 区分 enter/exit：`%caller1=enter` 时连接 WiFi，`%caller1=exit` 时断开 WiFi

### Task：SIM 切换 (task_sim_switch.tsk.xml)

7 步操作序列（`sr="act1"～"act7"`）：
1. Variable Set — 构建 JSON `{"action":"sim_switch","params":{"slot":0},"correlation_id":"tasker_sim_%TIMES"}`
2. Termux:Tasker — 调用 `trigger_atlas.sh`（Plugin Action code="1342177284"）
3. Wait — 等待 5 秒
4. Read File — 读取 `last_result.json`
5. Variable Set + ConditionList — 检查 `%result` 是否已设置（`op="12"` = Is Set）
6. Variable Split + Variable Set — 解析 status 字段
7. Notify — 显示通知（code="559"）

### Task：WiFi 切换 (task_wifi_toggle.tsk.xml)

6 步操作序列：
1. Variable Set — 构建 JSON
2. WiFi Info — 检查当前 WiFi 状态（code="43"）
3. Variable Set + ConditionList — 根据 `%WIFII` 状态设置 toggle 值（`%WIFII ~ on` → toggle=off，反之亦然）
4. Termux:Tasker — 调用 trigger_atlas.sh
5. Wait — 等待 3 秒
6. Notify — 显示通知

### Task：通用触发 (task_trigger_universal.tsk.xml)

可复用的模板 Task。通过 `%par1` 传递 action 名称、`%par2` 传递 JSON 参数。

用法示例：
```
Perform Task "ATLAS: 通用触发"
  %par1 = "shell_command"
  %par2 = {"cmd":"echo hello"}
```

### Task：结果处理 (task_result_handler.tsk.xml)

从共享目录读取最新结果并展示通知。8 步操作序列包括 JSON 解析和条件分支（ConditionList `op="12"` Is Set + Variable Search Replace）。

---

## 导入要求

### Tasker 版本兼容性

所有 XML 文件使用 `tv="6.6.20"` 属性声明目标版本。Tasker 6.6.20 或更高版本可直接导入。较低版本（6.4.x～6.6.x）通常兼容，但以下 Action 可能需要调整：

- `code="1342177284"` — Termux:Tasker Plugin（要求插件已安装）
- `code="339"` — Variable Search Replace（6.0+ 支持）
- `ConditionList` 嵌套格式（6.0+ 标准，5.x 使用平面 If 格式）

### 文件导入顺序

1. 先导入 `atlas_trigger.prj.xml`（项目文件，自动包含所有 Profile 和 Task）
2. 如需单独使用，按需导入 `.prf.xml` 和 `.tsk.xml` 文件
3. Profile 导入后需手动关联到对应的 Task

### Termux 路径约束

所有脚本路径使用 Android Termux 规范：
- `workdir`: `/data/data/com.termux/files/home/atlas-runtime`
- `executable`: `/data/data/com.termux/files/usr/bin/bash`
- FIFO 路径: `$TMPDIR/atlas_fifo`
- 共享目录: `/sdcard/atlas_shared/`

---

## 依赖关系

```
atlas_trigger.prj.xml (项目入口)
├── profile_time.xml   → task_sim_switch.tsk.xml
├── profile_event.xml  → task_trigger_universal.tsk.xml
├── profile_state.xml  → task_wifi_toggle.tsk.xml
└── (所有 Task)        → task_result_handler.tsk.xml (回调)
```

外部依赖：
- **Atlas Runtime API**: `runtime/trigger_atlas.sh` — FIFO + HTTP 双通道触发
- **Termux:Tasker Plugin**: `com.termux.tasker` — Intents 桥梁
- **共享存储**: `/sdcard/atlas_shared/last_result.json` — 结果回传
- **高级可选**: AutoNotification 插件 (com.joaomgcd.autonotification) — 如需正则文本匹配或多应用通知过滤，导入后在 Tasker UI 中将 Profile 2 的 Event 替换为 AutoNotification Intercept

---

## 故障排除

| 问题 | 可能原因 | 解决 |
|------|----------|------|
| 导入失败 "Unsupported version" | Tasker 版本过低 | 升级至 Tasker 6.6.20 |
| Termux:Tasker 提示 "Plugin not found" | 插件未安装或版本不兼容 | 从 F-Droid 安装 `com.termux.tasker` |
| trigger_atlas.sh 返回 exit 4 | curl 连接失败，HTTP 服务未就绪 | 确保 Atlas HTTP 服务运行中 |
| trigger_atlas.sh 返回 exit 2 | FIFO 和 HTTP 双通道均失败 | 检查 Atlas 是否启动，`pgrep -f atlas` |
| Tasker 无法读取 last_result.json | 共享存储未授权 | 执行 `termux-setup-storage` |
| task_sim_switch 执行无效果 | Atlas 引擎未处理 SIM 切换指令 | 检查日志：`logs/scheduler.log` |
| Profile 不触发 | 无障碍/通知权限未授予 | 检查 Tasker → 偏好设置 → 监控 → 启用相关服务 |
| 三星设备 Tasker 进程被杀 | One UI 自动优化 | 将 Tasker 添加到 "不优化的应用" 列表 |

---

## 三星 One UI 8.5 特别说明

- Termux:Tasker 通过 `am startservice` 与 Termux 通信，三星 Knox 通常不会拦截此调用
- 如果任务执行"无响应"，检查 Tasker → 偏好设置 → "使用可靠告警" → "总是"
- 将 Tasker 的 "使用唤醒锁" 设置为 "当屏幕关闭时" 可提高后台可靠性
- 三星的 "自动优化" 功能可能杀死后台 Atlas 进程，建议在设备维护中将 Termux 添加到 "不优化的应用" 列表
- 如果导入时 XML 解析失败，检查文件是否包含 BOM 头（UTF-8 without BOM 为推荐编码）
