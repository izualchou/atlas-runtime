# Tasker 综合技能描述与 XML 配置指南

> **版本**: 适配 Tasker 5.15 / tv 6.6+
> **最后更新**: 2026-08-09
> **用途**: 提供可直接导入 Tasker 的 XML 配置文件模板与完整的结构参考

---

## 目录

1. [快速导入指南](#快速导入指南)
2. [XML 根结构规范](#xml-根结构规范)
3. [Project 项目定义与导出设置](#project-项目定义与导出设置)
4. [Profile 触发条件完整参考](#profile-触发条件完整参考)
5. [Task 执行动作完整参考](#task-执行动作完整参考)
6. [Scene 界面场景完整参考](#scene-界面场景完整参考)
7. [变量类型与命名规范](#变量类型与命名规范)
8. [权限声明](#权限声明)
9. [可直接导入的完整配置范例](#可直接导入的完整配置范例)

---

## 快速导入指南

将 XML 内容保存为 `.tsk.xml`（单任务）、`.prf.xml`（单Profile）或 `.prj.xml`（完整项目）文件，放入 Android 设备的 `/sdcard/Tasker/` 目录后，在 Tasker 中选择「导入」。**注意**：Tasker 5.15 要求 XML 根元素为 `<TaskerData>`，且 `dvi` 和 `tv` 属性与导出版本匹配。

---

## XML 根结构规范

### `<TaskerData>` 根元素

所有可导入的 Tasker XML 必须以此元素为根。两类基本信息：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!--
  字段说明:
    sr:  序列化引用（通常为空 "" 或 "proj0", "taskXX", "profXX"）
    dvi: 设备版本号（Device Version Identifier）
    tv:  Tasker 应用程序版本号（Target Version），对应 datadef.xml 的版本
        常见值: 6.3.13（旧版）, 6.6.20（当前最新）
-->
<TaskerData sr="" dvi="1" tv="6.6.20">
  <!-- 内容区域 -->
</TaskerData>
```

**关键属性说明:**

| 属性 | 用途 | 示例值 | 说明 |
|:---|:---|:---|:---|
| `sr` | 序列化引用 | `""` 或 `"proj0"` | 根级通常为空 |
| `dvi` | 设备版本 | `"1"` | 任务数据格式版本 |
| `tv` | Tasker 版本 | `"6.6.20"` | 导出时的 Tasker 应用版本 |
| `ve` | 变量编码版本 | `"2"`, `"3"` | 数据元素的编码格式（`ve="3"` 表示最新格式） |

### 子元素总览

`<TaskerData>` 可包含以下任意顺序的子元素：

| 元素 | 用途 | 独立导入格式 |
|:---|:---|:---|
| `<Project>` | 项目定义（可含导出设置） | `.prj.xml` |
| `<Profile>` | 配置文件（触发条件） | `.prf.xml` |
| `<Task>` | 任务（执行动作序列） | `.tsk.xml` |
| `<Scene>` | 场景（自定义 UI 界面） | 包含在 `.prj.xml` 中 |
| `<dmetric>` | 显示规格 | `1080.0,2400.0` |

---

## Project 项目定义与导出设置

Project 是 Tasker 中的组织单元，绑定 Profile、Task 和 Scene，并提供导出源共享配置。

```xml
<!--
  项目定义完整模板
  关键属性:
    sr="proj0"   : 项目序列化标识
    pids         : 逗号分隔的 Profile ID 列表
    tids         : 逗号分隔的 Task ID 列表  
    scenes       : 逗号分隔的 Scene 名称列表
    <Share>      : 导出分享设置（可选但推荐）
      <b>false   : 是否需要密码（false = 不需要）
      <d>        : 项目描述文字
      <g>        : 分享权限组（Data=数据, Files=文件访问）
      <p>true    : 是否允许公开分享
      <t>        : 标签（逗号分隔）
    <Img>        : 项目图标（可选，使用应用图标）
-->
<Project sr="proj0" ve="2">
  <cdate>1700000000000</cdate>
  <name>自动化项目名称</name>
  <pids>100,101,102</pids>
  <tids>200,201,202</tids>
  <scenes>MainScene,SettingsScene</scenes>
  <Share sr="Share">
    <b>false</b>
    <d>
      项目描述说明文字。
      支持多行格式。
    </d>
    <g>Data,Files</g>
    <p>true</p>
    <t>automation,utility</t>
  </Share>
  <Img sr="icon" ve="2">
    <cls>com.example.app.MainActivity</cls>
    <pkg>com.example.app</pkg>
  </Img>
</Project>
```

**导出权限组 `<g>` 详解:**

| 权限组值 | 所需权限 | 说明 |
|:---|:---|:---|
| `Data` | 数据访问 | 读写 Tasker 内部数据文件 |
| `Files` | 文件系统 | 访问外部存储文件 |
| `Notifications` | 通知 | 读取和创建通知 |
| `Accessibility` | 无障碍 | 使用无障碍服务 |

---

## Profile 触发条件完整参考

### Profile 通用结构

Profile 包含触发条件上下文（可复合）和一个或多个关联的 Task（通过 `<midN>` 引用 Task ID）。Profile 关联的 Task 必须是**匿名**的（不包含 `<nme>` 标签）。

```xml
<!--
  Profile 通用模板
  结构说明:
    <mid0>       : 入口 Task ID（必需）
    <mid1>       : 出口 Task ID（可选—条件结束时执行）
    <flags>      : flags 值（推荐 40）
    <cdate>      : 创建时间戳（毫秒）
    <edate>      : 最后编辑时间戳（毫秒）
    <clp>        : 是否启用（true/false）
    <nme>        : Profile 名称
    <limit>      : 是否启用冷却时间（true/false）
-->
<Profile sr="prof101" ve="2">
  <cdate>1700000000000</cdate>
  <clp>true</clp>
  <edate>1700000000000</edate>
  <flags>40</flags>
  <id>101</id>
  <limit>true</limit>
  <mid0>201</mid0>
  <nme>我的配置文件名称</nme>
  <!-- 触发条件放在此处 -->
</Profile>
```

**flags 值说明:**

| 值 | 含义 |
|:---|:---|
| `8` | 旧版默认值（仍兼容） |
| `40` | **推荐**：Tasker 5.x+ 推荐配置值 |

### 1. 时间触发 — `<Time>`

```xml
<!--
  时间上下文: 在指定时间区间内触发
  子元素:
    <fh>: 起始小时（0-23 或 变量）
    <fm>: 起始分钟（0-59）
    <th>: 结束小时（0-23 或 变量）
    <tm>: 结束分钟（0-59）
  可选:
    <wday>: 星期几（逗号分隔: 1=周日, 2=周一 ... 7=周六）
    <day>:  月中日号（逗号分隔: 1-31）
    <month>: 月份（逗号分隔: 1-12）
-->
<Time sr="con0">
  <fh>8</fh>
  <fm>0</fm>
  <th>22</th>
  <tm>0</tm>
  <wday>2,3,4,5,6</wday>
</Time>
```

### 2. 应用上下文 — `<App>`

```xml
<!--
  应用上下文: 当前台应用匹配时触发
  cls/ClsN: Activity 类名（多个用 Cls0, Cls1...）
  pkg/PkgN: 包名（多个用 Pkg0, Pkg1...）
  label/LabelN: 应用标签（多个用 label0, label1...）
  
  限制: cls/label/pgk 不要混用，应使用 indexed 形式（ClsN/PkgN/LabelN）以支持多应用
-->
<App sr="con0" ve="2">
  <flags>2</flags>
  <label0>Chrome</label0>
  <pkg0>com.android.chrome</pkg0>
</App>
```

### 3. 事件触发 — `<Event>`

```xml
<!--
  事件上下文: 响应一次性的系统事件
  参数传递:
    <code>: 事件代码（参看 datadef.xml）
    <Int sr="argN" val="VALUE"/>: 整型参数
    <Str sr="argN" ve="3">VALUE</Str>: 字符串参数
    
  示例: 设备启动事件 (code=411)
-->
<Event sr="con0" ve="2">
  <code>411</code>
  <pri>0</pri>
</Event>
```

**常用事件代码速查:**

| 代码 | 事件名称 | 说明 |
|:---|:---|:---|
| `411` | Device Boot | 设备启动完成 |
| `222` | Notification | 通知到达 |
| `599` | Intent Received | 收到 Intent |
| `2091` | Command | 收到命令（`=:=` 分隔） |
| `402` | Display Off | 屏幕关闭 |
| `401` | Display On | 屏幕开启 |
| `403` | Display Unlocked | 屏幕解锁 |

### 4. 状态触发 — `<State>`

状态持续期间保持激活，可同时有入口和出口 Task。

```xml
<!--
  WiFi 连接状态 (code=39)
  arg0: SSID 名称（支持模式匹配），"" 匹配任何
  arg1: MAC 地址，"" 匹配任何
  arg2: 信号强度最小值
-->
<State sr="con0" ve="2">
  <code>39</code>
  <Str sr="arg0" ve="3">HomeWiFi_*</Str>
  <Str sr="arg1" ve="3"/>
  <Int sr="arg2" val="0"/>
</State>
```

### 5. 复合条件 — 多上下文

多个上下文并排时，逻辑为 AND（都满足才触发）。

```xml
<Profile sr="prof105" ve="2">
  <cdate>1700000000000</cdate>
  <clp>true</clp>
  <edate>1700000000000</edate>
  <flags>40</flags>
  <id>105</id>
  <mid0>205</mid0>
  <nme>WiFi + 夜间</nme>
  <Time sr="con0">
    <fh>22</fh><fm>30</fm><th>6</th><tm>30</tm>
  </Time>
  <State sr="con1" ve="2">
    <code>39</code>
    <Str sr="arg0" ve="3">HomeWiFi</Str>
    <Str sr="arg1" ve="3"/>
    <Int sr="arg2" val="0"/>
  </State>
</Profile>
```

### 6. 变量值状态 — Variable Value `<State code="165">`

```xml
<!--
  Variable Value 状态: 当变量满足条件时激活
  使用 ConditionList 格式（与 If 动作相同）
  op 代码: 12=Set, 13=Not Set, 0=Equals String, 2=Matches Simple Pattern
-->
<State sr="con0" ve="2">
  <code>165</code>
  <ConditionList sr="if">
    <Condition sr="c0" ve="3">
      <lhs>%AtHome</lhs>
      <op>8</op>
      <rhs>1</rhs>
    </Condition>
  </ConditionList>
</State>
```

### 7. Plugin 事件（如 Termux:Tasker）

```xml
<!--
  Termux:Tasker 插件事件 (code=1342177284)
  使用 Bundle 传递键值对
  Bundle key 约定: com.termux.tasker. 前缀
-->
<plugin.EB sr="con0" ve="2">
  <code>1342177284</code>
  <Bundle sr="arg0">
    <key>com.termux.tasker.ARGUMENTS</key>
    <value>script.sh --param1 value1</value>
    <key>com.termux.tasker.EXECUTABLE</key>
    <value>/data/data/com.termux/files/usr/bin/bash</value>
    <key>com.termux.tasker.TIMEOUT</key>
    <value>30</value>
    <key>com.termux.tasker.WORKDIR</key>
    <value>/data/data/com.termux/files/home/project</value>
  </Bundle>
  <Str sr="arg1" ve="3">com.termux.tasker</Str>
  <Str sr="arg2" ve="3">com.termux.tasker.TaskerReceiver</Str>
  <Int sr="arg3" val="0"/>
</plugin.EB>
```

---

## Task 执行动作完整参考

### Task 通用结构

```xml
<!--
  Task 模板
  关键属性:
    <nme>   : 任务名称（匿名则省略，仅独立 .tsk.xml 或命名任务使用）
    <id>    : 唯一数字 ID
    <pri>   : 优先级（5=默认, 10=高, 1=低）
    <rty>   : 冲突处理策略
              0 = 中断当前任务
              1 = 并行运行（新实例）
              2 = 排队等待
              3 = 中止新任务
    <limit> : 冷却时间启用（true/false）
    <CollisionT>: 任务冲突超时时间（毫秒）
-->
<Task sr="task201">
  <cdate>1700000000000</cdate>
  <edate>1700000000000</edate>
  <id>201</id>
  <pri>5</pri>
  <rty>1</rty>
  <nme>我的任务名称</nme>
  <limit>false</limit>
  <CollisionT>30000</CollisionT>
  
  <!-- 动作序列 -->
</Task>
```

**优先级与冲突处理:**

| 参数 | 值 | 说明 |
|:---|:---|:---|
| `pri` | `1`-`10` | 数字越大优先级越高 |
| `rty` | `0` | 中断当前同名任务 |
| `rty` | `1` | 并行运行新实例 |
| `rty` | `2` | 排队等待 |
| `rty` | `3` | 中止新任务 |

### 动作序列 — Action 通用格式

```xml
<!--
  每个 Action 包含:
    sr="actN" : 动作序列标识（act0, act1, act2... 必须连续）
    ve="7"    : 编码版本号（7 = 当前最新）
    <code>    : 动作代码（参看 datadef.xml）
    <Int>     : 整数类型参数（sr="argN"）
    <Str>     : 字符串类型参数（sr="argN", ve="3"）
    <Bundle>  : Bundle 类型参数（插件等复杂参数）
    <ConditionList> : 条件列表（If 动作专用）
    
  关键规则:
  - arg0, arg1, arg2... 必须严格按顺序对应 datadef.xml 的定义
  - 参数类型必须匹配 dataType（Int→<Int>, Str→<Str>, Bundle→<Bundle>）
  - XML 特殊字符需转义: &→&amp;  <→&lt;  >→&gt;  "→&quot;  '→&apos;
-->
<Action sr="act0" ve="7">
  <code>547</code>
  <Str sr="arg0" ve="3">%my_variable</Str>
  <Str sr="arg1" ve="3">Hello World</Str>
  <Int sr="arg2" val="0"/>
  <Int sr="arg3" val="0"/>
</Action>
```

### 常用动作示例（按类别）

#### 变量操作

```xml
<!--
  Variable Set (code=547)
  arg0: 变量名
  arg1: 值
  arg2: 替换（0=完整替换, 1=若未设置则替换）
  arg3: 四舍五入（0=不, 1=取整到 arg4 位）
  arg4: 小数位数
  arg5: 作为数学计算（0=文本, 1=计算）
  arg6: 结构输出（0=纯文本, 1=JSON网格化）
-->
<Action sr="act0" ve="7">
  <code>547</code>
  <Str sr="arg0" ve="3">%counter</Str>
  <Str sr="arg1" ve="3">%counter + 1</Str>
  <Int sr="arg2" val="0"/>
  <Int sr="arg3" val="1"/>
  <Int sr="arg4" val="0"/>
  <Int sr="arg5" val="1"/>
  <Int sr="arg6" val="0"/>
</Action>

<!--
  Array Push (code=592)
  arg0: 变量名
  arg1: 值
  arg2: 位置（1=头部, 999=尾部）
  arg3: 填充空格（0=不填充）
-->
<Action sr="act1" ve="7">
  <code>592</code>
  <Str sr="arg0" ve="3">%my_array</Str>
  <Str sr="arg1" ve="3">new_value</Str>
  <Int sr="arg2" val="999"/>
  <Int sr="arg3" val="0"/>
</Action>
```

#### 流程控制

```xml
<!--
  If (code=37) — 条件判断
  使用 ConditionList 格式（Tasker 5.x+ 标准格式）
  
  条件运算符代码（op 标签）:
    0  = Equals String (eq)
    1  = Not Equals String (ne)
    2  = Matches Simple Pattern (~)
    3  = Doesn't Match Simple Pattern (!~)
    4  = Matches Regex (~R)
    5  = Doesn't Match Regex (!~R)
    6  = Less Than (<)        严格数值
    7  = Greater Than (>)     严格数值
    8  = Equals (=)           严格数值
    9  = Not Equals (!=)      严格数值
    10 = Even                 严格数值
    11 = Odd                  严格数值
    12 = Is Set               变量存在性
    13 = Is Not Set           变量存在性
    
  多条件组合:
    bool0="And" / "Or" / "Xor" (n个条件需要n-1个bool)
    优先级: And2 > Or2 > Xor2 > And > Or > Xor
  
  重要规则:
    op 6-11 仅用于数值比较！
    op 12-13 省略 <rhs> 标签
    op 0-5 需要 <rhs>
-->
<Action sr="act2" ve="7">
  <code>37</code>
  <ConditionList sr="if">
    <Condition sr="c0" ve="3">
      <lhs>%result</lhs>
      <op>12</op>
    </Condition>
  </ConditionList>
</Action>

<!-- End If (code=38) -->
<Action sr="act3" ve="7">
  <code>38</code>
</Action>

<!-- Else (code=39) -->
<Action sr="act4" ve="7">
  <code>39</code>
</Action>

<!-- End If (code=38) — 必须闭合 -->
<Action sr="act5" ve="7">
  <code>38</code>
</Action>
```

**多条件组合示例：**

```xml
<Action sr="act2" ve="7">
  <code>37</code>
  <ConditionList sr="if">
    <Condition sr="c0" ve="3">
      <lhs>%battery_level</lhs>
      <op>6</op>
      <rhs>20</rhs>
    </Condition>
    <bool0>And</bool0>
    <Condition sr="c1" ve="3">
      <lhs>%is_charging</lhs>
      <op>8</op>
      <rhs>1</rhs>
    </Condition>
  </ConditionList>
</Action>
```

#### 网络操作

```xml
<!--
  HTTP Request (code=279)
  arg0: 服务器URL
  arg1: 方法（GET/POST/PUT/DELETE/HEAD/OPTIONS/PATCH）
  arg2: 请求体
  arg3: 保存结果到变量
  arg4: 文件保存路径（留空 = 不保存到文件）
  arg5: 超时（秒）
  arg6: 内容类型（自动/文本/JSON等，留空 = 自动检测）
  arg7: 信任任何证书（true/false）
  arg8: 跟随重定向（true/false）
-->
<Action sr="act3" ve="7">
  <code>279</code>
  <Str sr="arg0" ve="3">https://api.example.com/data</Str>
  <Str sr="arg1" ve="3">POST</Str>
  <Str sr="arg2" ve="3">{"key":"value"}</Str>
  <Str sr="arg3" ve="3">%http_response</Str>
  <Str sr="arg4" ve="3"/>
  <Int sr="arg5" val="15"/>
  <Str sr="arg6" ve="3"/>
  <Int sr="arg7" val="0"/>
  <Int sr="arg8" val="1"/>
</Action>
```

#### 文件操作

```xml
<!--
  Write File (code=410)
  arg0: 文件路径
  arg1: 内容
  arg2: 追加（true=追加, false=覆盖）
  arg3: 添加换行（true=添加）
-->
<Action sr="act4" ve="7">
  <code>410</code>
  <Str sr="arg0" ve="3">/sdcard/Tasker/output.txt</Str>
  <Str sr="arg1" ve="3">%result_content</Str>
  <Int sr="arg2" val="0"/>
  <Int sr="arg3" val="1"/>
</Action>

<!--
  Read File (code=417)
  arg0: 文件路径
  arg1: 保存到变量
  arg2: 结构输出（false=纯文本, true=解析JSON等）
-->
<Action sr="act5" ve="7">
  <code>417</code>
  <Str sr="arg0" ve="3">/sdcard/Tasker/input.json</Str>
  <Str sr="arg1" ve="3">%file_content</Str>
  <Int sr="arg2" val="0"/>
</Action>
```

#### JavaScriptlet

```xml
<!--
  JavaScriptlet (code=418)
  arg0: JavaScript 代码
  arg1: 超时（秒，0=无超时）
  
  可用的 Tasker JS 函数:
    global(key)     : 读取全局变量
    setGlobal(k, v) : 设置全局变量
    local(key)      : 读取局部变量
    setLocal(k, v)  : 设置局部变量
    flash(text)     : 弹出 Toast 提示
    popup(title, body, timeout) : 弹出对话框
    performTask(name, priority, var1, var2) : 调用其他任务
    sendIntent(...) : 发送 Intent
    setExitIcon(ic) : 设置通知栏图标
    readFile(path)  : 读取文件
    writeFile(p,t,append) : 写入文件
    exit()          : 终止任务
    tts(text)       : 文本朗读
    vibrate(dur)    : 振动
    
  任务调用特殊函数:
    performTask(name, priority, %par1, %par2) : 同步调用
    performTask(name, priority, %par1)       : 异步调用（priority 带 + 号）
      - 被调用任务通过 %par1, %par2 接收参数
      - 通过 Return 动作 (code=135) 返回值
      - 调用方的 %rt_code 变量接收返回值
-->
<Action sr="act6" ve="7">
  <code>418</code>
  <Str sr="arg0" ve="3">
    // 获取当前设备的CPU使用率
    var cpuInfo = local("cpu_info");
    if (cpuInfo === undefined || cpuInfo === "") {
        flash("CPU信息不可用");
        exit();
    }
    
    // 解析JSON数据
    try {
        var data = JSON.parse(cpuInfo);
        setLocal("cpu_temp", data.temp.toString());
        setLocal("cpu_pct", data.usage.toString());
        
        // 构建结果 JSON
        var result = {
            timestamp: Date.now(),
            temperature: data.temp,
            usage: data.usage,
            status: data.usage > 80 ? "warning" : "normal"
        };
        setLocal("result_json", JSON.stringify(result));
        
        flash("CPU: " + data.usage + "% / " + data.temp + "C");
    } catch (e) {
        flash("JSON解析失败: " + e.message);
    }
  </Str>
  <Int sr="arg1" val="30"/>
</Action>
```

#### 通知与提示

```xml
<!--
  Flash (code=548) — Toast 提示消息
  arg0: 文本内容
  arg1: 持续时间（0=短, 1=长）
  arg2: 任务按钮位置（0=不显示）
-->
<Action sr="act7" ve="7">
  <code>548</code>
  <Str sr="arg0" ve="3">操作已完成！</Str>
  <Int sr="arg1" val="0"/>
  <Int sr="arg2" val="0"/>
</Action>

<!--
  Notify (code=523) — 通知栏通知
  arg0: 标题
  arg1: 内容
  arg2: 图标
  arg3: 通知ID（用于取消）
-->
<Action sr="act8" ve="7">
  <code>523</code>
  <Str sr="arg0" ve="3">自动化完成</Str>
  <Str sr="arg1" ve="3">处理了 %counter 条数据</Str>
  <Str sr="arg2" ve="3"/>
  <Int sr="arg3" val="0"/>
  <Int sr="arg4" val="0"/>
  <Str sr="arg5" ve="3">ic_launcher</Str>
  <Int sr="arg6" val="0"/>
  <Int sr="arg7" val="0"/>
  <Int sr="arg8" val="0"/>
</Action>
```

#### 系统控制

```xml
<!--
  Shell (code=130) — 执行Shell命令
  arg0: 命令
  arg1: 超时（秒）
  arg2: 使用Root（true/false）
  arg3: 保存输出到变量
  arg4: 保存错误到变量
-->
<Action sr="act9" ve="7">
  <code>130</code>
  <Str sr="arg0" ve="3">dumpsys battery | grep level</Str>
  <Int sr="arg1" val="5"/>
  <Int sr="arg2" val="0"/>
  <Str sr="arg3" ve="3">%shell_output</Str>
  <Str sr="arg4" ve="3">%shell_error</Str>
</Action>
```

#### 任务间调用

```xml
<!--
  Perform Task (code=135) — 调用其他任务
  arg0: 目标任务名
  arg1: 优先级（%priority-1 = 低, %priority = 相同, %priority+1 = 高）
  arg2: %par1 的值
  arg3: %par2 的值
  arg4: 返回值变量名（可选）
  arg5: 是否传递变量（true=传递 %par1, %par2）
  arg6: 传递结构（0=纯文本, 1=JSON）
-->
<Action sr="act10" ve="7">
  <code>135</code>
  <Str sr="arg0" ve="3">ProcessData</Str>
  <Int sr="arg1" val="0"/>
  <Str sr="arg2" ve="3">%input_data</Str>
  <Str sr="arg3" ve="3">normal</Str>
  <Str sr="arg4" ve="3">%rt_code</Str>
  <Int sr="arg5" val="1"/>
  <Int sr="arg6" val="0"/>
</Action>
```

---

## Scene 界面场景完整参考

Scene 是 Tasker 中的自定义用户界面，支持两种模式：**旧版元素**（TextElement、ImageElement 等）和 **Widget v2 自定义布局**（新版推荐，使用 JSON 结构化描述）。

### Scene 结构模板（旧版）

```xml
<!--
  Scene 完整模板（旧版元素格式）
  通用属性:
    <nme>        : Scene 名称
    <heightLand> : 横屏高度（-1 = 自适应）
    <heightPort> : 竖屏高度
    <widthLand>  : 横屏宽度（-1 = 自适应）
    <widthPort>  : 竖屏宽度
    
  元素系列（sr="elementsN"）:
    TextElement  : 文本标签
    RectElement  : 矩形/分割线
    EditTextElement : 文本输入框
    ImageElement : 图片
    ButtonElement  : 按钮
    CheckBoxElement : 复选框
    ToggleElement : 开关
    SliderElement  : 滑动条
    
  属性面板:
    PropertiesElement : Scene 级别属性（背景、标题栏等）
  
  元素通用属性:
    <flags>  : 标志位（4=只读, 5=可交互, ...）
    <geom>   : 几何信息（x,y,w,h, 其他参数...）
    <clickTask> : 点击触发 Task ID
    <longClickTask> : 长按触发 Task ID
-->
<Scene sr="sceneMainScene">
  <cdate>1700000000000</cdate>
  <edate>1700000000000</edate>
  <heightLand>-1</heightLand>
  <heightPort>600</heightPort>
  <nme>MainScene</nme>
  <widthLand>-1</widthLand>
  <widthPort>400</widthPort>

  <!-- 标题文本 -->
  <TextElement sr="elements0" ve="3">
    <flags>4</flags>
    <geom>10,10,380,50,0,0,20,20</geom>
    <Str sr="arg0" ve="3">标题文字</Str>
    <Str sr="arg1" ve="3">系统状态</Str>
    <Int sr="arg2" val="24"/>
    <Int sr="arg3" val="100"/>
    <Str sr="arg4" ve="3">#FF333333</Str>
    <Str sr="arg5" ve="3"/>
    <Int sr="arg6" val="3"/>
    <Int sr="arg7"/>
    <Int sr="arg8"/>
  </TextElement>

  <!-- 分割线 -->
  <RectElement sr="elements1">
    <flags>4</flags>
    <geom>0,70,400,2,-1,-1,-1,-1</geom>
    <Str sr="arg0" ve="3">分隔线</Str>
    <Int sr="arg1" val="0"/>
    <Str sr="arg2" ve="3">#FFCCCCCC</Str>
    <Str sr="arg3" ve="3"/>
    <Int sr="arg4" val="0"/>
    <Str sr="arg5" ve="3">#FF000000</Str>
    <Int sr="arg6" val="0"/>
    <Int sr="arg7" val="0"/>
  </RectElement>

  <!-- 内容文本（可点击） -->
  <TextElement sr="elements2" ve="3">
    <clickTask>301</clickTask>
    <flags>5</flags>
    <geom>15,80,370,200,-1,-1,-1,-1</geom>
    <Str sr="arg0" ve="3">内容描述</Str>
    <Str sr="arg1" ve="3">%dynamic_content</Str>
    <Int sr="arg2" val="18"/>
    <Int sr="arg3" val="100"/>
    <Str sr="arg4" ve="3">#FF000000</Str>
    <Str sr="arg5" ve="3"/>
    <Int sr="arg6" val="0"/>
    <Int sr="arg7" val="0"/>
    <Int sr="arg8"/>
  </TextElement>

  <!-- 关闭按钮 -->
  <ButtonElement sr="elements3">
    <clickTask>302</clickTask>
    <flags>0</flags>
    <geom>60,300,280,60,-1,-1,-1,-1</geom>
    <Str sr="arg0" ve="3">关闭按钮</Str>
    <Str sr="arg1" ve="3">关闭</Str>
    <Int sr="arg2" val="18"/>
    <Int sr="arg3" val="100"/>
    <Str sr="arg4" ve="3">#FFFFFFFF</Str>
    <Str sr="arg5" ve="3">#FFE53935</Str>
    <Int sr="arg6" val="0"/>
    <Int sr="arg7" val="0"/>
  </ButtonElement>

  <!-- Scene 属性 -->
  <PropertiesElement sr="props">
    <Int sr="arg0" val="1"/>
    <Int sr="arg1" val="0"/>
    <Str sr="arg2" ve="3">#FFFFFFFF</Str>
    <Int sr="arg3" val="0"/>
    <Str sr="arg4" ve="3">系统状态面板</Str>
    <Str sr="arg5" ve="3"/>
    <Img sr="arg6" ve="2"/>
    <Str sr="arg7" ve="3"/>
  </PropertiesElement>
</Scene>
```

### Widget v2 自定义布局（推荐新格式）

新格式用于 Widget v2 动作（code=461）的 `arg13`。JSON 存放在 `<Str sr="arg13" ve="3">` 中。

完整 JSON schema 定义的元素类型：

| 类型 | 说明 | 关键属性 |
|:---|:---|:---|
| `Box` | 通用容器 | `children`, `horizontalAlignment`, `verticalAlignment`, `fillMaxSize` |
| `Column` | 垂直布局 | `scrolling`, `children` (超过10个子元素需启用滚动) |
| `Row` | 水平布局 | `children` (最多10个) |
| `Grid` | 网格布局 | `fixed`, `minSize`, `children` |
| `Scaffold` | 页面框架 | `titleBar`, `horizontalPadding` |
| `TitleBar` | 标题栏 | `icon`, `text`, `iconColor`, `textColor`, `actions` |
| `Text` | 文本 | `text`, `color`, `textSize`, `bold`, `align` (Left/Right/Center/Start/End), `maxLines` |
| `Image` | 图片 | `url`, `contentScale` (Crop/Fit/FillBounds), `tint`, `circle`, `grayscale`, `blur` |
| `Button` | 按钮 | `text`, `buttonType` (Filled/Outline/Normal), `enabled`, `contentColor`, `icon` |
| `IconButton` | 图标按钮 | `icon`, `buttonType` (Circle/Square) |
| `CheckBox` | 复选框 | `text`, `checked`, `checkedColor`, `uncheckedColor` |
| `Switch` | 开关 | `text`, `checked`, `checkedTrackColor`, `uncheckedTrackColor` |
| `Progress` | 进度条 | `progress` (0-100), `progressType` (Linear/Circle), `color`, `trackColor` |
| `Spacer` | 空白间隔 | （无特殊属性） |

**通用属性：**

| 属性 | 类型 | 说明 |
|:---|:---|:---|
| `size` | int/string | 尺寸（"fill"=填充, 数字=固定dp） |
| `width` | int | 宽度（dp） |
| `height` | int | 高度（dp） |
| `padding` | int | 内边距（dp） |
| `paddingTop/Bottom/Start/End` | int | 方向内边距 |
| `backgroundColor` | color | 背景色 |
| `cornerRadius` | int | 圆角半径 |
| `visibility` | string | Visible/Invisible/Gone |
| `fillMaxSize/Width/Height` | bool | 填充 |
| `task` | string | 指定点击时执行的任务名 |
| `taskVariables` | object | 传递给任务的变量（如 {"%url": "https://..."}） |
| `commandPrefix` | string | 命令前缀（Command System 备选方案） |
| `isWeighted` | bool | 权重分配（用于 Row/Column 内元素等比分配空间） |

**点击交互机制：**
- **优先使用**: `task` + `taskVariables` 属性 —— 在指定元素上设置，点击后调用命名 Task 并传递变量。这是推荐方式。
- **备选方案**: `commandPrefix` + Command Profile —— 点击后发送 `=:=` 分隔的命令。需要额外配置 Project 内的 Command 事件 Profile。仅作为备选。

#### Widget v2 布局 JSON 示例

```json
{
  "type": "Scaffold",
  "horizontalPadding": 16,
  "titleBar": {
    "type": "TitleBar",
    "icon": "ic_widget_system",
    "text": "系统状态监控",
    "iconColor": "#FFFFFF",
    "textColor": "#FFFFFF",
    "backgroundColor": "#FF1565C0",
    "actions": [
      {
        "type": "IconButton",
        "icon": "ic_action_refresh",
        "buttonType": "Square",
        "contentColor": "#FFFFFF",
        "task": "RefreshData",
        "taskVariables": {
          "%refresh_source": "widget_tap"
        }
      }
    ]
  },
  "children": [
    {
      "type": "Column",
      "children": [
        {
          "type": "Row",
          "padding": 12,
          "children": [
            {
              "type": "Text",
              "text": "CPU 使用率",
              "isWeighted": true,
              "textSize": "14sp",
              "type": "Text"
            },
            {
              "type": "Text",
              "text": "%cpu_usage %%",
              "textSize": "14sp",
              "bold": true,
              "type": "Text"
            }
          ]
        },
        {
          "type": "Progress",
          "progress": "%cpu_usage",
          "progressType": "Linear",
          "color": "#FF4CAF50",
          "trackColor": "#FFE0E0E0",
          "height": 6
        },
        {
          "type": "Row",
          "padding": 12,
          "children": [
            {
              "type": "Text",
              "text": "内存使用",
              "isWeighted": true,
              "textSize": "14sp",
              "type": "Text"
            },
            {
              "type": "Text",
              "text": "%mem_used GB / %mem_total GB",
              "textSize": "14sp",
              "bold": true,
              "type": "Text"
            }
          ]
        },
        {
          "type": "Row",
          "padding": 8,
          "children": [
            {
              "type": "Button",
              "text": "刷新",
              "buttonType": "Filled",
              "contentColor": "#FFFFFF",
              "backgroundColor": "#FF1976D2",
              "size": "fill",
              "task": "RefreshData",
              "taskVariables": {
                "%refresh_source": "button_tap"
              }
            }
          ]
        }
      ]
    }
  ]
}
```

---

## 变量类型与命名规范

### 变量分类

| 类别 | 前缀 | 作用域 | 示例 | 说明 |
|:---|:---|:---|:---|:---|
| 全局变量 | `%Name` | 全局可读写 | `%MyCounter` | 至少一个大写字母 |
| 局部变量 | `%name` | Task 内 | `%temp_result` | 全部小写 |
| 内置变量 | `%` + 大写 | 系统只读 | `%TIME`, `%WIFI` | Tasker 预定义 |
| 数组 | `%name()` | 取决于前缀 | `%data(1)` | 括号索引 |

### 常用内置变量

| 变量 | 说明 | 变量 | 说明 |
|:---|:---|:---|:---|
| `%TIME` | 当前时间 HH.MM | `%DATE` | 日期 MM-DD-YYYY |
| `%TIMES` | 时间戳（秒） | `%TIMEMS` | 时间戳（毫秒） |
| `%WIFI` | WiFi 状态 on/off | `%WIFII` | WiFi SSID 信息 或 %WIFII |
| `%BATT` | 电池电量 (0-100) | `%TEMP` | 电池温度 (0.1C) |
| `%SCREEN` | 屏幕状态 on/off | `%AIR` | 飞行模式 on/off |
| `%BLUE` | 蓝牙状态 on/off | `%CPUFREQ` | CPU 频率 |
| `%MEMF` | 可用内存（MB） | `%NTITLE` | 最近通知标题 |
| `%PACTIVE` | 前台应用包名 | `%LIGHT` | 光线传感器 |
| `%VOLM` | 媒体音量 | `%BRIGHT` | 屏幕亮度 |
| `%WIN` | 当前窗口标签 | `%SDK` | Android SDK 版本 |
| `%LOC` | GPS 位置（纬,经） | `%LOCN` | GPS 网位置 |
| `%DEVIP` | 设备 IP | `%ROAM` | 漫游状态 |
| `%err` | 错误消息 | `%errmsg` | 详细错误信息 |

### 变量命名建议

1. **全局变量**：使用 `%` 前缀 + 至少一个大写字母，如 `%AtHome`, `%UserConfig`
2. **局部变量**：使用 `%` 前缀 + 全小写，推荐用下划线分隔，如 `%count`, `%temp_result`, `%api_response_parsed`
3. **配置变量**：将用户可自定义的配置参数定义为全局变量，以 `%Config_` 前缀开头
4. **数组**：追加 `()` 后缀配合索引访问，如 `%data(1)`, `%files()`

---

## 权限声明

Tasker XML 中通过 Project 的 `<Share>` 标签中的 `<g>` 字段声明所需权限组（参见 Project 部分的导出权限组表），实际运行时 Android 会在相应权限触发时弹窗请求授权。

**Tasker 自身权限：**

| 权限 | 对应功能 |
|:---|:---|
| `android.permission.ACCESSIBILITY` | 无障碍服务（UI交互、通知拦截） |
| `android.permission.NOTIFICATION_LISTENER` | 通知读取 |
| `android.permission.WRITE_SECURE_SETTINGS` | 修改系统设置（需 ADB 授权：`pm grant net.dinglisch.android.taskerm android.permission.WRITE_SECURE_SETTINGS`） |
| `android.permission.DUMP` | 系统诊断（需 ADB 授权） |
| `android.permission.ACCESS_FINE_LOCATION` | GPS 精确定位 |
| `android.permission.ACCESS_COARSE_LOCATION` | 网络粗略定位 |
| `android.permission.CALL_PHONE` | 拨打电话 |
| `android.permission.READ_SMS` | 读取短信 |
| `android.permission.SEND_SMS` | 发送短信 |
| `android.permission.READ_PHONE_STATE` | 读取电话状态 |
| `android.permission.READ_EXTERNAL_STORAGE` | 读取外部存储 |
| `android.permission.WRITE_EXTERNAL_STORAGE` | 写入外部存储 |

**常用 ADB 授权命令：**

```bash
# Tasker 安全设置写入权限（推荐）
adb shell pm grant net.dinglisch.android.taskerm android.permission.WRITE_SECURE_SETTINGS

# 通知读取
adb shell cmd notification allow_listener net.dinglisch.android.taskerm

# 电池优化白名单
adb shell dumpsys deviceidle whitelist +net.dinglisch.android.taskerm

# 数据用量统计
adb shell pm grant net.dinglisch.android.taskerm android.permission.PACKAGE_USAGE_STATS
```

---

## 可直接导入的完整配置范例

**提示**：将以下任一范例保存为 `.prj.xml` 文件，放入 Android 设备的 `/sdcard/Tasker/` 目录，在 Tasker 中长按底部「配置文件」标签 → 选择「导入」即可使用。

### 范例一：系统监控自动化项目

**功能**：整点检测电池电量，低于 20% 时发送通知提醒充电，并写入日志文件。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!--
  项目: System Monitor
  版本: 1.0
  Tasker版本: >= 6.0 (tv=6.6.20)
  描述: 每小时检查电池电量，低于20%发送提醒，记录到日志文件。
  导入方法: 保存为 system_monitor.prj.xml，放入 /sdcard/Tasker/ 目录后导入。
-->
<TaskerData sr="" dvi="1" tv="6.6.20">

  <!-- =============================================================
       项目定义
  ============================================================= -->
  <Project sr="proj0" ve="2">
    <cdate>1700000000000</cdate>
    <name>System Monitor</name>
    <pids>101</pids>
    <tids>201</tids>
    <Share sr="Share">
      <b>false</b>
      <d>系统监控项目：每小时检查电池与内存状态，异常时提醒。</d>
      <g>Data,Files</g>
      <p>true</p>
      <t>monitoring,system</t>
    </Share>
  </Project>

  <!-- =============================================================
       Profile 101: 整点触发
       触发: Time — 每小时整点
       关联: Task 201
  ============================================================= -->
  <Profile sr="prof101" ve="2">
    <cdate>1700000000000</cdate>
    <clp>true</clp>
    <edate>1700000000000</edate>
    <flags>40</flags>
    <id>101</id>
    <mid0>201</mid0>
    <nme>Hourly System Check</nme>
    <Time sr="con0">
      <fh>0</fh>
      <fm>0</fm>
      <th>23</th>
      <tm>59</tm>
    </Time>
  </Profile>

  <!-- =============================================================
       Task 201: 系统检查与通知
       步骤: 获取电池电量 → 判断是否低于20% → 
             低于则通知+写日志 → 高于则静默记录
  ============================================================= -->
  <Task sr="task201">
    <cdate>1700000000000</cdate>
    <edate>1700000000000</edate>
    <id>201</id>
    <pri>5</pri>
    <rty>1</rty>
    <CollisionT>30000</CollisionT>

    <!-- Action 0: Variable Set — 创建日志条目 -->
    <Action sr="act0" ve="7">
      <code>547</code>
      <Str sr="arg0" ve="3">%log_entry</Str>
      <Str sr="arg1" ve="3">%DATE %TIME | Battery: %BATT % | Temp: %TEMP°C | Mem: %MEMF MB</Str>
      <Int sr="arg2" val="0"/>
      <Int sr="arg3" val="0"/>
      <Int sr="arg4" val="0"/>
      <Int sr="arg5" val="0"/>
      <Int sr="arg6" val="0"/>
    </Action>

    <!-- Action 1: If — 电池电量小于 20 -->
    <Action sr="act1" ve="7">
      <code>37</code>
      <ConditionList sr="if">
        <Condition sr="c0" ve="3">
          <lhs>%BATT</lhs>
          <op>6</op>
          <rhs>20</rhs>
        </Condition>
      </ConditionList>
    </Action>

    <!-- Action 2: Notify — 低电量提醒 -->
    <Action sr="act2" ve="7">
      <code>523</code>
      <Str sr="arg0" ve="3">低电量警告</Str>
      <Str sr="arg1" ve="3">电量仅剩 %BATT %，请及时充电！</Str>
      <Str sr="arg2" ve="3"/>
      <Int sr="arg3" val="0"/>
      <Int sr="arg4" val="0"/>
      <Str sr="arg5" ve="3">ic_alert</Str>
      <Int sr="arg6" val="0"/>
      <Int sr="arg7" val="0"/>
      <Int sr="arg8" val="0"/>
    </Action>

    <!-- Action 3: Variable Set — 标记为警告 -->
    <Action sr="act3" ve="7">
      <code>547</code>
      <Str sr="arg0" ve="3">%log_entry</Str>
      <Str sr="arg1" ve="3">%log_entry [WARNING: Low Battery]</Str>
      <Int sr="arg2" val="0"/>
      <Int sr="arg3" val="0"/>
      <Int sr="arg4" val="0"/>
      <Int sr="arg5" val="0"/>
      <Int sr="arg6" val="0"/>
    </Action>

    <!-- Action 4: End If -->
    <Action sr="act4" ve="7">
      <code>38</code>
    </Action>

    <!-- Action 5: Write File — 追加写入日志 -->
    <Action sr="act5" ve="7">
      <code>410</code>
      <Str sr="arg0" ve="3">/sdcard/Tasker/system_monitor.log</Str>
      <Str sr="arg1" ve="3">%log_entry
</Str>
      <Int sr="arg2" val="1"/>
      <Int sr="arg3" val="0"/>
    </Action>

  </Task>

</TaskerData>
```

### 范例二：WiFi 连接自动切换移动数据

**功能**：连接指定 WiFi 后关闭移动数据，断开 WiFi 后重新开启。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<TaskerData sr="" dvi="1" tv="6.6.20">

  <Project sr="proj0" ve="2">
    <cdate>1700000000000</cdate>
    <name>WiFi Data Manager</name>
    <pids>102</pids>
    <tids>202</tids>
    <Share sr="Share">
      <b>false</b>
      <d>连接WiFi时自动关闭移动数据，断开时自动恢复。</d>
      <g>Data</g>
      <p>true</p>
      <t>network,wifi</t>
    </Share>
  </Project>

  <!-- =============================================================
       Profile 102: WiFi 连接状态
       触发: State — 已连接 WiFi
       入口: Task 202 — 关闭移动数据
       出口: Task 202 — 移动数据也会被 Tasker 自动反操作
                （不建议依赖自动反操作，可创建专门的出口任务）
  ============================================================= -->
  <Profile sr="prof102" ve="2">
    <cdate>1700000000000</cdate>
    <clp>true</clp>
    <edate>1700000000000</edate>
    <flags>40</flags>
    <id>102</id>
    <mid0>202</mid0>
    <mid1>202</mid1>
    <nme>WiFi Connected - Toggle Data</nme>
    <State sr="con0" ve="2">
      <code>39</code>
      <Str sr="arg0" ve="3">*</Str>
      <Str sr="arg1" ve="3"/>
      <Int sr="arg2" val="0"/>
    </State>
  </Profile>

  <!-- =============================================================
       Task 202: 切换移动数据
       通过 %caller1 区分入口/出口:
         %caller1 = 1 (入口: WiFi 连接)
         %caller1 = 2 (出口: WiFi 断开)
  ============================================================= -->
  <Task sr="task202">
    <cdate>1700000000000</cdate>
    <edate>1700000000000</edate>
    <id>202</id>
    <pri>5</pri>
    <rty>1</rty>
    <CollisionT>30000</CollisionT>

    <!-- Action 0: If — 入口（WiFi 连上了） -->
    <Action sr="act0" ve="7">
      <code>37</code>
      <ConditionList sr="if">
        <Condition sr="c0" ve="3">
          <lhs>%caller1</lhs>
          <op>0</op>
          <rhs>enter</rhs>
        </Condition>
      </ConditionList>
    </Action>

    <!-- Action 1: Mobile Data — 关闭 -->
    <Action sr="act1" ve="7">
      <code>14</code>
      <Int sr="arg0" val="0"/>
    </Action>

    <!-- Action 2: Flash — 确认提示 -->
    <Action sr="act2" ve="7">
      <code>548</code>
      <Str sr="arg0" ve="3">已连接 WiFi，移动数据已关闭</Str>
      <Int sr="arg1" val="0"/>
      <Int sr="arg2" val="0"/>
    </Action>

    <!-- Action 3: Else — 出口（WiFi 断开了） -->
    <Action sr="act3" ve="7">
      <code>39</code>
    </Action>

    <!-- Action 4: Mobile Data — 开启 -->
    <Action sr="act4" ve="7">
      <code>14</code>
      <Int sr="arg0" val="1"/>
    </Action>

    <!-- Action 5: Flash — 确认提示 -->
    <Action sr="act5" ve="7">
      <code>548</code>
      <Str sr="arg0" ve="3">WiFi 已断开，移动数据已恢复</Str>
      <Int sr="arg1" val="0"/>
      <Int sr="arg2" val="0"/>
    </Action>

    <!-- Action 6: End If -->
    <Action sr="act6" ve="7">
      <code>38</code>
    </Action>

    <!-- Action 7: Wait — 2秒防抖 -->
    <Action sr="act7" ve="7">
      <code>30</code>
      <Int sr="arg0" val="2"/>
      <Int sr="arg1" val="0"/>
      <Int sr="arg2" val="0"/>
      <Int sr="arg3" val="0"/>
      <Int sr="arg4" val="0"/>
    </Action>

  </Task>

</TaskerData>
```

### 范例三：HTTP 请求 + JSON 解析

**功能**：手动触发 → 请求天气 API → 解析 JSON → 弹出通知。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<TaskerData sr="" dvi="1" tv="6.6.20">

  <Project sr="proj0" ve="2">
    <cdate>1700000000000</cdate>
    <name>Weather Fetcher</name>
    <pids>103</pids>
    <tids>203</tids>
    <Share sr="Share">
      <b>false</b>
      <d>调用天气API获取当前天气信息并通过通知展示。</d>
      <g>Data</g>
      <p>true</p>
      <t>weather,api</t>
    </Share>
  </Project>

  <!-- 手动触发的 Profile — 使用快捷方式或 Tasker 小部件触发 -->
  <Profile sr="prof103" ve="2">
    <cdate>1700000000000</cdate>
    <clp>true</clp>
    <edate>1700000000000</edate>
    <flags>40</flags>
    <id>103</id>
    <mid0>203</mid0>
    <nme>Manual Weather Fetch</nme>
  </Profile>

  <!-- =============================================================
       Task 203: 获取天气信息
       步骤: HTTP请求 → 检查响应 → JS解析JSON → 通知展示
  ============================================================= -->
  <Task sr="task203">
    <cdate>1700000000000</cdate>
    <edate>1700000000000</edate>
    <id>203</id>
    <pri>5</pri>
    <rty>1</rty>
    <CollisionT>30000</CollisionT>

    <!-- Action 0: Variable Set — 设置城市参数（可按需修改） -->
    <Action sr="act0" ve="7">
      <code>547</code>
      <Str sr="arg0" ve="3">%weather_city</Str>
      <Str sr="arg1" ve="3">Beijing</Str>
      <Int sr="arg2" val="1"/>
      <Int sr="arg3" val="0"/>
      <Int sr="arg4" val="0"/>
      <Int sr="arg5" val="0"/>
      <Int sr="arg6" val="0"/>
    </Action>

    <!-- Action 1: HTTP Request — 调用天气 API -->
    <Action sr="act1" ve="7">
      <code>279</code>
      <Str sr="arg0" ve="3">https://wttr.in/%weather_city?format=j1</Str>
      <Str sr="arg1" ve="3">GET</Str>
      <Str sr="arg2" ve="3"/>
      <Str sr="arg3" ve="3">%http_response</Str>
      <Str sr="arg4" ve="3"/>
      <Int sr="arg5" val="15"/>
      <Str sr="arg6" ve="3"/>
      <Int sr="arg7" val="0"/>
      <Int sr="arg8" val="1"/>
    </Action>

    <!-- Action 2: If — 检查 HTTP 返回状态 -->
    <Action sr="act2" ve="7">
      <code>37</code>
      <ConditionList sr="if">
        <Condition sr="c0" ve="3">
          <lhs>%http_response</lhs>
          <op>12</op>
        </Condition>
      </ConditionList>
    </Action>

    <!-- Action 3: JavaScriptlet — 解析 JSON -->
    <Action sr="act3" ve="7">
      <code>418</code>
      <Str sr="arg0" ve="3">
        try {
            var data = JSON.parse(local("http_response"));
            var current = data.current_condition[0];
            var weather = data.weather[0];
            
            setLocal("weather_temp", current.temp_C + "C");
            setLocal("weather_humidity", current.humidity + "%");
            setLocal("weather_desc", current.weatherDesc[0].value);
            setLocal("weather_wind", current.windspeedKmph + " km/h " + current.winddir16Point);
            setLocal("weather_max", weather.maxtempC + "C");
            setLocal("weather_min", weather.mintempC + "C");
            
            setLocal("weather_msg", 
                "温度: " + local("weather_temp") + 
                " (最高: " + local("weather_max") + " 最低: " + local("weather_min") + ")\n" +
                "天气: " + local("weather_desc") + "\n" +
                "湿度: " + local("weather_humidity") + " 风速: " + local("weather_wind")
            );
        } catch (e) {
            setLocal("weather_msg", "天气数据解析失败: " + e.message);
            setLocal("weather_error", "true");
        }
      </Str>
      <Int sr="arg1" val="10"/>
    </Action>

    <!-- Action 4: If — 解析成功，发送通知 -->
    <Action sr="act4" ve="7">
      <code>37</code>
      <ConditionList sr="if">
        <Condition sr="c0" ve="3">
          <lhs>%weather_error</lhs>
          <op>13</op>
        </Condition>
      </ConditionList>
    </Action>

    <!-- Action 5: Notify — 天气通知 -->
    <Action sr="act5" ve="7">
      <code>523</code>
      <Str sr="arg0" ve="3">%weather_city 天气</Str>
      <Str sr="arg1" ve="3">%weather_msg</Str>
      <Str sr="arg2" ve="3"/>
      <Int sr="arg3" val="0"/>
      <Int sr="arg4" val="0"/>
      <Str sr="arg5" ve="3">ic_weather</Str>
      <Int sr="arg6" val="0"/>
      <Int sr="arg7" val="0"/>
      <Int sr="arg8" val="0"/>
    </Action>

    <!-- Action 6: Else — 解析失败 -->
    <Action sr="act6" ve="7">
      <code>39</code>
    </Action>

    <!-- Action 7: Flash — 错误提示 -->
    <Action sr="act7" ve="7">
      <code>548</code>
      <Str sr="arg0" ve="3">%weather_msg</Str>
      <Int sr="arg1" val="1"/>
      <Int sr="arg2" val="0"/>
    </Action>

    <!-- Action 8: End If -->
    <Action sr="act8" ve="7">
      <code>38</code>
    </Action>

    <!-- Action 9: Else — 连接失败 -->
    <Action sr="act9" ve="7">
      <code>39</code>
    </Action>

    <!-- Action 10: Flash — 连接错误 -->
    <Action sr="act10" ve="7">
      <code>548</code>
      <Str sr="arg0" ve="3">无法连接到天气服务，请检查网络</Str>
      <Int sr="arg1" val="1"/>
      <Int sr="arg2" val="0"/>
    </Action>

    <!-- Action 11: End If -->
    <Action sr="act11" ve="7">
      <code>38</code>
    </Action>

  </Task>

</TaskerData>
```

### 范例四：Scene 弹窗界面

**功能**：Tasker 快捷方式触发 → 弹出自定义 Scene → 显示系统状态并支持刷新。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<TaskerData sr="" dvi="1" tv="6.6.20">

  <Project sr="proj0" ve="2">
    <cdate>1700000000000</cdate>
    <name>System Info Panel</name>
    <pids>104</pids>
    <tids>204,205</tids>
    <scenes>SysPanel</scenes>
    <Share sr="Share">
      <b>false</b>
      <d>自定义系统状态面板：显示电池、存储、内存等信息。</d>
      <g>Data</g>
      <p>true</p>
      <t>system,ui</t>
    </Share>
  </Project>

  <!-- =============================================================
       Profile 104: 快捷方式触发
  ============================================================= -->
  <Profile sr="prof104" ve="2">
    <cdate>1700000000000</cdate>
    <clp>true</clp>
    <edate>1700000000000</edate>
    <flags>40</flags>
    <id>104</id>
    <mid0>204</mid0>
    <nme>Show System Panel</nme>
  </Profile>

  <!-- =============================================================
       Task 204: 准备数据并显示 Scene
       步骤: 设置状态变量 → 显示 Scene
  ============================================================= -->
  <Task sr="task204">
    <cdate>1700000000000</cdate>
    <edate>1700000000000</edate>
    <id>204</id>
    <pri>5</pri>
    <rty>1</rty>
    <CollisionT>30000</CollisionT>

    <!-- Action 0: Variable Set — 电池状态文字 -->
    <Action sr="act0" ve="7">
      <code>547</code>
      <Str sr="arg0" ve="3">%panel_battery</Str>
      <Str sr="arg1" ve="3">电量: %BATT% | 温度: %TEMP°C</Str>
      <Int sr="arg2" val="0"/>
      <Int sr="arg3" val="0"/>
      <Int sr="arg4" val="0"/>
      <Int sr="arg5" val="0"/>
      <Int sr="arg6" val="0"/>
    </Action>

    <!-- Action 1: Variable Set — 内存 -->
    <Action sr="act1" ve="7">
      <code>547</code>
      <Str sr="arg0" ve="3">%panel_memory</Str>
      <Str sr="arg1" ve="3">可用内存: %MEMF MB | 屏幕: %SCREEN</Str>
      <Int sr="arg2" val="0"/>
      <Int sr="arg3" val="0"/>
      <Int sr="arg4" val="0"/>
      <Int sr="arg5" val="0"/>
      <Int sr="arg6" val="0"/>
    </Action>

    <!-- Action 2: Variable Set — 时间 -->
    <Action sr="act2" ve="7">
      <code>547</code>
      <Str sr="arg0" ve="3">%panel_time</Str>
      <Str sr="arg1" ve="3">更新时间: %TIME</Str>
      <Int sr="arg2" val="0"/>
      <Int sr="arg3" val="0"/>
      <Int sr="arg4" val="0"/>
      <Int sr="arg5" val="0"/>
      <Int sr="arg6" val="0"/>
    </Action>

    <!-- Action 3: Show Scene — 显示面板 -->
    <Action sr="act3" ve="7">
      <code>383</code>
      <Str sr="arg0" ve="3">SysPanel</Str>
      <Int sr="arg1" val="0"/>
      <Int sr="arg2" val="0"/>
      <Int sr="arg3" val="0"/>
      <Int sr="arg4" val="0"/>
      <Int sr="arg5" val="0"/>
      <Int sr="arg6" val="0"/>
      <Int sr="arg7" val="0"/>
      <Int sr="arg8" val="0"/>
    </Action>

  </Task>

  <!-- =============================================================
       Task 205: 刷新面板数据
  ============================================================= -->
  <Task sr="task205">
    <cdate>1700000000000</cdate>
    <edate>1700000000000</edate>
    <id>205</id>
    <pri>5</pri>
    <rty>1</rty>
    <CollisionT>30000</CollisionT>

    <Action sr="act0" ve="7">
      <code>547</code>
      <Str sr="arg0" ve="3">%panel_battery</Str>
      <Str sr="arg1" ve="3">电量: %BATT% | 温度: %TEMP°C</Str>
      <Int sr="arg2" val="0"/>
      <Int sr="arg3" val="0"/>
      <Int sr="arg4" val="0"/>
      <Int sr="arg5" val="0"/>
      <Int sr="arg6" val="0"/>
    </Action>

    <Action sr="act1" ve="7">
      <code>547</code>
      <Str sr="arg0" ve="3">%panel_memory</Str>
      <Str sr="arg1" ve="3">可用内存: %MEMF MB | 屏幕: %SCREEN</Str>
      <Int sr="arg2" val="0"/>
      <Int sr="arg3" val="0"/>
      <Int sr="arg4" val="0"/>
      <Int sr="arg5" val="0"/>
      <Int sr="arg6" val="0"/>
    </Action>

    <Action sr="act2" ve="7">
      <code>547</code>
      <Str sr="arg0" ve="3">%panel_time</Str>
      <Str sr="arg1" ve="3">更新时间: %TIME</Str>
      <Int sr="arg2" val="0"/>
      <Int sr="arg3" val="0"/>
      <Int sr="arg4" val="0"/>
      <Int sr="arg5" val="0"/>
      <Int sr="arg6" val="0"/>
    </Action>

    <Action sr="act3" ve="7">
      <code>548</code>
      <Str sr="arg0" ve="3">数据已刷新</Str>
      <Int sr="arg1" val="0"/>
      <Int sr="arg2" val="0"/>
    </Action>

  </Task>

  <!-- =============================================================
       Scene: SysPanel — 系统状态面板（竖屏400dp宽 x 480dp高）
  ============================================================= -->
  <Scene sr="sceneSysPanel">
    <cdate>1700000000000</cdate>
    <edate>1700000000000</edate>
    <heightLand>-1</heightLand>
    <heightPort>480</heightPort>
    <nme>SysPanel</nme>
    <widthLand>-1</widthLand>
    <widthPort>400</widthPort>

    <!-- 标题栏 -->
    <TextElement sr="elements0" ve="3">
      <flags>4</flags>
      <geom>0,0,400,60,0,0,0,0</geom>
      <Str sr="arg0" ve="3">TitleBar</Str>
      <Str sr="arg1" ve="3">系统状态</Str>
      <Int sr="arg2" val="22"/>
      <Int sr="arg3" val="100"/>
      <Str sr="arg4" ve="3">#FFFFFFFF</Str>
      <Str sr="arg5" ve="3">#FF1565C0</Str>
      <Int sr="arg6" val="3"/>
      <Int sr="arg7"/>
      <Int sr="arg8"/>
    </TextElement>

    <!-- 电池信息 -->
    <TextElement sr="elements1" ve="3">
      <flags>4</flags>
      <geom>20,80,360,50,0,0,10,10</geom>
      <Str sr="arg0" ve="3">BatteryLabel</Str>
      <Str sr="arg1" ve="3">%panel_battery</Str>
      <Int sr="arg2" val="16"/>
      <Int sr="arg3" val="100"/>
      <Str sr="arg4" ve="3">#FF333333</Str>
      <Str sr="arg5" ve="3"/>
      <Int sr="arg6" val="0"/>
      <Int sr="arg7"/>
      <Int sr="arg8"/>
    </TextElement>

    <!-- 分割线 -->
    <RectElement sr="elements2">
      <flags>4</flags>
      <geom>20,140,360,2,-1,-1,-1,-1</geom>
      <Str sr="arg0" ve="3">Divider</Str>
      <Int sr="arg1" val="0"/>
      <Str sr="arg2" ve="3">#FFDDDDDD</Str>
      <Str sr="arg3" ve="3"/>
      <Int sr="arg4" val="0"/>
      <Str sr="arg5" ve="3">#FF000000</Str>
      <Int sr="arg6" val="0"/>
      <Int sr="arg7" val="0"/>
    </RectElement>

    <!-- 内存信息 -->
    <TextElement sr="elements3" ve="3">
      <flags>4</flags>
      <geom>20,155,360,50,0,0,10,10</geom>
      <Str sr="arg0" ve="3">MemLabel</Str>
      <Str sr="arg1" ve="3">%panel_memory</Str>
      <Int sr="arg2" val="16"/>
      <Int sr="arg3" val="100"/>
      <Str sr="arg4" ve="3">#FF333333</Str>
      <Str sr="arg5" ve="3"/>
      <Int sr="arg6" val="0"/>
      <Int sr="arg7"/>
      <Int sr="arg8"/>
    </TextElement>

    <!-- 网络信息（动态） -->
    <TextElement sr="elements4" ve="3">
      <flags>4</flags>
      <geom>20,215,360,50,0,0,10,10</geom>
      <Str sr="arg0" ve="3">NetLabel</Str>
      <Str sr="arg1" ve="3">WiFi: %WIFII (IP: %DEVIP)</Str>
      <Int sr="arg2" val="14"/>
      <Int sr="arg3" val="100"/>
      <Str sr="arg4" ve="3">#FF666666</Str>
      <Str sr="arg5" ve="3"/>
      <Int sr="arg6" val="0"/>
      <Int sr="arg7"/>
      <Int sr="arg8"/>
    </TextElement>

    <!-- 更新时间 -->
    <TextElement sr="elements5" ve="3">
      <flags>4</flags>
      <geom>20,280,360,30,0,0,10,0</geom>
      <Str sr="arg0" ve="3">TimeLabel</Str>
      <Str sr="arg1" ve="3">%panel_time</Str>
      <Int sr="arg2" val="12"/>
      <Int sr="arg3" val="100"/>
      <Str sr="arg4" ve="3">#FF999999</Str>
      <Str sr="arg5" ve="3"/>
      <Int sr="arg6" val="2"/>
      <Int sr="arg7"/>
      <Int sr="arg8"/>
    </TextElement>

    <!-- 刷新按钮 -->
    <ButtonElement sr="elements6">
      <clickTask>205</clickTask>
      <flags>0</flags>
      <geom>40,340,320,56,-1,-1,-1,-1</geom>
      <Str sr="arg0" ve="3">RefreshBtn</Str>
      <Str sr="arg1" ve="3">刷新数据</Str>
      <Int sr="arg2" val="18"/>
      <Int sr="arg3" val="100"/>
      <Str sr="arg4" ve="3">#FFFFFFFF</Str>
      <Str sr="arg5" ve="3">#FF1976D2</Str>
      <Int sr="arg6" val="0"/>
      <Int sr="arg7" val="0"/>
    </ButtonElement>

    <!-- 关闭按钮 -->
    <ButtonElement sr="elements7">
      <flags>0</flags>
      <geom>40,410,320,56,-1,-1,-1,-1</geom>
      <Str sr="arg0" ve="3">CloseBtn</Str>
      <Str sr="arg1" ve="3">关闭面板</Str>
      <Int sr="arg2" val="16"/>
      <Int sr="arg3" val="100"/>
      <Str sr="arg4" ve="3">#FF333333</Str>
      <Str sr="arg5" ve="3">#FFE0E0E0</Str>
      <Int sr="arg6" val="0"/>
      <Int sr="arg7" val="0"/>
    </ButtonElement>

    <!-- Scene 属性面板 -->
    <PropertiesElement sr="props">
      <Int sr="arg0" val="1"/>
      <Int sr="arg1" val="0"/>
      <Str sr="arg2" ve="3">#FFFFFFFF</Str>
      <Int sr="arg3" val="0"/>
      <Str sr="arg4" ve="3">系统状态面板</Str>
      <Str sr="arg5" ve="3"/>
      <Img sr="arg6" ve="2"/>
      <Str sr="arg7" ve="3"/>
    </PropertiesElement>

  </Scene>

</TaskerData>
```

### 范例五：Termux:Tasker 集成调用

**功能**：Tasker 通过 Termux:Tasker 插件调用 Python 脚本处理数据。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<TaskerData sr="" dvi="1" tv="6.6.20">

  <Project sr="proj0" ve="2">
    <cdate>1700000000000</cdate>
    <name>Termux Python Runner</name>
    <pids>105</pids>
    <tids>206</tids>
    <Share sr="Share">
      <b>false</b>
      <d>通过Termux:Tasker插件调用Python脚本执行数据分析。</d>
      <g>Data,Files</g>
      <p>true</p>
      <t>termux,python</t>
    </Share>
  </Project>

  <!-- 通过快捷方式手动触发 -->
  <Profile sr="prof105" ve="2">
    <cdate>1700000000000</cdate>
    <clp>true</clp>
    <edate>1700000000000</edate>
    <flags>40</flags>
    <id>105</id>
    <mid0>206</mid0>
    <nme>Run Python Analysis</nme>
  </Profile>

  <Task sr="task206">
    <cdate>1700000000000</cdate>
    <edate>1700000000000</edate>
    <id>206</id>
    <pri>5</pri>
    <rty>1</rty>
    <CollisionT>60000</CollisionT>

    <!-- Action 0: Variable Set — 构建 JSON 参数 -->
    <Action sr="act0" ve="7">
      <code>547</code>
      <Str sr="arg0" ve="3">%script_params</Str>
      <Str sr="arg1" ve="3">{"timestamp":%TIMEMS,"battery":%BATT,"mem_free":%MEMF}</Str>
      <Int sr="arg2" val="0"/>
      <Int sr="arg3" val="0"/>
      <Int sr="arg4" val="0"/>
      <Int sr="arg5" val="0"/>
      <Int sr="arg6" val="0"/>
    </Action>

    <!-- Action 1: Termux:Tasker — 调用 Python 分析脚本 -->
    <Action sr="act1" ve="7">
      <code>1342177284</code>
      <Bundle sr="arg0">
        <key>com.termux.tasker.ARGUMENTS</key>
        <value>scripts/analyze.py %script_params</value>
        <key>com.termux.tasker.EXECUTABLE</key>
        <value>/data/data/com.termux/files/usr/bin/python</value>
        <key>com.termux.tasker.TIMEOUT</key>
        <value>30</value>
        <key>com.termux.tasker.WORKDIR</key>
        <value>/data/data/com.termux/files/home/atlas-runtime</value>
      </Bundle>
      <Str sr="arg1" ve="3">com.termux.tasker</Str>
      <Str sr="arg2" ve="3">com.termux.tasker.TaskerReceiver</Str>
      <Int sr="arg3" val="0"/>
    </Action>

    <!-- Action 2: Wait — 等待脚本执行完成 -->
    <Action sr="act2" ve="7">
      <code>30</code>
      <Int sr="arg0" val="3"/>
      <Int sr="arg1" val="0"/>
      <Int sr="arg2" val="0"/>
      <Int sr="arg3" val="0"/>
      <Int sr="arg4" val="0"/>
    </Action>

    <!-- Action 3: Notify — 执行完成通知 -->
    <Action sr="act3" ve="7">
      <code>523</code>
      <Str sr="arg0" ve="3">Python 分析完成</Str>
      <Str sr="arg1" ve="3">脚本 analyze.py 已执行，参数: %script_params</Str>
      <Str sr="arg2" ve="3"/>
      <Int sr="arg3" val="0"/>
      <Int sr="arg4" val="0"/>
      <Str sr="arg5" ve="3">ic_termux</Str>
      <Int sr="arg6" val="0"/>
      <Int sr="arg7" val="0"/>
      <Int sr="arg8" val="0"/>
    </Action>

  </Task>

</TaskerData>
```

---

## 常见坑点与调试建议

**XML 格式陷阱：**

1. **If 动作必须用 ConditionList**：不要使用旧版的平面 `<Str>/<Int>` 格式。Operator codes 严格对应：数值操作（6-11）只用于数字比较，字符串用 0-5。
2. **参数类型必须匹配**：`<Int>` 用于整数和布尔，`<Str>` 用于字符串。Bundle 用 `<Bundle>`。
3. **XML 转义**：`&` → `&amp;`、`<` → `&lt;`、`>` → `&gt;`、`"` → `&quot;`
4. **匿名任务**：Profile 通过 `<mid0>` 关联的任务不能用 `<nme>` 命名。
5. **flags 值**：推荐统一使用 `40` 而非旧版 `8`。
6. **sr 标识连续**：Action 的 `sr="act0", act1, act2...` 必须从 0 开始连续编号。

**调试建议：**

1. 导入后在 Tasker 长按项目 → Export → 查看生成的 XML 确认结构正确。
2. 启用 Tasker 的 Run Log（主界面 → 右上角菜单 → 运行日志）来追踪执行状态。
3. 使用 `Flash` 动作（code=548）在关键节点打印变量值。
4. 确保 Tasker 已加入电池优化白名单,并授予必要权限。
5. 测试时优先单独执行 Task 再组合到 Profile 中触发。

---

## 参考资源

- [Tasker 官方网站](https://tasker.joaoapps.com)
- [Tasker 用户指南](https://tasker.joaoapps.com/userguide.html)
- [Tasker Pattern Matching 指南](https://tasker.joaoapps.com/userguide/en/matching.html)
- [Tasker 变量列表](https://tasker.joaoapps.com/userguide/en/variables.html)
- `datadef.xml` — 完整 Action/Condition 参数定义（本地元数据文件）
- `capabilities.xml` — 设备能力检测定义（本地元数据文件）
- `tasker_ai_system_instructions_2.txt` — AI 交互系统指令与 XML Schema 定义（本地元数据文件）
