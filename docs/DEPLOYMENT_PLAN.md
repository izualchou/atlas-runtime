# Atlas Runtime v9.1 手机端部署方案

版本: v1.0 | 生效日期: 2026-08-08 | 维护者: Atlas DevOps Group | 审核周期: 每季度一次或重大架构变更时更新

本文档为 Atlas Runtime v9.1 在 Android 终端设备上的标准化生产部署方案。

---

## 第一章：部署目标与设备兼容性矩阵

### 1.1 主目标设备

Samsung S25 Plus 为 Atlas Runtime v9.1 的基准开发和全面验证设备。以下为详细规格参数：

| 参数 | 规格 |
|:---|:---|
| 型号 | Samsung S25 Plus (SM-S9360 / SM-S936U) |
| SoC | Snapdragon 8 Gen 4 for Galaxy / Exynos 2500 |
| RAM | 12GB LPDDR5X |
| 存储 | 256GB / 512GB UFS 4.0 |
| 屏幕 | 3120×1440 (QHD+), Dynamic AMOLED 2X, 120Hz |
| 屏幕比例 | 19.5:9 |
| 操作系统 | Android 16 |
| 系统UI | One UI 8.5 |
| 内核版本 | Linux 6.1 (Android Common Kernel) |
| 电池 | 4900 mAh |
| Knox 版本 | 3.12 |

在此设备上，Atlas Runtime 全部功能（Shell 执行、FIFO 通信、HTTP 服务、SIM 切换、WiFi/Data 控制、UI 自动化、高权限操作、健康检查、熔断保护、内存控制、去重过滤）均经过完整验证。

### 1.2 三级兼容矩阵

Atlas Runtime 的组件系统（非单一 APK）决定了其兼容性按组件粒度而非整机一刀切。以下分级依据 Android SDK 版本、厂商定制深度、Termux 支持程度、无障碍服务实现差异四个维度综合评估。

**Tier 1：全功能验证级**

Tier 1 设备在实验室条件下已通过全部 30 项 E2E checklist 验证。所有功能（含 Samsung 特定 service call 事务码、Knox 高权限操作、AutoJS6 UI 自动化）均可用且性能达标。

代表机型：Samsung S25/S25+/S25 Ultra (One UI 8.5/Android 16)、Samsung S24/S24+/S24 Ultra (One UI 7.1/Android 15)、Samsung S23/S23+/S23 Ultra (One UI 6.1/Android 14)、Samsung S22/S22+/S22 Ultra (One UI 5.1/Android 13)。

已知限制：S22 系列因 RAM 仅 8GB，在高负载并发（>5 个同时执行的任务）时 FIFO 延迟可能放宽至 P95 <15ms（S25 Plus 为 <5ms）；S22 系列电池管理策略较温和（Doze 阈值更高），反而比 S24/S25 系列的后台进程更不容易被杀。

**Tier 2：核心功能兼容级**

Tier 2 设备保证了核心运行时功能可用——Python asyncio 引擎、Shell 执行、FIFO 通信、HTTP loopback 服务、健康检查、存储持久化、熔断和去重。但 Samsung 特有的 service call 事务码不可用，高权限操作（WiFi/Data/SIM 切换）需回退到 AOSP 标准命令或 svc 命令，SIM 切换仅支持 Shizuku/Rish 方案（非 Samsung 设备 Rish 兼容性需额外验证）。UI 自动化因无障碍服务行为差异可能不可靠，需逐设备适配。

代表机型：Google Pixel 7/8/9 系列 (Android 13-16)、OnePlus 12/13 (OxygenOS 14/15)、Xiaomi 14/15 系列 (HyperOS)。Samsung 搭载 One UI 4.0-4.1 的旧旗舰（S21 系列）。

已知限制：Pixel 设备无 service call isub 支持，SIM 切换仅能通过 Shizuku/Rish 实现；Xiaomi HyperOS 的无障碍服务管理较严格，AutoJS6 安装后需手动授权并关闭 MIUI 优化；OnePlus 的电池优化策略可能导致 Termux 后台进程在熄屏 30 分钟后被挂起。

**Tier 3：基础运行级**

Tier 3 设备仅保证 Python 运行时可启动、Termux 环境可用、Shell 执行正常、FIFO 通信可建立。但健康检查、电池监控、高权限操作、UI 自动化、开机自启均不可靠或不支持。

代表机型：Android 7-11 的设备。Motorola、Nokia 等接近原生 Android 的中端机。低 RAM（<4GB）Android 12+ 设备。

已知限制：Android 10 以下 termux-battery-status 不可用（需 dumpsys 回退）；Android 11 以下 runit 守护进程不支持 Termux:Boot 集成；内存 <2GB 设备可能在 Python 运行时即触发 OOM；不建议在此类设备上用于生产自动化场景。

### 1.3 兼容性适配策略

设备兼容性适配遵循三层策略。第一层为平台检测自动适配——Atlas Runtime 启动时通过 `device/detector.py` 的 `PlatformInfo.discover()` 自动检测制造商、One UI 版本、Android SDK 级别、Root 状态和 Termux 工具链可用性，据此决定功能开关。非 Samsung 设备自动禁用 Samsung 特定功能路径并回退到 AOSP 标准命令。第二层为配置覆盖适配——用户可通过 `config/runtime.yaml` 手动指定 platform 段的参数（如 `service_call_transaction` 的自定义事务码）来适配非标设备。第三层为回退链适配——高权限操作内置多层回退策略，以 WiFi 切换为例：`settings put global wifi_on` → `svc wifi enable` → `cmd wifi set-wifi-enabled enabled`，逐级降级直到找到可用命令。

---

## 第二章：混合部署策略

### 2.1 策略总览

Atlas Runtime v9.1 是一个混合组件系统，非单一 APK。每个组件有各自的技术特性和分发约束，因此采用"组件-渠道匹配"策略，而非全系统走的单一渠道。

### 2.2 组件-渠道匹配矩阵

| 组件 | 分发渠道 | 版本策略 | 分发方式 |
|:---|:---|:---|:---|
| Termux | F-Droid | 跟随上游稳定版 | 用户自安装，deploy.sh 校验版本 |
| Termux:API | F-Droid | 跟随上游 | 用户自安装 |
| Termux:Boot | F-Droid | 跟随上游 | 用户自安装 |
| Termux:Widget | F-Droid | 跟随上游 | 用户自安装（可选） |
| Tasker | Google Play | 试用版→付费 ($3.49) | 用户自安装 |
| AutoApps 插件 | Google Play | 按需安装 | 用户自安装（AutoInput、AutoNotification 等） |
| AutoJS6 APK | Firebase App Distribution | 内部版本号 | 团队上传 → 测试者受邀安装 |
| Atlas Runtime Core | GitHub Releases + git clone | Git tag x.y.z | `git clone -b <tag>` + deploy.sh |
| Atlas 脚本+配置 | GitHub Releases（包内含） | 随 Core 版本 | 同一 repo，tag 打包 |
| PWA 状态面板 | GitHub Pages（静态托管） | 随 Core 版本更新 | 可选部署，独立分发 |

### 2.3 F-Droid 渠道——Termux 系列

选择理由：Termux 官方唯一推荐分发渠道为 F-Droid。Google Play 上的 Termux 版本已停止更新且缺少 API 包。F-Droid 版本附带完整 `termux-api` 套件，是 Atlas Runtime 硬件访问（电池、WiFi、传感器）的必需依赖。F-Droid 采用开源签名，与 Google Play 版本不兼容，若用户已从 Google Play 安装需先卸载再装 F-Droid 版。

分发流程：用户在 F-Droid 客户端搜索安装 Termux → 安装后运行 `pkg update && pkg upgrade` 更新包索引 → 安装 Termux:API、Termux:Boot、Termux:Widget（后两者可选但推荐）→ 执行 deploy.sh 前校验 `command -v termux-battery-status` 确认 API 包正确安装。deploy.sh 第 3-4 步自动检测并提示安装缺失的 Termux 组件。

适用场景：所有需要硬件感知的 Atlas 部署。F-Droid 渠道是部署的硬性前置条件，不经过此渠道无法获得 termux-api 包。

### 2.4 Google Play 渠道——Tasker 与 AutoApps 插件

选择理由：Tasker 是商业付费 APP，仅在 Google Play 分发。其配套 AutoApps 插件系列（AutoInput、AutoNotification、AutoVoice 等）同样仅通过 Play 商店更新。Google Play 提供自动更新、许可证验证和应用内购流程，适合商业化组件的分发需求。

分发流程：用户在 Google Play 搜索安装 Tasker（7 天免费试用后可购买）→ 在 Tasker 内通过 AutoApps 集成入口跳转到对应插件的 Play 页面 → 安装所需插件 → 按 `TASKER_INTEGRATION_GUIDE.md` 导入 Atlas Trigger 项目（1 个 project + 3 个 profile + 4 个 task 的 XML 配置文件）。

适用场景：所有使用 Tasker 触发 Atlas Runtime 的场景。对于不需要 Tasker 的基础部署（纯手动触发或通过 FIFO 直接写入），Tasker 为可选组件。

### 2.5 Firebase App Distribution 渠道——AutoJS6 APK 内测分发

选择理由：AutoJS6 因无障碍服务自动化特性，不在 Google Play 上架（Google 对此类 APP 审核严格且经常下架）。选择 Firebase App Distribution 作为内测分发渠道的理由包括：支持按测试者分组分发、自动通知更新、集成 Crashlytics 崩溃报告、无需自建分发服务器、内测者数量在免费配额内（100 名测试者）。

分发流程：开发者在 Firebase Console 上传 AutoJS6 APK（包名 `org.autojs.autojs6`）→ 在 App Distribution 页面添加测试者邮箱 → Firebase 自动发送邀请邮件，含安装链接 → 测试者在设备上接受邀请并下载安装 → Firebase 在开发者上传新版本时自动推送更新通知 → Crashlytics 实时收集崩溃数据供开发团队分析。APK 下载链接同时置于 GitHub Releases 的发布说明中，供不使用 Firebase 的用户侧载安装。

适用场景：内部测试和预发布验证阶段。生产环境建议锁定已验证的 AutoJS6 版本号，通过 deploy.sh 中的版本校验（`am start -n org.autojs.autojs6/.ui.main.MainActivity` 检查包是否存在）确保兼容性。

### 2.6 GitHub Releases + git clone 渠道——Atlas Runtime Core

选择理由：Atlas Runtime 核心代码为 Python 项目，不适合打包为 APK。GitHub Releases 提供语义化版本标签、release notes、assets 下载和变更追踪，是最适合开源 Python 项目的分发渠道。git clone 方式支持增量更新（`git fetch` 仅拉差异，减少移动网络流量消耗）。Tag 签名（`git tag -s`）提供分发链完整性验证。

分发流程：用户首次部署执行 `git clone -b v9.1.0 https://github.com/<org>/atlas-runtime.git ~/atlas-runtime` 或直接运行 `service/deploy.sh` 脚本（该脚本第 6 步自动 clone）。后续热更新执行 `git fetch origin && git checkout tags/vX.Y.Z`。GitHub Releases 页面提供每个版本的 Assets 下载（源码 tarball/zipball）和 Release Notes（含 Breaking Changes、新功能、Bug 修复清单）。为提升中国区访问速度，建议配置 Gitee 镜像仓库作为备选 clone 地址。

适用场景：所有部署场景。这是唯一必需的分发渠道——Atlas Runtime Core 代码是系统的核心大脑，其他组件均为可选增强。

### 2.7 PWA 状态监控面板——可选增值组件

选择理由：PWA 可以通过 `localhost:8787/health` API 获取运行状态数据（电池、内存、任务队列、熔断器状态、最近任务记录），以 Chart.js 图表展示。部署为静态 HTML 页面，无需服务端渲染，可托管到 GitHub Pages。PWA 支持 Service Worker 离线缓存，安装一次后零网络开销。

分发流程：开发者将 PWA HTML/JS/CSS 文件推送至 `gh-pages` 分支 → GitHub Pages 自动部署至 `https://<org>.github.io/atlas-monitor/` → 用户在 Samsung Internet/Chrome 中打开 URL → 浏览器提示"添加到主屏幕"→ 安装为 PWA 后离线可用 → PWA 通过 `127.0.0.1:8787` 回环地址连接本地 Atlas 实例。manifest.json 配置 `scope` 和 `start_url` 指向监控面板。

适用场景：运维人员需要直观查看 Atlas 运行状态时。对日常自动化使用为非必需组件。

---

## 第三章：环境配置规范

### 3.1 最低硬件配置

Atlas Runtime 的硬件需求与部署级别对应，分为最低配置和推荐配置两档。

**最低配置（Tier 3 基础运行级）**：SoC 架构必须为 ARM64-v8a（Termux 和 Python 3.11+ 不支持 32 位 ARM）。RAM 最低 3GB，其中 Termux 进程组预留约 300MB（Python 运行时 ~80MB + SQLite WAL 页缓存 ~50MB + asyncio 事件循环 ~30MB + Shell 子进程动态峰值 ~140MB）。存储可用空间最低 500MB（Termux 基础环境 ~200MB + Python 及依赖包 ~100MB + Atlas 代码库 ~20MB + 日志和 SQLite 数据文件 ~180MB）。屏幕分辨率最低 720p (1280×720)，主要用于 AutoJS6 UI 自动化操作时控件识别。

**推荐配置（Tier 1 全功能级）**：RAM 6GB+，确保 5+ 并发任务执行时无 OOM 风险。存储 1GB+ 可用空间，预留日志轮转归档（30 天历史 × 每日 ~10MB = 300MB 归档空间）。屏幕 1080p+ (2340×1080 或以上)，确保 AutoJS6 的 `text()`、`desc()` 控件匹配精度。Samsung 设备建议开启"RAM Plus"（虚拟内存）设为 4-8GB，降低极端内存压力下的进程被杀概率。

### 3.2 设备权限清单

权限按层级分为三类。

**Termux 内权限（部署阶段授予）**：在 Termux 中执行 `termux-setup-storage` 一次性授予存储访问权限（Android 的 `READ_EXTERNAL_STORAGE` 和 `WRITE_EXTERNAL_STORAGE`），此为必需权限，否则 `/sdcard/atlas_shared/` 共享目录无法创建，Tasker 和 AutoJS6 的跨进程数据交换链路中断。无需 root 权限。

**Android 系统权限（通过设置 > 应用 > 特殊权限 逐项开启）**：

无障碍服务 (`android.permission.BIND_ACCESSIBILITY_SERVICE`)：AutoJS6 UI 自动化必需。路径：设置 > 辅助功能 > 已安装的应用 > AutoJS6 > 开启。需注意 Samsung One UI 的"已安装的应用"列表可能将 AutoJS6 隐藏在"更多"中。

通知监听 (`android.permission.BIND_NOTIFICATION_LISTENER_SERVICE`)：Tasker 事件触发 Profile 依赖通知监听读取 SMS/Messages 通知内容。路径：设置 > 通知 > 高级设置 > 通知使用权 > Tasker > 开启。

后台运行权限 (Android 12+)：Termux 和 Tasker 均需关闭电池优化以保活。路径：设置 > 应用 > Termux/Tasker > 电池 > 不限制 / 无限制。Samsung 设备额外需在"设备维护" > "电池" > "后台使用限制"中将 Termux 和 Tasker 添加到"不进入休眠的应用"列表。另需在 Tasker 偏好设置中开启"保持服务运行"选项。

自启动权限：Termux 通过 Termux:Boot 插件实现开机自启。路径：安装 Termux:Boot 后，在 Termux 中创建 `~/.termux/boot/` 目录并放入 atlax-boot 脚本。Samsung 设备需额外在"智能管理器"中授予 Termux:Boot 自启动权限。

文件访问权限：AutoJS6 需要"所有文件访问权限"(Android 11+ MANAGE_EXTERNAL_STORAGE) 以读写 `/sdcard/atlas_shared/` 目录。路径：设置 > 应用 > AutoJS6 > 权限 > 文件和媒体 > 允许管理所有文件。

**Samsung 特定权限与配置**：

电池优化白名单：Samsung One UI 的电池管理策略比 AOSP 更激进，需在设备维护 (Device Care) 中将 Termux、Tasker、AutoJS6 三个应用全部添加到"不优化的应用"列表。同时关闭"自适应电池"和"将未使用的应用置于休眠"功能（至少对这三个应用）。

Game Booster 例外：如果用户使用 Game Booster 功能，需在 Game Booster 设置中将 Termux 排除在外，避免游戏模式限制后台 CPU 使用。

Knox 受限操作：Atlas Runtime 的高权限操作（WiFi/Data 切换、SIM 切换）通过 Shizuku/Rish 绕过 Knox 限制，无需 Knox SDK 授权。但以下 Knox 安全策略不可绕过：安全文件夹内的应用不可通过无障碍服务操作、KNOX 工作配置文件与个人资料的数据隔离不可穿透、SE for Android (SEAndroid) 策略不可修改（如 `/sys/class/net/wlan0/` 的写入权限）。

### 3.3 网络带宽要求

部署阶段：首次部署需要从 GitHub clone 代码库（~20MB 压缩）和 pip 安装依赖（aiohttp ~4MB + 其他 ~26MB），总计约 50MB 下载量。建议网络带宽不低于 5Mbps（在此速度下首次部署约 1.5 分钟）。中国区用户通过 Gitee 镜像 clone 可提速 3-5 倍。pip 依赖安装可通过 `--index-url https://pypi.tuna.tsinghua.edu.cn/simple` 使用清华镜像加速。

运行阶段：FIFO 管道通信零网络带宽消耗（直接通过文件系统 inode，不经过 TCP/IP 栈）。HTTP loopback 通过 `127.0.0.1:8787` 同样不消耗外网带宽。仅在代码热更新（git fetch）时需要网络连接，更新数据量为增量差异（典型 50KB-500KB）。Tasker 通过 Termux:Tasker 插件与 Termux 通信，该通信基于 Android Intent 机制 (`am startservice`)，不消耗网络带宽。

弱网降级策略：当网络不可用时，Atlas Runtime 完全正常运行——FIFO 优先触发链（Tasker → FIFO → TriggerServer → Scheduler）100% 离线可用。自动更新检测失败时静默跳过（非阻塞）。远程触发和云端数据同步功能在网络不可用时不可用（非核心路径）。

### 3.4 离线功能支持

**完全离线可用**：FIFO 触发链（Tasker 写入命名管道 → TriggerServer 读取 → 任务调度和执行）完全离线，不依赖任何网络连接。HTTP 127.0.0.1 loopback 服务同样离线可用。本地日志写入和 SQLite 持久化完全离线。健康检查、电池监控、内存控制、熔断器、去重过滤器全部离线运行。AutoJS6 脚本通过共享存储文件系统与 Atlas 交互，离线可用。

**限制**：首次部署需要网络获取代码和 Python 依赖。代码热更新需要网络。SIM 切换验证需要移动网络以读取运营商信息（切换本身通过 Shell 命令完成，无需网络，但后续验证 `getprop gsm.operator.alpha` 需要 SIM 已注册到网络）。远程触发（非本地 HTTP 调用）需要网络。

---

## 第四章：测试方案与通过标准

### 4.1 测试分层架构

Atlas Runtime 测试分两层执行。第一层为 CI 自动化测试层，使用 pytest 框架在 GitHub Actions 上自动运行，覆盖单元测试和集成测试，每次代码推送 (push) 和 Pull Request 时触发。当前测试集共 328 个用例，316 个通过（96.3%），12 个排除项（因 Windows 平台差异和时序敏感问题，目标设备为 Android/Linux 不受影响）。第二层为真机 E2E 手工测试层，在物理设备上按 5 场景 30 项 checklist 执行，每次重大版本发布前强制执行。

### 4.2 屏幕分辨率与显示测试矩阵

AutoJS6 UI 自动化的控件识别依赖于屏幕分辨率和 DPI 设置，因此屏幕适配是兼容性测试的重点维度。

| 分辨率 | 比例 | DPI 范围 | 代表机型 | 测试重点 |
|:---|:---|:---|:---|:---|
| 2400×1080 (FHD+) | 20:9 | 390-420 | S22, Pixel 7 | 竖屏标准布局，UI 控件识别精度 |
| 2340×1080 | 19.5:9 | 400-430 | S21, OnePlus 12 | 略不同的 DPI 密度下的控件偏移 |
| 3120×1440 (QHD+) | 19.5:9 | 510-560 | S25 Plus, S24 Ultra | 高分屏下的紧凑布局、小控件识别 |
| 3088×1440 | 19.3:9 | 500-540 | Pixel 9 Pro XL | 非 Samsung 高分屏适配 |

测试方法：在每个分辨率下依次执行 AutoJS6 的 app_launcher.js（打开设置 > 关于手机）、sim_switch_verify.js（读取运营商名称）、ui_click_sequence.js（执行 5 步点击序列）。每项验证控件是否可识别（`find()` 返回值非空）、点击落点是否在控件范围内（坐标相对于控件左上角的偏移量 <10dp）。

通过标准：所有控件识别成功率 100%（3 次重试内）。点击落点偏移量 <10dp。对于 <360dp 宽度的设备（如旧款 Galaxy S8 的 2960×1440），若控件重叠导致识别失败，降级为接受——记录为已知限制而非阻塞缺陷。

### 4.3 系统版本测试矩阵

Atlas Runtime 的核心路径（Python asyncio、SQLite、Shell 执行）在不同 Android 版本上行为稳定，但 Samsung One UI 的定制层引入了关键差异点，需逐版本验证。

| Android 版本 | One UI 版本 | 代表机型 | 关键差异测试 |
|:---|:---|:---|:---|
| Android 16 | One UI 8.5 | S25 Plus | 基准：全功能验证 |
| Android 15 | One UI 7.1 | S24 系列 | service call 事务码校验 (isub 段) |
| Android 14 | One UI 6.1 | S23 系列 | Knox 限制强度测试 |
| Android 13 | One UI 5.1 | S22 系列 | 电池管理 Doze 行为 |
| Android 12 | One UI 5.0 | S21 系列 | 后台进程生命周期 |
| Android 16 | AOSP | Pixel 9 | 非 Samsung service call 回退 |

每项测试的目标是验证：core/scheduler 任务调度正常（submit → scheduled → executing → success 状态转换）、executors/shell_executor 命令执行和超时 killpg 正常、executors/high_privilege 高权限操作多层回退链正常（WiFi/Data/Volume 切换）、device/health.py 健康检查 (`termux-battery-status` / `dumpsys battery` 回退) 正常、transport/trigger_server FIFO 创建和读取正常。Samsung 设备特有的 service call 事务码测试使用 `config/runtime.yaml` 中预设的事务码（`high_privilege.samsung.service_call_transactions` 段），验证每个事务码的返回值非空且退出码为 0。

通过标准：每个版本 4 类功能（调度、Shell、高权、健康）全部通过。Samsung 设备额外要求 service call 事务码验证通过率 100%（预设码全部返回 0）。若某版本出现不可逾越的系统限制（如 Knox 封锁某事务码），应记录为版本已知限制并给出降级路径。

### 4.4 网络环境测试矩阵

Atlas Runtime 的 FIFO 通信离线可用，但健康检查的电池信息（`termux-battery-status` 通过 Termux:API 的 binder 调用，不走网络）、HTTP loopback 服务响应、以及 `aiohttp` 异步网络库的初始化行为需要在不同网络环境下验证。

| 网络环境 | 参数 | 测试重点 |
|:---|:---|:---|
| Wi-Fi 6/6E | 802.11ax, 低延迟 <5ms | HTTP loopback 响应时间、git fetch 更新速度 |
| 5G NR | SA/NSA, 典型 10-30ms 延迟 | 公网远程触发可达性（若启用） |
| 4G LTE | 典型 30-80ms 延迟 | Tasker 网络状态变化 Profile 触发稳定性 |
| 弱网 (2G/3G 降级) | 100-300ms 延迟 | FIFO 不受影响验证、HTTP loopback 不受影响验证 |
| 极端弱网 | 10% 丢包 + 500ms RTT | git fetch 重试和超时行为、aiohttp 连接超时处理 |
| 飞行模式 | 无网络 | 离线功能完整性验证 |

测试方法：在每种网络环境下验证：FIFO 触发 → 任务执行 → 结果写入的端到端延迟（从 Tasker 触发到 last_result.json 更新的时间）；HTTP loopback `curl http://127.0.0.1:8787/health` 响应时间（应 <50ms 且不受外部网络状态影响）；`git fetch` 的完成时间和超时行为。弱网测试使用 Network Link Conditioner (Android 模拟器) 或 `tc` (traffic control) 命令注入丢包和延迟。

通过标准：FIFO E2E 延迟 P50 <10ms 不受网络环境影响。HTTP loopback 延迟 P95 <50ms 不受外部网络环境影响。git fetch 在弱网（10% 丢包）下 3 次重试内成功或优雅失败（不导致进程崩溃），超时时间按 `runtime.yaml` 中的 `runtime.http.request_timeout` 配置（默认 30s）。在飞行模式下所有核心功能（FIFO 触发、HTTP loopback、Shell 执行、日志写入）正常运行。

### 4.5 性能基准与通过标准

以下为 Tier 1 设备（Samsung S25 Plus）的性能基准和通过阈值：

| 指标 | 基准值 | 通过阈值 | 测量方法 |
|:---|:---|:---|:---|
| Shell 执行成功率 | 100% | >99.9% | 1000 次 `echo hello` + 解析退出码 |
| FIFO 触发延迟 (P50) | <2ms | <5ms | `time dd if=fifo bs=1 count=1` 单侧测量 |
| FIFO E2E 延迟 (P50) | <8ms | <15ms | Tasker 触发 → last_result.json 写入 |
| HTTP 触发延迟 (P95) | <15ms | <50ms | `curl -w "%{time_total}" localhost:8787/health` |
| 内存占用（正常运行） | <100MB | <150MB | `smem -P atlas` 或 /proc/PID/status VmRSS |
| 内存占用（峰值） | <150MB | <200MB | 5 并发高权操作时采集 max VmRSS |
| 崩溃恢复时间 | <3s | <5s | kill -9 PID → 监控 runit 重启 → /health 就绪 |
| CPU 占用（空闲） | <2% | <5% | `top -n 1 -p PID` 间隔 10s 取平均 |
| SQLite 写入成功率 | 100% | >99.99% | 10000 次并发写入 + 校验和验证 |
| 电池消耗（空闲/小时） | <0.3% | <0.5% | 锁屏 1 小时电量差 |
| 启动时间 | <2s | <5s | python app.py 到 /health 返回 200 |
| 熔断恢复延迟 | <35s | <45s | 触发 5 次连续失败 → 等待半开探测 → 成功 |

### 4.6 真机 E2E 手工测试清单

以下 5 场景 30 项在目标设备上手工执行并记录结果。详细执行步骤见项目内 `E2E_CHECKLIST.md`。

场景 1——基础部署验证（8 项）：Termux 环境检查、Python 版本 ≥3.11、pip 依赖完整性、git clone 成功、deploy.sh 14 步全部通过、runit 服务注册成功、Atlas 启动日志正常、/health 端点返回 200。

场景 2——Tasker 触发链验证（6 项）：Tasker 项目导入、时间触发 Profile 执行、事件触发 Profile 执行、状态触发 Profile 执行、SIM 切换 Task 端到端、last_result.json 更新正确。

场景 3——AutoJS6 UI 自动化验证（5 项）：AutoJS6 安装和激活、无障碍服务连接、app_launcher.js 启动设置、ui_click_sequence.js 执行序列、sim_switch_verify.js 运营商验证。

场景 4——故障自愈验证（6 项）：kill -9 主进程→ runit 重启、HTTP 端口占用→ fuser -k 释放重试、Shell 超时→ killpg 清理、存储满→ 拒绝写入切换到只读、FIFO 管道删除→ 自动重建、孤儿锁残留→ 启动时清理。

场景 5——长时间运行验证（5 项）：24 小时持续运行无崩溃、内存泄漏检测（VmRSS 增长 <5MB/h）、日志轮转正常、SQLite 数据库大小稳定、电池消耗 <12%/24h。

通过标准：场景 1-3 全部项目通过。场景 4 每项恢复时间在基准范围内。场景 5 所有指标在阈值内。

---

## 第五章：维护与更新策略

### 5.1 版本号规范

Atlas Runtime 严格遵循语义化版本规范 (Semantic Versioning 2.0.0)：`x.y.z`。x 为主版本号，用于不兼容的 API 变更（如 Python 最低版本要求变更、核心调度器接口重定义、配置 YAML 结构破坏性修改）。y 为次版本号，用于向后兼容的功能新增（如新增执行器类型、新增 Tasker Profile、新增 AutoJS6 脚本）。z 为修订号，用于向后兼容的 bug 修复（如修复内存泄漏、修复特定设备兼容性问题、优化日志输出）。

Git tag 命名格式：`vX.Y.Z`（如 `v9.1.1`）。tag 附注信息需包含：版本号、发布日期、变更摘要（来自 CHANGELOG.md）、关键提醒（Breaking Changes、安全修复、迁移步骤）。若涉及安全漏洞修复，在 tag 附注中标注 CVE 编号。

### 5.2 热更新流程

**适用条件**：y（次版本号）和 z（修订号）级别的变更、非破坏性配置修改、不涉及 SQLite 数据库 schema 变更、不涉及 Python 最低版本要求变更。不符合条件的变更走强制升级流程。

**执行步骤**（全程 <30 秒）：

第一步——预览变更：`cd ~/atlas-runtime && git fetch origin && git log --oneline HEAD..origin/main`，显示即将应用的 commit 列表。若用户确认，继续。

第二步——切换版本：`git checkout tags/vX.Y.Z`（或 `git pull origin main` 用于非 tag 的滚动更新）。若检出失败（工作区有未提交更改），先 `git stash` 暂存。

第三步——重启服务：`sv restart atlas-runtime`。runit 发送 SIGTERM 给旧进程 → 旧进程优雅停止（执行 stop() → 持久化最终快照 → 取消残留任务 → 关闭 event loop）→ runit 启动新进程。

第四步——验证：`sleep 2 && curl -s http://127.0.0.1:8787/health | python -m json.tool | grep '"status":"healthy"'` 确认新版本启动成功且健康检查通过。

**关于 pip 依赖**：热更新通常不涉及 Python 依赖变更。若新版本依赖新增或升级了 pip 包，deploy.sh 会检测到依赖差异并提示执行 `pip install -r requirements.txt --upgrade`。此步骤使热更新总时间增至 ~2-3 分钟（含依赖下载和安装）。

### 5.3 回滚机制

**触发条件**：热更新后 /health 端点连续 3 次返回 status 非 healthy、Tasker 触发成功率在更新后 5 分钟内下降超过 20%、新版本引入无法通过热修复解决的问题且需要紧急切回旧版本。

**执行步骤**（全程 <30 秒）：`cd ~/atlas-runtime && git reflog`（查看最近 HEAD 变更历史，定位旧 commit hash 或 tag）→ `git checkout <old_commit_or_tag>`（切回旧版本）→ `sv restart atlas-runtime`（重启服务）→ 验证 /health 端点恢复正常。

**数据兼容性保证**：同主版本号（x 相同）的回滚不涉及 SQLite schema 变更。回滚后的旧版本代码可正常读写新版本写入的数据文件。跨主版本号的回滚需额外执行 schema 迁移脚本（如有），否则可能遇到 Unknown column 错误。

### 5.4 强制升级触发规则

强制升级意味着用户必须通过 deploy.sh 重新部署（或手动执行等价步骤），不可通过热更新跳过。以下为触发强制升级的决策树：

1. **CVE 安全漏洞级别 >=7.0**：24 小时内通过 GitHub Releases 发布修复版本 → 通过 GitHub Issues 公告和 Tasker 通知（若用户配置了反馈 Task）推送给用户 → 旧版本 /health 端点增加 `"security_advisory": true` 字段并伴随警告日志。

2. **核心 API 不兼容变更**（Shell executor 接口变化、配置 YAML 结构破坏性修改、Scheduler 提交签名变更）：提前 7 天在 CHANGELOG.md 和 GitHub Releases 中公告 → 发布新主版本号 → 提供迁移指南（MIGRATION_vX_to_vY.md）。

3. **关键依赖库 EOL (End of Life)**：如 aiohttp 停止维护、aiosqlite 不再支持当前 Python 版本。提供 2 周窗口期 → 发布依赖升级后的新版本 → 旧版本 /health 端点增加 `"deprecation_notice"` 字段提示。

4. **Android 大版本升级导致的兼容性问题**：如 Android 17 / One UI 9 引入新的后台限制、Knox API 变更导致 service call 事务码失效。在新 Android 版本正式推送后 4 周内发布兼容版本（至少 Tier 1 设备通过验证）。在公告窗口内用户可通过 `/health` 端点检测到 `"platform_warning"` 字段。

5. **database schema 变更**：涉及新表、新列或索引变更。必须包含迁移脚本（`service/migrate_vX_to_vY.sql`），在 deploy.sh 中作为可选步骤（`--migrate` flag）。详见 DESIGN_SPEC_v8.0.md 第七节。

### 5.5 用户反馈渠道与响应 SLA

**渠道 1——Tasker 内 Atlas Feedback Task（结构化反馈，推荐）**

通过 HTTP POST `http://127.0.0.1:8787/trigger` 发送结构化反馈 JSON。格式：`{"action": "feedback", "params": {"type": "bug|feature|question", "severity": "P0|P1|P2|P3", "message": "描述", "context": {"os_version": "...", "one_ui_version": "...", "atlas_version": "..."}}}`。Atlas Runtime 收到后写入 SQLite events 表并（如配置了通知通道）通过邮件/webhook 通知维护者。用户需手动配一个 Tasker Task 与此格式匹配（见 TASKER_INTEGRATION_GUIDE.md 的 ATLAS: 通用触发 Task）。

**渠道 2——GitHub Issues（公开跟踪）**

适用于功能请求、bug 报告、使用问题。维护者使用 label 分类（`bug`、`enhancement`、`question`、`documentation`）和 milestone 关联版本。建议用户提交时附带 Atlas Runtime 的 `/health` 输出和设备信息。

**渠道 3——邮件（安全漏洞专用）**

紧急安全漏洞（不要公开披露）发送至 `atlas-security@example.com`。PGP 公钥置于 SECURITY.md 中。此渠道响应优先级最高。

**响应 SLA 承诺表**：

| 等级 | 定义 | 响应时间 | 修复时间 | 示例 |
|:---|:---|:---|:---|:---|
| P0 | 安全漏洞 / 阻断性缺陷（系统不可用） | 24h | 48h | CVE >=7.0、deploy.sh 在 Tier 1 设备上失败 |
| P1 | 功能缺陷（核心功能不可用） | 3 工作日 | 5 工作日 | SIM 切换失败、FIFO 卡死、内存泄漏 >50MB/h |
| P2 | 优化建议 / 非核心缺陷 | 2 周评估 | 纳入下一迭代 | 日志格式优化、某设备兼容性适配 |
| P3 | 功能请求 | 2 周评估 | 按 Roadmap 排期 | 新执行器支持、新 AutoJS6 脚本 |

SLA 基于工作日内（周一至周五，北京时间 9:00-18:00）。P0 支持 5×8 工作小时制，非工作时间发现的 P0 在下个工作日开始计时。所有响应通过反馈渠道原路回复（GitHub Issue 回复评论、Tasker 反馈在 Issue 中创建跟踪卡片、邮件回复）。

---

## 附录 A：文档引用索引

本部署方案中引用的子文档及其定位：

- `service/deploy.sh` — 14 步一键部署脚本，覆盖 Termux 环境配置到服务启动的全部步骤
- `docs/SAMSUNG_ONEUI85_COMPAT.md` — Samsung One UI 8.5 兼容性详细分析，包含特性矩阵、Service Call 事务码参考和故障排除
- `docs/TASKER_INTEGRATION_GUIDE.md` — Tasker 项目导入、Profile/Task 配置和触发链调试指南
- `docs/AUTOJS6_SCRIPT_GUIDE.md` — 6 个 AutoJS6 脚本的部署方法、参数说明和扩展开发指南
- `docs/ARCHITECTURE.md` — 6 层架构设计、依赖规则和组件定位
- `docs/DESIGN_SPEC_v8.0.md` — 完整设计规格书，含启动编排、数据流、故障自愈策略
- `docs/TEST_REPORT.md` — CI 自动化测试报告（316/328 通过）
- `config/runtime.yaml` — 运行时配置（含所有可调参数及其默认值）
- `E2E_CHECKLIST.md` — 5 场景 30 项真机测试清单（项目内文件）

## 附录 B：术语表

| 术语 | 说明 |
|:---|:---|
| Termux | Android 终端模拟器 + Linux 环境，提供包管理器 (pkg) 和 API 接口 |
| Termux:API | Termux 插件，通过 Android API 暴露电池/传感器/WiFi/通知等硬件能力 |
| Termux:Boot | Termux 插件，设备开机时自动执行 `~/.termux/boot/` 中的脚本 |
| Termux:Widget | Termux 插件，通过桌面小组件执行 Shell 脚本 |
| Tasker | Android 自动化应用，通过 Profile（条件）+ Task（动作）实现事件驱动的自动化 |
| AutoJS6 | 基于 JavaScript + 无障碍服务的 Android UI 自动化框架（开源社区维护版） |
| Shizuku | 无需 root 即可调用系统级 API 的中间件，通过 ADB 或无线调试启动 |
| Rish | Shizuku 提供的交互式 Shell，可执行需要 ADB 权限的命令（如 service call） |
| FIFO | 命名管道（Named Pipe），一种进程间单向通信机制，Atlas 用它替代 HTTP 作为主触发通道 |
| runit | 轻量级 Linux 进程守护工具，Termux 通过 termux-services 包提供 |
| Knox | Samsung 设备安全平台，提供硬件级隔离、安全文件夹和企业管理功能 |
| service call | Android 系统服务 IPC 调用命令，通过事务码（transaction code）与系统服务交互 |
| WAL | Write-Ahead Logging，SQLite 写入模式，提高并发写入性能 |
