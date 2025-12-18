"""打包命令
1) 推荐：使用 spec 文件
    pyinstaller RC-GUI.spec --noconfirm

2) 直接命令行（仅 icon_GUI.ico、top.ico）
pyinstaller -F -n RC-GUI --noconsole --icon=res\\icon_GUI.ico --add-data "res\\icon_GUI.ico;res" --add-data "res\\top.ico;res" GUI.py
程序名：RC-GUI.exe
"""
import os
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
import tkinter.ttk as ttk
import tkinter.font as tkfont
import json
import ctypes
import sys
import time
import psutil
import subprocess
import win32com.client
import re
import shutil
import locale
from typing import Any, Dict, List, Union

# ----------------------------
# i18n (zh/en) for GUI
# ----------------------------

def _normalize_lang(lang: str | None) -> str:
    if not lang:
        return ""
    s = str(lang).strip().lower().replace("_", "-")
    if s in ("zh", "zh-cn", "zh-hans", "cn", "zh-hans-cn"):
        return "zh"
    if s in ("en", "en-us", "en-gb"):
        return "en"
    if s.startswith("zh"):
        return "zh"
    if s.startswith("en"):
        return "en"
    return ""


def _detect_default_lang() -> str:
    # locale.getdefaultlocale() 已弃用（Python 3.15+），改用 setlocale/getlocale。
    try:
        locale.setlocale(locale.LC_ALL, "")
    except Exception:
        pass

    for getter in (
        lambda: locale.getlocale()[0],
        lambda: os.environ.get("LC_ALL"),
        lambda: os.environ.get("LC_CTYPE"),
        lambda: os.environ.get("LANG"),
    ):
        try:
            norm = _normalize_lang(getter())
            if norm:
                return norm
        except Exception:
            pass

    # Windows 默认偏中文用户群，这里保守地按系统语言判断失败则给 en
    return "en"


# 全局语言：在读取 config.json 后会被覆盖
LANG: str = _detect_default_lang()

# 中文源文案 -> 英文翻译（只翻 GUI 文案；未命中的保持原样）
_ZH_TO_EN: dict[str, str] = {
    "远程控制": "Remote Controls",
    "远程控制-": "Remote Controls - ",
    "(管理员)": "(Admin)",
    "系统配置": "System Settings",
    "MQTT认证配置": "MQTT Auth",
    "主题配置": "Themes",
    "网站：": "Broker:",
    "端口：": "Port:",
    "认证模式：": "Auth mode:",
    "私钥模式": "Private key",
    "账密模式": "Username/Password",
    "test模式": "Test mode",
    "通知提示": "Notifications",
    "点击打开任务计划": "Open Task Scheduler",
    "需要管理员权限才能设置": "Admin required",
    "开机自启/启用睡眠(休眠)功能": "Autostart / Sleep (Hibernate)",
    "获取权限": "Request admin",
    "用户名：": "Username:",
    "密码：": "Password:",
    "客户端ID：": "Client ID:",
    "启用TLS/SSL": "Use TLS/SSL",
    "私钥模式：\n        使用客户端ID作为私钥\n账密模式：\n        兼容大多数IoT平台": "Private key:\n        Client ID is used as the secret\nUsername/Password:\n        Works with most IoT platforms",
    "内置": "Built-in",
    "计算机": "Computer",
    "屏幕": "Screen",
    "音量": "Volume",
    "睡眠": "Sleep",
    "媒体控制": "Media",
    "详情": "Details",
    "主题：": "Theme:",
    "自定义：": "Custom:",
    "双击即可修改": "Double-click to edit",
    "刷新": "Reload",
    "更多": "More",
    "添加": "Add",
    "修改": "Edit",
    "打开配置文件夹": "Open config folder",
    "保存配置文件": "Save config",
    "取消": "Cancel",
    "提示": "Info",
    "警告": "Warning",
    "错误": "Error",
    "确认刷新": "Confirm reload",
    "配置文件错误": "Config error",
    "备份完成": "Backup created",
    "备份失败": "Backup failed",
    "程序退出": "Exit",
    "管理员权限": "Administrator",
    "管理员权限确认": "Administrator confirmation",
    "权限提醒": "Permission notice",
    "UAC提权": "UAC elevation",
    "检查失败": "Check failed",
    "睡眠功能状态": "Sleep status",
    "语言：": "Language:",
    "参数范围：": "Value range:",
        # 命令主题 {value} 范围
        "value 参数范围：": "Value range:",
    "最小：": "Min:",
    "最大：": "Max:",
    "请输入整数": "Please enter an integer",
    "参数超出范围：{lo}-{hi}": "Value out of range: {lo}-{hi}",
    "请输入 {value} 的值（范围 {lo}-{hi}），例如 {ex}：": "Enter a value for {value} (range {lo}-{hi}), e.g. {ex}:",

    # 开机自启
    "设置开机自启": "Enable autostart",
    "关闭开机自启": "Disable autostart",
    "选择启动方案": "Choose startup mode",
    "请选择以下两种启动方案之一：\n\n" +
    "【方案一】用户登录时运行\n注：无托盘时推荐!!\n" +
    "优点：只有用户登录时才运行\n" +
    "缺点：需要用户登录后才能启动\n\n" +
    "【方案二】系统启动时运行\n注：有托盘时推荐!!\n" +
    "优点：系统启动即可运行，无需用户登录\n" +
    "缺点：需要登录后托盘自动重启主程序才能使用媒体控制\n\n" +
    "选择 是：【方案一】\n\n选择 否：【方案二】":
        "Please choose one of the following startup modes:\n\n"
        "[Mode 1] Run at user logon\nNote: recommended when tray is disabled.\n"
        "Pros: runs only after a user signs in\n"
        "Cons: will not start until a user signs in\n\n"
        "[Mode 2] Run at system startup\nNote: recommended when tray is enabled.\n"
        "Pros: starts when Windows boots (no sign-in required)\n"
        "Cons: media control requires tray to restart main after sign-in\n\n"
        "Choose Yes: Mode 1\n\nChoose No: Mode 2",
    "已取消设置开机自启动": "Autostart setup cancelled",
    "未找到 RC-main.exe 文件\n请检查文件是否存在": "RC-main.exe not found.\nPlease check the file exists.",
    "未找到 RC-tray.exe 文件，跳过托盘启动设置": "RC-tray.exe not found. Skipping tray autostart setup.",
    "创建任务成功\n已配置为任何用户登录时以管理员组权限运行":
        "Task created.\nConfigured to run at logon for any user with Administrators group privileges.",
    "创建任务成功\n已配置为系统启动时以SYSTEM用户权限运行":
        "Task created.\nConfigured to run at system startup as SYSTEM.",
    "创建托盘自启动失败\n{code}": "Failed to create tray autostart.\n{code}",
    "移动文件位置后需重新设置任务哦！": "If you move the files, please reconfigure the task.",
    "创建开机自启动失败\n{code}": "Failed to create autostart task.\n{code}",
    "你确定要删除开机自启动任务吗？": "Are you sure you want to delete the autostart tasks?",
    "关闭所有自启动任务成功": "Disabled all autostart tasks successfully.",
    "关闭主程序自启动成功，托盘任务不存在": "Main autostart disabled. Tray task not found.",
    "关闭托盘自启动成功，主程序任务不存在": "Tray autostart disabled. Main task not found.",
    "关闭开机自启动失败": "Failed to disable autostart.",

    # 自定义主题：类型/关闭预设选项
    "程序或脚本": "Program/Script",
    "服务(需管理员权限)": "Service (admin)",
    "命令": "Command",
    "按键(Hotkey)": "Hotkey",
    "忽略": "Ignore",
    "强制结束": "Force kill",
    "中断": "Interrupt",
    "停止服务": "Stop service",
    "自定义": "Custom",
    "服务时主程序": "For service: main program",
    "需管理员权限": "Admin required",

    # 详情/自定义/内置主题设置等子窗口
    "详情信息": "Details",
    "内置主题": "Built-in themes",
    "自定义主题": "Custom themes",
    "提示说明": "Tips",
    "修改自定义主题": "Edit custom theme",
    "添加自定义主题": "Add custom theme",
    "类型：": "Type:",
    "状态：": "Enabled:",
    "昵称：": "Nickname:",
    "打开(on)：": "On:",
    "关闭(off)：": "Off:",
    "关闭预设：": "Off preset:",
    "选择文件": "Browse",
    "打开服务": "Open Services",
    "PowerShell测试": "Test in PowerShell",
    "PowerShell测试(关闭)": "Test off in PowerShell",
    "显示窗口": "Show window",
    "按键(Hotkey) 设置": "Hotkey settings",
    "录制": "Record",
    "字母段间隔(ms)：": "Char delay (ms):",
    "保存": "Save",
    "删除": "Delete",

    # 内置主题设置窗口
    "内置主题设置": "Built-in settings",
    "计算机(Computer) 主题动作": "Computer theme actions",
    "延时(秒)：": "Delay (s):",
    "提示：计算机主题延时仅对关机/重启有效，其它动作忽略延时。": "Note: Computer delays only apply to shutdown/restart.",
    "屏幕亮度控制方案": "Brightness control",
    "控制方式：": "Mode:",
    "系统接口(WMI)": "System (WMI)",
    "Twinkle Tray (命令行)": "Twinkle Tray (CLI)",
    "显示叠加层(Overlay)": "Show overlay",
    "Twinkle Tray 路径：": "Twinkle Tray path:",
    "选择 Twinkle Tray 可执行文件": "Select Twinkle Tray executable",
    "可执行文件": "Executable",
    "所有文件": "All files",
    "浏览": "Browse",
    "目标显示器：": "Target monitor:",
    "按编号(MonitorNum)": "By number (MonitorNum)",
    "按ID(MonitorID)": "By ID (MonitorID)",
    "全部显示器(All)": "All monitors",
    "睡眠(sleep) 主题动作": "Sleep theme actions",
    "提示：睡眠主题延时将在执行动作前等待指定秒数。": "Note: Sleep delays wait before executing.",
    "系统睡眠功能开关：": "System sleep toggle:",
    "注：需要管理员权限": "Note: admin required",
    " 启用 睡眠(休眠)功能": "Enable sleep/hibernate",
    " 关闭 睡眠(休眠)功能": "Disable sleep/hibernate",
    "检查睡眠功能状态": "Check sleep status",

    # 其它提示/弹窗
    "确定？": "Confirm?",
    "已取消": "Cancelled",
    "请先选择一个自定义主题": "Please select a custom theme first.",
    "确认删除": "Confirm delete",
    "确定要删除这个自定义主题吗？": "Delete this custom theme?",
    "确认包含中文字符": "Confirm non-ASCII",

    # 动作/选项通用
    "不执行": "None",
    "键盘组合": "Key combo",
    "锁屏": "Lock",
    "关机": "Shutdown",
    "重启": "Restart",
    "注销": "Log off",
    "睡眠": "Sleep",
    "休眠": "Hibernate",
    "关闭显示器": "Turn display off",
    "打开显示器": "Turn display on",

    # 内置设置告警文案
    "依赖于 Windows 的系统 API 来控制显示器电源状态\n未经过测试\n可能造成不可逆后果\n谨慎使用‘开/关显示器功能’": "Uses Windows system APIs to control display power.\nNot fully tested.\nMay cause irreversible side effects.\nUse display on/off with caution.",
    "当打开动作设置为“睡眠/休眠”时：\n设备将进入低功耗或断电状态，主程序会离线，\n期间无法接收远程命令，需要人工或计划唤醒。": "When the On action is Sleep/Hibernate:\nThe device goes offline and cannot receive commands.\nYou will need to wake it manually or via scheduled wake.",

    # 主界面状态提示
    "休眠/睡眠不可用\n系统未启用休眠功能": "Sleep/Hibernate unavailable\nHibernate is not enabled on this system",

    # 键盘录制弹窗
    "录制键盘组合": "Record hotkey",
    "已按下：(空)": "Pressed: (empty)",
    "已按下：": "Pressed: ",

    # 命令测试弹窗
    "输入参数": "Input parameter",
    "请输入 {value} 的值，例如 50：": "Enter a value for {value}, e.g. 50:",
    "请先在“值”中输入要测试的命令": "Please enter a command to test in the value field.",
    "请先在“关闭(off)”中输入要测试的命令": "Please enter a command to test in the Off field.",
    "请先将关闭预设切换为“自定义”并填写命令": "Switch Off preset to Custom and enter a command first.",
    "无法启动 PowerShell: {err}": "Failed to start PowerShell: {err}",
    "无法打开服务管理器: {err}": "Failed to open Services: {err}",

    # 配置保存提示
    "配置文件已保存\n请重新打开主程序以应用更改\n刷新test模式需重启本程序":
        "Config saved.\nPlease restart the main program to apply changes.\nRestart is required to refresh test mode.",

    # 刷新自定义主题弹窗
    "刷新将加载配置文件中的设置，\n您未保存的更改将会丢失！\n确定要继续吗？":
        "Reload will load settings from the config file.\nUnsaved changes will be lost!\nContinue?",
    "已从配置文件刷新自定义主题列表": "Custom themes reloaded from config.",
    "读取配置文件失败: {err}": "Failed to read config file: {err}",
    "配置文件不存在，无法刷新": "Config file not found; cannot reload.",
}

# 反向映射：用于从英文切回中文（避免某些控件在英文模式创建时无法回切）
_EN_TO_ZH: dict[str, str] = {}
for _zh, _en in _ZH_TO_EN.items():
    if _en and _en not in _EN_TO_ZH:
        _EN_TO_ZH[_en] = _zh



def t(s: str) -> str:
    """Translate UI string between zh/en based on current LANG."""
    if LANG == "en":
        return _ZH_TO_EN.get(s, s)
    return _EN_TO_ZH.get(s, s)


_LANG_OBSERVERS: list[callable] = []


def register_lang_observer(cb) -> None:
    """Register a callback to run on language changes."""
    try:
        _LANG_OBSERVERS.append(cb)
    except Exception:
        pass


def _set_root_title() -> None:
    try:
        base = f"远程控制-{BANBEN}"
        if IS_GUI_ADMIN:
            base = f"远程控制-{BANBEN}(管理员)"
        if LANG == "en":
            # 保留版本号，只替换前缀
            base = base.replace("远程控制-", "Remote Controls - ")
            base = base.replace("(管理员)", "(Admin)")
        root.title(base)
    except Exception:
        pass


def apply_language_to_widgets(widget: tk.Misc) -> None:
    """Apply current LANG to widget tree (static text only)."""

    def _has_cjk(s: str) -> bool:
        try:
            return any("\u4e00" <= ch <= "\u9fff" for ch in s)
        except Exception:
            return False

    def _apply_one(w: tk.Misc) -> None:
        # 常规 text 选项
        try:
            cfg = w.configure()
        except Exception:
            cfg = {}

        if "text" in cfg:
            try:
                cur = str(w.cget("text"))
                src = getattr(w, "_rc_text_src", None)
                if src is None:
                    src = cur
                else:
                    # 若控件文本被动态改写（如“设置/关闭开机自启”），刷新源文案以保证可双向切换
                    if _has_cjk(cur):
                        src = cur
                    elif cur in _EN_TO_ZH:
                        src = _EN_TO_ZH.get(cur, src)
                setattr(w, "_rc_text_src", src)
                w.configure(text=t(src))
            except Exception:
                pass

        # Treeview headings
        if isinstance(w, ttk.Treeview):
            try:
                src_map = getattr(w, "_rc_heading_src", None)
                if src_map is None:
                    src_map = {}
                    for col in w["columns"]:
                        src_map[col] = w.heading(col).get("text", "")
                    setattr(w, "_rc_heading_src", src_map)
                for col, src_text in src_map.items():
                    w.heading(col, text=t(str(src_text)))
            except Exception:
                pass

        # Notebook tab titles
        if isinstance(w, ttk.Notebook):
            try:
                src_tabs = getattr(w, "_rc_tab_src", None)
                if src_tabs is None:
                    src_tabs = {}
                    for tab_id in w.tabs():
                        try:
                            src_tabs[tab_id] = w.tab(tab_id, "text")
                        except Exception:
                            src_tabs[tab_id] = ""
                    setattr(w, "_rc_tab_src", src_tabs)
                for tab_id, src_text in src_tabs.items():
                    try:
                        w.tab(tab_id, text=t(str(src_text)))
                    except Exception:
                        pass
            except Exception:
                pass

    try:
        _apply_one(widget)
        for child in widget.winfo_children():
            apply_language_to_widgets(child)
    except Exception:
        return


def _apply_language_everywhere() -> None:
    # root/title
    _set_root_title()
    # 主窗口控件文案
    try:
        apply_language_to_widgets(root)
    except Exception:
        pass
    # 已打开的 Toplevel
    try:
        for w in root.winfo_children():
            if isinstance(w, tk.Toplevel):
                apply_language_to_widgets(w)
    except Exception:
        pass

    # 动态元素（combobox values / window titles 等）
    try:
        alive: list[callable] = []
        for cb in list(_LANG_OBSERVERS):
            try:
                cb()
                alive.append(cb)
            except Exception:
                pass
        _LANG_OBSERVERS[:] = alive
    except Exception:
        pass

def _normalize_command_for_powershell(cmd: str) -> str:
    """规范化命令避免 PowerShell 将 curl 映射为 Invoke-WebRequest。
    处理：行首/分隔符后的 curl -> curl.exe，末尾独立 curl -> curl.exe，独立 -s -> --silent。
    出错则返回原串。"""
    try:
        import re as _re
        txt = cmd or ""
        txt = _re.sub(r"^(\s*)curl(\s+)", r"\1curl.exe\2", txt, flags=_re.IGNORECASE)
        txt = _re.sub(r"([;&|]\s*)curl(\s+)", r"\1curl.exe\2", txt, flags=_re.IGNORECASE)
        txt = _re.sub(r"(\s+)curl(\s*)$", r"\1curl.exe\2", txt, flags=_re.IGNORECASE)
        txt = _re.sub(r"(?<![A-Za-z0-9_-])-s(?![A-Za-z0-9_-])(?=\s|$)", "--silent", txt)
        return txt
    except Exception:
        return cmd

# 统一版本来源
try:
    from version_info import get_version_string
    BANBEN = f"V{get_version_string()}"
except Exception:
    # 回退：避免因缺少版本文件导致运行异常
    BANBEN = "V未知版本"
# 计划任务名称（与安装器一致）
TASK_NAME_MAIN = "Remote Controls Main Service"
TASK_NAME_TRAY = "Remote Controls Tray"
# 资源路径（兼容 PyInstaller _MEIPASS）
def resource_path(relative_path: str) -> str:
    """返回资源文件的实际路径（兼容 PyInstaller）。"""
    bases: list[str] = []
    if hasattr(sys, "_MEIPASS"):
        try:
            bases.append(getattr(sys, "_MEIPASS"))  # type: ignore[attr-defined]
        except Exception:
            pass
    try:
        bases.append(os.path.abspath(os.path.dirname(__file__)))
    except Exception:
        pass
    try:
        bases.append(os.path.abspath(os.path.dirname(sys.executable)))
    except Exception:
        pass
    bases.append(os.path.abspath("."))
    seen = set()
    for base in bases:
        if not base or base in seen:
            continue
        seen.add(base)
        p = os.path.join(base, relative_path)
        if os.path.exists(p):
            return p
    return relative_path

# 创建一个命名的互斥体
# mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "RC-main-GUI")

# 检查互斥体是否已经存在
# if ctypes.windll.kernel32.GetLastError() == 183:
#     messagebox.showerror("错误", "应用程序已在运行。")
#     sys.exit()

# 运行模式 & 隐藏控制台
is_script_mode = not getattr(sys, "frozen", False)

def hide_console():
    """隐藏当前控制台窗口（脚本模式启动时使用，可用 RC_NO_HIDE=1 禁用）。"""
    try:
        if os.environ.get("RC_NO_HIDE") == "1":
            return
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass

if is_script_mode:
    hide_console()

# 获取管理员权限
def get_administrator_privileges() -> None:
    """
    English: Re-runs the program with administrator privileges
    中文: 以管理员权限重新运行当前程序
    """
    try:
        # 询问用户是否确认重启为管理员权限
        result = messagebox.askyesno(
            "管理员权限确认", 
            "程序将以管理员权限重新启动。\n\n"
            "这将关闭当前程序并请求管理员权限。\n\n"
            "是否继续？"
        )
        
        if result:
            # 重新启动程序，请求管理员权限
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, f'"{__file__}"', None, 1
            )
            # 只有在成功启动新进程时才退出当前程序
            if ret > 32:  # ShellExecuteW 返回值大于32表示成功
                sys.exit()
            else:
                messagebox.showwarning(
                    "权限提醒", 
                    "授权被取消或失败。\n\n"
                    "程序将以当前权限继续运行。\n"
                    "请注意：部分功能可能无法正常工作。"
                )
        else:
            messagebox.showwarning(
                "权限提醒", 
                "您选择了不使用管理员权限运行。\n\n"
                "请注意：部分功能可能无法正常工作。"
            )
    except Exception as e:
        messagebox.showerror("错误", f"请求管理员权限时出错: {e}")

def run_as_admin(executable_path, parameters=None, working_dir=None, show_cmd=0):
    """
    以管理员权限运行指定程序

    参数：
    executable_path (str): 要执行的可执行文件路径
    parameters (str, optional): 传递给程序的参数，默认为None
    working_dir (str, optional): 工作目录，默认为None（当前目录）
    show_cmd (int, optional): 窗口显示方式，默认为0（1正常显示，0隐藏）

    返回：
    int: ShellExecute的返回值，若小于等于32表示出错
    """
    if parameters is None:
        parameters = ''
    if working_dir is None:
        working_dir = ''
    # 调用ShellExecuteW，设置动词为'runas'
    result = ctypes.windll.shell32.ShellExecuteW(
        None,                  # 父窗口句柄
        'runas',               # 操作：请求管理员权限
        executable_path,       # 要执行的文件路径
        parameters,            # 参数
        working_dir,           # 工作目录
        show_cmd               # 窗口显示方式
    )
    
    return result

def run_py_in_venv_as_admin(python_exe_path:str, script_path:str, script_args=None, show_window:bool=True):
    """使用指定 Python 解释器提权运行脚本（直接调用，不经 cmd）。返回 ShellExecute 结果 (>32 成功)。"""
    if not os.path.exists(python_exe_path):
        raise FileNotFoundError(f"Python 解释器未找到: {python_exe_path}")
    if script_args is None:
        script_args = []
    params = ' '.join([f'"{script_path}"'] + [str(a) for a in script_args])
    workdir = os.path.dirname(script_path) or None
    show_cmd = 1 if show_window else 0
    try:
        return ctypes.windll.shell32.ShellExecuteW(None,'runas',python_exe_path,params,workdir,show_cmd)
    except Exception:
        return 0

def run_py_in_venv_as_admin_hidden(python_exe_path, script_path, script_args=None):
    # 兼容旧调用，默认隐藏窗口
    return run_py_in_venv_as_admin(python_exe_path, script_path, script_args, show_window=False)

def restart_self_as_admin():
    """以管理员权限重新启动当前程序"""
    try:
        # 获取当前程序的完整路径和参数
        if getattr(sys, "frozen", False):
            # 如果是打包后的exe
            current_exe = sys.executable
        else:
            # 如果是Python脚本
            current_script = os.path.abspath(__file__)
            current_exe = sys.executable
        
        # 构建重启命令
        if getattr(sys, "frozen", False):
            result = run_as_admin(current_exe)
        else:
            # 脚本模式优先 pythonw.exe
            base_dir = os.path.dirname(current_exe)
            pythonw = os.path.join(base_dir, 'pythonw.exe')
            interpreter = pythonw if os.path.exists(pythonw) else current_exe
            script_path = os.path.abspath(__file__)
            result = run_py_in_venv_as_admin(interpreter, script_path, show_window=False)

        if result > 32:
            # 等待新进程出现再退出（最多5s）
            if not getattr(sys, 'frozen', False):
                target = os.path.abspath(__file__)
                for _ in range(50):
                    new_found = False
                    try:
                        for proc in psutil.process_iter(['name','cmdline','pid']):
                            cl = proc.info.get('cmdline') or []
                            if proc.pid != os.getpid() and cl and target in ' '.join(cl) and 'python' in (proc.info.get('name') or '').lower():
                                new_found = True
                                break
                    except Exception:
                        pass
                    if new_found:
                        break
                    time.sleep(0.1)
            os._exit(0)
        else:
            messagebox.showwarning("UAC提权", f"获取管理员权限失败，错误码: {result}")
            return False
            
    except Exception as e:
        messagebox.showerror("UAC提权", f"重启程序时出错: {e}")
        return False

def check_and_request_uac():
    """检查并在需要时请求提权"""
    
    # 如果已经是管理员权限，无需提权
    if IS_GUI_ADMIN:
        return True
    
    try:
        # 询问用户是否要提权
        if messagebox.askyesno(t("管理员权限"), t("程序未获得管理员权限。\n是否立即请求管理员权限？\n\n选择'是'将重新启动程序并请求管理员权限。")):
            # 以管理员权限重新启动程序
            return restart_self_as_admin()
        else:
            return False
        
    except Exception as e:
        messagebox.showerror(t("管理员权限"), t(f"提权失败: {e}"))
        return False

def startup_admin_check():
    """启动时进行管理员权限检查和自动提权"""
    try:
        # 检查并请求提权（如果需要的话）
        admin_result = check_and_request_uac()
        if admin_result is False:  # 明确检查False，因为None表示其他情况
            messagebox.showinfo(t("管理员权限"), t("未进行提权或提权失败，程序将以当前权限继续运行"))
        # 如果admin_result是True，说明已经有管理员权限
        # 如果函数内部重启了程序，这里的代码不会执行到
    except Exception as e:
        messagebox.showerror(t("管理员权限检查"), t(f"管理员权限检查过程中出现异常: {e}"))


# DPI 与字体优化
def _enable_dpi_awareness() -> None:
    """
    Windows: 使进程 DPI 感知，避免高分屏字体/控件发糊。
    优先 Per-Monitor (v1)，回退到 System DPI Aware。
    """
    try:
        shcore = ctypes.windll.shcore
        # 2 = PROCESS_PER_MONITOR_DPI_AWARE # 每个监视器 DPI 感知
        shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

def _apply_font_readability_and_scaling(root: tk.Tk) -> None:
    """
    统一设置更易读的字体族，并根据系统缩放设置 Tk scaling。
    """
    body_min_size = 9
    heading_min_size = 10

    # 收集多种 DPI 信息，取最高的缩放值应用到 Tk
    scaling_candidates: list[float] = []
    try:
        scale_pct = ctypes.c_uint()
        ctypes.windll.shcore.GetScaleFactorForDevice(0, ctypes.byref(scale_pct))
        if scale_pct.value:
            dpi = 96 * (scale_pct.value / 100.0)
            scaling_candidates.append(dpi / 72.0)
    except Exception:
        pass
    try:
        user32 = ctypes.windll.user32
        dpi_val = None
        try:
            hwnd = root.winfo_id()
            if hwnd and hasattr(user32, "GetDpiForWindow"):
                dpi_val = user32.GetDpiForWindow(ctypes.c_void_p(hwnd))
        except Exception:
            dpi_val = None
        if dpi_val is None:
            try:
                dpi_val = user32.GetDpiForSystem()
            except Exception:
                dpi_val = None
        if dpi_val:
            scaling_candidates.append(float(dpi_val) / 72.0)
    except Exception:
        pass
    try:
        px_per_inch = root.winfo_fpixels("1i")
        if px_per_inch:
            scaling_candidates.append(float(px_per_inch) / 72.0)
    except Exception:
        pass

    scaling_to_apply = None
    if scaling_candidates:
        try:
            scaling_to_apply = max(scaling_candidates)
            if scaling_to_apply and scaling_to_apply > 0:
                root.tk.call("tk", "scaling", scaling_to_apply)
        except Exception:
            scaling_to_apply = None

    if scaling_to_apply and scaling_to_apply >= 1.5:
        body_min_size = 10
        heading_min_size = 11

    # 优选中文/中英皆宜的清晰字体
    preferred_ui = ("Microsoft YaHei UI", "Segoe UI", "Microsoft YaHei")
    preferred_fixed = ("Consolas", "Cascadia Mono", "Courier New")

    def _set_font(name: str, family_choices, min_size=9):
        try:
            f = tkfont.nametofont(name)
            # 选择第一个系统可用字体
            family = next((fam for fam in family_choices if tkfont.families() and fam in tkfont.families()), None)
            if family:
                f.configure(family=family)
            # 合理的最小字号
            size = f.cget("size")
            if isinstance(size, int) and size < min_size:
                f.configure(size=min_size)
        except Exception:
            pass

    _set_font("TkDefaultFont", preferred_ui, min_size=body_min_size)
    _set_font("TkTextFont", preferred_ui, min_size=body_min_size)
    _set_font("TkMenuFont", preferred_ui, min_size=body_min_size)
    _set_font("TkHeadingFont", preferred_ui, min_size=heading_min_size)
    _set_font("TkCaptionFont", preferred_ui, min_size=body_min_size)
    _set_font("TkSmallCaptionFont", preferred_ui, min_size=body_min_size)
    _set_font("TkIconFont", preferred_ui, min_size=body_min_size)
    _set_font("TkTooltipFont", preferred_ui, min_size=body_min_size)
    _set_font("TkFixedFont", preferred_fixed, min_size=body_min_size)

def _apply_ttk_ui_fonts(root: tk.Tk) -> None:
    """
    为 ttk 控件统一应用更清晰的 UI 字体，并根据字体行距调整 Treeview 行高。
    """
    try:
        style = ttk.Style(root)
        default_font = tkfont.nametofont("TkDefaultFont")
        heading_font = tkfont.nametofont("TkHeadingFont")

        # 常见 ttk 控件统一使用 UI 字体
        for cls in (
            "TLabel", "TButton", "TEntry", "TCombobox", "TCheckbutton",
            "TRadiobutton", "TMenubutton", "TNotebook", "TNotebook.Tab",
        ):
            try:
                style.configure(cls, font=default_font)
            except Exception:
                pass

        # LabelFrame 标题字体更清晰
        try:
            style.configure("TLabelframe.Label", font=heading_font)
        except Exception:
            pass

        # Treeview 内容与表头字体
        try:
            style.configure("Treeview", font=default_font)
        except Exception:
            pass

        # 兼容非 ttk 控件（如 tk.Text 等），通过 option_add 设置全局默认字体
        try:
            fam = default_font.cget("family")
            # Tk 需要整数字号；多词字体族需用花括号包裹
            size = int(default_font.cget("size"))
            root.option_add("*Font", f"{{{fam}}} {size}")
        except Exception:
            pass
        try:
            style.configure("Treeview.Heading", font=heading_font)
        except Exception:
            pass

        # 行高根据字体行距微调，避免文字被裁剪
        try:
            linespace = default_font.metrics("linespace")
            extra = 10
            try:
                _scaling = float(root.tk.call("tk", "scaling"))
                if _scaling >= 1.5:
                    extra = 14
            except Exception:
                pass
            row_h = max(22, int(linespace + extra))
            style.configure("Treeview", rowheight=row_h)
        except Exception:
            pass
    except Exception:
        pass

# 设置窗口居中
def center_window(window: Union[tk.Tk, tk.Toplevel]) -> None:
    """
    English: Centers the given window on the screen
    中文: 将指定窗口在屏幕上居中显示
    """
    window.update_idletasks()
    width: int = window.winfo_width()
    height: int = window.winfo_height()
    x: int = (window.winfo_screenwidth() // 2) - (width // 2)
    y: int = (window.winfo_screenheight() // 2) - (height // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


def _scaled_size(widget: tk.Misc, width: int, height: int) -> tuple[int, int]:
    """按照 Tk 当前 scaling 进行尺寸缩放（兼容高 DPI）。"""
    try:
        scale = float(widget.tk.call("tk", "scaling"))
        if scale <= 0:
            scale = 1.0
    except Exception:
        scale = 1.0
    try:
        return max(100, int(width * scale)), max(80, int(height * scale))
    except Exception:
        return width, height


# 检查任务计划是否存在
def check_task_exists(task_name: str) -> bool:
    """
    English: Checks if a scheduled task with the given name exists
    中文: 根据任务名称判断是否存在相应的计划任务
    """
    scheduler = win32com.client.Dispatch("Schedule.Service")
    scheduler.Connect()
    root_folder = scheduler.GetFolder("\\")
    for task in root_folder.GetTasks(0):
        if task.Name == task_name:
            return True
    return False

def open_keyboard_recorder(parent: Union[tk.Tk, tk.Toplevel], target_var: tk.StringVar) -> None:
    """
    通用“录制键盘组合”弹窗：
    - 在 parent 之上弹出
    - 实时显示已按下的组合并自动换行
    - Enter 完成（不会把 enter 计入组合），Esc 取消
    - 结果写入 target_var（形如：ctrl+alt+f）
    """
    rec = tk.Toplevel(parent)
    rec.title(t("录制键盘组合"))
    w, h = _scaled_size(rec, 580, 360)
    rec.geometry(f"{w}x{h}")

    msg_zh = (
        "请在此窗口按下要录制的组合键，\n"
        "按 Enter 完成，Esc 取消。\n"
        "支持：Ctrl/Alt/Shift/Win 与普通键。\n\n"
        "若不包含 +（加号），按字符序列逐个发送：例 f4 => f 然后 4。\n\n"
        "包含 + 时：字母段会按顺序逐个输入（例 qste）\n功能键（F1..F24、Tab、Enter、Esc 等）按原键发送。\n\n"
        "同时支持后缀 {down}/{up} 或 _down/_up 显式按下/抬起。\n"
        "提示：中文输入法状态下，仅记录英文字母/数字/功能键，中文字符将被忽略。\n"
        "示例：ctrl{down}+shift{down}+f4+shift{up}+d+ctrl{up}"
    )
    msg_en = (
        "Press the hotkey combo in this window.\n"
        "Enter to finish, Esc to cancel.\n"
        "Supported: Ctrl/Alt/Shift/Win and regular keys.\n\n"
        "If there is no '+', keys are sent as a character sequence (e.g. f4 => f then 4).\n\n"
        "With '+', letter segments are sent in order (e.g. qste).\n"
        "Function keys (F1..F24, Tab, Enter, Esc, etc.) are sent as-is.\n\n"
        "Suffixes {down}/{up} or _down/_up are also supported.\n"
        "Note: under Chinese IME, only ASCII keys are recorded; Chinese characters are ignored.\n"
        "Example: ctrl{down}+shift{down}+f4+shift{up}+d+ctrl{up}"
    )
    msg = ttk.Label(
        rec,
        text=(msg_en if LANG == "en" else msg_zh),
        justify="left",
    )
    msg.pack(padx=10, pady=8, anchor="w")

    # 记录按下顺序：允许重复键，使用列表保存顺序
    pressed_order: list[str] = []
    pressed_var = tk.StringVar(value=t("已按下：(空)"))
    # 使用 tk.Label 以获得 wraplength 自动换行能力
    pressed_lbl = tk.Label(
        rec, textvariable=pressed_var, fg="#555", anchor="w", justify="left", wraplength=320
    )
    pressed_lbl.pack(padx=10, pady=(0, 8), anchor="w", fill="x")

    normalize = {
        "control_l": "ctrl",
        "control_r": "ctrl",
        "control": "ctrl",
        "alt_l": "alt",
        "alt_r": "alt",
        "alt": "alt",
        "shift_l": "shift",
        "shift_r": "shift",
        "shift": "shift",
        "super_l": "win",
        "super_r": "win",
        "meta_l": "win",
        "meta_r": "win",
        "win_l": "win",
        "win_r": "win",
        "return": "enter",
        "escape": "esc",
    }

    def key_name(event_keysym: str) -> str:
        k = (event_keysym or "").lower()
        return normalize.get(k, k)

    def _current_keys() -> list[str]:
        return list(pressed_order)

    def _update_pressed_label():
        keys = _current_keys()
        if LANG == "en":
            pressed_var.set("Pressed: " + (" + ".join(keys) if keys else "(empty)"))
        else:
            pressed_var.set("已按下：" + (" + ".join(keys) if keys else "(空)"))

    def on_key_press(e):
        k = key_name(getattr(e, "keysym", ""))
        # 过滤非 ASCII（如中文输入法产生的字符名），仅保留英数字/功能键名
        if not k or not k.isascii():
            return
        pressed_order.append(k)
        _update_pressed_label()

    def on_key_release(e):
        pass

    def finish(*_):
        # 完成时忽略 Enter 本身；按按下顺序保存
        keys = [k for k in _current_keys() if k != "enter"]
        v = "+".join(keys)
        target_var.set(v)
        rec.destroy()

    def cancel(*_):
        rec.destroy()

    rec.bind("<KeyPress>", on_key_press)
    rec.bind("<KeyRelease>", on_key_release)
    rec.bind("<Return>", finish)
    rec.bind("<KP_Enter>", finish)
    rec.bind("<Escape>", cancel)

    def _on_rec_configure(event):
        try:
            pressed_lbl.configure(wraplength=max(100, event.width - 20))
        except Exception:
            pass

    rec.bind("<Configure>", _on_rec_configure)
    try:
        rec.focus_force()
    except Exception:
        pass
    center_window(rec)

    def _apply_lang_to_rec() -> None:
        if not rec.winfo_exists():
            return
        try:
            rec.title(t("录制键盘组合"))
        except Exception:
            pass
        try:
            msg.configure(text=(msg_en if LANG == "en" else msg_zh))
        except Exception:
            pass
        try:
            _update_pressed_label()
        except Exception:
            pass
        try:
            apply_language_to_widgets(rec)
        except Exception:
            pass

    register_lang_observer(_apply_lang_to_rec)
    _apply_lang_to_rec()


# 设置开机自启动
def set_auto_start() -> None:
    """
    English: Creates a scheduled task to auto-start the program upon logon or system start
    中文: 设置开机自启动，程序自动运行，提供两种方案选择
    """
    exe_path = os.path.join(
        os.path.dirname(os.path.abspath(sys.argv[0])), "RC-main.exe"
        # and "main.py"
    )

    # 检查文件是否存在
    if not os.path.exists(exe_path):
        messagebox.showerror(t("错误"), t("未找到 RC-main.exe 文件\n请检查文件是否存在"))
        return
    
    # 让用户选择两种方案
    choice = messagebox.askyesnocancel(
        t("选择启动方案"),
        t(
            "请选择以下两种启动方案之一：\n\n"
            + "【方案一】用户登录时运行\n注：无托盘时推荐!!\n"
            + "优点：只有用户登录时才运行\n"
            + "缺点：需要用户登录后才能启动\n\n"
            + "【方案二】系统启动时运行\n注：有托盘时推荐!!\n"
            + "优点：系统启动即可运行，无需用户登录\n"
            + "缺点：需要登录后托盘自动重启主程序才能使用媒体控制\n\n"
            + "选择 是：【方案一】\n\n选择 否：【方案二】"
        ),
        icon='question'
    )
      # 如果用户取消选择（点击右上角X），则退出设置过程
    if choice is None:
        messagebox.showinfo(t("已取消"), t("已取消设置开机自启动"))
        return

    def _run_schtasks(args: list[str]) -> int:
        try:
            cp = subprocess.run(["schtasks", *args], shell=False)
            return int(getattr(cp, "returncode", 1) or 0)
        except FileNotFoundError:
            return 1

    exe_cmd = exe_path
    
    if choice == True:  # 选择"是"，对应方案一
        # 方案一：使用Administrators用户组创建任务计划，任何用户登录时运行
        result = _run_schtasks(
            [
                "/Create",
                "/SC",
                "ONLOGON",
                "/TN",
                TASK_NAME_MAIN,
                "/TR",
                exe_cmd,
                "/RU",
                r"BUILTIN\Administrators",
                "/RL",
                "HIGHEST",
                "/F",
            ]
        )
    else:  # 选择"否"，对应方案二
        # 方案二：使用SYSTEM用户在系统启动时运行
        result = _run_schtasks(
            [
                "/Create",
                "/SC",
                "ONSTART",
                "/TN",
                TASK_NAME_MAIN,
                "/TR",
                exe_cmd,
                "/RU",
                "SYSTEM",
                "/RL",
                "HIGHEST",
                "/F",
            ]
        )
    # 清理可能存在的旧版中文任务名，忽略失败
    try:
        _run_schtasks(["/Delete", "/TN", "A远程控制", "/F"])
        _run_schtasks(["/Delete", "/TN", "A远程托盘", "/F"])
    except Exception:
        pass

    scheduler = win32com.client.Dispatch("Schedule.Service")
    scheduler.Connect()
    root_folder_main = scheduler.GetFolder("\\")
    task_definition = root_folder_main.GetTask(TASK_NAME_MAIN).Definition
    principal = task_definition.Principal
    # 根据选择的方案设置不同的登录类型和权限
    if choice == True:  # 选择"是"，对应方案一
        # 方案一：设置为用户组登录类型
        principal.LogonType = 3  # 3表示TASK_LOGON_GROUP，用户组登录
    else:  # 选择"否"，对应方案二
        # 方案二：设置为服务账户登录类型
        principal.LogonType = 5  # 5表示TASK_LOGON_SERVICE_ACCOUNT，服务账户登录
    
    principal.RunLevel = 1  # 最高权限
    settings = task_definition.Settings
    settings.MultipleInstances = 3  # 并行运行:0，排队：1，不运行：2，停止运行的：3
    settings.Hidden = False  # 确保不是隐藏运行
    settings.DisallowStartIfOnBatteries = False  # 不允许在电池供电时启动
    settings.StopIfGoingOnBatteries = False  # 允许在电池供电时启动
    settings.ExecutionTimeLimit = "PT0S"  # 无限时间限制
    # task_definition.Settings.Compatibility = 4    # 设置兼容性为 Windows 10
    root_folder_main.RegisterTaskDefinition(TASK_NAME_MAIN, task_definition, 6, "", "", 2)
    tray_exe_path = os.path.join(
            os.path.dirname(os.path.abspath(sys.argv[0])), "RC-tray.exe"
            # and "tray.py"
        )

    tray_result = 0
    if os.path.exists(tray_exe_path):
        tray_cmd = tray_exe_path  # 托盘程序使用当前登录用户（最高权限）运行，登录后触发
        tray_result = _run_schtasks(
            [
                "/Create",
                "/SC",
                "ONLOGON",
                "/TN",
                TASK_NAME_TRAY,
                "/TR",
                tray_cmd,
                "/RL",
                "HIGHEST",
                "/F",
            ]
        )
        # 同步设置权限和运行级别
        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        root_folder_tray = scheduler.GetFolder("\\")
        task_def = root_folder_tray.GetTask(TASK_NAME_TRAY).Definition
        settings_tray = task_def.Settings
        settings_tray.MultipleInstances = 0  # 并行运行:0，排队：1，不运行：2，停止运行的：3
        settings_tray.Hidden = False  # 确保不是隐藏运行
        settings_tray.DisallowStartIfOnBatteries = False  # 不允许在电池供电时启动
        settings_tray.StopIfGoingOnBatteries = False      # 允许在电池供电时启动
        settings_tray.ExecutionTimeLimit = "PT0S"         # 无限时间限制
        # task_def.Settings.Compatibility = 4

        root_folder_tray.RegisterTaskDefinition(
            TASK_NAME_TRAY, task_def, 6, "", "", 0  # 0表示只在用户登录时运行，2表示不管用户是否登录都运行
        )
        # if tray_result == 0:
        #     messagebox.showinfo("提示", "创建托盘任务成功(使用当前登录用户，最高权限运行)")
        # else:
        #     messagebox.showerror("错误", "创建托盘自启动失败")
    else:
        messagebox.showwarning(t("警告"), t("未找到 RC-tray.exe 文件，跳过托盘启动设置"))    # 检查创建任务的结果

    # 检查创建任务的结果
    if check_task_exists(TASK_NAME_MAIN):
        if choice == True:
            messagebox.showinfo(t("提示"), t("创建任务成功\n已配置为任何用户登录时以管理员组权限运行"))
        else:
            messagebox.showinfo(t("提示"), t("创建任务成功\n已配置为系统启动时以SYSTEM用户权限运行"))
            if tray_result != 0:
                messagebox.showwarning(
                    t("警告"),
                    t("创建托盘自启动失败\n{code}").format(code=tray_result),
                )
        messagebox.showinfo(t("提示"), t("移动文件位置后需重新设置任务哦！"))
        check_task()
    else:
        messagebox.showerror(
            t("错误"),
            t("创建开机自启动失败\n{code}").format(code=result),
        )
        check_task()


# 移除开机自启动
def remove_auto_start() -> None:
    """
    English: Removes the scheduled task for auto-start
    中文: 移除开机自启动的计划任务
    """
    if messagebox.askyesno(t("确定？"), t("你确定要删除开机自启动任务吗？")):
        delete_result = subprocess.run(
            ["schtasks", "/Delete", "/TN", TASK_NAME_MAIN, "/F"], shell=False
        ).returncode
        tray_delete = subprocess.run(
            ["schtasks", "/Delete", "/TN", TASK_NAME_TRAY, "/F"], shell=False
        ).returncode
        # 兼容清理旧中文任务名（若存在）
        try:
            subprocess.run(["schtasks", "/Delete", "/TN", "A远程控制", "/F"], shell=False)
            subprocess.run(["schtasks", "/Delete", "/TN", "A远程托盘", "/F"], shell=False)
        except Exception:
            pass
        if delete_result == 0 and tray_delete == 0:
            messagebox.showinfo(t("提示"), t("关闭所有自启动任务成功"))
        elif delete_result == 0:
            messagebox.showinfo(t("提示"), t("关闭主程序自启动成功，托盘任务不存在"))
        elif tray_delete == 0:
            messagebox.showinfo(t("提示"), t("关闭托盘自启动成功，主程序任务不存在"))
        else:
            messagebox.showerror(t("错误"), t("关闭开机自启动失败"))
        check_task()


# 检查是否有计划任务并更新按钮状态
def check_task() -> None:
    """
    English: Updates the button text based on whether the auto-start task exists
    中文: 检查是否存在开机自启任务，并更新按钮文字
    """
    src_text = "关闭开机自启" if check_task_exists(TASK_NAME_MAIN) else "设置开机自启"
    if check_task_exists(TASK_NAME_MAIN):
        auto_start_button.config(text=t(src_text), command=remove_auto_start)
    else:
        auto_start_button.config(text=t(src_text), command=set_auto_start)
    try:
        setattr(auto_start_button, "_rc_text_src", src_text)
    except Exception:
        pass
    auto_start_button.update_idletasks()


# 鼠标双击事件处理程序
def on_double_click(event: tk.Event) -> None:
    """
    English: Event handler for double-click on a custom theme tree item
    中文: 自定义主题列表项双击事件处理回调
    """
    modify_custom_theme()


# 如果配置中有自定义主题，加载它们
def load_custom_themes() -> None:
    """
    English: Loads user-defined themes from config and displays them in the tree
    中文: 从配置文件中读取自定义主题并展示到树状列表中
    """
    global config
    app_index = 1
    serve_index = 1
    command_index = 1
    while True:
        app_key = f"application{app_index}"
        if app_key in config:
            # 新结构: on_value / off_value / off_preset (kill/none) 兼容旧 value
            legacy_val = config.get(f"{app_key}_directory{app_index}", "")
            on_val = config.get(f"{app_key}_on_value", legacy_val)
            off_val = config.get(f"{app_key}_off_value", "")
            off_preset = config.get(f"{app_key}_off_preset", "kill")  # kill: 终止/中断；none: 不操作
            theme = {
                "type": "程序或脚本",
                "checked": config.get(f"{app_key}_checked", 0),
                "nickname": config.get(f"{app_key}_name", ""),
                "name": config.get(app_key, ""),
                "on_value": on_val,
                "off_value": off_val,
                "off_preset": off_preset,
            }
            custom_themes.append(theme)
            status = "开" if theme["checked"] else "关"
            display_name = theme["nickname"] or theme["name"]
            item_text = f"[{status}] {display_name}"
            tree_iid = str(len(custom_themes) - 1)
            custom_theme_tree.insert("", "end", iid=tree_iid, values=(item_text,))
            app_index += 1
        else:
            break
    while True:
        serve_key = f"serve{serve_index}"
        if serve_key in config:
            service_name = config.get(f"{serve_key}_value", "")
            on_val = config.get(f"{serve_key}_on_value", service_name)
            off_val = config.get(f"{serve_key}_off_value", "")
            off_preset = config.get(f"{serve_key}_off_preset", "stop")
            theme = {
                "type": "服务(需管理员权限)",
                "checked": config.get(f"{serve_key}_checked", 0),
                "nickname": config.get(f"{serve_key}_name", ""),
                "name": config.get(serve_key, ""),
                "value": service_name,
                "on_value": on_val,
                "off_value": off_val,
                "off_preset": off_preset,
            }
            custom_themes.append(theme)
            status = "开" if theme["checked"] else "关"
            display_name = theme["nickname"] or theme["name"]
            item_text = f"[{status}] {display_name}"
            tree_iid = str(len(custom_themes) - 1)
            custom_theme_tree.insert("", "end", iid=tree_iid, values=(item_text,))
            serve_index += 1
        else:
            break

    # 加载命令类型
    while True:
        cmd_key = f"command{command_index}"
        if cmd_key in config:
            legacy_cmd = config.get(f"{cmd_key}_value", "")
            on_cmd = config.get(f"{cmd_key}_on_value", legacy_cmd)
            off_cmd = config.get(f"{cmd_key}_off_value", "")
            off_preset = config.get(f"{cmd_key}_off_preset", "kill")

            _min_raw = config.get(f"{cmd_key}_value_min", 0)
            _max_raw = config.get(f"{cmd_key}_value_max", 100)
            try:
                _vmin = int(_min_raw)
            except Exception:
                _vmin = 0
            try:
                _vmax = int(_max_raw)
            except Exception:
                _vmax = 100
            if _vmin > _vmax:
                _vmin, _vmax = _vmax, _vmin

            theme = {
                "type": "命令",
                "checked": config.get(f"{cmd_key}_checked", 0),
                "nickname": config.get(f"{cmd_key}_name", ""),
                "name": config.get(cmd_key, ""),
                "on_value": on_cmd,
                "off_value": off_cmd,
                "off_preset": off_preset,
                "window": config.get(f"{cmd_key}_window", "show"),
                "value_min": _vmin,
                "value_max": _vmax,
            }
            custom_themes.append(theme)
            status = "开" if theme["checked"] else "关"
            display_name = theme["nickname"] or theme["name"]
            item_text = f"[{status}] {display_name}"
            tree_iid = str(len(custom_themes) - 1)
            custom_theme_tree.insert("", "end", iid=tree_iid, values=(item_text,))
            command_index += 1
        else:
            break

    # 加载 Hotkey 类型
    hotkey_index = 1
    while True:
        hk_key = f"hotkey{hotkey_index}"
        if hk_key in config:
            theme = {
                "type": "按键(Hotkey)",
                "checked": config.get(f"{hk_key}_checked", 0),
                "nickname": config.get(f"{hk_key}_name", ""),
                "name": config.get(hk_key, ""),
                "value": "",
                "on_type": config.get(f"{hk_key}_on_type", "keyboard"),
                "on_value": config.get(f"{hk_key}_on_value", ""),
                "off_type": config.get(f"{hk_key}_off_type", "none"),
                "off_value": config.get(f"{hk_key}_off_value", ""),
                "char_delay_ms": int(config.get(f"{hk_key}_char_delay_ms", 0) or 0),
            }
            custom_themes.append(theme)
            status = "开" if theme["checked"] else "关"
            display_name = theme["nickname"] or theme["name"]
            item_text = f"[{status}] {display_name}"
            tree_iid = str(len(custom_themes) - 1)
            custom_theme_tree.insert("", "end", iid=tree_iid, values=(item_text,))
            hotkey_index += 1
        else:
            break


_DETAIL_LAST_GEOM: str | None = None

def show_detail_window():
        """显示详细信息窗口（改进版：分栏、滚动、加大行距、段落留白）。"""
        global _DETAIL_LAST_GEOM
        win = tk.Toplevel(root)
        win.title(t("详情信息"))
        win.minsize(680, 520)
        # 恢复上次窗口尺寸
        if _DETAIL_LAST_GEOM:
                try:
                        win.geometry(_DETAIL_LAST_GEOM)
                except Exception:
                        pass
        else:
                w, h = _scaled_size(win, 760, 640)
                win.geometry(f"{w}x{h}")

        def _on_close():
                nonlocal win
                try:
                        geom = win.winfo_geometry()
                        # 只记录 宽x高+X+Y 结构
                        if geom:
                                # 去掉位置只保留宽高
                                parts = geom.split("+")
                                globals()["_DETAIL_LAST_GEOM"] = parts[0]
                except Exception:
                        pass
                win.destroy()

        win.protocol("WM_DELETE_WINDOW", _on_close)

        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=6, pady=6)

        def _fill_text(txt: tk.Text, content: str) -> None:
            try:
                txt.configure(state=tk.NORMAL)
            except Exception:
                pass
            try:
                txt.delete("1.0", tk.END)
            except Exception:
                return
            lines = content.strip().splitlines()
            for line in lines:
                striped = line.strip()
                if not striped:
                    txt.insert("end", "\n")
                    continue
                if striped.startswith("【") and striped.endswith("】"):
                    txt.insert("end", striped + "\n", ("section",))
                elif (striped.endswith("：") or striped.endswith(":")) and len(striped) < 40:
                    txt.insert("end", striped + "\n", ("sub",))
                else:
                    txt.insert("end", striped + "\n")
            txt.configure(state=tk.DISABLED)

        def make_text_tab(title_zh: str, content_zh: str, content_en: str) -> dict:
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=title_zh)
            # 使用 Text + Scrollbar 而非 scrolledtext（避免某些打包环境主题差异）
            txt = tk.Text(frame, wrap="word", undo=False, relief="flat", padx=8, pady=8)
            vsb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
            txt.configure(yscrollcommand=lambda *a: vsb.set(*a))
            vsb.pack(side="right", fill="y")
            txt.pack(side="left", fill="both", expand=True)

            # 字体：在系统默认字体基础上放大 + 行距
            base_font = tkfont.nametofont("TkDefaultFont").copy()
            size = max(10, base_font.cget("size"))
            try:
                base_font.configure(size=size + 1)
            except Exception:
                pass
            txt.configure(font=base_font, spacing1=4, spacing2=2, spacing3=6)

            # 插入内容并对标题/小节样式加粗
            txt.tag_config(
                "section",
                font=(base_font.cget("family"), base_font.cget("size") + 1, "bold"),
                spacing3=10,
            )
            txt.tag_config("sub", font=(base_font.cget("family"), base_font.cget("size"), "bold"))

            entry = {
                "frame": frame,
                "txt": txt,
                "title_zh": title_zh,
                "content_zh": content_zh,
                "content_en": content_en,
            }
            _fill_text(txt, content_en if LANG == "en" else content_zh)
            return entry

        builtin_content_zh = """
【内置主题概览】
屏幕：
    灯类型；调节系统亮度 (0-100)。

音量：
    窗帘类型；调节系统总音量 (0-100)，pause=静音。

媒体控制：
    窗帘类型；控制多媒体：
        on=上一曲  off=下一曲  pause=播放/暂停
        on#百分比：1-33 下一曲 / 34-66 播放暂停 / 67-100 上一曲。

睡眠主题：
    sleep / hibernate / display_off / display_on / lock；支持 on/off 延时。
"""

        builtin_content_en = """
【Built-in Themes Overview】
Screen:
    Light-type; adjust system brightness (0-100).

Volume:
    Curtain-type; adjust system master volume (0-100); pause = mute.

Media:
    Curtain-type; multimedia control:
        on=Previous  off=Next  pause=Play/Pause
        on#percent: 1-33 Next / 34-66 Play/Pause / 67-100 Previous.

Sleep:
    sleep / hibernate / display_off / display_on / lock; supports On/Off delay.
"""

        custom_content_zh = """
【自定义主题类型】
程序或脚本：
    “打开(on)”支持选择 EXE/.py/.ps1/.bat/.cmd 等；必要时自动补全解释器。
    “关闭(off)”可选预设（强制结束/忽略）或自定义脚本，切到自定义时可单独选文件。

服务(需管理员权限)：
    填写服务名称；“打开(on)”即启动，默认关闭预设为停止服务，可改为忽略或自定义命令。
    需管理员权限运行主程序/托盘，界面会提示不足权限。

命令：
    “打开(on)”为 PowerShell 片段，可随时点击测试按钮；
    支持 on#数字（默认 0-100，可在 config.json 中通过 commandN_value_min/commandN_value_max 自定义范围），命令中使用 {value} 占位符获取参数。
    关闭预设默认“中断”(CTRL+BREAK)，可改为强制结束或自定义并独立测试。

按键(Hotkey)：
    支持 ctrl/alt/shift/win 组合；可使用 {down}/{up} 形式；
    逐字符发送可设置间隔 (>=0)，保存时会提示非 ASCII 风险。
"""

        custom_content_en = """
【Custom Theme Types】
Program/Script:
    On supports selecting EXE/.py/.ps1/.bat/.cmd etc; interpreters may be auto-completed when needed.
    Off can use presets (Force kill/Ignore) or a custom script. When switching to Custom, you can pick a separate file.

Service (admin):
    Enter a Windows service name. On starts it; Off preset defaults to Stop service (can be Ignore or Custom command).
    Running main/tray as admin may be required; the UI will warn if permissions are insufficient.

Command:
    On is a PowerShell snippet; you can click the test button at any time.
    Supports on#number (default 0-100; configurable via commandN_value_min/commandN_value_max in config.json). Use the {value} placeholder in your command.
    Off preset defaults to Interrupt (CTRL+BREAK); you can change it to Force kill or Custom and test separately.

Hotkey:
    Supports ctrl/alt/shift/win combos; supports {down}/{up} suffixes.
    Char-by-char sending can be delayed (>=0); saving may warn about non-ASCII risks.
"""

        tips_content_zh = """
【使用与提示】
日志：
    issues 时附 logs/RC.log 便于排查。

更新：
    版本托盘菜单可手动检查；未知版本显示为 'V未知版本' 并提示升级。

权限：
    部分功能（服务/亮度/计划任务）需管理员；不足时界面会提示。

配置：
    GUI 保存后主程序自动读取；残留互斥体会自动忽略并继续。

多实例：
    主程序具互斥 + 进程确认；脚本模式可选择结束/忽略/退出。
"""

        tips_content_en = """
【Usage & Tips】
Logs:
    When reporting issues, attach logs/RC.log for troubleshooting.

Updates:
    You can manually check updates from the tray menu. Unknown versions show as 'VUnknown' with an upgrade prompt.

Permissions:
    Some features (Service/Brightness/Scheduled tasks) require admin; the UI will warn if missing.

Config:
    After saving in the GUI, the main program reads it automatically; leftover mutexes are ignored and it continues.

Multiple instances:
    The main program uses a mutex and process check; script mode can choose Kill/Ignore/Exit.
"""

        _detail_entries: list[dict] = []
        _detail_entries.append(make_text_tab("内置主题", builtin_content_zh, builtin_content_en))
        _detail_entries.append(make_text_tab("自定义主题", custom_content_zh, custom_content_en))
        _detail_entries.append(make_text_tab("提示说明", tips_content_zh, tips_content_en))

        center_window(win)

        def _apply_lang_to_detail() -> None:
            if not win.winfo_exists():
                return
            try:
                for ent in _detail_entries:
                    notebook.tab(ent["frame"], text=t(ent["title_zh"]))
                    _fill_text(ent["txt"], ent["content_en"] if LANG == "en" else ent["content_zh"])
            except Exception:
                pass
            try:
                win.title(t("详情信息"))
            except Exception:
                pass
            try:
                apply_language_to_widgets(win)
            except Exception:
                pass

        register_lang_observer(_apply_lang_to_detail)
        _apply_lang_to_detail()


def rebuild_custom_theme_tree() -> None:
    """
    重新构建自定义主题树视图，确保索引正确
    """
    # 清空树视图中的所有项目
    for item in custom_theme_tree.get_children():
        custom_theme_tree.delete(item)
    
    # 重新插入所有主题，使用正确的索引
    for index, theme in enumerate(custom_themes):
        status = "开" if theme["checked"] else "关"
        display_name = theme["nickname"] or theme["name"]
        item_text = f"[{status}] {display_name}"
        custom_theme_tree.insert("", "end", iid=str(index), values=(item_text,))


# 修改自定义主题的函数
def modify_custom_theme() -> None:
    """
    English: Opens a new window to modify selected custom theme
    中文: 打开新窗口修改已选定的自定义主题
    """
    selected = custom_theme_tree.selection()
    if not selected:
        messagebox.showwarning(t("警告"), t("请先选择一个自定义主题"))
        return

    index = int(selected[0])
    theme = custom_themes[index]

    theme_window = tk.Toplevel(root)
    theme_window.title(t("修改自定义主题"))
    # 增加默认高度
    try:
        w, h = _scaled_size(theme_window, 780, 360)
        theme_window.geometry(f"{w}x{h}")
    except Exception:
        pass
    PADX = 10
    PADY = 6
    # 允许窗口大小调整，并设置网格权重使输入控件随窗口拉伸
    theme_window.resizable(True, True)
    try:
        theme_window.columnconfigure(0, weight=0)
        theme_window.columnconfigure(1, weight=1)
        theme_window.columnconfigure(2, weight=0)
        theme_window.columnconfigure(3, weight=0)
    except Exception:
        pass

    ttk.Label(theme_window, text="类型：").grid(row=0, column=0, sticky="e", padx=PADX, pady=PADY)
    _type_keys = ["程序或脚本", "服务(需管理员权限)", "命令", "按键(Hotkey)"]
    _initial_type_key = theme.get("type") or "程序或脚本"
    if _initial_type_key not in _type_keys:
        _initial_type_key = "程序或脚本"
    theme_type_key_var = tk.StringVar(value=_initial_type_key)  # 内部值（保持中文 key）
    theme_type_var = tk.StringVar(value=t(_initial_type_key))  # 显示值（随语言变化）

    def _type_labels() -> list[str]:
        return [t(k) for k in _type_keys]

    def _type_key_by_label(label: str) -> str:
        m = {t(k): k for k in _type_keys}
        return m.get(label, "程序或脚本")

    def _type_label_by_key(key: str) -> str:
        if key not in _type_keys:
            key = "程序或脚本"
            theme_type_key_var.set(key)
        return t(key)

    theme_type_combobox = ttk.Combobox(
        theme_window,
        textvariable=theme_type_var,
        values=_type_labels(),
        state="readonly",
    )
    theme_type_combobox.grid(row=0, column=1, sticky="we", padx=(0, PADX), pady=PADY)
    try:
        theme_type_combobox.current(_type_keys.index(_initial_type_key))
    except Exception:
        theme_type_combobox.current(0)
        theme_type_key_var.set("程序或脚本")
        theme_type_var.set(t("程序或脚本"))

    ttk.Label(theme_window, text="服务时主程序").grid(row=0, column=2, sticky="w", padx=PADX, pady=PADY)
    ttk.Label(theme_window, text="需管理员权限").grid(row=1, column=2, sticky="w", padx=PADX, pady=PADY)

    ttk.Label(theme_window, text="状态：").grid(row=1, column=0, sticky="e", padx=PADX, pady=PADY)
    theme_checked_var = tk.IntVar(value=theme["checked"])
    ttk.Checkbutton(theme_window, variable=theme_checked_var).grid(
        row=1, column=1, sticky="w", padx=(0, PADX), pady=PADY
    )

    ttk.Label(theme_window, text="昵称：").grid(row=2, column=0, sticky="e", padx=PADX, pady=PADY)
    theme_nickname_entry = ttk.Entry(theme_window)
    theme_nickname_entry.insert(0, theme["nickname"])
    theme_nickname_entry.grid(row=2, column=1, sticky="we", padx=(0, PADX), pady=PADY)

    ttk.Label(theme_window, text="主题：").grid(row=3, column=0, sticky="e", padx=PADX, pady=PADY)
    theme_name_entry = ttk.Entry(theme_window)
    theme_name_entry.insert(0, theme["name"])
    theme_name_entry.grid(row=3, column=1, sticky="we", padx=(0, PADX), pady=PADY)

    # 新: 程序/命令类型拆分 ON/OFF 与关闭预设；Hotkey 保持原样
    on_label_mod = ttk.Label(theme_window, text="打开(on)：")
    on_label_mod.grid(row=4, column=0, sticky="e", padx=PADX, pady=PADY)
    on_frame_mod = ttk.Frame(theme_window)
    on_frame_mod.grid(row=4, column=1, sticky="nsew", padx=(0, PADX), pady=PADY)
    try:
        theme_window.rowconfigure(4, weight=2)
    except Exception:
        pass
    on_value_text = tk.Text(on_frame_mod, height=3, wrap="word")
    on_value_text.insert("1.0", theme.get("on_value", theme.get("value", "")))
    on_value_text.grid(row=0, column=0, sticky="nsew")
    on_scroll_y = ttk.Scrollbar(on_frame_mod, orient="vertical", command=on_value_text.yview)
    on_scroll_y.grid(row=0, column=1, sticky="ns")
    on_value_text.configure(yscrollcommand=on_scroll_y.set)
    try:
        on_frame_mod.columnconfigure(0, weight=1)
        on_frame_mod.rowconfigure(0, weight=1)
    except Exception:
        pass

    off_label_mod = ttk.Label(theme_window, text="关闭(off)：")
    off_label_mod.grid(row=5, column=0, sticky="e", padx=PADX, pady=PADY)
    off_frame_mod = ttk.Frame(theme_window)
    off_frame_mod.grid(row=5, column=1, sticky="nsew", padx=(0, PADX), pady=PADY)
    off_value_text = tk.Text(off_frame_mod, height=3, wrap="word")
    off_value_text.insert("1.0", theme.get("off_value", ""))
    off_value_text.grid(row=0, column=0, sticky="nsew")
    off_scroll_y = ttk.Scrollbar(off_frame_mod, orient="vertical", command=off_value_text.yview)
    off_scroll_y.grid(row=0, column=1, sticky="ns")
    off_value_text.configure(yscrollcommand=off_scroll_y.set)
    try:
        off_frame_mod.columnconfigure(0, weight=1)
        off_frame_mod.rowconfigure(0, weight=1)
    except Exception:
        pass

    off_preset_label_mod = ttk.Label(theme_window, text="关闭预设：")
    off_preset_label_mod.grid(row=6, column=0, sticky="e", padx=PADX, pady=PADY)
    # 关闭预设：内部 code + 显示 label 分离
    _preset_label_zh_by_code = {
        "none": "忽略",
        "kill": "强制结束",
        "interrupt": "中断",
        "stop": "停止服务",
        "custom": "自定义",
    }

    def _default_preset_code_for_type(t_type: str) -> str:
        if t_type == "命令":
            return "interrupt"
        if t_type == "程序或脚本":
            return "kill"
        if t_type == "服务(需管理员权限)":
            return "stop"
        return "none"

    def _preset_codes_for_type(t_type: str) -> tuple[str, ...]:
        if t_type == "命令":
            return ("none", "interrupt", "kill", "custom")
        if t_type == "程序或脚本":
            return ("none", "kill", "custom")
        if t_type == "服务(需管理员权限)":
            return ("none", "stop", "custom")
        return ("none",)

    def _preset_labels_for_type(t_type: str) -> list[str]:
        return [t(_preset_label_zh_by_code[c]) for c in _preset_codes_for_type(t_type)]

    def _preset_code_by_label(label: str) -> str:
        m = {t(v): k for k, v in _preset_label_zh_by_code.items()}
        return m.get(label, "none")

    def _preset_label_by_code(code: str) -> str:
        return t(_preset_label_zh_by_code.get(code, "忽略"))

    _t0 = theme_type_key_var.get()
    preset_internal_default = theme.get("off_preset", _default_preset_code_for_type(_t0))
    if preset_internal_default not in _preset_label_zh_by_code:
        preset_internal_default = _default_preset_code_for_type(_t0)
    off_preset_key_var_mod = tk.StringVar(value=preset_internal_default)
    off_preset_var_mod = tk.StringVar(value=_preset_label_by_code(preset_internal_default))

    off_preset_combo_mod = ttk.Combobox(
        theme_window,
        textvariable=off_preset_var_mod,
        state="readonly",
        values=_preset_labels_for_type(_t0),
    )
    off_preset_combo_mod.grid(row=6, column=1, sticky="w", padx=(0, PADX), pady=PADY)

    # 记录自定义内容以便在预设与自定义切换时还原
    previous_custom_off_value_mod = theme.get("off_value", "")
    def _preview_text_for_mod(code: str, t_type: str, service_name: str = "") -> str:
        if LANG == "en":
            if t_type == "命令":
                if code == "interrupt":
                    return "Preset: Interrupt — Sends CTRL+BREAK to the last recorded command process and tries to exit gracefully."
                if code == "kill":
                    return "Preset: Force kill — Kills all recorded command processes (kill/taskkill)."
                return "Preset: Ignore — No off action will be performed."
            if t_type == "程序或脚本":
                if code == "kill":
                    return "Preset: Force kill — Tries to terminate the process/script derived from the On target (cmd/bat enhanced, ps1 dedicated, otherwise taskkill /IM)."
                return "Preset: Ignore — No off action will be performed."
            if t_type == "服务(需管理员权限)":
                if code == "stop":
                    svc = service_name or "the specified service"
                    return f"Preset: Stop service — Runs: sc stop {svc}."
                return "Preset: Ignore — No off action will be performed."
            return "Preset: Ignore — No off action will be performed."

        # zh
        if t_type == "命令":
            if code == "interrupt":
                return "预设：中断 — 向最新记录的命令进程发送 CTRL+BREAK，并尝试优雅结束。"
            if code == "kill":
                return "预设：强制结束 — 结束所有记录的命令进程（kill/taskkill）。"
            return "预设：忽略 — 不执行任何关闭动作。"
        if t_type == "程序或脚本":
            if code == "kill":
                return "预设：强制结束 — 将尝试结束由“打开(on)”目标派生的脚本/进程（cmd/bat 优先增强终止，ps1 专用终止，其它 taskkill /IM）。"
            return "预设：忽略 — 不执行任何关闭动作。"
        if t_type == "服务(需管理员权限)":
            if code == "stop":
                svc = service_name or "指定服务"
                return f"预设：停止服务 — 使用 sc stop {svc} 停止服务。"
            return "预设：忽略 — 不执行任何关闭动作。"
        return "预设：忽略 — 不执行任何关闭动作。"

    def _update_off_editability_mod(*_):
        nonlocal previous_custom_off_value_mod
        code = off_preset_key_var_mod.get() or "none"
        t_type = theme_type_key_var.get()
        try:
            if code == "custom":
                # 从预览切回自定义，恢复用户之前的输入
                off_value_text.configure(state=tk.NORMAL)
                try:
                    off_value_text.delete("1.0", tk.END)
                    off_value_text.insert("1.0", previous_custom_off_value_mod)
                except Exception:
                    pass
            else:
                # 切换到预设，先缓存自定义内容
                try:
                    if str(off_value_text.cget("state")) == str(tk.NORMAL):
                        _cur = off_value_text.get("1.0", "end-1c")
                        if _cur.strip():
                            previous_custom_off_value_mod = _cur
                except Exception:
                    pass
                # 写入预览说明并禁用
                try:
                    off_value_text.configure(state=tk.NORMAL)
                    off_value_text.delete("1.0", tk.END)
                    service_name = on_value_text.get("1.0", "end-1c").strip()
                    off_value_text.insert("1.0", _preview_text_for_mod(code, t_type, service_name))
                except Exception:
                    pass
                off_value_text.configure(state=tk.DISABLED)
        except Exception:
            pass
        try:
            if t_type == "程序或脚本" and code == "custom":
                off_action_btn_mod.state(["!disabled"])
            elif t_type == "命令" and code == "custom":
                off_action_btn_mod.state(["!disabled"])
            else:
                off_action_btn_mod.state(["disabled"])
        except Exception:
            pass

    def _on_off_preset_selected_mod(_event=None):
        off_preset_key_var_mod.set(_preset_code_by_label(off_preset_var_mod.get()))
        _update_off_editability_mod()

    off_preset_combo_mod.bind("<<ComboboxSelected>>", _on_off_preset_selected_mod)

    def select_file():
        file_path = filedialog.askopenfilename()
        if file_path:
            # 根据类型写入到 on_value 文本框
            try:
                on_value_text.delete("1.0", tk.END)
                on_value_text.insert("1.0", file_path)
            except Exception:
                pass

    def open_services():
        try:
            os.startfile("services.msc")
        except Exception:
            try:
                subprocess.Popen(["services.msc"])  # 备用方式
            except Exception as e:
                messagebox.showerror(t("错误"), t("无法打开服务管理器: {err}").format(err=e))

    # 命令类型：{value} 参数范围（默认 0-100，可配置）
    cmd_value_min_var_add = tk.StringVar(value="0")
    cmd_value_max_var_add = tk.StringVar(value="100")

    def _get_cmd_value_range_add() -> tuple[int, int]:
        try:
            lo = int((cmd_value_min_var_add.get() or "0").strip())
            hi = int((cmd_value_max_var_add.get() or "100").strip())
        except Exception:
            messagebox.showwarning(t("提示"), t("请输入整数"))
            return 0, 100
        if lo > hi:
            lo, hi = hi, lo
        return lo, hi

    def _ask_value_for_placeholder_add(parent_win: tk.Misc) -> str | None:
        lo, hi = _get_cmd_value_range_add()
        ex = 50
        if ex < lo or ex > hi:
            ex = lo
        s = simpledialog.askstring(
            t("输入参数"),
            t("请输入 {value} 的值（范围 {lo}-{hi}），例如 {ex}：").format(value="{value}", lo=lo, hi=hi, ex=ex),
            initialvalue=str(ex),
            parent=parent_win,
        )
        if s is None:
            return None
        s = str(s).strip()
        try:
            v = int(s)
        except Exception:
            messagebox.showwarning(t("提示"), t("请输入整数"))
            return None
        if v < lo or v > hi:
            messagebox.showwarning(t("提示"), t("参数超出范围：{lo}-{hi}").format(lo=lo, hi=hi))
            return None
        return str(v)

    # 命令类型：{value} 参数范围（默认 0-100，可配置）
    cmd_value_min_var = tk.StringVar(value=str(int(theme.get("value_min", 0) or 0)))
    cmd_value_max_var = tk.StringVar(value=str(int(theme.get("value_max", 100) or 100)))

    def _get_cmd_value_range_mod() -> tuple[int, int]:
        try:
            lo = int((cmd_value_min_var.get() or "0").strip())
            hi = int((cmd_value_max_var.get() or "100").strip())
        except Exception:
            messagebox.showwarning(t("提示"), t("请输入整数"))
            return 0, 100
        if lo > hi:
            lo, hi = hi, lo
        return lo, hi

    def _ask_value_for_placeholder_mod(parent_win: tk.Misc) -> str | None:
        lo, hi = _get_cmd_value_range_mod()
        ex = 50
        if ex < lo or ex > hi:
            ex = lo
        s = simpledialog.askstring(
            t("输入参数"),
            t("请输入 {value} 的值（范围 {lo}-{hi}），例如 {ex}：").format(value="{value}", lo=lo, hi=hi, ex=ex),
            initialvalue=str(ex),
            parent=parent_win,
        )
        if s is None:
            return None
        s = str(s).strip()
        try:
            v = int(s)
        except Exception:
            messagebox.showwarning(t("提示"), t("请输入整数"))
            return None
        if v < lo or v > hi:
            messagebox.showwarning(t("提示"), t("参数超出范围：{lo}-{hi}").format(lo=lo, hi=hi))
            return None
        return str(v)

    def test_command_in_powershell():
        cmd = on_value_text.get("1.0", "end-1c").strip()
        if not cmd:
            messagebox.showwarning(t("提示"), t("请先在“值”中输入要测试的命令"))
            return
        if "{value}" in cmd:
            val = _ask_value_for_placeholder_mod(theme_window)
            if val is None:
                return
            cmd = cmd.replace("{value}", val)
        cmd = _normalize_command_for_powershell(cmd)
        # 在 PowerShell 中显示命令，等待用户按回车后再执行
        if LANG == "en":
            ps_script = (
                "Write-Host 'Ready to test command:' -ForegroundColor Cyan;"
                "\n$cmd = @'\n" + cmd.replace("'@", "'@@") + "\n'@;"
                "\nWrite-Host $cmd -ForegroundColor Yellow;"
                "\nRead-Host 'Press Enter to run';"
                "\nWrite-Host 'Running...' -ForegroundColor Green;"
                "\ntry { iex $cmd } catch { Write-Host ('Error: ' + $_.Exception.Message) -ForegroundColor Red }"
            )
        else:
            ps_script = (
                "Write-Host '已准备好要测试的命令：' -ForegroundColor Cyan;"
                "\n$cmd = @'\n" + cmd.replace("'@", "'@@") + "\n'@;"
                "\nWrite-Host $cmd -ForegroundColor Yellow;"
                "\nRead-Host '按回车后执行';"
                "\nWrite-Host '正在执行...' -ForegroundColor Green;"
                "\ntry { iex $cmd } catch { Write-Host ('发生错误: ' + $_.Exception.Message) -ForegroundColor Red }"
            )
        try:
            subprocess.Popen(
                ["powershell.exe", "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except Exception as e:
            messagebox.showerror(t("错误"), t("无法启动 PowerShell: {err}").format(err=e))

    select_file_btn_mod = ttk.Button(theme_window, text="选择文件", command=select_file)
    select_file_btn_mod.grid(row=4, column=2, sticky="w", padx=PADX, pady=PADY)
    def select_off_file():
        nonlocal previous_custom_off_value_mod
        file_path = filedialog.askopenfilename()
        if file_path:
            try:
                if (off_preset_key_var_mod.get() or "none") != "custom":
                    off_preset_key_var_mod.set("custom")
                    off_preset_var_mod.set(_preset_label_by_code("custom"))
                previous_custom_off_value_mod = file_path
                off_value_text.configure(state=tk.NORMAL)
                off_value_text.delete("1.0", tk.END)
                off_value_text.insert("1.0", file_path)
            except Exception:
                pass
            _update_off_editability_mod()

    def test_off_command_in_powershell():
        if (off_preset_key_var_mod.get() or "none") != "custom":
            messagebox.showwarning(t("提示"), t("请先将关闭预设切换为“自定义”并填写命令"))
            return
        try:
            off_value_text.configure(state=tk.NORMAL)
        except Exception:
            pass
        cmd = off_value_text.get("1.0", "end-1c").strip()
        if not cmd:
            messagebox.showwarning(t("提示"), t("请先在“关闭(off)”中输入要测试的命令"))
            return
        if "{value}" in cmd:
            val = _ask_value_for_placeholder_mod(theme_window)
            if val is None:
                return
            cmd = cmd.replace("{value}", val)
        cmd = _normalize_command_for_powershell(cmd)
        if LANG == "en":
            ps_script = (
                "Write-Host 'Ready to test command:' -ForegroundColor Cyan;"
                "\n$cmd = @'\n" + cmd.replace("'@", "'@@") + "\n'@;"
                "\nWrite-Host $cmd -ForegroundColor Yellow;"
                "\nRead-Host 'Press Enter to run';"
                "\nWrite-Host 'Running...' -ForegroundColor Green;"
                "\ntry { iex $cmd } catch { Write-Host ('Error: ' + $_.Exception.Message) -ForegroundColor Red }"
            )
        else:
            ps_script = (
                "Write-Host '已准备好要测试的命令：' -ForegroundColor Cyan;"
                "\n$cmd = @'\n" + cmd.replace("'@", "'@@") + "\n'@;"
                "\nWrite-Host $cmd -ForegroundColor Yellow;"
                "\nRead-Host '按回车后执行';"
                "\nWrite-Host '正在执行...' -ForegroundColor Green;"
                "\ntry { iex $cmd } catch { Write-Host ('发生错误: ' + $_.Exception.Message) -ForegroundColor Red }"
            )
        try:
            subprocess.Popen(
                ["powershell.exe", "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except Exception as e:
            messagebox.showerror(t("错误"), t("无法启动 PowerShell: {err}").format(err=e))

    off_action_btn_mod = ttk.Button(theme_window, text="选择文件", command=select_off_file)
    off_action_btn_mod.grid(row=5, column=2, sticky="w", padx=PADX, pady=PADY)
    _update_off_editability_mod()

    # 垂直方向自适应：占位扩展区，推开底部按钮
    try:
        theme_window.rowconfigure(7, weight=1)
        _spacer_mod = ttk.Frame(theme_window)
        _spacer_mod.grid(row=7, column=0, columnspan=4, sticky="nsew")
    except Exception:
        pass

    # 命令类型：命令窗口显示/隐藏 -> 改为复选框，放在“状态”后面
    cmd_window_var = tk.IntVar(value=0 if theme.get("window", "show") == "hide" else 1)
    cmd_window_check = ttk.Checkbutton(theme_window, text="显示窗口", variable=cmd_window_var)

    cmd_range_frame_mod = ttk.Frame(theme_window)
    ttk.Label(cmd_range_frame_mod, text=t("value 参数范围：")).grid(row=0, column=0, sticky="w")
    ttk.Label(cmd_range_frame_mod, text=t("最小：")).grid(row=0, column=1, sticky="e", padx=(8, 2))
    cmd_min_entry_mod = ttk.Entry(cmd_range_frame_mod, textvariable=cmd_value_min_var, width=8)
    cmd_min_entry_mod.grid(row=0, column=2, sticky="w")
    ttk.Label(cmd_range_frame_mod, text=t("最大：")).grid(row=0, column=3, sticky="e", padx=(10, 2))
    cmd_max_entry_mod = ttk.Entry(cmd_range_frame_mod, textvariable=cmd_value_max_var, width=8)
    cmd_max_entry_mod.grid(row=0, column=4, sticky="w")

    # Hotkey 专用设置（修改窗口）
    hotkey_frame_mod = ttk.Labelframe(theme_window, text="按键(Hotkey) 设置")
    hk_type_items = [
        ("none", "不执行"),
        ("keyboard", "键盘组合"),
    ]

    def _hk_type_labels_mod() -> list[str]:
        return [t(zh) for _, zh in hk_type_items]

    def _hk_type_key_by_label_mod(label: str) -> str:
        m = {t(zh): k for k, zh in hk_type_items}
        return m.get(label, "none")

    def _hk_type_label_by_key_mod(key: str) -> str:
        zh = next((zh for k, zh in hk_type_items if k == key), "不执行")
        return t(zh)

    hk_on_type_key_var_mod = tk.StringVar(value=theme.get("on_type", "keyboard") or "keyboard")
    hk_on_type_var_mod = tk.StringVar(value=_hk_type_label_by_key_mod(hk_on_type_key_var_mod.get()))
    hk_on_val_var_mod = tk.StringVar(value=theme.get("on_value", ""))

    hk_off_type_key_var_mod = tk.StringVar(value=theme.get("off_type", "none") or "none")
    hk_off_type_var_mod = tk.StringVar(value=_hk_type_label_by_key_mod(hk_off_type_key_var_mod.get()))
    hk_off_val_var_mod = tk.StringVar(value=theme.get("off_value", ""))
    hk_char_delay_var_mod = tk.StringVar(value=str(theme.get("char_delay_ms", 0)))

    ttk.Label(hotkey_frame_mod, text="打开(on)：").grid(row=0, column=0, sticky="e", padx=8, pady=4)
    hk_on_type_combo_mod = ttk.Combobox(hotkey_frame_mod, values=_hk_type_labels_mod(), textvariable=hk_on_type_var_mod, state="readonly", width=12)
    hk_on_type_combo_mod.grid(row=0, column=1, sticky="w")
    hk_on_entry_mod = ttk.Entry(hotkey_frame_mod, textvariable=hk_on_val_var_mod, width=24)
    hk_on_entry_mod.grid(row=0, column=2, sticky="w")
    ttk.Button(hotkey_frame_mod, text="录制", command=lambda: open_keyboard_recorder(theme_window, hk_on_val_var_mod)).grid(row=0, column=3, sticky="w")

    ttk.Label(hotkey_frame_mod, text="关闭(off)：").grid(row=1, column=0, sticky="e", padx=8, pady=4)
    hk_off_type_combo_mod = ttk.Combobox(hotkey_frame_mod, values=_hk_type_labels_mod(), textvariable=hk_off_type_var_mod, state="readonly", width=12)
    hk_off_type_combo_mod.grid(row=1, column=1, sticky="w")
    hk_off_entry_mod = ttk.Entry(hotkey_frame_mod, textvariable=hk_off_val_var_mod, width=24)
    hk_off_entry_mod.grid(row=1, column=2, sticky="w")
    ttk.Button(hotkey_frame_mod, text="录制", command=lambda: open_keyboard_recorder(theme_window, hk_off_val_var_mod)).grid(row=1, column=3, sticky="w")

    ttk.Label(hotkey_frame_mod, text="字母段间隔(ms)：").grid(row=2, column=0, sticky="e", padx=8, pady=4)
    hk_char_delay_entry_mod = ttk.Entry(hotkey_frame_mod, textvariable=hk_char_delay_var_mod, width=12)
    hk_char_delay_entry_mod.grid(row=2, column=1, sticky="w")

    def _on_hk_on_type_selected_mod(_event=None):
        hk_on_type_key_var_mod.set(_hk_type_key_by_label_mod(hk_on_type_var_mod.get()))
        hk_on_type_var_mod.set(_hk_type_label_by_key_mod(hk_on_type_key_var_mod.get()))

    def _on_hk_off_type_selected_mod(_event=None):
        hk_off_type_key_var_mod.set(_hk_type_key_by_label_mod(hk_off_type_var_mod.get()))
        hk_off_type_var_mod.set(_hk_type_label_by_key_mod(hk_off_type_key_var_mod.get()))

    hk_on_type_combo_mod.bind("<<ComboboxSelected>>", _on_hk_on_type_selected_mod)
    hk_off_type_combo_mod.bind("<<ComboboxSelected>>", _on_hk_off_type_selected_mod)

    def _update_type_specific_mod(*_):
        type_key = theme_type_key_var.get()
        if type_key == "命令":
            cmd_window_check.grid(row=1, column=1, sticky="n")
            # 放到“关闭预设”同一行右侧
            cmd_range_frame_mod.grid(row=6, column=1, columnspan=2, sticky="n", padx=(0, PADX), pady=PADY)
        else:
            cmd_window_check.grid_remove()
            cmd_range_frame_mod.grid_remove()
        if type_key == "按键(Hotkey)":
            on_label_mod.grid_remove()
            off_label_mod.grid_remove()
            on_frame_mod.grid_remove()
            off_frame_mod.grid_remove()
            off_preset_combo_mod.grid_remove()
            try:
                off_preset_label_mod.grid_remove()
            except Exception:
                pass
            hotkey_frame_mod.grid(row=4, column=1, columnspan=2, sticky="we")
            select_file_btn_mod.grid_remove()
            off_action_btn_mod.state(["disabled"])
            off_action_btn_mod.grid_remove()
        else:
            hotkey_frame_mod.grid_remove()
            on_label_mod.grid(row=4, column=0, sticky="e")
            on_frame_mod.grid(row=4, column=1, sticky="nsew")
            off_label_mod.grid(row=5, column=0, sticky="e")
            off_frame_mod.grid(row=5, column=1, sticky="nsew")
            off_preset_label_mod.grid(row=6, column=0, sticky="e")
            # 根据类型刷新可选值（保持内部 code 不变）
            values_now = _preset_labels_for_type(type_key)
            off_preset_combo_mod.configure(values=values_now)
            allowed_codes = _preset_codes_for_type(type_key)
            cur_code = off_preset_key_var_mod.get() or "none"
            if cur_code not in allowed_codes:
                cur_code = _default_preset_code_for_type(type_key)
                if cur_code not in allowed_codes:
                    cur_code = allowed_codes[0]
                off_preset_key_var_mod.set(cur_code)
            off_preset_var_mod.set(_preset_label_by_code(off_preset_key_var_mod.get() or "none"))
            off_preset_combo_mod.grid(row=6, column=1, sticky="w")
            # 根据类型设置按钮文本与功能
            if type_key == "程序或脚本":
                select_file_btn_mod.configure(text=t("选择文件"), command=select_file)
                select_file_btn_mod.grid(row=4, column=2, sticky="w", padx=15)
                off_action_btn_mod.configure(text=t("选择文件"), command=select_off_file)
                off_action_btn_mod.grid(row=5, column=2, sticky="w", padx=15)
            elif type_key == "服务(需管理员权限)":
                select_file_btn_mod.configure(text=t("打开服务"), command=open_services)
                select_file_btn_mod.grid(row=4, column=2, sticky="w", padx=15)
                off_action_btn_mod.state(["disabled"])
                off_action_btn_mod.grid_remove()
            elif type_key == "命令":
                select_file_btn_mod.configure(text=t("PowerShell测试"), command=test_command_in_powershell)
                select_file_btn_mod.grid(row=4, column=2, sticky="w", padx=15)
                off_action_btn_mod.configure(text=t("PowerShell测试(关闭)"), command=test_off_command_in_powershell)
                off_action_btn_mod.grid(row=5, column=2, sticky="w", padx=15)
            else:
                select_file_btn_mod.grid_remove()
                off_action_btn_mod.state(["disabled"])
                off_action_btn_mod.grid_remove()
            _update_off_editability_mod()

    theme_type_combobox.bind("<<ComboboxSelected>>", _update_type_specific_mod)
    _update_type_specific_mod()

    def _on_theme_type_selected_mod(_event=None):
        theme_type_key_var.set(_type_key_by_label(theme_type_var.get()))
        theme_type_var.set(_type_label_by_key(theme_type_key_var.get()))
        _update_type_specific_mod()

    # 覆盖绑定：先同步内部 key，再刷新 UI
    theme_type_combobox.bind("<<ComboboxSelected>>", _on_theme_type_selected_mod)

    def _refresh_type_and_preset_i18n_mod() -> None:
        try:
            theme_type_combobox.configure(values=_type_labels())
            # 维持当前选择
            cur_type_key = theme_type_key_var.get() or "程序或脚本"
            if cur_type_key not in _type_keys:
                cur_type_key = "程序或脚本"
                theme_type_key_var.set(cur_type_key)
            theme_type_var.set(_type_label_by_key(cur_type_key))
            try:
                theme_type_combobox.current(_type_keys.index(cur_type_key))
            except Exception:
                pass
        except Exception:
            pass
        try:
            t_key = theme_type_key_var.get() or "程序或脚本"
            off_preset_combo_mod.configure(values=_preset_labels_for_type(t_key))
            off_preset_var_mod.set(_preset_label_by_code(off_preset_key_var_mod.get() or "none"))
        except Exception:
            pass

        # Hotkey 下拉选项刷新
        try:
            hk_on_type_combo_mod.configure(values=_hk_type_labels_mod())
            hk_off_type_combo_mod.configure(values=_hk_type_labels_mod())
            hk_on_type_var_mod.set(_hk_type_label_by_key_mod(hk_on_type_key_var_mod.get()))
            hk_off_type_var_mod.set(_hk_type_label_by_key_mod(hk_off_type_key_var_mod.get()))
        except Exception:
            pass

        # 如果当前是预设（非 custom），则更新预设说明文本语言
        try:
            t_type = theme_type_key_var.get()
            code = off_preset_key_var_mod.get() or "none"
            if code != "custom":
                service_name = on_value_text.get("1.0", "end-1c").strip()
                off_value_text.configure(state=tk.NORMAL)
                off_value_text.delete("1.0", tk.END)
                off_value_text.insert("1.0", _preview_text_for_mod(code, t_type, service_name))
                off_value_text.configure(state=tk.DISABLED)
        except Exception:
            pass

    def save_theme():
        theme["type"] = theme_type_key_var.get()
        theme["checked"] = theme_checked_var.get()
        theme["nickname"] = theme_nickname_entry.get()
        theme["name"] = theme_name_entry.get()
        # 保存拆分字段
        theme["on_value"] = on_value_text.get("1.0", "end-1c").strip()
        # 根据预设决定是否保存 off_value
        off_preset_code = off_preset_key_var_mod.get() or "none"
        if off_preset_code == "custom":
            theme["off_value"] = off_value_text.get("1.0", "end-1c").strip()
        else:
            theme["off_value"] = ""
        theme["off_preset"] = off_preset_code
        if theme["type"] == "服务(需管理员权限)":
            theme["value"] = theme["on_value"]
        if theme["type"] == "命令":
            theme["window"] = "show" if cmd_window_var.get() else "hide"
            lo, hi = _get_cmd_value_range_mod()
            theme["value_min"] = lo
            theme["value_max"] = hi
        else:
            theme.pop("value_min", None)
            theme.pop("value_max", None)
        if theme["type"] == "按键(Hotkey)":
            # 读取临时值以便在保存前校验
            _on_type = hk_on_type_key_var_mod.get() or "keyboard"
            _on_value = hk_on_val_var_mod.get().strip()
            _off_type = hk_off_type_key_var_mod.get() or "none"
            _off_value = hk_off_val_var_mod.get().strip()
            try:
                _char_delay_ms = int(hk_char_delay_var_mod.get() or 0)
                if _char_delay_ms < 0:
                    _char_delay_ms = 0
            except Exception:
                _char_delay_ms = 0

            def _has_non_ascii(s: str) -> bool:
                try:
                    return any(ord(ch) > 127 for ch in s)
                except Exception:
                    return False

            warn_fields = []
            if _on_type == "keyboard" and _on_value and _has_non_ascii(_on_value):
                warn_fields.append("- 打开(on)")
            if _off_type == "keyboard" and _off_value and _has_non_ascii(_off_value):
                warn_fields.append("- 关闭(off)")
            if warn_fields:
                msg = (
                    "检测到以下热键包含中文或全角字符：\n" + "\n".join(warn_fields) +
                    "\n\n这些字符可能无法被正确解析，导致按键不生效或行为异常。\n是否仍然要保存？"
                )
                if not messagebox.askyesno(t("确认包含中文字符"), msg, parent=theme_window):
                    theme_window.lift()
                    return

            theme["on_type"] = _on_type
            theme["on_value"] = _on_value
            theme["off_type"] = _off_type
            theme["off_value"] = _off_value
            theme["char_delay_ms"] = _char_delay_ms
            theme["value"] = ""
        # 重新构建整个树视图以确保索引正确
        rebuild_custom_theme_tree()
        theme_window.destroy()

    def delete_theme():
        if messagebox.askyesno(
            t("确认删除"), t("确定要删除这个自定义主题吗？"), parent=theme_window
        ):
            custom_themes.pop(index)
            # 重新构建整个树视图
            rebuild_custom_theme_tree()
            theme_window.destroy()
        else:
            theme_window.lift()

    ttk.Button(theme_window, text="保存", command=save_theme).grid(
        row=8, column=0, pady=PADY + 6, padx=PADX
    )
    ttk.Button(theme_window, text="删除", command=delete_theme).grid(row=8, column=1, pady=PADY + 6, padx=PADX)
    ttk.Button(theme_window, text="取消", command=lambda:theme_window.destroy()).grid(row=8, column=2, pady=PADY + 6, padx=PADX)

    center_window(theme_window)

    def _apply_lang_to_modify_theme_win() -> None:
        if not theme_window.winfo_exists():
            return
        try:
            theme_window.title(t("修改自定义主题"))
        except Exception:
            pass
        _refresh_type_and_preset_i18n_mod()
        try:
            apply_language_to_widgets(theme_window)
        except Exception:
            pass

    register_lang_observer(_apply_lang_to_modify_theme_win)
    _apply_lang_to_modify_theme_win()


# 添加自定义主题的函数中，也要更新显示
def add_custom_theme(config: Dict[str, Any]) -> None:
    """
    English: Opens a new window to add a new custom theme and updates display
    中文: 打开新窗口添加新的自定义主题，并更新显示
    """
    theme_window = tk.Toplevel(root)
    theme_window.title(t("添加自定义主题"))
    # 增加默认高度
    try:
        w, h = _scaled_size(theme_window, 780, 360)
        theme_window.geometry(f"{w}x{h}")
    except Exception:
        pass
    PADX = 10
    PADY = 6
    # 允许窗口大小调整，并设置网格权重使输入控件随窗口拉伸
    theme_window.resizable(True, True)
    try:
        theme_window.columnconfigure(0, weight=0)
        theme_window.columnconfigure(1, weight=1)
        theme_window.columnconfigure(2, weight=0)
        theme_window.columnconfigure(3, weight=0)
    except Exception:
        pass

    ttk.Label(theme_window, text="类型：").grid(row=0, column=0, sticky="e", padx=PADX, pady=PADY)
    _type_keys_add = ["程序或脚本", "服务(需管理员权限)", "命令", "按键(Hotkey)"]
    theme_type_key_var = tk.StringVar(value="程序或脚本")
    theme_type_var = tk.StringVar(value=t("程序或脚本"))

    def _type_labels_add() -> list[str]:
        return [t(k) for k in _type_keys_add]

    def _type_key_by_label_add(label: str) -> str:
        m = {t(k): k for k in _type_keys_add}
        return m.get(label, "程序或脚本")

    def _type_label_by_key_add(key: str) -> str:
        if key not in _type_keys_add:
            key = "程序或脚本"
            theme_type_key_var.set(key)
        return t(key)

    theme_type_combobox = ttk.Combobox(
        theme_window,
        textvariable=theme_type_var,
        values=_type_labels_add(),
        state="readonly",
    )
    theme_type_combobox.grid(row=0, column=1, sticky="we", padx=(0, PADX), pady=PADY)
    try:
        theme_type_combobox.current(0)
    except Exception:
        pass


    ttk.Label(theme_window, text="服务时主程序").grid(row=0, column=2, sticky="w", padx=PADX, pady=PADY)
    ttk.Label(theme_window, text="需管理员权限").grid(row=1, column=2, sticky="w", padx=PADX, pady=PADY)

    ttk.Label(theme_window, text="状态：").grid(row=1, column=0, sticky="e", padx=PADX, pady=PADY)
    theme_checked_var = tk.IntVar()
    ttk.Checkbutton(theme_window, variable=theme_checked_var).grid(
        row=1, column=1, sticky="w", padx=(0, PADX), pady=PADY
    )

    ttk.Label(theme_window, text="昵称：").grid(row=2, column=0, sticky="e", padx=PADX, pady=PADY)
    theme_nickname_entry = ttk.Entry(theme_window)
    theme_nickname_entry.grid(row=2, column=1, sticky="we", padx=(0, PADX), pady=PADY)

    ttk.Label(theme_window, text="主题：").grid(row=3, column=0, sticky="e", padx=PADX, pady=PADY)
    theme_name_entry = ttk.Entry(theme_window)
    theme_name_entry.grid(row=3, column=1, sticky="we", padx=(0, PADX), pady=PADY)

    # 新：程序/命令类型拆分 ON/OFF 与关闭预设；Hotkey 保持原样
    on_label_add = ttk.Label(theme_window, text="打开(on)：")
    on_label_add.grid(row=4, column=0, sticky="e", padx=PADX, pady=PADY)
    on_frame_add = ttk.Frame(theme_window)
    on_frame_add.grid(row=4, column=1, sticky="nsew", padx=(0, PADX), pady=PADY)
    try:
        theme_window.rowconfigure(4, weight=2)
    except Exception:
        pass
    on_value_text_add = tk.Text(on_frame_add, height=3, wrap="word")
    on_value_text_add.grid(row=0, column=0, sticky="nsew")
    on_scroll_y_add = ttk.Scrollbar(on_frame_add, orient="vertical", command=on_value_text_add.yview)
    on_scroll_y_add.grid(row=0, column=1, sticky="ns")
    on_value_text_add.configure(yscrollcommand=on_scroll_y_add.set)
    try:
        on_frame_add.columnconfigure(0, weight=1)
        on_frame_add.rowconfigure(0, weight=1)
    except Exception:
        pass

    off_label_add = ttk.Label(theme_window, text="关闭(off)：")
    off_label_add.grid(row=5, column=0, sticky="e", padx=PADX, pady=PADY)
    off_frame_add = ttk.Frame(theme_window)
    off_frame_add.grid(row=5, column=1, sticky="nsew", padx=(0, PADX), pady=PADY)
    off_value_text_add = tk.Text(off_frame_add, height=3, wrap="word")
    off_value_text_add.grid(row=0, column=0, sticky="nsew")
    off_scroll_y_add = ttk.Scrollbar(off_frame_add, orient="vertical", command=off_value_text_add.yview)
    off_scroll_y_add.grid(row=0, column=1, sticky="ns")
    off_value_text_add.configure(yscrollcommand=off_scroll_y_add.set)
    try:
        off_frame_add.columnconfigure(0, weight=1)
        off_frame_add.rowconfigure(0, weight=1)
    except Exception:
        pass

    off_preset_label_add = ttk.Label(theme_window, text="关闭预设：")
    off_preset_label_add.grid(row=6, column=0, sticky="e", padx=PADX, pady=PADY)
    _preset_label_zh_by_code_add = {
        "none": "忽略",
        "kill": "强制结束",
        "interrupt": "中断",
        "stop": "停止服务",
        "custom": "自定义",
    }

    def _default_preset_code_for_type_add(t_type: str) -> str:
        if t_type == "命令":
            return "interrupt"
        if t_type == "程序或脚本":
            return "kill"
        if t_type == "服务(需管理员权限)":
            return "stop"
        return "none"

    def _preset_codes_for_type_add(t_type: str) -> tuple[str, ...]:
        if t_type == "命令":
            return ("none", "interrupt", "kill", "custom")
        if t_type == "程序或脚本":
            return ("none", "kill", "custom")
        if t_type == "服务(需管理员权限)":
            return ("none", "stop", "custom")
        return ("none",)

    def _preset_labels_for_type_add(t_type: str) -> list[str]:
        return [t(_preset_label_zh_by_code_add[c]) for c in _preset_codes_for_type_add(t_type)]

    def _preset_code_by_label_add(label: str) -> str:
        m = {t(v): k for k, v in _preset_label_zh_by_code_add.items()}
        return m.get(label, "none")

    def _preset_label_by_code_add(code: str) -> str:
        return t(_preset_label_zh_by_code_add.get(code, "忽略"))

    off_preset_key_var_add = tk.StringVar(value=_default_preset_code_for_type_add("程序或脚本"))
    off_preset_var_add = tk.StringVar(value=_preset_label_by_code_add(off_preset_key_var_add.get()))
    off_preset_combo_add = ttk.Combobox(
        theme_window,
        textvariable=off_preset_var_add,
        state="readonly",
        values=_preset_labels_for_type_add("程序或脚本"),
    )
    off_preset_combo_add.grid(row=6, column=1, sticky="w", padx=(0, PADX), pady=PADY)

    previous_custom_off_value_add = ""
    def _preview_text_for_add(code: str, t_type: str, service_name: str = "") -> str:
        if LANG == "en":
            if t_type == "命令":
                if code == "interrupt":
                    return "Preset: Interrupt — Sends CTRL+BREAK to the last recorded command process and tries to exit gracefully."
                if code == "kill":
                    return "Preset: Force kill — Kills all recorded command processes (kill/taskkill)."
                return "Preset: Ignore — No off action will be performed."
            if t_type == "程序或脚本":
                if code == "kill":
                    return "Preset: Force kill — Tries to terminate the process/script derived from the On target (cmd/bat enhanced, ps1 dedicated, otherwise taskkill /IM)."
                return "Preset: Ignore — No off action will be performed."
            if t_type == "服务(需管理员权限)":
                if code == "stop":
                    svc = service_name or "the specified service"
                    return f"Preset: Stop service — Runs: sc stop {svc}."
                return "Preset: Ignore — No off action will be performed."
            return "Preset: Ignore — No off action will be performed."

        # zh
        if t_type == "命令":
            if code == "interrupt":
                return "预设：中断 — 向最新记录的命令进程发送 CTRL+BREAK，并尝试优雅结束。"
            if code == "kill":
                return "预设：强制结束 — 结束所有记录的命令进程（kill/taskkill）。"
            return "预设：忽略 — 不执行任何关闭动作。"
        if t_type == "程序或脚本":
            if code == "kill":
                return "预设：强制结束 — 将尝试结束由“打开(on)”目标派生的脚本/进程（cmd/bat 优先增强终止，ps1 专用终止，其它 taskkill /IM）。"
            return "预设：忽略 — 不执行任何关闭动作。"
        if t_type == "服务(需管理员权限)":
            if code == "stop":
                svc = service_name or "指定服务"
                return f"预设：停止服务 — 使用 sc stop {svc} 停止服务。"
            return "预设：忽略 — 不执行任何关闭动作。"
        return "预设：忽略 — 不执行任何关闭动作。"

    def _update_off_editability_add(*_):
        nonlocal previous_custom_off_value_add
        code = off_preset_key_var_add.get() or "none"
        t_type = theme_type_key_var.get()
        try:
            if code == "custom":
                off_value_text_add.configure(state=tk.NORMAL)
                try:
                    off_value_text_add.delete("1.0", tk.END)
                    off_value_text_add.insert("1.0", previous_custom_off_value_add)
                except Exception:
                    pass
            else:
                # 保存自定义缓存
                try:
                    if str(off_value_text_add.cget("state")) == str(tk.NORMAL):
                        _cur = off_value_text_add.get("1.0", "end-1c")
                        if _cur.strip():
                            previous_custom_off_value_add = _cur
                except Exception:
                    pass
                # 写入预览并禁用
                try:
                    off_value_text_add.configure(state=tk.NORMAL)
                    off_value_text_add.delete("1.0", tk.END)
                    service_name = on_value_text_add.get("1.0", "end-1c").strip()
                    off_value_text_add.insert("1.0", _preview_text_for_add(code, t_type, service_name))
                except Exception:
                    pass
                off_value_text_add.configure(state=tk.DISABLED)
        except Exception:
            pass
        try:
            if t_type == "程序或脚本" and code == "custom":
                off_action_btn_add.state(["!disabled"])
            elif t_type == "命令" and code == "custom":
                off_action_btn_add.state(["!disabled"])
            else:
                off_action_btn_add.state(["disabled"])
        except Exception:
            pass

    def _on_off_preset_selected_add(_event=None):
        off_preset_key_var_add.set(_preset_code_by_label_add(off_preset_var_add.get()))
        _update_off_editability_add()

    off_preset_combo_add.bind("<<ComboboxSelected>>", _on_off_preset_selected_add)

    def select_file():
        file_path = filedialog.askopenfilename()
        if file_path:
            try:
                on_value_text_add.delete("1.0", tk.END)
                on_value_text_add.insert("1.0", file_path)
            except Exception:
                pass

    def open_services():
        try:
            os.startfile("services.msc")
        except Exception:
            try:
                subprocess.Popen(["services.msc"])  # 备用方式
            except Exception as e:
                messagebox.showerror(t("错误"), t("无法打开服务管理器: {err}").format(err=e))

    # 命令类型：{value} 参数范围（默认 0-100，可配置）
    cmd_value_min_var_add = tk.StringVar(value="0")
    cmd_value_max_var_add = tk.StringVar(value="100")

    def _get_cmd_value_range_add() -> tuple[int, int]:
        try:
            lo = int((cmd_value_min_var_add.get() or "0").strip())
            hi = int((cmd_value_max_var_add.get() or "100").strip())
        except Exception:
            messagebox.showwarning(t("提示"), t("请输入整数"))
            return 0, 100
        if lo > hi:
            lo, hi = hi, lo
        return lo, hi

    def _ask_value_for_placeholder_add(parent_win: tk.Misc) -> str | None:
        lo, hi = _get_cmd_value_range_add()
        ex = 50
        if ex < lo or ex > hi:
            ex = lo
        s = simpledialog.askstring(
            t("输入参数"),
            t("请输入 {value} 的值（范围 {lo}-{hi}），例如 {ex}：").format(value="{value}", lo=lo, hi=hi, ex=ex),
            initialvalue=str(ex),
            parent=parent_win,
        )
        if s is None:
            return None
        s = str(s).strip()
        try:
            v = int(s)
        except Exception:
            messagebox.showwarning(t("提示"), t("请输入整数"))
            return None
        if v < lo or v > hi:
            messagebox.showwarning(t("提示"), t("参数超出范围：{lo}-{hi}").format(lo=lo, hi=hi))
            return None
        return str(v)

    def test_command_in_powershell():
        cmd = on_value_text_add.get("1.0", "end-1c").strip()
        if not cmd:
            messagebox.showwarning(t("提示"), t("请先在“值”中输入要测试的命令"))
            return
        if "{value}" in cmd:
            val = _ask_value_for_placeholder_add(theme_window)
            if val is None:
                return
            cmd = cmd.replace("{value}", val)
        cmd = _normalize_command_for_powershell(cmd)
        if LANG == "en":
            ps_script = (
                "Write-Host 'Ready to test command:' -ForegroundColor Cyan;"
                "\n$cmd = @'\n" + cmd.replace("'@", "'@@") + "\n'@;"
                "\nWrite-Host $cmd -ForegroundColor Yellow;"
                "\nRead-Host 'Press Enter to run';"
                "\nWrite-Host 'Running...' -ForegroundColor Green;"
                "\ntry { iex $cmd } catch { Write-Host ('Error: ' + $_.Exception.Message) -ForegroundColor Red }"
            )
        else:
            ps_script = (
                "Write-Host '已准备好要测试的命令：' -ForegroundColor Cyan;"
                "\n$cmd = @'\n" + cmd.replace("'@", "'@@") + "\n'@;"
                "\nWrite-Host $cmd -ForegroundColor Yellow;"
                "\nRead-Host '按回车后执行';"
                "\nWrite-Host '正在执行...' -ForegroundColor Green;"
                "\ntry { iex $cmd } catch { Write-Host ('发生错误: ' + $_.Exception.Message) -ForegroundColor Red }"
            )
        try:
            subprocess.Popen(
                ["powershell.exe", "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except Exception as e:
            messagebox.showerror(t("错误"), t("无法启动 PowerShell: {err}").format(err=e))

    select_file_btn_add = ttk.Button(theme_window, text="选择文件", command=select_file)
    select_file_btn_add.grid(row=4, column=2, sticky="w", padx=PADX, pady=PADY)
    def select_off_file_add():
        nonlocal previous_custom_off_value_add
        file_path = filedialog.askopenfilename()
        if file_path:
            try:
                if (off_preset_key_var_add.get() or "none") != "custom":
                    off_preset_key_var_add.set("custom")
                    off_preset_var_add.set(_preset_label_by_code_add("custom"))
                previous_custom_off_value_add = file_path
                off_value_text_add.configure(state=tk.NORMAL)
                off_value_text_add.delete("1.0", tk.END)
                off_value_text_add.insert("1.0", file_path)
            except Exception:
                pass
            _update_off_editability_add()

    def test_off_command_in_powershell_add():
        if (off_preset_key_var_add.get() or "none") != "custom":
            messagebox.showwarning(t("提示"), t("请先将关闭预设切换为“自定义”并填写命令"))
            return
        try:
            off_value_text_add.configure(state=tk.NORMAL)
        except Exception:
            pass
        cmd = off_value_text_add.get("1.0", "end-1c").strip()
        if not cmd:
            messagebox.showwarning(t("提示"), t("请先在“关闭(off)”中输入要测试的命令"))
            return
        if "{value}" in cmd:
            val = _ask_value_for_placeholder_add(theme_window)
            if val is None:
                return
            cmd = cmd.replace("{value}", val)
        cmd = _normalize_command_for_powershell(cmd)
        if LANG == "en":
            ps_script = (
                "Write-Host 'Ready to test command:' -ForegroundColor Cyan;"
                "\n$cmd = @'\n" + cmd.replace("'@", "'@@") + "\n'@;"
                "\nWrite-Host $cmd -ForegroundColor Yellow;"
                "\nRead-Host 'Press Enter to run';"
                "\nWrite-Host 'Running...' -ForegroundColor Green;"
                "\ntry { iex $cmd } catch { Write-Host ('Error: ' + $_.Exception.Message) -ForegroundColor Red }"
            )
        else:
            ps_script = (
                "Write-Host '已准备好要测试的命令：' -ForegroundColor Cyan;"
                "\n$cmd = @'\n" + cmd.replace("'@", "'@@") + "\n'@;"
                "\nWrite-Host $cmd -ForegroundColor Yellow;"
                "\nRead-Host '按回车后执行';"
                "\nWrite-Host '正在执行...' -ForegroundColor Green;"
                "\ntry { iex $cmd } catch { Write-Host ('发生错误: ' + $_.Exception.Message) -ForegroundColor Red }"
            )
        try:
            subprocess.Popen(
                ["powershell.exe", "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except Exception as e:
            messagebox.showerror(t("错误"), t("无法启动 PowerShell: {err}").format(err=e))

    off_action_btn_add = ttk.Button(theme_window, text="选择文件", command=select_off_file_add)
    off_action_btn_add.grid(row=5, column=2, sticky="w", padx=PADX, pady=PADY)
    _update_off_editability_add()

    # Hotkey 专用设置区（默认隐藏，选中“按键(Hotkey)”时显示）
    hotkey_frame_add = ttk.Labelframe(theme_window, text="按键(Hotkey) 设置")
    hk_type_items = [
        ("none", "不执行"),
        ("keyboard", "键盘组合"),
    ]

    def _hk_type_labels_add() -> list[str]:
        return [t(zh) for _, zh in hk_type_items]

    def _hk_type_key_by_label_add(label: str) -> str:
        m = {t(zh): k for k, zh in hk_type_items}
        return m.get(label, "none")

    def _hk_type_label_by_key_add(key: str) -> str:
        zh = next((zh for k, zh in hk_type_items if k == key), "不执行")
        return t(zh)

    # 变量
    hk_on_type_key_var_add = tk.StringVar(value="keyboard")
    hk_on_type_var_add = tk.StringVar(value=_hk_type_label_by_key_add("keyboard"))
    hk_on_val_var_add = tk.StringVar(value="")
    hk_off_type_key_var_add = tk.StringVar(value="none")
    hk_off_type_var_add = tk.StringVar(value=_hk_type_label_by_key_add("none"))
    hk_off_val_var_add = tk.StringVar(value="")
    hk_char_delay_var_add = tk.StringVar(value="0")

    ttk.Label(hotkey_frame_add, text="打开(on)：").grid(row=0, column=0, sticky="e", padx=8, pady=4)
    hk_on_type_combo_add = ttk.Combobox(hotkey_frame_add, values=_hk_type_labels_add(), textvariable=hk_on_type_var_add, state="readonly", width=12)
    hk_on_type_combo_add.grid(row=0, column=1, sticky="w")
    hk_on_entry_add = ttk.Entry(hotkey_frame_add, textvariable=hk_on_val_var_add, width=24)
    hk_on_entry_add.grid(row=0, column=2, sticky="w")
    ttk.Button(hotkey_frame_add, text="录制", command=lambda: open_keyboard_recorder(theme_window, hk_on_val_var_add)).grid(row=0, column=3, sticky="w")

    ttk.Label(hotkey_frame_add, text="关闭(off)：").grid(row=1, column=0, sticky="e", padx=8, pady=4)
    hk_off_type_combo_add = ttk.Combobox(hotkey_frame_add, values=_hk_type_labels_add(), textvariable=hk_off_type_var_add, state="readonly", width=12)
    hk_off_type_combo_add.grid(row=1, column=1, sticky="w")
    hk_off_entry_add = ttk.Entry(hotkey_frame_add, textvariable=hk_off_val_var_add, width=24)
    hk_off_entry_add.grid(row=1, column=2, sticky="w")
    ttk.Button(hotkey_frame_add, text="录制", command=lambda: open_keyboard_recorder(theme_window, hk_off_val_var_add)).grid(row=1, column=3, sticky="w")

    ttk.Label(hotkey_frame_add, text="字母段间隔(ms)：").grid(row=2, column=0, sticky="e", padx=8, pady=4)
    hk_char_delay_entry_add = ttk.Entry(hotkey_frame_add, textvariable=hk_char_delay_var_add, width=12)
    hk_char_delay_entry_add.grid(row=2, column=1, sticky="w")

    def _on_hk_on_type_selected_add(_event=None):
        hk_on_type_key_var_add.set(_hk_type_key_by_label_add(hk_on_type_var_add.get()))
        hk_on_type_var_add.set(_hk_type_label_by_key_add(hk_on_type_key_var_add.get()))

    def _on_hk_off_type_selected_add(_event=None):
        hk_off_type_key_var_add.set(_hk_type_key_by_label_add(hk_off_type_var_add.get()))
        hk_off_type_var_add.set(_hk_type_label_by_key_add(hk_off_type_key_var_add.get()))

    hk_on_type_combo_add.bind("<<ComboboxSelected>>", _on_hk_on_type_selected_add)
    hk_off_type_combo_add.bind("<<ComboboxSelected>>", _on_hk_off_type_selected_add)

    # 垂直方向自适应：占位扩展区，推开底部按钮
    try:
        theme_window.rowconfigure(7, weight=1)
        _spacer_add = ttk.Frame(theme_window)
        _spacer_add.grid(row=7, column=0, columnspan=4, sticky="nsew")
    except Exception:
        pass

    # 命令类型：命令窗口显示/隐藏 -> 改为复选框，放在“状态”后面
    cmd_window_var = tk.IntVar(value=1)
    cmd_window_check = ttk.Checkbutton(theme_window, text="显示窗口", variable=cmd_window_var)

    cmd_range_frame_add = ttk.Frame(theme_window)
    ttk.Label(cmd_range_frame_add, text=t("value 参数范围：")).grid(row=0, column=0, sticky="w")
    ttk.Label(cmd_range_frame_add, text=t("最小：")).grid(row=0, column=1, sticky="e", padx=(8, 2))
    cmd_min_entry_add = ttk.Entry(cmd_range_frame_add, textvariable=cmd_value_min_var_add, width=8)
    cmd_min_entry_add.grid(row=0, column=2, sticky="w")
    ttk.Label(cmd_range_frame_add, text=t("最大：")).grid(row=0, column=3, sticky="e", padx=(10, 2))
    cmd_max_entry_add = ttk.Entry(cmd_range_frame_add, textvariable=cmd_value_max_var_add, width=8)
    cmd_max_entry_add.grid(row=0, column=4, sticky="w")

    def _update_type_specific_add(*_):
        type_key = theme_type_key_var.get()
        if type_key == "命令":
            cmd_window_check.grid(row=1, column=1, sticky="n")
            # 放到“关闭预设”同一行右侧
            cmd_range_frame_add.grid(row=6, column=1, columnspan=2, sticky="n", padx=(0, PADX), pady=PADY)
        else:
            cmd_window_check.grid_remove()
            cmd_range_frame_add.grid_remove()
        # Hotkey 面板显示控制；同时隐藏/显示 值 文本和选择按钮
        if type_key == "按键(Hotkey)":
            on_label_add.grid_remove()
            on_frame_add.grid_remove()
            off_label_add.grid_remove()
            off_frame_add.grid_remove()
            off_preset_combo_add.grid_remove()
            off_preset_label_add.grid_remove()
            select_file_btn_add.grid_remove()
            off_action_btn_add.state(["disabled"])
            off_action_btn_add.grid_remove()
            hotkey_frame_add.grid(row=4, column=1, columnspan=2, sticky="we")
        else:
            hotkey_frame_add.grid_remove()
            on_label_add.grid(row=4, column=0, sticky="e")
            on_frame_add.grid(row=4, column=1, sticky="nsew")
            off_label_add.grid(row=5, column=0, sticky="e")
            off_frame_add.grid(row=5, column=1, sticky="nsew")
            off_preset_label_add.grid(row=6, column=0, sticky="e")
            values_now = _preset_labels_for_type_add(type_key)
            off_preset_combo_add.configure(values=values_now)
            allowed_codes = _preset_codes_for_type_add(type_key)
            cur_code = off_preset_key_var_add.get() or "none"
            if cur_code not in allowed_codes:
                cur_code = _default_preset_code_for_type_add(type_key)
                if cur_code not in allowed_codes:
                    cur_code = allowed_codes[0]
                off_preset_key_var_add.set(cur_code)
            off_preset_var_add.set(_preset_label_by_code_add(off_preset_key_var_add.get() or "none"))
            off_preset_combo_add.grid(row=6, column=1, sticky="w")
            if type_key == "程序或脚本":
                select_file_btn_add.configure(text=t("选择文件"), command=select_file)
                select_file_btn_add.grid(row=4, column=2, sticky="w", padx=15)
                off_action_btn_add.configure(text=t("选择文件"), command=select_off_file_add)
                off_action_btn_add.grid(row=5, column=2, sticky="w", padx=15)
            elif type_key == "服务(需管理员权限)":
                select_file_btn_add.grid_remove()
                off_action_btn_add.state(["disabled"])
                off_action_btn_add.grid_remove()
            elif type_key == "命令":
                select_file_btn_add.configure(text=t("PowerShell测试"), command=test_command_in_powershell)
                select_file_btn_add.grid(row=4, column=2, sticky="w", padx=15)
                off_action_btn_add.configure(text=t("PowerShell测试(关闭)"), command=test_off_command_in_powershell_add)
                off_action_btn_add.grid(row=5, column=2, sticky="w", padx=15)
            else:
                select_file_btn_add.grid_remove()
                off_action_btn_add.state(["disabled"])
                off_action_btn_add.grid_remove()
            _update_off_editability_add()

    def _on_theme_type_selected_add(_event=None):
        theme_type_key_var.set(_type_key_by_label_add(theme_type_var.get()))
        theme_type_var.set(_type_label_by_key_add(theme_type_key_var.get()))
        _update_type_specific_add()

    theme_type_combobox.bind("<<ComboboxSelected>>", _on_theme_type_selected_add)
    _update_type_specific_add()

    def _refresh_type_and_preset_i18n_add() -> None:
        try:
            theme_type_combobox.configure(values=_type_labels_add())
            cur_type_key = theme_type_key_var.get() or "程序或脚本"
            theme_type_var.set(_type_label_by_key_add(cur_type_key))
            try:
                theme_type_combobox.current(_type_keys_add.index(cur_type_key))
            except Exception:
                pass
        except Exception:
            pass
        try:
            t_key = theme_type_key_var.get() or "程序或脚本"
            off_preset_combo_add.configure(values=_preset_labels_for_type_add(t_key))
            off_preset_var_add.set(_preset_label_by_code_add(off_preset_key_var_add.get() or "none"))
        except Exception:
            pass

        # Hotkey 下拉选项刷新
        try:
            hk_on_type_combo_add.configure(values=_hk_type_labels_add())
            hk_off_type_combo_add.configure(values=_hk_type_labels_add())
            hk_on_type_var_add.set(_hk_type_label_by_key_add(hk_on_type_key_var_add.get()))
            hk_off_type_var_add.set(_hk_type_label_by_key_add(hk_off_type_key_var_add.get()))
        except Exception:
            pass

        # 如果当前是预设（非 custom），则更新预设说明文本语言
        try:
            t_type = theme_type_key_var.get()
            code = off_preset_key_var_add.get() or "none"
            if code != "custom":
                service_name = on_value_text_add.get("1.0", "end-1c").strip()
                off_value_text_add.configure(state=tk.NORMAL)
                off_value_text_add.delete("1.0", tk.END)
                off_value_text_add.insert("1.0", _preview_text_for_add(code, t_type, service_name))
                off_value_text_add.configure(state=tk.DISABLED)
        except Exception:
            pass

    def save_theme():
        theme = {
            "type": theme_type_key_var.get(),
            "checked": theme_checked_var.get(),
            "nickname": theme_nickname_entry.get(),
            "name": theme_name_entry.get(),
        }
        if theme["type"] in ("程序或脚本", "命令", "服务(需管理员权限)"):
            theme["on_value"] = on_value_text_add.get("1.0","end-1c").strip()
            theme["off_preset"] = off_preset_key_var_add.get() or "none"
            if theme["off_preset"] == "custom":
                theme["off_value"] = off_value_text_add.get("1.0","end-1c").strip()
            else:
                theme["off_value"] = ""
        if theme["type"] == "服务(需管理员权限)":
            theme["value"] = theme["on_value"]
        if theme["type"] == "命令":
            theme["window"] = "show" if cmd_window_var.get() else "hide"
            lo, hi = _get_cmd_value_range_add()
            theme["value_min"] = lo
            theme["value_max"] = hi
        if theme["type"] == "按键(Hotkey)":
            _on_type = hk_on_type_key_var_add.get() or "keyboard"
            _on_value = hk_on_val_var_add.get().strip()
            _off_type = hk_off_type_key_var_add.get() or "none"
            _off_value = hk_off_val_var_add.get().strip()
            try:
                _char_delay_ms = int(hk_char_delay_var_add.get() or 0)
                if _char_delay_ms < 0:
                    _char_delay_ms = 0
            except Exception:
                _char_delay_ms = 0

            def _has_non_ascii(s: str) -> bool:
                try:
                    return any(ord(ch) > 127 for ch in s)
                except Exception:
                    return False

            warn_fields = []
            if _on_type == "keyboard" and _on_value and _has_non_ascii(_on_value):
                warn_fields.append("- 打开(on)")
            if _off_type == "keyboard" and _off_value and _has_non_ascii(_off_value):
                warn_fields.append("- 关闭(off)")
            if warn_fields:
                msg = (
                    "检测到以下热键包含中文或全角字符：\n" + "\n".join(warn_fields) +
                    "\n\n这些字符可能无法被正确解析，导致按键不生效或行为异常。\n是否仍然要保存？"
                )
                if not messagebox.askyesno(t("确认包含中文字符"), msg, parent=theme_window):
                    theme_window.lift()
                    return

            theme["on_type"] = _on_type
            theme["on_value"] = _on_value
            theme["off_type"] = _off_type
            theme["off_value"] = _off_value
            theme["char_delay_ms"] = _char_delay_ms
            theme["value"] = ""  # 兼容旧结构
        custom_themes.append(theme)
        # 重新构建整个树视图以确保索引正确
        rebuild_custom_theme_tree()
        theme_window.destroy()

    ttk.Button(theme_window, text="保存", command=save_theme).grid(
        row=8, column=0, pady=PADY + 6, padx=PADX
    )
    ttk.Button(theme_window, text="取消", command=theme_window.destroy).grid(row=8, column=2, pady=PADY + 6, padx=PADX)

    center_window(theme_window)

    def _apply_lang_to_add_theme_win() -> None:
        if not theme_window.winfo_exists():
            return
        try:
            theme_window.title(t("添加自定义主题"))
        except Exception:
            pass
        _refresh_type_and_preset_i18n_add()
        try:
            apply_language_to_widgets(theme_window)
        except Exception:
            pass

    register_lang_observer(_apply_lang_to_add_theme_win)
    _apply_lang_to_add_theme_win()


def generate_config() -> None:
    """
    English: Generates and saves the config file (JSON) based on the input
    中文: 根据输入生成并保存配置文件(JSON格式)
    """
    global config
    broker = (website_entry.get() or "").strip() or "bemfa.com"

    port_raw = (port_entry.get() or "").strip()
    if not port_raw:
        port = 9501
    else:
        try:
            port = int(port_raw)
        except Exception:
            messagebox.showerror(t("错误"), t("端口必须是数字"))
            return
    if port <= 0 or port > 65535:
        messagebox.showerror(t("错误"), t("端口范围应为 1-65535"))
        return

    # 从现有配置复制，保留扩展键（如 computer_* / sleep_*）
    config = dict(config)
    # 覆盖基础配置项
    config.update({
        "broker": broker,
        "port": port,
        "mqtt_tls": tls_var.get(),
        "mqtt_tls_verify": tls_verify_var.get(),
        "mqtt_tls_ca_file": (tls_ca_entry.get() or "").strip(),
        "test": test_var.get(),
        "notify": notify_var.get(),
        "auth_mode": auth_mode_var.get(),
        "mqtt_username": mqtt_username_entry.get(),
        "mqtt_password": mqtt_password_entry.get(),
        "client_id": client_id_entry.get(),
        "language": LANG,
    })

    # 内置主题配置
    for theme in builtin_themes:
        key = theme["key"]
        value = theme["name_var"].get()
        config[key] = value
        config[f"{key}_checked"] = theme["checked"].get()

    # 在写入自定义主题配置前，先清理旧的自定义主题键，避免重复累计
    # 例如：application1/_name/_checked/_directory1，serveN/commandN/hotkeyN 及其派生键
    # 多次保存时如果不清理旧键，load_custom_themes 会按 while True 读取，导致列表出现重复项
    custom_key_pattern = re.compile(r"^(application\d+|serve\d+|command\d+|hotkey\d+)(?:$|_)")
    for k in [key for key in list(config.keys()) if custom_key_pattern.match(key)]:
        try:
            del config[k]
        except Exception:
            pass

    # 自定义主题配置
    app_index = 1
    serve_index = 1
    command_index = 1
    hotkey_index = 1
    for theme in custom_themes:
        if theme["type"] == "程序或脚本":
            prefix = f"application{app_index}"
            config[prefix] = theme["name"]
            config[f"{prefix}_name"] = theme["nickname"]
            config[f"{prefix}_checked"] = theme["checked"]
            # 兼容旧结构: 仍写入 legacy directory 字段，以便旧版本读取
            legacy_dir = theme.get("on_value", "")
            config[f"{prefix}_directory{app_index}"] = legacy_dir
            # 新结构: on/off 值与关闭预设
            config[f"{prefix}_on_value"] = theme.get("on_value", "")
            config[f"{prefix}_off_value"] = theme.get("off_value", "")
            config[f"{prefix}_off_preset"] = theme.get("off_preset", "kill")
            app_index += 1
        elif theme["type"] == "服务(需管理员权限)":
            prefix = f"serve{serve_index}"
            config[prefix] = theme["name"]
            config[f"{prefix}_name"] = theme["nickname"]
            config[f"{prefix}_checked"] = theme["checked"]
            service_name = theme.get("value", "") or theme.get("on_value", "")
            config[f"{prefix}_value"] = service_name
            config[f"{prefix}_on_value"] = theme.get("on_value", service_name)
            config[f"{prefix}_off_value"] = theme.get("off_value", "")
            config[f"{prefix}_off_preset"] = theme.get("off_preset", "stop")
            serve_index += 1
        elif theme["type"] == "命令":
            prefix = f"command{command_index}"
            config[prefix] = theme["name"]
            config[f"{prefix}_name"] = theme["nickname"]
            config[f"{prefix}_checked"] = theme["checked"]
            # 兼容旧结构: 保留 value 写 on_value
            config[f"{prefix}_value"] = theme.get("on_value", "")
            # 新结构: on/off 值与关闭预设
            config[f"{prefix}_on_value"] = theme.get("on_value", "")
            config[f"{prefix}_off_value"] = theme.get("off_value", "")
            config[f"{prefix}_off_preset"] = theme.get("off_preset", "interrupt")
            # 保存命令窗口显示/隐藏设置，默认显示
            config[f"{prefix}_window"] = theme.get("window", "show")

            # {value} 参数范围（默认 0-100，可自定义）
            try:
                vmin = int(theme.get("value_min", 0) or 0)
            except Exception:
                vmin = 0
            try:
                vmax = int(theme.get("value_max", 100) or 100)
            except Exception:
                vmax = 100
            if vmin > vmax:
                vmin, vmax = vmax, vmin
            config[f"{prefix}_value_min"] = vmin
            config[f"{prefix}_value_max"] = vmax
            command_index += 1
        elif theme["type"] == "按键(Hotkey)":
            prefix = f"hotkey{hotkey_index}"
            config[prefix] = theme["name"]
            config[f"{prefix}_name"] = theme["nickname"]
            config[f"{prefix}_checked"] = theme["checked"]
            config[f"{prefix}_on_type"] = theme.get("on_type", "keyboard")
            config[f"{prefix}_on_value"] = theme.get("on_value", "")
            config[f"{prefix}_off_type"] = theme.get("off_type", "none")
            config[f"{prefix}_off_value"] = theme.get("off_value", "")
            config[f"{prefix}_char_delay_ms"] = int(theme.get("char_delay_ms", 0) or 0)
            hotkey_index += 1

    # 保存为 JSON 文件
    try:
        with open(config_file_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
    except PermissionError as e:
        messagebox.showerror(
            t("错误"),
            t(f"无法写入配置文件（可能没有权限）：\n{config_file_path}\n\n{e}")
        )
        return
    except Exception as e:
        messagebox.showerror(t("错误"), t(f"保存配置文件失败：\n{config_file_path}\n\n{e}"))
        return
    # 保存后刷新界面
    messagebox.showinfo(t("提示"), t("配置文件已保存\n请重新打开主程序以应用更改\n刷新test模式需重启本程序"))
    # 重新读取配置
    try:
        with open(config_file_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        # 不影响保存结果：读取失败则保留内存中的 config
        pass
    # 刷新test模式
    test_var.set(config.get("test", 0))
    # 刷新通知开关
    notify_var.set(config.get("notify", 1))
    # 刷新内置主题
    for idx, theme in enumerate(builtin_themes):
        theme_key = theme["key"]
        theme["name_var"].set(config.get(theme_key, ""))
        theme["checked"].set(config.get(f"{theme_key}_checked", 0))

    # 刷新自定义主题
    custom_themes.clear()
    for item in custom_theme_tree.get_children():
        custom_theme_tree.delete(item)
    load_custom_themes()
    
# 添加一个刷新自定义主题的函数
def refresh_custom_themes() -> None:
    """
    English: Refreshes the custom themes list by clearing and reloading from config
    中文: 通过清空并重新从配置文件加载来刷新自定义主题列表
    """
    global config
    
    # 提示用户未保存的更改将丢失
    if not messagebox.askyesno(t("确认刷新"), t("刷新将加载配置文件中的设置，\n您未保存的更改将会丢失！\n确定要继续吗？")):
        return
    
    # 从配置文件重新读取最新配置
    if os.path.exists(config_file_path):
        try:
            with open(config_file_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            # 刷新test模式
            test_var.set(config.get("test", 0))
            # 刷新通知开关
            try:
                notify_var.set(config.get("notify", 1))
            except Exception:
                pass
            
            # 清空自定义主题列表
            custom_themes.clear()
            
            # 清空树视图中的所有项目
            for item in custom_theme_tree.get_children():
                custom_theme_tree.delete(item)
            
            # 重新加载自定义主题
            load_custom_themes()
            
            messagebox.showinfo(t("提示"), t("已从配置文件刷新自定义主题列表"))
        except Exception as e:
            messagebox.showerror(t("错误"), t("读取配置文件失败: {err}").format(err=e))
    else:
        messagebox.showwarning(t("警告"), t("配置文件不存在，无法刷新"))


def _decode_bytes_best_effort(data: bytes) -> str:
    if not data:
        return ""
    encs: list[str] = []
    try:
        encs.append(locale.getpreferredencoding(False))
    except Exception:
        pass
    encs.extend(["utf-8", "gbk", "mbcs"])
    seen: set[str] = set()
    candidates: list[tuple[int, str]] = []
    for enc in encs:
        if not enc or enc in seen:
            continue
        seen.add(enc)
        try:
            s = data.decode(enc, errors="replace")
        except Exception:
            continue
        candidates.append((s.count("\ufffd"), s))
    if not candidates:
        return data.decode(errors="replace")
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _run_capture_text(args: list[str]) -> tuple[int, str, str]:
    try:
        cp = subprocess.run(args, capture_output=True, text=False, shell=False)
    except FileNotFoundError as e:
        return 1, "", str(e)
    stdout = _decode_bytes_best_effort(cp.stdout or b"")
    stderr = _decode_bytes_best_effort(cp.stderr or b"")
    return int(getattr(cp, "returncode", 1) or 0), stdout, stderr


def _is_hibernate_enabled_from_powercfg_output(output: str) -> bool:
    out = output or ""
    lower = out.lower()
    # 明确的“未启用/不可用”提示（中英文）
    if ("尚未启用休眠" in out) or ("休眠不可用" in out):
        return False
    if ("hibernation has not been enabled" in lower) or ("hibernate has not been enabled" in lower):
        return False

    lines = out.splitlines()
    hibernate_line = next(
        (
            l
            for l in lines
            if (l.strip().startswith("休眠") or l.strip().lower().startswith("hibernate"))
        ),
        None,
    )
    if not hibernate_line:
        # 输出不包含关键行，保守认为不可用
        return False
    hl = hibernate_line.lower()
    if ("不可用" in hibernate_line) or ("not available" in hl) or ("not enabled" in hl):
        return False
    return True

def sleep():
    # 检查系统休眠/睡眠支持（test模式开启时跳过检测）
    global sleep_disabled, sleep_status_message
    if not ("config" in globals() and config.get("test", 0) == 1):
        try:
            rc, out, err = _run_capture_text(["powercfg", "-a"])
            output = (out or "") + (err or "")
            if rc != 0:
                sleep_disabled = True
            else:
                sleep_disabled = not _is_hibernate_enabled_from_powercfg_output(output)
            sleep_status_message = output.strip() or "(no output)"
        except Exception as e:
            sleep_disabled = True
            sleep_status_message = f"检测失败: {e}"
    else:
        sleep_status_message = "test模式已开启，未检测系统休眠/睡眠支持。"

def _resolve_twinkle_tray_path_for_gui() -> str | None:
    candidates: list[str] = []
    try:
        custom = (config.get("twinkle_tray_path", "") or "").strip()
        if custom:
            candidates.append(os.path.expandvars(os.path.expanduser(custom)))
    except Exception:
        pass
    candidates.extend(
        [
            os.path.expandvars(r"%LocalAppData%\Programs\twinkle-tray\Twinkle Tray.exe"),
            os.path.expandvars(r"%LocalAppData%\Microsoft\WindowsApps\Twinkle-Tray.exe"),
        ]
    )
    for alias in ("Twinkle-Tray.exe", "Twinkle Tray.exe", "twinkle-tray.exe"):
        p = shutil.which(alias)
        if p:
            candidates.append(p)
    seen: set[str] = set()
    for p in candidates:
        if not p:
            continue
        norm = os.path.normpath(p)
        if norm in seen:
            continue
        seen.add(norm)
        if os.path.isfile(norm):
            return norm
    return None


def check_brightness_support():
    # 检查系统亮度调节支持（test模式开启时跳过检测）
    global brightness_disabled, brightness_status_message
    brightness_disabled = False
    brightness_status_message = ""

    mode = (config.get("brightness_mode", "wmi") or "wmi").lower()

    if mode == "twinkle_tray":
        path = _resolve_twinkle_tray_path_for_gui()
        if path:
            brightness_status_message = f"使用 Twinkle Tray 控制亮度: {path}"
        else:
            brightness_status_message = "Twinkle Tray 模式：未找到可执行文件，请在“更多”中设置路径或安装应用。"
        return

    if not ("config" in globals() and config.get("test", 0) == 1):
        try:
            import wmi

            brightness_controllers = wmi.WMI(namespace="wmi").WmiMonitorBrightnessMethods()
            if not brightness_controllers:
                brightness_status_message = "系统未暴露 WMI 亮度接口，若需调节请在“更多”中切换到 Twinkle Tray。"
            else:
                brightness_status_message = "系统支持亮度调节(WMI)。"
        except Exception as e:
            brightness_status_message = f"检测亮度控制接口失败: {e}"
    else:
        brightness_status_message = "test模式已开启，未检测系统亮度调节支持。"

def enable_sleep_window() -> None:
    """
    
    中文: 通过命令启用睡眠/休眠功能
    """
    # 二次确认
    if not messagebox.askyesno(
        t("确认启用？"),
        t("将启用系统的休眠/睡眠功能。\n\n此操作会更改系统电源配置，需管理员权限。\n\n是否继续？"),
    ):
        return
    # 检查是否有管理员权限
    if not IS_GUI_ADMIN:
        messagebox.showerror(t("错误"), t("需要管理员权限才能启用休眠/睡眠功能"))
        return
    # 尝试启用休眠/睡眠功能
    try:
        rc, out, err = _run_capture_text(["powercfg", "/hibernate", "on"])
        if rc == 0:
            messagebox.showinfo(t("提示"), t("休眠/睡眠功能已启用"))
        else:
            detail = (err or out).strip()
            messagebox.showerror(t("错误"), t(f"启用失败: \n{detail}"))
    except Exception as e:
        messagebox.showerror(t("错误"), t(f"启用失败: {e}"))

def disable_sleep_window() -> None:
    """
    中文: 通过命令关闭睡眠/休眠功能
    """
    # 二次确认
    if not messagebox.askyesno(
        t("确认关闭"),
        t("将关闭系统的休眠/睡眠功能。\n\n此操作会更改系统电源配置，需管理员权限。\n\n是否继续？"),
    ):
        return
    # 检查是否有管理员权限
    if not IS_GUI_ADMIN:
        messagebox.showerror(t("错误"), t("需要管理员权限才能关闭休眠/睡眠功能"))
        return
    # 尝试关闭休眠/睡眠功能
    try:
        rc, out, err = _run_capture_text(["powercfg", "/hibernate", "off"])
        if rc == 0:
            messagebox.showinfo(t("提示"), t("休眠/睡眠功能已关闭"))
        else:
            detail = (err or out).strip()
            messagebox.showerror(t("错误"), t(f"关闭失败: \n{detail}"))
    except Exception as e:
        messagebox.showerror(t("错误"), t(f"关闭失败: {e}"))

def check_sleep_status_window() -> None:
    """
    中文: 检查系统睡眠/休眠功能是否启用，并弹窗显示详细状态
    """
    try:
        rc, out, err = _run_capture_text(["powercfg", "-a"])
        output = (out or "") + (err or "")
        if rc != 0:
            messagebox.showerror(t("检查失败"), t(f"命令执行失败：\n{output.strip()}"))
            return

        enabled = _is_hibernate_enabled_from_powercfg_output(output)

        status_text = "已启用（可用）" if enabled else "未启用或不可用"
        if LANG == "en":
            status_text = "Enabled" if enabled else "Disabled/Unavailable"
        messagebox.showinfo(t("睡眠功能状态"), t(f"休眠/睡眠状态：{status_text}\n\n详细信息：\n{output.strip()}"))
    except Exception as e:
        messagebox.showerror(t("检查失败"), t(f"检查时出错：{e}"))

# 在程序启动时查询程序的管理员权限状态并保存为全局变量
IS_GUI_ADMIN = False
try:
    IS_GUI_ADMIN = ctypes.windll.shell32.IsUserAnAdmin() != 0
    # logging.info(f"程序管理员权限状态: {'已获得' if IS_TRAY_ADMIN else '未获得'}")
except Exception as e:
    # logging.error(f"检查程序管理员权限时出错: {e}")
    IS_GUI_ADMIN = False

# 配置文件和目录改为当前工作目录
appdata_dir: str = os.path.abspath(os.path.dirname(sys.argv[0]))

# 配置文件路径
config_file_path: str = os.path.join(appdata_dir, "config.json")

# 尝试读取配置文件
config: Dict[str, Any] = {}
if os.path.exists(config_file_path):
    try:
        with open(config_file_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.decoder.JSONDecodeError as e:
        if LANG == "en":
            error_msg = (
                f"Config file is invalid:\n{str(e)}\n\nChoose:\n"
                "• Yes: backup the broken config and continue\n"
                "• No: exit and keep the config"
            )
        else:
            error_msg = f"配置文件格式错误：\n{str(e)}\n\n请选择：\n• 点击\"是\"删除错误的配置文件并继续\n• 点击\"否\"退出程序不删除配置文件"
        if messagebox.askyesno(t("配置文件错误"), error_msg):
            # 用户选择删除配置文件
            try:
                os.rename(config_file_path, f"{config_file_path}.bak")
                messagebox.showinfo(t("备份完成"), t(f"已将错误的配置文件备份为：\n{config_file_path}.bak"))
            except Exception as backup_error:
                messagebox.showwarning(t("备份失败"), t(f"无法备份配置文件：{str(backup_error)}\n将直接删除错误的配置文件。"))           
                try:
                    os.remove(config_file_path)
                except Exception as remove_error:
                    messagebox.showerror(t("错误"), t(f"无法删除配置文件：{str(remove_error)}\n程序将退出。"))
                    sys.exit(1)
            # 继续使用空配置
            config = {}
        else:
            # 用户选择退出程序
            messagebox.showinfo(t("程序退出"), t("您选择了保留配置文件并退出程序。\n请手动修复配置文件后再次运行程序。"))
            sys.exit(0)

# 根据配置文件覆盖语言（如果存在）
try:
    _lang_cfg = _normalize_lang(config.get("language"))
    if _lang_cfg:
        LANG = _lang_cfg
except Exception:
    pass


# 创建主窗口前启用 DPI 感知
_enable_dpi_awareness()

# 启动时检查管理员权限并请求提权（已启用 DPI/字体，避免提示窗模糊）
check_and_request_uac()
# 创建主窗口
root = tk.Tk()
_set_root_title()

# 设置窗口左上角与任务栏图标为 top.ico（优先打包资源，其次侧边 res/）
try:
    icon_candidates = [
        resource_path("res/top.ico"),
        resource_path("top.ico"),
        os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "res", "top.ico"),
    ]
    for _p in icon_candidates:
        if _p and os.path.exists(_p):
            try:
                root.iconbitmap(_p)
                break
            except Exception:
                continue
except Exception:
    pass

# 应用字体与缩放优化
try:
    _apply_font_readability_and_scaling(root)
    _apply_ttk_ui_fonts(root)
except Exception:
    pass

# 设置根窗口的行列权重
root.rowconfigure(0, weight=1)
root.rowconfigure(1, weight=1)
root.rowconfigure(2, weight=0)
root.columnconfigure(0, weight=1)

# 主界面统一内边距
PADX = 10
PADY = 6

# 系统配置部分
system_frame = ttk.LabelFrame(root, text=t("系统配置"))
system_frame.grid(row=0, column=0, padx=PADX, pady=PADY, sticky="nsew")
for i in range(6):
    system_frame.rowconfigure(i, weight=1)
for j in range(3):
    system_frame.columnconfigure(j, weight=1)

ttk.Label(system_frame, text=t("网站：")).grid(row=0, column=0, sticky="e", padx=PADX, pady=PADY)
website_entry = ttk.Entry(system_frame)
website_entry.grid(row=0, column=1, sticky="ew", padx=PADX, pady=PADY)
website_entry.insert(0, config.get("broker", ""))

ttk.Label(system_frame, text=t("端口：")).grid(row=1, column=0, sticky="e", padx=PADX, pady=PADY)
port_entry = ttk.Entry(system_frame)
port_entry.grid(row=1, column=1, sticky="ew", padx=PADX, pady=PADY)
port_entry.insert(0, str(config.get("port", "")))

# MQTT认证模式选择
ttk.Label(system_frame, text=t("认证模式：")).grid(row=2, column=0, sticky="e", padx=PADX, pady=PADY)
auth_mode_var = tk.StringVar(value=config.get("auth_mode", "private_key"))

def _auth_mode_labels() -> list[str]:
    return [t("私钥模式"), t("账密模式")]

auth_mode_combo = ttk.Combobox(system_frame, values=_auth_mode_labels(), state="readonly", width=18)
auth_mode_combo.grid(row=2, column=1, sticky="w", padx=PADX, pady=PADY)

# 设置下拉框显示文本
def update_auth_mode_display():
    current_value = auth_mode_var.get()
    if current_value == "private_key":
        auth_mode_combo.set(t("私钥模式"))
    elif current_value == "username_password":
        auth_mode_combo.set(t("账密模式"))

# 绑定选择事件
def on_auth_mode_change(event):
    selected_text = auth_mode_combo.get()
    if selected_text == t("私钥模式"):
        auth_mode_var.set("private_key")
    elif selected_text == t("账密模式"):
        auth_mode_var.set("username_password")

auth_mode_combo.bind("<<ComboboxSelected>>", on_auth_mode_change)
update_auth_mode_display()

test_var = tk.IntVar(value=config.get("test", 0))
test_check = ttk.Checkbutton(system_frame, text=t("test模式"), variable=test_var)
test_check.grid(row=3, column=0, sticky="n", padx=PADX, pady=PADY)

# 通知开关（控制主程序是否发送 toast 通知），位于 test 模式开关右侧
notify_var = tk.IntVar(value=config.get("notify", 1))
notify_check = ttk.Checkbutton(system_frame, text=t("通知提示"), variable=notify_var)
notify_check.grid(row=3, column=1, sticky="n", padx=PADX, pady=PADY)

#添加打开任务计划按钮
task_button = ttk.Button(system_frame, text=t("点击打开任务计划"), command=lambda:os.startfile("taskschd.msc"))
task_button.grid(row=3, column=2, sticky="n", padx=PADX, pady=PADY)

# 添加设置开机自启动按钮上面的提示
auto_start_label = ttk.Label(
    system_frame,
    text=t("需要管理员权限才能设置"),
)
auto_start_label.grid(row=0, column=2, sticky="n", padx=PADX, pady=PADY)
auto_start_label1 = ttk.Label(
    system_frame,
    text=t("开机自启/启用睡眠(休眠)功能"),
)
auto_start_label1.grid(row=1, column=2, sticky="n", padx=PADX, pady=PADY)

# 添加设置开机自启动按钮
auto_start_button = ttk.Button(system_frame, text="", command=set_auto_start)
auto_start_button.grid(row=2, column=2,  sticky="n", padx=PADX, pady=PADY)

# 语言选择
language_var = tk.StringVar(value=LANG)
ttk.Label(system_frame, text=t("语言：")).grid(row=4, column=0, sticky="e", padx=PADX, pady=PADY)
language_combo = ttk.Combobox(system_frame, state="readonly", width=18)
language_combo["values"] = ["中文", "English"]
language_combo.grid(row=4, column=1, sticky="w", padx=PADX, pady=PADY)

def _sync_language_combo() -> None:
    try:
        language_combo.set("English" if LANG == "en" else "中文")
    except Exception:
        pass

def _on_language_change(_event=None) -> None:
    global LANG
    sel = (language_combo.get() or "").strip()
    LANG = "en" if sel.lower().startswith("english") else "zh"
    language_var.set(LANG)
    # 更新组合框显示、认证模式文案、窗口文案
    try:
        auth_mode_combo.configure(values=_auth_mode_labels())
        update_auth_mode_display()
    except Exception:
        pass
    _apply_language_everywhere()

language_combo.bind("<<ComboboxSelected>>", _on_language_change)
_sync_language_combo()

# MQTT认证配置部分
auth_frame = ttk.LabelFrame(root, text=t("MQTT认证配置"))
auth_frame.grid(row=1, column=0, padx=PADX, pady=PADY, sticky="nsew")
for i in range(6):
    auth_frame.rowconfigure(i, weight=1)
for j in range(3):
    auth_frame.columnconfigure(j, weight=1)

# 用户名配置
ttk.Label(auth_frame, text=t("用户名：")).grid(row=0, column=0, sticky="e", padx=PADX, pady=PADY)
mqtt_username_entry = ttk.Entry(auth_frame)
mqtt_username_entry.grid(row=0, column=1, sticky="ew", padx=PADX, pady=PADY)
mqtt_username_entry.insert(0, config.get("mqtt_username", ""))

# 密码配置
ttk.Label(auth_frame, text=t("密码：")).grid(row=1, column=0, sticky="e", padx=PADX, pady=PADY)
mqtt_password_entry = ttk.Entry(auth_frame, show="*")
mqtt_password_entry.grid(row=1, column=1, sticky="ew", padx=PADX, pady=PADY)
mqtt_password_entry.insert(0, config.get("mqtt_password", ""))

# 客户端ID配置
ttk.Label(auth_frame, text=t("客户端ID：")).grid(row=2, column=0, sticky="e", padx=PADX, pady=PADY)
client_id_entry = ttk.Entry(auth_frame)
client_id_entry.grid(row=2, column=1, sticky="ew", padx=PADX, pady=PADY)
# 读取client_id配置
client_id_value = config.get("client_id", "")
client_id_entry.insert(0, client_id_value)

# TLS/SSL 开关（主程序使用 ssl:// 连接）
tls_var = tk.IntVar(value=int(config.get("mqtt_tls", 0) or 0))
tls_check = ttk.Checkbutton(auth_frame, text=t("启用TLS/SSL"), variable=tls_var)
tls_check.grid(row=3, column=0, columnspan=2, sticky="w", padx=PADX, pady=PADY)

# TLS 证书校验与 CA 文件（可选）
tls_verify_var = tk.IntVar(value=int(config.get("mqtt_tls_verify", 0) or 0))
tls_verify_check = ttk.Checkbutton(auth_frame, text=t("校验证书"), variable=tls_verify_var)
tls_verify_check.grid(row=3, column=1, columnspan=2, sticky="n", padx=PADX, pady=PADY)

tls_ca_label = ttk.Label(auth_frame, text=t("CA证书："))
tls_ca_label.grid(row=5, column=0, sticky="e", padx=PADX, pady=PADY)
tls_ca_entry = ttk.Entry(auth_frame)
tls_ca_entry.grid(row=5, column=1, sticky="ew", padx=PADX, pady=PADY)
tls_ca_entry.insert(0, config.get("mqtt_tls_ca_file", "") or "")

def choose_tls_ca_file() -> None:
    path = filedialog.askopenfilename(
        title=t("选择CA证书文件"),
        filetypes=[
            (t("证书文件"), "*.pem *.crt *.cer"),
            (t("所有文件"), "*.*"),
        ],
    )
    if path:
        try:
            tls_ca_entry.delete(0, tk.END)
            tls_ca_entry.insert(0, path)
        except Exception:
            pass

tls_ca_button = ttk.Button(auth_frame, text=t("选择文件"), command=choose_tls_ca_file)
tls_ca_button.grid(row=5, column=2, sticky="w", padx=PADX, pady=PADY)

def _set_widget_enabled(w, enabled: bool) -> None:
    try:
        w.configure(state=("normal" if enabled else "disabled"))
        return
    except Exception:
        pass
    try:
        if enabled:
            w.state(["!disabled"])
        else:
            w.state(["disabled"])
    except Exception:
        pass

def _sync_tls_ca_controls() -> None:
    tls_enabled = bool(tls_var.get())
    verify_enabled = bool(tls_verify_var.get())
    ca_enabled = tls_enabled and verify_enabled
    _set_widget_enabled(tls_ca_label, ca_enabled)
    _set_widget_enabled(tls_ca_entry, ca_enabled)
    _set_widget_enabled(tls_ca_button, ca_enabled)

def _sync_tls_controls() -> None:
    tls_enabled = bool(tls_var.get())
    _set_widget_enabled(tls_verify_check, tls_enabled)
    if not tls_enabled:
        try:
            tls_verify_var.set(0)
        except Exception:
            pass
    _sync_tls_ca_controls()

def _on_tls_or_verify_change(*_args) -> None:
    _sync_tls_controls()

tls_var.trace_add("write", _on_tls_or_verify_change)
tls_verify_var.trace_add("write", _on_tls_or_verify_change)
_sync_tls_controls()

# 认证模式说明
auth_info_label = ttk.Label(
    auth_frame,
    text=t("私钥模式：\n        使用客户端ID作为私钥\n账密模式：\n        兼容大多数IoT平台"),
    justify="left"
)
auth_info_label.grid(row=0, column=2, rowspan=6, sticky="n", padx=PADX, pady=PADY)

def toggle_auth_mode(*args):
    """根据MQTT认证模式切换界面显示"""
    mode = auth_mode_var.get()
    if mode == "username_password":
        # 账密模式：适用于大多数IoT平台
        mqtt_username_entry.config(state="normal")
        mqtt_password_entry.config(state="normal")
        client_id_entry.config(state="normal", show="")
    else:
        # 私钥模式：兼容巴法云等特殊平台，客户端ID作为私钥需要保密
        mqtt_username_entry.config(state="disabled")
        mqtt_password_entry.config(state="disabled")
        client_id_entry.config(state="normal", show="*")

# 绑定认证模式变化事件（Tcl 9 下 trace() 已弃用，改用 trace_add）
auth_mode_var.trace_add("write", toggle_auth_mode)
# 初始化界面状态
toggle_auth_mode()

# 程序标题栏
if IS_GUI_ADMIN:
    check_task()
    _set_root_title()
else:
    auto_start_button.config(text=t("获取权限"), command=get_administrator_privileges)

# 主题配置部分
theme_frame = ttk.LabelFrame(root, text=t("主题配置"))
theme_frame.grid(row=2, column=0, padx=PADX, pady=PADY, sticky="nsew")
for i in range(6):
    theme_frame.rowconfigure(i, weight=1)
for j in range(4):
    theme_frame.columnconfigure(j, weight=1)

# 内置主题
builtin_themes: List[Dict[str, Any]] = [
    {
        "nickname": "计算机",
        "key": "Computer",
        "name_var": tk.StringVar(),
        "checked": tk.IntVar(),
    },
    {
        "nickname": "屏幕",
        "key": "screen",
        "name_var": tk.StringVar(),
        "checked": tk.IntVar(),
    },
    {
        "nickname": "音量",
        "key": "volume",
        "name_var": tk.StringVar(),
        "checked": tk.IntVar(),
    },
    {
        "nickname": "睡眠",
        "key": "sleep",
        "name_var": tk.StringVar(),
        "checked": tk.IntVar(),
    },
    {
        "nickname": "媒体控制",
        "key": "media",
        "name_var": tk.StringVar(),
        "checked": tk.IntVar(),
    },
]

ttk.Label(theme_frame, text=t("内置")).grid(row=0, column=0, sticky="w", padx=PADX, pady=PADY)

# 更多：打开内置主题设置
def open_builtin_settings():
    win = tk.Toplevel(root)
    win.title(t("内置主题设置"))
    # win.resizable(False, False)

    # 计算机主题动作（去除与睡眠主题重复的“睡眠/休眠”）
    actions = [
        ("none", "不执行"),
        ("lock", "锁屏"),
        ("shutdown", "关机"),
        ("restart", "重启"),
        ("logoff", "注销"),
    ]
    key_to_label_zh = {k: v for k, v in actions}

    def _action_labels() -> list[str]:
        return [t(label) for _, label in actions]

    def _action_key_by_label(label: str) -> str:
        m = {t(v): k for k, v in actions}
        return m.get(label, "none")

    def _action_label_by_key(key: str, default_key: str = "none") -> str:
        zh = key_to_label_zh.get(key, key_to_label_zh.get(default_key, ""))
        return t(zh)

    # 读取计算机主题配置（带默认值）
    cur_on = config.get("computer_on_action", "lock")
    cur_off = config.get("computer_off_action", "restart")
    cur_on_delay = int(config.get("computer_on_delay", 0) or 0)
    cur_off_delay = int(config.get("computer_off_delay", 0) or 0)

    row_i = 0
    ttk.Label(win, text="计算机(Computer) 主题动作").grid(row=row_i, column=0, columnspan=3, padx=10, pady=(10, 6), sticky="w")
    row_i += 1

    ttk.Label(win, text="打开(on)：").grid(row=row_i, column=0, sticky="e", padx=8, pady=4)
    on_key_var = tk.StringVar(value=cur_on)
    on_var = tk.StringVar(value=_action_label_by_key(cur_on, "lock"))
    on_combo = ttk.Combobox(win, values=_action_labels(), textvariable=on_var, state="readonly", width=18)
    on_combo.bind("<<ComboboxSelected>>", lambda e: on_key_var.set(_action_key_by_label(on_var.get())))
    on_combo.grid(row=row_i, column=1, sticky="w")
    ttk.Label(win, text="延时(秒)：").grid(row=row_i, column=2, sticky="e", padx=8)
    on_delay_var = tk.StringVar(value=str(cur_on_delay))
    on_delay_entry = ttk.Entry(win, textvariable=on_delay_var, width=8)
    on_delay_entry.grid(row=row_i, column=3, sticky="w")
    row_i += 1

    ttk.Label(win, text="关闭(off)：").grid(row=row_i, column=0, sticky="e", padx=8, pady=4)
    off_key_var = tk.StringVar(value=cur_off)
    off_var = tk.StringVar(value=_action_label_by_key(cur_off, "restart"))
    off_combo = ttk.Combobox(win, values=_action_labels(), textvariable=off_var, state="readonly", width=18)
    off_combo.bind("<<ComboboxSelected>>", lambda e: off_key_var.set(_action_key_by_label(off_var.get())))
    off_combo.grid(row=row_i, column=1, sticky="w")
    ttk.Label(win, text="延时(秒)：").grid(row=row_i, column=2, sticky="e", padx=8)
    off_delay_var = tk.StringVar(value=str(cur_off_delay))
    off_delay_entry = ttk.Entry(win, textvariable=off_delay_var, width=8)
    off_delay_entry.grid(row=row_i, column=3, sticky="w")
    row_i += 1

    tip = ttk.Label(win, text="提示：计算机主题延时仅对关机/重启有效，其它动作忽略延时。")
    tip.grid(row=row_i, column=0, columnspan=4, padx=10, pady=(6, 10), sticky="w")
    row_i += 1

    # 亮度控制方案
    ttk.Label(win, text="屏幕亮度控制方案").grid(row=row_i, column=0, columnspan=4, padx=10, pady=(0, 6), sticky="w")
    row_i += 1

    brightness_modes = [
        ("wmi", "系统接口(WMI)"),
        ("twinkle_tray", "Twinkle Tray (命令行)")
    ]
    bm_key_to_label_zh = {k: v for k, v in brightness_modes}
    cur_bm_key = config.get("brightness_mode", "wmi")
    bm_key_var = tk.StringVar(value=cur_bm_key)
    brightness_mode_var = tk.StringVar(value=t(bm_key_to_label_zh.get(cur_bm_key, "系统接口(WMI)")))

    def _bm_labels() -> list[str]:
        return [t(label) for _, label in brightness_modes]

    def _bm_key_by_label(label: str) -> str:
        m = {t(v): k for k, v in brightness_modes}
        return m.get(label, "wmi")

    def _bm_label_by_key(key: str) -> str:
        return t(bm_key_to_label_zh.get(key, "系统接口(WMI)"))

    ttk.Label(win, text="控制方式：").grid(row=row_i, column=0, sticky="e", padx=8, pady=4)
    brightness_mode_combo = ttk.Combobox(win, values=_bm_labels(), textvariable=brightness_mode_var, state="readonly", width=22)
    brightness_mode_combo.bind(
        "<<ComboboxSelected>>",
        lambda e: bm_key_var.set(_bm_key_by_label(brightness_mode_var.get())),
    )
    brightness_mode_combo.grid(row=row_i, column=1, sticky="w")

    twinkle_overlay_var = tk.IntVar(value=int(config.get("twinkle_tray_overlay", 1) or 0))
    overlay_cb = ttk.Checkbutton(win, text="显示叠加层(Overlay)", variable=twinkle_overlay_var)
    overlay_cb.grid(row=row_i, column=2, columnspan=2, sticky="w")
    row_i += 1

    ttk.Label(win, text="Twinkle Tray 路径：").grid(row=row_i, column=0, sticky="e", padx=8, pady=4)
    twinkle_path_var = tk.StringVar(value=(config.get("twinkle_tray_path", "") or "Twinkle Tray"))
    twinkle_path_entry = ttk.Entry(win, textvariable=twinkle_path_var, width=24)
    twinkle_path_entry.grid(row=row_i, column=1, columnspan=1, sticky="w")

    def browse_twinkle_path():
        try:
            path = filedialog.askopenfilename(
                title=t("选择 Twinkle Tray 可执行文件"),
                filetypes=[(t("可执行文件"), "*.exe"), (t("所有文件"), "*.*")],
            )
            if path:
                twinkle_path_var.set(path)
        except Exception as e:
            messagebox.showerror(t("错误"), t(f"选择文件失败: {e}"))
    btns_frame = ttk.Frame(win)
    btns_frame.grid(row=row_i, column=2, columnspan=2, sticky="w", padx=6)
    browse_btn = ttk.Button(btns_frame, text="浏览", command=browse_twinkle_path)
    browse_btn.grid(row=0, column=0, sticky="w")
    def open_twinkle_store():
        try:
            import webbrowser
            webbrowser.open("https://apps.microsoft.com/detail/9pljwwsv01lk?hl=zh-cn&gl=CN")
        except Exception as e:
            messagebox.showerror(t("错误"), t(f"打开微软应用商店失败: {e}"))
    download_btn = ttk.Button(btns_frame, text="下载", command=open_twinkle_store)
    download_btn.grid(row=0, column=1, sticky="w", padx=(6, 0))
    row_i += 1

    ttk.Label(win, text="目标显示器：").grid(row=row_i, column=0, sticky="e", padx=8, pady=4)
    target_modes = [
        ("monitor_num", "按编号(MonitorNum)"),
        ("monitor_id", "按ID(MonitorID)"),
        ("all", "全部显示器(All)")
    ]
    tm_key_to_label_zh = {k: v for k, v in target_modes}
    tm_key_var = tk.StringVar(value=str(config.get("twinkle_tray_target_mode", "monitor_num") or "monitor_num"))
    twinkle_target_mode_var = tk.StringVar(value=t(tm_key_to_label_zh.get(tm_key_var.get(), "按编号(MonitorNum)")))
    twinkle_target_value_var = tk.StringVar(value=str(config.get("twinkle_tray_target_value", "1") or ""))

    def _tm_labels() -> list[str]:
        return [t(label) for _, label in target_modes]

    def _tm_key_by_label(label: str) -> str:
        m = {t(v): k for k, v in target_modes}
        return m.get(label, "monitor_num")

    def _tm_label_by_key(key: str) -> str:
        return t(tm_key_to_label_zh.get(key, "按编号(MonitorNum)"))

    twinkle_target_mode_combo = ttk.Combobox(win, values=_tm_labels(), textvariable=twinkle_target_mode_var, state="readonly", width=22)
    twinkle_target_mode_combo.bind(
        "<<ComboboxSelected>>",
        lambda e: tm_key_var.set(_tm_key_by_label(twinkle_target_mode_var.get())),
    )
    twinkle_target_mode_combo.grid(row=row_i, column=1, sticky="w")

    twinkle_target_entry = ttk.Entry(win, textvariable=twinkle_target_value_var, width=18)
    twinkle_target_entry.grid(row=row_i, column=2, sticky="w")
    row_i += 1

    def _toggle_twinkle_fields(*_args):
        mode_key = _bm_key_by_label(brightness_mode_var.get()) or "wmi"
        use_twinkle = mode_key == "twinkle_tray"
        state = "normal" if use_twinkle else "disabled"
        for w in (twinkle_path_entry, twinkle_target_mode_combo, twinkle_target_entry, overlay_cb, browse_btn, download_btn):
            try:
                w.state(["!disabled"] if use_twinkle else ["disabled"])
            except Exception:
                try:
                    w.config(state=state)
                except Exception:
                    pass

        target_mode_key = tm_key_var.get() or "monitor_num"
        if use_twinkle and target_mode_key == "all":
            twinkle_target_entry.state(["disabled"])
        elif use_twinkle:
            twinkle_target_entry.state(["!disabled"])

    brightness_mode_var.trace_add("write", _toggle_twinkle_fields)
    twinkle_target_mode_var.trace_add("write", _toggle_twinkle_fields)
    _toggle_twinkle_fields()

    # 分隔线
    ttk.Separator(win, orient="horizontal").grid(row=row_i, column=0, columnspan=4, sticky="ew", padx=10, pady=(0, 10))
    row_i += 1

    # 睡眠主题设置
    sleep_actions_on = [
        ("sleep", "睡眠"),
        ("hibernate", "休眠"),
        ("display_off", "关闭显示器"),
        ("none", "不执行"),
    ]
    sleep_actions_off = [
        ("none", "不执行"),
        ("display_on", "打开显示器"),
        ("lock", "锁屏"),
    ]
    s_key_to_label_on_zh = {k: v for k, v in sleep_actions_on}
    s_key_to_label_off_zh = {k: v for k, v in sleep_actions_off}

    def _s_on_labels() -> list[str]:
        return [t(v) for _, v in sleep_actions_on]

    def _s_off_labels() -> list[str]:
        return [t(v) for _, v in sleep_actions_off]

    def _s_on_key_by_label(label: str) -> str:
        m = {t(v): k for k, v in sleep_actions_on}
        return m.get(label, "sleep")

    def _s_off_key_by_label(label: str) -> str:
        m = {t(v): k for k, v in sleep_actions_off}
        return m.get(label, "none")

    def _s_on_label_by_key(key: str) -> str:
        return t(s_key_to_label_on_zh.get(key, "睡眠"))

    def _s_off_label_by_key(key: str) -> str:
        return t(s_key_to_label_off_zh.get(key, "不执行"))

    s_cur_on = config.get("sleep_on_action", "sleep")
    s_cur_off = config.get("sleep_off_action", "none")
    s_cur_on_delay = int(config.get("sleep_on_delay", 0) or 0)
    s_cur_off_delay = int(config.get("sleep_off_delay", 0) or 0)

    ttk.Label(win, text="睡眠(sleep) 主题动作").grid(row=row_i, column=0, columnspan=4, padx=10, pady=(0, 6), sticky="w")
    row_i += 1

    ttk.Label(win, text="打开(on)：").grid(row=row_i, column=0, sticky="e", padx=8, pady=4)
    s_on_key_var = tk.StringVar(value=s_cur_on)
    s_on_var = tk.StringVar(value=_s_on_label_by_key(s_cur_on))
    s_on_combo = ttk.Combobox(win, values=_s_on_labels(), textvariable=s_on_var, state="readonly", width=18)
    s_on_combo.grid(row=row_i, column=1, sticky="w")
    s_on_combo.bind("<<ComboboxSelected>>", lambda e: s_on_key_var.set(_s_on_key_by_label(s_on_var.get())))
    ttk.Label(win, text="延时(秒)：").grid(row=row_i, column=2, sticky="e", padx=8)
    s_on_delay_var = tk.StringVar(value=str(s_cur_on_delay))
    ttk.Entry(win, textvariable=s_on_delay_var, width=8).grid(row=row_i, column=3, sticky="w")
    row_i += 1

    ttk.Label(win, text="关闭(off)：").grid(row=row_i, column=0, sticky="e", padx=8, pady=4)
    s_off_key_var = tk.StringVar(value=s_cur_off)
    s_off_var = tk.StringVar(value=_s_off_label_by_key(s_cur_off))
    s_off_combo = ttk.Combobox(win, values=_s_off_labels(), textvariable=s_off_var, state="readonly", width=18)
    s_off_combo.grid(row=row_i, column=1, sticky="w")
    s_off_combo.bind("<<ComboboxSelected>>", lambda e: s_off_key_var.set(_s_off_key_by_label(s_off_var.get())))
    ttk.Label(win, text="延时(秒)：").grid(row=row_i, column=2, sticky="e", padx=8)
    s_off_delay_var = tk.StringVar(value=str(s_cur_off_delay))
    ttk.Entry(win, textvariable=s_off_delay_var, width=8).grid(row=row_i, column=3, sticky="w")
    row_i += 1

    ttk.Label(win, text="提示：睡眠主题延时将在执行动作前等待指定秒数。").grid(row=row_i, column=0, columnspan=4, padx=10, pady=(6, 10), sticky="w")
    row_i += 1

    # 分隔线（睡眠动作 与 睡眠功能开关）
    ttk.Separator(win, orient="horizontal").grid(row=row_i, column=0, columnspan=4, sticky="ew", padx=10, pady=(0, 10))
    row_i += 1

    # 睡眠支持操作：将启用/关闭睡眠功能搬到“更多”中
    op_frame = ttk.Frame(win)
    op_frame.grid(row=row_i, column=0, columnspan=4, padx=10, pady=(0, 10), sticky="w")
    ttk.Label(op_frame, text="系统睡眠功能开关：").grid(row=0, column=0, sticky="w")
    ttk.Label(op_frame, text="注：需要管理员权限").grid(row=0, column=1, sticky="n")
    ttk.Button(op_frame, text=" 启用 睡眠(休眠)功能", command=enable_sleep_window).grid(row=1, column=0, padx=(0, 8))
    ttk.Button(op_frame, text=" 关闭 睡眠(休眠)功能", command=disable_sleep_window).grid(row=1, column=1, padx=(0, 8))
    ttk.Button(op_frame, text="检查睡眠功能状态", command=check_sleep_status_window).grid(row=1, column=2, padx=(0, 8))
    row_i += 1

    # 分隔线
    ttk.Separator(win, orient="horizontal").grid(row=row_i, column=0, columnspan=4, sticky="ew", padx=10, pady=(0, 10))
    row_i += 1

    # 移除：按键(Hotkey) 主题设置（改由自定义主题管理）

    def save_builtin_settings():
        try:
            # 更新内存配置
            config["computer_on_action"] = on_key_var.get() or "lock"
            config["computer_off_action"] = off_key_var.get() or "restart"
            try:
                config["computer_on_delay"] = max(0, int(on_delay_var.get()))
            except Exception:
                config["computer_on_delay"] = 0
            try:
                config["computer_off_delay"] = max(0, int(off_delay_var.get()))
            except Exception:
                config["computer_off_delay"] = 60

            # 读取睡眠动作选择
            _sleep_on_sel = s_on_key_var.get() or "sleep"
            _sleep_off_sel = s_off_key_var.get() or "none"

            # 保存前，给出风险提示（不阻断保存）
            if (_sleep_on_sel in ("display_off", "display_on")) or (_sleep_off_sel in ("display_off", "display_on")):
                messagebox.showwarning(
                    t("警告"),
                    t("依赖于 Windows 的系统 API 来控制显示器电源状态\n未经过测试\n可能造成不可逆后果\n谨慎使用‘开/关显示器功能’")
                )

            # 打开动作为“睡眠/休眠”时提示：设备将离线
            if _sleep_on_sel in ("sleep", "hibernate"):
                messagebox.showwarning(t("提示"), t("当打开动作设置为“睡眠/休眠”时：\n设备将进入低功耗或断电状态，主程序会离线，\n期间无法接收远程命令，需要人工或计划唤醒。"))

            config["sleep_on_action"] = _sleep_on_sel
            config["sleep_off_action"] = _sleep_off_sel
            try:
                config["sleep_on_delay"] = max(0, int(s_on_delay_var.get()))
            except Exception:
                config["sleep_on_delay"] = 0
            try:
                config["sleep_off_delay"] = max(0, int(s_off_delay_var.get()))
            except Exception:
                config["sleep_off_delay"] = 0

            config["brightness_mode"] = bm_key_var.get() or "wmi"
            config["twinkle_tray_path"] = twinkle_path_var.get().strip()
            config["twinkle_tray_target_mode"] = tm_key_var.get() or "monitor_num"
            config["twinkle_tray_target_value"] = twinkle_target_value_var.get().strip()
            config["twinkle_tray_overlay"] = 1 if twinkle_overlay_var.get() else 0

            # Hotkey 不在内置设置中保存

            # 统一通过 generate_config 保存并刷新
            generate_config()
            win.destroy()
        except Exception as e:
            messagebox.showerror(t("错误"), t(f"保存失败: {e}"))

    btn_frame = ttk.Frame(win)
    btn_frame.grid(row=row_i, column=0, columnspan=4, pady=(0, 10))
    ttk.Button(btn_frame, text="保存", command=save_builtin_settings).grid(row=0, column=0, padx=6)
    ttk.Button(btn_frame, text="取消", command=win.destroy).grid(row=0, column=1, padx=6)

    def _apply_lang_to_builtin_win() -> None:
        if not win.winfo_exists():
            return
        try:
            win.title(t("内置主题设置"))
        except Exception:
            pass
        try:
            on_combo.configure(values=_action_labels())
            off_combo.configure(values=_action_labels())
            on_var.set(_action_label_by_key(on_key_var.get() or "lock", "lock"))
            off_var.set(_action_label_by_key(off_key_var.get() or "restart", "restart"))
        except Exception:
            pass
        try:
            brightness_mode_combo.configure(values=_bm_labels())
            brightness_mode_var.set(_bm_label_by_key(bm_key_var.get() or "wmi"))
        except Exception:
            pass
        try:
            twinkle_target_mode_combo.configure(values=_tm_labels())
            twinkle_target_mode_var.set(_tm_label_by_key(tm_key_var.get() or "monitor_num"))
        except Exception:
            pass
        try:
            s_on_combo.configure(values=_s_on_labels())
            s_off_combo.configure(values=_s_off_labels())
            s_on_var.set(_s_on_label_by_key(s_on_key_var.get() or "sleep"))
            s_off_var.set(_s_off_label_by_key(s_off_key_var.get() or "none"))
        except Exception:
            pass

    register_lang_observer(lambda: (_apply_lang_to_builtin_win(), apply_language_to_widgets(win)))
    _apply_lang_to_builtin_win()
    apply_language_to_widgets(win)

    # 窗口居中
    try:
        center_window(win)
    except Exception:
        pass


ttk.Button(theme_frame, text=t("详情"), command=show_detail_window).grid(row=0, column=2, sticky="e", columnspan=2, padx=PADX, pady=PADY)
ttk.Label(theme_frame, text=t("主题：")).grid(row=0, column=2, sticky="w", padx=PADX, pady=PADY)
ttk.Label(theme_frame, text=t("自定义：")).grid(
    row=0, column=3, sticky="w", padx=PADX, pady=PADY
)

sleep_disabled = False
sleep_status_message = ""
brightness_disabled = False
brightness_status_message = ""
sleep()
check_brightness_support()

for idx, theme in enumerate(builtin_themes):
    theme_key = theme["key"]
    theme["name_var"].set(config.get(theme_key, ""))
    theme["checked"].set(config.get(f"{theme_key}_checked", 0))
    if theme_key == "sleep" and sleep_disabled:
        theme["checked"].set(0)
        theme["name_var"].set("")
        cb = ttk.Checkbutton(theme_frame, text=theme["nickname"], variable=theme["checked"])
        cb.state(["disabled"])
        cb.grid(row=idx + 1, column=0, sticky="w", columnspan=2, padx=PADX, pady=PADY)
        entry = ttk.Entry(theme_frame, textvariable=theme["name_var"])
        entry.config(state="disabled")
        entry.grid(row=idx + 1, column=2, sticky="ew", padx=PADX, pady=PADY)
        # 改为不可点击提示
        sleep_tip = ttk.Label(theme_frame, text="休眠/睡眠不可用\n系统未启用休眠功能")
        sleep_tip.grid(row=idx + 1, column=2, sticky="w", padx=PADX, pady=PADY)
    elif theme_key == "screen" and brightness_disabled:
        ttk.Checkbutton(theme_frame, text=theme["nickname"], variable=theme["checked"]).grid(
            row=idx + 1, column=0, sticky="w", columnspan=2, padx=PADX, pady=PADY
        )
        ttk.Entry(theme_frame, textvariable=theme["name_var"]).grid(
            row=idx + 1, column=2, sticky="ew", padx=PADX, pady=PADY
        )
    else:
        ttk.Checkbutton(theme_frame, text=theme["nickname"], variable=theme["checked"]).grid(
            row=idx + 1, column=0, sticky="w", columnspan=2, padx=PADX, pady=PADY
        )
        ttk.Entry(theme_frame, textvariable=theme["name_var"]).grid(
            row=idx + 1, column=2, sticky="ew", padx=PADX, pady=PADY
        )

# 自定义主题列表
custom_themes: List[Dict[str, Any]] = []

# 自定义主题列表组件
custom_theme_tree = ttk.Treeview(theme_frame, columns=("theme",), show="headings")
custom_theme_tree.heading("theme", text=t("双击即可修改"))
custom_theme_tree.grid(row=1, column=3, rowspan=5, pady=PADY, padx=PADX, sticky="nsew")

# 刷新主题配置按钮
ttk.Button(theme_frame, text=t("刷新"), command=refresh_custom_themes).grid(
    row=6, pady=PADY, padx=PADX, column=0, sticky="w"
)
ttk.Button(theme_frame, text=t("更多"), command=open_builtin_settings).grid(row=6, column=2, pady=PADY, padx=PADX, sticky="n")

# 添加和修改按钮
ttk.Button(theme_frame, text=t("添加"), command=lambda: add_custom_theme(config)).grid(
    row=6, pady=PADY, padx=PADX, column=3, sticky="w"
)
ttk.Button(theme_frame, text=t("修改"), command=lambda: modify_custom_theme()).grid(
    row=6, pady=PADY, padx=PADX, column=3, sticky="e"
)

# 绑定鼠标双击事件到自定义主题列表
custom_theme_tree.bind("<Double-Button-1>", on_double_click)

# 添加按钮到框架中
button_frame = tk.Frame(root)
button_frame.grid(row=3, column=0, pady=PADY * 2, padx=PADX, sticky="ew")
button_frame.grid_rowconfigure(0, weight=1)
button_frame.grid_columnconfigure(0, weight=1)
button_frame.grid_columnconfigure(1, weight=1)
button_frame.grid_columnconfigure(2, weight=1)

ttk.Button(button_frame, text=t("打开配置文件夹"), command=lambda:os.startfile(appdata_dir)).grid(
    row=0, column=0, padx=PADX, pady=PADY, sticky="e"
)
ttk.Button(button_frame, text=t("保存配置文件"), command=generate_config).grid(
    row=0, column=1, padx=PADX, pady=PADY, sticky="w"
)
ttk.Button(button_frame, text=t("取消"), command=lambda:root.destroy()).grid(
    row=0, column=2, padx=PADX, pady=PADY, sticky="w"
)

# 设置窗口在窗口大小变化时，框架自动扩展
root.rowconfigure(0, weight=1)
root.rowconfigure(1, weight=1)
root.rowconfigure(2, weight=0)
root.columnconfigure(0, weight=1)

# 设置窗口居中
# center_window(root)

# 调用加载自定义主题的函数
load_custom_themes()

# 初始应用一次语言（确保 LabelFrame/heading/按钮在英文模式下生效）
_apply_language_everywhere()

root.mainloop()

# 释放互斥体
# ctypes.windll.kernel32.ReleaseMutex(mutex)

"""
GUI程序用来生成配置文件(用于Windows系统)
系统配置的内容为:
1.网站
2.密钥
3.端口
4.test模式开关(用于记录是否开启测试模式)
主题配置的内容为:
注:2和4和5是自定义主题才有,内置主题和自定义主题要分开显示,第一次打开无自定义主题
1.向服务器订阅用的主题名称
2.主题昵称
3.主题开关状态
4.主题值(需要填写路径,或调用系统api选择文件),是一个程序或文件(绝对路径)
5.主题类型(程序或者服务)下拉框选择(默认为程序)
自定义主题部分有两个按钮:添加和修改
添加按钮会弹出一个窗口,选择主题类型,主题开关状态,填写主题昵称,主题名称,主题值
修改按钮会弹出一个窗口,修改主题,有保存和删除按钮
"""
