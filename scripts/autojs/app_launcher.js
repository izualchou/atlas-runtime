/**
 * app_launcher.js — 通用 APP 启动器
 * 版本: v1.0
 * 
 * 用途: 启动指定 APP，执行预定义操作序列，然后返回。
 *       适用于需要自动打开 APP 并执行简单操作的场景。
 * 
 * 参数:
 *   app_name: "微信" — 要启动的应用名称
 *   app_package: "com.tencent.mm" — 可选，包名（用于精确启动）
 *   actions: [{type:"click", target:"发现"}, {type:"click", target:"朋友圈"}]
 *            — 可选，启动后执行的操作序列
 *   timeout_sec: 45 — 超时秒数
 * 
 * 依赖: atlas_ui_template.js、无障碍服务
 */

"use strict";

var Template = require("./atlas_ui_template.js");

/**
 * 执行 APP 启动和操作序列
 */
function execute(params) {
    var appName = params.app_name;
    var appPackage = params.app_package;
    var actions = params.actions || [];
    
    if (!appName && !appPackage) {
        return {
            success: false,
            data: { error: "Either app_name or app_package is required" }
        };
    }
    
    // 步骤 1: 启动 APP
    var launched = launchApp(appName, appPackage);
    if (!launched) {
        return {
            success: false,
            data: {
                step: "launch",
                error: "Failed to launch: " + (appName || appPackage)
            }
        };
    }
    
    Template.Logger.info("App launched: " + (appName || appPackage));
    
    // 步骤 2: 等待 APP 加载
    sleep(2500);
    
    // 步骤 3: 执行操作序列
    var actionResults = [];
    for (var i = 0; i < actions.length; i++) {
        var action = actions[i];
        var result = executeAction(action, i);
        actionResults.push(result);
        
        if (!result.success && action.required) {
            return {
                success: false,
                data: {
                    step: "action_" + i,
                    action: action,
                    error: result.error,
                    completed_actions: actionResults
                }
            };
        }
    }
    
    return {
        success: true,
        data: {
            app_name: appName || appPackage,
            action_count: actions.length,
            actions_completed: actionResults.filter(function(r) { return r.success; }).length,
            action_results: actionResults
        }
    };
}

/**
 * 启动应用
 */
function launchApp(name, pkg) {
    try {
        if (pkg) {
            // 优先使用包名精确启动
            app.launch(pkg);
            return true;
        } else if (name) {
            // 使用名称模糊匹配
            var launched = app.launchApp(name);
            if (launched) return true;
            
            // 常见应用名→包名映射
            var pkgMap = {
                "微信": "com.tencent.mm",
                "QQ": "com.tencent.mobileqq",
                "支付宝": "com.eg.android.AlipayGphone",
                "淘宝": "com.taobao.taobao",
                "设置": "com.android.settings",
                "相机": "com.sec.android.app.camera",
                "短信": "com.samsung.android.messaging",
                "电话": "com.samsung.android.dialer",
            };
            
            var knownPkg = pkgMap[name];
            if (knownPkg) {
                app.launch(knownPkg);
                return true;
            }
        }
        return false;
    } catch (e) {
        Template.Logger.error("Launch failed: " + e);
        return false;
    }
}

/**
 * 执行单个操作
 */
function executeAction(action, index) {
    Template.Logger.info("Action " + index + ": " + action.type + " -> " + (action.target || ""));
    
    switch (action.type) {
        case "click":
            return doClick(action.target);
        
        case "long_click":
            return doLongClick(action.target);
        
        case "input":
            return doInput(action.target, action.text);
        
        case "swipe":
            return doSwipe(action.direction);
        
        case "back":
            back();
            return { success: true, action: "back" };
        
        case "home":
            home();
            return { success: true, action: "home" };
        
        case "wait":
            sleep(action.duration || 1000);
            return { success: true, action: "wait_" + action.duration };
        
        default:
            return {
                success: false,
                error: "Unknown action type: " + action.type
            };
    }
}

function doClick(target) {
    var obj = Template.AccessibilityHelper.findWithRetry(target);
    if (obj && obj.clickable()) {
        obj.click();
        sleep(500);
        return { success: true, target: target };
    }
    return { success: false, error: "Click target not found: " + target };
}

function doLongClick(target) {
    var obj = Template.AccessibilityHelper.findWithRetry(target);
    if (obj && obj.longClickable()) {
        obj.longClick();
        sleep(500);
        return { success: true, target: target };
    }
    return { success: false, error: "Long-click target not found: " + target };
}

function doInput(target, text) {
    var obj = Template.AccessibilityHelper.findWithRetry(target);
    if (obj && obj.editable()) {
        obj.setText(text || "");
        sleep(300);
        return { success: true, target: target };
    }
    return { success: false, error: "Input target not found: " + target };
}

function doSwipe(direction) {
    var w = device.width;
    var h = device.height;
    var centerX = w / 2;
    var centerY = h / 2;
    
    switch (direction) {
        case "up":
            swipe(centerX, h * 0.7, centerX, h * 0.3, 500);
            break;
        case "down":
            swipe(centerX, h * 0.3, centerX, h * 0.7, 500);
            break;
        case "left":
            swipe(w * 0.8, centerY, w * 0.2, centerY, 500);
            break;
        case "right":
            swipe(w * 0.2, centerY, w * 0.8, centerY, 500);
            break;
    }
    sleep(500);
    return { success: true, direction: direction };
}

// ====================================================================
// 主入口
// ====================================================================
var params = Template.parseParams();
params.script_name = "app_launcher";
Template.run(execute);
