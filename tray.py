"""
程序文件名RC-tray.exe
运行用户：当前登录用户（可能有管理员权限）
pyinstaller -F -n RC-tray --windowed --icon=res\\icon.ico --add-data "res\\icon.ico;."  tray.py
"""

import os
import sys
import subprocess
import threading
import time
import ctypes
import logging
from logging.handlers import RotatingFileHandler
import traceback
from tkinter import N, messagebox
import pystray
from win11toast import notify as toast
from PIL import Image
import psutil

BANBEN = "V2.1.3"

# 日志配置
appdata_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
logs_dir = os.path.join(appdata_dir, "logs")
# 确保日志目录存在
if not os.path.exists(logs_dir):
    try:
        os.makedirs(logs_dir)
    except Exception as e:
        print(f"创建日志目录失败: {e}")
        logs_dir = appdata_dir

tray_log_path = os.path.join(logs_dir, "tray.log")

# 配置日志处理器，启用日志轮转
log_handler = RotatingFileHandler(
    tray_log_path, 
    maxBytes=1*1024*1024,  # 1MB
    backupCount=1,          # 保留1个备份
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

# 检查程序是以脚本形式运行还是打包后的exe运行
is_script_mode = not getattr(sys, "frozen", False)
if is_script_mode:
    # 如果是脚本形式运行，先清空日志文件
    try:
        with open(tray_log_path, 'w', encoding='utf-8') as f:
            f.write('')  # 清空文件内容
        logging.info(f"已清空日志文件: {tray_log_path}")
        print(f"已清空日志文件: {tray_log_path}")
    except Exception as e:
        logging.error(f"清空日志文件失败: {e}")
        print(f"清空日志文件失败: {e}")

# 记录程序启动信息
logging.info("="*50)
logging.info("远程控制托盘程序启动")
logging.info(f"程序路径: {os.path.abspath(__file__)}")
logging.info(f"工作目录: {os.getcwd()}")
logging.info(f"运行模式: {'脚本模式' if is_script_mode else 'EXE模式'}")
logging.info(f"Python版本: {sys.version}")
logging.info(f"系统信息: {sys.platform}")
logging.info("="*50)

# 在程序启动时查询托盘程序的管理员权限状态并保存为全局变量
IS_TRAY_ADMIN = False
try:
    IS_TRAY_ADMIN = ctypes.windll.shell32.IsUserAnAdmin() != 0
    logging.info(f"托盘程序管理员权限状态: {'已获得' if IS_TRAY_ADMIN else '未获得'}")
except Exception as e:
    logging.error(f"检查托盘程序管理员权限时出错: {e}")
    IS_TRAY_ADMIN = False
# 配置
MAIN_EXE_NAME = "RC-main.exe" if getattr(sys, "frozen", False) else "main.py"
GUI_EXE_ = "RC-GUI.exe"
GUI_PY_ = "GUI.py"
ICON_FILE = "icon.ico" if getattr(sys, "frozen", False) else "res\\icon.ico"
MUTEX_NAME = "RC-main"
MAIN_EXE = os.path.join(appdata_dir, MAIN_EXE_NAME)
GUI_EXE = os.path.join(appdata_dir, GUI_EXE_)
GUI_PY = os.path.join(appdata_dir, GUI_PY_)

def resource_path(relative_path):
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)

# 信号处理函数，用于捕获CTRL+C等中断信号
def signal_handler(signum, frame):
    logging.info(f"接收到信号: {signum}，正在退出")
    # 直接调用停止托盘图标和退出
    if 'icon' in globals() and icon:
        try:
            icon.stop()
            logging.info("托盘图标已停止")
        except Exception as e:
            logging.error(f"停止托盘图标时出错: {e}")
    logging.info("托盘程序收到信号正常退出")
    os._exit(0)
# 注册信号处理器
try:
    import signal
    signal.signal(signal.SIGINT, signal_handler)  # 处理 Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # 处理终止信号
    logging.info("已注册信号处理器")
except (ImportError, AttributeError) as e:
    logging.warning(f"无法注册信号处理器: {e}")

def is_main_running():
    # 优先按进程检测主程序是否已运行
    logging.info(f"执行函数: is_main_running")
    main_proc = get_main_proc(MAIN_EXE_NAME)
    if main_proc:
        return True
    
    # 回退到互斥体判断，脚本运行时跳过
    if is_script_mode:
        logging.info(f"脚本运行模式，跳过互斥体判断")
        return False
        
    mutex = ctypes.windll.kernel32.OpenMutexW(0x100000, False, MUTEX_NAME)
    if mutex:
        ctypes.windll.kernel32.CloseHandle(mutex)
        logging.info(f"互斥体存在，主程序正在运行")
        return True
    else:
        logging.info(f"互斥体不存在，主程序未运行")
        return False

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

def run_py_in_venv_as_admin_hidden(python_exe_path, script_path, script_args=None):
    """
    使用指定的 Python 解释器（如虚拟环境中的 python.exe）以管理员权限静默运行脚本
    
    参数：
    python_exe_path (str): Python 解释器路径（如 "D:/Code/Python/Remote-Controls/.venv/Scripts/python.exe"）
    script_path (str): 要运行的 Python 脚本路径
    script_args (list): 传递给脚本的参数（可选）
    """
    logging.info(f"执行函数: run_py_in_venv_as_admin_hidden；参数: {python_exe_path}, {script_path}")
    if not os.path.exists(python_exe_path):
        raise FileNotFoundError(f"Python 解释器未找到: {python_exe_path}")

    if script_args is None:
        script_args = []

    # 构造命令（确保路径带引号，防止空格问题）
    command = f'"{python_exe_path}" "{script_path}" {" ".join(script_args)}'
    logging.info(f"构造的命令: {command}")

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
            # EXE模式：直接以管理员权限运行exe
            result = run_as_admin(current_exe)
        else:
            # 脚本模式：以管理员权限运行Python脚本
            result = run_py_in_venv_as_admin_hidden(current_exe, os.path.abspath(__file__))
        
        if result > 32:
            logging.info(f"成功以管理员权限重启程序，返回值: {result}")
            # 重启成功，退出当前进程
            logging.info("正在退出当前进程...")
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
    if IS_TRAY_ADMIN:
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


def get_main_proc(process_name):
    """查找程序进程是否存在"""
    logging.info(f"执行函数: get_main_proc; 参数: {process_name}")
    
    # 如果不是管理员权限运行，可能无法查看所有进程，记录警告
    global IS_TRAY_ADMIN
    if not IS_TRAY_ADMIN:
        logging.warning("托盘程序未以管理员权限运行,可能无法查看所有进程")
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
                        logging.info(f"找到主程序进程: {proc.pid}, 用户: {current_user}")
                        return True
                    # 指定用户时提取用户名部分比较
                    if current_user:
                        user_part = current_user.split('\\')[-1].lower()
                        if user_part == target_user:
                            logging.info(f"找到主程序进程: {proc.pid}, 用户: {current_user}")
                            return True
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        # 如果找不到进程，记录信息
        logging.info(f"未找到主程序进程: {process_name}")
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
                        logging.info(f"找到主程序Python进程: {proc.pid}, 命令行: {cmdline}")
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
                            logging.info(f"wmic找到主程序Python进程: {current_pid}, 命令行: {current_cmd}")
                            return psutil.Process(int(current_pid))
                        except (psutil.NoSuchProcess, ValueError) as e:
                            logging.error(f"获取进程对象失败，PID: {current_pid}, 错误: {e}")
                    
                    current_pid = None
                    current_cmd = None
        except Exception as e:
            logging.error(f"使用wmic查找Python进程失败: {e}")
    
    logging.info("未找到主程序进程")
    return None

def is_main_admin():
    """检查主程序是否以管理员权限运行"""
    logging.info("执行函数: is_main_admin")
    # 通过读取主程序写入的状态文件来判断管理员权限
    status_file = os.path.join(logs_dir, "admin_status.txt")
    
    # 首先检查文件是否存在
    if os.path.exists(status_file):
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                logging.info(f"读取主程序权限状态文件: {content}")
                # 检查文件内容
                if content == "admin=1":
                    return True
                elif content == "admin=0":
                    return False
                else:
                    logging.warning(f"权限状态文件内容格式错误: {content}")
        except Exception as e:
            logging.error(f"读取权限状态文件时出错: {e}")
    else:
        logging.warning(f"权限状态文件不存在: {status_file}")
        return False

def is_admin_start_main(icon=None, item=None):
    """管理员权限运行主程序"""
    logging.info("执行函数: is_admin_start_main")
    # 使用线程池中的一个工作线程执行，而不是每次创建新线程
    threading.Thread(target=_admin_start_main_worker).start()

def _admin_start_main_worker():
    """管理员权限运行主程序的实际工作函数"""
    notify("正在启动主程序...")
    if MAIN_EXE_NAME.endswith('.exe') and os.path.exists(MAIN_EXE):
        logging.info(f"以可执行文件方式启动: {MAIN_EXE}")
        rest=run_as_admin(MAIN_EXE)
        if rest > 32:
            logging.info(f"成功以管理员权限启动主程序，PID: {rest}")
        else:
            notify(f"以管理员权限启动主程序失败，错误码: {rest}", level="error", show_error=True)
    elif os.path.exists(MAIN_EXE):
        logging.info(f"以Python脚本方式启动: {sys.executable} {MAIN_EXE}")
        rest=run_py_in_venv_as_admin_hidden(sys.executable, MAIN_EXE)
        if rest > 32:
            logging.info(f"成功以管理员权限启动主程序，PID: {rest}")
        else:
            notify(f"以管理员权限启动主程序失败，错误码: {rest}", level="error", show_error=True)

def check_admin(icon=None, item=None):
    """检查主程序的管理员权限状态"""
    logging.info("执行函数: check_admin")
    if is_main_running():
        if is_main_admin():
            notify("主程序已获得管理员权限")
            return
        else:
            notify("主程序未获得管理员权限")
            return
    else:
        notify("主程序未运行")
        return

def open_gui(icon=None, item=None):
    """打开配置界面"""
    logging.info("执行函数: open_gui")
    if os.path.exists(GUI_EXE):
        subprocess.Popen([GUI_EXE])
        logging.info(f"打开配置界面: {GUI_EXE}")
    elif os.path.exists(GUI_PY):
        logging.info(f"打开配置界面: {GUI_PY}")
        subprocess.Popen([sys.executable, GUI_PY])
    else:
        logging.error(f"未找到配置界面: {GUI_EXE} 或 {GUI_PY}")
        notify("未找到配置界面")

def notify(msg, level="info", show_error=False):
    """
    发送通知并记录日志
    
    参数:
    - msg: 通知消息
    - level: 日志级别 ( "info", "warning", "error", "critical")
    - show_error: 是否在通知失败时显示错误对话框
    """
    # 根据级别记录日志
    log_func = getattr(logging, level.lower())
    log_func(f"通知: {msg}")
    
    # 在单独的线程中发送通知，避免阻塞主线程
    def _show_toast_in_thread():
        try:
            toast(msg)
        except Exception as e:
            logging.error(f"发送通知失败: {e}")
            if show_error:
                try:
                    messagebox.showinfo("通知", msg)
                except Exception as e2:
                    logging.error(f"显示消息框也失败: {e2}")
            else:
                print(msg)
    
    # 启动一个守护线程来显示通知
    t = threading.Thread(target=_show_toast_in_thread)
    t.daemon = True
    t.start()

def close_exe(name:str,skip_admin:bool=False):
    """关闭指定名称的进程"""
    logging.info(f"执行函数: close_exe; 参数: {name}")
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        if is_admin or skip_admin:
            logging.info(f"尝试关闭进程: {name}")
            script_content = f"""
            @echo off
            taskkill /im "{name}" /f
            if %errorlevel% equ 0 (
                echo 成功关闭进程 "{name}".
            ) else (
                echo 进程 "{name}" 未运行或关闭失败.
            )
            exit
            """
            temp_script = os.path.join(os.environ.get('TEMP', '.'), 'stop_tray.bat')
            with open(temp_script, 'w') as f:
                f.write(script_content)
            
            # 以管理员权限运行批处理
            rest=ctypes.windll.shell32.ShellExecuteW(
                None, "runas", "cmd.exe", f"/c {temp_script}", None, 0
            )
            if rest > 32:
                logging.info(f"成功关闭进程，PID: {rest}")
            else:
                # logging.error(f"关闭进程失败，错误码: {rest}")
                notify(f"关闭进程失败，错误码: {rest}", level="error", show_error=True)
                return
        else:
            # logging.warning(f"当前用户没有管理员权限，无法关闭进程{name}")
            notify(f"当前用户没有管理员权限，无法关闭进程{name}", level="warning")
    except FileNotFoundError:
        # logging.error(f"未找到进程文件: {name}")
        notify(f"未找到进程文件: {name}", level="error", show_error=True)
    except Exception as e:
        logging.error(f"关闭{name}时出错: {e}")
        # 如果出错，仍然尝试正常退出
        threading.Timer(1.0, lambda: os._exit(0)).start()

def close_script(script_name,skip_admin:bool=False):
    """关闭脚本函数"""
    logging.info(f"执行函数: close_script; 参数: {script_name}")
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        if is_admin or skip_admin:
            # 通过名称查找进程（模糊匹配）
            logging.info(f"尝试关闭脚本: {script_name}")
            cmd_find = f'tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH'
            output = subprocess.check_output(cmd_find, shell=True).decode('utf-8')
            
            # 解析输出，找到目标脚本的PID
            target_pids = []
            for line in output.splitlines():
                if script_name in line:
                    parts = line.replace('"', '').split(',')
                    pid = parts[1].strip()
                    target_pids.append(pid)
            
            # 终止所有匹配的进程
            for pid in target_pids:
                try:
                    # 以管理员权限调用 taskkill
                    subprocess.run(
                        f'taskkill /F /PID {pid}',
                        shell=True,
                        check=True,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    print(f"已终止进程 PID: {pid}")
                except subprocess.CalledProcessError:
                    print(f"无法终止进程 PID: {pid}（可能需要管理员权限）")
        else:
            # logging.warning(f"当前用户没有管理员权限，无法关闭脚本{script_name}")
            notify(f"当前用户没有管理员权限，无法关闭脚本{script_name}", level="warning")
    except FileNotFoundError:
        # logging.error(f"未找到脚本文件: {script_name}")
        notify(f"未找到脚本文件: {script_name}", level="error", show_error=True)
    except Exception as e:
        logging.error(f"关闭脚本{script_name}时出错: {e}")

def stop_tray():
    """关闭托盘程序"""
    logging.info("执行函数: stop_tray")
    logging.info("="*30)
    logging.info("正在关闭托盘程序")
    
    # 有管理员权限或UAC未启用时，正常重启主程序并退出托盘
    logging.info("托盘程序退出，将重启主程序并退出托盘")
    
    # 定义在restart_main完成后执行的回调函数
    def exit_after_restart():
        logging.info("主程序重启完成，现在可以安全退出托盘")
        # 安全停止托盘图标
        if 'icon' in globals() and icon:
            try:
                icon.stop()
                logging.info("托盘图标已停止")
            except Exception as e:
                logging.error(f"停止托盘图标时出错: {e}")
        # 设置一个定时器在2秒后退出程序
        threading.Timer(0.5, lambda: os._exit(0)).start()
    
    # 调用restart_main并传递回调函数
    restart_main(callback=exit_after_restart)

def close_main():
    """关闭主程序"""
    logging.info(f"执行函数: close_main,{MAIN_EXE}")
    try:
        if MAIN_EXE_NAME.endswith('.exe') and os.path.exists(MAIN_EXE):
            close_exe(MAIN_EXE_NAME)
        elif os.path.exists(MAIN_EXE):
            close_script(MAIN_EXE_NAME)
    except Exception as e:
        # logging.error(f"关闭主程序时出错: {e}")
        notify(f"关闭主程序时出错: {e}", level="error", show_error=True)

def restart_main(icon=None, item=None, callback=None):
    """重启主程序（先关闭再启动）"""
    # 使用单个线程执行重启过程，避免创建多个线程
    threading.Thread(target=lambda: _restart_main_worker(callback)).start()

def _restart_main_worker(callback=None):
    """重启主程序的实际工作函数"""
    logging.info("执行函数: restart_main")
    notify("正在重启主程序...")
    # 先关闭主程序
    close_main()
    # 等待一会儿确保进程完全关闭
    time.sleep(1)
    # 再启动主程序
    _admin_start_main_worker()
    logging.info("主程序重启完成")
    
    # 如果有回调函数，执行它
    if callback and callable(callback):
        logging.info("执行重启后的回调函数")
        callback()

def start_notify():
    """启动时发送通知"""
    logging.info("执行函数: start_notify")
    # 检查主程序状态
    main_status = "未运行"
    if is_main_running():
        main_status = "以管理员权限运行" if is_main_admin() else "以普通权限运行"

    # 检查托盘程序状态
    tray_status = "以管理员权限运行" if IS_TRAY_ADMIN else "以普通权限运行"

    # 权限提示
    admin_tip = ""
    if not IS_TRAY_ADMIN:
        admin_tip = "，可能无法查看开机自启的主程序状态"

    run_mode_info = "（脚本模式）" if is_script_mode else "（EXE模式）"
    notify(f"远程控制托盘程序已启动{run_mode_info}\n主程序状态: {main_status}\n托盘状态: {tray_status}{admin_tip}")

def get_menu_items():
    """生成动态菜单项列表"""
    logging.info("执行函数: get_menu_items")
    # 检查托盘程序管理员权限状态
    global IS_TRAY_ADMIN
    admin_status = "【已获得管理员权限】" if IS_TRAY_ADMIN else "【未获得管理员权限】"
      # 添加运行模式提示
    mode_info = "【脚本模式】" if is_script_mode else "【EXE模式】"
    return [
        pystray.MenuItem(f"{mode_info} 版本-{BANBEN}", None),
        # 显示权限状态的纯文本项
        pystray.MenuItem(f"托盘状态: {admin_status}", None),
        # 其他功能菜单项
        pystray.MenuItem("打开配置界面", open_gui),
        pystray.MenuItem("检查主程序管理员权限", check_admin),
        pystray.MenuItem("启动主程序", is_admin_start_main),
        pystray.MenuItem("重启主程序", lambda icon, item: restart_main(icon, item)),        
        pystray.MenuItem("关闭主程序", close_main),
        pystray.MenuItem("退出托盘（使用主程序自带托盘）", lambda icon, item: stop_tray()),
    ]

# 托盘启动时检查主程序状态，使用单独线程处理主程序启动/重启，避免阻塞UI
def init_main_program():
    if is_main_running():
        logging.info("托盘启动时发现主程序正在运行，准备重启...")
        restart_main()
    else:
        logging.info("托盘启动时未发现主程序运行，准备启动...")
        is_admin_start_main()

# 启动时检查管理员权限并请求提权
check_and_request_uac()

# 在单独的线程中处理主程序初始化
threading.Thread(target=init_main_program, daemon=True).start()

# 托盘图标设置
icon_path = resource_path(ICON_FILE)
image = Image.open(icon_path) if os.path.exists(icon_path) else None
# 创建静态菜单项，只在程序启动时生成一次
menu_items = get_menu_items()
menu = pystray.Menu(*menu_items)

# 创建托盘图标
icon = pystray.Icon("RC-main-Tray", image, f"远程控制托盘-{BANBEN}", menu)

# 使用定时器延迟执行通知，不会阻塞主线程
timer = threading.Timer(3.0, start_notify)
timer.daemon = True  # 设置为守护线程，程序退出时自动结束
timer.start()

# 在带异常处理的环境中运行托盘程序
try:
    logging.info("开始运行托盘图标")
    icon.run()
except KeyboardInterrupt:
    logging.info("检测到键盘中断，正在退出")
    if 'icon' in globals() and icon:
        try:
            icon.stop()
        except Exception as e:
            logging.error(f"停止托盘图标时出错: {e}")
except Exception as e:
    logging.error(f"托盘图标运行时出错: {e}")
    logging.error(traceback.format_exc())
finally:
    logging.warning("托盘程序正在退出")
    os._exit(0)
