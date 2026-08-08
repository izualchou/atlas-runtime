/**
 * battery_monitor.js — 电池状态监控 UI 脚本
 * 版本: v1.0
 * 
 * 用途: 监控电池状态变化并向 Atlas Runtime 上报。
 *       连续运行模式，定时（默认 60 秒）采集电池数据。
 *       当电量低于阈值时触发告警。
 * 
 * 参数:
 *   interval_sec: 60 — 采集间隔（秒）
 *   low_threshold: 20 — 低电量告警阈值（%）
 *   critical_threshold: 10 — 严重低电量阈值（%）
 *   single_shot: false — true 表示只采集一次后退出
 *   timeout_sec: 600 — 总运行超时（秒），0 表示无限运行
 * 
 * 依赖: atlas_ui_template.js
 */

"use strict";

var Template = require("./atlas_ui_template.js");

// 运行状态跟踪
var lastLevel = -1;
var lastStatus = "";
var reportCount = 0;

function execute(params) {
    var interval = (params.interval_sec || 60) * 1000;
    var lowThreshold = params.low_threshold || 20;
    var criticalThreshold = params.critical_threshold || 10;
    var singleShot = params.single_shot === true;
    var totalTimeout = (params.timeout_sec || 600) * 1000;
    
    Template.Logger.info("Battery monitor started (interval=" + 
        params.interval_sec + "s, low=" + lowThreshold + "%, critical=" + criticalThreshold + "%)");
    
    var startTime = Date.now();
    var readings = [];
    
    while (true) {
        // 超时检查
        if (totalTimeout > 0 && (Date.now() - startTime) >= totalTimeout) {
            Template.Logger.info("Monitor timeout reached");
            break;
        }
        
        // 采集电池数据
        var reading = collectBatteryData(lowThreshold, criticalThreshold);
        readings.push(reading);
        
        // 状态变化时上报
        if (reading.level !== lastLevel || reading.status !== lastStatus) {
            lastLevel = reading.level;
            lastStatus = reading.status;
            reportReading(reading, params);
        }
        
        reportCount++;
        
        // 单次采集模式
        if (singleShot) {
            break;
        }
        
        // 深度放电保护：电量过低时加大间隔
        var actualInterval = reading.level < criticalThreshold ? 
            Math.max(interval * 3, 300000) : // 至少5分钟
            interval;
        
        sleep(actualInterval);
    }
    
    return {
        success: true,
        data: {
            readings_count: readings.length,
            last_reading: readings[readings.length - 1],
            duration_sec: Math.round((Date.now() - startTime) / 1000),
            report_count: reportCount
        }
    };
}

/**
 * 采集当前电池数据
 */
function collectBatteryData(lowThreshold, criticalThreshold) {
    var level = -1;
    var status = "unknown";
    var temp = -1;
    var plugged = false;
    var health = "unknown";
    
    try {
        level = device.battery;
    } catch (e) {
        Template.Logger.warn("Failed to read battery level: " + e);
    }
    
    try {
        var charging = device.isCharging();
        plugged = !!charging;
    } catch (e) {}
    
    try {
        temp = device.batteryTemp;
    } catch (e) {}
    
    // 确定状态
    if (level < 0) {
        status = "unavailable";
    } else if (level <= criticalThreshold) {
        status = "critical";
    } else if (level <= lowThreshold) {
        status = "low";
    } else if (plugged) {
        status = "charging";
    } else {
        status = "normal";
    }
    
    return {
        level: level,
        status: status,
        temperature: temp,
        plugged: plugged,
        low_threshold: lowThreshold,
        critical_threshold: criticalThreshold,
        timestamp: Date.now()
    };
}

/**
 * 向 Atlas Runtime 上报电池读数
 */
function reportReading(reading, params) {
    var report = {
        action: "battery_update",
        params: {
            level: reading.level,
            status: reading.status,
            temperature: reading.temperature,
            plugged: reading.plugged,
            low_threshold: reading.low_threshold,
            critical_threshold: reading.critical_threshold,
            report_count: reportCount
        },
        correlation_id: "battery_monitor_" + Date.now()
    };
    
    // 通过 HTTP POST 上报
    try {
        var resp = http.postJson(params.http_callback, report, {
            timeout: 5000,
            headers: {
                "Content-Type": "application/json",
                "X-Trigger-Source": "autojs6_battery"
            }
        });
        
        Template.Logger.info("Battery reading reported: " + reading.level + "%" + 
            " (HTTP " + resp.statusCode + ")");
    } catch (e) {
        Template.Logger.warn("Battery report failed: " + e);
        
        // 文件兜底
        try {
            var fallbackFile = Template.CONFIG.SHARED_DIR + 
                "/battery_reading_" + Date.now() + ".json";
            files.ensureDir(Template.CONFIG.SHARED_DIR);
            files.write(fallbackFile, JSON.stringify(report, null, 2));
        } catch (e2) {
            Template.Logger.error("File fallback also failed: " + e2);
        }
    }
}

// ====================================================================
// 主入口
// ====================================================================
var params = Template.parseParams();
params.script_name = "battery_monitor";
Template.run(execute);
