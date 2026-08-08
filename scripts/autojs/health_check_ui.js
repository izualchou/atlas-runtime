/**
 * health_check_ui.js — 系统健康检查 UI 验证脚本
 * 版本: v1.0
 * 
 * 用途: 通过 UI 交互验证 Android 系统关键服务是否正常运行。
 *       检查项包括无障碍服务、存储权限、网络状态、电池信息。
 * 
 * 参数:
 *   checks: ["accessibility", "storage", "network", "battery"]
 *           — 可选，要执行的检查项，默认全部
 *   timeout_sec: 45
 * 
 * 依赖: atlas_ui_template.js、无障碍服务
 */

"use strict";

var Template = require("./atlas_ui_template.js");

function execute(params) {
    var checks = params.checks || ["accessibility", "storage", "network", "battery"];
    
    Template.Logger.info("Running health checks: " + checks.join(", "));
    
    var results = {};
    var allPassed = true;
    
    for (var i = 0; i < checks.length; i++) {
        var check = checks[i];
        Template.Logger.info("Check " + (i + 1) + "/" + checks.length + ": " + check);
        
        var result = runCheck(check);
        results[check] = result;
        
        if (!result.passed) {
            allPassed = false;
            Template.Logger.warn("Check FAILED: " + check + " — " + result.error);
        } else {
            Template.Logger.info("Check PASSED: " + check);
        }
    }
    
    return {
        success: allPassed,
        data: {
            checks_performed: checks.length,
            checks_passed: Object.values(results).filter(function(r) { return r.passed; }).length,
            checks_failed: Object.values(results).filter(function(r) { return !r.passed; }).length,
            results: results
        }
    };
}

function runCheck(check) {
    switch (check) {
        case "accessibility":
            return checkAccessibility();
        case "storage":
            return checkStorage();
        case "network":
            return checkNetwork();
        case "battery":
            return checkBattery();
        default:
            return { passed: false, error: "Unknown check: " + check };
    }
}

/**
 * 检查无障碍服务
 */
function checkAccessibility() {
    try {
        var service = auto();
        if (!service) {
            return { passed: false, error: "auto() returned null" };
        }
        return {
            passed: true,
            detail: "Accessibility service is active"
        };
    } catch (e) {
        return { passed: false, error: String(e) };
    }
}

/**
 * 检查存储权限
 */
function checkStorage() {
    try {
        var dir = Template.CONFIG.SHARED_DIR;
        files.ensureDir(dir);
        
        // 尝试写入测试文件
        var testFile = dir + "/.autojs_health_test";
        files.write(testFile, "health_check_" + Date.now());
        
        // 读取验证
        var content = files.read(testFile);
        if (!content) {
            return { passed: false, error: "Failed to read test file" };
        }
        
        // 清理
        files.remove(testFile);
        
        return {
            passed: true,
            detail: "Storage write/read successful at " + dir
        };
    } catch (e) {
        return { passed: false, error: "Storage check: " + String(e) };
    }
}

/**
 * 检查网络状态
 */
function checkNetwork() {
    try {
        // 检查网络连接
        var connected = device.isWifiEnabled() || device.isMobileDataEnabled();
        
        if (!connected) {
            return { passed: false, error: "No network connection active" };
        }
        
        // 检查 Atlas HTTP 服务是否可达
        try {
            var resp = http.get(Template.CONFIG.HTTP_CALLBACK.replace("/trigger", "/health"), {
                timeout: 3000
            });
            return {
                passed: true,
                detail: "Network OK, Atlas reachable: HTTP " + resp.statusCode
            };
        } catch (e) {
            // Atlas 不可达但网络正常
            return {
                passed: true,
                detail: "Network OK, Atlas service unreachable (HTTP: " + e + ")"
            };
        }
    } catch (e) {
        return { passed: false, error: "Network check: " + String(e) };
    }
}

/**
 * 检查电池信息
 */
function checkBattery() {
    try {
        var level = device.battery;
        
        if (level < 0) {
            return { passed: false, error: "Battery level unavailable" };
        }
        
        var status = "OK";
        if (level < 10) status = "CRITICAL";
        else if (level < 20) status = "LOW";
        
        return {
            passed: true,
            detail: "Battery: " + level + "% — " + status
        };
    } catch (e) {
        return { passed: false, error: "Battery check: " + String(e) };
    }
}

// ====================================================================
// 主入口
// ====================================================================
var params = Template.parseParams();
params.script_name = "health_check_ui";
Template.run(execute);
