<!-- @format -->

# 版本管理系统使用说明

## 概述

项目现在支持统一的版本管理系统，可以在打包时动态指定版本号，所有程序将自动显示正确的版本信息。

## 文件结构

```
Remote-Controls/
├── src/python/version_info.py          # 版本信息配置文件
├── version.txt                       # 简单版本文件（供 Inno Setup/脚本读取）
└── installer/
    ├── update_version.py             # 版本更新工具（生成 version_info.py 与 version.txt）
    └── Remote-Controls.iss  # 安装脚本（已更新支持动态版本）
```

## 使用方法

### 1. 指定版本打包

#### 方式一：命令行参数（推荐）

```powershell
# 顶层入口（推荐）：转发到 installer/build_installer.ps1

# 方式 A：直接指定版本号
pwsh -NoProfile -ExecutionPolicy Bypass -File .\build.ps1 3.0.0

# 方式 B：直接运行 installer/build_installer.ps1
pwsh -NoProfile -ExecutionPolicy Bypass -File .\installer\build_installer.ps1 3.0.0
```

#### 方式二：交互式输入（推荐）

```cmd
# 运行脚本，然后输入版本号
pwsh -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
# 脚本会提示：请输入版本号 (格式: X.Y.Z，如 1.0.0)
# 版本号: 3.0.0
```

#### 方式三：使用当前版本

```cmd
# 直接按回车，使用 src/python/version_info.py 中的当前版本
pwsh -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
# 版本号: [直接按回车]
```

### 2. 手动更新版本

```cmd
# 更新版本到 1.0.0
python .\installer\update_version.py 3.0.0

# 交互式输入版本
python .\installer\update_version.py
```

### 3. 在程序中使用版本信息

#### 导入版本信息

```python
try:
    from version_info import get_version_string, get_version_info, get_program_info

    # 获取版本字符串
    version = get_version_string()  # "1.0.0"

    # 获取完整版本信息
    info = get_version_info()

    # 获取特定程序信息
    tray_info = get_program_info("tray")
    gui_info = get_program_info("gui")
    main_info = get_program_info("main")

except ImportError:
    # 处理版本文件不存在的情况
    def get_version_string():
        return "未知版本"
```

#### 托盘程序中使用

```python
# 在托盘菜单中显示版本
version = get_version_string()
menu_items = [
    ("配置界面", open_gui),
    ("版本 v" + version, open_homepage),  # 显示版本
    ("退出", quit_app)
]

# 托盘提示文本
program_info = get_program_info("tray")
tooltip = f"{program_info['app_name_cn']} v{version}"
```

#### GUI 程序中使用

```python
# 窗口标题
program_info = get_program_info("gui")
version = get_version_string()
window_title = f"{program_info['display_name']} v{version}"

# 关于对话框
about_text = f"""
{program_info['app_name']} v{version}
{program_info['description']}

{program_info['copyright']}
GitHub: {program_info['github_url']}
"""
```

## 版本号格式

支持的版本号格式：

-   `X.Y.Z` (如 1.0.0)
-   `X.Y.Z.B` (如 1.0.0.1，包含构建号)

示例：

-   `1.0.0` → VERSION_MAJOR=1, VERSION_MINOR=0, VERSION_PATCH=0, VERSION_BUILD=0
-   `1.0.0.5` → VERSION_MAJOR=1, VERSION_MINOR=0, VERSION_PATCH=0, VERSION_BUILD=5

## 打包流程

当前打包流程（`installer/build_installer.ps1`）包含 7 个步骤：

1. **检查 Python 环境** - 自动检测虚拟环境
2. **更新版本信息** - 如果指定了版本参数，自动更新版本文件
3. **清理旧文件** - 删除 `installer/dist` 和 `installer/build`
4. **构建 C 主程序** - 运行 `build_main.ps1` 输出 `bin/RC-main.exe`，并复制到 `installer/dist/`
5. **打包 GUI 程序** - 使用 PyInstaller 打包 `src/python/GUI.py` 输出 `installer/dist/RC-GUI.exe`
6. **构建 C 托盘程序** - 运行 `build_tray.ps1` 输出 `bin/RC-tray.exe`，并复制到 `installer/dist/`
7. **生成安装包** - 使用 Inno Setup 6（通过临时脚本注入版本号）

## 安装包版本

安装脚本 `installer/Remote-Controls.iss` 现在会自动从 `src/python/version_info.py` 读取版本号，生成的安装包文件名将包含正确的版本号。

## 注意事项

1. **版本文件**: `src/python/version_info.py` 是自动生成的，不要手动编辑
2. **兼容性**: 程序中的版本导入使用 try-except，确保在版本文件不存在时也能正常运行
3. **构建顺序**: 必须先运行版本更新，再进行打包
4. **文件编码**: 所有版本相关文件使用 UTF-8 编码

## 示例脚本

查看 `version_example.py` 了解完整的使用示例，包括：

-   托盘程序版本显示
-   GUI 程序版本显示
-   更新检查版本比较

## 迁移指南

### 从旧脚本迁移

1. 使用新的打包脚本：

    - 使用项目根目录的 `build.ps1` 作为统一入口（内部转发到 `installer/build_installer.ps1`）
    - 旧的 `.bat` 入口若仍存在，可视为历史遗留，建议统一使用 PowerShell 入口以获得更好的编码与日志支持

2. 在程序中添加版本信息导入：

    ```python
    try:
        from version_info import get_version_string
        VERSION = get_version_string()
    except ImportError:
        VERSION = "未知版本"  # 默认版本
    ```

3. 更新程序中硬编码的版本号为动态获取

这样就完成了版本管理系统的集成！
