# Samsung One UI 8.5 + Termux 兼容性指南

## 1. 概述

Atlas Runtime v9.0 已针对 **三星 Galaxy 设备 (One UI 8.5 / Android 16) + Termux** 环境进行适配。本文档记录了已知的平台差异、限制和建议。

## 2. 平台特性矩阵

| 特性 | AOSP Android 16 | Samsung One UI 8.5 | Termux 中的状态 |
|------|-----------------|-------------------|-----------------|
| `svc wifi/data` | ✓ 完整支持 | ✓ 支持 | ✓ 通过 `/system/bin/svc` |
| `settings get/put` | ✓ 完整支持 | ✓ 支持 | ✓ 通过 `/system/bin/settings` |
| `service call` | ✓ AOSP 标准码 | ⚠️ 不同事务码 | ✓ 已自动适配 |
| `uiautomator dump` | ✓ 支持 | ✓ 支持 | ✓ 使用 Termux tmp |
| `/data/local/tmp` 写权限 | ✓ 可写 | ⚠️ 可能受限 | ✗ 使用 `$PREFIX/tmp` |
| `/sys/class/power_supply` | ✓ 可读 | ⚠️ SELinux 限制 | ⚠️ 部分文件可能不可读 |
| `termux-battery-status` | N/A | ✓ (via termux-api) | ✓ 最可靠的电池API |
| `termux-wake-lock` | N/A | ✓ (via termux-api) | ✓ 防止激进休眠 |
| WiFi 控制 (settings) | ✓ | ✓ | ✓ |
| 移动数据控制 (svc) | ✓ | ⚠️ 可能受限 | ⚠️ Samsung Knox 可能拦截 |
| 飞行模式 (settings) | ✓ | ✓ | ✓ 不会触发确认对话框 |
| SIM 切换 (service call) | ✓ | ⚠️ 事务码不同 | ⚠️ 需要正确的事务码 |
| 双 SIM | ✓ | ✓ | ✓ 自动检测 |
| Bixby 按键 | N/A | ✓ KEYCODE_BIXBY | ✓ |
| Knox 安全限制 | N/A | ⚠️ 部分进程操作受限 | ⚠️ killpg 可能被拦截 |

## 3. 已知限制

### 3.1 Samsung Knox 限制

Samsung One UI 8.5 集成 Knox 安全平台，以下操作可能受限：

- **进程组信号 (killpg)**：对系统进程和非自身进程组的 `os.killpg()` 可能被 Knox 拦截
  - 缓解：`SafeShellExecutor` 已添加 `proc.kill()` 回退策略

- **系统属性写入**：`setprop` 写入非持久化属性可能被限制
  - 影响：无 — Atlas 仅使用 `getprop` 读取

- **无障碍服务**：三星对无障碍服务的权限检查更严格
  - 影响：UI 自动化功能需要在"设置 → 辅助功能"中手动授权

### 3.2 SAMOLED 电池优化

三星的电池优化策略非常激进：
- 屏幕关闭后 5-10 分钟可能进入深度休眠
- **缓解方案**：已在 `service/run` 中使用 `termux-wake-lock` 获取 CPU wakelock
- **用户操作**：建议在系统设置中将 Termux 排除在电池优化之外

### 3.3 内存限制

| 级别 | 内存限制 | 触发动作 |
|------|---------|---------|
| 正常 | < 150MB | 正常运行 |
| 软限制 (告警) | ≥ 150MB | 日志告警，暂停非关键写入 |
| 硬限制 (拒绝) | ≥ 200MB | 拒绝新任务，触发 GC |

Samsung One UI 8.5 对后台进程的内存限制通常为 150-400MB，具体取决于设备 RAM 总量。

### 3.4 service call 事务码

Samsung One UI 8.5 的 `service call` 事务码与 AOSP 不同：

| 操作 | AOSP 码 | One UI 8.5 估计码 | 实际可用 |
|------|--------|-------------------|---------|
| WiFi 开关 | 28 | 55 | 待验证 |
| 移动数据 | 53 | 77 | 待验证 |
| 飞行模式 | 59 | 98 | 待验证 |
| SIM 切换 | 86 | 126 | 待验证 |

> **注意**：以上 One UI 8.5 事务码为基于 One UI 6/7 模式的估计值。
> 实际值可能因设备型号而异。如果失败，Atlas 会自动回退到 `settings` 命令。

### 3.5 uiautomator dump 性能

Samsung 设备的 `uiautomator dump` 在以下情况可能变慢：
- One UI 动画效果开启时
- 系统负载较高时
- 复杂 UI（如 Samsung 设置页面）

建议将 UI 自动化超时从默认的 10 秒增加到 15 秒（已在 `runtime.yaml` 中默认配置）。

## 4. 测试矩阵

| 测试类别 | 状态 | 备注 |
|---------|------|------|
| 平台检测 | ✓ | 自动识别 Samsung/One UI/Termux |
| 电池检测 | ✓ | termux-battery-status → dumpsys → /sys |
| 内存监控 | ✓ | /proc/meminfo 始终可读 |
| Shell 执行 | ✓ | PATH 自动包含 /system/bin |
| FIFO 通信 | ✓ | $PREFIX/tmp 始终可写 |
| HTTP 服务 | ✓ | 端口 8787（非特权端口） |
| SIM 切换 | ⚠️ | 依赖正确的事务码 |
| WiFi 控制 | ✓ | svc/cmd/settings 回退链 |
| 飞行模式 | ✓ | settings 路径不触发对话框 |
| UI 自动化 | ⚠️ | 可能需无障碍服务授权 |

## 5. 安装检查清单

在 Samsung One UI 8.5 设备上部署前，请验证：

- [ ] Termux 已从 F-Droid 安装（非 Play Store 版本）
- [ ] Termux:API APK 已从 F-Droid 安装
- [ ] Termux:Boot APK 已从 F-Droid 安装（可选，用于开机自启）
- [ ] `pkg update && pkg upgrade` 已执行
- [ ] `pkg install python git curl jq termux-api termux-services` 已完成
- [ ] 系统设置 → Termux → 电池 → "不受限制"
- [ ] 系统设置 → 辅助功能 → Termux → 已开启（如需 UI 自动化）
- [ ] 已运行 `termux-setup-storage`（如需访问存储）

## 6. 故障排除

### 服务无法启动

```bash
# 查看服务日志
tail -50 /data/data/com.termux/files/usr/var/log/atlas-runtime/current

# 手动运行（前台调试模式）
cd ~/atlas-runtime
python3 runtime/app.py --config config/runtime.yaml
```

### FIFO 不可用

```bash
# 检查 mkfifo 是否可用
which mkfifo
# 手动创建
rm -f $PREFIX/tmp/atlas_trigger.fifo
mkfifo $PREFIX/tmp/atlas_trigger.fifo
chmod 666 $PREFIX/tmp/atlas_trigger.fifo
```

### service call 命令失败

```bash
# 验证 Samsung 事务码
# 列出所有电话服务的事务码（格式：code: 函数名）
service list | grep phone

# 手动测试 WiFi 切换
svc wifi enable   # 优先用 svc 而不是 service call
```

### 电池状态不可用

```bash
# 测试电池状态获取路径（按优先级）
termux-battery-status          # 首选
dumpsys battery                # 回退
cat /sys/class/power_supply/battery/capacity  # 最后回退
```
