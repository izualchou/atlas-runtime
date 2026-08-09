---
name: tasker
description: Tasker Android automation expert. Use this skill when users ask about creating Tasker profiles, tasks, scenes, or automating Android actions. Also use when users mention AutoApps plugins (AutoInput, AutoNotification, AutoVoice, etc.), ADB commands, or Tasker JavaScript. This skill is especially suited for generating Tasker XML configuration files that can be directly imported into Tasker app.
---

# Tasker XML Configuration & Automation Expert

This skill covers two major domains: **(1) general Tasker automation consulting** and **(2) generating import-ready XML configuration files**.

## When to Use This Skill

Trigger this skill when the user mentions:
- Tasker profiles, tasks, scenes, or projects
- Generating Tasker XML files for import
- Android automation workflows with Tasker
- AutoApps plugins (AutoInput, AutoNotification, AutoVoice, etc.)
- Tasker ADB WiFi commands
- Tasker JavaScriptlets (JavaScript code embedded in Tasker)
- Tasker + Termux integration via Termux:Tasker plugin
- Tasker variable manipulation, event/state contexts, or scene UI design

## Skill Architecture

This skill uses progressive disclosure:
- **SKILL.md** (this file): Core XML generation workflow and procedural instructions
- **references/xml-schema.md**: Complete XML structure specification (root, Project, Profile, Task, Scene)
- **references/action-reference.md**: Action code tables, operator codes, arg type mappings
- **references/variable-reference.md**: Variable system (global/local/built-in/array), naming conventions
- **references/permissions.md**: Tasker permissions, ADB grant commands
- **references/plugins.md**: Termux:Tasker and other plugin Bundle key references
- **references/troubleshooting.md**: Common pitfalls, XML format traps, debugging guide
- **assets/**: 5 ready-to-import example XML files

## Core Workflow: Generating Tasker XML

When the user asks to generate Tasker XML configurations, follow this process:

### Step 1: Understand Requirements

Identify:
- What triggers the automation? (Profile: Time, App, Event, State, Plugin)
- What actions should execute? (Task: variables, HTTP, shell, JavaScript, notifications, etc.)
- Is a UI needed? (Scene: text, buttons, inputs)
- What permissions are required? (Data, Files, Notifications, Accessibility)
- Should it be a standalone import or part of an existing project?

### Step 2: Consult Reference Files

Before generating XML, load the relevant reference files:
- For XML structure and element definitions: `references/xml-schema.md`
- For action codes and parameter types: `references/action-reference.md`
- For variable names and types: `references/variable-reference.md`
- For permission declarations: `references/permissions.md`
- For plugin Bundle keys: `references/plugins.md`
- For XML gotchas: `references/troubleshooting.md`

### Step 3: Generate XML

Follow these rules strictly:

**Root Structure:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<TaskerData sr="" dvi="1" tv="6.6.20">
  <!-- Project(s) with Profiles, Tasks, Scenes -->
</TaskerData>
```

**Critical Rules:**
- Use `tv="6.6.20"` (latest version) on all elements
- Use `flags="40"` on Profile entries (not old `8`)
- Action `sr` attributes: `"act0"`, `"act1"`, `"act2"`... continuous from 0
- If conditions MUST use `<ConditionList>` format, not legacy flat format
- Parameter tags MUST match dataType from datadef.xml: Int→`<Int>`, Str→`<Str>`, Bundle→`<Bundle>`
- XML escape: `&`→`&amp;`, `<`→`&lt;`, `>`→`&gt;`, `"`→`&quot;`
- Anonymous tasks (linked via `<mid0>` in Profile) must NOT have `<nme>`

**Project `Share` settings:**
```xml
<Share sr="Share">
  <b>false</b>           <!-- true = standalone import, false = part of project -->
  <d>Description</d>
  <g>Data,Files</g>       <!-- comma-separated: Data,Files,Notifications,Accessibility -->
  <p>true</p>              <!-- allow external access -->
  <t>tags,comma,separated</t>
</Share>
```

**Profile Types:**

| Type | XML Element | Usage |
|------|------------|-------|
| Time | `<Time sr="con0">` | Clock-based triggers with hour/min/day/month constraints |
| App | `<App sr="con0">` | App foreground events, up to 5 packages |
| Event | `<Event sr="con0">` | System events (Boot, Notification, Intent, etc.) |
| State | `<State sr="con0">` | Persistent conditions (WiFi, Power, Variable Value) |
| Plugin | Plugin element | External plugin conditions (Termux, AutoApps) |

Each Profile links to tasks via `<mid0>` (enter task) and `<mid1>` (exit task).

### Step 4: Format Output

Always present XML in two forms:
1. **Code block** with complete XML for copy-paste
2. **File path suggestion**: `[name].prj.xml` → copy to `/sdcard/Tasker/configs/user/` (standalone) or `/sdcard/Tasker/projects/` (project)

Include a summary table showing the structure:
- Project name and tags
- Profile(s): trigger type and conditions
- Task(s): summary of actions
- Scene(s): layout description (if any)
- Required permissions

### Step 5: Provide Import Instructions

```
1. Copy the XML to /sdcard/Tasker/configs/user/[name].prj.xml
2. In Tasker: long-press "Profiles" tab → Import → select file
3. Or: Tasker → menu → Import Project
4. Grant any missing permissions when prompted
5. Test the Task individually before enabling the Profile
```

## Consulting Mode (Non-XML Questions)

When users ask general Tasker questions without requesting XML generation:

- Explain Tasker concepts: Profiles (contexts), Tasks (actions), Scenes (UI), Variables
- Describe available actions, contexts, and plugins
- Suggest automation approaches with reasoning
- Reference official Tasker docs when appropriate
- Mention ADB WiFi for advanced permissions

## Key Constraints

1. ALL XML MUST use `tv="6.6.20"` attribute
2. NEVER use legacy flat If format — always `<ConditionList>`
3. Anonymous tasks (profile-linked) must NOT have `<nme>`
4. Action `sr` must be sequential from 0
5. Parameter types must match datadef.xml definitions exactly
6. Always specify `<Share>` with appropriate permission groups
7. Termux:Tasker Bundle keys use `com.termux.tasker.` prefix
8. For standalone imports, set `<b>true</b>` in Share

## Example Assets

The `assets/` directory contains 5 complete, import-ready XML examples:
1. `system-monitor.prj.xml` — Hourly battery check + notification + logging
2. `wifi-manager.prf.xml` — WiFi connect/disconnect → mobile data toggle
3. `http-api-caller.prj.xml` — Weather API call → JSON parse → notification
4. `scene-panel.prj.xml` — Custom system status overlay with refresh/close
5. `termux-python.prj.xml` — Termux:Tasker → Python script execution
