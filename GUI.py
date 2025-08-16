"""打包命令
pyinstaller -F -n RC-GUI --noconsole --icon=res\\icon_GUI.ico GUI.py
程序名：RC-GUI.exe
"""
import os
import tkinter as tk
from tkinter import messagebox, filedialog
import tkinter.ttk as ttk
import tkinter.font as tkfont
import json
import ctypes
import sys
import shlex
import subprocess
import win32com.client
from typing import Any, Dict, List, Union

BANBEN = "V2.2.0"
# 创建一个命名的互斥体
# mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "RC-main-GUI")

# 检查互斥体是否已经存在
# if ctypes.windll.kernel32.GetLastError() == 183:
#     messagebox.showerror("错误", "应用程序已在运行。")
#     sys.exit()

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

def run_py_in_venv_as_admin_hidden(python_exe_path, script_path, script_args=None):
    """
    使用指定的 Python 解释器（如虚拟环境中的 python.exe）以管理员权限静默运行脚本
    
    参数：
    python_exe_path (str): Python 解释器路径
    script_path (str): 要运行的 Python 脚本路径
    script_args (list): 传递给脚本的参数（可选）
    """
    if not os.path.exists(python_exe_path):
        raise FileNotFoundError(f"Python 解释器未找到: {python_exe_path}")

    if script_args is None:
        script_args = []

    # 构造命令（确保路径带引号，防止空格问题）
    command = f'"{python_exe_path}" "{script_path}" {" ".join(script_args)}'

    # 使用 ShellExecuteW 以管理员权限静默运行
    result = ctypes.windll.shell32.ShellExecuteW(
        None,               # 父窗口句柄
        'runas',            # 请求管理员权限
        'cmd.exe',          # 通过 cmd 执行（但隐藏窗口）
        f'/c {command}',    # /c 执行后关闭窗口
        None,               # 工作目录
        0                   # 窗口模式：0=隐藏
    )
    return result

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
            # EXE模式：直接以管理员权限运行exe
            result = run_as_admin(current_exe)
        else:
            # 脚本模式：以管理员权限运行Python脚本
            result = run_py_in_venv_as_admin_hidden(current_exe, os.path.abspath(__file__))
        
        if result > 32:  # ShellExecuteW 返回值大于32表示成功
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
        if messagebox.askyesno("管理员权限", "程序未获得管理员权限。\n是否立即请求管理员权限？\n\n选择'是'将重新启动程序并请求管理员权限。"):
            # 以管理员权限重新启动程序
            return restart_self_as_admin()
        else:
            return False
        
    except Exception as e:
        messagebox.showerror("管理员权限", f"提权失败: {e}")
        return False

def startup_admin_check():
    """启动时进行管理员权限检查和自动提权"""
    try:
        # 检查并请求提权（如果需要的话）
        admin_result = check_and_request_uac()
        if admin_result is False:  # 明确检查False，因为None表示其他情况
            messagebox.showinfo("管理员权限", "未进行提权或提权失败，程序将以当前权限继续运行")
        # 如果admin_result是True，说明已经有管理员权限
        # 如果函数内部重启了程序，这里的代码不会执行到
    except Exception as e:
        messagebox.showerror("管理员权限检查", f"管理员权限检查过程中出现异常: {e}")


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

    _set_font("TkDefaultFont", preferred_ui)
    _set_font("TkTextFont", preferred_ui)
    _set_font("TkMenuFont", preferred_ui)
    _set_font("TkHeadingFont", preferred_ui, min_size=10)
    _set_font("TkCaptionFont", preferred_ui)
    _set_font("TkSmallCaptionFont", preferred_ui)
    _set_font("TkIconFont", preferred_ui)
    _set_font("TkTooltipFont", preferred_ui)
    _set_font("TkFixedFont", preferred_fixed)

    # 按系统缩放设置 Tk scaling（像素/pt，pt=1/72英寸）
    try:
        scale_pct = None
        try:
            # Windows 8.1+ 可用，返回 100/125/150...
            scale_pct = ctypes.c_uint()
            ctypes.windll.shcore.GetScaleFactorForDevice(0, ctypes.byref(scale_pct))
            scale_pct = scale_pct.value
        except Exception:
            scale_pct = None

        if scale_pct:
            dpi = 96 * (scale_pct / 100.0)
            scaling = dpi / 72.0
            root.tk.call("tk", "scaling", scaling)
    except Exception:
        pass

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
            row_h = max(22, int(linespace + 10))
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
    rec.title("录制键盘组合")
    rec.geometry("580x360")
    msg = ttk.Label(
        rec,
        text=(
            "请在此窗口按下要录制的组合键，\n"
            "按 Enter 完成，Esc 取消。\n"
            "支持：Ctrl/Alt/Shift/Win 与普通键。\n\n"
            "若不包含 +（加号），按字符序列逐个发送：例 f4 => f 然后 4。\n\n"
            "包含 + 时：字母段会按顺序逐个输入（例 qste）\n功能键（F1..F24、Tab、Enter、Esc 等）按原键发送。\n\n"
            "同时支持后缀 {down}/{up} 或 _down/_up 显式按下/抬起。\n"
            "提示：中文输入法状态下，仅记录英文字母/数字/功能键，中文字符将被忽略。\n"
            "示例：ctrl{down}+shift{down}+f4+shift{up}+d+ctrl{up}"
        ),
        justify="left",
    )
    msg.pack(padx=10, pady=8, anchor="w")

    # 记录按下顺序：允许重复键，使用列表保存顺序
    pressed_order: list[str] = []
    pressed_var = tk.StringVar(value="已按下：(空)")
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
        messagebox.showerror(
            "错误", "未找到 RC-main.exe 文件\n请检查文件是否存在"
        )
        return
    
    # 让用户选择两种方案
    choice = messagebox.askyesnocancel(
        "选择启动方案", 
        "请选择以下两种启动方案之一：\n\n" +
        "【方案一】用户登录时运行\n注：无托盘时推荐!!\n" +
        "优点：只有用户登录时才运行\n" +
        "缺点：需要用户登录后才能启动\n\n" +
        "【方案二】系统启动时运行\n注：有托盘时推荐!!\n" +
        "优点：系统启动即可运行，无需用户登录\n" +
        "缺点：需要登录后托盘自动重启主程序才能使用媒体控制\n\n" +
        "选择 是：【方案一】\n\n选择 否：【方案二】",
        icon='question'
    )
      # 如果用户取消选择（点击右上角X），则退出设置过程
    if choice is None:
        messagebox.showinfo("已取消", "已取消设置开机自启动")
        return

    quoted_exe_path = shlex.quote(exe_path)
    
    if choice == True:  # 选择"是"，对应方案一
        # 方案一：使用Administrators用户组创建任务计划，任何用户登录时运行
        result = subprocess.call(
            f'schtasks /Create /SC ONLOGON /TN "A远程控制" /TR "{quoted_exe_path}" /RU "BUILTIN\\Administrators" /RL HIGHEST /F',
            shell=True,
        )
    else:  # 选择"否"，对应方案二
        # 方案二：使用SYSTEM用户在系统启动时运行
        result = subprocess.call(
            f'schtasks /Create /SC ONSTART /TN "A远程控制" /TR "{quoted_exe_path}" /RU "SYSTEM" /RL HIGHEST /F',
            shell=True,
        )
    scheduler = win32com.client.Dispatch("Schedule.Service")
    scheduler.Connect()
    root_folder_main = scheduler.GetFolder("\\")
    task_definition = root_folder_main.GetTask("A远程控制").Definition
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
    root_folder_main.RegisterTaskDefinition("A远程控制", task_definition, 6, "", "", 2)  # 0表示只在用户登录时运行，2表示不管用户是否登录都运行
    tray_exe_path = os.path.join(
            os.path.dirname(os.path.abspath(sys.argv[0])), "RC-tray.exe"
            # and "tray.py"
        )
    if os.path.exists(tray_exe_path):
        quoted_tray_path = shlex.quote(tray_exe_path)  # 托盘程序使用当前登录用户（最高权限）运行，登录后触发
        tray_result = subprocess.call(
            f'schtasks /Create /SC ONLOGON /TN "A远程控制-托盘" /TR "{quoted_tray_path}" /RL HIGHEST /F',
            shell=True,
        )
        # 同步设置权限和运行级别
        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        root_folder_tray = scheduler.GetFolder("\\")
        task_def = root_folder_tray.GetTask("A远程控制-托盘").Definition
        settings_tray = task_def.Settings
        settings_tray.MultipleInstances = 0  # 并行运行:0，排队：1，不运行：2，停止运行的：3
        settings_tray.Hidden = False  # 确保不是隐藏运行
        settings_tray.DisallowStartIfOnBatteries = False  # 不允许在电池供电时启动
        settings_tray.StopIfGoingOnBatteries = False      # 允许在电池供电时启动
        settings_tray.ExecutionTimeLimit = "PT0S"         # 无限时间限制
        # task_def.Settings.Compatibility = 4

        root_folder_tray.RegisterTaskDefinition(
            "A远程控制-托盘", task_def, 6, "", "", 0  # 0表示只在用户登录时运行，2表示不管用户是否登录都运行
        )
        # if tray_result == 0:
        #     messagebox.showinfo("提示", "创建托盘任务成功(使用当前登录用户，最高权限运行)")
        # else:
        #     messagebox.showerror("错误", "创建托盘自启动失败")
    else:
        messagebox.showwarning("警告", "未找到 RC-tray.exe 文件，跳过托盘启动设置")    # 检查创建任务的结果
    if check_task_exists("A远程控制"):
        if choice == True:  # 选择"是"，对应方案一
            messagebox.showinfo("提示", "创建任务成功\n已配置为任何用户登录时以管理员组权限运行")
        else:  # 选择"否"，对应方案二
            messagebox.showinfo("提示", "创建任务成功\n已配置为系统启动时以SYSTEM用户权限运行")
            if tray_result != 0:
                messagebox.showwarning("警告", f"创建托盘自启动失败\n{tray_result}")
        messagebox.showinfo("提示", "移动文件位置后需重新设置任务哦！")
        check_task()
    else:
        messagebox.showerror("错误", f"创建开机自启动失败\n{result}")
        check_task()


# 移除开机自启动
def remove_auto_start() -> None:
    """
    English: Removes the scheduled task for auto-start
    中文: 移除开机自启动的计划任务
    """
    if messagebox.askyesno("确定？", "你确定要删除开机自启动任务吗？"):
        delete_result = subprocess.call(
            'schtasks /Delete /TN "A远程控制" /F', shell=True
        )
        tray_delete = subprocess.call(
            'schtasks /Delete /TN "A远程控制-托盘" /F', shell=True
        )
        if delete_result == 0 and tray_delete == 0:
            messagebox.showinfo("提示", "关闭所有自启动任务成功")
        elif delete_result == 0:
            messagebox.showinfo("提示", "关闭主程序自启动成功，托盘任务不存在")
        elif tray_delete == 0:
            messagebox.showinfo("提示", "关闭托盘自启动成功，主程序任务不存在")
        else:
            messagebox.showerror("错误", "关闭开机自启动失败")
        check_task()


# 检查是否有计划任务并更新按钮状态
def check_task() -> None:
    """
    English: Updates the button text based on whether the auto-start task exists
    中文: 检查是否存在开机自启任务，并更新按钮文字
    """
    if check_task_exists("A远程控制"):
        auto_start_button.config(text="关闭开机自启", command=remove_auto_start)
    else:
        auto_start_button.config(text="设置开机自启", command=set_auto_start)
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
            theme = {
                "type": "程序或脚本",
                "checked": config.get(f"{app_key}_checked", 0),
                "nickname": config.get(f"{app_key}_name", ""),
                "name": config.get(app_key, ""),
                "value": config.get(f"{app_key}_directory{app_index}", ""),
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
            theme = {
                "type": "服务(需管理员权限)",
                "checked": config.get(f"{serve_key}_checked", 0),
                "nickname": config.get(f"{serve_key}_name", ""),
                "name": config.get(serve_key, ""),
                "value": config.get(f"{serve_key}_value", ""),
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
            theme = {
                "type": "命令",
                "checked": config.get(f"{cmd_key}_checked", 0),
                "nickname": config.get(f"{cmd_key}_name", ""),
                "name": config.get(cmd_key, ""),
                "value": config.get(f"{cmd_key}_value", ""),
                "window": config.get(f"{cmd_key}_window", "show"),
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
                "char_delay_ms": int(config.get(f"{hk_key}_char_delay_ms", 25) or 25),
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


def show_detail_window():
    detail_win = tk.Toplevel(root)
    detail_win.title("详情信息")
    detail_win.geometry("600x800")
    detail_text = tk.Text(detail_win, wrap="word")
    sleep()
    detail_text.insert("end", "\n【内置主题详解】\n\n屏幕：\n\n        灯泡设备，通过API调节屏幕亮度(百分比)\n\n\n音量：\n\n        窗帘设备，可调节系统总音量(百分比)，暂停为静音\n\n\n媒体控制：\n\n        窗帘设备，可控制系统媒体播放\n\n        打开(on)：上一曲\n\n        关闭(off)：下一曲\n\n        暂停(pause)：播放/暂停\n\n        打开百分比(on#80)：\n\n          1-33%：下一曲\n\n          34-66%：播放/暂停\n\n          67-100%：上一曲\n\n\n【自定义主题详解】\n\n\n注：[均为开关设备]\n\n程序或脚本：\n\n        需要填写路径，或调用系统api选择程序或脚本文件\n\n\n服务：\n\n        主程序需要管理员权限（开机自启时默认拥有）\n        填写服务名称\n\n\n命令：\n\n        需要填写需要执行的命令，关闭为发送中断信号\n\n\n")
    detail_text.config(state="disabled")
    detail_text.pack(expand=True, fill="both", padx=10, pady=10)
    center_window(detail_win)


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
        messagebox.showwarning("警告", "请先选择一个自定义主题")
        return

    index = int(selected[0])
    theme = custom_themes[index]

    theme_window = tk.Toplevel(root)
    theme_window.title("修改自定义主题")
    # 增加默认高度
    try:
        theme_window.geometry("780x310")
    except Exception:
        pass
    # 允许窗口大小调整，并设置网格权重使输入控件随窗口拉伸
    theme_window.resizable(True, True)
    try:
        theme_window.columnconfigure(0, weight=0)
        theme_window.columnconfigure(1, weight=1)
        theme_window.columnconfigure(2, weight=0)
        theme_window.columnconfigure(3, weight=0)
    except Exception:
        pass

    ttk.Label(theme_window, text="类型：").grid(row=0, column=0, sticky="e")
    theme_type_var = tk.StringVar(value=theme["type"])
    # 创建 Combobox
    theme_type_combobox = ttk.Combobox(
        theme_window, 
        textvariable=theme_type_var, 
        values=["程序或脚本", "服务(需管理员权限)", "命令", "按键(Hotkey)"],
        state="readonly"
    )
    theme_type_combobox.grid(row=0, column=1, sticky="we")
    _type_options = ["程序或脚本", "服务(需管理员权限)", "命令", "按键(Hotkey)"]
    try:
        type_index = _type_options.index(theme["type"])
    except ValueError:
        type_index = 0
    theme_type_combobox.current(type_index)

    ttk.Label(theme_window, text="服务时主程序").grid(row=0, column=2, sticky="w")
    ttk.Label(theme_window, text="需管理员权限").grid(row=1, column=2, sticky="w")

    ttk.Label(theme_window, text="状态：").grid(row=1, column=0, sticky="e")
    theme_checked_var = tk.IntVar(value=theme["checked"])
    ttk.Checkbutton(theme_window, variable=theme_checked_var).grid(
        row=1, column=1, sticky="w"
    )

    ttk.Label(theme_window, text="昵称：").grid(row=2, column=0, sticky="e")
    theme_nickname_entry = ttk.Entry(theme_window)
    theme_nickname_entry.insert(0, theme["nickname"])
    theme_nickname_entry.grid(row=2, column=1, sticky="we")

    ttk.Label(theme_window, text="主题：").grid(row=3, column=0, sticky="e")
    theme_name_entry = ttk.Entry(theme_window)
    theme_name_entry.insert(0, theme["name"])
    theme_name_entry.grid(row=3, column=1, sticky="we")

    ttk.Label(theme_window, text="值：").grid(row=4, column=0, sticky="ne")
    # 可纵向拉伸的多行文本框 + 滚动条
    value_frame_mod = ttk.Frame(theme_window)
    value_frame_mod.grid(row=4, column=1, sticky="nsew")
    try:
        theme_window.rowconfigure(4, weight=2)
    except Exception:
        pass
    theme_value_text = tk.Text(value_frame_mod, height=4, wrap="word")
    theme_value_text.insert("1.0", theme.get("value", ""))
    theme_value_text.grid(row=0, column=0, sticky="nsew")
    value_scroll_y = ttk.Scrollbar(value_frame_mod, orient="vertical", command=theme_value_text.yview)
    value_scroll_y.grid(row=0, column=1, sticky="ns")
    theme_value_text.configure(yscrollcommand=value_scroll_y.set)
    try:
        value_frame_mod.columnconfigure(0, weight=1)
        value_frame_mod.rowconfigure(0, weight=1)
    except Exception:
        pass

    def select_file():
        file_path = filedialog.askopenfilename()
        if file_path:
            theme_value_text.delete("1.0", tk.END)
            theme_value_text.insert("1.0", file_path)

    select_file_btn_mod = ttk.Button(theme_window, text="选择文件", command=select_file)
    select_file_btn_mod.grid(row=4, column=2, sticky="w", padx=15)

    # 垂直方向自适应：占位扩展区，推开底部按钮
    try:
        theme_window.rowconfigure(5, weight=1)
        _spacer_mod = ttk.Frame(theme_window)
        _spacer_mod.grid(row=5, column=0, columnspan=4, sticky="nsew")
    except Exception:
        pass

    # 命令类型：命令窗口显示/隐藏 -> 改为复选框，放在“状态”后面
    cmd_window_var = tk.IntVar(value=0 if theme.get("window", "show") == "hide" else 1)
    cmd_window_check = ttk.Checkbutton(theme_window, text="显示窗口", variable=cmd_window_var)

    # Hotkey 专用设置（修改窗口）
    hotkey_frame_mod = ttk.Labelframe(theme_window, text="按键(Hotkey) 设置")
    hk_type_labels = ["不执行", "键盘组合"]
    hk_type_map = {"不执行": "none", "键盘组合": "keyboard"}
    hk_label_by_type = {v: k for k, v in hk_type_map.items()}

    hk_on_type_var_mod = tk.StringVar(value=hk_label_by_type.get(theme.get("on_type", "keyboard"), "不执行"))
    hk_on_val_var_mod = tk.StringVar(value=theme.get("on_value", ""))
    hk_off_type_var_mod = tk.StringVar(value=hk_label_by_type.get(theme.get("off_type", "none"), "不执行"))
    hk_off_val_var_mod = tk.StringVar(value=theme.get("off_value", ""))
    hk_char_delay_var_mod = tk.StringVar(value=str(theme.get("char_delay_ms", 0)))

    ttk.Label(hotkey_frame_mod, text="打开(on)：").grid(row=0, column=0, sticky="e", padx=8, pady=4)
    hk_on_type_combo_mod = ttk.Combobox(hotkey_frame_mod, values=hk_type_labels, textvariable=hk_on_type_var_mod, state="readonly", width=12)
    hk_on_type_combo_mod.grid(row=0, column=1, sticky="w")
    hk_on_entry_mod = ttk.Entry(hotkey_frame_mod, textvariable=hk_on_val_var_mod, width=24)
    hk_on_entry_mod.grid(row=0, column=2, sticky="w")
    ttk.Button(hotkey_frame_mod, text="录制", command=lambda: open_keyboard_recorder(theme_window, hk_on_val_var_mod)).grid(row=0, column=3, sticky="w")

    ttk.Label(hotkey_frame_mod, text="关闭(off)：").grid(row=1, column=0, sticky="e", padx=8, pady=4)
    hk_off_type_combo_mod = ttk.Combobox(hotkey_frame_mod, values=hk_type_labels, textvariable=hk_off_type_var_mod, state="readonly", width=12)
    hk_off_type_combo_mod.grid(row=1, column=1, sticky="w")
    hk_off_entry_mod = ttk.Entry(hotkey_frame_mod, textvariable=hk_off_val_var_mod, width=24)
    hk_off_entry_mod.grid(row=1, column=2, sticky="w")
    ttk.Button(hotkey_frame_mod, text="录制", command=lambda: open_keyboard_recorder(theme_window, hk_off_val_var_mod)).grid(row=1, column=3, sticky="w")

    ttk.Label(hotkey_frame_mod, text="字母段间隔(ms)：").grid(row=2, column=0, sticky="e", padx=8, pady=4)
    hk_char_delay_entry_mod = ttk.Entry(hotkey_frame_mod, textvariable=hk_char_delay_var_mod, width=12)
    hk_char_delay_entry_mod.grid(row=2, column=1, sticky="w")

    def _update_type_specific_mod(*_):
        t = theme_type_var.get()
        if t == "命令":
            cmd_window_check.grid(row=1, column=1, sticky="n")
        else:
            cmd_window_check.grid_remove()
        if t == "按键(Hotkey)":
            value_frame_mod.grid_remove()
            select_file_btn_mod.grid_remove()
            hotkey_frame_mod.grid(row=4, column=1, columnspan=2, sticky="we")
        else:
            hotkey_frame_mod.grid_remove()
            value_frame_mod.grid(row=4, column=1, sticky="nsew")
            select_file_btn_mod.grid(row=4, column=2, sticky="w", padx=15)

    theme_type_combobox.bind("<<ComboboxSelected>>", _update_type_specific_mod)
    _update_type_specific_mod()

    def save_theme():
        theme["type"] = theme_type_var.get()
        theme["checked"] = theme_checked_var.get()
        theme["nickname"] = theme_nickname_entry.get()
        theme["name"] = theme_name_entry.get()
        theme["value"] = theme_value_text.get("1.0", "end-1c").strip()
        if theme["type"] == "命令":
            theme["window"] = "show" if cmd_window_var.get() else "hide"
        if theme["type"] == "按键(Hotkey)":
            # 读取临时值以便在保存前校验
            _on_type = {"不执行": "none", "键盘组合": "keyboard"}.get(hk_on_type_var_mod.get(), "keyboard")
            _on_value = hk_on_val_var_mod.get().strip()
            _off_type = {"不执行": "none", "键盘组合": "keyboard"}.get(hk_off_type_var_mod.get(), "none")
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
                if not messagebox.askyesno("确认包含中文字符", msg, parent=theme_window):
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
            "确认删除", "确定要删除这个自定义主题吗？", parent=theme_window
        ):
            custom_themes.pop(index)
            # 重新构建整个树视图
            rebuild_custom_theme_tree()
            theme_window.destroy()
        else:
            theme_window.lift()

    ttk.Button(theme_window, text="保存", command=save_theme).grid(
        row=6, column=0, pady=15, padx=15
    )
    ttk.Button(theme_window, text="删除", command=delete_theme).grid(row=6, column=1)
    ttk.Button(theme_window, text="取消", command=lambda:theme_window.destroy()).grid(row=6, column=2)

    center_window(theme_window)


# 添加自定义主题的函数中，也要更新显示
def add_custom_theme(config: Dict[str, Any]) -> None:
    """
    English: Opens a new window to add a new custom theme and updates display
    中文: 打开新窗口添加新的自定义主题，并更新显示
    """
    theme_window = tk.Toplevel(root)
    theme_window.title("添加自定义主题")
    # 增加默认高度
    try:
        theme_window.geometry("780x310")
    except Exception:
        pass
    # 允许窗口大小调整，并设置网格权重使输入控件随窗口拉伸
    theme_window.resizable(True, True)
    try:
        theme_window.columnconfigure(0, weight=0)
        theme_window.columnconfigure(1, weight=1)
        theme_window.columnconfigure(2, weight=0)
        theme_window.columnconfigure(3, weight=0)
    except Exception:
        pass

    ttk.Label(theme_window, text="类型：").grid(row=0, column=0, sticky="e")
    theme_type_var = tk.StringVar(value="程序或脚本")
    theme_type_combobox = ttk.Combobox(
        theme_window, 
        textvariable=theme_type_var, 
        values=["程序或脚本", "服务(需管理员权限)", "命令", "按键(Hotkey)"],
        state="readonly"
    )
    theme_type_combobox.grid(row=0, column=1, sticky="we")


    ttk.Label(theme_window, text="服务时主程序").grid(row=0, column=2, sticky="w")
    ttk.Label(theme_window, text="需管理员权限").grid(row=1, column=2, sticky="w")

    ttk.Label(theme_window, text="状态：").grid(row=1, column=0, sticky="e")
    theme_checked_var = tk.IntVar()
    ttk.Checkbutton(theme_window, variable=theme_checked_var).grid(
        row=1, column=1, sticky="w"
    )

    ttk.Label(theme_window, text="昵称：").grid(row=2, column=0, sticky="e")
    theme_nickname_entry = ttk.Entry(theme_window)
    theme_nickname_entry.grid(row=2, column=1, sticky="we")

    ttk.Label(theme_window, text="主题：").grid(row=3, column=0, sticky="e")
    theme_name_entry = ttk.Entry(theme_window)
    theme_name_entry.grid(row=3, column=1, sticky="we")

    ttk.Label(theme_window, text="值：").grid(row=4, column=0, sticky="ne")
    # 可纵向拉伸的多行文本框 + 滚动条（用于程序/服务/命令）
    value_frame_add = ttk.Frame(theme_window)
    value_frame_add.grid(row=4, column=1, sticky="nsew")
    try:
        theme_window.rowconfigure(4, weight=2)
    except Exception:
        pass
    theme_value_text2 = tk.Text(value_frame_add, height=4, wrap="word")
    theme_value_text2.grid(row=0, column=0, sticky="nsew")
    value2_scroll_y = ttk.Scrollbar(value_frame_add, orient="vertical", command=theme_value_text2.yview)
    value2_scroll_y.grid(row=0, column=1, sticky="ns")
    theme_value_text2.configure(yscrollcommand=value2_scroll_y.set)
    try:
        value_frame_add.columnconfigure(0, weight=1)
        value_frame_add.rowconfigure(0, weight=1)
    except Exception:
        pass

    def select_file():
        file_path = filedialog.askopenfilename()
        if file_path:
            theme_value_text2.delete("1.0", tk.END)
            theme_value_text2.insert("1.0", file_path)

    select_file_btn_add = ttk.Button(theme_window, text="选择文件", command=select_file)
    select_file_btn_add.grid(row=4, column=2, sticky="w", padx=15)

    # Hotkey 专用设置区（默认隐藏，选中“按键(Hotkey)”时显示）
    hotkey_frame_add = ttk.Labelframe(theme_window, text="按键(Hotkey) 设置")
    # 键盘类型
    hk_type_labels = ["不执行", "键盘组合"]
    hk_type_map = {"不执行": "none", "键盘组合": "keyboard"}
    hk_label_by_type = {v: k for k, v in hk_type_map.items()}


    # 变量
    hk_on_type_var_add = tk.StringVar(value=hk_label_by_type.get("keyboard", "键盘组合"))
    hk_on_val_var_add = tk.StringVar(value="")
    hk_off_type_var_add = tk.StringVar(value=hk_label_by_type.get("none", "不执行"))
    hk_off_val_var_add = tk.StringVar(value="")
    hk_char_delay_var_add = tk.StringVar(value="25")

    ttk.Label(hotkey_frame_add, text="打开(on)：").grid(row=0, column=0, sticky="e", padx=8, pady=4)
    hk_on_type_combo_add = ttk.Combobox(hotkey_frame_add, values=hk_type_labels, textvariable=hk_on_type_var_add, state="readonly", width=12)
    hk_on_type_combo_add.grid(row=0, column=1, sticky="w")
    hk_on_entry_add = ttk.Entry(hotkey_frame_add, textvariable=hk_on_val_var_add, width=24)
    hk_on_entry_add.grid(row=0, column=2, sticky="w")
    ttk.Button(hotkey_frame_add, text="录制", command=lambda: open_keyboard_recorder(theme_window, hk_on_val_var_add)).grid(row=0, column=3, sticky="w")

    ttk.Label(hotkey_frame_add, text="关闭(off)：").grid(row=1, column=0, sticky="e", padx=8, pady=4)
    hk_off_type_combo_add = ttk.Combobox(hotkey_frame_add, values=hk_type_labels, textvariable=hk_off_type_var_add, state="readonly", width=12)
    hk_off_type_combo_add.grid(row=1, column=1, sticky="w")
    hk_off_entry_add = ttk.Entry(hotkey_frame_add, textvariable=hk_off_val_var_add, width=24)
    hk_off_entry_add.grid(row=1, column=2, sticky="w")
    ttk.Button(hotkey_frame_add, text="录制", command=lambda: open_keyboard_recorder(theme_window, hk_off_val_var_add)).grid(row=1, column=3, sticky="w")

    ttk.Label(hotkey_frame_add, text="字母段间隔(ms)：").grid(row=2, column=0, sticky="e", padx=8, pady=4)
    hk_char_delay_entry_add = ttk.Entry(hotkey_frame_add, textvariable=hk_char_delay_var_add, width=12)
    hk_char_delay_entry_add.grid(row=2, column=1, sticky="w")

    # 垂直方向自适应：占位扩展区，推开底部按钮
    try:
        theme_window.rowconfigure(5, weight=1)
        _spacer_add = ttk.Frame(theme_window)
        _spacer_add.grid(row=5, column=0, columnspan=4, sticky="nsew")
    except Exception:
        pass

    # 命令类型：命令窗口显示/隐藏 -> 改为复选框，放在“状态”后面
    cmd_window_var = tk.IntVar(value=1)
    cmd_window_check = ttk.Checkbutton(theme_window, text="显示窗口", variable=cmd_window_var)

    def _update_type_specific_add(*_):
        t = theme_type_var.get()
        if t == "命令":
            cmd_window_check.grid(row=1, column=1, sticky="n")
        else:
            cmd_window_check.grid_remove()
        # Hotkey 面板显示控制；同时隐藏/显示 值 文本和选择按钮
        if t == "按键(Hotkey)":
            # 隐藏值文本和选择按钮
            value_frame_add.grid_remove()
            select_file_btn_add.grid_remove()
            hotkey_frame_add.grid(row=4, column=1, columnspan=2, sticky="we")
        else:
            hotkey_frame_add.grid_remove()
            value_frame_add.grid(row=4, column=1, sticky="nsew")
            select_file_btn_add.grid(row=4, column=2, sticky="w", padx=15)

    theme_type_combobox.bind("<<ComboboxSelected>>", _update_type_specific_add)
    _update_type_specific_add()

    def save_theme():
        theme = {
            "type": theme_type_var.get(),
            "checked": theme_checked_var.get(),
            "nickname": theme_nickname_entry.get(),
            "name": theme_name_entry.get(),
            "value": theme_value_text2.get("1.0", "end-1c").strip(),
        }
        if theme["type"] == "命令":
            theme["window"] = "show" if cmd_window_var.get() else "hide"
        if theme["type"] == "按键(Hotkey)":
            _on_type = hk_type_map.get(hk_on_type_var_add.get(), "keyboard")
            _on_value = hk_on_val_var_add.get().strip()
            _off_type = hk_type_map.get(hk_off_type_var_add.get(), "none")
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
                if not messagebox.askyesno("确认包含中文字符", msg, parent=theme_window):
                    theme_window.lift()
                    return

            theme["on_type"] = _on_type
            theme["on_value"] = _on_value
            theme["off_type"] = _off_type
            theme["off_value"] = _off_value
            theme["char_delay_ms"] = _char_delay_ms
            theme["value"] = ""
        custom_themes.append(theme)
        # 重新构建整个树视图以确保索引正确
        rebuild_custom_theme_tree()
        theme_window.destroy()

    ttk.Button(theme_window, text="保存", command=save_theme).grid(
        row=6, column=0, pady=15, padx=15
    )
    ttk.Button(theme_window, text="取消", command=theme_window.destroy).grid(row=6, column=2)

    center_window(theme_window)


def generate_config() -> None:
    """
    English: Generates and saves the config file (JSON) based on the input
    中文: 根据输入生成并保存配置文件(JSON格式)
    """
    global config
    # 从现有配置复制，保留扩展键（如 computer_* / sleep_*）
    config = dict(config)
    # 覆盖基础配置项
    config.update({
        "broker": website_entry.get(),
        "port": int(port_entry.get()),
        "test": test_var.get(),
        "notify": notify_var.get(),
        "auth_mode": auth_mode_var.get(),
        "mqtt_username": mqtt_username_entry.get(),
        "mqtt_password": mqtt_password_entry.get(),
        "client_id": client_id_entry.get(),
    })

    # 内置主题配置
    for theme in builtin_themes:
        key = theme["key"]
        value = theme["name_var"].get()
        config[key] = value
        config[f"{key}_checked"] = theme["checked"].get()

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
            config[f"{prefix}_directory{app_index}"] = theme["value"]
            app_index += 1
        elif theme["type"] == "服务(需管理员权限)":
            prefix = f"serve{serve_index}"
            config[prefix] = theme["name"]
            config[f"{prefix}_name"] = theme["nickname"]
            config[f"{prefix}_checked"] = theme["checked"]
            config[f"{prefix}_value"] = theme["value"]
            serve_index += 1
        elif theme["type"] == "命令":
            prefix = f"command{command_index}"
            config[prefix] = theme["name"]
            config[f"{prefix}_name"] = theme["nickname"]
            config[f"{prefix}_checked"] = theme["checked"]
            config[f"{prefix}_value"] = theme["value"]
            # 保存命令窗口显示/隐藏设置，默认显示
            config[f"{prefix}_window"] = theme.get("window", "show")
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
    with open(config_file_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
    # 保存后刷新界面
    messagebox.showinfo("提示", "配置文件已保存\n请重新打开主程序以应用更改\n刷新test模式需重启本程序")
    # 重新读取配置
    with open(config_file_path, "r", encoding="utf-8") as f:
        config = json.load(f)
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
    if not messagebox.askyesno("确认刷新", "刷新将加载配置文件中的设置，\n您未保存的更改将会丢失！\n确定要继续吗？"):
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
            
            messagebox.showinfo("提示", "已从配置文件刷新自定义主题列表")
        except Exception as e:
            messagebox.showerror("错误", f"读取配置文件失败: {e}")
    else:
        messagebox.showwarning("警告", "配置文件不存在，无法刷新")

def sleep():
    # 检查系统休眠/睡眠支持（test模式开启时跳过检测）
    global sleep_disabled, sleep_status_message
    if not ("config" in globals() and config.get("test", 0) == 1):
        try:
            result = subprocess.run(["powercfg", "-a"], capture_output=True, text=True, shell=True)
            output = result.stdout + result.stderr
            # 只要有“休眠不可用”或“尚未启用休眠”就禁用
            if ("休眠不可用" in output) or ("尚未启用休眠" in output):
                sleep_disabled = True
            else:
                # 还需判断“休眠”行是否包含“不可用”
                if "休眠" in output:
                    lines = output.splitlines()
                    hibernate_line = next((l for l in lines if l.strip().startswith("休眠")), None)
                    if hibernate_line and ("不可用" in hibernate_line):
                        sleep_disabled = True
                    else:
                        sleep_disabled = False
                else:
                    sleep_disabled = True
            sleep_status_message = output.strip()
        except Exception as e:
            sleep_disabled = True
            sleep_status_message = f"检测失败: {e}"
    else:
        sleep_status_message = "test模式已开启，未检测系统休眠/睡眠支持。"

def check_brightness_support():
    # 检查系统亮度调节支持（test模式开启时跳过检测）
    global brightness_disabled, brightness_status_message
    if not ("config" in globals() and config.get("test", 0) == 1):
        try:
            # 尝试使用WMI获取亮度控制接口
            import wmi
            brightness_controllers = wmi.WMI(namespace="wmi").WmiMonitorBrightnessMethods()
            if not brightness_controllers:
                brightness_disabled = True
                brightness_status_message = "系统不支持亮度调节功能，未找到亮度控制接口。"
            else:
                brightness_disabled = False
                brightness_status_message = "系统支持亮度调节功能。"
        except Exception as e:
            brightness_disabled = True
            brightness_status_message = f"检测亮度控制接口失败: {e}"
    else:
        brightness_status_message = "test模式已开启，未检测系统亮度调节支持。"

def enable_sleep_window() -> None:
    """
    
    中文: 通过命令启用睡眠/休眠功能
    """
    # 二次确认
    if not messagebox.askyesno(
        "确认启用？",
        "将启用系统的休眠/睡眠功能。\n\n此操作会更改系统电源配置，需管理员权限。\n\n是否继续？",
    ):
        return
    # 检查是否有管理员权限
    if not IS_GUI_ADMIN:
        messagebox.showerror("错误", "需要管理员权限才能启用休眠/睡眠功能")
        return
    # 尝试启用休眠/睡眠功能
    try:
        result = subprocess.run(["powercfg", "/hibernate", "on"], capture_output=True, text=True, shell=True)
        if result.returncode == 0:
            messagebox.showinfo("提示", "休眠/睡眠功能已启用")
        else:
            messagebox.showerror("错误", f"启用失败: \n{result.stderr.strip()}")
    except Exception as e:
        messagebox.showerror("错误", f"启用失败: {e}")

def disable_sleep_window() -> None:
    """
    中文: 通过命令关闭睡眠/休眠功能
    """
    # 二次确认
    if not messagebox.askyesno(
        "确认关闭",
        "将关闭系统的休眠/睡眠功能。\n\n此操作会更改系统电源配置，需管理员权限。\n\n是否继续？",
    ):
        return
    # 检查是否有管理员权限
    if not IS_GUI_ADMIN:
        messagebox.showerror("错误", "需要管理员权限才能关闭休眠/睡眠功能")
        return
    # 尝试关闭休眠/睡眠功能
    try:
        result = subprocess.run(["powercfg", "/hibernate", "off"], capture_output=True, text=True, shell=True)
        if result.returncode == 0:
            messagebox.showinfo("提示", "休眠/睡眠功能已关闭")
        else:
            messagebox.showerror("错误", f"关闭失败: \n{result.stderr.strip()}")
    except Exception as e:
        messagebox.showerror("错误", f"关闭失败: {e}")

def check_sleep_status_window() -> None:
    """
    中文: 检查系统睡眠/休眠功能是否启用，并弹窗显示详细状态
    """
    try:
        result = subprocess.run(["powercfg", "-a"], capture_output=True, text=True, shell=True)
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            messagebox.showerror("检查失败", f"命令执行失败：\n{output.strip()}")
            return

        enabled = True
        if ("尚未启用休眠" in output) or ("休眠不可用" in output):
            enabled = False
        else:
            lines = output.splitlines()
            hibernate_line = next((l for l in lines if l.strip().startswith("休眠")), None)
            if hibernate_line and ("不可用" in hibernate_line):
                enabled = False

        status_text = "已启用（可用）" if enabled else "未启用或不可用"
        messagebox.showinfo("睡眠功能状态", f"休眠/睡眠状态：{status_text}\n\n详细信息：\n{output.strip()}")
    except Exception as e:
        messagebox.showerror("检查失败", f"检查时出错：{e}")

# 在程序启动时查询程序的管理员权限状态并保存为全局变量
IS_GUI_ADMIN = False
try:
    IS_GUI_ADMIN = ctypes.windll.shell32.IsUserAnAdmin() != 0
    # logging.info(f"程序管理员权限状态: {'已获得' if IS_TRAY_ADMIN else '未获得'}")
except Exception as e:
    # logging.error(f"检查程序管理员权限时出错: {e}")
    IS_GUI_ADMIN = False

# 启动时检查管理员权限并请求提权
check_and_request_uac()

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
        error_msg = f"配置文件格式错误：\n{str(e)}\n\n请选择：\n• 点击\"是\"删除错误的配置文件并继续\n• 点击\"否\"退出程序不删除配置文件"
        if messagebox.askyesno("配置文件错误", error_msg):
            # 用户选择删除配置文件
            try:
                os.rename(config_file_path, f"{config_file_path}.bak")
                messagebox.showinfo("备份完成", f"已将错误的配置文件备份为：\n{config_file_path}.bak")
            except Exception as backup_error:
                messagebox.showwarning("备份失败", f"无法备份配置文件：{str(backup_error)}\n将直接删除错误的配置文件。")           
                try:
                    os.remove(config_file_path)
                except Exception as remove_error:
                    messagebox.showerror("错误", f"无法删除配置文件：{str(remove_error)}\n程序将退出。")
                    sys.exit(1)
            # 继续使用空配置
            config = {}
        else:
            # 用户选择退出程序
            messagebox.showinfo("程序退出", "您选择了保留配置文件并退出程序。\n请手动修复配置文件后再次运行程序。")
            sys.exit(0)


# 创建主窗口前启用 DPI 感知
_enable_dpi_awareness()

# 创建主窗口
root = tk.Tk()
root.title(f"远程控制-{BANBEN}")

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

# 系统配置部分
system_frame = ttk.LabelFrame(root, text="系统配置")
system_frame.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")
for i in range(3):
    system_frame.rowconfigure(i, weight=1)
for j in range(3):
    system_frame.columnconfigure(j, weight=1)

ttk.Label(system_frame, text="网站：").grid(row=0, column=0, sticky="e")
website_entry = ttk.Entry(system_frame)
website_entry.grid(row=0, column=1, sticky="ew")
website_entry.insert(0, config.get("broker", ""))

ttk.Label(system_frame, text="端口：").grid(row=1, column=0, sticky="e")
port_entry = ttk.Entry(system_frame)
port_entry.grid(row=1, column=1, sticky="ew")
port_entry.insert(0, str(config.get("port", "")))

# MQTT认证模式选择
ttk.Label(system_frame, text="认证模式：").grid(row=2, column=0, sticky="e")
auth_mode_var = tk.StringVar(value=config.get("auth_mode", "private_key"))
auth_mode_combo = ttk.Combobox(system_frame, 
                               values=["私钥模式", "账密模式"], 
                               state="readonly", width=15)
auth_mode_combo.grid(row=2, column=1, sticky="w")

# 设置下拉框显示文本
def update_auth_mode_display():
    current_value = auth_mode_var.get()
    if current_value == "private_key":
        auth_mode_combo.set("私钥模式")
    elif current_value == "username_password":
        auth_mode_combo.set("账密模式")

# 绑定选择事件
def on_auth_mode_change(event):
    selected_text = auth_mode_combo.get()
    if selected_text == "私钥模式":
        auth_mode_var.set("private_key")
    elif selected_text == "账密模式":
        auth_mode_var.set("username_password")

auth_mode_combo.bind("<<ComboboxSelected>>", on_auth_mode_change)
update_auth_mode_display()

test_var = tk.IntVar(value=config.get("test", 0))
test_check = ttk.Checkbutton(system_frame, text="test模式", variable=test_var)
test_check.grid(row=3, column=0, sticky="n")

# 通知开关（控制主程序是否发送 toast 通知），位于 test 模式开关右侧
notify_var = tk.IntVar(value=config.get("notify", 1))
notify_check = ttk.Checkbutton(system_frame, text="通知提示", variable=notify_var)
notify_check.grid(row=3, column=1, sticky="n")

#添加打开任务计划按钮
task_button = ttk.Button(system_frame, text="点击打开任务计划", command=lambda:os.startfile("taskschd.msc"))
task_button.grid(row=3, column=2, sticky="n", padx=15)

# 添加设置开机自启动按钮上面的提示
auto_start_label = ttk.Label(
    system_frame,
    text="需要管理员权限才能设置",
)
auto_start_label.grid(row=0, column=2, sticky="n")
auto_start_label1 = ttk.Label(
    system_frame,
    text="开机自启/启用睡眠(休眠)功能",
)
auto_start_label1.grid(row=1, column=2, sticky="n")

# 添加设置开机自启动按钮
auto_start_button = ttk.Button(system_frame, text="", command=set_auto_start)
auto_start_button.grid(row=2, column=2,  sticky="n")

# MQTT认证配置部分
auth_frame = ttk.LabelFrame(root, text="MQTT认证配置")
auth_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
for i in range(3):
    auth_frame.rowconfigure(i, weight=1)
for j in range(3):
    auth_frame.columnconfigure(j, weight=1)

# 用户名配置
ttk.Label(auth_frame, text="用户名：").grid(row=0, column=0, sticky="e")
mqtt_username_entry = ttk.Entry(auth_frame)
mqtt_username_entry.grid(row=0, column=1, sticky="ew")
mqtt_username_entry.insert(0, config.get("mqtt_username", ""))

# 密码配置
ttk.Label(auth_frame, text="密码：").grid(row=1, column=0, sticky="e")
mqtt_password_entry = ttk.Entry(auth_frame, show="*")
mqtt_password_entry.grid(row=1, column=1, sticky="ew")
mqtt_password_entry.insert(0, config.get("mqtt_password", ""))

# 客户端ID配置
ttk.Label(auth_frame, text="客户端ID：").grid(row=2, column=0, sticky="e")
client_id_entry = ttk.Entry(auth_frame)
client_id_entry.grid(row=2, column=1, sticky="ew")
# 读取client_id配置
client_id_value = config.get("client_id", "")
client_id_entry.insert(0, client_id_value)

# 认证模式说明
auth_info_label = ttk.Label(
    auth_frame,
    text="私钥模式：\n        使用客户端ID作为私钥\n账密模式：\n        兼容大多数IoT平台",
    justify="left"
)
auth_info_label.grid(row=0, column=2, rowspan=3, sticky="n")

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

# 绑定认证模式变化事件
auth_mode_var.trace("w", toggle_auth_mode)
# 初始化界面状态
toggle_auth_mode()

# 程序标题栏
if IS_GUI_ADMIN:
    check_task()
    root.title(f"远程控制-{BANBEN}(管理员)")
else:
    auto_start_button.config(text="获取权限", command=get_administrator_privileges)

# 主题配置部分
theme_frame = ttk.LabelFrame(root, text="主题配置")
theme_frame.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")
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

ttk.Label(theme_frame, text="内置").grid(row=0, column=0, sticky="w")

# 更多：打开内置主题设置
def open_builtin_settings():
    win = tk.Toplevel(root)
    win.title("内置主题设置")
    # win.resizable(False, False)

    # 计算机主题动作（去除与睡眠主题重复的“睡眠/休眠”）
    actions = [
        ("none", "不执行"),
        ("lock", "锁屏"),
        ("shutdown", "关机"),
        ("restart", "重启"),
        ("logoff", "注销"),
    ]
    key_to_label = {k: v for k, v in actions}
    labels = [label for _, label in actions]
    key_by_label = {v: k for k, v in actions}

    # 读取计算机主题配置（带默认值）
    cur_on = config.get("computer_on_action", "lock")
    cur_off = config.get("computer_off_action", "restart")
    cur_on_delay = int(config.get("computer_on_delay", 0) or 0)
    cur_off_delay = int(config.get("computer_off_delay", 0) or 0)

    row_i = 0
    ttk.Label(win, text="计算机(Computer) 主题动作").grid(row=row_i, column=0, columnspan=3, padx=10, pady=(10, 6), sticky="w")
    row_i += 1

    ttk.Label(win, text="打开(on)：").grid(row=row_i, column=0, sticky="e", padx=8, pady=4)
    on_var = tk.StringVar(value=key_to_label.get(cur_on, "锁屏"))
    on_combo = ttk.Combobox(win, values=labels, textvariable=on_var, state="readonly", width=18)
    on_combo.grid(row=row_i, column=1, sticky="w")
    ttk.Label(win, text="延时(秒)：").grid(row=row_i, column=2, sticky="e", padx=8)
    on_delay_var = tk.StringVar(value=str(cur_on_delay))
    on_delay_entry = ttk.Entry(win, textvariable=on_delay_var, width=8)
    on_delay_entry.grid(row=row_i, column=3, sticky="w")
    row_i += 1

    ttk.Label(win, text="关闭(off)：").grid(row=row_i, column=0, sticky="e", padx=8, pady=4)
    off_var = tk.StringVar(value=key_to_label.get(cur_off, "重启"))
    off_combo = ttk.Combobox(win, values=labels, textvariable=off_var, state="readonly", width=18)
    off_combo.grid(row=row_i, column=1, sticky="w")
    ttk.Label(win, text="延时(秒)：").grid(row=row_i, column=2, sticky="e", padx=8)
    off_delay_var = tk.StringVar(value=str(cur_off_delay))
    off_delay_entry = ttk.Entry(win, textvariable=off_delay_var, width=8)
    off_delay_entry.grid(row=row_i, column=3, sticky="w")
    row_i += 1

    tip = ttk.Label(win, text="提示：计算机主题延时仅对关机/重启有效，其它动作忽略延时。")
    tip.grid(row=row_i, column=0, columnspan=4, padx=10, pady=(6, 10), sticky="w")
    row_i += 1

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
    s_labels_on = [label for _, label in sleep_actions_on]
    s_labels_off = [label for _, label in sleep_actions_off]
    s_key_by_label_on = {v: k for k, v in sleep_actions_on}
    s_key_by_label_off = {v: k for k, v in sleep_actions_off}
    s_key_to_label_on = {k: v for k, v in sleep_actions_on}
    s_key_to_label_off = {k: v for k, v in sleep_actions_off}

    s_cur_on = config.get("sleep_on_action", "sleep")
    s_cur_off = config.get("sleep_off_action", "none")
    s_cur_on_delay = int(config.get("sleep_on_delay", 0) or 0)
    s_cur_off_delay = int(config.get("sleep_off_delay", 0) or 0)

    ttk.Label(win, text="睡眠(sleep) 主题动作").grid(row=row_i, column=0, columnspan=4, padx=10, pady=(0, 6), sticky="w")
    row_i += 1

    ttk.Label(win, text="打开(on)：").grid(row=row_i, column=0, sticky="e", padx=8, pady=4)
    s_on_var = tk.StringVar(value=s_key_to_label_on.get(s_cur_on, "睡眠"))
    ttk.Combobox(win, values=s_labels_on, textvariable=s_on_var, state="readonly", width=18).grid(row=row_i, column=1, sticky="w")
    ttk.Label(win, text="延时(秒)：").grid(row=row_i, column=2, sticky="e", padx=8)
    s_on_delay_var = tk.StringVar(value=str(s_cur_on_delay))
    ttk.Entry(win, textvariable=s_on_delay_var, width=8).grid(row=row_i, column=3, sticky="w")
    row_i += 1

    ttk.Label(win, text="关闭(off)：").grid(row=row_i, column=0, sticky="e", padx=8, pady=4)
    s_off_var = tk.StringVar(value=s_key_to_label_off.get(s_cur_off, "不执行"))
    ttk.Combobox(win, values=s_labels_off, textvariable=s_off_var, state="readonly", width=18).grid(row=row_i, column=1, sticky="w")
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
            config["computer_on_action"] = key_by_label.get(on_var.get(), "lock")
            config["computer_off_action"] = key_by_label.get(off_var.get(), "restart")
            try:
                config["computer_on_delay"] = max(0, int(on_delay_var.get()))
            except Exception:
                config["computer_on_delay"] = 0
            try:
                config["computer_off_delay"] = max(0, int(off_delay_var.get()))
            except Exception:
                config["computer_off_delay"] = 60

            # 读取睡眠动作选择
            _sleep_on_sel = s_key_by_label_on.get(s_on_var.get(), "sleep")
            _sleep_off_sel = s_key_by_label_off.get(s_off_var.get(), "none")

            # 保存前，给出风险提示（不阻断保存）
            if (_sleep_on_sel in ("display_off", "display_on")) or (_sleep_off_sel in ("display_off", "display_on")):
                messagebox.showwarning("警告", "依赖于 Windows 的系统 API 来控制显示器电源状态\n未经过测试\n可能造成不可逆后果\n谨慎使用“开/关显示器功能”")

            # 打开动作为“睡眠/休眠”时提示：设备将离线
            if _sleep_on_sel in ("sleep", "hibernate"):
                messagebox.showwarning("提示", "当打开动作设置为“睡眠/休眠”时：\n设备将进入低功耗或断电状态，主程序会离线，\n期间无法接收远程命令，需要人工或计划唤醒。")

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

            # Hotkey 不在内置设置中保存

            # 统一通过 generate_config 保存并刷新
            generate_config()
            win.destroy()
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    btn_frame = ttk.Frame(win)
    btn_frame.grid(row=row_i, column=0, columnspan=4, pady=(0, 10))
    ttk.Button(btn_frame, text="保存", command=save_builtin_settings).grid(row=0, column=0, padx=6)
    ttk.Button(btn_frame, text="取消", command=win.destroy).grid(row=0, column=1, padx=6)

    # 窗口居中
    try:
        center_window(win)
    except Exception:
        pass


ttk.Button(theme_frame, text="详情", command=show_detail_window).grid(row=0, column=2, sticky="e", columnspan=2)
ttk.Label(theme_frame, text="主题：").grid(row=0, column=2, sticky="w")
ttk.Label(theme_frame, text="自定义：").grid(
    row=0, column=3, sticky="w"
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
        cb.grid(row=idx + 1, column=0, sticky="w", columnspan=2)
        entry = ttk.Entry(theme_frame, textvariable=theme["name_var"])
        entry.config(state="disabled")
        entry.grid(row=idx + 1, column=2, sticky="ew")
        # 改为不可点击提示
        sleep_tip = ttk.Label(theme_frame, text="休眠/睡眠不可用\n系统未启用休眠功能")
        sleep_tip.grid(row=idx + 1, column=2, sticky="w")
    elif theme_key == "screen" and brightness_disabled:
        theme["checked"].set(0)
        theme["name_var"].set("")
        cb = ttk.Checkbutton(theme_frame, text=theme["nickname"], variable=theme["checked"])
        cb.state(["disabled"])
        cb.grid(row=idx + 1, column=0, sticky="w", columnspan=2)
        entry = ttk.Entry(theme_frame, textvariable=theme["name_var"])
        entry.config(state="disabled")
        entry.grid(row=idx + 1, column=2, sticky="ew")
        # 改为不可点击提示
        brightness_tip = ttk.Label(theme_frame, text="亮度调节不可用\n系统不支持此功能")
        brightness_tip.grid(row=idx + 1, column=2, sticky="w")
    else:
        ttk.Checkbutton(theme_frame, text=theme["nickname"], variable=theme["checked"]).grid(
            row=idx + 1, column=0, sticky="w", columnspan=2
        )
        ttk.Entry(theme_frame, textvariable=theme["name_var"]).grid(
            row=idx + 1, column=2, sticky="ew"
        )

# 自定义主题列表
custom_themes: List[Dict[str, Any]] = []

# 自定义主题列表组件
custom_theme_tree = ttk.Treeview(theme_frame, columns=("theme",), show="headings")
custom_theme_tree.heading("theme", text="双击即可修改")
custom_theme_tree.grid(row=1, column=3, rowspan=5, pady=10, padx=15, sticky="nsew")

# 刷新主题配置按钮
ttk.Button(theme_frame, text="刷新", command=refresh_custom_themes).grid(
    row=6, pady=10, column=0, sticky="w"
)
ttk.Button(theme_frame, text="更多", command=open_builtin_settings).grid(row=6, column=2, pady=10, sticky="n")

# 添加和修改按钮
ttk.Button(theme_frame, text="添加", command=lambda: add_custom_theme(config)).grid(
    row=6, pady=10, column=3, sticky="w"
)
ttk.Button(theme_frame, text="修改", command=lambda: modify_custom_theme()).grid(
    row=6, pady=10, column=3, sticky="e"
)

# 绑定鼠标双击事件到自定义主题列表
custom_theme_tree.bind("<Double-Button-1>", on_double_click)

# 添加按钮到框架中
button_frame = tk.Frame(root)
button_frame.grid(row=3, column=0, pady=15, sticky="ew")
button_frame.grid_rowconfigure(0, weight=1)
button_frame.grid_columnconfigure(0, weight=1)
button_frame.grid_columnconfigure(1, weight=1)

ttk.Button(button_frame, text="打开配置文件夹", command=lambda:os.startfile(appdata_dir)).grid(
    row=0, column=0, padx=20, sticky="e"
)
ttk.Button(button_frame, text="保存配置文件", command=generate_config).grid(
    row=0, column=1, padx=20, sticky="w"
)
ttk.Button(button_frame, text="取消", command=lambda:root.destroy()).grid(
    row=0, column=2, padx=20, sticky="w"
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
