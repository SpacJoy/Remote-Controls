"""打包命令
pyinstaller -F -n RC-GUI --noconsole --icon=res\\icon_GUI.ico GUI.py
程序名：RC-GUI.exe
"""
import os
import tkinter as tk
from tkinter import messagebox, filedialog
import tkinter.ttk as ttk
import json
import ctypes
import sys
import shlex
import subprocess
import win32com.client
from typing import Any, Dict, List, Union

BANBEN = "V2.1.2"
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


def show_detail_window():
    detail_win = tk.Toplevel(root)
    detail_win.title("详情信息")
    detail_win.geometry("600x600")
    detail_text = tk.Text(detail_win, wrap="word")
    sleep()
    detail_text.insert("end", "\n【内置主题详解】\n计算机：\n    打开：锁定计算机（Win+L）\n    关闭：60秒后重启计算机\n屏幕：\n    灯泡设备，通过API调节屏幕亮度(百分比)\n音量：\n    窗帘设备，可调节系统总音量(百分比)，暂停为静音\n睡眠：\n    开关设备，可休眠计算机\n媒体控制：\n    窗帘设备，可控制系统媒体播放\n    打开(on)：上一曲\n    关闭(off)：下一曲\n    暂停(pause)：播放/暂停\n    打开百分比(on#80)：\n      1-33%：下一曲\n      34-66%：播放/暂停\n      67-100%：上一曲\n\n\n【自定义主题详解】\n\n注：[均为开关设备]\n程序或脚本：\n    需要填写路径，或调用系统api选择程序或脚本文件\n服务：\n    主程序需要管理员权限（开机自启时默认拥有）\n填写服务名称\n\n\n【系统睡眠支持检测】\n\n可开启test模式以禁用本程序的睡眠支持检测\n\n可尝试此命令启用：powercfg.exe /hibernate on\n\n" + sleep_status_message+"\n\n\n")
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
    theme_window.resizable(False, False)  # 禁用窗口大小调整

    ttk.Label(theme_window, text="类型：").grid(row=0, column=0, sticky="e")
    theme_type_var = tk.StringVar(value=theme["type"])
    # 创建 Combobox
    theme_type_combobox = ttk.Combobox(
        theme_window, 
        textvariable=theme_type_var, 
        values=["程序或脚本", "服务(需管理员权限)"],
        state="readonly"
    )
    theme_type_combobox.grid(row=0, column=1, sticky="w")
    type_index = ["程序或脚本", "服务(需管理员权限)"].index(theme["type"])
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
    theme_nickname_entry.grid(row=2, column=1, sticky="w")

    ttk.Label(theme_window, text="主题：").grid(row=3, column=0, sticky="e")
    theme_name_entry = ttk.Entry(theme_window)
    theme_name_entry.insert(0, theme["name"])
    theme_name_entry.grid(row=3, column=1, sticky="w")

    ttk.Label(theme_window, text="值：").grid(row=4, column=0, sticky="e")
    theme_value_entry = ttk.Entry(theme_window)
    theme_value_entry.insert(0, theme["value"])
    theme_value_entry.grid(row=4, column=1, sticky="w")

    def select_file():
        file_path = filedialog.askopenfilename()
        theme_value_entry.delete(0, tk.END)
        theme_value_entry.insert(0, file_path)

    ttk.Button(theme_window, text="选择文件", command=select_file).grid(
        row=4, column=2, sticky="w", padx=15
    )

    def save_theme():
        theme["type"] = theme_type_var.get()
        theme["checked"] = theme_checked_var.get()
        theme["nickname"] = theme_nickname_entry.get()
        theme["name"] = theme_name_entry.get()
        theme["value"] = theme_value_entry.get()
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
        row=5, column=0, pady=15, padx=15
    )
    ttk.Button(theme_window, text="删除", command=delete_theme).grid(row=5, column=1)
    ttk.Button(theme_window, text="取消", command=lambda:theme_window.destroy()).grid(row=5, column=2)

    center_window(theme_window)


# 添加自定义主题的函数中，也要更新显示
def add_custom_theme(config: Dict[str, Any]) -> None:
    """
    English: Opens a new window to add a new custom theme and updates display
    中文: 打开新窗口添加新的自定义主题，并更新显示
    """
    theme_window = tk.Toplevel(root)
    theme_window.title("添加自定义主题")
    theme_window.resizable(False, False)  # 禁用窗口大小调整

    ttk.Label(theme_window, text="类型：").grid(row=0, column=0, sticky="e")
    theme_type_var = tk.StringVar(value="程序或脚本")
    theme_type_combobox = ttk.Combobox(
        theme_window, 
        textvariable=theme_type_var, 
        values=["程序或脚本", "服务(需管理员权限)"],
        state="readonly"
    )
    theme_type_combobox.grid(row=0, column=1, sticky="w")


    ttk.Label(theme_window, text="服务时主程序").grid(row=0, column=2, sticky="w")
    ttk.Label(theme_window, text="需管理员权限").grid(row=1, column=2, sticky="w")

    ttk.Label(theme_window, text="状态：").grid(row=1, column=0, sticky="e")
    theme_checked_var = tk.IntVar()
    ttk.Checkbutton(theme_window, variable=theme_checked_var).grid(
        row=1, column=1, sticky="w"
    )

    ttk.Label(theme_window, text="昵称：").grid(row=2, column=0, sticky="e")
    theme_nickname_entry = ttk.Entry(theme_window)
    theme_nickname_entry.grid(row=2, column=1, sticky="w")

    ttk.Label(theme_window, text="主题：").grid(row=3, column=0, sticky="e")
    theme_name_entry = ttk.Entry(theme_window)
    theme_name_entry.grid(row=3, column=1, sticky="w")

    ttk.Label(theme_window, text="值：").grid(row=4, column=0, sticky="e")
    theme_value_entry = ttk.Entry(theme_window)
    theme_value_entry.grid(row=4, column=1, sticky="w")

    def select_file():
        file_path = filedialog.askopenfilename()
        theme_value_entry.delete(0, tk.END)
        theme_value_entry.insert(0, file_path)

    ttk.Button(theme_window, text="选择文件", command=select_file).grid(
        row=4, column=2, sticky="w", padx=15
    )

    def save_theme():
        theme = {
            "type": theme_type_var.get(),
            "checked": theme_checked_var.get(),
            "nickname": theme_nickname_entry.get(),
            "name": theme_name_entry.get(),
            "value": theme_value_entry.get(),
        }
        custom_themes.append(theme)
        # 重新构建整个树视图以确保索引正确
        rebuild_custom_theme_tree()
        theme_window.destroy()

    ttk.Button(theme_window, text="保存", command=save_theme).grid(
        row=5, column=0, pady=15, padx=15
    )
    ttk.Button(theme_window, text="取消", command=theme_window.destroy).grid(row=5, column=2)

    center_window(theme_window)


def generate_config() -> None:
    """
    English: Generates and saves the config file (JSON) based on the input
    中文: 根据输入生成并保存配置文件(JSON格式)
    """
    global config
    config = {
        "broker": website_entry.get(),
        "secret_id": secret_entry.get(),
        "port": int(port_entry.get()),
        "test": test_var.get(),
    }

    # 内置主题配置
    for theme in builtin_themes:
        key = theme["key"]
        value = theme["name_var"].get()
        config[key] = value
        config[f"{key}_checked"] = theme["checked"].get()

    # 自定义主题配置
    app_index = 1
    serve_index = 1
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

def enable_window() -> None:
    """
    
    中文: 通过命令启用睡眠/休眠功能
    """
    #检查是否有管理员权限
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


# 创建主窗口
root = tk.Tk()
root.title(f"远程控制-{BANBEN}")

# 设置根窗口的行列权重
root.rowconfigure(0, weight=1)
root.rowconfigure(1, weight=1)
root.rowconfigure(2, weight=0)
root.columnconfigure(0, weight=1)

# 系统配置部分
system_frame = ttk.LabelFrame(root, text="系统配置")
system_frame.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")
for i in range(4):
    system_frame.rowconfigure(i, weight=1)
for j in range(3):
    system_frame.columnconfigure(j, weight=1)

ttk.Label(system_frame, text="网站：").grid(row=0, column=0, sticky="e")
website_entry = ttk.Entry(system_frame)
website_entry.grid(row=0, column=1, sticky="ew")
website_entry.insert(0, config.get("broker", ""))

ttk.Label(system_frame, text="密钥：").grid(row=1, column=0, pady=10,sticky="e")
secret_entry = ttk.Entry(system_frame,show="*")
secret_entry.grid(row=1, column=1, sticky="ew")
secret_entry.insert(0, config.get("secret_id", ""))

ttk.Label(system_frame, text="端口：").grid(row=2, column=0, sticky="e")
port_entry = ttk.Entry(system_frame)
port_entry.grid(row=2, column=1, sticky="ew")
port_entry.insert(0, str(config.get("port", "")))

test_var = tk.IntVar(value=config.get("test", 0))
test_check = ttk.Checkbutton(system_frame, text="test模式", variable=test_var)
test_check.grid(row=3, column=0, columnspan=2, sticky="w")

#添加打开任务计划按钮
task_button = ttk.Button(system_frame, text="点击此按钮可以手动设置", command=lambda:os.startfile("taskschd.msc"))
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

# 程序标题栏
if IS_GUI_ADMIN:
    check_task()
    root.title(f"远程控制-{BANBEN}(管理员)")
else:
    auto_start_button.config(text="获取权限", command=get_administrator_privileges)

# 主题配置部分
theme_frame = ttk.LabelFrame(root, text="主题配置")
theme_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
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
ttk.Button(theme_frame, text="详情", command=show_detail_window).grid(row=0, column=1, sticky="e", columnspan=2)
ttk.Label(theme_frame, text="主题:").grid(row=0, column=2, sticky="w")
ttk.Label(theme_frame, text="自定义(服务需管理员)").grid(
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
        sleep_tip = ttk.Button(theme_frame, text="休眠/睡眠不可用\n点击(详情)查看原因",command=enable_window)
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
        brightness_tip = ttk.Button(theme_frame, text="亮度调节不可用\n系统不支持此功能",command=show_detail_window)
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
custom_theme_tree.grid(row=1, column=3, rowspan=5, pady=10, sticky="nsew")

# 刷新主题配置按钮
ttk.Button(theme_frame, text="刷新", command=refresh_custom_themes).grid(
    row=6, column=0, sticky="w"
)
# 添加和修改按钮
ttk.Button(theme_frame, text="添加", command=lambda: add_custom_theme(config)).grid(
    row=6, column=3, sticky="w"
)
ttk.Button(theme_frame, text="修改", command=lambda: modify_custom_theme()).grid(
    row=6, column=3, sticky="e"
)

# 绑定鼠标双击事件到自定义主题列表
custom_theme_tree.bind("<Double-Button-1>", on_double_click)

# 添加按钮到框架中
button_frame = tk.Frame(root)
button_frame.grid(row=2, column=0, pady=15, sticky="ew")
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
