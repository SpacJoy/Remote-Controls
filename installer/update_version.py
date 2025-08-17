#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本信息生成器
用于动态更新 version_info.py 文件
"""

import sys
import os
from datetime import datetime

def update_version_info(version=None):
    """更新版本信息文件"""
    if version is None:
        version = "2.2.3"  # 默认版本
    
    # 解析版本号
    try:
        parts = version.split('.')
        if len(parts) < 3:
            parts.extend(['0'] * (3 - len(parts)))
        major, minor, patch = parts[0:3]
        build = parts[3] if len(parts) > 3 else '0'
        
        major, minor, patch, build = int(major), int(minor), int(patch), int(build)
    except (ValueError, IndexError):
        print(f"错误：版本号格式不正确: {version}")
        print("正确格式: X.Y.Z 或 X.Y.Z.B")
        return False
    
    # 生成版本文件内容
    current_year = datetime.now().year
    content = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本信息配置文件
所有程序的版本信息统一在此管理
自动生成于: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

# 主版本信息
VERSION = "{version}"
VERSION_MAJOR = {major}
VERSION_MINOR = {minor}
VERSION_PATCH = {patch}
VERSION_BUILD = {build}

# 应用信息
APP_NAME = "Remote Controls"
APP_NAME_CN = "远程控制"
COMPANY = "chen6019"
COPYRIGHT = f"Copyright © 2024-{current_year} {{COMPANY}}"
DESCRIPTION = "Windows 远程控制工具套件"

# GitHub 信息
GITHUB_REPO = "chen6019/Remote-Controls"
GITHUB_URL = f"https://github.com/{{GITHUB_REPO}}"
RELEASE_URL = f"{{GITHUB_URL}}/releases"

# 程序文件信息
PROGRAMS = {{
    "main": {{
        "name": "RC-main",
        "display_name": "远程控制主程序",
        "description": "Remote Controls Main Program",
        "exe_name": "RC-main.exe"
    }},
    "gui": {{
        "name": "RC-GUI", 
        "display_name": "远程控制配置界面",
        "description": "Remote Controls Configuration GUI",
        "exe_name": "RC-GUI.exe"
    }},
    "tray": {{
        "name": "RC-tray",
        "display_name": "远程控制托盘",
        "description": "Remote Controls System Tray",
        "exe_name": "RC-tray.exe"
    }}
}}

def get_version_string():
    """获取版本字符串"""
    return VERSION

def get_version_tuple():
    """获取版本元组"""
    return (VERSION_MAJOR, VERSION_MINOR, VERSION_PATCH, VERSION_BUILD)

def get_version_info():
    """获取完整版本信息"""
    return {{
        "version": VERSION,
        "version_tuple": get_version_tuple(),
        "app_name": APP_NAME,
        "app_name_cn": APP_NAME_CN,
        "company": COMPANY,
        "copyright": COPYRIGHT,
        "description": DESCRIPTION,
        "github_url": GITHUB_URL,
        "release_url": RELEASE_URL
    }}

def get_program_info(program_key):
    """获取指定程序的信息"""
    if program_key in PROGRAMS:
        info = PROGRAMS[program_key].copy()
        info.update(get_version_info())
        return info
    return None

if __name__ == "__main__":
    print(f"Remote Controls v{{VERSION}}")
    print(f"版本信息: {{get_version_info()}}")'''

    # 写入文件
    try:
        with open('version_info.py', 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 同时创建一个简单的版本文件供 Inno Setup 使用
        simple_version_content = f'VERSION={version}\n'
        with open('version.txt', 'w', encoding='utf-8') as f:
            f.write(simple_version_content)
            
        print(f"版本信息已更新: {version}")
        return True
    except Exception as e:
        print(f"写入版本文件失败: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        version = sys.argv[1]
    else:
        version = input("请输入版本号 (默认 2.2.3): ").strip()
        if not version:
            version = "2.2.3"
    
    if update_version_info(version):
        print("版本信息生成完成！")
    else:
        sys.exit(1)
