"""
打包指令:
1) 推荐：使用 spec 文件
    pyinstaller RC-main.spec --noconfirm

2) 直接命令行（仅 icon.ico，放到根目录）
pyinstaller -F -n RC-main --windowed --icon=res\\icon.ico --add-data "res\\icon.ico;." main.py
程序名：RC-main.exe
运行用户：当前登录用户（通过计划任务启动）
"""

#导入各种必要的模块
import io
import paho.mqtt.client as mqtt
import os
import psutil
import pystray
from PIL import Image
import wmi
from win11toast import notify
import json
import logging
from logging.handlers import RotatingFileHandler
from tkinter import messagebox
import sys
import threading
import subprocess
import time
import ctypes
import socket
from comtypes import CLSCTX_ALL
import signal
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import pyautogui
from pyautogui import press as pyautogui_press

# 统一版本来源
try:
    from version_info import get_version_string
    BANBEN = f"V{get_version_string()}"
except Exception:
    BANBEN = "V未知版本"

# DPI 与字体渲染优化（高DPI下更清晰）
def _enable_dpi_awareness() -> None:
    """
    使进程 DPI 感知，避免高分屏托盘菜单/提示发糊。
    优先 Per-Monitor DPI 感知，回退到 System DPI Aware。
    """
    try:
        shcore = ctypes.windll.shcore
        # 2 = PROCESS_PER_MONITOR_DPI_AWARE
        shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# 禁用 PyAutoGUI 安全模式，确保即使鼠标在屏幕角落也能执行命令
pyautogui.FAILSAFE = False

# 运行模式 & 隐藏控制台
is_script_mode = not getattr(sys, 'frozen', False)

def hide_console():
    """隐藏当前控制台窗口（脚本模式启动时使用，可用 RC_NO_HIDE=1 禁用）。"""
    try:
        if os.environ.get('RC_NO_HIDE') == '1':
            return
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass

if is_script_mode:
    hide_console()

# 创建互斥体并进行更严格的二次确认，避免脚本模式下误报
MUTEX_NAME = "RC-main"
mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
last_err = ctypes.windll.kernel32.GetLastError()

def _other_instance_exists() -> bool:
    """通过进程列表确认是否有其他实例运行。"""
    try:
        current_pid = os.getpid()
        target_script = os.path.abspath(__file__)
        exe_name = "RC-main.exe"
        found_other = False
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            if proc.info.get("pid") == current_pid:
                continue
            name = (proc.info.get("name") or "").lower()
            if name == exe_name.lower():
                found_other = True
                break
            # 脚本模式判定：python 进程且 cmdline 包含 main.py 绝对路径
            if name in ("python.exe", "pythonw.exe"):
                cmd = " ".join(proc.info.get("cmdline") or [])
                # 用 endswith 防止路径差异带来的子串误匹配
                if cmd and os.path.basename(target_script) in cmd and target_script in cmd:
                    found_other = True
                    break
        return found_other
    except Exception:
        # 容错：若进程枚举失败，保持保守（返回 True 避免多开）
        return True

if last_err == 183:  # ERROR_ALREADY_EXISTS
    def _list_other_instances():
        items = []
        try:
            current_pid = os.getpid()
            target_script = os.path.abspath(__file__)
            exe_name = "RC-main.exe"
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                pid = proc.info.get("pid")
                if pid == current_pid:
                    continue
                name = (proc.info.get("name") or "").lower()
                cl_list = proc.info.get("cmdline") or []
                cmdline = " ".join(cl_list)
                match = False
                if name == exe_name.lower():
                    match = True
                elif name in ("python.exe", "pythonw.exe") and target_script in cmdline:
                    match = True
                if match:
                    items.append((pid, proc.info.get("name"), cmdline))
        except Exception:
            pass
        return items

    others = _list_other_instances()
    if others:
        if is_script_mode:
            # 使用原生 MessageBox (YES=结束其它实例并继续, NO=忽略互斥体直接继续, CANCEL=退出)
            try:
                details = "\n".join([f"PID {pid} - {name}" for pid, name, _ in others][:10])
                if len(others) > 10:
                    details += f"\n... 共 {len(others)} 个实例"
                text = (
                    "检测到程序已在运行:\n\n" + details +
                    "\n\n是: 结束其它实例后继续\n否: 忽略互斥体直接继续(可能导致多开)\n取消: 退出程序"
                )
                MB_ICONQUESTION = 0x20
                MB_YESNOCANCEL = 0x03
                res = ctypes.windll.user32.MessageBoxW(None, text, "程序已在运行", MB_ICONQUESTION | MB_YESNOCANCEL)
                IDYES, IDNO, IDCANCEL = 6, 7, 2
                if res == IDYES:
                    # 结束其它实例
                    for pid, _name, _ in others:
                        try:
                            psutil.Process(pid).terminate()
                        except Exception:
                            pass
                    deadline = time.time() + 3
                    while time.time() < deadline:
                        if all(not psutil.pid_exists(pid) for pid, _, _ in others):
                            break
                        time.sleep(0.2)
                    still = [pid for pid, _, _ in others if psutil.pid_exists(pid)]
                    if still:
                        ctypes.windll.user32.MessageBoxW(None, f"以下进程仍存在, 无法继续:\n{still}", "仍在运行", 0x10)
                        sys.exit(1)
                    logging.warning("已结束其它实例, 继续启动")
                elif res == IDNO:
                    logging.warning("用户选择忽略互斥体并继续运行 (可能多开)")
                else:  # IDCANCEL or any other
                    sys.exit(0)
            except Exception:
                # 回退处理
                try:
                    messagebox.showerror("错误", "应用程序已在运行。")
                finally:
                    sys.exit(1)
        else:
            try:
                messagebox.showerror("错误", "应用程序已在运行。")
            finally:
                sys.exit(0)
    else:
        logging.warning("检测到残留互斥体但未发现其他实例，忽略并继续运行")

"""
执行系统命令，并在超时后终止命令。

参数:
- cmd: 要执行的命令（字符串或列表）
- timeout: 命令执行的超时时间（秒，默认为30秒）

返回值:
- 命令终止的返回码
"""


def execute_command(cmd: str, timeout: int = 30) -> int:
    """
    English: Executes a system command with an optional timeout, terminating the command if it exceeds the timeout
    中文: 使用可选超时时间执行系统命令，如果超时则终止命令
    """
    process = subprocess.Popen(cmd, shell=True)
    process.poll()
    if timeout:
        remaining = timeout
        while process.poll() is None and remaining > 0:
            logging.info(f"命令正在运行: {cmd}")
            time.sleep(1)
            remaining -= 1
        if remaining == 0 and process.poll() is None:
            logging.warning(f"命令超时，正在终止: {cmd}")
            process.kill()
    return process.wait()


"""
MQTT订阅成功时的回调函数。

参数:
- client: MQTT客户端实例
- userdata: 用户数据
- mid: 消息ID
- reason_code_list: 订阅结果的状态码列表
- properties: 属性
"""


def on_subscribe(client, userdata, mid, reason_code_list, properties=None):
    """
    English: Callback when MQTT subscription completes
    中文: MQTT成功订阅后回调函数
    """
    for sub_result in reason_code_list:
        if isinstance(sub_result, int) and sub_result >= 128:
            logging.error(f"订阅失败:{reason_code_list}")
        else:
            logging.info(f"使用代码发送订阅申请成功：{mid}")


"""
MQTT取消订阅时的回调函数。

参数:
- client: MQTT客户端实例
- userdata: 用户数据
- mid: 消息ID
- reason_code_list: 取消订阅结果的状态码列表
- properties: 属性
"""


def on_unsubscribe(client, userdata: list, mid: int, reason_code_list: list, properties) -> None:
    """
    English: Callback when MQTT unsubscription completes
    中文: MQTT取消订阅后回调函数
    """
    if len(reason_code_list) == 0 or not reason_code_list[0].is_failure:
        logging.info("退订成功")
    else:
        logging.error(f"{broker} 回复失败: {reason_code_list[0]}")
    client.disconnect()


"""
设置屏幕亮度。

参数:
- value: 亮度值（0-100）
"""


def set_brightness(value: int) -> None:
    """
    English: Sets the screen brightness to the specified value (0-100)
    中文: 设置屏幕亮度，取值范围为 0-100
    """
    try:
        logging.info(f"设置亮度: {value}")
        wmi.WMI(namespace="wmi").WmiMonitorBrightnessMethods()[0].WmiSetBrightness(
            value, 0
        )
    except Exception as e:
        logging.error(f"无法设置亮度: {e}")


"""
设置音量。

参数:
- value: 音量值（0-100）
"""


def set_volume(value: int) -> None:
    """
    English: Sets the system volume to the specified value (0-100)
    中文: 设置系统音量，取值范围为 0-100
    """
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))

    # 控制音量在 0.0 - 1.0 之间
    volume.SetMasterVolumeLevelScalar(value / 100, None)  # type: ignore


NOTIFY_ENABLED = True

def notify_in_thread(message: str) -> None:
    """
    English: Displays a Windows toast notification in a separate thread
    中文: 在单独线程中显示 Windows toast 通知
    """
    if not NOTIFY_ENABLED:
        logging.info(f"通知(已禁用): {message}")
        return
    logging.info(f"通知: {message}")
    def notify_message():
        notify(message)

    thread = threading.Thread(target=notify_message)
    thread.daemon = True
    thread.start()


def perform_computer_action(action: str, delay: int = 0) -> None:
    """
    根据配置执行计算机主题动作。

    参数:
    - action: 'lock'|'shutdown'|'restart'|'sleep'|'hibernate'|'logoff'|'none'
    - delay: 延时秒数，仅对shutdown/restart有效
    """
    try:
        act = (action or "").lower()
        if act == "none":
            logging.info("计算机主题设置为不执行动作")
            return
        if act == "lock":
            logging.info("执行锁屏操作")
            ctypes.windll.user32.LockWorkStation()
            return
        if act == "shutdown":
            d = max(0, int(delay or 0))
            logging.info(f"执行关机操作，延时: {d}s")
            execute_command(f"shutdown -s -t {d}")
            if d > 0:
                notify_in_thread(f"电脑将在{d}秒后关机")
            else:
                notify_in_thread("电脑即将关机")
            return
        if act == "restart":
            d = max(0, int(delay or 0))
            logging.info(f"执行重启操作，延时: {d}s")
            execute_command(f"shutdown -r -t {d}")
            if d > 0:
                notify_in_thread(f"电脑将在{d}秒后重启")
            else:
                notify_in_thread("电脑即将重启")
            return
        # if act == "sleep":
        #     logging.info("执行睡眠操作")
        #     execute_command("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        #     return
        # if act == "hibernate":
        #     logging.info("执行休眠操作")
        #     execute_command("shutdown /h")
        #     return
        if act == "logoff":
            logging.info("执行注销操作")
            execute_command("shutdown -l")
            return
        logging.warning(f"未知计算机动作: {action}")
    except Exception as e:
        logging.error(f"执行计算机动作失败: {e}")


def set_display_power(mode: str) -> None:
    """
    控制显示器电源状态：mode='off' 关闭显示器，mode='on' 打开显示器。
    """
    try:
        HWND_BROADCAST = 0xFFFF
        WM_SYSCOMMAND = 0x0112
        SC_MONITORPOWER = 0xF170
        if mode == 'off':
            ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2)
        else:
            ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, -1)
    except Exception as e:
        logging.error(f"设置显示器电源状态失败: {e}")


def perform_sleep_action(action: str) -> None:
    """
    执行睡眠主题动作：'sleep'|'hibernate'|'display_off'|'display_on'|'lock'|'none'
    """
    try:
        act = (action or '').lower()
        if act == 'none':
            logging.info("睡眠主题：不执行动作")
            return
        if act == 'sleep':
            logging.info("执行睡眠操作")
            execute_command("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            return
        if act == 'hibernate':
            logging.info("执行休眠操作")
            execute_command("shutdown /h")
            return
        if act == 'display_off':
            logging.info("关闭显示器")
            set_display_power('off')
            return
        if act == 'display_on':
            logging.info("打开显示器")
            set_display_power('on')
            return
        if act == 'lock':
            logging.info("锁屏")
            ctypes.windll.user32.LockWorkStation()
            return
        logging.warning(f"未知睡眠动作: {action}")
    except Exception as e:
        logging.error(f"执行睡眠动作失败: {e}")

def _parse_hotkey_string(hs: str) -> list[str]:
    """将 'ctrl+alt+delete' 这类组合拆成有序列表，并统一命名。"""
    if not hs:
        return []
    parts = [p.strip().lower() for p in hs.replace(" ", "").split("+") if p.strip()]
    normalize = {
        "control": "ctrl", "ctrl": "ctrl",
        "alt": "alt",
        "shift": "shift",
        "win": "win", "super": "win", "meta": "win",
        "enter": "enter", "return": "enter",
        "esc": "esc", "escape": "esc",
    }
    res = [normalize.get(p, p) for p in parts]
    order = {"ctrl": 0, "alt": 1, "shift": 2, "win": 3}
    res.sort(key=lambda x: (order.get(x, 9), x))
    return res

def perform_hotkey(action_type: str, action_value: str, char_delay_ms: int | None = None) -> None:
    """
    执行按键(Hotkey)动作：
    - keyboard: 组合键（依次按下修饰键 -> 主键 -> 释放修饰键）
    - none: 不执行
    """
    try:
        t = (action_type or "none").lower()
        v = (action_value or "").strip()
        if t == "none" or not v:
            logging.info("Hotkey: 不执行")
            return
        if t == "keyboard":
            delay_s = 0.0
            try:
                if char_delay_ms is not None and int(char_delay_ms) > 0:
                    delay_s = int(char_delay_ms) / 1000.0
            except Exception:
                delay_s = 0.0
            # 无连接符（+）时，将字符串按字符序列依次按下，例如 "f4" => 'f' 然后 '4'
            if "+" not in v:
                seq = [ch for ch in v if not ch.isspace()]
                if not seq:
                    logging.info("Hotkey: 空组合，忽略")
                    return
                # 与组合键路径保持一致的映射
                def map_key(k: str) -> str:
                    return "winleft" if k.lower() == "win" else k.lower()
                for i, ch in enumerate(seq):
                    if i > 0 and delay_s > 0:
                        time.sleep(delay_s)
                    pyautogui.press(map_key(ch))
                return

            # 有连接符：支持按键后缀 {down}/{up} 显式控制，字母段按字符序列依次输入
            raw_tokens = [t for t in v.replace(" ", "").split("+") if t]
            if not raw_tokens:
                logging.info("Hotkey: 空组合，忽略")
                return

            normalize = {
                "control": "ctrl", "ctrl": "ctrl",
                "alt": "alt",
                "shift": "shift",
                "win": "win", "super": "win", "meta": "win",
                "enter": "enter", "return": "enter",
                "esc": "esc", "escape": "esc",
            }
            mod_prio = {"ctrl": 0, "alt": 1, "shift": 2, "win": 3}

            def map_key(k: str) -> str:
                return "winleft" if k == "win" else k

            def split_suffix(tok: str) -> tuple[str, str]:
                t = tok.lower()
                for suf, act in (("{down}", "down"), ("{up}", "up"), ("_down", "down"), ("_up", "up")):
                    if t.endswith(suf):
                        return t[: -len(suf)], act
                return t, "press"

            parsed = []  # (key, action)
            for t in raw_tokens:
                base, act = split_suffix(t)
                base = normalize.get(base, base)
                parsed.append((base, act))

            # 先找出需要全程按住的修饰键（无显式 down/up）
            mods_held: list[str] = []
            seen = set()
            for k, act in parsed:
                if k in mod_prio and act == "press" and k not in seen:
                    seen.add(k)
                    mods_held.append(k)
            mods_held.sort(key=lambda m: mod_prio[m])

            # 按下这些修饰键
            to_release_end = list(mods_held)
            for m in mods_held:
                pyautogui.keyDown(map_key(m))

            # 顺序处理各 token；显式 down/up 立即生效；纯字母段展开为字符序列
            try:
                active_down: set[str] = set()  # 记录通过显式 down 按下的键
                for key, act in parsed:
                    if key in mod_prio:
                        if act == "press":
                            # 已由 mods_held 处理，跳过
                            continue
                        if act == "down":
                            if key not in mods_held and key not in active_down:
                                pyautogui.keyDown(map_key(key))
                                active_down.add(key)
                            continue
                        if act == "up":
                            # 若本来作为 held，则提前释放并从收尾释放列表移除
                            if key in to_release_end:
                                pyautogui.keyUp(map_key(key))
                                to_release_end.remove(key)
                            elif key in active_down:
                                pyautogui.keyUp(map_key(key))
                                active_down.discard(key)
                            continue
                    # 非修饰键
                    if act == "down":
                        pyautogui.keyDown(map_key(key))
                        continue
                    if act == "up":
                        pyautogui.keyUp(map_key(key))
                        continue
                    # 默认 press：纯字母段展开，否则按原样按压
                    if key.isalpha():
                        for i, ch in enumerate(key):
                            if i > 0 and delay_s > 0:
                                time.sleep(delay_s)
                            pyautogui.press(ch)
                    else:
                        pyautogui.press(map_key(key) if key == "win" else key)
            finally:
                # 释放仍按住的修饰键（倒序）
                for m in reversed(to_release_end):
                    pyautogui.keyUp(map_key(m))
            return
        logging.warning(f"Hotkey: 未知类型 {t}")
    except Exception as e:
        logging.error(f"执行 Hotkey 动作失败: {e}")


"""
根据接收到的命令和主题来处理相应的操作。

参数:
- command: 接收到的命令
- topic: 命令的主题
"""


def process_command(command: str, topic: str) -> None:
    """
    English: Handles the command received from MQTT messages based on the given topic
    中文: 根据主题处理从 MQTT 消息接收到的命令
    """
    logging.info(f"处理命令: {command} 主题: {topic}")

    # 先判断应用程序或服务类型主题
    for application, directory in applications:
        if topic == application:
            if command == "off":
                process_name = os.path.basename(directory)
                logging.info(f"尝试终止进程: {process_name}")
                notify_in_thread(f"尝试终止进程: {process_name}")
                
                # 检查是否是脚本文件
                if directory.lower().endswith(('.cmd', '.bat', '.ps1', '.py', '.pyw')):
                    # 对于不同类型的脚本使用不同的终止方法
                    if directory.lower().endswith(('.cmd', '.bat')):
                        # 批处理文件：先尝试增强版终止方法
                        if terminate_batch_process_enhanced(directory):
                            notify_in_thread(f"成功终止批处理脚本: {process_name}")
                        elif terminate_script_process(directory):
                            notify_in_thread(f"成功终止脚本: {process_name}")
                        else:
                            notify_in_thread(f"终止脚本失败: {process_name}")
                    elif directory.lower().endswith('.ps1'):
                        # PowerShell脚本：使用专门的PowerShell终止方法
                        if terminate_powershell_process_enhanced(directory):
                            notify_in_thread(f"成功终止PowerShell脚本: {process_name}")
                        elif terminate_script_process(directory):
                            notify_in_thread(f"成功终止脚本: {process_name}")
                        else:
                            notify_in_thread(f"终止PowerShell脚本失败: {process_name}")
                    else:
                        # Python脚本：使用标准方法
                        if terminate_script_process(directory):
                            notify_in_thread(f"成功终止Python脚本: {process_name}")
                        else:
                            notify_in_thread(f"终止Python脚本失败: {process_name}")
                else:
                    # 普通可执行文件
                    result = subprocess.run(
                        ["taskkill", "/F", "/IM", process_name],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        logging.info(f"成功终止进程: {result.stdout}")
                        notify_in_thread(f"成功终止进程: {process_name}")
                    else:
                        logging.error(f"终止进程失败: {result.stderr}")
                        notify_in_thread(f"终止进程失败: {process_name}")
            elif command == "on":
                if not directory or not os.path.isfile(directory):
                    logging.error(f"启动失败，文件不存在: {directory}")
                    notify_in_thread(f"启动失败，文件不存在: {directory}")
                    return
                
                logging.info(f"启动: {directory}")
                
                # 检查文件类型，选择合适的启动方式
                if directory.lower().endswith('.ps1'):
                    # PowerShell脚本需要通过PowerShell解释器启动（设置工作目录）
                    try:
                        abs_path = os.path.abspath(directory)
                        work_dir = os.path.dirname(abs_path)
                        subprocess.Popen(["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", abs_path], cwd=work_dir)
                        notify_in_thread(f"启动PowerShell脚本: {os.path.basename(directory)}")
                        logging.info(f"成功启动PowerShell脚本: {directory}")
                    except Exception as e:
                        logging.error(f"启动PowerShell脚本失败: {e}")
                        notify_in_thread(f"启动PowerShell脚本失败: {os.path.basename(directory)}")
                elif directory.lower().endswith(('.py', '.pyw')):
                    # Python脚本需要通过Python解释器启动（设置工作目录）
                    try:
                        abs_path = os.path.abspath(directory)
                        work_dir = os.path.dirname(abs_path)
                        subprocess.Popen(["python", abs_path], cwd=work_dir)
                        notify_in_thread(f"启动Python脚本: {os.path.basename(directory)}")
                        logging.info(f"成功启动Python脚本: {directory}")
                    except Exception as e:
                        logging.error(f"启动Python脚本失败: {e}")
                        notify_in_thread(f"启动Python脚本失败: {os.path.basename(directory)}")
                elif directory.lower().endswith(('.cmd', '.bat')):
                    # 批处理文件需要通过cmd启动（设置工作目录）
                    try:
                        abs_path = os.path.abspath(directory)
                        work_dir = os.path.dirname(abs_path)
                        # 使用cmd /c来启动批处理文件，确保路径正确处理
                        subprocess.Popen(["cmd", "/c", abs_path], shell=False, cwd=work_dir)
                        notify_in_thread(f"启动批处理脚本: {os.path.basename(directory)}")
                        logging.info(f"成功启动批处理脚本: {directory}")
                    except Exception as e:
                        logging.error(f"启动批处理脚本失败: {e}")
                        notify_in_thread(f"启动批处理脚本失败: {os.path.basename(directory)}")
                else:
                    # 其他可执行文件（使用ShellExecuteW模拟双击，必要时兜底）
                    try:
                        abs_path = os.path.abspath(directory)
                        work_dir = os.path.dirname(abs_path)
                        # 优先使用ShellExecuteW，lpDirectory指定工作目录
                        try:
                            hinst = ctypes.windll.shell32.ShellExecuteW(None, 'open', abs_path, None, work_dir, 1)
                        except Exception:
                            hinst = 0
                        # 统一成整数进行判断
                        if not isinstance(hinst, int) and hasattr(hinst, 'value'):
                            hinst = int(hinst.value)
                        if hinst is None:
                            hinst = 0
                        if hinst <= 32:
                            # 回退到Popen，并指定工作目录
                            subprocess.Popen([abs_path], cwd=work_dir)
                        notify_in_thread(f"启动程序: {os.path.basename(directory)}")
                        logging.info(f"成功启动程序: {directory}")
                    except Exception as e:
                        logging.error(f"启动程序失败: {e}")
                        notify_in_thread(f"启动程序失败: {os.path.basename(directory)}")
            return
    
    # 命令类型（统一通过 PowerShell 执行）
    for cmd_topic, cmd_text in commands:
        if topic == cmd_topic:
            if not cmd_text:
                logging.error(f"命令为空，无法执行: {cmd_topic}")
                notify_in_thread(f"命令为空: {cmd_topic}")
                return
            if command == "on":
                try:
                    # 始终使用 PowerShell 执行命令
                    creationflags = 0x00000200  # CREATE_NEW_PROCESS_GROUP（用于后续CTRL_BREAK）

                    # 读取该命令的窗口显示设置（默认为show）
                    window_mode = None
                    try:
                        for i in range(1, 50):
                            key = f"command{i}"
                            if config.get(key) == cmd_topic:
                                window_mode = config.get(f"{key}_window", "show")
                                break
                    except Exception:
                        window_mode = "show"
                    if window_mode is None:
                        window_mode = "show"

                    startupinfo = None
                    args = [
                        "powershell.exe",
                        "-NoProfile",
                        "-ExecutionPolicy", "Bypass",
                    ]

                    if window_mode == "hide":
                        # 隐藏窗口：创建新控制台并将其隐藏，保留控制台以支持CTRL_BREAK
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        startupinfo.wShowWindow = 0  # SW_HIDE
                        creationflags |= 0x00000010  # CREATE_NEW_CONSOLE
                        args += [
                            "-WindowStyle", "Hidden",
                            "-NonInteractive",
                            "-Command", cmd_text,
                        ]
                    else:
                        # 显示窗口：创建新控制台并保持窗口
                        creationflags |= 0x00000010  # CREATE_NEW_CONSOLE
                        args += [
                            "-NoExit",
                            "-Command", cmd_text,
                        ]

                    proc = subprocess.Popen(
                        args,
                        shell=False,
                        creationflags=creationflags,
                        startupinfo=startupinfo,
                    )
                    register_command_process(cmd_topic, proc.pid)
                    notify_in_thread(f"已执行命令: {cmd_topic}")
                    logging.info(f"执行命令[{cmd_topic}] (window={window_mode}): {cmd_text}; PID={proc.pid}")
                except Exception as e:
                    logging.error(f"执行命令失败[{cmd_topic}]: {e}")
                    notify_in_thread(f"执行命令失败: {cmd_topic}")
            elif command == "off":
                if interrupt_command_processes(cmd_topic):
                    notify_in_thread(f"已发送中断信号: {cmd_topic}")
                else:
                    notify_in_thread(f"未找到可中断进程或中断失败: {cmd_topic}")
            return
            
    def check_service_status(service_name):
        result = subprocess.run(["sc", "query", service_name], capture_output=True, text=True)
        if "RUNNING" in result.stdout:
            logging.info(f"服务 {service_name} 正在运行")
            return "running"
        elif "STOPPED" in result.stdout:
            logging.info(f"服务 {service_name} 已停止")
            return "stopped"
        else:
            logging.error(f"无法获取服务{service_name}的状态:{result.stderr}")
            return "unknown"
    
    for serve, serve_name in serves:
        if topic == serve:
            if command == "off":
                status = check_service_status(serve_name)
                if status == "unknown":
                    logging.error(f"无法获取服务{serve_name}的状态")
                    notify_in_thread(f"无法获取 {serve_name} 的状态,详情请查看日志")
                if status == "stopped":
                    logging.info(f"{serve_name} 还没有运行")
                    notify_in_thread(f"{serve_name} 还没有运行")
                else:
                    result = subprocess.run(["sc", "stop", serve_name], shell=True)
                    if result.returncode == 0:
                        logging.info(f"成功关闭 {serve_name}")
                        notify_in_thread(f"成功关闭 {serve_name}")
                    else:
                        logging.error(f"关闭 {serve_name} 失败")
                        logging.error(result.stderr)
                        notify_in_thread(f"关闭 {serve_name} 失败")
            elif command == "on":
                status = check_service_status(serve_name)
                if status == "unknown":
                    logging.error(f"无法获取服务{serve_name}的状态")
                    notify_in_thread(f"无法获取 {serve_name} 的状态,详情请查看日志")
                if status == "running":
                    logging.info(f"{serve_name} 已经在运行")
                    notify_in_thread(f"{serve_name} 已经在运行")
                else:
                    result = subprocess.run(["sc", "start", serve_name], shell=True)
                    if result.returncode == 0:
                        logging.info(f"成功启动 {serve_name}")
                        notify_in_thread(f"成功启动 {serve_name}")
                    else:
                        logging.error(f"启动 {serve_name} 失败")
                        logging.error(result.stderr)
                        notify_in_thread(f"启动 {serve_name} 失败")
            return

    # 若不匹配应用程序或服务，再判断是否为内置主题
    if topic == Computer:
        # 电脑主题：根据配置执行
        on_action = config.get("computer_on_action", "lock")
        off_action = config.get("computer_off_action", "none")
        on_delay = 0
        off_delay = 60
        try:
            on_delay = int(config.get("computer_on_delay", 0) or 0)
        except Exception:
            on_delay = 0
        try:
            off_delay = int(config.get("computer_off_delay", 60) or 60)
        except Exception:
            off_delay = 60

        if command == "on":
            perform_computer_action(on_action, on_delay)
        elif command == "off":
            perform_computer_action(off_action, off_delay)
    elif topic == screen:
        # 屏幕亮度控制
        if command == "off":
            logging.info("执行亮度最小化操作")
            set_brightness(0)
        elif command == "on":
            logging.info("执行亮度最大化操作")
            set_brightness(100)
        elif command.startswith("on#"):
            try:
                # 解析百分比值
                brightness = int(command.split("#")[1])
                logging.info(f"设置亮度: {brightness}")
                set_brightness(brightness)
            except ValueError:
                logging.error("亮度值无效")
                notify_in_thread("亮度值无效")
            except Exception as e:
                logging.error(f"设置亮度时出错: {e}")
                notify_in_thread(f"设置亮度时发生未知错误，请查看日志")
        else:
            logging.error(f"未知的亮度控制命令: {command}")
            notify_in_thread(f"未知的亮度控制命令: {command}")
    elif topic == volume:
        # 音量控制
        if command == "off":
            logging.info("执行音量最小化操作")
            set_volume(0)
        elif command == "on":
            logging.info("执行音量最大化操作")
            set_volume(100)
        elif command == "pause":
            # 播放/暂停
            logging.info("执行静音操作")
            set_volume(0)
        elif command.startswith("on#"):
            try:
                # 解析百分比值
                volume_value = int(command.split("#")[1])
                logging.info(f"设置音量: {volume_value}")
                set_volume(volume_value)
            except ValueError:
                logging.error("音量值无效")
                notify_in_thread("音量值无效")
            except Exception as e:
                logging.error(f"设置音量时出错: {e}")
                notify_in_thread(f"设置音量时发生未知错误，请查看日志")
        else:
            logging.error(f"未知的音量控制命令: {command}")
            notify_in_thread(f"未知的音量控制命令: {command}")
    elif topic == sleep:
        # 睡眠主题：根据配置执行，可配置延时
        on_action = config.get("sleep_on_action", "sleep")
        off_action = config.get("sleep_off_action", "none")
        try:
            on_delay = int(config.get("sleep_on_delay", 0) or 0)
        except Exception:
            on_delay = 0
        try:
            off_delay = int(config.get("sleep_off_delay", 0) or 0)
        except Exception:
            off_delay = 0

        if command == "on":
            if on_delay > 0:
                notify_in_thread(f"将在{on_delay}秒后执行睡眠动作")
                logging.info(f"{on_delay}s 后执行睡眠动作: {on_action}")
                threading.Timer(on_delay, lambda: perform_sleep_action(on_action)).start()
            else:
                perform_sleep_action(on_action)
        elif command == "off":
            if off_delay > 0:
                notify_in_thread(f"将在{off_delay}秒后执行睡眠关闭动作")
                logging.info(f"{off_delay}s 后执行睡眠关闭动作: {off_action}")
                threading.Timer(off_delay, lambda: perform_sleep_action(off_action)).start()
            else:
                perform_sleep_action(off_action)
    elif topic == media:
        # 媒体控制（作为窗帘设备）
        try:
            if command == "off":
                # 下一曲
                logging.info("执行下一曲操作")
                pyautogui_press('nexttrack')
            elif command == "on":
                # 上一曲
                logging.info("执行上一曲操作")
                pyautogui_press('prevtrack')
            elif command == "pause":
                # 播放/暂停
                logging.info("执行播放/暂停操作")
                pyautogui_press('playpause')
            elif command.startswith("on#"):
                    # 解析百分比值
                    value = int(command.split("#")[1])
                    if value <= 33:
                        # 1-33：下一曲
                        logging.info(f"执行下一曲操作（百分比:{value}）")
                        pyautogui_press('nexttrack')
                    elif value <= 66:
                        # 34-66：播放/暂停
                        logging.info(f"执行播放/暂停操作（百分比:{value}）")
                        pyautogui_press('playpause')
                    else:
                        # 67-100：上一曲
                        logging.info(f"执行上一曲操作（百分比:{value}）")
                        pyautogui_press('prevtrack')
            else:
                logging.error(f"未知的媒体控制命令: {command}")
                notify_in_thread(f"未知的媒体控制命令: {command}")
        except Exception as e:
            logging.error(f"媒体控制执行失败: {e}")
            notify_in_thread(f"媒体控制执行失败，详情请查看日志")
    # 自定义 Hotkey 主题
    else:
        for hk_topic, hk_conf in hotkeys:
            if topic == hk_topic:
                on_type = (hk_conf.get("on_type") or "keyboard").lower()
                on_value = (hk_conf.get("on_value") or "")
                off_type = (hk_conf.get("off_type") or "none").lower()
                off_value = (hk_conf.get("off_value") or "")
                char_delay_ms = None
                try:
                    _d = hk_conf.get("char_delay_ms")
                    if _d is not None:
                        char_delay_ms = int(_d)
                except Exception:
                    char_delay_ms = None
                if command == "on":
                    perform_hotkey(on_type, on_value, char_delay_ms)
                elif command == "off":
                    perform_hotkey(off_type, off_value, char_delay_ms)
                return
        # 未知主题
        logging.error(f"未知主题: {topic}")
        notify_in_thread(f"未知主题: {topic}")
        

# 命令类型进程注册与中断支持
command_process_registry: dict[str, list[int]] = {}

def register_command_process(topic: str, pid: int) -> None:
    lst = command_process_registry.setdefault(topic, [])
    lst.append(pid)

def _send_ctrl_break_via_console(pid: int) -> bool:
    """
    尝试通过附加到目标控制台并发送 CTRL_BREAK 实现中断。
    要求目标进程以 CREATE_NEW_PROCESS_GROUP 启动，且具备控制台（我们使用 CREATE_NEW_CONSOLE）。
    返回是否成功触发事件。
    """
    try:
        kernel32 = ctypes.windll.kernel32
        # 确保当前进程没有附着其他控制台
        try:
            kernel32.FreeConsole()
        except Exception:
            pass

        if kernel32.AttachConsole(ctypes.c_uint(pid)) == 0:
            err = ctypes.GetLastError()
            logging.warning(f"AttachConsole 失败 PID={pid}, 错误码={err}")
            return False

        try:
            # 忽略本进程的控制台信号，避免自身受影响
            kernel32.SetConsoleCtrlHandler(None, True)
        except Exception:
            pass

        CTRL_BREAK_EVENT = 1
        if kernel32.GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, ctypes.c_uint(pid)) == 0:
            err = ctypes.GetLastError()
            logging.warning(f"GenerateConsoleCtrlEvent 失败 PID={pid}, 错误码={err}")
            try:
                kernel32.FreeConsole()
            except Exception:
                pass
            return False

        # 给子进程一点时间处理中断
        time.sleep(0.5)

        try:
            kernel32.FreeConsole()
        except Exception:
            pass
        return True
    except Exception as e:
        logging.error(f"通过控制台发送CTRL_BREAK失败 PID={pid}: {e}")
        return False

def cleanup_dead_pids(pid_list: list[int]) -> list[int]:
    alive = []
    for pid in pid_list:
        try:
            if psutil.pid_exists(pid):
                p = psutil.Process(pid)
                if p.is_running():
                    alive.append(pid)
        except Exception:
            continue
    return alive

def interrupt_command_processes(topic: str) -> bool:
    """
    尝试对该命令下由本程序启动的进程发送中断信号(CTRL_BREAK)。
    若失败，则尝试优雅结束；最后回退 taskkill。
    返回是否至少对一个进程采取了动作。
    """
    pids = command_process_registry.get(topic, [])
    if not pids:
        logging.warning(f"命令[{topic}]未记录到任何PID")
        return False

    # 清理已退出的PID
    pids = cleanup_dead_pids(pids)
    if not pids:
        command_process_registry[topic] = []
        logging.info(f"命令[{topic}]持有PID均已退出")
        return False

    did_any = False
    # 只针对“最新的存活 PID”发送中断，避免影响旧窗口
    target_pid = None
    if pids:
        alive_pids = cleanup_dead_pids(pids)
        if alive_pids:
            target_pid = alive_pids[-1]
            command_process_registry[topic] = alive_pids

    if target_pid is None:
        logging.warning(f"命令[{topic}]没有可中断的存活PID")
        return False

    try:
        pid = target_pid
        # 首选：通过附加控制台并发送 CTRL_BREAK（更可靠）
        if _send_ctrl_break_via_console(pid):
            did_any = True
            logging.info(f"已发送CTRL_BREAK给PID={pid}")
        else:
            # 次选：os.kill（在某些场景下仍可能有效）
            try:
                os.kill(pid, signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                did_any = True
                logging.info(f"通过os.kill发送CTRL_BREAK给PID={pid}")
            except Exception as e:
                logging.warning(f"os.kill CTRL_BREAK 失败 PID={pid}: {e}")
                # 次选优雅终止
                try:
                    proc = psutil.Process(pid)
                    proc.terminate()
                    did_any = True
                    logging.info(f"已尝试优雅终止 PID={pid}")
                except Exception as e2:
                    logging.warning(f"优雅终止失败 PID={pid}: {e2}")
                    # 兜底 taskkill
                    result = subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True, text=True)
                    if result.returncode == 0:
                        did_any = True
                        logging.info(f"taskkill 返回成功 PID={pid}: {result.stdout}")
                    else:
                        logging.warning(f"taskkill 失败 PID={pid}: {result.stderr}")
    except Exception as e:
        logging.error(f"中断命令进程失败 PID={target_pid}: {e}")

    # 清理注册表中已退出或被终止的PID
    command_process_registry[topic] = cleanup_dead_pids(pids)
    return did_any

def terminate_script_process(script_path: str) -> bool:
    """
    终止脚本相关的进程
    
    参数:
    - script_path: 脚本文件路径
    
    返回:
    - bool: 是否成功终止进程
    """
    script_name = os.path.basename(script_path)
    script_full_path = os.path.abspath(script_path)
    logging.info(f"尝试终止脚本进程: {script_name}")
    logging.info(f"脚本完整路径: {script_full_path}")
    
    terminated_count = 0
    process_pids = []
    
    try:
        # 方法1: 精确匹配通过相应解释器启动的脚本进程
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info['cmdline']
                if not cmdline:
                    continue
                
                proc_name = proc.info['name'].lower()
                cmdline_str = ' '.join(cmdline).lower()
                script_name_lower = script_name.lower()
                script_path_lower = script_full_path.lower()
                
                # 判断是否是脚本相关的进程
                is_script_process = False
                
                if script_name.lower().endswith('.ps1'):
                    # PowerShell脚本：查找powershell.exe进程
                    if proc_name in ['powershell.exe', 'pwsh.exe']:
                        # 检查命令行是否包含脚本文件
                        if (script_path_lower in cmdline_str or 
                            script_name_lower in cmdline_str):
                            # 进一步验证是否是执行脚本
                            if any(script_name_lower in arg.lower() for arg in cmdline):
                                is_script_process = True
                                
                elif script_name.lower().endswith(('.py', '.pyw')):
                    # Python脚本：查找python.exe进程
                    if proc_name in ['python.exe', 'pythonw.exe']:
                        # 检查命令行是否包含脚本文件
                        if (script_path_lower in cmdline_str or 
                            script_name_lower in cmdline_str):
                            # 进一步验证是否是执行脚本
                            if any(script_name_lower in arg.lower() for arg in cmdline):
                                is_script_process = True
                                
                elif script_name.lower().endswith(('.cmd', '.bat')):
                    # 批处理脚本：查找cmd.exe进程
                    if proc_name == 'cmd.exe':
                        # 检查是否是通过/c或/k参数启动的脚本
                        if '/c' in cmdline_str or '/k' in cmdline_str:
                            if (script_path_lower in cmdline_str or 
                                script_name_lower in cmdline_str):
                                # 进一步验证是否是脚本执行
                                if any(script_name_lower in arg.lower() and 
                                      (arg.lower().endswith('.bat') or arg.lower().endswith('.cmd'))
                                      for arg in cmdline):
                                    is_script_process = True
                
                if is_script_process:
                    logging.info(f"找到脚本进程: PID={proc.info['pid']}, 命令行={cmdline}")
                    process_pids.append(proc.info['pid'])
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        # 先尝试优雅终止
        for pid in process_pids:
            try:
                proc = psutil.Process(pid)
                # 获取子进程
                children = proc.children(recursive=True)
                
                # 先终止子进程
                for child in children:
                    try:
                        logging.info(f"终止子进程: PID={child.pid}")
                        child.terminate()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                
                # 再终止主进程
                proc.terminate()
                terminated_count += 1
                logging.info(f"已终止进程: PID={pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # 等待进程终止
        if terminated_count > 0:
            time.sleep(3)
            
        # 检查进程是否真的被终止，如果没有则强制终止
        still_running = []
        for pid in process_pids:
            try:
                proc = psutil.Process(pid)
                if proc.is_running():
                    still_running.append(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # 强制终止仍在运行的进程
        for pid in still_running:
            try:
                proc = psutil.Process(pid)
                # 强制终止子进程
                children = proc.children(recursive=True)
                for child in children:
                    try:
                        logging.info(f"强制终止子进程: PID={child.pid}")
                        child.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                
                # 强制终止主进程
                proc.kill()
                logging.info(f"强制终止进程: PID={pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # 方法2: 如果没有找到相关进程，使用精确的taskkill命令
        if terminated_count == 0:
            logging.info("尝试使用taskkill命令终止相关进程")
            # 使用更精确的taskkill命令，避免误杀用户进程
            result = subprocess.run(
                ["taskkill", "/F", "/FI", f"IMAGENAME eq cmd.exe", "/FI", f"COMMANDLINE eq *{script_name}*"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and "SUCCESS" in result.stdout:
                logging.info(f"taskkill成功终止相关进程: {result.stdout}")
                terminated_count += 1
            else:
                logging.info(f"taskkill未找到匹配的进程: {result.stderr}")
        
        return terminated_count > 0
        
    except Exception as e:
        logging.error(f"终止脚本进程时出错: {e}")
        return False

def terminate_batch_process_enhanced(script_path: str) -> bool:
    """
    增强版批处理文件终止功能
    
    参数:
    - script_path: 脚本文件路径
    
    返回:
    - bool: 是否成功终止进程
    """
    script_name = os.path.basename(script_path)
    script_full_path = os.path.abspath(script_path)
    logging.info(f"使用增强版方法终止批处理进程: {script_name}")
    logging.info(f"脚本完整路径: {script_full_path}")
    
    terminated_count = 0
    
    try:
        # 方法1: 使用wmic精确查找并终止进程
        try:
            # 使用完整路径进行精确匹配
            cmd = f'wmic process where "name=\'cmd.exe\' AND (CommandLine LIKE \'%{script_full_path}%\' OR CommandLine LIKE \'%{script_name}%\')" get ProcessId,CommandLine /format:value'
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            
            pids = []
            current_pid = None
            current_cmdline = None
            
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if line.startswith("CommandLine="):
                    current_cmdline = line[12:]
                elif line.startswith("ProcessId="):
                    pid_str = line.split("=")[1].strip()
                    if pid_str.isdigit():
                        current_pid = int(pid_str)
                    
                    # 当获取到完整信息时进行验证
                    if current_pid and current_cmdline:
                        # 进一步验证：确保是通过/c或/k执行的脚本
                        if (('/c' in current_cmdline.lower() or '/k' in current_cmdline.lower()) and
                            (script_name.lower() in current_cmdline.lower() or 
                             script_full_path.lower() in current_cmdline.lower())):
                            pids.append(current_pid)
                            logging.info(f"找到匹配的进程: PID={current_pid}, 命令行={current_cmdline}")
                        
                        # 重置
                        current_pid = None
                        current_cmdline = None
            
            # 终止找到的进程
            for pid in pids:
                try:
                    # 使用taskkill /T 终止进程树
                    result = subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        logging.info(f"成功终止进程树 PID={pid}")
                        terminated_count += 1
                    else:
                        logging.warning(f"终止进程树 PID={pid} 失败: {result.stderr}")
                except Exception as e:
                    logging.error(f"终止进程树 PID={pid} 时出错: {e}")
                    
        except Exception as e:
            logging.error(f"使用wmic查找进程失败: {e}")
        
        # 方法2: 使用psutil进行精确查找
        if terminated_count == 0:
            logging.info("尝试使用psutil进行精确查找")
            try:
                cmd_processes = []
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        if proc.info['name'].lower() == 'cmd.exe':
                            cmdline = proc.info['cmdline']
                            if cmdline:
                                cmdline_str = ' '.join(cmdline).lower()
                                # 精确匹配：必须包含/c或/k参数，且包含脚本名
                                if (('/c' in cmdline_str or '/k' in cmdline_str) and
                                    (script_name.lower() in cmdline_str or 
                                     script_full_path.lower() in cmdline_str)):
                                    # 进一步验证脚本文件扩展名
                                    if any(arg.lower().endswith(('.bat', '.cmd')) for arg in cmdline):
                                        cmd_processes.append(proc.info['pid'])
                                        logging.info(f"psutil找到匹配进程: PID={proc.info['pid']}, 命令行={cmdline}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
                
                # 终止找到的进程及其子进程
                for pid in cmd_processes:
                    try:
                        # 使用taskkill /T 终止进程树
                        result = subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(pid)],
                            capture_output=True,
                            text=True,
                        )
                        if result.returncode == 0:
                            logging.info(f"成功终止进程树 PID={pid}")
                            terminated_count += 1
                        else:
                            logging.warning(f"终止进程树 PID={pid} 失败: {result.stderr}")
                    except Exception as e:
                        logging.error(f"终止进程树 PID={pid} 时出错: {e}")
                        
            except Exception as e:
                logging.error(f"psutil查找方法失败: {e}")
        
        # 方法3: 使用taskkill的精确过滤（不再使用兜底方案）
        if terminated_count == 0:
            logging.info("尝试使用taskkill精确过滤")
            try:
                # 使用多个过滤条件确保精确匹配
                result = subprocess.run(
                    ["taskkill", "/F", "/FI", f"IMAGENAME eq cmd.exe", 
                     "/FI", f"COMMANDLINE eq *{script_name}*"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0 and "SUCCESS" in result.stdout:
                    logging.info(f"taskkill成功终止相关进程: {result.stdout}")
                    terminated_count += 1
                else:
                    logging.info(f"taskkill未找到匹配的进程")
            except Exception as e:
                logging.error(f"taskkill方法失败: {e}")
        
        if terminated_count == 0:
            logging.warning(f"未找到与脚本 {script_name} 相关的进程")
        
        return terminated_count > 0
        
    except Exception as e:
        logging.error(f"增强版批处理终止功能出错: {e}")
        return False

def terminate_powershell_process_enhanced(script_path: str) -> bool:
    """
    增强版PowerShell脚本终止功能
    
    参数:
    - script_path: PowerShell脚本文件路径
    
    返回:
    - bool: 是否成功终止进程
    """
    script_name = os.path.basename(script_path)
    script_full_path = os.path.abspath(script_path)
    logging.info(f"使用增强版方法终止PowerShell进程: {script_name}")
    logging.info(f"脚本完整路径: {script_full_path}")
    
    terminated_count = 0
    
    try:
        # 方法1: 使用wmic精确查找PowerShell进程
        try:
            cmd = f'wmic process where "name=\'powershell.exe\' OR name=\'pwsh.exe\'" get ProcessId,CommandLine /format:value'
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            
            pids = []
            current_pid = None
            current_cmdline = None
            
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if line.startswith("CommandLine="):
                    current_cmdline = line[12:]
                elif line.startswith("ProcessId="):
                    pid_str = line.split("=")[1].strip()
                    if pid_str.isdigit():
                        current_pid = int(pid_str)
                    
                    # 当获取到完整信息时进行验证
                    if current_pid and current_cmdline:
                        # 检查是否包含脚本名称
                        if (script_name.lower() in current_cmdline.lower() or 
                            script_full_path.lower() in current_cmdline.lower()):
                            pids.append(current_pid)
                            logging.info(f"找到匹配的PowerShell进程: PID={current_pid}, 命令行={current_cmdline}")
                        
                        # 重置
                        current_pid = None
                        current_cmdline = None
            
            # 终止找到的进程
            for pid in pids:
                try:
                    # 使用taskkill /T 终止进程树
                    result = subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        logging.info(f"成功终止PowerShell进程树 PID={pid}")
                        terminated_count += 1
                    else:
                        logging.warning(f"终止PowerShell进程树 PID={pid} 失败: {result.stderr}")
                except Exception as e:
                    logging.error(f"终止PowerShell进程树 PID={pid} 时出错: {e}")
                    
        except Exception as e:
            logging.error(f"使用wmic查找PowerShell进程失败: {e}")
        
        # 方法2: 使用psutil进行精确查找
        if terminated_count == 0:
            logging.info("尝试使用psutil查找PowerShell进程")
            try:
                ps_processes = []
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        proc_name = proc.info['name'].lower()
                        if proc_name in ['powershell.exe', 'pwsh.exe']:
                            cmdline = proc.info['cmdline']
                            if cmdline:
                                cmdline_str = ' '.join(cmdline).lower()
                                # 检查是否包含脚本名称
                                if (script_name.lower() in cmdline_str or 
                                    script_full_path.lower() in cmdline_str):
                                    # 进一步验证是否是脚本执行
                                    if any(script_name.lower() in arg.lower() for arg in cmdline):
                                        ps_processes.append(proc.info['pid'])
                                        logging.info(f"psutil找到匹配的PowerShell进程: PID={proc.info['pid']}, 命令行={cmdline}")
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
                
                # 终止找到的进程及其子进程
                for pid in ps_processes:
                    try:
                        # 使用taskkill /T 终止进程树
                        result = subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(pid)],
                            capture_output=True,
                            text=True,
                        )
                        if result.returncode == 0:
                            logging.info(f"成功终止PowerShell进程树 PID={pid}")
                            terminated_count += 1
                        else:
                            logging.warning(f"终止PowerShell进程树 PID={pid} 失败: {result.stderr}")
                    except Exception as e:
                        logging.error(f"终止PowerShell进程树 PID={pid} 时出错: {e}")
                        
            except Exception as e:
                logging.error(f"psutil查找PowerShell进程失败: {e}")
        
        # 方法3: 使用taskkill精确过滤
        if terminated_count == 0:
            logging.info("尝试使用taskkill精确过滤PowerShell进程")
            try:
                # 首先尝试powershell.exe
                result = subprocess.run(
                    ["taskkill", "/F", "/FI", f"IMAGENAME eq powershell.exe", 
                     "/FI", f"COMMANDLINE eq *{script_name}*"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0 and "SUCCESS" in result.stdout:
                    logging.info(f"taskkill成功终止PowerShell进程: {result.stdout}")
                    terminated_count += 1
                else:
                    # 尝试pwsh.exe（PowerShell Core）
                    result = subprocess.run(
                        ["taskkill", "/F", "/FI", f"IMAGENAME eq pwsh.exe", 
                         "/FI", f"COMMANDLINE eq *{script_name}*"],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0 and "SUCCESS" in result.stdout:
                        logging.info(f"taskkill成功终止PowerShell Core进程: {result.stdout}")
                        terminated_count += 1
                    else:
                        logging.info(f"taskkill未找到匹配的PowerShell进程")
            except Exception as e:
                logging.error(f"taskkill方法失败: {e}")
        
        if terminated_count == 0:
            logging.warning(f"未找到与PowerShell脚本 {script_name} 相关的进程")
        
        return terminated_count > 0
        
    except Exception as e:
        logging.error(f"增强版PowerShell终止功能出错: {e}")
        return False

"""
MQTT接收到消息时的回调函数。

参数:
- client: MQTT客户端实例
- userdata: 用户数据
- message: 接收到的消息
"""


def on_message(client, userdata: list, message) -> None:
    """
    English: Callback when an MQTT message is received
    中文: MQTT接收到消息时的回调函数
    """
    userdata.append(message.payload)
    command = message.payload.decode()
    logging.info(f"'{message.topic}' 主题收到 '{command}'")
    process_command(command, message.topic)


"""
MQTT连接时的回调函数。

参数:
- client: MQTT客户端实例
- userdata: 用户数据
- flags: 连接标志
- reason_code: 连接结果的状态码
- properties: 属性
"""


def on_connect(client, userdata: list, flags: dict, reason_code, properties=None) -> None:
    # 兼容 int 和 ReasonCode 类型
    try:
        is_fail = reason_code.is_failure
        reason_str = str(reason_code)
    except AttributeError:
        is_fail = reason_code != 0
        reason_str = str(reason_code)

    if is_fail:
        # 检查是否是认证失败（错误代码5表示Not authorized）
        if "Not authorized" in reason_str or reason_code == 5:
            error_msg = f"MQTT认证失败: {reason_str}\n\n可能的原因：\n• 账号密码模式：用户名或密码错误\n• 私钥模式：客户端ID（私钥）错误\n• 服务器配置问题\n\n程序将停止重试，请检查配置后重新启动。"
            logging.error(f"MQTT认证失败: {reason_str}，停止重试")
            notify_in_thread("MQTT认证失败，程序即将退出")
            
            # 认证失败时停止重试并退出程序
            try:
                messagebox.showerror("MQTT认证失败", error_msg)
                open_gui()
                client.loop_stop()
                client.disconnect()
            except Exception as e:
                logging.error(f"处理认证失败时出错: {e}")
            finally:
                logging.info("因认证失败退出程序")
                threading.Timer(0.5, lambda: os._exit(0)).start()
                sys.exit(0)
        else:
            notify_in_thread(f"连接MQTT失败: {reason_str}. 重新连接中...")
            logging.error(f"连接失败: {reason_str}. loop_forever() 将重试连接")
    else:
        notify_in_thread(f"MQTT成功连接至{broker}")
        logging.info(f"连接到 {broker}")
        for key, value in config.items():
            if key.endswith("_checked") and value == 1:
                topic_key = key.replace("_checked", "")
                topic = config.get(topic_key)
                if topic:
                    client.subscribe(topic)
                    logging.info(f'订阅主题: "{topic}"')

def get_main_proc(process_name):
    """查找程序进程是否存在"""
    logging.info(f"执行函数: get_main_proc; 参数: {process_name}")
    
    # 如果不是管理员权限运行，可能无法查看所有进程，记录警告
    global IS_ADMIN
    if not IS_ADMIN:
        logging.warning("程序未以管理员权限运行,可能无法查看所有进程")
    if process_name.endswith('.exe'):
        logging.info(f"查找程序可执行文件: {process_name}")
        # 可执行文件查找方式
        target_user=None
        process_name = process_name.lower()
        target_user = target_user.lower() if target_user else None

        for proc in psutil.process_iter(['name', 'username']):
            try:
                # 获取进程信息
                proc_info = proc.info
                current_name = proc_info['name'].lower()
                current_user = proc_info['username']

                # 匹配进程名
                if current_name == process_name:
                    # 未指定用户则直接返回True
                    if target_user is None:
                        logging.info(f"找到程序进程: {proc.pid}, 用户: {current_user}")
                        return True
                    # 指定用户时提取用户名部分比较
                    if current_user:
                        user_part = current_user.split('\\')[-1].lower()
                        if user_part == target_user:
                            logging.info(f"找到程序进程: {proc.pid}, 用户: {current_user}")
                            return True
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                logging.error(f"获取进程信息失败: {proc.pid}")
                continue
        # 如果找不到进程，记录信息
        logging.info(f"未找到程序进程: {process_name}")
        return None
    else:
        # Python脚本查找方式
        logging.info(f"查找Python脚本主程序: {process_name}")
        # 尝试查找命令行中包含脚本名的Python进程
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'username']):
            try:
                proc_info = proc.info
                if proc_info['name'] and proc_info['name'].lower() in ('python.exe', 'pythonw.exe'):
                    cmdline = ' '.join(proc_info['cmdline']) if proc_info['cmdline'] else ""
                    if process_name in cmdline:
                        logging.info(f"找到程序Python进程: {proc.pid}, 命令行: {cmdline}")
                        return proc
            except (psutil.AccessDenied, psutil.NoSuchProcess, Exception) as e:
                logging.error(f"获取Python进程信息失败: {e}")
                continue
        
        # 如果常规方法找不到，尝试使用wmic命令行工具
        logging.info("常规方法未找到Python进程，尝试使用wmic命令行工具")
        try:
            cmd = 'wmic process where "name=\'python.exe\' or name=\'pythonw.exe\'" get ProcessId,CommandLine /value'
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            lines = result.stdout.strip().split('\n')
            
            current_pid = None
            current_cmd = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                if line.startswith("CommandLine="):
                    current_cmd = line[12:]
                elif line.startswith("ProcessId="):
                    current_pid = line[10:]
                    
                    if current_cmd and current_pid and process_name in current_cmd:
                        try:
                            logging.info(f"wmic找到程序Python进程: {current_pid}, 命令行: {current_cmd}")
                            return psutil.Process(int(current_pid))
                        except (psutil.NoSuchProcess, ValueError) as e:
                            logging.error(f"获取进程对象失败，PID: {current_pid}, 错误: {e}")
                    
                    current_pid = None
                    current_cmd = None
        except Exception as e:
            logging.error(f"使用wmic查找Python进程失败: {e}")
    
    logging.info("未找到程序进程")
    return None



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
    logging.info(f"执行函数: run_as_admin；参数: {executable_path}")
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
    """使用指定 Python 解释器提权运行脚本（直接 ShellExecute，不经 cmd）。返回值>32成功。"""
    logging.info(f"执行函数: run_py_in_venv_as_admin；参数: {python_exe_path}, {script_path}")
    if not os.path.exists(python_exe_path):
        raise FileNotFoundError(f"Python 解释器未找到: {python_exe_path}")
    if script_args is None:
        script_args = []
    params = ' '.join([f'"{script_path}"'] + [str(a) for a in script_args])
    workdir = os.path.dirname(script_path) or None
    show_cmd = 1 if show_window else 0
    try:
        res = ctypes.windll.shell32.ShellExecuteW(None,'runas',python_exe_path,params,workdir,show_cmd)
    except Exception as e:
        logging.error(f"ShellExecuteW 失败: {e}")
        res = 0
    return res

def run_py_in_venv_as_admin_hidden(python_exe_path, script_path, script_args=None):
    return run_py_in_venv_as_admin(python_exe_path, script_path, script_args, show_window=False)

def restart_self_as_admin():
    """以管理员权限重新启动当前程序"""
    logging.info("执行函数: restart_self_as_admin")
    try:
        # 获取当前程序的完整路径和参数
        if getattr(sys, "frozen", False):
            # 如果是打包后的exe
            current_exe = sys.executable
            logging.info(f"当前程序路径(EXE): {current_exe}")
        else:
            # 如果是Python脚本
            current_script = os.path.abspath(__file__)
            current_exe = sys.executable
            logging.info(f"当前程序路径(脚本): {current_script}")
            logging.info(f"Python解释器路径: {current_exe}")
        
        # 构建重启命令
        if getattr(sys, "frozen", False):
            result = run_as_admin(current_exe)
        else:
            # 脚本模式优先使用 pythonw.exe 隐藏窗口
            base_dir = os.path.dirname(current_exe)
            pythonw = os.path.join(base_dir, 'pythonw.exe')
            interpreter = pythonw if os.path.exists(pythonw) else current_exe
            script_path = os.path.abspath(__file__)
            result = run_py_in_venv_as_admin(interpreter, script_path, show_window=False)

        if result > 32:
            logging.info(f"成功以管理员权限重启程序，返回值: {result}")
            # 等待新进程出现再退出，避免用户看到直接退出
            if not getattr(sys, 'frozen', False):
                target = os.path.abspath(__file__)
                for _ in range(50):  # 最多 5 秒
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
            logging.error(f"以管理员权限重启程序失败，错误码: {result}")
            messagebox.showwarning("UAC提权", f"获取管理员权限失败，错误码: {result}")
            return False
            
    except Exception as e:
        logging.error(f"重启程序时出错: {e}")
        messagebox.showerror("UAC提权", f"重启程序时出错: {e}")
        return False

def check_and_request_uac():
    """检查并在需要时请求提权"""
    logging.info("执行函数: check_and_request_uac")
    
    # 如果已经是管理员权限，无需提权
    if IS_ADMIN:
        logging.info("当前已具有管理员权限，无需提权")
        return True
    
    logging.info("当前程序未获得管理员权限，准备提权...")
    
    try:
        # 询问用户是否要提权
        if messagebox.askyesno("管理员权限", "程序未获得管理员权限。\n是否立即请求管理员权限？\n\n选择'是'将重新启动程序并请求管理员权限。"):
            # 以管理员权限重新启动程序
            return restart_self_as_admin()
        else:
            logging.info("用户选择不进行提权")
            return False
        
    except Exception as e:
        logging.error(f"提权过程中出错: {e}")
        messagebox.showerror("管理员权限", f"提权失败: {e}")
        return False

def startup_admin_check():
    """启动时进行管理员权限检查和自动提权"""
    logging.info("开始检查管理员权限状态...")
    try:
        # 检查并请求提权（如果需要的话）
        admin_result = check_and_request_uac()
        if admin_result is False:  # 明确检查False，因为None表示其他情况
            logging.info("未进行提权或提权失败，程序将以当前权限继续运行")
        # 如果admin_result是True，说明已经有管理员权限
        # 如果函数内部重启了程序，这里的代码不会执行到
    except Exception as e:
        logging.error(f"管理员权限检查过程中出现异常: {e}")
        logging.info("程序将以当前权限继续运行")


def open_gui() -> None:
    """
    English: Attempts to open GUI.py or RC-GUI.exe, else shows an error message
    中文: 尝试运行 GUI.py 或 RC-GUI.exe，如果找不到则弹出错误提示
    """
    if os.path.isfile("GUI.py"):
        logging.info("正在打开配置窗口...")
        subprocess.Popen([".venv\\Scripts\\python.exe", "GUI.py"])
        # notify_in_thread("正在打开配置窗口...")
    elif os.path.isfile("RC-GUI.exe"):
        logging.info("正在打开配置窗口...")
        subprocess.Popen(["RC-GUI.exe"])
        # notify_in_thread("正在打开配置窗口...")
    else:
        def show_message():
            current_path = os.getcwd()
            logging.error(f"找不到GUI.py或RC-GUI.exe\n当前工作路径{current_path}")
            messagebox.showerror(
                "Error", f"找不到GUI.py或RC-GUI.exe\n当前工作路径{current_path}"
            )

        thread = threading.Thread(target=show_message)
        thread.daemon = True
        thread.start()


"""
退出程序。

无参数
无返回值
"""


def exit_program() -> None:
    """
    English: Stops the MQTT loop and exits the program
    中文: 停止 MQTT 循环，并退出程序
    """
    logging.info("正在退出程序...")
    try:
        mqttc.loop_stop()
        mqttc.disconnect()
    except Exception as e:
        logging.error(f"程序停止时出错: {e}")
    finally:
        try:
            ctypes.windll.kernel32.ReleaseMutex(mutex)
            ctypes.windll.kernel32.CloseHandle(mutex)
            logging.info("互斥体已释放")
        except Exception as e:
            logging.error(f"释放互斥体时出错: {e}")
        
        logging.info("程序已停止")
        threading.Timer(0.5, lambda: os._exit(0)).start()
        sys.exit(0)

# 获取资源文件的路径（统一实现，兼容 PyInstaller/Nuitka）
def resource_path(relative_path: str) -> str:
    """返回资源文件路径，兼容 PyInstaller 与 Nuitka。"""
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

# 获取应用程序的路径
if getattr(sys, "frozen", False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

# 改变当前的工作路径
os.chdir(application_path)

# 配置文件和日志文件路径改为当前工作目录
appdata_path = os.path.abspath(os.path.dirname(sys.argv[0]))
logs_dir = os.path.join(appdata_path, "logs")

# 确保日志目录存在
if not os.path.exists(logs_dir):
    try:
        os.makedirs(logs_dir)
    except Exception as e:
        print(f"创建日志目录失败: {e}")
        logs_dir = appdata_path

log_path = os.path.join(logs_dir, "RC.log")
config_path = os.path.join(appdata_path, "config.json")

# 配置日志处理器，启用日志轮转
log_handler = RotatingFileHandler(
    log_path, 
    maxBytes=1*1024*1024,  # 1MB
    backupCount=1,          # 保留1个备份文件
    encoding='utf-8'
)

# 设置日志格式
log_formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s',
    datefmt="%Y-%m-%d %H:%M:%S"
)
log_handler.setFormatter(log_formatter)

# 获取根日志记录器并设置
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)

# 检查配置文件是否存在
if os.path.exists(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            # 读取通知开关
            try:
                globals()["NOTIFY_ENABLED"] = bool(config.get("notify", 1))
            except Exception:
                pass
    except json.JSONDecodeError:
        messagebox.showerror("Error", "配置文件格式错误\n请检查config.json文件")
        logging.error("config.json 文件格式错误")
        open_gui()
        threading.Timer(0.5, lambda: os._exit(0)).start()
        sys.exit()
else:
    messagebox.showerror("Error", "配置文件不存在\n请先打开RC-GUI配置文件")
    logging.error("config.json 文件不存在")
    open_gui()
    threading.Timer(0.5, lambda: os._exit(0)).start()
    sys.exit()

# 检查程序是以脚本形式运行还是打包后的exe运行
is_script_mode = not getattr(sys, "frozen", False)
if is_script_mode:
    # 如果是脚本形式运行，先清空日志文件
    try:
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write('')  # 清空文件内容
        logging.info(f"已清空日志文件: {log_path}")
        print(f"已清空日志文件: {log_path}")
        
        # 记录程序启动信息
        logging.info("="*50)
        logging.info("远程控制主程序启动")
        logging.info(f"程序路径: {os.path.abspath(__file__)}")
        logging.info(f"工作目录: {os.getcwd()}")
        logging.info(f"运行模式: {'脚本模式' if is_script_mode else 'EXE模式'}")
        logging.info(f"Python版本: {sys.version}")
        logging.info(f"系统信息: {sys.platform}")
        logging.info(f"配置文件: {config_path}")
        logging.info(f"日志文件: {log_path}")
        logging.info("="*50)
    except Exception as e:
        logging.error(f"清空日志文件失败: {e}")
        print(f"清空日志文件失败: {e}")


# 确保config已经定义后再继续
# 如果启用测试模式，并且当前不是脚本模式，则清空旧日志（与脚本模式一致）
try:
    if config.get("test") == 1 and not is_script_mode:
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write('')
        logging.info(f"测试模式启用，已清空日志文件: {log_path}")
        print(f"测试模式启用，已清空日志文件: {log_path}")
        # 记录程序启动信息
        logging.info("="*50)
        logging.info("远程控制主程序启动（测试模式）")
        logging.info(f"程序路径: {os.path.abspath(__file__)}")
        logging.info(f"工作目录: {os.getcwd()}")
        logging.info(f"运行模式: {'脚本模式' if is_script_mode else 'EXE模式'}")
        logging.info(f"Python版本: {sys.version}")
        logging.info(f"系统信息: {sys.platform}")
        logging.info(f"配置文件: {config_path}")
        logging.info(f"日志文件: {log_path}")
        logging.info("="*50)
except Exception as e:
    logging.error(f"测试模式清空日志失败: {e}")


# 在程序启动时查询托盘程序的管理员权限状态并保存为全局变量
IS_ADMIN = False
try:
    IS_ADMIN = ctypes.windll.shell32.IsUserAnAdmin() != 0
    logging.info(f"管理员权限状态: {'已获得' if IS_ADMIN else '未获得'}")
except Exception as e:
    logging.error(f"检查管理员权限时出错: {e}")
    IS_ADMIN = False

# 记录程序正常启动信息（如果之前没有记录的话）
if not is_script_mode and config.get("test") != 1:
    logging.info("="*50)
    logging.info("远程控制主程序启动")
    logging.info(f"程序路径: {os.path.abspath(__file__)}")
    logging.info(f"工作目录: {os.getcwd()}")
    logging.info(f"运行模式: {'脚本模式' if is_script_mode else 'EXE模式'}")
    logging.info(f"Python版本: {sys.version}")
    logging.info(f"系统信息: {sys.platform}")
    logging.info(f"配置文件: {config_path}")
    logging.info(f"日志文件: {log_path}")
    logging.info("="*50)
    

if config.get("test") == 1:
    logging.warning("开启测试模式:可以不启用任何主题")
else:
    if (
        all(
            config.get(f"{key}_checked", 0) == 0
            for key in ["Computer", "screen", "volume", "sleep"]
        )
        and all(
            config.get(f"application{index}_checked", 0) == 0
            for index in range(1, 100)
        )
        and all(
            config.get(f"serve{index}_checked", 0) == 0 for index in range(1, 100)
        )
    ):
        logging.error("没有启用任何主题，显示错误信息")
        messagebox.showerror("Error", "主题不能一个都没有吧！\n（除了测试模式）")
        open_gui()
        logging.info("程序已停止")
        threading.Timer(0.5, lambda: os._exit(0)).start()
        sys.exit(0)
    else:
        logging.info("至少已有一个主题被启用")

broker = config.get("broker")
# 读取客户端ID配置
client_id = config.get("client_id", "")
port = int(config.get("port"))

# 获取MQTT认证信息
mqtt_username = config.get("mqtt_username", "")  # 用户名
mqtt_password = config.get("mqtt_password", "")  # 密码
auth_mode = config.get("auth_mode", "private_key")  # 认证模式：private_key（私钥）或 username_password（账号密码）


# 动态加载主题
def load_theme(key):
    """
    English: Loads the theme from config if it is enabled
    中文: 如果主题被勾选启用，则从配置中加载该主题
    """
    return config.get(key) if config.get(f"{key}_checked") == 1 else None


Computer = load_theme("Computer")
screen = load_theme("screen")
volume = load_theme("volume")
sleep = load_theme("sleep")
media = load_theme("media")

# 加载应用程序主题到应用程序列表
applications = []
for i in range(1, 50):
    app_key = f"application{i}"
    directory_key = f"application{i}_directory{i}"
    application = load_theme(app_key)
    directory = config.get(directory_key) if application else None
    if application:
        logging.info(f"加载应用程序: {app_key}, 目录: {directory}")
        applications.append((application, directory))
logging.info(f"读取的应用程序列表: {applications}\n")

# 加载服务主题到服务列表
serves = []
for i in range(1, 50):
    serve_key = f"serve{i}"
    serve_name_key = f"serve{i}_value"
    serve = load_theme(serve_key)
    serve_name = config.get(serve_name_key) if serve else None
    if serve:
        logging.info(f"加载服务: {serve_key}, 名称: {serve_name}")
        serves.append((serve, serve_name))
logging.info(f"读取的服务列表: {serves}\n")

# 加载命令主题到命令列表
commands = []
for i in range(1, 50):
    cmd_key = f"command{i}"
    cmd_value_key = f"command{i}_value"
    cmd_topic = load_theme(cmd_key)
    cmd_value = config.get(cmd_value_key) if cmd_topic else None
    if cmd_topic:
        logging.info(f"加载命令: {cmd_key}, 命令: {cmd_value}")
        commands.append((cmd_topic, cmd_value))
logging.info(f"读取的命令列表: {commands}\n")

# 加载 Hotkey 自定义主题
hotkeys = []
for i in range(1, 50):
    hk_key = f"hotkey{i}"
    hk_topic = load_theme(hk_key)
    if hk_topic:
        hk_conf = {
            "on_type": (config.get(f"{hk_key}_on_type") or "keyboard"),
            "on_value": (config.get(f"{hk_key}_on_value") or ""),
            "off_type": (config.get(f"{hk_key}_off_type") or "none"),
            "off_value": (config.get(f"{hk_key}_off_value") or ""),
            "char_delay_ms": (config.get(f"{hk_key}_char_delay_ms") or 0),
        }
        logging.info(f"加载Hotkey: {hk_key}, 配置: {hk_conf}")
        hotkeys.append((hk_topic, hk_conf))
logging.info(f"读取的Hotkey列表: {hotkeys}\n")

# 兼容：如果旧版内置 Hotkey 主题仍被勾选，作为热键条目加入（建议迁移到自定义主题）
legacy_hotkey_topic = load_theme("hotkey")
if legacy_hotkey_topic:
    legacy_conf = {
        "on_type": (config.get("hotkey_on_type") or "keyboard"),
        "on_value": (config.get("hotkey_on_value") or ""),
        "off_type": (config.get("hotkey_off_type") or "none"),
        "off_value": (config.get("hotkey_off_value") or ""),
    }
    logging.warning("检测到旧版内置 Hotkey 主题，已临时兼容；建议在GUI中将其迁移为‘按键(Hotkey)’自定义主题。")
    hotkeys.append((legacy_hotkey_topic, legacy_conf))

# 如果主题不为空，将其记录到日志中
for key in ["Computer", "screen", "volume", "sleep", "media"]:
    if config.get(key):
        logging.info(f'主题"{config.get(key)}"')

for application, directory in applications:
    logging.info(f'主题"{application}"，值："{directory}"')

for serve, serve_name in serves:
    logging.info(f'主题"{serve}"，值："{serve_name}"')
for cmd_topic, cmd_value in commands:
    logging.info(f'主题"{cmd_topic}"，值："{cmd_value}"')
    
"""
托盘图标

"""
def tray() -> None:
    try:
        global IS_ADMIN
        admin_status = "【已获得管理员权限】" if IS_ADMIN else "【未获得管理员权限】"
        logging.info(f"开始加载托盘图标，当前权限状态: {admin_status}")
        # 初始化系统托盘图标和菜单
        icon_path = resource_path("icon.ico" if getattr(sys, "frozen", False) else "res\\icon.ico")
        # 从资源文件中读取图像
        with open(icon_path, "rb") as f:
            image_data = f.read()
        icon = pystray.Icon("RC-main", title=f"远程控制-{BANBEN}")
        image = Image.open(io.BytesIO(image_data))
        menu = (
            pystray.MenuItem(f"{admin_status}", None),
            pystray.MenuItem("打开配置", open_gui, default=True),
            pystray.MenuItem("退出", exit_program),
        )
        icon.menu = menu
        icon.icon = image
        icon_Thread = threading.Thread(target=icon.run)
        icon_Thread.daemon = True
        icon_Thread.start()
        logging.info("托盘图标已加载完成")
    except Exception as e:
        messagebox.showerror(
            "Error", f"加载托盘图标时出错\n详情请查看日志"
        )
        logging.error(f"加载托盘图标时出错: {e}")


def check_tray_and_start():
    """
    检测托盘程序是否运行，如果未运行则启动自带托盘
    """
    TRAY_EXE_NAME = "RC-tray.exe" if getattr(sys, "frozen", False) else "tray.py"
    tray_zt = get_main_proc(TRAY_EXE_NAME)
    if not tray_zt:
        logging.error("托盘未启动，将使用自带托盘")
        tray()
        notify_in_thread("托盘未启动，将使用自带托盘")
    else:
        logging.info("托盘进程已存在")

def tray_():
    """
    延迟1秒后检测托盘状态，不阻塞主进程
    """
    logging.info("将在1秒后检测托盘程序状态")
    timer = threading.Timer(1.0, check_tray_and_start)
    timer.daemon = True
    timer.start()

# 启动时检查管理员权限并请求提权
check_and_request_uac()

# 提升高DPI下托盘菜单与提示清晰度
try:
    _enable_dpi_awareness()
except Exception:
    pass

tray_()

if IS_ADMIN:
    logging.info("当前程序以管理员权限运行")
    # 将管理员权限状态写入文件，方便其他程序查询
    try:
        status_file = os.path.join(logs_dir, "admin_status.txt")
        with open(status_file, "w", encoding="utf-8") as f:
            f.write("admin=1")
        logging.info(f"管理员权限状态已写入文件: {status_file}")
    except Exception as e:
        logging.error(f"写入管理员权限状态文件失败: {e}")
else:
    logging.info("当前程序以普通权限运行")
    # 将普通权限状态写入文件
    try:
        status_file = os.path.join(logs_dir, "admin_status.txt")
        with open(status_file, "w", encoding="utf-8") as f:
            f.write("admin=0")
        logging.info(f"权限状态已写入文件: {status_file}")
    except Exception as e:
        logging.error(f"写入权限状态文件失败: {e}")

# 初始化MQTT客户端
mqttc = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2) # type: ignore
mqttc.on_connect = on_connect
mqttc.on_message = on_message
mqttc.on_subscribe = on_subscribe
mqttc.on_unsubscribe = on_unsubscribe

mqttc.user_data_set([])

# 根据认证模式设置连接参数
if auth_mode == "username_password" and mqtt_username and mqtt_password:
    # 方式二：使用用户名密码进行身份验证（适用于大多数IoT平台）
    logging.info("使用账号密码方式连接MQTT服务器")
    logging.info(f"用户名: {mqtt_username}")
    logging.info("密码: [已隐藏]")
    
    # 设置用户名和密码
    mqttc.username_pw_set(mqtt_username, mqtt_password)
    
    # 客户端ID可以设置为任意值
    final_client_id = config.get("client_id", mqtt_username)
    mqttc._client_id = final_client_id
    logging.info(f"客户端ID: {final_client_id}")
else:
    # 方式一：使用私钥作为客户端ID（兼容巴法云等平台）
    logging.info("使用私钥方式连接MQTT服务器")
    
    # 检查客户端ID是否为空
    if not client_id or client_id.strip() == "":
        error_msg = "私钥模式下客户端ID不能为空！\n请在配置文件中设置客户端ID（私钥）。"
        logging.error(error_msg)
        messagebox.showerror("配置错误", error_msg)
        open_gui()
        threading.Timer(0.5, lambda: os._exit(0)).start()
        sys.exit(0)
    
    logging.info(f"客户端ID（私钥）: {client_id}")
    
    # 设置私钥作为客户端ID
    mqttc._client_id = client_id
    # 不设置用户名和密码

try:
    mqttc.connect(broker, port)
except socket.timeout:
    messagebox.showerror(
        "Error", "连接到 MQTT 服务器超时，请检查网络连接或服务器地址，端口号！"
    )
    open_gui()
    threading.Timer(0.5, lambda: os._exit(0)).start()
    sys.exit(0)
except socket.gaierror:
    messagebox.showerror(
        "Error", "无法解析 MQTT 服务器地址，请重试或检查服务器地址是否正确！"
    )
    open_gui()
    threading.Timer(0.5, lambda: os._exit(0)).start()
    sys.exit(0)
except ConnectionRefusedError:
    error_msg = f"连接被拒绝，无法连接到MQTT服务器！\n\n可能的原因：\n• 服务器地址错误：{broker}\n• 端口号错误：{port}\n• 服务器未启动或不可用\n• 防火墙阻止连接\n\n请检查配置文件中的服务器信息。"
    logging.error(f"连接被拒绝: {broker}:{port}")
    messagebox.showerror("连接被拒绝", error_msg)
    open_gui()
    threading.Timer(0.5, lambda: os._exit(0)).start()
    sys.exit(0)
except Exception as e:
    error_msg = f"连接MQTT服务器时发生未知错误：\n{str(e)}\n\n请检查网络连接和服务器配置。"
    logging.error(f"MQTT连接异常: {e}")
    messagebox.showerror("连接错误", error_msg)
    open_gui()
    threading.Timer(0.5, lambda: os._exit(0)).start()
    sys.exit(0)
try:
    mqttc.loop_forever()
except KeyboardInterrupt:
    logging.warning("收到中断,程序停止")
    notify_in_thread("收到中断信号\n程序停止")
    exit_program()
except Exception as e:
    logging.error(f"程序异常: {e}")
    exit_program()

logging.info(f"总共收到以下消息: {mqttc.user_data_get()}")

try:
    logging.info("释放互斥体")
    ctypes.windll.kernel32.ReleaseMutex(mutex)
    ctypes.windll.kernel32.CloseHandle(mutex)
except Exception as e:
    logging.error(f"释放互斥体时出错: {e}")
