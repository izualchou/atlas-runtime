# Tasker Permissions Reference

## Permission Groups (for `<Share><g>`)

| Group | Covers | When Required |
|-------|--------|---------------|
| `Data` | App usage stats, package info, device admin | Launching/killing apps, reading package info |
| `Files` | Storage read/write, file access | Read File, Write File, List Files, Open File |
| `Notifications` | Notification listener, notification access | Notification event context, Notify action |
| `Accessibility` | Accessibility service | UI query, UI interaction, AutoInput |

## System Permissions (Grant via ADB)

```bash
# Grant WRITE_SECURE_SETTINGS (required for many system actions)
adb shell pm grant net.dinglisch.android.taskerm android.permission.WRITE_SECURE_SETTINGS

# Grant notification listener
adb shell cmd notification allow_listener net.dinglisch.android.taskerm

# Grant usage stats
adb shell pm grant net.dinglisch.android.taskerm android.permission.PACKAGE_USAGE_STATS

# Grant accessibility (auto-input)
adb shell pm grant net.dinglisch.android.taskerm android.permission.BIND_ACCESSIBILITY_SERVICE

# Grant DUMP permission
adb shell pm grant net.dinglisch.android.taskerm android.permission.DUMP

# Grant WRITE_GRANTED_URI_PERMISSIONS (Android 13+)
adb shell appops set net.dinglisch.android.taskerm SYSTEM_ALERT_WINDOW allow

# Grant draw over other apps
adb shell settings put global policy_control immersive.full=*
```

## Battery Optimization

**Critical**: Tasker MUST be excluded from battery optimization or profiles may not fire reliably.

```
Settings → Apps → Tasker → Battery → Battery optimization → Don't optimize
```

Or via ADB:
```bash
adb shell dumpsys deviceidle whitelist +net.dinglisch.android.taskerm
```

## AutoApps Plugin Permissions

Each AutoApps plugin typically requires:
- Accessibility service enabled
- Notification listener (for AutoNotification)
- Usage stats (for AutoInput UI interactions)
- Draw over other apps (for scenes and overlays)

Grant via ADB:
```bash
adb shell pm grant com.joaomgcd.autoinput android.permission.WRITE_SECURE_SETTINGS
adb shell pm grant com.joaomgcd.autonotification android.permission.BIND_NOTIFICATION_LISTENER_SERVICE
```

## Permission Checks in Tasks

Use the "Test Tasker" action (code=43) to verify permissions at runtime:
- arg0 = PermissionType
- arg1 = %result_var

## Manifest Permissions (in Tasker APK, not configurable)

Tasker requests these permissions at install:
- `INTERNET` — for HTTP Request and network operations
- `ACCESS_NETWORK_STATE` — WiFi/data state reading
- `ACCESS_WIFI_STATE` — WiFi state reading
- `CHANGE_WIFI_STATE` — WiFi toggle
- `BLUETOOTH` / `BLUETOOTH_ADMIN` — Bluetooth control
- `VIBRATE` — Vibration
- `RECEIVE_BOOT_COMPLETED` — Boot event context
- `READ_PHONE_STATE` — Call state
- `READ_SMS` / `SEND_SMS` — SMS operations
- `ACCESS_FINE_LOCATION` / `ACCESS_COARSE_LOCATION` — Location
- `FOREGROUND_SERVICE` — Keep running in background
- `WAKE_LOCK` — Prevent sleep during task execution
- `REQUEST_INSTALL_PACKAGES` — App installation
- `SYSTEM_ALERT_WINDOW` — Overlay scenes
- `POST_NOTIFICATIONS` — Notification posting (Android 13+)
- `READ_EXTERNAL_STORAGE` / `WRITE_EXTERNAL_STORAGE` — File access
- `MANAGE_EXTERNAL_STORAGE` — Full file access (Android 11+)
