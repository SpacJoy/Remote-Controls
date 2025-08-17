#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本信息配置文件
所有程序的版本信息统一在此管理
自动生成于: 2025-08-18 01:39:10
"""

# 主版本信息
VERSION = "2.2.4"
VERSION_MAJOR = 2
VERSION_MINOR = 2
VERSION_PATCH = 4
VERSION_BUILD = 0

# 应用信息
APP_NAME = "Remote Controls"
APP_NAME_CN = "远程控制"
COMPANY = "chen6019"
COPYRIGHT = f"Copyright © 2024-2025 {COMPANY}"
DESCRIPTION = "Windows 远程控制工具套件"

# GitHub 信息
GITHUB_REPO = "chen6019/Remote-Controls"
GITHUB_URL = f"https://github.com/{GITHUB_REPO}"
RELEASE_URL = f"{GITHUB_URL}/releases"

# 程序文件信息
PROGRAMS = {
    "main": {
        "name": "RC-main",
        "display_name": "远程控制主程序",
        "description": "Remote Controls Main Program",
        "exe_name": "RC-main.exe"
    },
    "gui": {
        "name": "RC-GUI", 
        "display_name": "远程控制配置界面",
        "description": "Remote Controls Configuration GUI",
        "exe_name": "RC-GUI.exe"
    },
    "tray": {
        "name": "RC-tray",
        "display_name": "远程控制托盘",
        "description": "Remote Controls System Tray",
        "exe_name": "RC-tray.exe"
    }
}

def get_version_string():
    """获取版本字符串"""
    return VERSION

def get_version_tuple():
    """获取版本元组"""
    return (VERSION_MAJOR, VERSION_MINOR, VERSION_PATCH, VERSION_BUILD)

def get_version_info():
    """获取完整版本信息"""
    return {
        "version": VERSION,
        "version_tuple": get_version_tuple(),
        "app_name": APP_NAME,
        "app_name_cn": APP_NAME_CN,
        "company": COMPANY,
        "copyright": COPYRIGHT,
        "description": DESCRIPTION,
        "github_url": GITHUB_URL,
        "release_url": RELEASE_URL
    }

def get_program_info(program_key):
    """获取指定程序的信息"""
    if program_key in PROGRAMS:
        info = PROGRAMS[program_key].copy()
        info.update(get_version_info())
        return info
    return None

if __name__ == "__main__":
    print(f"Remote Controls v{VERSION}")
    print(f"版本信息: {get_version_info()}")