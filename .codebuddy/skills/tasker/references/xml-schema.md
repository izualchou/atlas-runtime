# Tasker XML Schema Reference

## Root Structure

```xml
<?xml version="1.0" encoding="UTF-8"?>
<TaskerData sr="" dvi="1" tv="6.6.20">
```

| Attribute | Value | Description |
|-----------|-------|-------------|
| `sr` | `""` | Always empty string on root |
| `dvi` | `"1"` | Data version |
| `tv` | `"6.6.20"` | Tasker version (latest) |

Root contains `<Project>`, `<Profile>`, `<Task>`, `<Scene>` elements.

## Import Formats

| File Extension | Contents | Purpose |
|---------------|----------|---------|
| `.prj.xml` | `<Project>` with embedded Profiles/Tasks/Scenes | Full project import |
| `.prf.xml` | Standalone `<Profile>` + referenced `<Task>` IDs | Profile-only import |
| `.tsk.xml` | Standalone `<Task>` | Task-only import |
| `.scn.xml` | Standalone `<Scene>` | Scene-only import |

## Project Definition (`<Project>`)

```xml
<Project sr="proj0" ve="2">
  <cdate>1700000000000</cdate>
  <name>Project Name</name>
  <pids>101,102</pids>       <!-- comma-separated profile IDs -->
  <tids>201,202</tids>       <!-- comma-separated task IDs -->
  <img sr="appicon" ve="2"/> <!-- optional: project icon -->
  <Share sr="Share">
    <b>false</b>
    <d>Description text</d>
    <g>Data,Files</g>
    <p>true</p>
    <t>tags</t>
  </Share>
</Project>
```

### Share Settings

| Element | Values | Description |
|---------|--------|-------------|
| `<b>` | `true` or `false` | `true` for standalone import, `false` for sub-project |
| `<d>` | text | Human-readable description |
| `<g>` | `Data`, `Files`, `Notifications`, `Accessibility` | Comma-separated permission groups |
| `<p>` | `true` or `false` | Allow external access |
| `<t>` | comma-separated text | Search tags |

## Profile Definition (`<Profile>`)

```xml
<Profile sr="prof101" ve="2">
  <cdate>1700000000000</cdate>
  <clp>true</clp>            <!-- limit repeats -->
  <edate>1700000000000</edate>
  <flags>40</flags>          <!-- 40 = recommended; 8 = legacy -->
  <id>101</id>
  <mid0>201</mid0>           <!-- enter task ID (required) -->
  <mid1>202</mid1>           <!-- exit task ID (optional) -->
  <nme>Profile Name</nme>    <!-- OMIT for anonymous profiles -->
</Profile>
```

### Context Types Inside Profile

#### Time (`<Time>`)

```xml
<Time sr="con0">
  <fh>8</fh>          <!-- from hour (0-23) -->
  <fm>0</fm>          <!-- from minute (0-59) -->
  <th>22</th>         <!-- to hour (0-23) -->
  <tm>0</tm>          <!-- to minute (0-59) -->
  <wd>MO,WE,FR</wd>   <!-- weekdays: MO,TU,WE,TH,FR,SA,SU or empty -->
  <day>15</day>       <!-- day of month (1-31) or empty -->
  <mth>1,6</mth>      <!-- month (1-12) or empty -->
</Time>
```

#### App (`<App>`)

```xml
<App sr="con0">
  <flags>0</flags>
  <label0>Chrome</label0>                          <!-- app label -->
  <package0>com.android.chrome</package0>          <!-- app package -->
  <label1>YouTube</label1>                         <!-- up to 5 apps -->
  <package1>com.google.android.youtube</package1>
</App>
```

#### Event (`<Event>`)

```xml
<Event sr="con0">
  <code>411</code>               <!-- event code -->
  <pri>0</pri>
  <Str sr="arg0" ve="3"/>        <!-- optional args per datadef.xml -->
  <Str sr="arg1" ve="3"/>
</Event>
```

**Common Event Codes:**

| Code | Event | Description |
|------|-------|-------------|
| 351 | BootCompleted | Device boot |
| 352 | DisplayOn | Screen turned on |
| 353 | DisplayOff | Screen turned off |
| 354 | HeadsetPlugged | Headset connected |
| 355 | PowerConnected | Charger connected |
| 356 | PowerDisconnected | Charger disconnected |
| 411 | DeviceBoot | Full device boot complete |
| 412 | DeviceShutdown | Device shutting down |
| 222 | Notification | Notification posted |
| 223 | NotificationRemoved | Notification removed |
| 247 | ButtonGadget | Button widget pressed |
| 265 | TickTrigger | Periodic timer tick |
| 310 | IntentReceived | Received broadcast intent |
| 599 | IntentReceived | Custom intent filter |

#### State (`<State>`)

```xml
<State sr="con0">
  <code>39</code>                    <!-- state code -->
  <Str sr="arg0" ve="3">SSID</Str>  <!-- args per datadef.xml -->
  <Str sr="arg1" ve="3"/>
</State>
```

**Common State Codes:**

| Code | State | Key Arg |
|------|-------|---------|
| 39 | WiFi Connected | arg0=SSID (blank=any), arg1=MAC (blank=any) |
| 40 | WiFi Near | arg0=SSID, arg1=MAC, arg2=min signal |
| 27 | Power | arg0=source (AC/USB/Wireless/Any) |
| 14 | Display State | arg0=On/Off |
| 165 | Variable Value | arg0=%varname, arg1=op code, arg2=value |
| 1 | Headset Plugged | arg0=type (Mic/No Mic/Any) |
| 10 | Battery Level | arg0=from%, arg1=to% |

#### Plugin (e.g., Termux:Tasker)

```xml
<Plugin sr="con0">
  <Bundle sr="arg0">
    <key>com.termux.tasker.ARGUMENTS</key>
    <value>script.py</value>
  </Bundle>
  <Str sr="arg1" ve="3">com.termux.tasker</Str>
  <Str sr="arg2" ve="3">com.termux.tasker.TaskerReceiver</Str>
  <Int sr="arg3" val="0"/>
</Plugin>
```

#### Compound Conditions (AND Logic)

Multiple `<Time>`, `<App>`, `<Event>`, `<State>` elements within one Profile form an AND relationship:

```xml
<Profile sr="prof102" ve="2">
  <!-- Both conditions must be true -->
  <Time sr="con0">...</Time>       <!-- during time window -->
  <State sr="con1">...</State>     <!-- AND WiFi connected -->
  <mid0>201</mid0>
</Profile>
```

## Task Definition (`<Task>`)

```xml
<Task sr="task201">
  <cdate>1700000000000</cdate>
  <edate>1700000000000</edate>
  <id>201</id>
  <pri>5</pri>                       <!-- priority 1-10 -->
  <rty>1</rty>                       <!-- run type: 1=first, 2=abort existing, 3=abort new -->
  <CollisionT>30000</CollisionT>     <!-- collision timeout ms -->
  <!-- Actions 0 through N -->
</Task>
```

### Action Structure

```xml
<Action sr="act0" ve="7">      <!-- ve always 7 for Action -->
  <code>547</code>              <!-- action code (from datadef.xml) -->
  <!-- Parameters per datadef.xml dataType -->
  <Str sr="arg0" ve="3">...</Str>   <!-- ve=3 for strings -->
  <Int sr="arg1" val="0"/>          <!-- no ve for ints -->
  <Bundle sr="argN">
    <key>key_name</key>
    <value>value</value>
  </Bundle>
</Action>
```

## Scene Definition (`<Scene>`)

```xml
<Scene sr="scenePanel">
  <cdate>1700000000000</cdate>
  <edate>1700000000000</edate>
  <heightLand>-1</heightLand>    <!-- landscape height (-1=auto) -->
  <heightPort>480</heightPort>   <!-- portrait height -->
  <nme>PanelName</nme>           <!-- scene name -->
  <widthLand>-1</widthLand>
  <widthPort>400</widthPort>
  <!-- Elements -->
  <PropertiesElement sr="props">...</PropertiesElement>
</Scene>
```

### Element Types

| Element | Purpose | Key Args |
|---------|---------|----------|
| `TextElement` | Text display | arg0=name, arg1=text, arg2=size, arg3=width%, arg4=textColor, arg5=bgColor |
| `ButtonElement` | Clickable button | Same as TextElement + `<clickTask>`, `<longClickTask>` |
| `EditTextElement` | Text input field | Same as TextElement + arg6=inputType |
| `ImageElement` | Image display | arg0=name, arg1=img source |
| `RectElement` | Rectangle/shape | arg0=name, arg1=width, arg2=fillColor, arg3=strokeColor |
| `OvalElement` | Oval/circle | Same as RectElement |
| `SliderElement` | Seekbar/slider | arg0=name, arg1=value, arg2=min, arg3=max |
| `SpinnerElement` | Dropdown selector | arg0=name, arg1=items (newline-separated) |

### Element Geometry (`<geom>`)

Format: `left,top,width,height,leftMargin,topMargin,rightMargin,bottomMargin`

- All values in display-independent pixels (dp)
- `-1` = fill/match parent (for width/height in RectElement)

### Element Interaction

- `<clickTask>`: Task ID to run on click
- `<longClickTask>`: Task ID to run on long press
- `<flags>`: 0=no special, 4=visible normally

### PropertiesElement

```xml
<PropertiesElement sr="props">
  <Int sr="arg0" val="1"/>        <!-- type: 1=overlay, 2=dialog, 3=activity -->
  <Int sr="arg1" val="0"/>        <!-- show title bar -->
  <Str sr="arg2" ve="3">#FFFFFFFF</Str>  <!-- background color -->
  <Int sr="arg3" val="0"/>        <!-- horizontal margin -->
  <Str sr="arg4" ve="3">Title</Str>      <!-- scene label -->
  <Str sr="arg5" ve="3"/>                <!-- property type -->
  <Img sr="arg6" ve="2"/>               <!-- icon -->
  <Str sr="arg7" ve="3"/>               <!-- display mode -->
</PropertiesElement>
```
