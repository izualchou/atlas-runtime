---
name: mobile-deployment-plan
overview: 为 Atlas Runtime v9.1 制定完整的手机端部署方案文档，涵盖部署目标、混合部署渠道策略、环境配置要求、全场景测试流程、以及维护与更新策略五大模块。
todos:
  - id: deploy-target
    content: 编写第一章：部署目标与设备兼容性矩阵 — 定义 Samsung S25 Plus 主目标规格、Tier 1/2/3 三级设备分级标准、每级功能支持范围和已知限制
    status: completed
  - id: deploy-strategy
    content: 编写第二章：混合部署策略 — 组件-渠道匹配矩阵、F-Droid/Google Play/Firebase App Distribution/GitHub Releases/PWA 各渠道的分发流程与选择理由
    status: completed
  - id: env-requirements
    content: 编写第三章：环境配置规范 — 最低硬件规格、三层权限清单（Termux/Android 系统/Samsung 特定）、网络带宽需求和离线能力分析
    status: completed
  - id: test-plan
    content: 编写第四章：测试方案与通过标准 — 屏幕分辨率/系统版本/网络环境测试矩阵及量化通过标准，区分 CI 自动化测试和真机 E2E 手工测试
    status: completed
  - id: maintenance
    content: 编写第五章：维护与更新策略 — 热更新流程与回滚机制、强制升级触发决策树、三层反馈渠道与 SLA 承诺表
    status: completed
  - id: finalize-doc
    content: 汇总所有章节、添加文档元数据和跨文档引用链接、最终审查表格一致性和编号连续性
    status: completed
    dependencies:
      - deploy-target
      - deploy-strategy
      - env-requirements
      - test-plan
      - maintenance
---


## 用户需求

基于已完成审计、修复并通过 316 项测试的 Atlas Runtime v9.1 代码库，制定一份完整的手机端标准化部署方案文档 `docs/DEPLOYMENT_PLAN.md`，供生产交付使用。文档需覆盖五大模块：

1. **部署目标**：以 Samsung S25 Plus (Android 16 / One UI 8.5) 为主要目标设备，按 Tier 1/2/3 三级对其他 Android 机型做兼容性分级，明确每级的支持范围与适配策略。

2. **部署方式**：Atlas Runtime 是混合组件系统（非单一 APK），需为每个组件匹配最优分发渠道。Termux 系列走 F-Droid，Tasker 走 Google Play，AutoJs6 APK 走 Firebase App Distribution 内测分发，Atlas Runtime Core 代码走 GitHub Releases + git clone，配套 PWA 状态监控面板（可选）。说明各渠道的选择理由与分发流程。

3. **环境配置要求**：最低硬件配置（ARM64-v8a / 4GB RAM / 500MB 存储），分 Termux 内 / Android 系统 / Samsung 特定三层权限清单，网络带宽需求（部署阶段 vs 运行阶段），离线功能支持的具体能力（FIFO 管道 100% 离线，HTTP loopback 无外网依赖）与限制。

4. **测试流程**：覆盖 2400x1080 至 3120x1440 屏幕分辨率、Android 12-16（含 One UI 5-8.5）系统版本、Wi-Fi/4G/5G/弱网（2G + 10% 丢包 + 500ms 延迟）环境矩阵的功能/性能/兼容性测试方案，每项附量化通过标准。测试分 CI 自动化（316 项已通过）和真机 E2E 手工执行两层。

5. **维护与更新策略**：热更新（git fetch + git checkout tag + sv restart）触发条件与回滚机制（git reflog + 切回旧 tag），强制升级触发规则（CVE >=7.0 / 不兼容 API 变更 / 依赖库 EOL），用户反馈渠道（Tasker 内结构化反馈 / GitHub Issues / 邮件）及各级 SLA 承诺（P0 24h / P1 3 工作日 / P2 2 周 / P3 按 Roadmap）。



## 文档架构与内容组织

### 文档框架

`docs/DEPLOYMENT_PLAN.md` 将采用分层结构：每章以策略级决策为主线，具体操作步骤引用现有子文档（`deploy.sh`、`SAMSUNG_ONEUI85_COMPAT.md`、`TASKER_INTEGRATION_GUIDE.md`、`AUTOJS6_SCRIPT_GUIDE.md`），避免冗余。新增内容聚焦部署特有的决策逻辑、标准定义和执行策略。

### 章节规划

**第一章：部署目标与设备兼容性矩阵**
- Samsung S25 Plus 主目标详细规格（SoC: Snapdragon 8 Gen 4 / Exynos 2500, RAM: 12GB, 存储: 256GB+, 屏幕: 3120x1440 Dynamic AMOLED 2X, One UI 8.5 / Android 16）
- Tier 1（全功能验证）：Samsung One UI 8.x 旗舰系列（S25/S24/S23 系列）+ One UI 7.x 旗舰（S22 系列）—— 所有功能包括 SIM 切换、UI 自动化、高权限操作均通过验证
- Tier 2（核心功能兼容）：Android 12+ 主流厂商（Pixel 7-9 / OnePlus 12-13 / Xiaomi 14-15）—— Shell 执行、FIFO 通信、HTTP 服务均可用，但 Samsung 特有 service call 事务码需适配或回退到 AOSP 标准命令
- Tier 3（基础运行）：Android 7-11 设备 —— 仅保证 Python 运行时和 Termux 服务可启动，不保证高权限操作和 UI 自动化
- 每级附带已知限制列表（从 `SAMSUNG_ONEUI85_COMPAT.md` 第 3-4 节提取关键要点）

**第二章：混合部署策略**
- 组件-渠道匹配矩阵（组件类型 × 分发渠道，附选择理由）
- F-Droid 分发流程（Termux + Termux:API + Termux:Boot + Termux:Widget）：版本策略（跟随上游稳定版）、安装验证脚本
- Google Play 分发流程（Tasker + AutoApps 插件）：商业化 APP，链接到 Play 商店页面
- Firebase App Distribution 内测分发（AutoJs6 APK）：适用场景（内部测试、预发布验证）、分发流程（上传 APK → 邀请测试者 → 自动通知 → 崩溃报告收集）
- GitHub Releases + git clone 分发（Atlas Runtime Core + 脚本 + 配置）：版本管理策略（git tag x.y.z）、更新流程、镜像加速
- PWA 状态监控面板（可选增值组件）：技术栈（HTML + Chart.js，通过 localhost:8787/health 获取状态数据）、部署方式（静态文件托管至 GitHub Pages / 本地 localhost）

**第三章：环境配置规范**
- 硬件最低配置：SoC（ARM64-v8a 必选）、RAM（4GB 最低，6GB+ 推荐）、存储可用空间（Termux 环境 ~200MB + 依赖 ~100MB + 数据 ~200MB = 500MB）、屏幕（720p 最低，1080p+ 推荐）
- 三层权限清单：
  - Termux 内权限（termux-setup-storage 授予存储访问，无需 root）
  - Android 系统权限（无障碍服务、通知监听、后台运行、忽略电池优化；每项附获取方式：设置路径 + adb 命令）
  - Samsung 特定权限（电池优化白名单、Game Booster 例外、Knox 受限操作列表；附操作路径）
- 网络需求：部署阶段（首次 clone ~20MB 代码 + ~30MB pip 依赖，建议 >5Mbps）、运行阶段（FIFO 管道零带宽；HTTP loopback 无外网消耗；仅代码更新时需要网络）；弱网下的降级策略（FIFO 优先，HTTP 备选，更新延迟允许）
- 离线能力：FIFO 触发链 100% 离线（不经过 TCP/IP 栈）；HTTP 127.0.0.1 无外网依赖；Tasker→Termux:Tasker→FIFO 路径完全离线；限制（首次部署需网络获取代码和依赖、远程触发和云端同步需网络）

**第四章：测试方案与通过标准**
- 测试分层：CI 自动化测试（316 项单元/集成测试在 GitHub Actions 上执行，Windows/Linux 双平台）+ 真机 E2E 手工测试（5 场景 30 项在目标设备上执行）
- 屏幕分辨率测试矩阵（覆盖 2400x1080 FHD+、2340x1080、3120x1440 QHD+、20:9 和 19.5:9 比例），每类对应代表机型
- 系统版本测试矩阵（Android 12/13/14/15/16 × One UI 5/6/7/8/8.5 × AOSP），标注核心差异点（Samsung service call 事务码、Knox 限制强度、电池管理策略）
- 网络环境测试矩阵：Wi-Fi 6/6E、5G NR、4G LTE、弱网（2G/3G 降级、10% 丢包、500ms 往返延迟），每种环境下的测试重点和预期行为
- 量化通过标准表：Shell 执行成功率 >99.9%、FIFO 触发延迟 <5ms（本地 P50）、HTTP 触发延迟 <50ms（本地 P95）、内存占用 <150MB（正常运行）、<200MB（峰值）、崩溃恢复时间 <5s（runit 保活）、CPU 占用 <5%（空闲）、SQLite 写入成功率 >99.99%

**第五章：维护与更新策略**
- 版本号规范：遵循 Semantic Versioning x.y.z（x=不兼容 API 变更, y=功能新增, z=bug 修复）
- 热更新流程：`git fetch origin && git log --oneline HEAD..origin/main`（预览）→ `git checkout tags/vX.Y.Z`（切换版本）→ `sv restart atlas-runtime`（重启服务）→ `curl http://127.0.0.1:8787/health`（验证），全程 <30 秒
- 热更新适用条件：y 和 z 级别变更、非破坏性配置修改、不涉及数据库迁移
- 回滚机制：`git reflog`（查看历史）→ `git checkout <旧commit>`（切回）→ `sv restart atlas-runtime`（重启），恢复时间 <30 秒
- 强制升级触发规则（决策树）：CVE >=7.0 安全漏洞（24h 内强制推送）、核心 API 不兼容变更（提前 7 天公告后推送）、关键依赖库 EOL（2 周窗口期）、Android 大版本升级导致兼容性问题（在公告窗口内推送兼容版本）、数据库 schema 变更（需手动迁移，见 DESIGN_SPEC 第七节）
- 用户反馈三层渠道：
  - Tasker 内 Atlas Feedback Task（通过 HTTP POST /trigger 发送结构化反馈 JSON，格式：{action: "feedback", params: {type, severity, message, context}}，自动写入 events 表并通知维护者）
  - GitHub Issues（公开跟踪，使用 label 和 milestone 分类）
  - 邮件（紧急安全漏洞专用，PGP 签名可选）
- SLA 承诺表：P0 安全漏洞/阻断性缺陷 24h 响应 48h 修复、P1 功能缺陷 3 工作日响应 5 工作日修复、P2 优化建议 2 周评估后纳入迭代、P3 功能请求按 Roadmap 排期

### 文档元数据

- 版本号：v1.0
- 生效日期：2026-08-08
- 维护者：Atlas DevOps Group
- 审核周期：每季度一次或重大架构变更时更新

### 复用策略

新增文档的重点是部署策略、标准和决策逻辑，具体操作步骤通过引用链接复用现有文档：`deploy.sh` 的 14 步流程、`SAMSUNG_ONEUI85_COMPAT.md` 的特性矩阵和故障排除、`TASKER_INTEGRATION_GUIDE.md` 的 Tasker 配置步骤、`AUTOJS6_SCRIPT_GUIDE.md` 的脚本部署方法。每个引用标为"[详见 xxx](xxx.md)"格式。

