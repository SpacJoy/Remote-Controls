<!-- @format -->

# 版本管理系统使用说明

## 概述

项目现在支持统一的版本管理系统，可以在打包时动态指定版本号，所有程序将自动显示正确的版本信息。

## 文件结构

```
Remote-Controls/
├── version_info.py          # 版本信息配置文件
├── update_version.py        # 版本更新工具
├── version_example.py       # 使用示例
├── build_installer_new.bat  # 新的打包脚本（批处理）
├── build_installer_new.ps1  # 新的打包脚本（PowerShell）
└── installer/
    └── Remote-Controls.iss  # 安装脚本（已更新支持动态版本）
```

## 使用方法

### 1. 指定版本打包

#### 方式一：命令行参数

```cmd
# 批处理版本 - 命令行指定版本
.\build_installer_new.bat 1.0.0

# PowerShell版本 - 命令行指定版本
.\build_installer_new.ps1 -Version "1.0.0"
```

#### 方式二：交互式输入（推荐）

```cmd
# 运行脚本，然后输入版本号
.\build_installer_new.bat
# 脚本会提示：请输入版本号 (格式: X.Y.Z，如 1.0.0)
# 版本号: 1.0.0

# PowerShell版本
.\build_installer_new.ps1
# 脚本会提示输入版本号
```

#### 方式三：使用当前版本

```cmd
# 直接按回车，使用 version_info.py 中的当前版本
.\build_installer_new.bat
# 版本号: [直接按回车]
```

### 2. 手动更新版本

```cmd
# 更新版本到 1.0.0
python update_version.py 1.0.0

# 交互式输入版本
python update_version.py
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

新的打包流程包含 7 个步骤：

1. **检查 Python 环境** - 自动检测虚拟环境
2. **更新版本信息** - 如果指定了版本参数，自动更新版本文件
3. **清理旧文件** - 删除 dist 和 build 目录
4. **打包主程序** - 使用 RC-main.spec
5. **打包 GUI 程序** - 使用 RC-GUI.spec
6. **打包托盘程序** - 使用 RC-tray.spec
7. **生成安装包** - 使用 Inno Setup（自动读取版本信息）

## 安装包版本

安装脚本 `installer/Remote-Controls.iss` 现在会自动从 `version_info.py` 读取版本号，生成的安装包文件名将包含正确的版本号。

## 注意事项

1. **版本文件**: `version_info.py` 是自动生成的，不要手动编辑
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

    - `build_installer_new.bat` 替代 `build_installer.bat`
    - `build_installer_new.ps1` 替代 `build_installer.ps1`

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
