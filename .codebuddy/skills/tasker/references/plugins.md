# Tasker Plugin Integration Reference

## Termux:Tasker Plugin

The Termux:Tasker plugin (code `1342177284`) allows Tasker to execute scripts in Termux.

### Bundle Configuration

```xml
<Action sr="actN" ve="7">
  <code>1342177284</code>
  <Bundle sr="arg0">
    <key>com.termux.tasker.EXECUTABLE</key>
    <value>/data/data/com.termux/files/usr/bin/python</value>
    <key>com.termux.tasker.ARGUMENTS</key>
    <value>script.py arg1 arg2</value>
    <key>com.termux.tasker.WORKDIR</key>
    <value>/data/data/com.termux/files/home</value>
    <key>com.termux.tasker.TIMEOUT</key>
    <value>30</value>
  </Bundle>
  <Str sr="arg1" ve="3">com.termux.tasker</Str>
  <Str sr="arg2" ve="3">com.termux.tasker.TaskerReceiver</Str>
  <Int sr="arg3" val="0"/>
</Action>
```

### Bundle Keys Reference

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `com.termux.tasker.EXECUTABLE` | String | Yes | Path to executable (python, bash, node, etc.) |
| `com.termux.tasker.ARGUMENTS` | String | Yes | Script path + arguments (space separated) |
| `com.termux.tasker.WORKDIR` | String | No | Working directory for script execution |
| `com.termux.tasker.TIMEOUT` | String | No | Execution timeout in seconds |
| `com.termux.tasker.INPUT` | String | No | Stdin input for the script |
| `com.termux.tasker.ENVIRONMENT` | String | No | Environment variables (KEY=VAL format) |

### Common Executable Paths

| Runtime | Path |
|---------|------|
| Python | `/data/data/com.termux/files/usr/bin/python` |
| Python 3 | `/data/data/com.termux/files/usr/bin/python3` |
| Bash | `/data/data/com.termux/files/usr/bin/bash` |
| Node.js | `/data/data/com.termux/files/usr/bin/node` |
| Perl | `/data/data/com.termux/files/usr/bin/perl` |

## AutoNotification Plugin

### Intercept Notifications (Event Context)

```xml
<Event sr="con0">
  <code>222</code>                        <!-- Notification event -->
  <Str sr="arg0" ve="3">AutoNotification</Str>
  <Str sr="arg1" ve="3"/>
</Event>
```

### Create Notification (Action)

```xml
<Action sr="actN" ve="7">
  <code>1342177284</code>
  <Bundle sr="arg0">
    <key>com.joaomgcd.autonotification.intent.action</key>
    <value>com.joaomgcd.autonotification.intent.action.NOTIFICATION</value>
  </Bundle>
  <Str sr="arg1" ve="3">com.joaomgcd.autonotification</Str>
  <Str sr="arg2" ve="3">com.joaomgcd.autonotification.activity.ActivityConfigNotification</Str>
  <Int sr="arg3" val="0"/>
</Action>
```

## AutoInput Plugin

### UI Query (Action)

```xml
<Action sr="actN" ve="7">
  <code>1342177284</code>
  <Bundle sr="arg0">
    <key>com.joaomgcd.autoinput.intent.action</key>
    <value>com.joaomgcd.autoinput.intent.action.QUERY</value>
  </Bundle>
  <Str sr="arg1" ve="3">com.joaomgcd.autoinput</Str>
  <Str sr="arg2" ve="3">com.joaomgcd.autoinput.activity.ActivityConfigQuery</Str>
  <Int sr="arg3" val="0"/>
</Action>
```

## AutoVoice Plugin

### Voice Recognition (Action)

```xml
<Action sr="actN" ve="7">
  <code>1342177284</code>
  <Bundle sr="arg0">
    <key>com.joaomgcd.autovoice.intent.action</key>
    <value>com.joaomgcd.autovoice.intent.action.RECOGNIZE</value>
  </Bundle>
  <Str sr="arg1" ve="3">com.joaomgcd.autovoice</Str>
  <Str sr="arg2" ve="3">com.joaomgcd.autovoice.activity.ActivityConfigRecognize</Str>
  <Int sr="arg3" val="0"/>
</Action>
```

## General Plugin Pattern

All plugins follow the same XML pattern:

```xml
<Action sr="actN" ve="7">
  <code>1342177284</code>                        <!-- Universal plugin code -->
  <Bundle sr="arg0">                              <!-- Plugin-specific params -->
    <key>intent.action.key</key>
    <value>intent.action.value</value>
  </Bundle>
  <Str sr="arg1" ve="3">plugin.package.name</Str>  <!-- Plugin package -->
  <Str sr="arg2" ve="3">plugin.activity.class</Str> <!-- Plugin activity class -->
  <Int sr="arg3" val="0"/>                         <!-- Launch mode -->
</Action>
```

For the EXACT Bundle keys required by each plugin, check the plugin's own export/share functionality or the `datadef.xml` for the specific plugin.

## ADB WiFi Plugin

### Send ADB Command

```xml
<Action sr="actN" ve="7">
  <code>123</code>                    <!-- Run Shell -->
  <Str sr="arg0" ve="3">settings put global airplane_mode_on 1; am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true</Str>
  <Int sr="arg1" val="0"/>           <!-- no timeout -->
  <Int sr="arg2" val="1"/>           <!-- use root -->
  <Int sr="arg3" val="0"/>
  <Str sr="arg4" ve="3"/>
  <Str sr="arg5" ve="3"/>
</Action>
```

Note: Root is needed for many ADB WiFi commands. Without root, use Termux as intermediate.
