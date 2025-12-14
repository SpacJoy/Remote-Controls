/**
 * 远程控制托盘程序 - 日志信息实现
 * Remote Control Tray - Log Messages Implementation
 *
 * 设计目标（方案B）：
 * - 将“日志文案模板”集中管理，避免在 tray.c 中散落硬编码字符串。
 * - 日志文案与 UI 文案分离：
 *   - language.c/language.h：偏 UI 展示的字符串（菜单/提示/通知等）
 *   - log_messages.c/log_messages.h：偏开发/排障的日志模板（例如函数进入、错误码、进程检测结果）
 *
 * 初始化策略：
 * - `g_logMessages` 指向当前语言的静态常量表。
 * - `GetLogMessages()` 采用“懒初始化”：首次调用时根据当前语言初始化。
 *
 * 线程安全：
 * - 该模块没有锁；托盘主程序通常单线程调用，满足需求。
 *   若未来在后台线程也要切换语言并写日志，建议在外层做同步。
 */

#include "log_messages.h"
#include "language.h"
#include <stdio.h>

// 全局变量
// 指向“当前语言”的日志文案表；指向静态只读数据，整个进程生命周期有效。
static const LogMessages *g_logMessages = NULL;

// 中文日志消息
static const LogMessages g_chineseLogMessages = {
    // 应用程序启动相关
    .appStarted = "远程控制托盘程序启动",
    .appPath = "程序路径: %s",
    .systemInfo = "系统信息: Windows",
    .trayAdminStatus = "托盘程序管理员权限状态: %s",
    .adminYes = "已获得",
    .adminNo = "未获得",
    .mainPath = "主程序路径: %s",

    // 进程检查相关
    .createSnapshotFailed = "无法创建进程快照",
    .mainFound = "通过进程名找到主程序：%s",
    .mainFoundMutex = "通过互斥体 %s 发现主程序正在运行",
    .mainNotFound = "未发现主程序运行",

    // 图标加载相关
    .iconLoadedFile = "从文件加载图标: %s",
    .iconLoadFailed = "无法加载自定义图标，使用系统默认图标",
    .iconLoadedResource = "从资源加载图标成功",

    // 通知相关
    .notification = "通知: %s - %s",

    // 启动程序相关
    .runasAttempt = "尝试以管理员权限启动: %s",
    .uacCancelled = "用户取消了UAC提示",
    .startFailed = "启动程序失败，错误码: %lu",
    .startSuccess = "成功启动程序",

    // 函数执行和主程序管理相关
    .funcStartMain = "执行函数: StartMainProgram",
    .mainRunning = "主程序已在运行",
    .mainStartSuccess = "主程序启动成功",
    .mainStartFailed = "主程序启动失败",
    .mainNotExists = "主程序不存在: %s",
    .funcCloseMain = "执行函数: CloseMainProgram",
    .mainNotRunning = "主程序未在运行",
    .taskkillCommand = "执行命令: %s",
    .taskkillExitCode = "taskkill 退出代码: %lu",
    .taskkillFailed = "执行taskkill失败，错误码: %lu",
    .closeRequested = "已请求关闭主程序",
    .funcRestartMain = "执行函数: RestartMainProgram",

    // 配置界面相关
    .funcOpenConfig = "执行函数: OpenConfigGui",
    .configOpened = "成功打开配置界面",
    .configOpenFailed = "打开配置界面失败，错误码: %lu",
    .configNotExists = "配置界面不存在: %s",

    // 管理员权限检查相关
    .funcCheckAdmin = "执行函数: CheckMainAdminStatus",

    // UI相关
    .createMenuFailed = "无法创建菜单",
    .registerClassFailed = "注册窗口类失败",
    .createWindowFailed = "创建窗口失败", // 托盘启动和退出相关
    .trayStartNoMain = "托盘启动时未发现主程序运行，准备启动...",
    .trayStartMainRunning = "托盘启动时发现主程序正在运行",
    .initTrayFailed = "初始化托盘失败",
    .trayCreated = "托盘图标创建成功",
    .userRequestExit = "用户请求退出程序",
    .trayExit = "托盘程序正常退出"};

// 英文日志消息
static const LogMessages g_englishLogMessages = {
    // 应用程序启动相关
    .appStarted = "Remote Control Tray started",
    .appPath = "Program path: %s",
    .systemInfo = "System info: Windows",
    .trayAdminStatus = "Tray admin status: %s",
    .adminYes = "admin",
    .adminNo = "non-admin",
    .mainPath = "Main program path: %s",

    // 进程检查相关
    .createSnapshotFailed = "Failed to create process snapshot",
    .mainFound = "Found main program by process name: %s",
    .mainFoundMutex = "Found main program running by mutex %s",
    .mainNotFound = "Main program not running",

    // 图标加载相关
    .iconLoadedFile = "Loaded icon from file: %s",
    .iconLoadFailed = "Failed to load custom icon, using system default",
    .iconLoadedResource = "Successfully loaded icon from resource",

    // 通知相关
    .notification = "Notification: %s - %s",

    // 启动程序相关
    .runasAttempt = "Attempting to run with admin rights: %s",
    .uacCancelled = "User cancelled UAC prompt",
    .startFailed = "Failed to start program, error code: %lu",
    .startSuccess = "Successfully started program",

    // 函数执行和主程序管理相关
    .funcStartMain = "Function: StartMainProgram",
    .mainRunning = "Main program is already running",
    .mainStartSuccess = "Main program started successfully",
    .mainStartFailed = "Failed to start main program",
    .mainNotExists = "Main program does not exist: %s",
    .funcCloseMain = "Function: CloseMainProgram",
    .mainNotRunning = "Main program is not running",
    .taskkillCommand = "Executing command: %s",
    .taskkillExitCode = "Taskkill exit code: %lu",
    .taskkillFailed = "Failed to execute taskkill, error code: %lu",
    .closeRequested = "Close main program requested",
    .funcRestartMain = "Function: RestartMainProgram",

    // 配置界面相关
    .funcOpenConfig = "Function: OpenConfigGui",
    .configOpened = "Successfully opened configuration interface",
    .configOpenFailed = "Failed to open configuration interface, error code: %lu",
    .configNotExists = "Configuration interface does not exist: %s",

    // 管理员权限检查相关
    .funcCheckAdmin = "Function: CheckMainAdminStatus",

    // UI相关
    .createMenuFailed = "Failed to create menu",
    .registerClassFailed = "Failed to register window class",
    .createWindowFailed = "Failed to create window", // 托盘启动和退出相关
    .trayStartNoMain = "No main program running at tray startup, preparing to start...",
    .trayStartMainRunning = "Found main program running at tray startup",
    .initTrayFailed = "Failed to initialize tray",
    .trayCreated = "Tray icon created successfully",
    .userRequestExit = "User requested to exit program",
    .trayExit = "Tray program exited normally"};

/**
 * 获取当前语言的日志消息表
 *
 * 返回：
 * - 指向 `LogMessages` 的静态常量表（无需释放）。
 *
 * 约定：
 * - 若尚未调用 InitializeLogMessages()，这里会自动初始化，确保调用方始终拿到可用指针。
 */
const LogMessages *GetLogMessages(void)
{
    if (!g_logMessages)
    {
        // 如果尚未初始化，则调用初始化函数（懒初始化）
        InitializeLogMessages();
    }
    return g_logMessages;
}

/**
 * 初始化日志消息表
 *
 * 作用：
 * - 根据当前语言（GetCurrentLanguage）选择中文/英文日志模板表。
 *
 * 注意：
 * - 该函数只设置指针，不会复制字符串，也不会分配内存。
 */
void InitializeLogMessages(void)
{
    // 根据当前语言设置选择相应的日志消息
    Language currentLanguage = GetCurrentLanguage();

    if (currentLanguage == TRAY_LANG_ENGLISH)
    {
        g_logMessages = &g_englishLogMessages;
    }
    else
    {
        g_logMessages = &g_chineseLogMessages;
    }
}