# Atlas Runtime v9.1 — Samsung S25 Plus 详细部署操作手册

版本: v1.0 | 日期: 2026-08-09 | 适用范围: Samsung S25 Plus (SM-S9360/SM-S936U), One UI 8.5, Android 16

本文档为 Atlas Runtime v9.1 在 Samsung S25 Plus 设备上的逐步骤部署指南，按操作顺序编排，每步包含操作指令、预期结果和异常处理方案。在执行前请通读全文，部署过程预计耗时 15-25 分钟（视网络速度而定）。

---

## 前置说明

### 设备初始状态要求

Samsung S25 Plus 设备已完成初始设置向导、已连接到 Wi-Fi 网络、已登录 Samsung Account、Google 账户已登录并可访问 Google Play Store、设备语言设为中文或英文均可（以下路径以中文界面为准，英文界面请对照翻译）、设备电量建议 >50%。

### 所需外部资源一览

以下文件需提前下载或确认可访问：

| 资源 | 用途 | 获取方式 |
|:---|:---|:---|
| F-Droid APK | Termux 系列组件分发 | `https://f-droid.org/` |
| Termux (F-Droid版) | Python 运行环境 | F-Droid 内搜索安装 |
| Termux:API (F-Droid版) | 硬件传感器访问 | F-Droid 内搜索安装 |
| Termux:Boot (F-Droid版) | 开机自启 | F-Droid 内搜索安装 |
| Tasker | 事件触发引擎 | Google Play 搜索安装 |
| AutoJS6 APK | UI 自动化 | Firebase App Distribution 或侧载 |
| Shizuku | 高权限操作代理 | Google Play 搜索安装 |
| Atlas Runtime 源码 | 核心运行时 | `git clone` 从 GitHub |

### 文档引用

本手册中引用的配置细节详见: `docs/DEPLOYMENT_PLAN.md`、`docs/SAMSUNG_ONEUI85_COMPAT.md`、`docs/TASKER_INTEGRATION_GUIDE.md`、`docs/AUTOJS6_SCRIPT_GUIDE.md`、`docs/ARCHITECTURE.md`、`config/runtime.yaml`。

---

## 第一阶段：设备兼容性检查（部署前）

此阶段在设备上直接操作，不依赖任何已安装的开发工具，仅使用系统自带功能。全部 4 项检查通过后方可进入第二阶段的软件安装。

### 步骤 1：确认设备型号与 SoC 平台

操作: 打开"设置 → 关于手机"，查看"型号"字段。

预期结果: 显示 "SM-S9360"（中国/亚太版）或 "SM-S936U"（北美版）。两者均为 Samsung S25 Plus，Atlas Runtime 全功能支持。

异常处理:
- 若型号显示为 SM-S9380/SM-S938U：此为 S25 Ultra 机型，同样在 Tier 1 全功能验证范围内，可继续部署。
- 若型号显示为 SM-S9310/SM-S931U：此为 S25 标准版（RAM 12GB，3120×1440 屏幕），同样在 Tier 1 范围内，可继续部署。
- 若型号显示为 SM-S9260/SM-S9280 等 S24 系列：在 Tier 1 范围内，但需注意 One UI 7.1 而非 8.5，部分 Samsung service call 事务码可能不同。继续部署前请先查阅 `SAMSUNG_ONEUI85_COMPAT.md` 第 3.4 节的事务码验证方法。
- 若型号为其他非 Samsung 设备：进入 Tier 2 或 Tier 3 兼容路径，请转至 `DEPLOYMENT_PLAN.md` 第 1.2 节查看对应级别的功能限制和适配策略。本手册后续步骤中的 Samsung 特定操作（电池优化白名单、Game Booster 例外等）不再适用。

操作: 在同一页面查看"处理器"字段。

预期结果: "Snapdragon 8 Gen 4 for Galaxy" 或 "Exynos 2500"（取决于销售区域）。两者均为 ARM64-v8a 架构（`ro.product.cpu.abi` = arm64-v8a），完全符合 Atlas Runtime 的架构要求。

### 步骤 2：确认操作系统与 One UI 版本

操作: "设置 → 关于手机 → 软件信息"，查看 "One UI 版本" 和 "Android 版本"。

预期结果: One UI 版本为 8.5，Android 版本为 16。

异常处理:
- 若 One UI 版本低于 8.5（如 8.0 或 7.1）：基本功能可用，但 `config/runtime.yaml` 中预设的 Samsung service call 事务码（wifi_enable: 55, data_enable: 77, airplane_on: 98）可能需要调整。部署后需执行手动事务码验证（见步骤 20）。
- 若 Android 版本为 15：在 Tier 1 范围内（S24 系列基准），全功能可用。但 Samsung 的电池管理策略可能与 Android 16 有差异，部署后需特别关注后台保活表现（见步骤 18）。
- 若系统有可用更新提示：建议先完成系统更新（"设置 → 软件更新 → 下载并安装"），再继续部署。Atlas Runtime 的兼容性以更新后的版本为准。

操作: 在"软件信息"页面向下滑动，查看"内核版本"。

预期结果: 内核版本为 6.1 系列（Android Common Kernel）。此为 Android 16 的标准内核基线，确保 `/proc/meminfo`、`/sys/class/power_supply/` 等伪文件系统行为一致。

### 步骤 3：确认硬件规格（RAM、存储空间、屏幕分辨率）

操作: "设置 → 设备维护 → 存储"。查看"可用空间"。

预期结果: 可用空间 >1GB。S25 Plus 基础存储为 256GB 或 512GB，系统预装占用约 30-35GB，在正常使用后应仍有充足空间。

异常处理:
- 若可用空间在 500MB-1GB 之间：满足最低要求，可继续部署。但部署完成后需监控日志轮转是否正常（`logs/` 目录增长），建议清理部分文件释放空间。用于生产的自动化场景，存储空间不足可能导致 SQLite 写入失败并触发只读保护模式。
- 若可用空间 <500MB：不满足最低要求。部署前需清理空间。可通过"设置 → 设备维护 → 存储 → 清理"释放缓存文件，或卸载不常用应用。若无法释放至 500MB 以上，可选择不安装可选组件（PWA 监控面板、AutoJS6）以缩减占用，仅部署 Core + Termux 基础环境（约 200MB）。

操作: "设置 → 设备维护 → 内存"。查看"RAM"总量和当前可用。

预期结果: 总 RAM 12GB（LPDDR5X），当前可用应 >4GB（正常使用状态下）。S25 Plus 的 RAM 配置远超 Atlas Runtime 推荐配置（6GB+），即使在 5 并发高负载场景下也无 OOM 风险。

操作: "设置 → 显示 → 屏幕分辨率"。确认当前分辨率设置。

预期结果: QHD+ (3120×1440)。若用户为省电设置为 FHD+ (2340×1080)，同样可用——AutoJS6 控件识别基于实际渲染分辨率自适应，`device/detector.py` 启动时会通过 `wm size` 获取真实分辨率。但建议部署验证阶段使用 QHD+ 以测试高 DPI 下的控件识别效果，日常使用可按需切换。

### 步骤 4：确认 Knox 版本

操作: "设置 → 关于手机 → 软件信息 → Knox 版本"。

预期结果: Knox 3.12 或更高版本。Atlas Runtime 的高权限操作通过 Shizuku/Rish 绕过 Knox 限制，无需 Knox SDK 授权。但需注意以下 Knox 不可绕过的限制——安全文件夹内的应用不可通过无障碍服务操作；KNOX 工作配置文件与个人资料的数据隔离不可穿透；SE for Android (SEAndroid) 策略不可修改（如 `/sys/class/net/wlan0/` 的写入权限）。若部署场景涉及企业 KNOX 工作配置文件，需将 Atlas Runtime 安装在个人资料分区中。

---

## 第二阶段：基础软件安装

此阶段安装 Atlas Runtime 运行所需的全部外部应用。按顺序安装，因为后续步骤依赖前置安装结果。

### 步骤 5：安装 F-Droid 应用商店

操作: 打开 Samsung Internet 浏览器，访问 `https://f-droid.org/`，点击"下载 F-Droid"按钮。下载完成后，从通知栏点击 APK 文件，按系统提示完成安装。在 Samsung 设备上可能弹出"未知来源"警告——点击"设置" → 开启"允许从此来源安装"（Samsung Internet）→ 返回继续安装。

预期结果: F-Droid 应用图标出现在应用抽屉中。打开 F-Droid，应显示应用列表并可正常浏览。

异常处理:
- 若三星安全警告阻止安装：进入"设置 → 安全和隐私 → 更多安全设置 → 安装未知应用"，找到 Samsung Internet 或文件管理器，开启"允许从此来源安装"，后重新执行安装。
- 若 F-Droid 下载缓慢：F-Droid 服务器位于境外，中国区用户可访问 `https://mirrors.tuna.tsinghua.edu.cn/fdroid/repo/` 获取 F-Droid 和 Termux APK 的国内镜像下载链接。

### 步骤 6：从 F-Droid 安装 Termux、Termux:API、Termux:Boot

操作: 打开 F-Droid，在搜索栏依次搜索并安装以下三个应用。注意：必须从 F-Droid 安装，不可从 Google Play 安装 Termux（Google Play 版本已停止更新且缺少 `termux-api` 包）。

安装顺序: Termux（基础终端）→ Termux:API（硬件接口）→ Termux:Boot（开机自启）。

预期结果: 三个应用均在应用抽屉中可见。打开 Termux，应显示终端界面，命令提示符为 `$`。首次启动 Termux 可能需要 10-30 秒完成初始化（下载 bootstrap 包）。

异常处理:
- 若 Termux 启动时长时间卡在 "Setting up..." 界面：网络连接问题导致 bootstrap 包下载失败。断开 Wi-Fi 切换到移动数据重试，或通过 `termux-change-repo` 切换到清华镜像源（启动后在 Termux 中执行 `termux-change-repo`，选择 "Mirrors by Tsinghua University"）。
- 若 F-Droid 搜索不到 Termux:API：在 F-Droid 设置中确认已启用 "F-Droid Archive" 仓库（设置 → 仓库 → 确保 F-Droid 和 F-Droid Archive 均已勾选）。
- 若 Termux 安装后启动闪退：可能是 Samsung Game Booster 误将 Termux 识别为游戏。暂时在 Game Launcher → 更多 → Game Booster → 关闭 Game Booster，待部署完成后再将 Termux 加入例外列表。

### 步骤 7：从 Google Play 安装 Tasker

操作: 打开 Google Play Store，搜索 "Tasker"，点击安装。Tasker 提供 7 天免费试用，后续购买费用为 $3.49。同步安装 Termux:Tasker 插件（搜索 "Termux:Tasker" 安装，此插件是 Tasker 与 Termux 通信的桥梁）。

预期结果: Tasker 和 Termux:Tasker 均显示"已安装"。打开 Tasker，应显示主界面（Profiles/Tasks/Scenes/Vars 四个标签页）。

异常处理:
- 若 Google Play 显示"您的设备与此版本不兼容"：确认 Google Play Services 已更新至最新版本（"设置 → 关于手机 → 软件信息 → Google Play 系统更新"）。
- 若 Tasker 安装后打开提示"无障碍服务未开启"：暂时跳过，权限配置将在第三阶段统一处理。
- 若 Termux:Tasker 插件安装后 Tasker 中找不到：重启 Tasker 应用，插件由 Tasker 自动发现。

### 步骤 8：安装 AutoJS6（通过 Firebase App Distribution 或侧载）

操作: 若已收到 Firebase App Distribution 邀请邮件，在设备上打开邀请链接 → 接受邀请 → 下载并安装 AutoJS6 APK。若无邀请，从团队提供的 Google Drive / 内部网盘链接下载最新 AutoJS6 APK 文件，通过 Samsung 文件管理器打开安装。

预期结果: AutoJS6 图标出现在应用抽屉中。打开 AutoJS6，应显示脚本列表主界面。

异常处理:
- 若安装时提示"应用未安装"：检查是否已卸载旧版 AutoJS6（不同签名版本的 AutoJS6 无法覆盖安装）。进入"设置 → 应用 → AutoJS6"卸载旧版，重新安装新版。
- 若安装时提示"风险应用"：此为三星安全警告，因为 AutoJS6 并非通过 Play Store 分发。点击"仍然安装"继续。此应用仅用于合法的自动化操作。
- 若 Firebase 邀请链接在 Samsung Internet 中无法打开：复制链接到 Chrome 浏览器中打开。
- 若侧载 APK 文件无法找到：使用 Samsung 文件管理器（"我的文件"App），在"下载"目录中查找 APK 文件。

### 步骤 9：安装 Shizuku（SIM 切换等高权限操作代理）

操作: 打开 Google Play Store，搜索 "Shizuku"，安装。

预期结果: Shizuku 图标出现在应用抽屉中。暂时不启动，后续步骤中将通过 ADB 或无线调试激活。

异常处理:
- 若 Google Play 搜索不到 Shizuku：Shizuku 在部分区域的 Play Store 中可能有区域限制。可从 GitHub Releases 侧载安装（`https://github.com/RikkaApps/Shizuku/releases`）。
- 若安装后 Shizuku 提示 "需要 ADB 权限"：此为正常状态，Shizuku 启动依赖 ADB/无线调试。跳至步骤 14 处理。

---

## 第三阶段：安全权限配置

此阶段授予 Atlas Runtime 运行所需的全部 Android 系统权限。权限按重要性排序，前三项（电池优化、无障碍服务、通知监听）为生产环境必需。

### 步骤 10：关闭 Termux 和 Tasker 的电池优化

操作: "设置 → 应用 → Termux → 电池 → 选择'不受限制'"。同样路径设置 Tasker → 电池 → 不受限制。同样路径设置 AutoJS6 → 电池 → 不受限制。

操作（Samsung 特有）: "设置 → 设备维护 → 电池 → 后台使用限制" → 将 Termux、Tasker、AutoJS6 添加到"不进入休眠的应用"列表。同时关闭"自适应电池"和"将未使用的应用置于休眠"功能——或者至少将这三个应用添加到例外列表。

预期结果: 三个应用的电池设置均显示为"不受限制"，且在设备维护中列为"永不休眠"。

异常处理:
- 若找不到"不受限制"选项：Android 16 / One UI 8.5 中可能更名为"无限制"。在任何情况下选择最宽松的选项。
- 若关闭"自适应电池"后担心整机续航：可保留"自适应电池"功能，但必须手动将 Termux、Tasker、AutoJS6 加入"不进入休眠的应用"列表（在"设备维护 → 电池 → 后台使用限制 → 深度休眠应用"中确认这三个应用不在列表中）。
- 若 Termux 不在"后台使用限制"的应用列表中：先在 Termux 中执行任意操作（如 `pkg update`），使其出现在后台活动应用列表中。

### 步骤 11：开启无障碍服务（AutoJS6 UI 自动化）

操作: "设置 → 辅助功能 → 已安装的应用 → AutoJS6 → 开启"。系统弹出权限确认对话框，点击"允许"。

预期结果: AutoJS6 的无障碍服务状态显示为"已开启"。在 AutoJS6 应用中，无障碍服务图标变为绿色（或显示"无障碍服务已连接"）。

异常处理:
- 若 AutoJS6 在"已安装的应用"列表中找不到：下拉列表到底部，查看"更多"或"其他应用"分组。Samsung One UI 有时将第三方应用隐藏在下拉列表的底部。
- 若开启后立即自动关闭：进入"设置 → 应用 → AutoJS6 → 强制停止"，然后重新打开 AutoJS6 并再次尝试开启无障碍服务。
- 若开启后弹出"检测到安全问题"警告：此为 Samsung Knox 的正常行为（AutoJS6 的无障碍服务权限较高）。此服务仅用于合法的 UI 自动化操作，确认"仍要开启"继续。
- 若提示"此服务与 Samsung 辅助功能冲突"：检查是否开启了 Samsung 自家的辅助功能（如 Assistant Menu、Universal Switch），暂时关闭后再开启 AutoJS6 无障碍服务。

### 步骤 12：开启 Tasker 通知监听权限

操作: "设置 → 通知 → 高级设置 → 通知使用权 → Tasker → 开启"。

预期结果: Tasker 的通知监听权限为"已授权"。在 Tasker 应用的偏好设置中，通知监听状态应显示为"活跃"。

异常处理:
- 若 Tasker 不在通知使用权列表中：确保已在 Google Play 安装最新版 Tasker（v6.6+，推荐 v6.6.20）。重启设备后重新检查。
- 若开启后提示"此权限可能影响隐私"：此为标准系统提示，Tasker 使用此权限仅用于读取 SMS/Messages 通知内容以触发自动化 Profile。确认开启。

### 步骤 13：授予 Termux 存储访问权限

操作: 打开 Termux 应用，在终端中输入以下命令：

```bash
termux-setup-storage
```

系统弹出权限请求对话框，点击"允许"。

验证: 输入 `ls /sdcard/` 应显示 Android 共享存储的目录列表。输入 `ls ~/storage/` 应显示 `dcim`、`downloads`、`shared` 等符号链接。

预期结果: Termux 可正常读写 `/sdcard/` 目录。后续将创建 `/sdcard/atlas_shared/` 共享目录用于 Tasker 和 AutoJS6 跨进程数据交换。

异常处理:
- 若执行 `termux-setup-storage` 后无权限弹窗：进入"设置 → 应用 → Termux → 权限 → 文件和媒体"，手动选择"允许管理所有文件"。返回 Termux 重新执行 `termux-setup-storage`。
- 若 `ls ~/storage/shared` 显示 "Permission denied"：再次执行 `termux-setup-storage`，确保权限弹窗中点击了"允许"而非"拒绝"。Android 的存储权限可能需要在每次 Termux 更新后重新授予。

### 步骤 14：配置 Samsung 特定优化项

操作（Game Booster 例外）: 若使用 Game Booster 功能，打开 "Game Launcher → 更多 → Game Booster → 实验室" → 将 Termux 添加到"不优化的应用"列表。Game Booster 可能误判 Termux 的进程行为为游戏进程，从而限制其后台 CPU 使用率。

操作（RAM Plus 虚拟内存）: "设置 → 设备维护 → 内存 → RAM Plus"，选择 4GB 或 8GB 档位。RAM Plus 利用 UFS 4.0 存储空间提供额外虚拟内存，降低极端内存压力下 Termux 进程被 LMK (Low Memory Killer) 杀死的概率。

预期结果: Game Booster 中 Termux 被标记为例外。RAM Plus 已设置为 4-8GB（设备需要重启后生效）。

异常处理:
- 若 Game Booster 实验室中没有"不优化的应用"选项：更新 Game Booster 至最新版本（通过 Galaxy Store）。
- 若 RAM Plus 选项为灰色不可选：确保存储可用空间 >（所选 RAM Plus 大小 + 2GB），否则系统会阻止设置。先清理存储空间。

---

## 第四阶段：Termux 环境配置

此阶段在 Termux 终端中执行全部命令。注意：所有命令均区分大小写，路径中的 `/data/data/com.termux/files/` 为 Termux 在 Android 文件系统中的固定前缀。

### 步骤 15：更新 Termux 包索引与基础环境

操作: 在 Termux 中依次执行以下命令：

```bash
pkg update -y && pkg upgrade -y
```

此命令更新所有已安装的 Termux 包至最新版本。首次执行可能需要 2-5 分钟。

预期结果: 所有包更新完成，无错误输出。最后一行为 `The packages were upgraded successfully` 或类似信息。

异常处理:
- 若更新过程中网络中断：重新执行 `pkg update -y && pkg upgrade -y`。Termux 的 pkg 命令具有断点续传能力，中断后可安全重试。
- 若出现 `repository is not signed` 错误：执行 `termux-change-repo`，选择"Mirrors by Tsinghua University"（中国区）或 "Main Repository"（国际），然后重新执行更新。
- 若 `pkg` 下载速度极慢（<100KB/s）：执行 `termux-change-repo` 切换到离用户最近的镜像源。在中国区推荐清华镜像，在国际区推荐默认的 IPFS 镜像。

操作: 更新 Python（若版本低于 3.11）：

```bash
pkg install python -y
python3 --version
```

预期结果: `python3 --version` 输出 "Python 3.11.x" 或 "Python 3.12.x"。Atlas Runtime v9.1 要求 Python >=3.11（依赖 `asyncio.TaskGroup` 等新特性）。

异常处理:
- 若 `python3 --version` 输出低于 3.11：执行 `pkg uninstall python -y && pkg install python -y` 强制重新安装最新版。
- 若 `pkg install python` 提示冲突：执行 `pkg install python --upgrade` 升级而非全新安装。

### 步骤 16：安装必需工具链包

操作: 在 Termux 中执行：

```bash
pkg install git curl jq termux-api termux-services -y
```

此命令一次性安装 5 个核心依赖。git（代码克隆）、curl（HTTP 请求和健康检查）、jq（JSON 解析）、termux-api（硬件传感器访问）、termux-services（runit 守护进程）。

预期结果: 5 个包均安装成功。验证：

```bash
command -v git && echo "git OK"
command -v curl && echo "curl OK"
command -v jq && echo "jq OK"
command -v termux-battery-status && echo "termux-api OK"
which sv && echo "sv OK"
```

所有命令应均有输出，无 "command not found" 错误。

异常处理:
- 若 `termux-battery-status` 未找到：termux-api 包包含命令行工具，但同时需要安装 Termux:API APK（步骤 6）。确认 Termux:API APK 已安装，然后重启 Termux（`exit` 后重新打开）。
- 若 `sv` 命令未找到：执行 `source $PREFIX/etc/profile` 加载 runit 环境变量。若无效，关闭并重新打开 Termux（首次安装 termux-services 后需重启 Termux 才能自动加载 runit 环境）。
- 若安装 `termux-services` 时包下载失败：尝试 `pkg install termux-services -y --force` 强制覆盖缓存。

### 步骤 17：配置 Python pip 镜像源（推荐，中国区用户）

操作: 在 Termux 中执行：

```bash
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

此操作将 pip 默认源切换至清华大学镜像，大幅提升中国区用户的依赖安装速度（从国际源约 50KB/s 提升至 10-50MB/s）。

预期结果: 执行 `pip config list` 应显示 `global.index-url='https://pypi.tuna.tsinghua.edu.cn/simple'`。

异常处理:
- 若非中国区用户：跳过此步，保持默认 PyPI 源即可。国际用户使用默认源速度正常。
- 若清华镜像不可用：可临时使用阿里镜像 `https://mirrors.aliyun.com/pypi/simple/` 或中科大镜像 `https://pypi.mirrors.ustc.edu.cn/simple/`。

### 步骤 18：安装 Python 运行时依赖

操作: 在 Termux 中按以下顺序执行（先安装 pkg 预编译包以节省时间，再通过 pip 安装纯 Python 包）：

```bash
# 第一步：通过 pkg 安装预编译二进制包（速度快，省编译时间）
pkg install python-psutil -y 2>/dev/null || true

# 第二步：通过 pip 安装核心依赖
pip install --quiet aiosqlite msgpack pyyaml aiohttp
```

预期结果: 所有依赖安装成功无报错。验证：

```bash
python3 -c "import aiosqlite; import msgpack; import yaml; import aiohttp; print('All imports OK')"
```

应输出 "All imports OK"。

异常处理:
- 若 `pip install` 时出现 `fatal error: Python.h: No such file or directory`：说明缺少 Python 开发头文件。执行 `pkg install python-dev -y` 后重试 pip 安装。
- 若 `aiohttp` 安装失败（在 Exynos 2500 设备上可能因 C 扩展编译超时，需要 5-10 分钟）：使用 `pip install aiohttp --only-binary=:all:` 尝试安装预编译轮子。若轮子不可用，耐心等待编译完成，这是 Exynos 设备的正常现象。
- 若 `msgpack` 安装失败：执行 `pkg install clang -y` 确保 C 编译器可用后重试。

---

## 第五阶段：网络连接与 Shizuku 配置

### 步骤 19：激活 Shizuku（高权限操作代理）

Atlas Runtime 的 SIM 切换、WiFi/Data 控制等操作通过 Shizuku/Rish 代理实现，无需 root 权限。Samsung S25 Plus 推荐使用无线调试方式启动 Shizuku。

操作:
1. "设置 → 开发者选项 → 无线调试 → 开启"。
   - 若未启用开发者选项：前往"设置 → 关于手机 → 软件信息 → 连续点击 7 次'版本号'"以启用。
2. 在无线调试页面点击"使用配对码配对设备"，记下显示的 IP 地址、端口和 Wi-Fi 配对码。
3. 打开 Shizuku 应用，选择"通过无线调试启动" → "配对"，输入步骤 2 中显示的配对码。
4. 配对成功后返回 Shizuku，点击"启动"按钮。

验证: Shizuku 应用主页显示"Shizuku 正在运行"，版本号旁状态为绿色圆点。

预期结果: Shizuku 服务已启动并运行。在 Termux 中执行以下命令验证 Rish 可用：

```bash
# Shizuku 安装后 Rish 脚本默认位于 /sdcard/Android/data/moe.shizuku.privileged.api/files/
# 创建 Rish 快捷链接到 Atlas 期望的路径
mkdir -p ~/.atlas_sentinel/bin
cp /sdcard/Android/data/moe.shizuku.privileged.api/files/rish ~/.atlas_sentinel/bin/rish 2>/dev/null || true
chmod +x ~/.atlas_sentinel/bin/rish 2>/dev/null || true
```

异常处理:
- 若在开发者选项中找不到"无线调试"：Android 11+ / One UI 3.0+ 均支持无线调试。若选项不存在，确认 Android 系统版本为 16 且 Google Play Services 已更新。
- 若配对后 Shizuku 显示"未授权"：重新执行配对步骤。注意配对码区分大小写，且有效期为 5 分钟。
- 若 Shizuku 每隔几分钟自动停止：Samsung 电池优化可能在杀死 Shizuku 后台进程。进入"设置 → 应用 → Shizuku → 电池 → 不受限制"。进入"设备维护 → 电池 → 后台使用限制 → 将 Shizuku 添加到不进入休眠的应用列表"。
- 若 Rish 脚本路径不在上述位置：在 Shizuku 应用中，进入"设置 → 已授权的应用 → 资源"页面查看 Rish 脚本的确切路径。
- 若部署场景不需要 SIM 切换、WiFi/Data 控制等高权限操作：Shizuku 为可选组件。跳过此步骤，Atlas Runtime 的核心功能（Shell 执行、FIFO 通信、HTTP 服务、健康检查）不受影响。`config/runtime.yaml` 中的 `shizuku_sim` 段将在启动时静默跳过。

---

## 第六阶段：Atlas Runtime Core 部署

此阶段执行 `service/deploy.sh` 一键部署脚本，完成代码克隆、服务注册和启动的全部步骤。

### 步骤 20：执行 deploy.sh 部署脚本

操作: 在 Termux 中执行以下命令：

```bash
# 首次部署：直接通过 curl 拉取部署脚本并执行
cd ~
bash <(curl -s https://raw.githubusercontent.com/izualchou/atlas-runtime/main/service/deploy.sh)
```

若 curl 方式不可用（如网络限制），使用备选方案——先 git clone 再执行本地的 deploy.sh：

```bash
# 备选方案
cd ~
git clone --depth 1 https://github.com/izualchou/atlas-runtime.git ~/atlas-runtime-temp
bash ~/atlas-runtime-temp/service/deploy.sh
```

Gitee 镜像（中国区推荐）:

```bash
cd ~
git clone --depth 1 https://gitee.com/izualchou/atlas-runtime.git ~/atlas-runtime-temp
bash ~/atlas-runtime-temp/service/deploy.sh
```

预期结果: deploy.sh 按顺序执行 14 个步骤（详见 `service/deploy.sh` 源代码中的 `print_step` 标注），最终输出：

```
╔══════════════════════════════════════════════════════════╗
║   Atlas Runtime v9.1 — 部署完成！                       ║
╚══════════════════════════════════════════════════════════╝

注意：v9.1 版 deploy.sh 已在步骤 9 中自动创建 runit 的 `supervise/` 目录结构（含 `ok`、`control`、`status` 文件）及 `log/run` 日志管线脚本，从根源上杜绝了 "supervise/ok 文件不存在" 的错误。如果你正在阅读一份提及 v9.0 的旧版文档，请升级至仓库最新版本后重新部署。
```

最后几行输出应包含验证命令提示，如 `sv status atlas-runtime` 和 `curl http://127.0.0.1:8787/health`。

异常处理——按步骤号对应：

步骤 1（Samsung 设备检测失败）: 脚本检测 `ro.product.manufacturer` 时返回 "unknown"。原因通常是 Termux 无权限读取系统属性。这是 Samsung Knox 的正常行为——`getprop` 的部分属性被 Knox 隐藏。不影响部署继续，但部署后需手动将 `config/runtime.yaml` 中 `platform` 段的 `prefer_termux_api` 设为 `true`（强制使用 termux-api 而非 dumpsys 回退）。同时 Samsung service call 事务码可能需要手动验证——在 Termux 中执行 `service list | grep isub` 确认事务码列表，与 `runtime.yaml` 中预设的 `wifi_enable: 55` 等值对比。若不一致，修改配置文件中 `samsung_service_codes` 段的对应值。

步骤 3（termux-api 不可用）: `pkg install termux-api` 成功但 `termux-battery-status` 仍不可用。确认 Termux:API APK（在步骤 6 中安装的）已授予 Termux 相关权限——"设置 → 应用 → Termux:API → 权限 → 确保'传感器'和'电池'权限已开启"。然后强制停止 Termux 并重新打开（`exit` + 从启动器重新打开）。

步骤 5（Python < 3.11 升级失败）: 执行 `pkg uninstall python -y && pkg clean && pkg install python -y` 完全清理后重新安装。若仍为旧版本，可能是 Termux 的软件源未更新。执行 `pkg update -y` 后重试。

步骤 6（git clone 失败）: 网络超时或 DNS 无法解析 `github.com`。在中国区尝试 Gitee 镜像。若镜像也失败，从电脑下载 `https://github.com/izualchou/atlas-runtime/archive/refs/heads/main.zip`，通过 USB 传输到设备 `~/storage/downloads/`，然后在 Termux 中执行 `unzip ~/storage/downloads/main.zip -d ~/ && mv ~/atlas-runtime-main ~/atlas-runtime`。后续更新需走热更新流程（git fetch 不可用时可重新下载 zip 覆盖）。

步骤 9（runit 服务注册失败）: `sv-enable atlas-runtime` 提示 "command not found"。首先执行 `source $PREFIX/etc/profile` 加载环境变量。若仍不可用，关闭 Termux 并重新打开（termux-services 安装后首次需要重启）。若 sv 命令存在但注册失败，查看 `/data/data/com.termux/files/usr/var/log/atlas-runtime/current` 日志获取详细错误信息。

步骤 13（服务启动失败）: `sv up atlas-runtime` 执行后 `sv status` 显示 "down: ..." 而非 "run: ..."。查看运行日志：

```bash
tail -50 /data/data/com.termux/files/usr/var/log/atlas-runtime/current
```

常见原因包括：Python 依赖缺失（执行 `pip install -r ~/atlas-runtime/requirements.txt` 手动安装）、端口 8787 被占用（执行 `fuser -k 8787/tcp` 释放端口后重启）、配置文件格式错误（检查 `config/runtime.yaml` 的 YAML 缩进）、compatibility stubs 缺失（确认 core/ 下三个 re-export 存根文件存在）。如果日志显示 import 错误，逐一确认 `pip list` 中所有依赖均已安装。

步骤 13-F（supervise/ok 文件缺失——"无法打开 supervise/ok 文件，因为该文件不存在"）:

这是 runit 的 supervise 目录未正常初始化的典型错误。runit 使用 `supervise/` 子目录中的 `ok`、`control`、`status` 和 `lock` 文件来管理服务进程的监控状态。当这些文件不存在时，`sv-enable` 和 `sv up` 均会失败。

此问题的根因有两个层面：(1) v9.0 版 `deploy.sh` 在步骤 9 中未预创建 `supervise/` 目录及其 `ok` 文件，导致 `sv-enable` 调用时 runit 无法找到必需的监控文件；(2) 如果之前曾手动停止或删除过服务，`supervise/` 目录可能被 `sv-disable` 清理或残留了孤儿锁文件。

v9.1 修复版 `deploy.sh` 已在步骤 9 中自动创建完整的 supervise 目录结构。如果你正在使用 v9.0 版脚本或遇到已有部署的 supervise 损坏问题，请按以下步骤手动修复：

修复操作（在 Termux 中逐条执行）：

```bash
# 1. 定义路径变量
SVC_DIR=/data/data/com.termux/files/usr/var/service/atlas-runtime
LOG_DIR=/data/data/com.termux/files/usr/var/log/atlas-runtime

# 2. 确保 supervise 目录存在
mkdir -p "$SVC_DIR/supervise"
mkdir -p "$LOG_DIR/supervise"

# 3. 创建 ok/control/status 文件（runit 三要素）
touch "$SVC_DIR/supervise/ok"
touch "$SVC_DIR/supervise/control"
touch "$SVC_DIR/supervise/status"
touch "$LOG_DIR/supervise/ok"
touch "$LOG_DIR/supervise/control"

# 4. 清理可能残留的锁文件（防止 "supervise/ok: already locked" 警告）
rm -f "$SVC_DIR/supervise/lock"
rm -f "$LOG_DIR/supervise/lock"

# 5. 确认 run 脚本存在且可执行
ls -la "$SVC_DIR/run"
# 预期: -rwxr-xr-x ... run

# 6. 确认 log/run 脚本存在（日志管线）
ls -la "$SVC_DIR/log/run" 2>/dev/null || {
    # 若不存在，创建 log/run
    mkdir -p "$SVC_DIR/log"
    cat > "$SVC_DIR/log/run" << 'EOF'
#!/data/data/com.termux/files/usr/bin/bash
exec svlogd -tt /data/data/com.termux/files/usr/var/log/atlas-runtime
EOF
    chmod +x "$SVC_DIR/log/run"
    echo "log/run 已创建"
}

# 7. 验证 supervise 目录完整性
echo "=== 服务 supervise 目录 ==="
ls -la "$SVC_DIR/supervise/"
echo "=== 日志 supervise 目录 ==="
ls -la "$LOG_DIR/supervise/"
echo "=== run 脚本 ==="
ls -la "$SVC_DIR/run"
echo "=== log/run 脚本 ==="
ls -la "$SVC_DIR/log/run"

# 8. 重新启动服务
sv enable atlas-runtime
sv up atlas-runtime
sleep 3
sv status atlas-runtime
# 预期: run: atlas-runtime: (pid XXXX) XXs
```

异常处理（修复后仍失败的情况）：

- 若 `sv enable` 返回 "warning: atlas-runtime: can't create supervise/ok: file does not exist"：这表明 `supervise/` 目录本身不存在或路径不对。执行 `ls -la "$SVC_DIR/"` 查看服务目录内容，确认路径中存在 `supervise` 子目录。在极端情况下，请执行 `rm -rf "$SVC_DIR" && mkdir -p "$SVC_DIR/supervise"` 完全重建服务目录后重新执行上述步骤 3-8。

- 若 `sv status` 显示 "fail: ..." 或 "down: ..." 但 supervise 文件已就绪：服务进程本身崩溃，与 supervise 无关，应查阅运行日志 `tail -50 "$LOG_DIR/current"` 排查 Python 或配置层面的错误。

- 若 `sv status` 长时间显示 "run: ... (pid XXXX) 0s" 且秒数不增长：runsv 在反复启动进程（进程每次都立即退出）。执行 `cat "$LOG_DIR/current"` 查看最近的错误输出，通常是 Python 导入错误或端口冲突。

### 步骤 21：验证部署完整性

操作: 在 Termux 中依次执行以下验证命令：

```bash
# 1. 服务状态
sv status atlas-runtime
# 预期输出: run: atlas-runtime: (pid 12345) 5s; ...

# 2. 健康检查端点
curl -s http://127.0.0.1:8787/health | python3 -m json.tool
# 预期输出: JSON 对象，status 字段值为 "healthy"

# 3. 就绪检查端点
curl -s http://127.0.0.1:8787/ready
# 预期输出: OK 或 Ready

# 4. FIFO 管道存在性
ls -la /data/data/com.termux/files/usr/tmp/atlas_trigger.fifo
# 预期输出: 文件名后显示 p（表示命名管道），权限为 rw-rw-rw-

# 5. 版本信息
curl -s http://127.0.0.1:8787/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Version: {d.get(\"version\",\"unknown\")}')"
# 预期输出: Version: 9.1.x
```

预期结果: 全部 5 项验证通过。若任一验证失败，执行异常处理流程。

异常处理:
- 验证 1 失败（sv status 非 run 状态）: 执行 `sv up atlas-runtime` 手动拉起。若仍失败，跳至步骤 20 的步骤 13 异常处理查阅日志。
- 验证 2 失败（curl 无响应）: HTTP 端口未就绪。`sleep 5` 后重试，Atlas 启动需要 2-5 秒完成 bootstrap 全部 16 个步骤。若 3 次重试（共 15 秒）后仍无响应，检查日志 `tail -20 /data/data/com.termux/files/usr/var/log/atlas-runtime/current`。
- 验证 4 失败（FIFO 不存在）: 手动创建：`rm -f /data/data/com.termux/files/usr/tmp/atlas_trigger.fifo && mkfifo /data/data/com.termux/files/usr/tmp/atlas_trigger.fifo && chmod 666 /data/data/com.termux/files/usr/tmp/atlas_trigger.fifo`，然后重启服务：`sv restart atlas-runtime`。

---

## 第七阶段：Tasker 集成配置

### 步骤 22：导入 Atlas Trigger Tasker 项目

操作:
1. 打开 Tasker 应用，切换到"任务"标签。
2. 长按底部"任务"按钮或右下角加号按钮旁的菜单 → 选择"导入项目"。
3. 在文件选择器中导航至 `~/atlas-runtime/config/tasker/atlas_trigger.prj.xml`，选择并确认导入。

注意：导入路径需通过 Termux 的共享存储访问。若 Tasker 文件选择器无法直接访问 Termux 的 home 目录，先将项目文件复制到共享存储：

```bash
# 在 Termux 中执行
cp ~/atlas-runtime/config/tasker/atlas_trigger.prj.xml /sdcard/atlas_shared/
```

然后在 Tasker 文件选择器中导航至 `/sdcard/atlas_shared/atlas_trigger.prj.xml`。

预期结果: 项目 "Atlas Trigger" 出现在 Tasker 的 Profiles/Tasks 列表中。项目包含 3 个 Profile（定时触发、事件触发、状态触发）和 4 个 Task（SIM 切换、WiFi 切换、通用触发、结果处理）。所有 XML 文件的 `tv` 版本属性均为 `"6.6.20"`，与 Tasker v6.6.20 完全兼容。

异常处理:
- 若 Tasker 提示"不支持的版本"：说明 Tasker 版本过低。所有 XML 文件使用 `tv="6.6.20"` 格式，需 Tasker 6.6.20 或更高版本。请从 Google Play 更新 Tasker 至最新版后重试。
- 若 Tasker 提示"文件格式错误"：确认文件为 `.prj.xml` 格式（非 `.tsk.xml` 单任务文件）。检查文件完整性——在 Termux 中执行 `wc -l ~/atlas-runtime/config/tasker/atlas_trigger.prj.xml`，文件应不少于 50 行。另外确认文件编码为 UTF-8 without BOM（在 Termux 中执行 `file ~/atlas-runtime/config/tasker/atlas_trigger.prj.xml` 验证）。
- 若导入后 Profiles 显示为灰色（未激活）：点击 Profile 名称旁的开关图标手动激活。部分 Profile 需要额外权限（如通知监听）才能激活。
- 若 Tasker 列表中出现重复项目：长按旧项目 → 删除，保留最新导入的版本。

### 步骤 23：配置 Termux:Tasker Action 路径

操作: 在 Tasker 中打开任意导入的 Task（如 "ATLAS: SIM切换"），编辑包含 Termux:Tasker 的 Action。确认以下三个字段：

- **Workdir**: `/data/data/com.termux/files/home/atlas-runtime`
- **Executable**: `/data/data/com.termux/files/usr/bin/bash`
- **Arguments**: `runtime/trigger_atlas.sh {"action":"sim_switch","params":{"slot":0},"correlation_id":"tasker_sim_%TIMES"}`

如果路径不一致，根据 Termux 的实际 PREFIX 路径调整。通常在 Termux 中执行 `echo $PREFIX` 确认路径前缀。

预期结果: 所有 Task 中的 Termux:Tasker Action 配置指向正确的 Termux 路径。

异常处理:
- 若 Tasker 提示 "Plugin not found / 插件未找到"：确认 Termux:Tasker 插件已在 Google Play 安装（步骤 7）。在 Android 的"设置 → 应用 → 特殊应用权限 → 在其他应用上层显示"中确认 Tasker 已开启。
- 若 Action 编辑界面为空白：尝试退出 Tasker 后重新打开。若仍为空白，Tasker 的插件缓存可能损坏——"设置 → 应用 → Tasker → 清除缓存"，然后重启 Tasker。

### 步骤 24：创建共享数据目录

操作: 在 Termux 中执行：

```bash
mkdir -p /sdcard/atlas_shared/
echo "test" > /sdcard/atlas_shared/test_write.txt && rm /sdcard/atlas_shared/test_write.txt && echo "Shared directory OK"
```

预期结果: 目录创建成功，测试写入和删除正常。"Shared directory OK" 被输出。

异常处理:
- 若 `mkdir` 返回 "Permission denied"：`termux-setup-storage` 未完成存储授权。重新在 Termux 中执行 `termux-setup-storage` 并确认权限弹窗中点击"允许"。
- 若 `/sdcard/` 不存在：部分 Android 设备上 `/sdcard` 可能指向 `/storage/emulated/0`。使用 `echo $EXTERNAL_STORAGE` 确认实际路径后调整。

---

## 第八阶段：AutoJS6 脚本部署

### 步骤 25：部署 AutoJS6 脚本到设备

操作: 在 Termux 中执行：

```bash
# 将脚本目录复制到共享存储
cp -r ~/atlas-runtime/scripts/autojs/ /sdcard/atlas_shared/autojs/

# 验证复制完整性
ls -la /sdcard/atlas_shared/autojs/
```

预期结果: 6 个 .js 文件均出现在 `/sdcard/atlas_shared/autojs/` 目录中。

操作: 打开 AutoJS6 应用，在主页点击"导入文件"（或加号 → 导入），选择 `/sdcard/atlas_shared/autojs/` 目录中的文件，逐个导入。至少导入 `atlas_ui_template.js`（基础模板）和 `sim_switch_verify.js`（SIM 验证）两个文件，其余按需导入。

预期结果: 导入的脚本出现在 AutoJS6 的脚本列表中。点击 `atlas_ui_template.js`，应能正常打开并显示代码。

异常处理:
- 若 AutoJS6 无法访问 `/sdcard/atlas_shared/`：AutoJS6 未获取"所有文件访问权限"。进入"设置 → 应用 → AutoJS6 → 权限 → 文件和媒体 → 允许管理所有文件"，然后重启 AutoJS6。
- 若脚本导入后显示乱码：文件编码问题。确保 `scripts/autojs/` 下的文件为 UTF-8 编码。在 Termux 中执行 `file /sdcard/atlas_shared/autojs/*.js` 确认编码。
- 若 AutoJS6 提示 Rhino 引擎错误：AutoJS6 使用 Mozilla Rhino 引擎而非 V8，不支持 ES6+ 语法（箭头函数、let/const、模板字符串等）。Atlas 提供的脚本已适配 Rhino 引擎，若自定义脚本报错请检查是否符合 Rhino 语法要求。

---

## 第九阶段：部署后功能验证测试

此阶段按 5 个场景依次执行验证，每个场景包含具体的操作指令和通过标准。全部通过后方可认定部署完成。

### 步骤 26：场景 1——基础部署验证（8 项）

在 Termux 中依次执行以下 8 项验证：

**验证 1.1 — Termux 环境完整性**

```bash
echo "PREFIX=$PREFIX"
echo "HOME=$HOME"
python3 --version
```
预期: `PREFIX` 为 `/data/data/com.termux/files/usr`，`HOME` 为 `/data/data/com.termux/files/home`，Python 版本 >=3.11。

**验证 1.2 — pip 依赖完整性**

```bash
python3 -c "
import aiosqlite, msgpack, yaml, aiohttp
print('All core deps OK')
"
```
预期: "All core deps OK"，无 ModuleNotFoundError。

**验证 1.3 — git 仓库完整性**

```bash
cd ~/atlas-runtime && git log --oneline -1
```
预期: 显示最新 commit 的 hash 和消息。若为 git clone --depth 1 方式部署，仅显示一个 commit 是正常的。

**验证 1.4 — deploy.sh 步骤回顾**

回顾 `service/deploy.sh` 执行时的终端输出，确认无红色 "✗" 错误标记。若有黄色 "!" 警告，逐一确认其影响——`SAMSUNG_ONEUI85_COMPAT.md` 的"安装检查清单"中标注了每项的可接受范围。

**验证 1.5 — runit 服务状态**

```bash
sv status atlas-runtime
```
预期: 以 "run:" 开头，表示服务正在运行。

**验证 1.6 — Atlas 启动日志**

```bash
tail -20 /data/data/com.termux/files/usr/var/log/atlas-runtime/current
```
预期: 无 ERROR 级别日志行（WARNING 是允许的，如非 Samsung 设备的兼容性警告）。应能看到 bootstrap 各步骤的 INFO 日志。

**验证 1.7 — /health 端点**

```bash
curl -s http://127.0.0.1:8787/health | python3 -m json.tool
```
预期: `"status": "healthy"` 出现在输出中。JSON 响应还应包含 battery、memory、circuit_breaker、uptime 等字段。

**验证 1.8 — /ready 端点**

```bash
curl -s http://127.0.0.1:8787/ready
```
预期: 返回 "Ready" 或 HTTP 200。

通过标准: 8 项全部通过。

### 步骤 27：场景 2——Tasker 触发链验证（6 项）

**验证 2.1 — Tasker 项目完整性**

在 Tasker 中确认 "Atlas Trigger" 项目下的 3 个 Profile 和 4 个 Task 全部可用。切换 Profile 开关确认其可正常激活和停用。

**验证 2.2 — FIFO 手动触发验证**

在 Termux 中执行：

```bash
echo '{"action":"ping","params":{},"correlation_id":"manual_test_001"}' > /data/data/com.termux/files/usr/tmp/atlas_trigger.fifo
# 等待 2 秒
sleep 2
# 检查结果
cat /sdcard/atlas_shared/last_result.json 2>/dev/null | python3 -m json.tool
```
预期: `last_result.json` 包含 `correlation_id: "manual_test_001"` 的回执，status 为 "success" 或 "completed"。

**验证 2.3 — Tasker 手动触发 SIM 切换 Task**

在 Tasker 中，切换到 Tasks 标签，找到 "ATLAS: SIM切换"，点击底部的播放按钮手动执行。观察是否：
1. Termux 收到执行请求（在 Termux 中执行 `tail -f ~/atlas-runtime/logs/atlas.log` 实时查看日志，应出现 "sim_switch" 或相关日志行）。
2. `/sdcard/atlas_shared/last_result.json` 在 Task 执行后 5-10 秒内更新。
3. 通知栏出现 Tasker 的结果通知。

**验证 2.4 — Tasker 通用触发 Task 验证**

在 Tasker 中手动执行 "ATLAS: 通用触发" Task，设置 `%par1 = "shell_command"`、`%par2 = {"cmd":"echo hello from tasker"}`。执行后检查 `last_result.json` 中的 stdout 字段是否包含 "hello from tasker"。

**验证 2.5 — 时间触发 Profile 验证**

确认 "定时触发" Profile 已激活（每日 08:55 自动执行 SIM 切换）。可以临时修改 Profile 的时间条件为当前时间 +2 分钟，等待自动触发后验证。

**验证 2.6 — last_result.json 格式完整性**

```bash
cat /sdcard/atlas_shared/last_result.json | python3 -c "
import sys, json
d = json.load(sys.stdin)
required = ['timestamp', 'status', 'task_id']
for k in required:
    assert k in d, f'Missing field: {k}'
print('Result format OK')
"
```
预期: "Result format OK"。

通过标准: 6 项全部通过。

### 步骤 28：场景 3——AutoJS6 UI 自动化验证（5 项）

**验证 3.1 — AutoJS6 无障碍服务确认**

打开 AutoJS6 应用，确认无障碍服务状态指示灯为绿色（或显示"已连接"）。在 AutoJS6 中打开 `health_check_ui.js`，点击运行按钮 → 观察日志输出中的 `accessibility` 检查项是否显示 "OK"。

**验证 3.2 — app_launcher.js 启动系统设置**

在 AutoJS6 中打开 `app_launcher.js`，修改参数（或在运行时传入参数）使 `app_package` 为 `com.android.settings`、`actions` 中包含 `{"type":"wait","ms":2000},{"type":"back"}`。运行脚本，观察是否成功打开系统设置页面并在 2 秒后返回 AutoJS6。

**验证 3.3 — ui_click_sequence.js 执行序列**

在 AutoJS6 中运行 `ui_click_sequence.js`（可从系统设置页面开始），传入 `steps` 参数包含 5 步点击序列。每步验证点击落点是否在目标控件范围内。

**验证 3.4 — sim_switch_verify.js 运营商验证**

```bash
# 在 Termux 中获取当前运营商信息
getprop gsm.operator.alpha
```
在 AutoJS6 中运行 `sim_switch_verify.js`，传入参数 `{"slot":0, "expected_operator":"<上述命令的输出>"}`。验证脚本能正确读取运营商信息并确认匹配。

**验证 3.5 — battery_monitor.js 电池监控**

在 AutoJS6 中运行 `battery_monitor.js`，参数 `{"single_shot":true}`。确认输出中包含当前的电池电量和充电状态。

通过标准: 5 项全部通过。

### 步骤 29：场景 4——故障自愈验证（6 项）

**验证 4.1 — 进程崩溃自动重启**

```bash
# 获取 Atlas Runtime PID
PID=$(cat /data/data/com.termux/files/usr/var/service/atlas-runtime/supervise/pid 2>/dev/null)
echo "Killing PID: $PID"
kill -9 $PID
sleep 5
sv status atlas-runtime
curl -s http://127.0.0.1:8787/health | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])"
```
预期: `kill -9` 后 5 秒内服务恢复，`sv status` 显示 "run:"，`/health` 返回 "healthy"。恢复时间（从 kill 到 healthy）应 <5 秒。

**验证 4.2 — HTTP 端口占用处理**

```bash
# 模拟端口占用
python3 -m http.server 8787 --bind 127.0.0.1 &
sleep 2
sv restart atlas-runtime
sleep 5
curl -s http://127.0.0.1:8787/health | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])"
# 清理
fuser -k 8787/tcp 2>/dev/null
```
预期: 即使 8787 端口被占用，Atlas 仍应能启动（通过 fuser -k 释放端口或提示用户在日志中）。若此场景需手动干预（fuser -k），则为已知限制，记录即可。

**验证 4.3 — Shell 命令超时处理**

```bash
echo '{"action":"shell_command","params":{"cmd":"sleep 30","timeout":3},"correlation_id":"timeout_test"}' > /data/data/com.termux/files/usr/tmp/atlas_trigger.fifo
sleep 8
cat /sdcard/atlas_shared/last_result.json | python3 -c "import sys,json; d=json.load(sys.stdin); print('Timeout handled' if d.get('status') in ['timeout','failed'] else 'Unexpected: '+d.get('status','?'))"
```
预期: 任务在 3 秒超时后被杀死（killpg），状态为 timeout。Shell 的子进程（sleep 30）不会残留。

**验证 4.4 — FIFO 管道重建**

```bash
rm -f /data/data/com.termux/files/usr/tmp/atlas_trigger.fifo
sleep 3
ls -la /data/data/com.termux/files/usr/tmp/atlas_trigger.fifo
```
预期: FIFO 管道在删除后 3 秒内被 TriggerServer 自动重建。

**验证 4.5 — 孤儿锁清理**

重启 Atlas Runtime 后检查日志中是否包含 "cleaning orphan lock" 或类似信息。在 Termux 中执行：

```bash
cat /data/data/com.termux/files/usr/var/log/atlas-runtime/current | grep -i "lock\|orphan" | tail -5
```
预期: 启动日志中可能包含锁清理信息，无持续出现的锁错误。

**验证 4.6 — 熔断器自动恢复**

```bash
# 快速触发 6 次失败任务（超过 failure_threshold = 5）
for i in $(seq 1 6); do
  echo "{\"action\":\"invalid_action_$i\",\"params\":{},\"correlation_id\":\"cb_test_$i\"}" > /data/data/com.termux/files/usr/tmp/atlas_trigger.fifo
done
sleep 35
# 等待冷却结束（recovery_timeout = 30s），再发一次正常请求
echo '{"action":"ping","params":{},"correlation_id":"cb_recovery_test"}' > /data/data/com.termux/files/usr/tmp/atlas_trigger.fifo
sleep 3
cat /sdcard/atlas_shared/last_result.json | python3 -c "import sys,json; d=json.load(sys.stdin); print('Recovered' if d.get('status')=='success' else 'Still open: '+d.get('status','?'))"
```
预期: 前 5 次失败后熔断器进入 OPEN 状态（第 6 次请求被拒绝），约 30 秒冷却后进入 HALF_OPEN，正常请求被接受并返回 success。整个恢复周期 <45 秒。

通过标准: 场景 4 全部 6 项验证通过。

### 步骤 30：场景 5——性能基准验证（7 项）

在 Termux 中执行以下 7 项性能测试。每项测试可能需要 1-10 分钟。建议在设备不插电（使用电池供电）且后台无大量应用运行的条件下测试。

**验证 5.1 — Shell 执行成功率**

```bash
cd ~/atlas-runtime
python3 -c "
import subprocess, time
total, ok = 500, 0
for i in range(total):
    r = subprocess.run(['echo', 'hello'], capture_output=True, text=True, timeout=5)
    if r.returncode == 0 and 'hello' in r.stdout:
        ok += 1
print(f'Success rate: {ok}/{total} = {ok/total*100:.2f}%')
"
```
预期: 成功率 >99.8%（500 次中 499 次以上成功）。

**验证 5.2 — HTTP loopback 响应延迟**

```bash
curl -s -o /dev/null -w "HTTP response time: %{time_total}s\n" http://127.0.0.1:8787/health
```
预期: 响应时间 <0.05s（P95 <50ms）。若 >0.1s，检查是否开启了 VPN 或防火墙软件。

**验证 5.3 — 内存占用（正常运行）**

```bash
PID=$(cat /data/data/com.termux/files/usr/var/service/atlas-runtime/supervise/pid 2>/dev/null)
if [ -n "$PID" ]; then
  RSS=$(awk '/VmRSS/ {print $2}' /proc/$PID/status 2>/dev/null)
  echo "Atlas Runtime RSS: ${RSS}KB = $(($RSS/1024))MB"
fi
```
预期: RSS <100MB（正常工作状态）。若 >150MB，检查是否有异常的任务循环或内存泄漏。

**验证 5.4 — 启动时间**

```bash
sv restart atlas-runtime
START_TIME=$(date +%s%3N)
# 轮询等待 health endpoint 就绪
for i in $(seq 1 30); do
  if curl -s --connect-timeout 1 http://127.0.0.1:8787/health > /dev/null 2>&1; then
    END_TIME=$(date +%s%3N)
    echo "Startup time: $((END_TIME - START_TIME))ms"
    break
  fi
  sleep 0.2
done
```
预期: 启动时间 <5 秒（从 sv restart 到 /health 返回 200）。

**验证 5.5 — 崩溃恢复时间**

```bash
PID=$(cat /data/data/com.termux/files/usr/var/service/atlas-runtime/supervise/pid 2>/dev/null)
kill -9 $PID
START=$(date +%s%3N)
for i in $(seq 1 30); do
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 1 http://127.0.0.1:8787/health 2>/dev/null || echo "000")
  if [ "$HTTP_CODE" = "200" ]; then
    END=$(date +%s%3N)
    echo "Recovery time: $((END - START))ms"
    break
  fi
  sleep 0.2
done
```
预期: 恢复时间 <5 秒。

**验证 5.6 — 长时间运行稳定性（快速抽查）**

若时间有限，执行 30 分钟的快速稳定性测试：

```bash
# 在 Termux 中启动循环触发
for i in $(seq 1 60); do
  echo "{\"action\":\"ping\",\"params\":{},\"correlation_id\":\"stability_$i\"}" > /data/data/com.termux/files/usr/tmp/atlas_trigger.fifo
  sleep 30
done &
# 监控内存
for i in $(seq 1 60); do
  PID=$(cat /data/data/com.termux/files/usr/var/service/atlas-runtime/supervise/pid 2>/dev/null)
  if [ -n "$PID" ]; then
    RSS=$(awk '/VmRSS/ {printf "%.0f", $2/1024}' /proc/$PID/status 2>/dev/null)
    echo "[$(date +%H:%M:%S)] RSS: ${RSS}MB"
  else
    echo "[$(date +%H:%M:%S)] Process not found!"
  fi
  sleep 30
done
```
预期: 30 分钟内无进程崩溃，RSS 增长 <5MB。

**验证 5.7 — 电池消耗（空闲状态快速估算）**

锁屏放置 15 分钟（或用 `termux-battery-status` 记录起始电量），之后检查电量变化。也可以在 Termux 中执行：

```bash
START_BATT=$(termux-battery-status 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['percentage'])")
echo "Starting battery: ${START_BATT}%"
echo "Lock screen and wait 15 minutes..."
sleep 900
END_BATT=$(termux-battery-status 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['percentage'])")
echo "Ending battery: ${END_BATT}%"
echo "Consumption: ~$((START_BATT - END_BATT))% in 15 min"
```
预期: 空闲 15 分钟电量消耗 <0.2%，折合每小时 <0.8%。若 >1%/h，检查是否有其他后台应用消耗电量（非 Atlas 原因），或检查 Termux:Boot 的 wakelock 是否正确释放。

通过标准: 全部 7 项指标在 `DEPLOYMENT_PLAN.md` 第 4.5 节定义的通过阈值内。

---

## 第十阶段：开机自启与长期运维

### 步骤 31：验证开机自启

操作: 重启 Samsung S25 Plus 设备。重启完成后，等待约 30 秒（Termux:Boot 引导延迟约 5 秒 + Atlas 启动约 5 秒 + 缓冲时间）。然后：

1. 在 Termux 中执行 `sv status atlas-runtime`，确认显示 "run:"。
2. 执行 `curl -s http://127.0.0.1:8787/health | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])"`，确认返回 "healthy"。

预期结果: 设备重启后 Atlas Runtime 自动启动且健康状态为 healthy。无需任何手动操作。

异常处理:
- 若重启后 Atlas 未自动启动：确认 Termux:Boot APK 已安装（步骤 6），且在 Samsung "智能管理器"中授予了 Termux:Boot 自启动权限——"设置 → 设备维护 → 自动运行应用 → 确保 Termux:Boot 开关已开启"。同时确认 `~/.termux/boot/start-atlas-runtime` 脚本存在且可执行（`ls -la ~/.termux/boot/start-atlas-runtime`）。
- 若重启后 Termux 进程被系统杀死：Samsung One UI 8.5 的电池优化可能在设备重启后重置应用设置。重新执行步骤 10 中的电池优化白名单配置。若问题持续，在"设置 → 设备维护 → 电池 → 后台使用限制 → 始终休眠的应用"中确认 Termux 未被列入。

### 步骤 32：部署文档归档

操作: 记录以下关键信息，保存至团队的部署记录表或 Wiki：

| 记录项 | 值 |
|:---|:---|
| 设备型号 | SM-S9360 / SM-S936U |
| Android / One UI 版本 | Android 16 / One UI 8.5 |
| Atlas Runtime 版本 | v9.1.x |
| 部署日期 | YYYY-MM-DD |
| deploy.sh 是否全部通过 | 是 / 否（注明失败步骤） |
| 场景 1-5 验证结果 | 通过项数 / 总项数 |
| 已知限制 | 列出验证中发现的任何异常项 |
| 部署人 | 姓名 |

---

## 附录 A：快速诊断命令速查表

| 诊断场景 | 命令 |
|:---|:---|
| 查看服务状态 | `sv status atlas-runtime` |
| 查看实时日志 | `tail -f /data/data/com.termux/files/usr/var/log/atlas-runtime/current` |
| 查看 Atlas 应用日志 | `tail -f ~/atlas-runtime/logs/atlas.log` |
| 健康检查 | `curl -s http://127.0.0.1:8787/health \| python3 -m json.tool` |
| 手动触发任务 | `echo '{"action":"ping","params":{}}' > /data/data/com.termux/files/usr/tmp/atlas_trigger.fifo` |
| 查看最新执行结果 | `cat /sdcard/atlas_shared/last_result.json \| python3 -m json.tool` |
| 重启服务 | `sv restart atlas-runtime` |
| 停止服务 | `sv down atlas-runtime` |
| 启动服务 | `sv up atlas-runtime` |
| 查看服务 PID | `cat /data/data/com.termux/files/usr/var/service/atlas-runtime/supervise/pid` |
| 查看内存占用 | `awk '/VmRSS/ {print $2/1024 " MB"}' /proc/$(cat /data/data/com.termux/files/usr/var/service/atlas-runtime/supervise/pid)/status` |
| 查看电池状态 | `termux-battery-status` |
| 查看设备信息 | `getprop ro.product.model && getprop ro.build.version.release && getprop ro.build.version.oneui` |
| 验证 Shizuku | `~/.atlas_sentinel/bin/rish -c "id" 2>/dev/null \|\| echo "Shizuku 不可用"` |
| 验证 FIFO 通信 | `[ -p /data/data/com.termux/files/usr/tmp/atlas_trigger.fifo ] && echo "FIFO OK" \|\| echo "FIFO MISSING"` |
| 验证 AutoJS6 安装 | `pm list packages \| grep autojs` |

## 附录 B：部署故障速查表

| 症状 | 最可能原因 | 首要排查步骤 |
|:---|:---|:---|
| `sv status` 显示 "down" | Python 依赖缺失 / 端口占用 / 配置文件错误 | 查看日志 `~atlas-runtime/logs/atlas.log` |
| /health 返回 connection refused | Atlas 未启动 / HTTP 端口更换 | `sv up atlas-runtime` + 等待 5 秒后重试 |
| FIFO 写入超时或阻塞 | FIFO 管道损坏 / TriggerServer 未监听 | `ls -la $PREFIX/tmp/atlas_trigger.fifo` 检查文件类型 |
| Tasker 触发无效果 | Termux:Tasker 路径错误 / 共享目录权限 | 手动在 Termux 中执行 `termux-setup-storage` |
| AutoJS6 脚本卡在 "等待无障碍服务" | 无障碍服务被系统关闭 | 重新开启："设置 → 辅助功能 → AutoJS6 → 开启" |
| Shizuku 频繁自动断开 | 电池优化杀死 Shizuku | 将 Shizuku 加入"不受限制"电池白名单 |
| 内存持续增长 | 可能的任务循环 / 事件处理异常 | 检查日志是否有大量重复的任务提交记录 |
| `termux-battery-status` 返回空 | Termux:API APK 未安装或未授权 | 确认 F-Droid 版 Termux:API APK 已安装 |
| 更新后服务无法启动 | 配置结构变更 / 依赖版本冲突 | 对比新旧 `config/runtime.yaml` 差异 |
| 开机后 Atlas 未启动 | 电池优化重置 / Termux:Boot 权限丢失 | 重新配置步骤 10 和步骤 31 |

---

## 附录 C：文档引用索引

本操作手册中引用的文档及定位：

- `docs/DEPLOYMENT_PLAN.md` — 完整部署策略（5 章 + 2 附录），含三级兼容矩阵、混合部署策略、环境配置规范、测试方案、维护策略
- `docs/SAMSUNG_ONEUI85_COMPAT.md` — Samsung One UI 8.5 兼容性分析，含特性矩阵、已知限制、故障排除
- `docs/TASKER_INTEGRATION_GUIDE.md` — Tasker 集成详细配置（项目导入、Profile/Task 使用、故障排除）
- `docs/AUTOJS6_SCRIPT_GUIDE.md` — 6 个 AutoJS6 脚本的使用和扩展开发说明
- `docs/ARCHITECTURE.md` — 6 层架构设计、依赖规则、数据流、故障自愈策略
- `docs/DESIGN_SPEC_v8.0.md` — 完整设计规格书（启动编排、数据流、故障处理）
- `config/runtime.yaml` — 运行时配置的完整参数说明和默认值
- `service/deploy.sh` — 14 步一键部署脚本源码
