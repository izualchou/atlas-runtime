# AutoJS6 脚本开发指南

版本: v1.0 | 日期: 2026-08-08

本文档说明 Atlas Runtime 配套 AutoJS6 脚本的使用和开发方法。

---

## 脚本清单

Atlas Runtime 提供 6 个 AutoJS6 脚本，位于 `scripts/autojs/`：

| 文件 | 用途 | 依赖 |
|------|------|------|
| `atlas_ui_template.js` | 通用 UI 自动化框架 | 无（基础模块） |
| `sim_switch_verify.js` | SIM 卡切换后验证运营商 | atlas_ui_template.js |
| `app_launcher.js` | 通用 APP 启动 + 操作序列 | atlas_ui_template.js |
| `ui_click_sequence.js` | 通用 UI 点击序列 | atlas_ui_template.js |
| `health_check_ui.js` | 系统健康检查验证 | atlas_ui_template.js |
| `battery_monitor.js` | 电池状态持续监控 | atlas_ui_template.js |

---

## 部署脚本到设备

### 方法一：通过 HTTP 触发（推荐）

Atlas Runtime 通过 `autojs_launcher.py` 自动启动 AutoJS6 脚本。

1. 将 `scripts/autojs/` 目录复制到 `/sdcard/atlas_shared/autojs/`
2. Atlas 通过 `am` 命令携带参数文件路径启动脚本

### 方法二：AutoJS6 手动运行

1. 将脚本复制到 AutoJS6 的脚本目录
2. 在 AutoJS6 应用中打开脚本
3. 点击运行按钮（确保无障碍服务已开启）

### 方法三：通过定时脚本

创建 AutoJS6 定时任务，每 30 秒检测 `/sdcard/atlas_shared/` 中的 fallback 文件：

```javascript
// autojs_fallback_checker.js - 放在 AutoJS6 定时任务中
var fallbackDir = "/sdcard/atlas_shared/";
var files = java.nio.file.Files.list(java.nio.file.Paths.get(fallbackDir));
var iterator = files.iterator();
while (iterator.hasNext()) {
    var path = iterator.next().toString();
    if (path.indexOf("autojs_fallback_") >= 0 && path.endsWith(".json")) {
        var content = files.read(path);
        var request = JSON.parse(content);
        // 根据 request.script_name 启动对应脚本
        toast("AutoJS6 fallback: starting " + request.script_name);
        engines.execScriptFile(fallbackDir + request.script_name);
        files.remove(path);  // 清理标记文件
    }
}
```

---

## 脚本详解

### atlas_ui_template.js — 基础模板

所有其他脚本的基础框架，提供：

- **无障碍服务初始化**: `auto.waitFor()` 等待服务就绪
- **参数解析**: 从 `engines.myEngine().execArgv.scriptParams` 或本地 JSON 文件读取参数
- **结果上报**: HTTP POST（优先）→ 本地文件写入（兜底）
- **超时保护**: 全局 `setTimeout` + 超时自动退出和上报
- **日志系统**: `console.log` + `toast` + 文件日志

导出接口：

```javascript
module.exports = {
    CONFIG,            // 全局配置对象
    Logger,            // 日志工具
    parseParams,       // 参数解析函数
    ResultReporter,    // 结果上报器
    AccessibilityHelper, // 无障碍辅助
    run                // 主入口 (executeFn) => void
};
```

### sim_switch_verify.js — SIM 切换验证

执行 SIM 切换后的运营商验证。

参数:
- `slot`: 0（卡 1）或 1（卡 2）
- `expected_operator`: 期望的运营商名称

验证流程:
1. 通过 adb/shell 打开 SIM 卡管理设置
2. 使用无障碍服务读取运营商名称文本
3. 对比期望值与实际值
4. 通过 `getprop gsm.operator.alpha` 备选验证

### app_launcher.js — 通用 APP 启动器

启动指定 APP 并执行操作序列。

参数:
- `app_name` 或 `app_package`: 目标应用
- `actions`: 操作序列数组，每项包含 `type`、`target`、`wait` 等

支持的操作类型:
- `click`: 文本匹配点击
- `long_click`: 长按
- `input`: 文本输入（需目标控件可编辑）
- `swipe`: 滑动（上/下/左/右）
- `back`/`home`: 返回/主页
- `wait`: 等待指定毫秒

### ui_click_sequence.js — UI 点击序列

在当前界面按顺序执行预定义操作。

参数:
- `steps`: 步骤数组

支持的步骤:
- `click`/`click_id`/`click_desc`/`click_xy`: 多种匹配方式的点击
- `long_click`/`long_click_xy`: 长按
- `input`: 输入文本
- `wait`: 等待
- `scroll_up`/`scroll_down`: 滚动
- `back`: 返回

### health_check_ui.js — 健康检查

验证系统关键服务状态。

检查项:
- `accessibility`: 无障碍服务是否活跃
- `storage`: 存储读写是否正常
- `network`: 网络连接 + Atlas 服务可达性
- `battery`: 电池电量读取

### battery_monitor.js — 电池监控

持续监控电池状态并向 Atlas 上报。

参数:
- `interval_sec`: 采集间隔（默认 60 秒）
- `low_threshold`: 低电量阈值（默认 20%）
- `critical_threshold`: 严重低电量阈值（默认 10%）
- `single_shot`: 是否只采集一次

特点:
- 电量低于严重阈值时自动加大采集间隔
- 仅在电量/充电状态变化时上报
- HTTP 上报优先，文件兜底

---

## 扩展开发指南

### 创建新脚本

1. 在 `scripts/autojs/` 下创建新 `.js` 文件
2. 加载模板: `var Template = require("./atlas_ui_template.js");`
3. 实现 `execute(params)` 函数
4. 调用 `Template.run(execute);`

示例模板：

```javascript
"use strict";
var Template = require("./atlas_ui_template.js");

function execute(params) {
    Template.Logger.info("Starting my script");

    // 1. 你的业务逻辑
    // ...

    // 2. 返回结果
    return {
        success: true,
        data: {
            message: "Done",
            detail: "All steps completed"
        }
    };
}

var params = Template.parseParams();
params.script_name = "my_custom_script";
Template.run(execute);
```

### 注意事项

- **Rhino 引擎限制**: AutoJS6 使用 Mozilla Rhino 引擎，不完全支持 ES6+。避免使用箭头函数（`=>`）、`let`/`const`（使用 `var`）、模板字符串、`Promise`。
- **三星 One UI 8.5 约束**: Knox 可能限制无障碍服务对某些系统界面的访问。遇到 `SecurityException` 时确认已在无障碍设置中为 AutoJS6 开启所有权限。
- **超时设置**: 三星设备在屏幕关闭后可能暂停无障碍服务。建议将 `timeout_sec` 控制在 120 秒内，超过此值考虑使用分步执行。
- **内存管理**: 长时间运行的脚本（如 battery_monitor.js）应定期清理不再使用的变量，避免 OOM。
