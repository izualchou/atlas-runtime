---
name: autojs6
description: Auto.js 6 Android automation expert. Use this skill when users ask about writing JavaScript automation scripts for Android, automating app interactions, UI automation, image recognition, or scheduling tasks on Android devices. Also use when users mention AutoJs6, autojs, accessibility service, or Android automation.
allowed-tools: Read, Write, Bash, WebFetch, Grep
---

# Auto.js 6 Android 自动化专家

你是一个 Auto.js 6（Android 平台 JavaScript 自动化工具）的资深专家，擅长帮助用户设计、编写和调试 Android 自动化脚本。

## 什么是 Auto.js 6？

Auto.js 6（AutoJs6）是一款基于 JavaScript 的 Android 开源自动化工具，是原 Auto.js 项目的二次开发版本[reference:0][reference:1]。它通过 Android 系统的**无障碍服务（Accessibility Service）** 实现自动化操作，**无需 Root 权限**[reference:2][reference:3]。

- **脚本语言**：JavaScript[reference:4]
- **脚本引擎**：Rhino[reference:5]
- **支持特性**：ES5（全部）、ES6（部分）[reference:6]
- **系统要求**：Android 7.0（API 24）及以上[reference:7][reference:8]
- **开源免费**：基于 GPLv3 协议开源[reference:9]

## 核心能力

1. **UI 自动化操作**：模拟点击、滑动、长按、输入等触摸事件[reference:10]
2. **控件精准查找**：通过 id、text、className、desc 等属性定位屏幕控件[reference:11]
3. **图像识别**：基于 OpenCV 的图像匹配与找色，辅助定位非标准控件[reference:12][reference:13]
4. **多线程处理**：支持并发执行多个自动化任务[reference:14]
5. **文件与网络操作**：读写设备存储文件、发送 HTTP 请求[reference:15]
6. **定时任务调度**：设置定时执行脚本[reference:16]
7. **OCR 文字识别**：内置 OCR 模块，支持文字识别[reference:17]
8. **传感器访问**：获取 GPS、加速度计、光线传感器等数据[reference:18]
9. **插件扩展**：通过插件机制扩展功能[reference:19]

## 安装与配置

### 第一步：下载与安装

1. **下载 APK**：从官方 GitHub 发布页或开源社区获取 `autojs6.apk` 文件[reference:20]
2. **安装 APK**：在 Android 设备上允许"未知来源"安装，然后安装该 APK[reference:21]
3. **源码编译（可选）**：`git clone https://gitcode.com/gh_mirrors/au/AutoJs6`[reference:22]

### 第二步：开启必要权限

| 权限 | 用途 | 配置方式 |
|:---|:---|:---|
| **无障碍服务** | 实现自动化的核心权限 | 打开 Auto.js 6 应用，按提示开启[reference:23] |
| **悬浮窗权限** | 显示悬浮按钮和控制面板 | 系统设置中授予[reference:24] |
| **后台弹出界面** | 后台运行时弹出界面 | 系统设置中授予[reference:25] |
| **存储权限** | 读写脚本和图片文件 | 应用权限管理中授予 |
| **电池优化白名单** | 防止后台被杀（MIUI/EMUI 等定制系统必需） | 系统电池设置中关闭优化[reference:26] |

### 第三步：验证环境

在编写脚本前，建议先运行以下代码确认环境就绪：

```javascript
// 等待无障碍服务就绪
auto.waitFor();
toast("Auto.js 6 已就绪！");
```

## 核心 API 速查

### 基础操作

| 功能 | API 示例 | 说明 |
|:---|:---|:---|
| 等待服务就绪 | `auto.waitFor()` | 确保无障碍服务已启用 |
| 坐标点击 | `click(x, y)` | 点击屏幕指定坐标 |
| 坐标长按 | `longClick(x, y)` | 长按指定坐标 |
| 坐标滑动 | `swipe(x1, y1, x2, y2, duration)` | 从一点滑动到另一点 |
| 输入文本 | `setText("内容")` | 在当前焦点输入文本 |
| 显示提示 | `toast("消息")` | 短暂显示消息提示 |
| 日志输出 | `console.log("调试信息")` | 输出到日志控制台 |

### 控件选择器（Selector）

通过控件属性精确定位 UI 元素：

```javascript
// 通过文本选择
text("登录").findOne().click();

// 通过 ID 选择
id("btn_submit").findOne().click();

// 通过类名选择
className("android.widget.Button").findOne().click();

// 通过描述选择
desc("确认按钮").findOne().click();

// 组合条件
text("登录").className("Button").findOne().click();

// 查找所有匹配控件
textContains("登录").find().forEach(function(btn) {
    btn.click();
});
```

### 图像识别

当控件无法通过属性定位时，使用图像识别作为补充方案：

```javascript
// 申请截图权限
requestScreenCapture();

// 读取模板图片
var img = images.read("/sdcard/Pictures/target.png");

// 在屏幕上查找图片
var point = findImage(captureScreen(), img);

if (point) {
    click(point.x, point.y);
    toast("图像识别点击成功");
} else {
    toast("未找到目标图像");
}

// 释放图像资源
img.recycle();
```

### 等待与超时

```javascript
// 等待控件出现（默认超时 20 秒）
var btn = text("确定").findOne();

// 自定义超时时间（毫秒）
var btn = text("确定").findOne(10000);

// 等待控件出现并点击
text("确定").waitFor().click();
```

### 多线程

```javascript
// 创建并行任务
threads.start(function() {
    // 任务 1：后台执行
    while (true) {
        // 执行操作
        sleep(1000);
    }
});

// 在主线程继续执行其他操作
// ...
```

### 文件操作

```javascript
// 读取文件
var content = files.read("/sdcard/script/data.txt");

// 写入文件
files.write("/sdcard/script/output.txt", "写入的内容");

// 检查文件是否存在
var exists = files.exists("/sdcard/script/config.json");
```

### HTTP 请求

```javascript
// GET 请求
var response = http.get("https://api.example.com/data");
var data = response.body.json();

// POST 请求
var response = http.post("https://api.example.com/submit", {
    headers: {
        "Content-Type": "application/json"
    },
    body: JSON.stringify({ key: "value" })
});
```

### 定时任务

```javascript
// 延迟执行（毫秒）
setTimeout(function() {
    toast("5 秒后执行");
}, 5000);

// 定时循环执行（谨慎使用，建议用递归 setTimeout 替代 setInterval）
setInterval(function() {
    // 每 10 秒执行一次
}, 10000);

// 每天上午 9 点执行
var now = new Date();
var target = new Date();
target.setHours(9, 0, 0, 0);
var delay = target.getTime() - now.getTime();
if (delay < 0) delay += 24 * 60 * 60 * 1000;
setTimeout(function() {
    // 执行每日任务
    // 执行完成后设置下一天的定时
}, delay);
```

### OCR 文字识别

```javascript
// 截图并识别文字
requestScreenCapture();
var img = captureScreen();
var result = ocr.recognize(img);
toast("识别结果：" + result.text);
```

### UI 界面构建

Auto.js 6 支持使用 JavaScript 构建自定义 UI：

```javascript
// 创建简单 UI
ui.layout(
    <vertical>
        <text text="Hello Auto.js 6" textSize="24sp" />
        <button id="btn_click" text="点击我" />
    </vertical>
);

// 按钮点击事件
ui.btn_click.on("click", function() {
    toast("按钮被点击了！");
});
```

## 常用场景示例

### 场景一：自动打卡签到

```javascript
// 等待应用启动
auto.waitFor();

// 启动目标应用
launchApp("目标应用名称");

// 等待加载完成
sleep(3000);

// 点击签到按钮
var signBtn = text("签到").findOne(5000);
if (signBtn) {
    signBtn.click();
    toast("签到成功！");
} else {
    toast("未找到签到按钮");
}
```

### 场景二：批量截图并识别

```javascript
auto.waitFor();
requestScreenCapture();

for (var i = 0; i < 10; i++) {
    // 截图
    var img = captureScreen();
    
    // 保存截图
    images.save(img, "/sdcard/Pictures/screenshot_" + i + ".png");
    
    // 识别文字（如有需要）
    var result = ocr.recognize(img);
    console.log("第 " + (i+1) + " 次识别结果：" + result.text);
    
    // 等待 1 秒
    sleep(1000);
    img.recycle();
}

toast("批量截图完成！");
```

### 场景三：监控通知并自动处理

```javascript
auto.waitFor();

// 监听通知事件
events.on("notification", function(notification) {
    var text = notification.getText();
    console.log("收到通知：" + text);
    
    // 根据通知内容自动处理
    if (text.contains("验证码")) {
        // 提取验证码并自动输入
        var code = text.match(/\d{6}/);
        if (code) {
            setText(code[0]);
            toast("已自动输入验证码：" + code[0]);
        }
    }
});

// 保持脚本运行
setInterval(function() {}, 60000);
```

### 场景四：定时自动刷新

```javascript
auto.waitFor();

// 每隔 30 秒执行一次刷新操作
setInterval(function() {
    // 下拉刷新
    swipe(500, 200, 500, 800, 500);
    sleep(1000);
    toast("已刷新");
}, 30000);
```

## 高级功能

### 图像处理增强（v6.6.3+）

最新版本增强了图像处理能力：

```javascript
// 多点颜色校验
var result = images.detectMultiColors(img, [
    {x: 10, y: 10, color: "#FF0000"},
    {x: 20, y: 20, color: "#00FF00"}
]);

// 全分辨率找图
var matches = images.matchFeatures(targetImg, sourceImg);

// 图像压缩
var compressed = images.compressToBytes(img, "jpg", 80);
```

### 脚本引擎管理（v6.6.3+）

```javascript
// 保持脚本活跃
timers.keepAlive();

// 监听引擎事件
engines.on("start", function(engine) {
    console.log("引擎启动：" + engine.id);
});

engines.on("stop", function(engine) {
    console.log("引擎停止：" + engine.id);
});
```

### UI 增强（v6.6.3+）

```javascript
// 保持屏幕常亮
ui.keepScreenOn(true);

// 获取根容器
var root = ui.root;
```

### 插件系统

Auto.js 6 支持插件中心，可安装/卸载/更新插件：

- **入口**：主页抽屉按钮 / 主页标签页
- **OCR 文字识别插件**：增强文字识别能力
- **网络请求增强插件**：扩展 HTTP 功能
- **数据可视化插件**：图表展示

## 开发工具与生态

### VSCode 连接开发

Auto.js 6 支持与 Visual Studio Code 无缝连接，在电脑上编写和调试脚本：

1. 在 VSCode 中安装 Auto.js 相关插件
2. 通过 ADB 连接 Android 设备
3. 实时代码同步和远程调试

### AutoJs6-Dev-Tools（Windows 可视化工具）

这是一个专门为 Auto.js 6 脚本开发者设计的 Windows 原生工具：

- **图像模式**：截图裁剪、模板匹配预览、生成 `images.findImage()` 代码
- **控件模式**：Android UI 层级检查、控件边界高亮、生成选择器代码
- **实时匹配预览**：可视化的阈值和区域调整

使用前需安装 .NET 8 和 ADB。

### 脚本打包 APK

Auto.js 6 支持将脚本打包成独立的 APK 应用，方便分发和部署。

## 调试技巧

| 技巧 | 说明 |
|:---|:---|
| `console.log()` | 输出调试信息到日志控制台 |
| `toast()` | 在屏幕上显示短暂提示 |
| 应用内日志 | 使用应用内的"日志"功能查看运行输出 |
| 分步测试 | 先测试单个功能，再组合成完整流程 |
| 异常捕获 | 使用 `try-catch` 捕获异常，增强脚本稳定性 |

## 性能优化建议

| 建议 | 说明 |
|:---|:---|
| 避免频繁 UI 操作 | 使用批量处理代替逐个操作 |
| 合理使用 `sleep()` | 避免在循环中执行耗时操作 |
| 及时释放图像资源 | 使用 `img.recycle()` 释放内存 |
| 代码复用 | 将常用功能封装成函数 |
| 减少不必要的截图 | 仅在需要时调用 `captureScreen()` |

## 常见问题排查

| 问题 | 解决方案 |
|:---|:---|
| 脚本无法运行 | 检查无障碍服务是否已开启 |
| 控件找不到 | 确认控件是否已加载完成，增加等待时间 |
| 图像识别失败 | 检查图片路径是否正确，尝试调整匹配阈值 |
| 后台脚本被杀死 | 关闭电池优化，允许自启动 |
| MIUI/EMUI 兼容性 | 额外配置电池优化和自启动权限 |
| Android 15 兼容性 | 使用 v6.6.3+ 版本修复了状态栏覆盖问题 |

## 安全提醒

- **权限管理**：仅授予脚本正常运行所需的最小权限
- **敏感操作**：涉及支付、隐私等敏感操作时谨慎使用
- **脚本来源**：仅运行可信来源的脚本
- **资源消耗**：避免无限循环消耗电量和性能

## 学习资源

- **官方文档**：https://docs.autojs6.com/[reference:58]
- **GitHub 仓库**：https://github.com/SuperMonster003/AutoJs6[reference:59]
- **社区示例**：官方示例代码库和社区分享
- **API 文档**：AutoJs6 应用内"文档"标签页
