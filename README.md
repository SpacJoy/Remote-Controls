# 远程控制工具（RC-remote-controls）

让 Windows 电脑接入智能家居：通过 MQTT 控制开关、脚本、媒体/亮度/音量、热键等，一键配置、托盘管理、支持 EXE 打包与自启。

[使用教程](#使用教程) • [图文教程](https://blog.spacjoy.top/posts/remote-control-tutorial) • [项目结构](#项目结构) • [更新日志](CHANGELOG.md) • [贡献指南](CONTRIBUTING.md)

提醒与声明：仅供学习交流，请勿用于非法用途。

## 未来计划

-[] 配置文件迁移为TOML（支持注释和增加可读性）  
-[] 项目更名为更简洁合适的名字（可任意方式投稿）

## 特性一览

- MQTT 控制：支持“私钥客户端ID（巴法云等）”与“用户名/密码”两种认证
- 设备动作：锁屏/关机/重启；亮度（支持 WMI、Dxva2 DDC/CI、Twinkle Tray 多种模式）；音量与媒体控制；热键发送
- 自定义主题：支持程序/脚本、服务、命令、热键四类，开关动作可分别配置
- 亮度高级设置：独立配置窗口，支持自定义控制顺序、策略（同时执行/成功即止）与单显示器目标控制
- 参数化命令：on#/off# 默认 0-100（可通过 `commandN_value_min/value_max` 自定义）+ `{value}` 占位符，GUI 测试会询问参数
- 托盘管理：一键启动/重启/关闭主程序，显示权限与运行模式
- 打包与发布：一键构建（github actions），安装器自动注入版本
- Windows Toast 通知，可开关；异常保护与弱网自动重连

## 使用教程

- MQTT 认证说明与示例：`md/MQTT_AUTH_GUIDE_V2.md`
- 配置文件字段说明（`config.json`）：`md/Detailed-introduction.md`
- 巴法云接入与小爱同学（官方文档）：<https://cloud.bemfa.com/docs/src/speaker_mi.html>
- 主题速查（内置 + 自定义）：
  - 电脑（开关）：lock/restart/shutdown 等，支持延时
  - 屏幕（灯）：on=100，off=0，`on#数字` 设亮度；支持通过“高级亮度设置”切换 WMI、Dxva2、Twinkle Tray 模式，适配外接显示器与 DDC/CI 控制。
  - 音量（窗帘）：on=100，off=0，`on#数字` 设音量；pause=静音
  - 媒体（窗帘）：上一曲/下一曲/播放暂停；`on#百分比` 映射三段操作
  - 睡眠（开关）：sleep/hibernate/display_off/display_on/lock
  - 自定义：脚本/程序/服务/命令/热键（支持 {down}/{up}、逐字符、录制器）

### 自定义主题详解

- 程序或脚本：填写“打开(on)”路径或命令，关闭动作可选预设（强制结束、忽略）或自定义脚本，双按钮分别支持选择文件。
- 服务(需管理员权限)：“打开(on)”写入服务名；关闭预设默认停止服务，也可改为忽略，自定义内容需确保具有管理员权限。
- 命令：默认显示 PowerShell 测试按钮；打开与关闭各自支持预设，中断(`CTRL+BREAK`)为默认关闭方式，切换到自定义时可测试代码片段。支持 `{value}` 占位符，命令可由 `on#/off#数字` 注入参数；范围默认 0-100，可在 `config.json` 中用 `commandN_value_min/value_max` 自定义；越界时主程序会告警并钳制到范围内，GUI 测试会提示范围并要求输入合法值。
- 按键(Hotkey)：可录制或手动输入键盘组合，支持设置按键类型（不执行/键盘组合）和字符间隔，保存时会提示全角字符风险。

## [图文教程（宝宝巴士版）](https://blog.spacjoy.top/posts/remote-control-tutorial)

## [详细教程](https://github.com/SpacJoy/Remote-Controls/blob/main/md/Detailed-introduction.md)

## 项目结构

```text
Remote-Controls/
├─ build.ps1            # 顶层一键打包入口（调用 installer/ 下脚本）
├─ build_main.ps1       # 构建 C 版主程序（输出 bin/RC-main.exe）
├─ build_tray.ps1       # 构建 C 版托盘（输出 bin/RC-tray.exe）
├─ setup_python_env.ps1 # Python 虚拟环境部署脚本（支持多版本选择）
├─ setup_C_dev.ps1      # C 语言开发环境一键部署（MinGW/Paho/Inno Setup）
├─ dome_config.json     # 配置示例
├─ installer/           # 构建、版本管理与安装包脚本
│  ├─ build_installer.ps1 # PyInstaller 打包与 Inno Setup 逻辑
│  └─ update_version.py   # 版本号同步工具
├─ res/                 # 图标、图片等静态资源
├─ src/
│  ├─ main/             # C 版主程序源码（核心逻辑、MQTT、指令转发）
│  ├─ tray/             # C 版托盘源码（Win32 托盘、菜单、进程管理）
│  ├─ python/           # Python 源码（当前主要为配置 GUI）
│  └─ *.c/h             # 跨模块共用组件（JSON 解析、通知等）
└─ scripts/             # 辅助工具脚本
```

## 安装与构建

项目采用 C (Win32) 作为核心运行程序，Python 作为配置界面。

### 1. 开发环境部署 (推荐)

我们提供了自动化脚本，帮助您快速配置所需环境：

- **Python 环境**：运行 `.\setup_python_env.ps1`。它会扫描系统中的 Python 解释器，由您选择一个版本来创建 `.venv` 并自动安装 `requirements.txt` 中的依赖。
- **C 语言环境**：以管理员权限运行 `.\setup_C_dev.ps1`。它会检查并尝试通过 `winget` 安装 MSYS2/MinGW、Paho MQTT C 库以及 Inno Setup 6。

### 2. 手动配置

- **Python**: 3.12.10+。手动创建虚拟环境并安装依赖。
- **C 工具链**: 需要 MinGW-w64。确保 `gcc` 和 `windres` 在系统 PATH 中。
- **MQTT 库**: 依赖 [Paho MQTT C](https://github.com/eclipse/paho.mqtt.c)。需设置环境变量 `PAHO_MQTT_C_ROOT` 指向其安装目录。
- **安装包工具**: Inno Setup 6。

### 3. 一键构建

运行根目录下的 `build.ps1` 即可完成全流程构建：

```powershell
# 交互式运行：手动输入版本号并查看过程
.\build.ps1

# 自动化构建：指定版本并跳过暂停
.\build.ps1 3.0.2.1 -NoPause
```

- **产物位置**：
    - 独立程序：`installer/dist/*.exe`
    - 安装包：`installer/dist/installer/Remote-Controls-Installer-*.exe`
- **构建日志**：详细日志保存在 `logs/` 目录下（如 `build_main.log`）。

## GitHub CI/CD

项目集成了完善的自动化流水线，确保代码质量与发布效率：

- **代码检查 (CI)**：[ci.yml](file:///d:/Code/Python/Remote-Controls/.github/workflows/ci.yml)
    - 触发条件：`main` 分支推送或 Pull Request。
    - 操作：安装 Python 依赖、静态语法检查 (`compileall`)、关键模块导入测试。
- **构建与发布 (Release)**：[build-and-release.yml](file:///d:/Code/Python/Remote-Controls/.github/workflows/build-and-release.yml)
    - 触发条件：推送以 `V` 开头的标签（如 `V3.0.2`）、手动触发，或 **`dev` 分支推送（自动递增版本号）**。
    - 操作：
        1. 自动配置 MSYS2/MinGW 和 Paho MQTT C 环境。
        2. 安装 Inno Setup 并注入版本号（`dev` 分支自动在最新标签基础上加 `0.0.0.1`）。
        3. 编译 C 语言主程序与托盘。
        4. 使用 PyInstaller 打包 Python GUI。
        5. 生成最终安装包并自动创建 GitHub Release / Pre-release 上传产物。

更多工作流细节请参考 [.github/workflows/README.md](file:///d:/Code/Python/Remote-Controls/.github/workflows/README.md)。

更多细节见 `installer/` 目录与 `CHANGELOG.md`。

## 常见问题（精简）

- MQTT 连接失败：检查地址/端口/认证，程序会在弱网下自动重连
- MQTT 8883/TLS：默认关闭 TLS。可在 `config.json` 设置 `mqtt_tls=1` 启用 `ssl://`；若需要校验证书，可设置 `mqtt_tls_verify=1` 并指定 `mqtt_tls_ca_file`（CA 证书文件路径）。注意：启用 TLS 需要构建时链接 Paho SSL 库（如 `paho-mqtt3cs`）。
- 休眠不可用：以管理员运行并启用休眠 `powercfg /hibernate on`
- 托盘找不到主程序：以管理员运行托盘；或直接运行 `RC-main.exe`
- 脚本执行策略：PowerShell 需允许脚本 `Set-ExecutionPolicy RemoteSigned`
- 打包异常：优先使用 `build.ps1`（PyInstaller）

---

- 更新日志：`CHANGELOG.md`
- 贡献指南：`CONTRIBUTING.md`
- 发布页（下载）：<https://github.com/SpacJoy/Remote-Controls/releases>
- 反馈与支持：提交 Issue 或邮件 `mc_chen6019@qq.com`
