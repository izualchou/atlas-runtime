/**
 * ui_click_sequence.js — 通用 UI 点击序列脚本
 * 版本: v1.0
 * 
 * 用途: 在当前界面执行预定义的 UI 点击序列。
 *       支持按文本/ID/描述匹配控件，支持坐标点击。
 * 
 * 参数:
 *   steps: [
 *     {type:"click", target:"确定", wait:500},          // 文本匹配点击
 *     {type:"click_id", target:"com.android:id/ok"},   // ID 匹配点击
 *     {type:"click_xy", x:540, y:1200},                 // 坐标点击
 *     {type:"click_desc", target:"返回"},               // 描述匹配点击
 *     {type:"wait", duration:2000},                      // 等待
 *     {type:"input", target:"输入框", text:"hello"},    // 输入文本
 *   ]
 *   timeout_sec: 45
 * 
 * 依赖: atlas_ui_template.js、无障碍服务
 */

"use strict";

var Template = require("./atlas_ui_template.js");

function execute(params) {
    var steps = params.steps || [];
    
    if (steps.length === 0) {
        return {
            success: false,
            data: { error: "No steps defined in params" }
        };
    }
    
    Template.Logger.info("Executing " + steps.length + " UI steps");
    
    var completedSteps = [];
    var failedSteps = [];
    
    for (var i = 0; i < steps.length; i++) {
        var step = steps[i];
        Template.Logger.info("Step " + (i + 1) + "/" + steps.length + ": " + 
            step.type + " -> " + (step.target || "(" + step.x + "," + step.y + ")"));
        
        var result = executeStep(step);
        
        if (result.success) {
            completedSteps.push(i);
        } else {
            failedSteps.push({ index: i, step: step, error: result.error });
            
            if (step.required !== false) {
                // 关键步骤失败则终止
                return {
                    success: false,
                    data: {
                        error: "Step " + i + " failed: " + result.error,
                        step: step,
                        completed_before_failure: completedSteps.length,
                        failed_steps: failedSteps
                    }
                };
            }
        }
        
        // 步骤间等待
        sleep(step.wait || 500);
    }
    
    return {
        success: true,
        data: {
            total_steps: steps.length,
            completed: completedSteps.length,
            failed: failedSteps.length,
            completed_indices: completedSteps,
            failed_details: failedSteps
        }
    };
}

function executeStep(step) {
    try {
        switch (step.type) {
            case "click":
                return doClickByText(step.target);
            
            case "click_id":
                return doClickById(step.target);
            
            case "click_desc":
                return doClickByDesc(step.target);
            
            case "click_xy":
                return doClickByCoord(step.x, step.y);
            
            case "long_click":
                return doLongClick(step.target);
            
            case "long_click_xy":
                return doLongClickCoord(step.x, step.y);
            
            case "input":
                return doInput(step.target, step.text);
            
            case "wait":
                sleep(step.duration || 1000);
                return { success: true };
            
            case "scroll_up":
                scrollUp();
                sleep(500);
                return { success: true };
            
            case "scroll_down":
                scrollDown();
                sleep(500);
                return { success: true };
            
            case "back":
                back();
                sleep(500);
                return { success: true };
            
            default:
                return { success: false, error: "Unknown step type: " + step.type };
        }
    } catch (e) {
        return { success: false, error: String(e) };
    }
}

function doClickByText(target) {
    var obj = Template.AccessibilityHelper.findWithRetry(target);
    if (obj) {
        obj.click();
        return { success: true };
    }
    return { success: false, error: "Text not found: " + target };
}

function doClickById(target) {
    try {
        var obj = id(target).findOne(Template.CONFIG.STEP_TIMEOUT);
        if (obj) {
            obj.click();
            return { success: true };
        }
    } catch (e) {}
    return { success: false, error: "ID not found: " + target };
}

function doClickByDesc(target) {
    try {
        var obj = desc(target).findOne(Template.CONFIG.STEP_TIMEOUT);
        if (obj) {
            obj.click();
            return { success: true };
        }
    } catch (e) {}
    return { success: false, error: "Desc not found: " + target };
}

function doClickByCoord(x, y) {
    try {
        click(x, y);
        return { success: true };
    } catch (e) {
        return { success: false, error: "Coord click failed: " + e };
    }
}

function doLongClick(target) {
    var obj = Template.AccessibilityHelper.findWithRetry(target);
    if (obj) {
        obj.longClick();
        return { success: true };
    }
    return { success: false, error: "Long click target not found: " + target };
}

function doLongClickCoord(x, y) {
    try {
        longClick(x, y);
        return { success: true };
    } catch (e) {
        return { success: false, error: "Coord long click failed: " + e };
    }
}

function doInput(target, text) {
    var obj = Template.AccessibilityHelper.findWithRetry(target);
    if (obj && obj.editable()) {
        obj.setText(text || "");
        return { success: true };
    }
    return { success: false, error: "Input target not found or not editable: " + target };
}

// ====================================================================
// 主入口
// ====================================================================
var params = Template.parseParams();
params.script_name = "ui_click_sequence";
Template.run(execute);
