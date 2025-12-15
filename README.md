# 远程控制工具（RC-remote-controls）

让 Windows 电脑接入智能家居：通过 MQTT 控制开关、脚本、媒体/亮度/音量、热键等，一键配置、托盘管理、支持 EXE 打包与自启。

[快速开始](#快速开始) • [使用教程](#使用教程) • [图文教程](https://blog.spacjoy.top/posts/remote-control-tutorial) • [项目结构](#项目结构) • [更新日志](CHANGELOG.md) • [贡献指南](CONTRIBUTING.md)

提醒与声明：仅供学习交流，请勿用于非法用途。

## 特性一览

- MQTT 控制：支持“私钥客户端ID（巴法云等）”与“用户名/密码”两种认证
- 设备动作：锁屏/关机/重启；亮度（系统接口或 Twinkle Tray）；音量与媒体控制；热键发送
- 自定义主题：支持程序/脚本、服务、命令、热键四类，开关动作可分别配置
- 参数化命令：on#/off# 默认 0-100（可通过 `commandN_value_min/value_max` 自定义）+ `{value}` 占位符，GUI 测试会询问参数
- 托盘管理：一键启动/重启/关闭主程序，显示权限与运行模式
- 打包与发布：一键构建（github actions），安装器自动注入版本
- Windows Toast 通知，可开关；异常保护与弱网自动重连

## 快速开始

1. 下载或构建

- 到 Releases 下载 `RC-main/GUI/tray` 可执行文件 **或 安装包**：`Remote-Controls-Installer-x.x.x.exe` 或在本地构建：

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
./build.ps1
```

2. 配置 MQTT 与主题

- 运行 `RC-GUI.exe`，填写 MQTT（密钥或用户名/密码、服务器、端口），保存生成 `config.json`
- 在 GUI 启用需要的主题（内置 + 自定义）

3. 运行与控制

- 运行 `RC-tray.exe`（推荐）或 `RC-main.exe`；托盘可管理主程序并显示状态
- 需要接入小爱/米家：参考下方“教程”绑定巴法云账号并同步设备

## 使用教程

- MQTT 认证说明与示例：`md/MQTT_AUTH_GUIDE_V2.md`
- 巴法云接入与小爱同学（官方文档）：<https://cloud.bemfa.com/docs/src/speaker_mi.html>
- 主题速查（内置 + 自定义）：
  - 电脑（开关）：lock/restart/shutdown 等，支持延时
  - 屏幕（灯）：on=100，off=0，`on#数字` 设亮度；在“更多”中可切换 Twinkle Tray 命令行模式以适配外接显示器
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
├─ build_main.ps1  # 构建 C 版主程序（输出 bin/RC-main.exe）
├─ build_tray.ps1  # 构建 C 版托盘（输出 bin/RC-tray.exe）
├─ config.json     # 运行配置（GUI 首次保存生成）
├─ dome_config.json# 配置示例
├─ installer/      # 构建与安装脚本（PyInstaller）
├─ res/            # 资源（图标等）
├─ src/
│  ├─ main/        # C 版主程序源码
│  ├─ tray/        # C 版托盘源码
│  └─ python/      # Python 版源码（当前保留 GUI）
└─ scripts/        # 清理等辅助脚本
```


## 托盘与权限

- 推荐以管理员权限运行 `RC-tray.exe`；未运行独立托盘时，主程序会启用“内置托盘”
- 托盘菜单：打开配置、启动/重启/关闭主程序、查看版本与权限状态
- 提权与自启：GUI 一键设置/移除开机自启；需要服务控制等操作时请以管理员运行主程序

![Star History Chart](https://api.star-history.com/svg?repos=spacjoy/Remote-Controls&type=Date)

## 安装与构建

- 环境：Windows 10/11；Python 3.12.10+（开发/本地构建时）
- 依赖安装：

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
```

- 一键构建（推荐）：

```powershell
./build.ps1
```

- 产物位置：`installer/dist/RC-*.exe` 与安装包 `installer/dist/installer/*.exe`

## GitHub CI/CD

- CI：PR / 推送到 `main` 会触发 `.github/workflows/ci.yml`，做依赖安装与最小自检（`compileall` + 关键依赖导入 + `pip check`）。
- Release：推送标签 `V*` 或手动触发会运行 `.github/workflows/build-and-release.yml`，完成构建并上传产物/创建 Release。

更多细节见 `installer/` 目录与 `CHANGELOG.md`。

## 常见问题（精简）

- MQTT 连接失败：检查地址/端口/认证，程序会在弱网下自动重连
- 休眠不可用：以管理员运行并启用休眠 `powercfg /hibernate on`
- 托盘找不到主程序：以管理员运行托盘；或直接运行 `RC-main.exe`
- 脚本执行策略：PowerShell 需允许脚本 `Set-ExecutionPolicy RemoteSigned`
- 打包异常：优先使用 `build.ps1`（PyInstaller）

---

- 更新日志：`CHANGELOG.md`
- 贡献指南：`CONTRIBUTING.md`
- 发布页（下载）：<https://github.com/SpacJoy/Remote-Controls/releases>
- 反馈与支持：提交 Issue 或邮件 `mc_chen6019@qq.com`
