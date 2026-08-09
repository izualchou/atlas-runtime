# Tasker XML Troubleshooting & Debugging

## Common XML Format Traps

### 1. If Condition Must Use ConditionList
**WRONG** (legacy format):
```xml
<Action sr="act0" ve="7">
  <code>37</code>
  <Str sr="arg0" ve="3">%BATT</Str>
  <Int sr="arg1" val="6"/>
  <Str sr="arg2" ve="3">20</Str>
</Action>
```
**CORRECT**:
```xml
<Action sr="act0" ve="7">
  <code>37</code>
  <ConditionList sr="if">
    <IfCondition sr="c0" ve="3">
      <lhs>%BATT</lhs><op>6</op><rhs>20</rhs>
    </IfCondition>
  </ConditionList>
</Action>
```

### 2. Parameter Type Must Match datadef.xml
Integer fields: `<Int sr="argN" val="0"/>` (no `ve` attribute)
String fields: `<Str sr="argN" ve="3">value</Str>` (always `ve="3"`)
Bundle fields: `<Bundle sr="argN">...<key>...</key><value>...</value>...</Bundle>`

### 3. XML Escaping
Always escape these characters in text content:
- `&` → `&amp;`
- `<` → `&lt;`
- `>` → `&gt;`
- `"` → `&quot;` (in attribute values)

### 4. Anonymous Tasks
Tasks linked via `<mid0>` in a Profile must NOT have a `<nme>` element:
```xml
<!-- CORRECT: anonymous task -->
<Task sr="task201">
  <cdate>...</cdate>
  <id>201</id>
  <!-- NO <nme> element -->
  ...
</Task>
```

### 5. Flags Value
Use `flags="40"` on `<Profile>` elements (recommended). Old `flags="8"` may cause issues in Tasker 6.x+.

### 6. Action sr Continuous Numbering
Action `sr` attributes must start from `"act0"` and increment continuously:
```xml
<Action sr="act0" ve="7">...</Action>  <!-- 0-based, no gaps -->
<Action sr="act1" ve="7">...</Action>
<Action sr="act2" ve="7">...</Action>
```

### 7. Version Attribute
All major elements (Project, Profile, Task, Scene) should carry `tv="6.6.20"`. Actions carry `ve="7"`.

### 8. Operator Code Usage
- Strings: op 0-5 (Eq, Neq, ~Regex, !~Regex, ~X, !~X)
- Numbers: op 6-11 (lt, gt, Eq, Neq, leq, geq)
- Existence: op 12-13 (Is Set, Is not Set)
- Never mix numeric ops for string comparisons or vice versa

### 9. Bundle Key Prefix
When using Termux:Tasker plugin, Bundle keys MUST use the full prefix:
- `com.termux.tasker.EXECUTABLE`
- `com.termux.tasker.ARGUMENTS`
- `com.termux.tasker.WORKDIR`
- `com.termux.tasker.TIMEOUT`

## Debugging Guide

### Enable Run Log
Tasker main screen → menu → More → Run Log
- Shows every action execution with timestamps
- Shows variable values at each step
- Filter by task/profile

### Use Flash Action for Debugging
Insert Flash actions (code=548) at key points:
```xml
<Action sr="actX" ve="7">
  <code>548</code>
  <Str sr="arg0" ve="3">DEBUG: BATT=%BATT, WIFI=%WIFI</Str>
  <Int sr="arg1" val="0"/>
</Action>
```

### Verify XML After Import
1. Import the XML into Tasker
2. Long-press the project/profile/task
3. Select Export → As XML to compare with the original
4. Look for differences that indicate parsing issues

### Test Tasks in Isolation
Before linking a Profile to a Task:
1. Import only the Task first
2. Run it manually (play button)
3. Verify all variables have expected values
4. Check the Run Log for any errors
5. Only then add the Profile trigger

### Common Runtime Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Profile never triggers | Battery optimization | Add Tasker to whitelist |
| Profile never triggers | Wrong context flags | Use `flags="40"` |
| File actions fail | Missing storage permission | Grant Files permission via ADB |
| HTTP request fails | No INTERNET permission | Check if Tasker has internet access |
| Scene elements overlap | Incorrect geom values | Verify left,top,width,height in dp |
| Variable not expanding | Wrong case | Global: uppercase, Local: lowercase |
| Plugin action fails | Missing plugin | Install the required plugin app |
| Shell command fails | No permission or wrong path | Use full paths, check with `which` |

### Profile Activation Check
Use the Tasker notification icon or the Profile status indicator:
- Green checkmark: Profile is active and conditions match
- Gray: Profile is enabled but conditions don't match
- No icon: Profile is disabled

## Quick Pre-Import Checklist

Before importing XML into Tasker:
- [ ] Root `<TaskerData>` has `tv="6.6.20"`
- [ ] All `<Int>` args have `val` attribute (not empty)
- [ ] All `<Str>` args have `ve="3"`
- [ ] If conditions use `<ConditionList>` not flat format
- [ ] Action `sr` numbering is sequential from 0
- [ ] Anonymous tasks (linked to Profile) have no `<nme>`
- [ ] XML special characters are escaped
- [ ] `<Share>` specifies correct permission groups
- [ ] Plugin Bundle keys use full package prefix
