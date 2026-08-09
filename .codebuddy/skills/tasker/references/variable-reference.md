# Tasker Variable Reference

## Variable Types

### Global Variables
- Prefixed with at least one uppercase letter: `%Battery`, `%MyVar`
- Persist across reboots
- Available to all tasks
- Can be exported for external apps

### Local Variables
- All lowercase: `%my_var`, `%local_data`
- Exist only within the current task
- Destroyed when the task ends
- Use for temporary/transient data

### Built-in Variables
- Prefixed with `%` and all uppercase
- Read-only (some writable)
- Automatically updated by Tasker

### Array Variables
- Any variable can become an array: `%arr()` or `%arr(#)` for count
- Index from 1: `%arr(1)`, `%arr(2)`
- `%arr(#)` returns array length
- `%arr(<)` returns first element (pop)
- `%arr(>)` returns last element (pop)
- `%arr(*elems*)` returns sorted array

## Naming Conventions

| Scope | Convention | Example |
|-------|-----------|---------|
| Global | `%CamelCase` or `%UPPERCASE` | `%MyCounter`, `%API_KEY` |
| Local | `%lower_snake` | `%http_response`, `%temp_val` |
| Task Parameters | `%par1`, `%par2` | Sent via Perform Task |
| Return Value | `%rtval` or specified var | Set by "Return" action |

## Built-in Variables Quick Reference

### Battery & Power

| Variable | Description |
|----------|-------------|
| `%BATT` | Battery level (0-100) |
| `%CHG` | Charging (AC/USB/Wireless) or empty |
| `%TEMP` | Battery temperature (Celsius, x10) |
| `%PACTIVE` | Power connected (1=yes, 0=no) |

### Time & Date

| Variable | Description |
|----------|-------------|
| `%TIME` | Current time (HH.MM) |
| `%DATE` | Current date (MM-DD-YYYY) |
| `%TIMES` | Current time in seconds |
| `%TIMEMS` | Current time in milliseconds |
| `%DAYW` | Day of week (Sunday, Monday, etc.) |
| `%DAYM` | Day of month (1-31) |
| `%HOUR` | Current hour (0-23) |
| `%MINUTE` | Current minute |
| `%SECOND` | Current second |
| `%MONTH` | Current month (1-12) |
| `%YEAR` | Current year |

### Display

| Variable | Description |
|----------|-------------|
| `%SCREEN` | Screen state (on/off) |
| `%BRIGHT` | Screen brightness (0-255) |
| `%DTOUT` | Display timeout (seconds) |
| `%DISPLAYX` | Display width (pixels) |
| `%DISPLAYY` | Display height (pixels) |

### Device Info

| Variable | Description |
|----------|-------------|
| `%DEVID` | Device ID |
| `%DEVNAME` | Device name |
| `%SDK` | Android SDK version |
| `%ROOT` | Device rooted? (yes/no) |
| `%CPUGOV` | CPU governor |
| `%CPUREV` | CPU revision |
| `%CPUTEMP` | CPU temperature |
| `%MEMF` | Free memory (MB) |
| `%MEMORG` | Original free memory |

### Network

| Variable | Description |
|----------|-------------|
| `%WIFI` | WiFi status (on/off) |
| `%WIFII` | WiFi SSID (when connected) |
| `%WIFISSID` | WiFi SSID |
| `%WIFIBSSID` | WiFi BSSID (MAC) |
| `%DEVIP` | Device IP address |
| `%NTWKIP` | Network IP address |
| `%NTRANS` | Network data transferred |
| `%NRECV` | Network data received |
| `%CELLID` | Cell tower ID |
| `%CELLSIG` | Cell signal strength |
| `%SIMNUM` | SIM phone number |
| `%SIMSTATE` | SIM state |

### Audio

| Variable | Description |
|----------|-------------|
| `%VOLA` | Alarm volume |
| `%VOLC` | Call volume |
| `%VOLM` | Music/media volume |
| `%VOLN` | Notification volume |
| `%VOLR` | Ringer volume |
| `%VOLS` | System volume |
| `%SILENT` | Silent mode (on/off/vibrate) |
| `%INTERRUPT` | Do Not Disturb mode |
| `%MUTED` | Microphone muted |

### Location

| Variable | Description |
|----------|-------------|
| `%LOC` | Last GPS location (lat,lng) |
| `%LOCN` | Last network location (lat,lng) |
| `%LOCACC` | GPS accuracy (meters) |
| `%LOCSPD` | GPS speed (m/s) |
| `%LOCALT` | GPS altitude (meters) |
| `%LOCTMS` | Time of last GPS fix |

### Bluetooth

| Variable | Description |
|----------|-------------|
| `%BLUE` | Bluetooth status (on/off) |
| `%BTADDR` | Bluetooth address |
| `%BTNAME` | Bluetooth name |
| `%BTCON` | BT devices connected |
| `%BTCONN` | BT devices connected count |

### Application Context

| Variable | Description |
|----------|-------------|
| `%APP` | Current foreground app (package) |
| `%WIN` | Current window label |
| `%LAPP` | Last foreground app (package) |
| `%LWIN` | Last window label |

### Call & SMS

| Variable | Description |
|----------|-------------|
| `%CNUM` | Caller number (incoming) |
| `%CNAME` | Caller name (incoming) |
| `%CTIME` | Call duration |
| `%CSIG` | Call signal |
| `%SMSRF` | SMS sender number |
| `%SMSRB` | SMS message body |
| `%SMSRN` | SMS sender name |
| `%SMSRD` | SMS date |
| `%MMSRS` | MMS subject |

### Notification Context

| Variable | Description |
|----------|-------------|
| `%NTITLE` | Notification title |
| `%NTEXT` | Notification text |
| `%NSUB` | Notification subtext |
| `%NICON` | Notification icon (path) |
| `%NEVCAT` | Notification category |
| `%NTTAG` | Notification tag |
| `%NTID` | Notification ID |
| `%NTCNT` | Notification count |

## Variable Operations

### Pattern Matching
Use `%varname *matches* %search` in If conditions:
- Simple match: `%WIFII ~ *HomeWiFi*`
- Capture groups (with parentheses): Variable Search Replace → store in array

### Mathematical Operations
- Variable Add/Subtract: `%count + 1`
- Variable Set: `%result = %a + %b` (with "Do Maths" enabled, arg2=0)

### String Operations
- Concatenation: `%str = %part1 %part2`
- Variable Section: extract by character position
- Variable Split: `%csv(+,)` → splits by comma
- Variable Join: `%list(,+)` → joins with comma
