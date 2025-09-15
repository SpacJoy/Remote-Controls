"""
程序文件名RC-tray.exe
运行用户：当前登录用户（可能有管理员权限）

打包（当前仅需 icon.ico；托盘随机图片改为远程接口，无需打包 cd1~cd5）：
1) PyInstaller 示例：
    pyinstaller -F -n RC-tray --windowed --icon=res\\icon.ico --add-data "res\\icon.ico;." tray.py
2) Nuitka 示例：
    python -m nuitka --onefile --windows-icon-from-ico=res\\icon.ico --include-data-files=res\\icon.ico=icon.ico --output-filename=RC-tray.exe tray.py
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
from win11toast import notify as toast, clear_toast
from PIL import Image
import psutil
import webbrowser
import random
import urllib.request
import json
import re
import threading as _threading_for_hook

# 安全：设置全局异常钩子，避免未捕获异常导致 PyInstaller 弹 CrashSender 进程（某些环境会尝试调用缺失的 CrashSender.exe）
def _safe_excepthook(exc_type, exc_value, exc_tb):
    try:
        import traceback as _tb
        msg = ''.join(_tb.format_exception(exc_type, exc_value, exc_tb))
        logging.error("未捕获异常:\n" + msg)
        # 尽量非阻塞提示
        try:
            notify("托盘内部异常(已记录)", level="error")
        except Exception:
            pass
    except Exception:
        pass
    # 不再次抛出，防止触发外部 crash 报告
sys.excepthook = _safe_excepthook

# 统一版本来源
try:
    from version_info import get_version_string
    BANBEN = f"V{get_version_string()}"
except Exception:
    BANBEN = "V未知版本"
REPO_OWNER = "chen6019"
REPO_NAME = "Remote-Controls"
GITHUB_RELEASES_LATEST_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"

# 全局变量：版本检查缓存
_version_check_cache = {
    "status": "pending",  # "pending", "checking", "ok", "error"
    "latest": None,       # 最新版本号或None
    "checked_time": 0.0   # 检查时间戳
}

# DPI 与字体渲染优化（高DPI下更清晰）
def _enable_dpi_awareness() -> None:
    """
    使进程 DPI 感知，避免高分屏托盘菜单/提示发糊。
    优先 Per-Monitor DPI 感知，回退到 System DPI Aware。
    """
    try:
        shcore = ctypes.windll.shcore
        # 2 = PROCESS_PER_MONITOR_DPI_AWARE
        shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

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

def hide_console():
    """隐藏当前控制台窗口（脚本模式启动时使用）。"""
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # 0 = SW_HIDE
            logging.info("已隐藏控制台窗口")
    except Exception as e:
        logging.warning(f"隐藏控制台窗口失败: {e}")

# 在脚本模式下自动隐藏控制台（可通过设置环境变量 RC_NO_HIDE=1 禁用）
if is_script_mode and os.environ.get("RC_NO_HIDE") != "1":
    hide_console()

# 若开启测试模式，在非脚本模式下同样清空旧日志，保持与脚本一致
try:
    # 配置文件位于当前程序目录
    appdata_dir_cfg = os.path.abspath(os.path.dirname(sys.argv[0]))
    config_path = os.path.join(appdata_dir_cfg, "config.json")
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            _cfg = None
            try:
                import json
                _cfg = json.load(f)
            except Exception:
                _cfg = None
        if _cfg and _cfg.get('test') == 1 and not is_script_mode:
            with open(tray_log_path, 'w', encoding='utf-8') as f:
                f.write('')
            logging.info(f"测试模式启用，已清空日志文件: {tray_log_path}")
            print(f"测试模式启用，已清空日志文件: {tray_log_path}")
except Exception as e:
    logging.error(f"测试模式清空日志失败: {e}")

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

def resource_path(relative_path: str) -> str:
    """返回资源文件的实际路径。
    兼容 PyInstaller(_MEIPASS) 与 Nuitka(onefile 临时解包目录/可执行目录)。
    """
    bases: list[str] = []
    # PyInstaller 提取目录
    if hasattr(sys, "_MEIPASS"):
        try:
            bases.append(getattr(sys, "_MEIPASS"))  # type: ignore[attr-defined]
        except Exception:
            pass
    # Nuitka/通用：当前文件所在目录（onefile 场景下通常为临时解包目录）
    try:
        bases.append(os.path.abspath(os.path.dirname(__file__)))
    except Exception:
        pass
    # 可执行文件所在目录（作为兜底）
    try:
        bases.append(os.path.abspath(os.path.dirname(sys.executable)))
    except Exception:
        pass
    # 当前工作目录（最后兜底）
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

def _find_first_existing(paths:list[str]) -> str | None:
    """在候选路径中返回第一个存在的文件路径。"""
    for p in paths:
        try:
            if p and os.path.exists(p):
                return p
        except Exception:
            continue
    return None

def _open_url(url: str) -> None:
    try:
        webbrowser.open_new_tab(url)
    except Exception as e:
        logging.error(f"打开链接失败: {e}")
        notify(f"无法打开链接:\n{url}", level="error", show_error=True)

def _parse_version_tuple(v: str) -> tuple:
    """将 'V2.2.2' / 'v2.3' / '2.3.1' 转为可比较的元组，例如 (2,3,1)。未匹配则返回空元组。"""
    try:
        nums = [int(x) for x in re.findall(r"\d+", v or "")]
        return tuple(nums)
    except Exception:
        return tuple()

def _compare_versions(a: str, b: str) -> int:
    """比较两个版本字符串。a<b 返回 -1，a==b 返回 0，a>b 返回 1。
    特殊处理：当a包含'未知版本'时，始终返回-1表示需要更新。"""
    # 特殊处理：未知版本始终认为需要更新
    if "未知版本" in a:
        return -1
    
    ta = list(_parse_version_tuple(a))
    tb = list(_parse_version_tuple(b))
    # 对齐长度
    n = max(len(ta), len(tb))
    ta += [0] * (n - len(ta))
    tb += [0] * (n - len(tb))
    if ta < tb:
        return -1
    if ta > tb:
        return 1
    return 0

def _check_latest_release(timeout: float = 2.5) -> tuple[str, str | None]:
    """
    访问 GitHub Releases API 获取最新 tag_name。
    返回 (status, latest_tag)；status 为 'ok'/'error'，latest_tag 可能为 None。
    """
    try:
        req = urllib.request.Request(
            GITHUB_RELEASES_LATEST_API,
            headers={
                "User-Agent": f"RC-tray/{BANBEN}",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return ("error", None)
            data = json.loads(resp.read().decode("utf-8", errors="ignore") or "{}")
            tag = data.get("tag_name") or data.get("name")
            if isinstance(tag, str) and tag.strip():
                return ("ok", tag.strip())
            return ("error", None)
    except Exception as e:
        logging.warning(f"检查更新失败: {e}")
        return ("error", None)

def _update_menu_after_version_check():
    """版本检查完成后更新托盘菜单"""
    global icon
    if 'icon' in globals() and icon:
        try:
            # 重新生成菜单项
            new_menu_items = get_menu_items()
            new_menu = pystray.Menu(*new_menu_items)
            # 更新托盘图标的菜单
            icon.menu = new_menu
            logging.info("已更新托盘菜单显示最新版本检查结果")
        except Exception as e:
            logging.error(f"更新托盘菜单失败: {e}")

# 版本菜单点击：打开项目主页，同时在后台检查更新并提示结果
def on_version_click(icon=None, item=None):
    try:
        _open_url("https://github.com/chen6019/Remote-Controls")
    finally:
        def _bg_check():
            global _version_check_cache
            # 标记正在检查
            _version_check_cache["status"] = "checking"
            _version_check_cache["latest"] = None
            _version_check_cache["checked_time"] = time.time()
            
            # 更新菜单显示"检查中"状态
            _update_menu_after_version_check()
            
            # 执行实际检查
            status, latest = _check_latest_release()
            
            # 更新缓存
            _version_check_cache["status"] = status
            _version_check_cache["latest"] = latest
            _version_check_cache["checked_time"] = time.time()
            
            # 更新菜单显示检查结果
            _update_menu_after_version_check()
            
            # 显示通知
            if status == "ok" and latest:
                cmp = _compare_versions(BANBEN, latest)
                if cmp < 0:
                    if "未知版本" in BANBEN:
                        notify(f"发现最新版本 {latest}，当前版本未知，建议更新。", level="info")
                    else:
                        notify(f"发现新版本 {latest}，当前 {BANBEN}。", level="info")
                elif cmp == 0:
                    notify(f"已是最新版本 {BANBEN}")
                else:
                    notify(f"当前版本 {BANBEN} 新于远端 {latest}")
            else:
                notify("检查更新失败", level="warning")
        threading.Thread(target=_bg_check, daemon=True).start()


def _open_random_egg_image() -> None:
    """异步、安全地打开随机图片 URL，减少浏览器启动偶发触发 CrashSender 的概率。

    策略：
    - 使用 ShellExecuteW 打开 URL（更接近用户双击行为，较 webbrowser.open 更少包装层）。
    - 失败时回退 webbrowser.open。
    - 加 1 秒节流，防止快速连点产生竞态。
    """
    remote_url = "https://rad.ysy.146019.xyz/bz"
    global _LAST_RANDOM_OPEN_TS
    now = time.time()
    if globals().get('_LAST_RANDOM_OPEN_TS') and now - _LAST_RANDOM_OPEN_TS < 1.0:
        notify("操作过快，稍后重试", level="warning")
        return
    _LAST_RANDOM_OPEN_TS = now

    def _worker():
        try:
            # 优先 ShellExecuteW
            try:
                SW_SHOWNORMAL = 1
                res = ctypes.windll.shell32.ShellExecuteW(None, 'open', remote_url, None, None, SW_SHOWNORMAL)
                if res <= 32:
                    logging.warning(f"ShellExecuteW 打开URL返回: {res}，回退 webbrowser")
                    raise RuntimeError(f"ShellExecuteW失败 {res}")
                logging.info(f"ShellExecuteW 打开随机图片: {remote_url} (ret={res})")
                notify("已打开随机图片", level="info")
                return
            except Exception as e1:
                logging.info(f"ShellExecuteW 失败: {e1}")
                # 回退 webbrowser
                try:
                    webbrowser.open(remote_url, new=2, autoraise=True)
                    logging.info(f"webbrowser.open 打开随机图片: {remote_url}")
                    notify("已打开随机图片", level="info")
                    return
                except Exception as e2:
                    logging.error(f"webbrowser 打开随机图片失败: {e2}")
                    notify("打开随机图片失败", level="error")
        except Exception as e:
            logging.error(f"随机图片打开线程异常: {e}")
    threading.Thread(target=_worker, daemon=True).start()

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

def run_py_in_venv_as_admin(python_exe_path:str, script_path:str, script_args=None, show_window:bool=True):
    """使用指定 Python 解释器提权运行脚本（直接调用，不经 cmd /c）。
    返回 ShellExecuteW 结果码 (>32 视为成功)。"""
    logging.info(f"执行函数: run_py_in_venv_as_admin；参数: {python_exe_path}, {script_path}")
    if not os.path.exists(python_exe_path):
        raise FileNotFoundError(f"Python 解释器未找到: {python_exe_path}")
    if script_args is None:
        script_args = []
    # 组装参数："script" arg1 arg2 ...
    params = ' '.join([f'"{script_path}"'] + [str(a) for a in script_args])
    workdir = os.path.dirname(script_path) or None
    show_cmd = 1 if show_window else 0
    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            'runas',
            python_exe_path,
            params,
            workdir,
            show_cmd
        )
        logging.info(f"ShellExecuteW 提权启动结果: {result}")
        return result
    except Exception as e:
        logging.error(f"提权启动脚本失败: {e}")
        return 0

# 兼容旧函数名（保留调用方，如仍有引用）
def run_py_in_venv_as_admin_hidden(python_exe_path, script_path, script_args=None):
    # 兼容旧调用：默认隐藏窗口
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
            # EXE模式：直接以管理员权限运行exe
            result = run_as_admin(current_exe)
        else:
            # 脚本模式：优先使用 pythonw.exe（若存在）以隐藏窗口提权启动
            base_dir = os.path.dirname(current_exe)
            pythonw = os.path.join(base_dir, 'pythonw.exe')
            interpreter = pythonw if os.path.exists(pythonw) else current_exe
            script_path = os.path.abspath(__file__)
            result = run_py_in_venv_as_admin(interpreter, script_path, show_window=False)

        if result > 32:
            logging.info(f"成功以管理员权限重启程序，ShellExecute 返回值: {result}")
            # 等待新进程出现（最多 5s）再退出当前进程，避免用户感知“直接退出”
            if not getattr(sys, "frozen", False):
                target = os.path.abspath(__file__)
                found = False
                for _ in range(50):  # 50 * 0.1s = 5s
                    try:
                        for proc in psutil.process_iter(['name','cmdline']):
                            if not proc.info.get('cmdline'):
                                continue
                            cmdline_join = ' '.join(proc.info['cmdline'])
                            if 'python' in proc.info['name'].lower() and target in cmdline_join and proc.pid != os.getpid():
                                found = True
                                break
                        if found:
                            break
                    except Exception:
                        pass
                    time.sleep(0.1)
                logging.info(f"提权后新脚本进程检测结果: {'已发现' if found else '未发现'}")
            logging.info("退出当前非管理员进程，交由新进程继续运行")
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

def open_gui():
    """打开配置界面

    逻辑说明：
    - 通过菜单项点击打开。
    """
    logging.info("执行函数: open_gui")
    try:
        if os.path.exists(GUI_EXE):
            subprocess.Popen([GUI_EXE])
            logging.info(f"打开配置界面: {GUI_EXE}")
        elif os.path.exists(GUI_PY):
            logging.info(f"打开配置界面: {GUI_PY}")
            subprocess.Popen([sys.executable, GUI_PY])
        else:
            logging.error(f"未找到配置界面: {GUI_EXE} 或 {GUI_PY}")
            notify("未找到配置界面")
    except Exception as e:
        logging.error(f"打开配置界面出现异常: {e}")
        notify(f"打开配置界面失败: {e}", level="error")

APP_NOTIFY_NAME = "远程控制托盘"
_ICON_CANDIDATES = [
    ICON_FILE,
    "icon.ico",
    os.path.join("res", "icon.ico"),
]
ICON_NOTIFY_PATH = None
for _p in _ICON_CANDIDATES:
    try:
        rp = resource_path(_p)
        if rp and os.path.exists(rp):
            ICON_NOTIFY_PATH = rp
            break
    except Exception:
        pass

_SCALED_NOTIFY_ICON = None

def _prepare_scaled_icon(scale: float = 0.7) -> str | None:
    """生成带透明留白的缩放图标，减少被裁切、显得过大的问题。只生成一次缓存。"""
    global _SCALED_NOTIFY_ICON
    if _SCALED_NOTIFY_ICON:
        return _SCALED_NOTIFY_ICON
    if not ICON_NOTIFY_PATH:
        return None
    try:
        from PIL import Image as _PILImage
        base = _PILImage.open(ICON_NOTIFY_PATH)
        # 取最大边，生成 64x64 画布
        canvas_size = 64
        # 计算缩放后尺寸（保持比例）
        max_edge = max(base.size)
        target_edge = max(16, int(canvas_size * scale))
        ratio = target_edge / float(max_edge)
        new_size = (max(1, int(base.size[0]*ratio)), max(1, int(base.size[1]*ratio)))
        base = base.resize(new_size, _PILImage.LANCZOS)
        canvas = _PILImage.new("RGBA", (canvas_size, canvas_size), (0,0,0,0))
        off = ((canvas_size - new_size[0])//2, (canvas_size - new_size[1])//2)
        canvas.paste(base, off, base if base.mode in ("RGBA","LA") else None)
        import tempfile, hashlib
        h = hashlib.md5((ICON_NOTIFY_PATH+str(scale)).encode('utf-8')).hexdigest()[:8]
        out_path = os.path.join(tempfile.gettempdir(), f"rc_toast_icon_{h}.png")
        canvas.save(out_path, "PNG")
        _SCALED_NOTIFY_ICON = out_path
        return out_path
    except Exception as e:
        logging.warning(f"缩放通知图标失败，使用原图: {e}")
        return ICON_NOTIFY_PATH

def notify(msg, level="info", show_error=False, title: str | None = None, unique: bool = True, mode: str = "replace"):
    """发送系统通知并记录日志，统一显示为应用名而不是 python。

    参数:
    - msg: 通知内容
    - level: info/warning/error/critical
    - show_error: 通知失败时是否弹出消息框
    - title: 自定义标题（默认使用 APP_NOTIFY_NAME）
    """
    log_func = getattr(logging, level.lower(), logging.info)
    log_func(f"通知: {msg}")

    t_title = title or APP_NOTIFY_NAME

    def _show_toast_in_thread():
        try:
            icon_use = _prepare_scaled_icon()
            icon_param = None
            if icon_use:
                icon_param = {"src": icon_use, "placement": "appLogoOverride", "hint-crop": "none"}
            tag = group = None
            if mode == "replace":
                # 固定 tag/group，实现覆盖
                tag = "rc_live"
                group = "rc_live_group"
                try:
                    clear_toast(app_id=APP_NOTIFY_NAME, tag=tag, group=group)
                except Exception:
                    pass
            elif unique:
                now_ms = int(time.time()*1000)
                tag = f"t{now_ms%1000000}"
                group = "rc_fast"
            # 正确参数形式：title= 标题, body= 内容, app_id= 自定义应用名
            if icon_param:
                toast(title=t_title, body=msg, app_id=APP_NOTIFY_NAME, icon=icon_param, tag=tag, group=group)
            else:
                toast(title=t_title, body=msg, app_id=APP_NOTIFY_NAME, tag=tag, group=group)
        except TypeError:
            # 旧版本可能不支持 body 关键字（不大可能），尝试最简降级
            try:
                icon_use = _prepare_scaled_icon()
                if icon_use:
                    toast(t_title, msg, app_id=APP_NOTIFY_NAME, icon={"src": icon_use, "placement": "appLogoOverride", "hint-crop": "none"})
                else:
                    toast(t_title, msg, app_id=APP_NOTIFY_NAME)
            except Exception:
                try:
                    icon_use = _prepare_scaled_icon()
                    if icon_use:
                        toast(t_title, msg, icon={"src": icon_use, "placement": "appLogoOverride", "hint-crop": "none"})
                    else:
                        toast(t_title, msg)
                except Exception as e:
                    logging.error(f"发送通知失败: {e}")
                    if show_error:
                        try:
                            messagebox.showinfo(t_title, msg)
                        except Exception:
                            pass
                    else:
                        try:
                            print(f"[{t_title}] {msg}")
                        except Exception:
                            pass
        except Exception as e:
            logging.error(f"发送通知失败: {e}")
            if show_error:
                try:
                    messagebox.showinfo(t_title, msg)
                except Exception:
                    pass
            else:
                try:
                    print(f"[{t_title}] {msg}")
                except Exception:
                    pass

    th = threading.Thread(target=_show_toast_in_thread, daemon=True)
    th.start()

def close_script(script_name, skip_admin: bool = False):
    """关闭脚本函数（按名字匹配 python.exe/pythonw.exe 中的命令行）。"""
    logging.info(f"执行函数: close_script; 参数: {script_name}")
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        if is_admin or skip_admin:
            logging.info(f"尝试关闭脚本: {script_name}")
            cmd_find = 'tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH'
            output = subprocess.check_output(cmd_find, shell=True).decode('utf-8', errors='ignore')
            target_pids: list[str] = []
            for line in output.splitlines():
                if script_name in line:
                    parts = line.replace('"', '').split(',')
                    if len(parts) > 1:
                        pid = parts[1].strip()
                        target_pids.append(pid)
            for pid in target_pids:
                try:
                    subprocess.run(
                        f'taskkill /F /PID {pid}',
                        shell=True,
                        check=True,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    logging.info(f"已终止进程 PID: {pid}")
                except subprocess.CalledProcessError:
                    logging.warning(f"无法终止进程 PID: {pid}")
        else:
            notify(f"当前用户没有管理员权限，无法关闭脚本{script_name}", level="warning")
    except FileNotFoundError:
        notify(f"未找到脚本文件: {script_name}", level="error", show_error=True)
    except Exception as e:
        logging.error(f"关闭脚本{script_name}时出错: {e}")

def close_exe(name: str, skip_admin: bool = False):
    """关闭指定 exe 进程（按名称）。"""
    logging.info(f"执行函数: close_exe; 参数: {name}")
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        if is_admin or skip_admin:
            script_content = f"""
            @echo off
            taskkill /im "{name}" /f
            exit /b 0
            """
            temp_script = os.path.join(os.environ.get('TEMP', '.'), f'_rc_kill_{name}.bat')
            with open(temp_script, 'w', encoding='utf-8') as f:
                f.write(script_content)
            r = ctypes.windll.shell32.ShellExecuteW(None, 'runas', 'cmd.exe', f'/c "{temp_script}"', None, 0)
            if r <= 32:
                notify(f"结束进程 {name} 失败，错误码: {r}", level='error')
        else:
            notify(f"当前用户没有管理员权限，无法关闭进程 {name}", level='warning')
    except Exception as e:
        logging.error(f"关闭{name}进程时出错: {e}")

def stop_tray():
    """关闭托盘程序"""
    logging.info("执行函数: stop_tray")
    logging.info("="*30)
    logging.info("正在关闭托盘程序")
    # 判断主程序是否正在运行
    try:
        running = is_main_running()
    except Exception as e:
        logging.error(f"检测主程序运行状态失败: {e}")
        running = False

    if not running:
        # 主程序未运行 -> 仅退出托盘，不启动主程序
        logging.info("主程序未运行，仅退出托盘，不启动主程序")
        if 'icon' in globals() and icon:
            try:
                icon.stop()
                logging.info("托盘图标已停止")
            except Exception as e:
                logging.error(f"停止托盘图标时出错: {e}")
        threading.Timer(0.3, lambda: os._exit(0)).start()
        return

    # 主程序已在运行，沿用原逻辑：重启主程序再退出托盘
    logging.info("托盘程序退出，将重启主程序并退出托盘（主程序当前已运行）")

    def exit_after_restart():
        logging.info("主程序重启完成，现在可以安全退出托盘")
        if 'icon' in globals() and icon:
            try:
                icon.stop()
                logging.info("托盘图标已停止")
            except Exception as e:
                logging.error(f"停止托盘图标时出错: {e}")
        threading.Timer(0.5, lambda: os._exit(0)).start()

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
    global IS_TRAY_ADMIN, _version_check_cache
    admin_status = "【已获得管理员权限】" if IS_TRAY_ADMIN else "【未获得管理员权限】"
    
    # 版本菜单文本（使用缓存的检查结果）
    version_text = f"版本-{BANBEN}"
    if not is_script_mode:
        cache_status = _version_check_cache.get("status", "pending")
        cached_latest = _version_check_cache.get("latest")
        
        if cache_status == "checking":
            version_text = f"版本-{BANBEN}（检查中...）"
        elif cache_status == "ok" and cached_latest:
            cmp = _compare_versions(BANBEN, cached_latest)
            if cmp < 0:
                if "未知版本" in BANBEN:
                    version_text = f"版本-{BANBEN}（发现版本 {cached_latest}）"
                else:
                    version_text = f"版本-{BANBEN}（发现新版本 {cached_latest}）"
            else:
                version_text = f"版本-{BANBEN}（已是最新）"
        elif cache_status == "error":
            version_text = f"版本-{BANBEN}（检查失败）"
        # 如果是"pending"状态，保持默认显示
    
    items = [
        # 版本点击 -> 打开项目主页并后台检查更新
        pystray.MenuItem(version_text, on_version_click),
        # 托盘状态点击 -> 打开彩蛋随机图片（cd1~cd5.*）
        pystray.MenuItem(f"托盘状态: {admin_status}", lambda icon, item: _open_random_egg_image()),
    ]

    # 脚本模式提示（仅脚本模式显示）
    if is_script_mode:
        # disabled 状态：使用一个空的回调函数并设置 default=False
        items.append(pystray.MenuItem("当前运行方式：脚本模式", lambda icon, item: None, enabled=False))
        

    # 其他功能菜单项
    items.extend([
        pystray.MenuItem("打开配置界面", open_gui),
        pystray.MenuItem("检查主程序管理员权限", check_admin),
        pystray.MenuItem("启动主程序", is_admin_start_main),
        pystray.MenuItem("重启主程序", lambda icon, item: restart_main(icon, item)),
        pystray.MenuItem("关闭主程序", close_main),
        pystray.MenuItem("退出托盘（使用主程序自带托盘）", lambda icon, item: stop_tray()),
    ])

    return items

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

# 进程级 DPI 感知（提升托盘菜单/提示在高DPI显示的清晰度）
try:
    _enable_dpi_awareness()
except Exception:
    pass

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
