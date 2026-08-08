/**
 * atlas_ui_template.js — Atlas Runtime AutoJS6 通用 UI 自动化模板
 * 版本: v1.0
 * 
 * 本脚本是所有 AutoJS6 专用脚本的基础框架，提供：
 * 1. 无障碍服务初始化与等待
 * 2. 参数解析 (通过 engines.myEngine().execArgv.scriptParams 接收)
 * 3. 结果上报 (HTTP POST 回调 + 本地文件兜底)
 * 4. 超时保护 (全局超时 + 单步超时)
 * 5. 错误处理与日志
 * 
 * 用法:
 *   在 AutoJS6 中通过 engines.execScriptFile() 或 Intent 启动。
 *   参数通过 scriptParams JSON 对象传递:
 *   {
 *     "params_file": "/sdcard/atlas_shared/autojs_params_xxxx.json",
 *     "http_callback": "http://127.0.0.1:8787/trigger",
 *     "timeout_sec": 60
 *   }
 * 
 * 依赖: AutoJS6 v6.5+、无障碍服务
 * 兼容: Android 8.0+
 */

"use strict";

// ====================================================================
// 全局配置
// ====================================================================
var CONFIG = {
    // Atlas HTTP 回调地址
    HTTP_CALLBACK: "http://127.0.0.1:8787/trigger",
    
    // 共享目录
    SHARED_DIR: "/sdcard/atlas_shared",
    
    // 默认超时 (秒)
    DEFAULT_TIMEOUT: 60,
    
    // 单步操作超时 (毫秒)
    STEP_TIMEOUT: 5000,
    
    // 控件查找重试次数
    MAX_RETRIES: 5,
    
    // 重试间隔 (毫秒)
    RETRY_INTERVAL: 1000,
    
    // 日志文件路径
    LOG_FILE: "/sdcard/atlas_shared/autojs.log",
};

// ====================================================================
// 日志工具
// ====================================================================
var Logger = {
    _logEntries: [],
    
    info: function(msg) {
        var entry = "[INFO] " + new Date().toISOString() + " " + msg;
        console.log(entry);
        this._logEntries.push(entry);
    },
    
    warn: function(msg) {
        var entry = "[WARN] " + new Date().toISOString() + " " + msg;
        console.warn(entry);
        this._logEntries.push(entry);
        toast("[Atlas] " + msg);
    },
    
    error: function(msg) {
        var entry = "[ERROR] " + new Date().toISOString() + " " + msg;
        console.error(entry);
        this._logEntries.push(entry);
        toast("[Atlas ERROR] " + msg);
    },
    
    flush: function() {
        try {
            var logDir = CONFIG.SHARED_DIR;
            files.ensureDir(logDir);
            files.append(CONFIG.LOG_FILE, this._logEntries.join("\n") + "\n");
        } catch (e) {
            console.error("Failed to flush log: " + e);
        }
        this._logEntries = [];
    }
};

// ====================================================================
// 参数解析
// ====================================================================
function parseParams() {
    var params = {};
    
    // 从引擎参数获取
    try {
        var engine = engines.myEngine();
        if (engine && engine.execArgv && engine.execArgv.scriptParams) {
            params = JSON.parse(engine.execArgv.scriptParams);
        }
    } catch (e) {
        Logger.warn("Failed to parse engine execArgv: " + e);
    }
    
    // 如果提供了 params_file，从文件读取
    if (params.params_file) {
        try {
            var fileContent = files.read(params.params_file);
            var fileParams = JSON.parse(fileContent);
            // 合并参数 (文件参数优先)
            for (var key in fileParams.params) {
                params[key] = fileParams.params[key];
            }
            Logger.info("Params loaded from file: " + params.params_file);
        } catch (e) {
            Logger.warn("Failed to read params file: " + params.params_file + " - " + e);
        }
    }
    
    // 设置默认值
    if (!params.http_callback) params.http_callback = CONFIG.HTTP_CALLBACK;
    if (!params.timeout_sec) params.timeout_sec = CONFIG.DEFAULT_TIMEOUT;
    if (!params.correlation_id) params.correlation_id = "autojs_" + Date.now();
    
    Logger.info("Parsed params: correlation_id=" + params.correlation_id);
    return params;
}

// ====================================================================
// 结果上报
// ====================================================================
var ResultReporter = {
    /**
     * 上报执行结果。
     * 优先 HTTP POST 回调 Atlas Runtime，失败时降级到本地文件。
     * 
     * @param {Object} params - 脚本参数
     * @param {boolean} success - 是否成功
     * @param {Object} data - 结果数据
     */
    report: function(params, success, data) {
        var result = {
            status: success ? "success" : "failed",
            script_name: params.script_name || "unknown",
            correlation_id: params.correlation_id,
            timestamp: Date.now(),
            data: data || {}
        };
        
        // 通道 1: HTTP POST
        var httpSuccess = this._httpReport(params.http_callback, result);
        
        // 通道 2: 本地文件兜底
        if (!httpSuccess) {
            this._fileReport(result, params.correlation_id);
        }
    },
    
    _httpReport: function(url, result) {
        try {
            var body = JSON.stringify(result);
            var response = http.postJson(url, result, {
                timeout: 5000,
                headers: {
                    "Content-Type": "application/json",
                    "X-Trigger-Source": "autojs6"
                }
            });
            
            if (response.statusCode >= 200 && response.statusCode < 300) {
                Logger.info("Result reported via HTTP: " + response.statusCode);
                return true;
            }
            
            Logger.warn("HTTP report returned " + response.statusCode);
            return false;
        } catch (e) {
            Logger.warn("HTTP report failed: " + e + " — will use file fallback");
            return false;
        }
    },
    
    _fileReport: function(result, correlationId) {
        try {
            var fallbackFile = CONFIG.SHARED_DIR + "/autojs_fallback_" + correlationId + ".json";
            files.ensureDir(CONFIG.SHARED_DIR);
            files.write(fallbackFile, JSON.stringify(result, null, 2));
            Logger.info("Result saved to file: " + fallbackFile);
        } catch (e) {
            Logger.error("File report failed: " + e);
        }
    }
};

// ====================================================================
// 无障碍服务
// ====================================================================
var AccessibilityHelper = {
    /**
     * 等待无障碍服务就绪。
     * 三星 One UI 8.5 可能需要额外等待 Knox 权限检查完成。
     */
    waitForService: function() {
        Logger.info("Waiting for accessibility service...");
        try {
            auto.waitFor();
            Logger.info("Accessibility service ready");
            return true;
        } catch (e) {
            Logger.error("Accessibility service not available: " + e);
            return false;
        }
    },
    
    /**
     * 智能查找控件，支持重试。
     * 
     * @param {string|RegExp} selector - 文本/ID/描述匹配
     * @param {number} maxRetries - 最大重试次数
     * @returns {Object|null} 找到的控件或 null
     */
    findWithRetry: function(selector, maxRetries) {
        maxRetries = maxRetries || CONFIG.MAX_RETRIES;
        for (var i = 0; i < maxRetries; i++) {
            try {
                var obj;
                
                // 尝试 text 匹配
                if (typeof selector === "string") {
                    obj = text(selector).findOne(CONFIG.STEP_TIMEOUT);
                    if (obj) return obj;
                }
                
                // 尝试 desc 匹配
                if (typeof selector === "string") {
                    obj = desc(selector).findOne(CONFIG.STEP_TIMEOUT);
                    if (obj) return obj;
                }
                
                // 尝试 id 匹配
                obj = id(selector).findOne(CONFIG.STEP_TIMEOUT);
                if (obj) return obj;
                
            } catch (e) {
                // 控件未找到，继续等待
            }
            
            if (i < maxRetries - 1) {
                sleep(CONFIG.RETRY_INTERVAL);
            }
        }
        return null;
    }
};

// ====================================================================
// 脚本主入口 (子类应覆盖 execute 函数)
// ====================================================================

/**
 * 全局超时定时器 ID
 */
var _timeoutTimer = null;

/**
 * 超时处理
 */
function _onTimeout(params) {
    Logger.error("Script timed out after " + params.timeout_sec + " seconds");
    ResultReporter.report(params, false, {
        error: "timeout",
        message: "Script execution timed out after " + params.timeout_sec + "s"
    });
    Logger.flush();
    exit();
}

/**
 * 主入口函数。
 * 子类应调用此函数，传入自己的执行逻辑。
 * 
 * @param {Function} executeFn - 执行函数 (params) => {success: bool, data: object}
 */
function run(executeFn) {
    var params = parseParams();
    
    // 设置超时
    var timeoutMs = params.timeout_sec * 1000;
    _timeoutTimer = setTimeout(function() { _onTimeout(params); }, timeoutMs);
    
    // 确保无障碍服务就绪
    if (!AccessibilityHelper.waitForService()) {
        clearTimeout(_timeoutTimer);
        ResultReporter.report(params, false, {
            error: "accessibility_unavailable",
            message: "Accessibility service not available"
        });
        Logger.flush();
        return;
    }
    
    // 执行子类逻辑
    Logger.info("Starting script execution: " + (params.script_name || "unknown"));
    var result;
    try {
        result = executeFn(params);
    } catch (e) {
        Logger.error("Script execution error: " + e);
        result = { success: false, data: { error: e.message || String(e) } };
    }
    
    // 清除超时
    clearTimeout(_timeoutTimer);
    
    // 上报结果
    ResultReporter.report(params, result.success, result.data);
    
    // 输出最终日志
    Logger.info("Script execution finished: " + (result.success ? "SUCCESS" : "FAILED"));
    Logger.flush();
}

// ====================================================================
// 导出 (供其他脚本引用)
// ====================================================================
module.exports = {
    CONFIG: CONFIG,
    Logger: Logger,
    parseParams: parseParams,
    ResultReporter: ResultReporter,
    AccessibilityHelper: AccessibilityHelper,
    run: run
};
