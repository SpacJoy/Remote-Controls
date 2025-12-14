/**
 * rc_utils.h - 远程控制工具通用函数库
 * 提供系统管理、进程控制和GUI交互等通用功能
 *
 * 编码约定：本库对外暴露的所有 const char* 字符串参数均按 UTF-8 解释。
 * 内部会按需转换为 UTF-16 并调用 Win32 的 W 系列 API，以兼容中文路径/中文提示。
 */

#ifndef RC_UTILS_H
#define RC_UTILS_H

#include <windows.h>
#include <stdbool.h>

// 回调函数类型定义
typedef void (*LogFunction)(const char *level, const char *format, ...);
typedef void (*NotifyFunction)(const char *title, const char *message);

// 检查当前进程是否具有管理员权限
// - 内部通常通过 shell32!IsUserAnAdmin 或 TokenElevated 等方式判断。
BOOL RC_IsUserAdmin(void);

// 以管理员权限运行 cmd.exe /c ...
// - cmdParams：传给 cmd.exe 的参数（例如 "/c taskkill /im ..."），UTF-8。
// - showWindow：是否显示窗口（SW_SHOW/SW_HIDE 等）。
// - 通常通过 ShellExecute("runas") 触发 UAC。
BOOL RC_AdminRunCmd(const char *cmdParams, int showWindow);

// 以管理员权限运行指定可执行文件
// - exePath：可执行文件路径（UTF-8），允许包含空格。
// - parameters：命令行参数（UTF-8，可为 NULL）。
// - showWindow：窗口显示方式。
BOOL RC_AdminRunExecutable(const char *exePath, const char *parameters, int showWindow);

// 以管理员权限执行 taskkill 关闭指定进程
// - processName：例如 "RC-main.exe"。
// - 通常等价于 taskkill /im <name> /f。
BOOL RC_AdminTaskkill(const char *processName);

// 检查指定的程序是否正在运行
// - processName：进程名（例如 "RC-main.exe"）。
// - mutexName：可选互斥体名（例如 "RC-main"），用于更可靠判断。
// - logFunc/logMsg*：用于记录日志（托盘侧传入）。
BOOL RC_IsProcessRunning(const char *processName, const char *mutexName, LogFunction logFunc, const char *logMsgFound,
                         const char *logMsgFoundMutex, const char *logMsgNotFound);

// 以管理员权限启动程序
// - 返回 TRUE 表示已成功发起提权启动（可能当前进程随后退出）。
// - 返回 FALSE 表示用户取消 UAC 或启动失败。
BOOL RC_RunAsAdmin(const char *exePath, LogFunction logFunc,
                   const char *logMsgAttempt, const char *logMsgCancelled,
                   const char *logMsgStartFailed, const char *logMsgStartSuccess,
                   NotifyFunction notifyFunc, const char *promptTitle,
                   const char *userCancelledUAC, const char *errorPromptTitle,
                   const char *startFailed);

// 启动程序 (通用函数，可用于启动主程序或GUI等)
// - useAdminRights=TRUE 时，内部会尝试以管理员权限启动（runas）。
void RC_StartProgram(const char *exePath, BOOL (*isRunningFunc)(void),
                     LogFunction logFunc, NotifyFunction notifyFunc,
                     const char *logMsgFuncName, const char *logMsgAlreadyRunning,
                     const char *logMsgStartSuccess, const char *logMsgStartFailed,
                     const char *logMsgNotExists, const char *promptTitle,
                     const char *notifyAlreadyRunning, const char *startingMsg,
                     const char *errorPromptTitle, const char *notExistsMsg,
                     BOOL useAdminRights);

// 关闭程序
// - 典型实现：taskkill（可根据是否提权走不同路径）。
void RC_CloseMainProgram(const char *processName, BOOL (*isRunningFunc)(void),
                         LogFunction logFunc, NotifyFunction notifyFunc,
                         const char *logMsgFuncName, const char *logMsgMainNotRunning,
                         const char *logMsgTaskkillCmd, const char *logMsgTaskkillExitCode,
                         const char *logMsgTaskkillFailed, const char *logMsgCloseRequested,
                         const char *promptTitle, const char *notifyMainNotRunning,
                         const char *errorPromptTitle, const char *closeFailed,
                         const char *closingMain);

// 重启程序
// - 通常流程：若在运行先结束 -> 等待 -> 再启动。
void RC_RestartMainProgram(const char *processName, const char *mainExePath,
                           BOOL (*isRunningFunc)(void),
                           LogFunction logFunc, NotifyFunction notifyFunc,
                           const char *logMsgFuncName, const char *restartingMainMsg,
                           const char *mainNotRunning, const char *promptTitle);

// 检查程序管理员权限状态
// - 通过读取 logsDir\admin_status.txt（由主程序写入）判断主程序是否以管理员运行。
void RC_CheckMainAdminStatus(const char *logsDir, BOOL (*isRunningFunc)(void),
                             LogFunction logFunc, NotifyFunction notifyFunc,
                             const char *logMsgFuncName, const char *promptTitle,
                             const char *notifyMainNotRunning, const char *adminCheckYes,
                             const char *adminCheckNo, const char *adminCheckUnknown,
                             const char *adminCheckReadError, const char *adminCheckFileNotExists);

#endif // RC_UTILS_H
