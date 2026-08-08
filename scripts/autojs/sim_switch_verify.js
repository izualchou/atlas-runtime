/**
 * sim_switch_verify.js — SIM 卡切换后验证脚本
 * 版本: v1.0
 * 
 * 用途: SIM 切换完成后，验证运营商名称是否已变更。
 *       打开设置 → SIM 卡管理 → 检查运营商名称。
 * 
 * 参数:
 *   slot: 0 (卡1) 或 1 (卡2) — 要验证的 SIM 卡槽位
 *   expected_operator: "中国移动" 等 — 期望的运营商名称
 *   timeout_sec: 60 — 超时秒数
 * 
 * 依赖: atlas_ui_template.js、无障碍服务
 * 兼容: Samsung One UI 8.5、Android 8.0+
 */

"use strict";

// 加载模板
var Template = require("./atlas_ui_template.js");

/**
 * 执行 SIM 切换验证
 */
function execute(params) {
    var slot = params.slot || 0;
    var expected = params.expected_operator;
    
    Template.Logger.info("Verifying SIM slot " + slot + 
        (expected ? " (expected: " + expected + ")" : ""));
    
    // 步骤 1: 打开 SIM 卡管理
    if (!openSimSettings()) {
        return {
            success: false,
            data: {
                step: "open_settings",
                error: "Failed to open SIM settings"
            }
        };
    }
    
    // 步骤 2: 读取运营商名称
    var operator = readOperatorName(slot);
    
    if (!operator) {
        return {
            success: false,
            data: {
                step: "read_operator",
                error: "Failed to read operator name for slot " + slot
            }
        };
    }
    
    // 步骤 3: 验证运营商匹配
    var matched = !expected || operator.indexOf(expected) >= 0;
    
    if (!matched && expected) {
        Template.Logger.warn("Operator mismatch: got '" + operator + 
            "', expected '" + expected + "'");
    }
    
    // 步骤 4: 返回并上报
    Template.Logger.info("SIM slot " + slot + " operator: " + operator + 
        (matched ? " (MATCHED)" : " (MISMATCHED)"));
    
    return {
        success: true,
        data: {
            slot: slot,
            operator: operator,
            expected: expected,
            matched: matched
        }
    };
}

/**
 * 打开 SIM 卡管理设置
 */
function openSimSettings() {
    try {
        // 方法 1: 通过 adb shell 直接打开
        shell("am start -a android.settings.DUAL_SIM_SETTINGS", true);
        sleep(2000);
        return true;
    } catch (e1) {
        Template.Logger.warn("Method 1 failed: " + e1);
        try {
            // 方法 2: 打开网络设置
            shell("am start -a android.settings.NETWORK_OPERATOR_SETTINGS", true);
            sleep(2000);
            return true;
        } catch (e2) {
            // 方法 3: 手动打开设置
            try {
                app.startActivity({
                    action: "android.settings.SETTINGS"
                });
                sleep(1000);
                
                // 尝试点击 "连接" 或 "SIM 卡管理"
                var connBtn = Template.AccessibilityHelper.findWithRetry("连接", 3) ||
                              Template.AccessibilityHelper.findWithRetry("SIM", 3);
                if (connBtn) {
                    connBtn.click();
                    sleep(1500);
                }
                
                var simBtn = Template.AccessibilityHelper.findWithRetry("SIM 卡管理器", 3) ||
                             Template.AccessibilityHelper.findWithRetry("SIM 卡管理", 3);
                if (simBtn) {
                    simBtn.click();
                    sleep(1500);
                }
                return true;
            } catch (e3) {
                Template.Logger.error("All methods to open SIM settings failed");
                return false;
            }
        }
    }
}

/**
 * 读取指定 slot 的运营商名称
 */
function readOperatorName(slot) {
    // 三星 One UI 8.5 的 SIM 管理页面通常显示 "卡 1" 和 "卡 2"
    var slotLabel = (slot === 0) ? "卡 1" : "卡 2";
    
    // 方法 1: 从设置页面读取运营商文本
    try {
        // 查找包含运营商名称的控件
        // 通常在 "卡 X" 标签下方显示运营商名称
        var slotView = Template.AccessibilityHelper.findWithRetry(slotLabel, 3);
        if (slotView) {
            // 尝试获取父布局中运营商名称
            var parent = slotView.parent();
            if (parent) {
                var children = parent.children();
                for (var i = 0; i < children.length; i++) {
                    var child = children[i];
                    var childText = "";
                    if (child.text()) childText = child.text();
                    if (child.desc()) childText = childText || child.desc();
                    
                    // 常见的运营商名称模式
                    if (childText && 
                        (childText.indexOf("中国") >= 0 ||
                         childText.indexOf("CHN") >= 0 ||
                         childText.indexOf("CMCC") >= 0 ||
                         childText.indexOf("CUCC") >= 0 ||
                         childText.indexOf("CTCC") >= 0)) {
                        return childText;
                    }
                }
            }
        }
    } catch (e) {
        Template.Logger.warn("UI read method failed: " + e);
    }
    
    // 方法 2: 通过 getprop 获取
    try {
        var result = shell("getprop gsm.operator.alpha", true);
        if (result.code === 0 && result.result) {
            var operator = result.result.trim();
            if (operator) {
                // 双卡可能对应 gsm.operator.alpha 和 gsm.operator.alpha.1
                if (slot === 1) {
                    var result2 = shell("getprop gsm.operator.alpha.1", true);
                    if (result2.code === 0 && result2.result) {
                        operator = result2.result.trim();
                    }
                }
                return operator || "Unknown";
            }
        }
    } catch (e) {
        Template.Logger.warn("getprop method failed: " + e);
    }
    
    return null;
}

// ====================================================================
// 主入口
// ====================================================================
var params = Template.parseParams();
params.script_name = "sim_switch_verify";
Template.run(execute);
