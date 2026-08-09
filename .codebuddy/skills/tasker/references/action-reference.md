# Tasker Action Reference

## Action Code Quick Reference

Every action is identified by a numeric `code` attribute. Parameters follow the order defined in `datadef.xml`.

### Variable Actions

| Code | Action | Key Args |
|------|--------|----------|
| 547 | Variable Set | arg0=%name, arg1=value, arg2=0 (replace) / 1 (append) |
| 549 | Variable Add | arg0=%name, arg1=value, arg2=wrap |
| 588 | Variable Subtract | arg0=%name, arg1=value, arg2=wrap |
| 590 | Variable Randomize | arg0=%name, arg1=min, arg2=max |
| 598 | Variable Clear | arg0=%name |
| 548 | Variable Search Replace | arg0=%name, arg1=search, arg2=replace, arg3=replace |
| 584 | Variable Join | arg0=%name, arg1=joiner |
| 590 | Variable Split | arg0=%name, arg1=splitter |
| 592 | Variable Convert | arg0=%name, arg1=function (URL Encode, To Upper, etc.) |
| 596 | Array Push | arg0=%name, arg1=position (1-based), arg2=value |
| 595 | Array Pop | arg0=%name, arg1=position |
| 594 | Array Clear | arg0=%name |
| 597 | Array Process | arg0=%name, arg1=shuffle/sort/reverse |

### Flow Control

| Code | Action | Key Args |
|------|--------|----------|
| 37 | If (ConditionList) | Contains `<ConditionList>` with nested `<IfCondition>` |
| 38 | Else | No args |
| 39 | End If | No args |
| 130 | Goto | arg0=label, arg1=top/end/stay |
| 135 | Label | arg0=label name |
| 40 | Stop | arg0=with error (0=no, 1=yes), arg1=task (0=this, 1=all) |
| 30 | Wait | arg0=seconds, arg1=ms |
| 35 | Wait Until | Uses ConditionList |
| 53 | Anchor | arg0=name, arg1=background continue |

### Alert Actions

| Code | Action | Key Args |
|------|--------|----------|
| 523 | Notify | arg0=title, arg1=text, arg2=actions, arg5=icon |
| 524 | Notify Cancel | arg0=title/ID |
| 548 | Flash | arg0=text, arg1=long (0=short, 1=long) |
| 525 | Popup | arg0=title, arg1=text, arg2=timeout, arg3=show over keyguard |
| 526 | Menu | arg0=title, arg1=items (newline separated), arg2=timeout |
| 531 | Vibrate | arg0=time ms |
| 532 | Vibrate Pattern | arg0=pattern (comma separated durations) |
| 558 | Beep | arg0=frequency, arg1=duration, arg2=amplitude |

### App Actions

| Code | Action | Key Args |
|------|--------|----------|
| 20 | Launch App | arg0=package |
| 331 | Load App | arg0=package (fresh launch) |
| 330 | Go Home | arg0=page (0=default) |
| 18 | Kill App | arg0=package |
| 325 | Open Map | arg0=mode/point |
| 21 | Browse URL | arg0=URL |
| 424 | Keyboard | arg0=input type |

### Input Actions

| Code | Action | Key Args |
|------|--------|----------|
| 578 | Button | arg0=button (Back/Call/Camera/EndCall/Menu/Search/VolumeUp/VolumeDown) |
| 583 | Type | arg0=text, arg1=repeat, arg2=interval |
| 587 | Type WLAN | arg0=SSID |

### Task Actions

| Code | Action | Key Args |
|------|--------|----------|
| 131 | Perform Task | arg0=task name, arg1=priority, arg2=%par1, arg3=%par2, arg4=return var, arg7=local vars |
| 567 | Wait For Task | arg0=task names, arg1=timeout |
| 137 | Return | arg0=value |

### Net Actions

| Code | Action | Key Args |
|------|--------|----------|
| 116 | HTTP Request | arg0=Method, arg1=URL, arg2=Headers, arg3=Body/BodyFile, arg4=Filetype, arg5=OutputFile, arg6=Timeout, arg7=TrustAny |
| 63 | WiFi Set | arg0=On/Off/Toggle |
| 40 | WiFi | arg0=On/Off |
| 64 | Bluetooth | arg0=On/Off |
| 85 | Mobile Data | arg0=On/Off |
| 65 | Airplane Mode | arg0=On/Off |
| 117 | HTTP Auth | arg0=Method, arg1=URL, arg2=Username, arg3=Password |
| 50 | Get Location | arg0=source (GPS/Net/Any) |
| 34 | Compose Email | arg0=to, arg1=subject, arg2=body |
| 33 | Send SMS | arg0=number, arg1=message |
| 12 | Browse URL | arg0=URL |

### File Actions

| Code | Action | Key Args |
|------|--------|----------|
| 416 | Read File | arg0=path, arg1=%varname |
| 410 | Write File | arg0=path, arg1=text, arg2=append (0/1), arg3=newline |
| 414 | Delete File | arg0=path, arg1=recurse |
| 415 | List Files | arg0=dir, arg1=%varname |
| 417 | Copy File | arg0=from, arg1=to |
| 418 | Move | arg0=from, arg1=to |
| 420 | Open File | arg0=file, arg1=mime type |
| 43 | Test File | arg0=type (Exists/Size/Modified/Type/etc.), arg1=path or data, arg2=store result |

### Code Actions

| Code | Action | Key Args |
|------|--------|----------|
| 527 | JavaScriptlet | arg0=code, arg1=auto exit, arg2=timeout |
| 528 | JavaScript | arg0=file path |
| 123 | Run Shell | arg0=command, arg1=timeout, arg2=use root (0/1), arg3=store in var, arg5=store errors |
| 1342177284 | Termux:Tasker | Bundle arg0: EXECUTABLE, ARGUMENTS, WORKDIR, TIMEOUT |
| 394 | Music Play | arg0=file, arg1=start, arg2=audio stream |
| 391 | Say | arg0=text, arg1=engine, arg2=pitch, arg3=speed |
| 395 | Take Photo | arg0=camera, arg1=filename, arg2=resolution |
| 80 | Search | arg0=query |

### Tasker Actions

| Code | Action | Key Args |
|------|--------|----------|
| 14 | Set Tasker Pref | arg0=key, arg1=value |
| 43 | Test Tasker | arg0=type, arg1=store in |
| 423 | Profile Status | arg0=name, arg1=On/Off/Toggle |
| 44 | Profile Inactive | arg0=name (disable for N seconds) |
| 56 | Misc | arg0=type (clock, cpu, etc.) |
| 383 | Show Scene | arg0=name, arg1=as (0=overlay, 1=dialog, 2=activity), arg5=horizontal pos, arg6=vertical pos |
| 385 | Hide Scene | arg0=name |
| 387 | Destroy Scene | arg0=name |
| 386 | Scene Element | arg0=scene, arg1=element, arg2=element type, arg3=element action |

### System Actions

| Code | Action | Key Args |
|------|--------|----------|
| 384 | Set Wallpaper | arg0=image |
| 13 | Display Brightness | arg0=level (0-255) or Auto |
| 118 | Display Timeout | arg0=secs/hours/mins |
| 82 | Speakerphone | arg0=On/Off/Toggle |
| 208 | Ringer Volume | arg0=level |
| 304 | Media Volume | arg0=level |
| 210 | Silent Mode | arg0=On/Off/Vibrate |
| 211 | Notification Volume | arg0=level |
| 9 | Reboot | arg0=type (Normal/Recovery/Bootloader) |
| 211 | Shutdown | No args |

## ConditionList Format (If/Else If)

```xml
<Action sr="act0" ve="7">
  <code>37</code>                    <!-- If -->
  <ConditionList sr="if">
    <IfCondition sr="c0" ve="3">
      <lhs>%BATT</lhs>
      <op>6</op>                     <!-- operator code (see below) -->
      <rhs>20</rhs>
      <vt>Integer</vt>
    </IfCondition>
    <!-- Multiple conditions linked by bool0 -->
    <bool0>And</bool0>
    <IfCondition sr="c1" ve="3">
      <lhs>%WIFI</lhs>
      <op>2</op>
      <rhs>on</rhs>
    </IfCondition>
  </ConditionList>
</Action>
```

## Operator Codes (`<op>`)

| Code | Operator | Description |
|------|----------|-------------|
| 0 | Eq | Equals (strings) |
| 1 | Neq | Not equals (strings) |
| 2 | ~ | Regex match (strings) |
| 3 | !~ | Regex not match (strings) |
| 4 | ~X | Regex match XML |
| 5 | !~X | Regex not match XML |
| 6 | lt | Less than (numeric) |
| 7 | gt | Greater than (numeric) |
| 8 | Eq | Equals (numeric) |
| 9 | Neq | Not equals (numeric) |
| 10 | leq | Less than or equal (numeric) |
| 11 | geq | Greater than or equal (numeric) |
| 12 | Is Set | Variable exists |
| 13 | Is Not Set | Variable does not exist |

**Rule**: Use op 0-5 for string comparisons, op 6-11 for numeric comparisons, op 12-13 for existence checks.

## Condition Connectors (`<bool0>`)

| Value | Logic |
|-------|-------|
| `And` | All conditions must match |
| `Or` | Any condition can match |
| `true` | Same as And |

## Parameter Type Mapping

Parameters in `<Action>` correspond to dataType in `datadef.xml`:

| dataType in datadef.xml | XML Tag |
|-------------------------|---------|
| `Int` | `<Int sr="argN" val="VALUE"/>` |
| `Str` | `<Str sr="argN" ve="3">VALUE</Str>` |
| `Bundle` | `<Bundle sr="argN">...<key>...</key><value>...</value>...</Bundle>` |
| `Img` | `<Img sr="argN" ve="2"/>` |

**Always verify parameter types in `datadef.xml` before writing XML.** The arg order in the XML must match the order defined in datadef.xml.
