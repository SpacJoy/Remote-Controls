#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本信息使用示例
展示如何在程序中使用版本信息
"""

try:
    from version_info import get_version_string, get_version_info, get_program_info # type: ignore
except ImportError:
    # 如果没有版本文件，使用默认值
    def get_version_string():
        return "2.2.3"
    
    def get_version_info():
        return {
            "version": "2.2.3",
            "app_name": "Remote Controls",
            "company": "chen6019",
            "description": "Windows 远程控制工具套件"
        }
    
    def get_program_info(program_key):
        return get_version_info()

# 示例：在托盘程序中显示版本
def show_tray_version():
    """托盘显示版本示例"""
    version = get_version_string()
    program_info = get_program_info("tray")
    
    # 菜单项文本
    version_text = f"版本 v{version}"
    
    # 托盘提示文本
    tooltip_text = f"{program_info['app_name_cn']} v{version}"
    
    # 关于对话框文本
    about_text = f"""
{program_info['app_name']} v{version}
{program_info['description']}

{program_info['copyright']}
GitHub: {program_info['github_url']}
"""
    
    print("托盘版本信息:")
    print(f"菜单项: {version_text}")
    print(f"提示文本: {tooltip_text}")
    print(f"关于信息: {about_text}")

# 示例：在GUI中显示版本
def show_gui_version():
    """GUI显示版本示例"""
    version = get_version_string()
    program_info = get_program_info("gui")
    
    # 窗口标题
    window_title = f"{program_info['display_name']} v{version}"
    
    # 状态栏文本
    status_text = f"就绪 - v{version}"
    
    # 关于窗口
    about_title = f"关于 {program_info['app_name']}"
    about_content = f"""
产品名称: {program_info['app_name']}
版本号: v{version}
描述: {program_info['description']}
开发者: {program_info['company']}
{program_info['copyright']}

项目主页: {program_info['github_url']}
发布页面: {program_info['release_url']}
"""
    
    print("GUI版本信息:")
    print(f"窗口标题: {window_title}")
    print(f"状态栏: {status_text}")
    print(f"关于标题: {about_title}")
    print(f"关于内容: {about_content}")

# 示例：检查更新时使用的版本
def check_update_version():
    """检查更新时使用版本信息"""
    version_info = get_version_info()
    current_version = version_info["version"]
    
    # GitHub API 检查最新版本
    github_api_url = f"https://api.github.com/repos/chen6019/Remote-Controls/releases/latest"
    
    print("更新检查信息:")
    print(f"当前版本: v{current_version}")
    print(f"检查更新API: {github_api_url}")
    print(f"发布页面: {version_info['release_url']}")

if __name__ == "__main__":
    print("=== 版本信息使用示例 ===")
    print()
    
    # 显示基本版本信息
    version = get_version_string()
    print(f"当前版本: v{version}")
    print()
    
    # 托盘版本示例
    show_tray_version()
    print()
    
    # GUI版本示例
    show_gui_version()
    print()
    
    # 更新检查示例
    check_update_version()
