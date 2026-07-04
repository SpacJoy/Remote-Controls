# Remote-Controls Code Wiki

> 本文档为 **Remote-Controls（远程控制工具）** 项目的结构化代码 Wiki，涵盖项目整体架构、模块职责、关键类与函数、依赖关系、数据流与运行方式。
> 项目目标：让 Windows 电脑接入智能家居，通过 MQTT 控制（开关、脚本、媒体/亮度/音量、热键等），支持配置热重载、托盘管理、EXE 打包与自启。

---

## 一、项目概览

| 项目 | 说明 |
| --- | --- |
| 仓库 | `Remote-Controls`（Windows 桌面工具） |
| 技术栈 | **C (Win32 + Paho MQTT C)** 作为核心运行程序 + **Python (Tkinter)** 作为配置界面 |
| 产物 | `RC-main.exe`（主程序）、`RC-tray.exe`（外部托盘）、`RC-GUI.exe`（配置界面）、Inno Setup 安装包 |
| 配置 | `config.toml`（TOML 格式，UTF-8，支持热重载） |
| 平台 | Windows（适配 Linux/macOS 为长期计划） |
| 语言 | 中 / 英（i18n 动态加载） |

**三大可执行程序协作模型：**

- `RC-main.exe`：常驻后台的 MQTT 客户端，订阅主题、解析指令、执行 Windows 动作。是整个系统的“核心执行器”。
- `RC-tray.exe`：独立系统托盘，提供菜单入口（打开 GUI / 启停主程序 / 检查权限 / 切换语言 / 在线版本检查）。
- `RC-GUI.exe`：Tkinter 配置界面，读写 `config.toml`，管理内置主题与自定义主题。

---

## 二、整体架构

### 2.1 架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                         智能家居平台 / MQTT Broker                      │
│              (bemfa 巴法云 / 自建 broker, 支持 TLS)                      │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ MQTT (pub/sub)
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         RC-main.exe (C/Win32)                          │
│  ┌──────────┐   ┌──────────────┐   ┌───────────────┐   ┌───────────┐  │
│  │ rc_mqtt  │──▶│  rc_router   │──▶│  rc_actions   │──▶│  Windows  │  │
│  │ (Paho)   │   │ (topic→动作)  │   │ (执行动作)     │   │  API/进程 │  │
│  └──────────┘   └──────┬───────┘   └───────────────┘   └───────────┘  │
│                        │ owns config                                 │
│  ┌─────────────────────┘                                             │
│  │ rc_config_watcher (ReadDirectoryChangesW, 零 CPU 热重载)            │
│  │ rc_main_tray (RC-tray.exe 未运行时的兜底最小托盘)                     │
│  │ rc_log / rc_json / toml / rc_notify / rc_utf (共享工具)             │
│  └──────────────────────────────────────────────────────────────────  │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ 读写 config.toml
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         RC-GUI.exe (Python/Tkinter)                    │
│  读写 config.toml │ 内置主题配置 │ 自定义主题(程序/服务/命令/热键) │        │
│  亮度高级设置 │ 热键录制器 │ 开机自启(schtasks) │ UAC 提权 │ i18n      │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                         RC-tray.exe (C/Win32)                          │
│  系统托盘菜单 │ 进程/互斥体检测主程序 │ 读取 admin_status.txt 判权限     │
│  启动/重启/关闭 RC-main │ 打开 RC-GUI │ WinHTTP 在线版本检查 │ i18n      │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 三程序协作约定

- **单实例**：`RC-main` 通过命名互斥体 `L"RC-main"` 防止重复启动。
- **权限状态文件**：`RC-main` 启动时写 `logs/admin_status.txt`（内容 `admin=1`/`admin=0`），`RC-tray` 读取该文件向用户提示主程序权限状态。
- **托盘去重**：`RC-main` 启动时延迟约 1s 检测 `RC-tray.exe` 是否已运行；若已运行则不创建内置兜底托盘，避免重复图标。
- **配置回退**：`RC-main` 配置异常时优先启动 `RC-GUI.exe` 让用户修复；若 GUI 不存在或启动失败则回退用 `notepad.exe` 打开 `config.toml`。

---

## 三、目录结构

```text
Remote-Controls/
├─ build.ps1                 # 顶层一键打包入口（转发到 installer/build_installer.ps1）
├─ build_main.ps1            # 构建 C 主程序 → bin/RC-main.exe
├─ build_tray.ps1            # 构建 C 托盘  → bin/RC-tray.exe
├─ setup_C_dev.ps1           # C 开发环境一键部署（MinGW/Paho/Inno Setup）
├─ setup_python_env.ps1      # Python 虚拟环境部署
├─ dome_config.toml          # 配置示例（TOML）
├─ requirements.txt          # Python 依赖
├─ src/
│  ├─ main/                  # RC-main 源码
│  │  ├─ main.c / main.rc
│  │  ├─ rc_mqtt.{c,h}       # MQTT 通信
│  │  ├─ rc_router.{c,h}     # 路由（topic→动作）
│  │  ├─ rc_actions.{c,h}    # Windows 动作执行
│  │  ├─ rc_config_watcher.{c,h}  # 配置热重载
│  │  ├─ rc_main_tray.{c,h}  # 内置兜底托盘
│  │  ├─ rc_log.{c,h}        # 日志
│  │  └─ rc_utf.{c,h}        # UTF-8/UTF-16 互转
│  ├─ tray/                  # RC-tray 源码
│  │  ├─ tray.{c,h} / tray*.rc
│  │  ├─ language.{c,h}      # 托盘 i18n
│  │  └─ log_messages.{c,h}  # 日志文案
│  ├─ python/GUI.py          # RC-GUI 配置界面（单文件）
│  ├─ rc_json.{c,h}          # 轻量 JSON + 极简 TOML 解析
│  ├─ toml.{c,h}             # TOML 解析（托盘侧使用）
│  ├─ rc_notify.{c,h}        # 气泡通知封装
│  └─ rc_utils.{c,h}         # 通用工具（提权/taskkill/进程检测，托盘侧使用）
├─ installer/                # 打包与版本管理（Inno Setup + PyInstaller）
├─ res/                      # 图标、图片、多语言文件（languages/*.json）
├─ md/                       # 详细文档与教程
├─ scripts/cleanup.py        # 辅助清理脚本
└─ .github/workflows/        # CI/CD（build-and-release.yml）
```

---

## 四、核心模块详解

### 4.1 RC-main 主程序（`src/main/`）

主程序是 GUI-less 的 Win32 应用（`wWinMain` 入口，`-mwindows -municode` 链接）。职责是常驻运行、订阅 MQTT、按指令执行 Windows 动作。

#### 4.1.1 [main.c](file:///d:/Code/Python/Remote-Controls/src/main/main.c) — 入口与编排

入口 `wWinMain`（[main.c#L296](file:///d:/Code/Python/Remote-Controls/src/main/main.c#L296)）执行顺序：

1. **单实例互斥**：`CreateMutexW(NULL, FALSE, L"RC-main")`，`ERROR_ALREADY_EXISTS` 时直接退出。
2. **定位目录**：`GetModuleDirW` 取 exe 所在目录，`SetCurrentDirectoryW` 固定工作目录（保证 `logs\`、`config.toml` 相对路径稳定）。
3. **初始化日志与权限状态**：`RC_LogInit` + `WriteAdminStatusFile`（写 `logs/admin_status.txt`，供托盘读取）。
4. **读取并解析配置**：`ReadFileUtf8Alloc(config.toml)` → `RC_JsonParseToml` → 校验 `broker/port/client_id` 等关键字段。
5. **创建路由**：`RC_RouterCreate(root)`，**Router 接管 `root` 所有权**（Destroy 时负责 `RC_JsonFree`）。
6. **启动配置监听**：`RC_ConfigWatcherCreate(tomlPath, on_config_changed, router)`。
7. **启动兜底托盘**：`RC_MainTrayStartDelayed`（仅当 `RC-tray.exe` 未运行）。
8. **进入 MQTT 主循环**：`RC_MqttRunLoop`（阻塞，直到用户退出或致命错误）。
9. **退出清理**：销毁 watcher / router，`free(tomlText)`，释放互斥体。

**关键内部函数：**
- `OpenGuiOrNotepadConfig`（[main.c#L242](file:///d:/Code/Python/Remote-Controls/src/main/main.c#L242)）：配置异常的统一回退策略（GUI → notepad）。
- `on_config_changed`（[main.c#L257](file:///d:/Code/Python/Remote-Controls/src/main/main.c#L257)）：配置变更回调，调用 `RC_RouterReloadConfig` 并发通知。

#### 4.1.2 [rc_mqtt.h](file:///d:/Code/Python/Remote-Controls/src/main/rc_mqtt.h) / rc_mqtt.c — MQTT 通信

基于 **Paho MQTT C 同步客户端**（`paho-mqtt3cs`，静态链接）。

**核心结构 `RC_MqttConfig`**（[rc_mqtt.h#L20](file:///d:/Code/Python/Remote-Controls/src/main/rc_mqtt.h#L20)）：

| 字段 | 说明 |
| --- | --- |
| `brokerHost` / `port` | broker 地址与端口（明文 TCP） |
| `useTls` / `tlsVerifyServerCert` / `tlsCaFile` | TLS 开关、证书校验、CA 文件 |
| `authMode` | `"private_key"`（私钥/客户端 ID 模式，巴法云等）/ `"username_password"` |
| `clientId` / `username` / `password` | 鉴权凭据 |
| `keepAliveSeconds` | 心跳（默认 60） |
| `reconnectMinSeconds` / `reconnectMaxSeconds` | 自动重连退避区间（默认 2~30） |

**核心函数：**
- `RC_MqttRunLoop(cfg, router, shouldStop)`（[rc_mqtt.h#L73](file:///d:/Code/Python/Remote-Controls/src/main/rc_mqtt.h#L73)）：阻塞主循环，内部完成 `connect → subscribe → recv publish → dispatch to router`，弱网下按退避策略自动重连；`shouldStop` 被置 `true` 或鉴权失败等不可恢复错误时返回。

#### 4.1.3 [rc_router.h](file:///d:/Code/Python/Remote-Controls/src/main/rc_router.h) / rc_router.c — 路由

Router 是配置驱动的事件分发中心，把“主题(topic) → 动作(action)”映射统一抽象为 `topic + on/off` 行为，并持有配置树。

**内部结构体**（[rc_router.c#L238](file:///d:/Code/Python/Remote-Controls/src/main/rc_router.c#L238)）：
- `struct RC_Router`：持有 `config`(owned)、`notifyEnabled`、`langEnglish`，以及 4 类自定义主题数组 `RcApp[]` / `RcCommand[]` / `RcServe[]` / `RcHotkey[]`，外加内置主题 topic 字符串与 `topics[]` 订阅列表。
- `RcApp`（程序/脚本）：`topic / onPath / offPath / offPreset(kill/none/custom)`。
- `RcCommand`（命令）：`topic / value / onValue / offValue / offPreset / window(show/hide) / valueMin / valueMax`，支持 `{value}` 占位与参数范围钳制。
- `RcServe`（服务）：`topic / serviceName / offPreset(stop/none/custom) / offValue`。
- `RcHotkey`（热键）：`topic / onType / onValue / offType / offValue / charDelayMs`。
- `RcCmdProc`：命令进程 PID 跟踪表（用于 off 时中断）。

**API：**
| 函数 | 职责 |
| --- | --- |
| `RC_RouterCreate(configRoot)` | 解析配置、构建主题数组、接管 config 所有权 |
| `RC_RouterDestroy(r)` | 释放资源（含 `RC_JsonFree`） |
| `RC_RouterGetTopics(r, &n)` | 返回需订阅的 topic 列表（指针由 Router 持有） |
| `RC_RouterHandle(r, topic, payload)` | **核心分发**：解析 payload 并执行动作 |
| `RC_RouterReloadConfig(r, path)` | 热重载配置（重新读盘+解析+重建内部状态） |
| `RC_RouterNotifyUtf8(r, title, msg)` | 主程序气泡通知（尊重 `notify` 开关） |
| `RC_RouterIsEnglish(r)` | 当前是否英文 |

**分发逻辑 `RC_RouterHandle`**（[rc_router.c#L2107](file:///d:/Code/Python/Remote-Controls/src/main/rc_router.c#L2107)）：

1. **payload 解析**：`base ∈ {on, off, pause}`；`on#<n>` / `off#<n>` 解析出 `value` 与 `hasValue`。非法 payload 直接告警并忽略。
2. **匹配顺序**（先自定义后内置，**首个匹配即返回**，保证一条消息只触发一个动作）：
   1. **Applications**：`on`→启动程序；`off`→自定义脚本或预设 `kill`（按路径结束进程）。
   2. **Commands**：执行 PowerShell（`window=hide` 后台 / `show` 调试），`{value}` 替换，越界钳制并告警；`off` 可 `interrupt`(CTRL_BREAK) / `kill` / 自定义。
   3. **Services**：`on`→`StartService`；`off`→预设 `stop` 或自定义命令。
   4. **Built-ins**：电脑(lock/shutdown/restart)、屏幕亮度、音量、睡眠、媒体（按 `*_action` 与 `*_delay` 执行）。
   5. **Hotkeys**：模拟键盘输入。

#### 4.1.4 [rc_actions.h](file:///d:/Code/Python/Remote-Controls/src/main/rc_actions.h) / rc_actions.c — 动作执行

把“字符串动作/参数”转换成实际 Windows 行为，是项目能力落地层。

| 函数 | 能力 |
| --- | --- |
| `RC_ActionPerformComputer(action, delay)` | lock / shutdown / restart / logoff / none（支持延时） |
| `RC_ActionPerformSleep(action)` | sleep / hibernate / display_off / display_on / lock |
| `RC_ActionSetDisplayPower(on)` | 广播 `WM_SYSCOMMAND/SC_MONITORPOWER` 控制显示器电源 |
| `RC_ActionMediaCommand(command)` | 媒体：播放/暂停/上一首/下一首，`on#xx` 映射三段操作 |
| `RC_ActionSetBrightnessDxva2Percent` | Dxva2 DDC/CI 物理显示器亮度（外接显示器） |
| `RC_ActionSetBrightnessWmiPercent` | WMI `WmiMonitorBrightnessMethods`（笔记本/部分台式机，常需管理员） |
| `RC_ActionSetBrightnessTwinkleTrayPercentUtf8` | 调用 Twinkle Tray CLI 设置亮度 |
| `RC_ActionSetVolumePercent` | Core Audio (MMDevice/EndpointVolume) 主音量 |
| `RC_ActionRunProgramUtf8` / `RC_ActionRunPowershellCommandUtf8[Ex]` | 启动程序 / PowerShell（可隐藏窗口、返回 PID） |
| `RC_ActionRunPowershellCommandWithOutput` | 执行并捕获 stdout |
| `RC_ActionTaskkillPidTree` / `TaskkillPid` / `TaskkillPidForce` / `TerminatePid` / `SendCtrlBreak[NoAttach]` | 多种进程结束方式 |
| `RC_ActionKillByPathUtf8` | 按可执行路径定位并结束进程 |
| `RC_ActionServiceStartUtf8` / `ServiceStopUtf8` | SCM 服务启停（`OpenSCManager`/`StartService`/`ControlService`） |
| `RC_ActionHotkey(actionType, actionValue, charDelayMs)` | 模拟键盘输入（支持组合键、逐字符、字符间延迟） |

#### 4.1.5 [rc_config_watcher.h](file:///d:/Code/Python/Remote-Controls/src/main/rc_config_watcher.h) — 配置热重载

- 使用 `ReadDirectoryChangesW` 在独立后台线程监控 `config.toml`，**零 CPU 占用**。
- 变更时触发回调 `RC_ConfigChangedCallback(configPath, userContext)` → `RC_RouterReloadConfig`。
- `RC_ConfigWatcherCreate` / `RC_ConfigWatcherDestroy` 管理生命周期。

#### 4.1.6 其他主程序模块

- [rc_main_tray.h](file:///d:/Code/Python/Remote-Controls/src/main/rc_main_tray.h)：`RC_MainTrayStartDelayed` — `RC-tray.exe` 未运行时的兜底最小托盘，从托盘选 Exit 时置 `*stopFlag=true` 通知 MQTT 循环退出。
- [rc_log.h](file:///d:/Code/Python/Remote-Controls/src/main/rc_log.h)：日志写 `logs/main.log`，`_SH_DENYNO` 共享访问，200KB 上限自动清空，支持 `RC_LogSetNotifyCallback` 把 WARN/ERROR 转 UI toast。
- [rc_utf.h](file:///d:/Code/Python/Remote-Controls/src/main/rc_utf.h)：`RC_Utf8ToWideAlloc` / `RC_WideToUtf8Alloc` / `RC_NormalizePathSlashes`。

### 4.2 RC-tray 托盘程序（`src/tray/`）

独立系统托盘，提供 UI 入口与进程/权限管理。

#### 4.2.1 [tray.h](file:///d:/Code/Python/Remote-Controls/src/tray/tray.h) / tray.c

**职责（见 [tray.c](file:///d:/Code/Python/Remote-Controls/src/tray/tray.c) 文件头注释）：**
1. 系统托盘图标 + 右键菜单：打开配置、检查主程序权限、启动/重启/关闭主程序、切换语言、退出。
2. 与主程序协作：进程名 + 互斥体（`MUTEX_NAME "RC-main"`）双重检测运行状态；读 `logs/admin_status.txt` 判权限。
3. 日志：写 `logs/tray.log`，共享访问，200KB 上限。
4. 在线版本检查：WinHTTP 请求 GitHub `releases/latest`，解析 `tag_name` 并提示。

**关键函数（[tray.h](file:///d:/Code/Python/Remote-Controls/src/tray/tray.h)）：**
- `InitApplication` / `IsUserAdmin` / `IsMainRunning` / `CreateTrayIcon` / `ShowNotificationDirect`
- `RunAsAdmin` / `StartMainProgram` / `CloseMainProgram` / `RestartMainProgram` / `OpenConfigGui`
- `CheckMainAdminStatus`（读 `logs/admin_status.txt`）/ `LogMessage`

**菜单项 ID**（[tray.c#L54](file:///d:/Code/Python/Remote-Controls/src/tray/tray.c#L54)）：`IDM_CONFIG` / `IDM_CHECK_ADMIN` / `IDM_START_MAIN` / `IDM_RESTART_MAIN` / `IDM_CLOSE_MAIN` / `IDM_EXIT` / `IDM_VERSION_INFO` / `IDM_TRAY_STATUS` / `IDM_SWITCH_LANG`。

#### 4.2.2 [language.h](file:///d:/Code/Python/Remote-Controls/src/tray/language.h) — 托盘 i18n

- `Language` 枚举（`TRAY_LANG_CHINESE` / `TRAY_LANG_ENGLISH`）。
- `LanguageStrings` 结构集中所有 UI 文案（应用标题、通知、菜单项、版本检查提示、提权提示等）。
- `DetectSystemLanguage` / `InitializeLanguage` / `GetLanguageStrings` / `SetLanguage` / `ToggleLanguage`。

#### 4.2.3 [log_messages.h](file:///d:/Code/Python/Remote-Controls/src/tray/log_messages.h) — 日志文案

集中托盘日志消息字符串，便于 i18n。

### 4.3 RC-GUI 配置界面（`src/python/GUI.py`）

**单文件 Tkinter 应用**（约 4000+ 行，模块级函数风格，无类定义）。打包命令见文件头注释（PyInstaller → `RC-GUI.exe`）。

#### 4.3.1 主要功能区

| 区块 | 关键函数 |
| --- | --- |
| **i18n 动态加载** | `_normalize_lang` / `_detect_default_lang` / `_get_available_languages` / `t(s)` / `register_lang_observer` / `apply_language_to_widgets` / `_apply_language_everywhere`（扫描 `res/languages/*.json`，内置中文无需文件） |
| **资源路径** | `resource_path`（兼容 PyInstaller `_MEIPASS`） |
| **提权与自启** | `get_administrator_privileges` / `run_as_admin` / `restart_self_as_admin` / `check_and_request_uac` / `startup_admin_check` / `set_auto_start`(schtasks) / `remove_auto_start` / `check_task` |
| **UI 渲染** | `_enable_dpi_awareness` / `_apply_font_readability_and_scaling` / `_apply_ttk_ui_fonts` / `center_window` / `_scaled_size` / `_get_scaling` |
| **热键录制器** | `open_keyboard_recorder`（独立 Toplevel，捕获按键组合） |
| **配置读写** | `load_config_file` / `flatten_config` / `unflatten_config` / `save_config_toml`（tomli_w 生成 + 逐项中英注释注入）/ `generate_config` |
| **自定义主题** | `load_custom_themes` / `rebuild_custom_theme_tree` / `modify_custom_theme` / `add_custom_theme` / `delete_theme` / `refresh_custom_themes` |
| **详情/内置设置** | `show_detail_window` / `open_builtin_settings` / `on_auth_mode_change` |
| **测试与辅助** | `test_command_in_powershell` / `_run_capture_text` / `_is_hibernate_enabled_from_powercfg_output` / `sleep` / `_resolve_twinkle_tray_path_for_gui` |

#### 4.3.2 配置加载流程

1. `load_config_file()`（[GUI.py#L3878](file:///d:/Code/Python/Remote-Controls/src/python/GUI.py#L3878)）：以二进制读 `config.toml` → `tomllib.load` → `flatten_config` 拍平为 `{key: value}` 字典赋给全局 `config`。
2. 全局 `config: Dict[str, Any] = {}`（[GUI.py#L3876](file:///d:/Code/Python/Remote-Controls/src/python/GUI.py#L3876)），所有 UI 控件双向绑定。
3. 保存时 `generate_config` 收集控件值 → `unflatten_config` 还原嵌套 → `save_config_toml` 写盘并注入双语注释。
4. **热重载联动**：GUI 保存 `config.toml` 后，`RC-main` 的 `rc_config_watcher` 自动触发 `RC_RouterReloadConfig`，无需重启。

### 4.4 共享组件（`src/`）

| 文件 | 职责 |
| --- | --- |
| [rc_json.h](file:///d:/Code/Python/Remote-Controls/src/rc_json.h) | 轻量 JSON 解析/构建（`RC_JsonParse` / `RC_JsonParseToml` / `RC_JsonObjectGet` / `RC_JsonPrintPretty`）。`RC_JsonParseToml` 为极简 TOML 键值对解析，扁平化为 Object，**主程序用它读 config.toml**。 |
| [toml.h](file:///d:/Code/Python/Remote-Controls/src/toml.h) | TOML 解析（托盘侧读取配置使用） |
| [rc_notify.h](file:///d:/Code/Python/Remote-Controls/src/rc_notify.h) | 气泡通知封装 `RC_NotifyShowUtf8` / `RC_NotifyShowW`（基于 `Shell_NotifyIconW` + `NIF_INFO`） |
| [rc_utils.h](file:///d:/Code/Python/Remote-Controls/src/rc_utils.h) | 通用工具库（**托盘侧使用**）：`RC_IsUserAdmin` / `RC_AdminRunCmd` / `RC_AdminTaskkill` / `RC_IsProcessRunning` / `RC_RunAsAdmin` / `RC_StartProgram` / `RC_CloseMainProgram` / `RC_RestartMainProgram` / `RC_CheckMainAdminStatus`。所有 `const char*` 按 UTF-8 解释。 |

> **注意**：`rc_json.c` / `toml.c` / `rc_notify.c` / `rc_utils.c` 被 main 与 tray **分别编译**为不同 `.o`（如 `rc_json_main.o` / `rc_json_tray.o`），见构建脚本。

---

## 五、关键类与函数速查

### 5.1 C 侧核心 API

#### Router（路由）
```c
RC_Router *RC_RouterCreate(RC_Json *configRoot);          // 接管 config 所有权
void       RC_RouterDestroy(RC_Router *r);
const char *const *RC_RouterGetTopics(const RC_Router *r, int *outCount);
void       RC_RouterHandle(RC_Router *r, const char *topicUtf8, const char *payloadUtf8);  // 核心分发
bool       RC_RouterReloadConfig(RC_Router *r, const wchar_t *configPath);                 // 热重载
void       RC_RouterNotifyUtf8(RC_Router *r, const char *titleUtf8, const char *messageUtf8);
bool       RC_RouterIsEnglish(const RC_Router *r);
```

#### MQTT
```c
typedef struct RC_MqttConfig {
    const char *brokerHost, *authMode, *clientId, *username, *password, *tlsCaFile;
    int port, keepAliveSeconds, reconnectMinSeconds, reconnectMaxSeconds;
    bool useTls, tlsVerifyServerCert;
} RC_MqttConfig;

void RC_MqttRunLoop(const RC_MqttConfig *cfg, RC_Router *router, volatile bool *shouldStop);
```

#### Actions（动作执行，见 [rc_actions.h](file:///d:/Code/Python/Remote-Controls/src/main/rc_actions.h)）
覆盖：电源/会话、睡眠、显示器、媒体、亮度(WMI/Dxva2/Twinkle Tray)、音量(Core Audio)、程序/PowerShell、进程结束(taskkill/TerminateProcess/CTRL_BREAK)、服务(SCM)、热键模拟。

#### Config Watcher
```c
typedef void (*RC_ConfigChangedCallback)(const wchar_t *configPath, void *userContext);
RC_ConfigWatcher *RC_ConfigWatcherCreate(const wchar_t *configPath, RC_ConfigChangedCallback cb, void *ctx);
void              RC_ConfigWatcherDestroy(RC_ConfigWatcher *w);
```

#### JSON / TOML
```c
RC_Json *RC_JsonParse(const char *text, RC_JsonError *err);
RC_Json *RC_JsonParseToml(const char *text, RC_JsonError *err);   // 主程序读 config.toml
RC_Json *RC_JsonObjectGet(const RC_Json *obj, const char *key);
const char *RC_JsonGetString(const RC_Json *node);
int  RC_JsonGetInt(const RC_Json *node, int defVal);
void RC_JsonFree(RC_Json *node);
```

### 5.2 Python 侧关键函数

| 函数 | 位置 | 作用 |
| --- | --- | --- |
| `load_config_file()` | [GUI.py#L3878](file:///d:/Code/Python/Remote-Controls/src/python/GUI.py#L3878) | 读 `config.toml` → `flatten_config` → 全局 `config` |
| `flatten_config` / `unflatten_config` | [GUI.py#L3282](file:///d:/Code/Python/Remote-Controls/src/python/GUI.py#L3282) / [GUI.py#L3202](file:///d:/Code/Python/Remote-Controls/src/python/GUI.py#L3202) | TOML 嵌套 ↔ 拍平字典 |
| `save_config_toml(nested, path)` | [GUI.py#L3296](file:///d:/Code/Python/Remote-Controls/src/python/GUI.py#L3296) | tomli_w 生成 + 逐项双语注释注入 |
| `generate_config()` | [GUI.py#L3479](file:///d:/Code/Python/Remote-Controls/src/python/GUI.py#L3479) | 收集 UI 控件 → 嵌套配置 → 保存 |
| `t(s)` | [GUI.py#L152](file:///d:/Code/Python/Remote-Controls/src/python/GUI.py#L152) | i18n 翻译入口 |
| `open_keyboard_recorder(parent, var)` | [GUI.py#L746](file:///d:/Code/Python/Remote-Controls/src/python/GUI.py#L746) | 热键录制 Toplevel |
| `set_auto_start` / `remove_auto_start` / `check_task` | [GUI.py#L895](file:///d:/Code/Python/Remote-Controls/src/python/GUI.py#L895) / [GUI.py#L1071](file:///d:/Code/Python/Remote-Controls/src/python/GUI.py#L1071) / [GUI.py#L1101](file:///d:/Code/Python/Remote-Controls/src/python/GUI.py#L1101) | schtasks 开机自启管理 |
| `restart_self_as_admin` | [GUI.py#L440](file:///d:/Code/Python/Remote-Controls/src/python/GUI.py#L440) | UAC 提权重启自身 |

---

## 六、配置文件说明（`config.toml`）

TOML 格式，UTF-8，由 `RC-GUI` 维护，支持手动编辑。完整示例见 [dome_config.toml](file:///d:/Code/Python/Remote-Controls/dome_config.toml)。

| Section | 关键字段 | 说明 |
| --- | --- | --- |
| `[mqtt]` | `broker` / `port` / `auth_mode` / `client_id` / `mqtt_username` / `mqtt_password` / `mqtt_tls` / `mqtt_tls_verify` / `mqtt_tls_ca_file` | MQTT 连接与鉴权（`auth_mode`: `private_key`/`username`） |
| `[settings]` | `test` / `notify` / `language` | 测试模式 / 通知开关 / 界面语言(zh/en) |
| `[built_in_themes]` | `Computer` / `screen` / `volume` / `sleep` / `media` + 各自 `_checked`；`sleep_on_action` / `sleep_off_action` / `sleep_on_delay` / `sleep_off_delay` | 内置主题 topic 与启用开关、睡眠动作/延时 |
| `[brightness]` | `brightness_mode`(wmi/dxva2/twinkle_tray/custom) / `twinkle_tray_path` / `twinkle_tray_target_mode` / `twinkle_tray_target_value` / `twinkle_tray_overlay` / `brightness_custom_list` / `brightness_custom_strategy`(all/success) | 亮度控制模式与高级策略 |
| `[other]` | `computer_on_action` / `computer_off_action` / `computer_on_delay` / `computer_off_delay` / `wmi_target` / `wmi_brightness_min/max` / `dxva2_target` / `dxva2_brightness_min/max` / `volume_min` / `volume_max` | 电脑动作、亮度/音量上下限 |
| `[custom_themes.applications]` | `applicationN` / `applicationN_name` / `applicationN_checked` / `applicationN_directoryN` / `applicationN_on_value` / `applicationN_off_value` / `applicationN_off_preset`(kill/none/custom) | 程序/脚本主题 |
| `[custom_themes.services]` | `serveN` / `serveN_name` / `serveN_checked` / `serveN_value` / `serveN_on_value` / `serveN_off_value` / `serveN_off_preset`(stop/none/custom) | Windows 服务主题（需管理员） |
| `[custom_themes.commands]` | `commandN` / `commandN_name` / `commandN_checked` / `commandN_value` / `commandN_on_value` / `commandN_off_value` / `commandN_off_preset` / `commandN_window`(show/hide) / `commandN_value_min/max` | PowerShell 命令主题（支持 `{value}` 占位） |
| `[custom_themes.hotkeys]` | `hotkeyN` / `hotkeyN_name` / `hotkeyN_checked` / `hotkeyN_on_type` / `hotkeyN_on_value` / `hotkeyN_off_type` / `hotkeyN_off_value` / `hotkeyN_char_delay_ms` | 热键主题（keyboard/none） |

**指令约定：**
- `on` / `off` / `pause`：开关/暂停。
- `on#<n>` / `off#<n>`：带数值参数（默认 0-100，命令主题可用 `commandN_value_min/max` 自定义）；越界由主程序钳制并告警。
- 命令主题支持 `{value}` 占位符由 `on#`/`off#` 注入。

---

## 七、数据流与运行时序

### 7.1 主程序启动时序

```
wWinMain
  ├─ CreateMutexW("RC-main")          # 单实例
  ├─ GetModuleDirW + SetCurrentDirectoryW
  ├─ RC_LogInit + WriteAdminStatusFile  # 写 logs/admin_status.txt
  ├─ 读 config.toml (UTF-8)
  ├─ RC_JsonParseToml → 校验 broker/port/client_id
  ├─ RC_RouterCreate(root)            # 接管 config 所有权，构建主题数组
  ├─ RC_ConfigWatcherCreate           # 后台线程监听 config.toml
  ├─ RC_MainTrayStartDelayed          # 兜底托盘（仅 RC-tray.exe 未运行）
  └─ RC_MqttRunLoop (阻塞)
        └─ connect → subscribe(topics) → recv → RC_RouterHandle → RC_Action*
                     └─ 断线按 2~30s 退避重连
```

### 7.2 消息处理时序

```
MQTT payload (topic, "on#55")
  └─ RC_MqttRunLoop
       └─ RC_RouterHandle(router, topic, "on#55")
            ├─ parse_percent_payload_strict → base="on", value=55, hasValue=true
            ├─ 匹配 Applications  → RC_ActionRunProgramUtf8 / RC_ActionKillByPathUtf8
            ├─ 匹配 Commands      → RC_ActionRunPowershellCommandUtf8Ex ({value} 替换, 范围钳制)
            ├─ 匹配 Services      → RC_ActionServiceStartUtf8 / ServiceStopUtf8
            ├─ 匹配 Built-ins     → RC_ActionPerformComputer / SetBrightnessWmiPercent / SetVolumePercent / ...
            └─ 匹配 Hotkeys       → RC_ActionHotkey
            （首个匹配即 return）
```

### 7.3 配置热重载时序

```
RC-GUI 保存 config.toml
  └─ ReadDirectoryChangesW (rc_config_watcher 后台线程) 触发
       └─ on_config_changed
            └─ RC_RouterReloadConfig(router, path)
                 ├─ 重新读盘 + RC_JsonParseToml
                 ├─ 重建 topic 列表 / 主题数组
                 └─ RC_RouterNotifyUtf8("配置已成功重载")
  （MQTT 连接不中断，主题订阅由主循环下一轮自然更新）
```

### 7.4 托盘与主程序协作

```
RC-tray.exe
  ├─ IsMainRunning()  # 进程名 + 互斥体 "RC-main" 双重检测
  ├─ CheckMainAdminStatus()  # 读 logs/admin_status.txt
  ├─ StartMainProgram / RestartMainProgram / CloseMainProgram  # taskkill / ShellExecute
  └─ OpenConfigGui()  # 启动 RC-GUI.exe
```

---

## 八、依赖关系

### 8.1 C 侧依赖

**构建工具链**（[setup_C_dev.ps1](file:///d:/Code/Python/Remote-Controls/setup_C_dev.ps1) 自动部署）：
- MinGW-w64（`gcc` / `windres`），自动探测 `C:\msys64\mingw64`、`ucrt64`、`mingw32`。

**第三方库**：
- **Paho MQTT C**（`paho-mqtt3cs`，强制使用，静态链接）：通过 `-PahoRoot` 或环境变量 `PAHO_MQTT_C_ROOT` 指定，构建脚本自动探测 MSYS2 前缀。
- **OpenSSL**（`libssl` / `libcrypto`，静态链接）：Paho SSL 依赖，消除 `libcrypto-3-x64.dll` / `libssl-3-x64.dll` 运行时依赖。
- **Inno Setup 6**：生成安装包。

**Win32 系统库**（见 [build_main.ps1#L288](file:///d:/Code/Python/Remote-Controls/build_main.ps1#L288)）：
- 主程序：`shlwapi shell32 user32 ole32 oleaut32 uuid wbemuuid dxva2 ws2_32 crypt32 rpcrt4 advapi32`
- 托盘：`psapi shlwapi shell32 gdi32 user32 advapi32 comctl32 winhttp`

### 8.2 Python 侧依赖（[requirements.txt](file:///d:/Code/Python/Remote-Controls/requirements.txt)）

| 包 | 用途 |
| --- | --- |
| `psutil>=7.0.0` | 进程检测/管理 |
| `pywin32>=310` | Windows API（`win32com.client`，服务/WMI 等） |
| `wmi>=1.5.1` | WMI 亮度查询 |
| `tomli>=2.2.1; python_version<"3.11"` | TOML 读取（Python <3.11 回退） |
| `tomli_w>=1.2.0` | TOML 写入 |
| `setuptools>=80.1.0` | 打包基础 |
| `pyinstaller>=6.13.0` | 打包为 `RC-GUI.exe` |

标准库：`tkinter` / `ctypes` / `subprocess` / `locale` / `shutil` / `re` / `json` 等。Python 推荐 3.12.10+。

### 8.3 模块间编译依赖

```
RC-main.exe  ← main.c, rc_mqtt, rc_router, rc_actions, rc_config_watcher,
                rc_main_tray, rc_log, rc_utf, rc_json(→rc_json_main.o),
                toml(→toml_main.o), rc_notify(→rc_notify_main.o), main.rc
RC-tray.exe  ← tray.c, language, log_messages, rc_utils,
                rc_json(→rc_json_tray.o), toml(→toml_tray.o),
                rc_notify(→rc_notify_tray.o), tray_unified.rc
```

> 共享源文件 `rc_json.c` / `toml.c` / `rc_notify.c` 在两个产物中各编译一份（不同 `.o` 名），避免符号冲突。

---

## 九、构建与运行

### 9.1 开发环境部署（推荐）

```powershell
# Python 环境（扫描多版本解释器，创建 .venv 并装依赖）
.\setup_python_env.ps1

# C 环境（管理员权限；winget 装 MSYS2/MinGW + Paho MQTT C + Inno Setup 6）
.\setup_C_dev.ps1
```

### 9.2 一键构建

```powershell
# 顶层入口，转发到 installer/build_installer.ps1
.\build.ps1                 # 交互式输入版本号
.\build.ps1 x.y.z -NoPause  # 自动化：指定版本，跳过暂停
```

**产物：**
- 独立程序：`installer/dist/*.exe`（`RC-main.exe` / `RC-tray.exe` / `RC-GUI.exe`）
- 安装包：`installer/dist/installer/Remote-Controls-Installer-*.exe`
- 构建日志：`logs/`（如 `build_main.log`）

### 9.3 分步构建

| 脚本 | 产物 | 关键步骤 |
| --- | --- | --- |
| [build_main.ps1](file:///d:/Code/Python/Remote-Controls/build_main.ps1) | `bin/RC-main.exe` | `windres` 编译 `main.rc` → `gcc` 编译各 `.c` → 链接（`-mwindows -municode`，Paho 静态链接 + OpenSSL 静态）。版本宏 `-DRC_MAIN_VERSION=Vx.y.z` 经 stringize 转字符串。 |
| [build_tray.ps1](file:///d:/Code/Python/Remote-Controls/build_tray.ps1) | `bin/RC-tray.exe` | `windres` 编译 `tray_unified.rc` → `gcc` 编译 → 链接。版本宏 `-DRC_TRAY_VERSION=Vx.y.z`。 |
| PyInstaller | `RC-GUI.exe` | `pyinstaller RC-GUI.spec --noconfirm`（或命令行，见 [GUI.py](file:///d:/Code/Python/Remote-Controls/src/python/GUI.py) 文件头注释） |
| [installer/build_installer.ps1](file:///d:/Code/Python/Remote-Controls/installer/build_installer.ps1) | 安装包 | 调用上述构建 + Inno Setup（`Remote-Controls.iss`）+ 版本注入（`update_version.py`） |

### 9.4 运行

- 日常使用：安装后运行 `RC-tray.exe`（托盘入口）→ 菜单启动主程序 / 打开配置界面。
- 调试：直接运行 `bin/RC-main.exe`（若无 `RC-tray.exe`，主程序会启用内置兜底托盘）。
- 配置：运行 `RC-GUI.exe` 编辑 `config.toml`，保存后主程序自动热重载。

### 9.5 常见运行约束

- `config.toml` 必须存在且格式合法，否则主程序弹窗并回退到 GUI/记事本。
- 至少启用一个主题（除非 `test=1`）。
- 服务控制、WMI 亮度等动作需管理员权限；休眠需 `powercfg /hibernate on`。
- PowerShell 脚本策略：`Set-ExecutionPolicy RemoteSigned`。
- MQTT 8883/TLS：`mqtt_tls=1` 启用 `ssl://`；证书校验需 `mqtt_tls_verify=1` + `mqtt_tls_ca_file`。

---

## 十、CI/CD（GitHub Actions）

工作流：[.github/workflows/build-and-release.yml](file:///d:/Code/Python/Remote-Controls/.github/workflows/build-and-release.yml)

**触发条件：**
- 推送 `V*` 开头 tag（如 `V3.0.0`）：构建 + 发布 Release。
- `dev` 分支推送：自动递增版本号（最新 tag + `0.0.0.1`）并构建（Pre-release）。
- 手动触发（`workflow_dispatch`）：仅 `main` 分支可发布，`dev` 仅构建。

**流程：**
1. `prepare` 作业解析版本号（支持 `V3.0.0-test` 形式）。
2. 配置 MSYS2/MinGW 与 Paho MQTT C 环境。
3. 安装 Inno Setup 6 并注入版本号（`update_version.py`）。
4. 编译 C 主程序与托盘（`build_main.ps1` / `build_tray.ps1`）。
5. PyInstaller 打包 Python GUI。
6. Inno Setup 生成安装包。
7. 自动创建 GitHub Release / Pre-release 并上传产物。

**并发控制：`concurrency` 按 `workflow + ref` 分组，`cancel-in-progress: true`。**

> 另有 CI 检查工作流（`ci.yml`）：`main` 分支推送/PR 触发，安装 Python 依赖 + `compileall` 静态检查 + 关键模块导入测试。详见 [.github/workflows/README.md](file:///d:/Code/Python/Remote-Controls/.github/workflows/README.md)。

---

## 十一、关键设计要点小结

1. **C/Python 混合架构**：性能敏感与常驻部分用 C（低内存、无运行时依赖），易变的配置 UI 用 Python（Tkinter 开发效率高）。三者通过 `config.toml` 与 `admin_status.txt` 文件解耦协作。
2. **配置热重载**：`ReadDirectoryChangesW` 零 CPU 监听 + Router 原子重建，编辑保存即生效，无需重启主程序。
3. **单消息单动作**：`RC_RouterHandle` 首个匹配即返回，避免一条消息触发多个动作。
4. **静态链接**：Paho + OpenSSL 静态链接，`RC-main.exe` 单文件无外部 DLL 依赖（便于分发）。
5. **权限解耦**：主程序把 admin 状态写入文件，托盘读取提示，避免跨进程权限查询复杂度。
6. **兜底设计**：`RC-tray.exe` 缺失时主程序自带最小托盘；`RC-GUI.exe` 缺失时回退记事本；`config.toml` 缺失时自动创建。
7. **i18n 双轨**：C 侧（托盘）用编译期 `LanguageStrings` 表 + 运行时切换；Python 侧（GUI）用 `res/languages/*.json` 动态加载 + 内置中文。
8. **参数化命令**：`on#n`/`off#n` + `{value}` 占位 + 可配置范围 + 越界钳制，兼顾灵活性与安全性。

---

## 参考文档

- [README.md](file:///d:/Code/Python/Remote-Controls/README.md) — 项目总览与使用教程
- [md/Detailed-introduction.md](file:///d:/Code/Python/Remote-Controls/md/Detailed-introduction.md) — 配置字段详细说明
- [md/MQTT_AUTH_GUIDE_V2.md](file:///d:/Code/Python/Remote-Controls/md/MQTT_AUTH_GUIDE_V2.md) — MQTT 认证说明
- [CHANGELOG.md](file:///d:/Code/Python/Remote-Controls/CHANGELOG.md) — 更新日志
- [CONTRIBUTING.md](file:///d:/Code/Python/Remote-Controls/CONTRIBUTING.md) — 贡献指南
- [installer/VERSION_GUIDE.md](file:///d:/Code/Python/Remote-Controls/installer/VERSION_GUIDE.md) — 版本管理说明
