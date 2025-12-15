/**
 * rc_utils.c - 远程控制工具通用函数库实现
 *
 * 模块职责（方案B）：
 * - 抽象“托盘/主程序都会用到”的 Win32 通用操作，降低重复代码与行为分歧：
 *   - UAC 提权启动（ShellExecuteExW + verb="runas"）
 *   - 进程运行检测（进程名扫描 + 可选互斥体检测）
 *   - 启动外部程序（普通权限 CreateProcessW / 管理员权限 runas）
 *   - 关闭/重启主程序（taskkill，必要时先提权）
 *   - 读取主程序的管理员状态文件（logs\admin_status.txt）并给出通知
 *
 * 文本编码约定：
 * - 对外参数通常为 UTF-8（便于 JSON/日志与跨模块传递）。
 * - 调用 Win32 宽字符 API 时在内部转换为 UTF-16（W 系列 API）。
 *
 * 回调约定：
 * - LogFunction：用于输出日志（例如 tray.c 的 LogMessage）。
 * - NotifyFunction：用于 UI 提示（托盘气泡、弹窗等）。
 *   rc_utils 本身不直接依赖具体 UI，只通过回调让上层决定如何展示。
 */

#include "rc_utils.h"
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <process.h>
#include <direct.h>
#include <shlwapi.h>
#include <psapi.h>
#include <time.h>
#include <tlhelp32.h>
#include <stdarg.h>
#include <string.h>
#include <wchar.h>

static BOOL RC_Utf8ToWide(const char *src, wchar_t *dst, int dstCount)
{
    // UTF-8 -> UTF-16（Windows 宽字符）转换。
    // 约定：
    // - src 为 NULL 视为“空字符串”，返回 TRUE。
    // - dstCount 包含结尾 '\0' 的容量。
    if (!dst || dstCount <= 0)
        return FALSE;
    dst[0] = L'\0';
    if (!src)
        return TRUE;
    int n = MultiByteToWideChar(CP_UTF8, 0, src, -1, dst, dstCount);
    return n > 0;
}

static BOOL RC_WideToUtf8(const wchar_t *src, char *dst, int dstCount)
{
    // UTF-16 -> UTF-8 转换。
    // 主要用于：将 Process32 枚举到的 exe 名从宽字符转换为日志可读的 UTF-8。
    if (!dst || dstCount <= 0)
        return FALSE;
    dst[0] = '\0';
    if (!src)
        return TRUE;
    int n = WideCharToMultiByte(CP_UTF8, 0, src, -1, dst, dstCount, NULL, NULL);
    return n > 0;
}

// 统一的管理员权限执行 cmd.exe /c ...
//
// 说明：
// - 通过 ShellExecuteExW("runas") 触发 UAC。
// - cmdParams 需要包含 "/c ..." 等参数；调用方可以控制 show（SW_HIDE 等）。
// - 该函数仅负责发起进程；不等待执行完成。
BOOL RC_AdminRunCmd(const char *cmdParams, int show)
{
    SHELLEXECUTEINFOW sei = {0};
    sei.cbSize = sizeof(SHELLEXECUTEINFOW);
    sei.lpVerb = L"runas";
    sei.lpFile = L"cmd.exe";

    wchar_t paramsW[4096];
    if (!RC_Utf8ToWide(cmdParams, paramsW, (int)(sizeof(paramsW) / sizeof(paramsW[0]))))
        return FALSE;
    sei.lpParameters = paramsW;
    sei.nShow = show;
    sei.fMask = SEE_MASK_NOCLOSEPROCESS;

    if (!ShellExecuteExW(&sei))
    {
        return FALSE;
    }
    if (sei.hProcess)
    {
        CloseHandle(sei.hProcess);
    }
    return TRUE;
}

// 以管理员权限运行指定可执行文件
//
// 与 RC_AdminRunCmd 的区别：
// - 这里直接以 exeW 为 lpFile 启动目标程序，而不是 cmd.exe。
BOOL RC_AdminRunExecutable(const char *exePath, const char *parameters, int show)
{
    SHELLEXECUTEINFOW sei = {0};
    sei.cbSize = sizeof(SHELLEXECUTEINFOW);
    sei.lpVerb = L"runas";

    wchar_t exeW[MAX_PATH];
    wchar_t paramsW[4096];
    if (!RC_Utf8ToWide(exePath, exeW, MAX_PATH))
        return FALSE;
    if (!RC_Utf8ToWide(parameters, paramsW, (int)(sizeof(paramsW) / sizeof(paramsW[0]))))
        return FALSE;

    sei.lpFile = exeW;
    sei.lpParameters = paramsW;
    sei.nShow = show;
    sei.fMask = SEE_MASK_NOCLOSEPROCESS;

    if (!ShellExecuteExW(&sei))
    {
        return FALSE;
    }
    if (sei.hProcess)
    {
        CloseHandle(sei.hProcess);
    }
    return TRUE;
}

// 以管理员权限执行 taskkill 关闭指定进程
//
// 注意：
// - 使用 taskkill /F 会强制终止进程，可能导致未保存数据丢失。
// - 托盘侧在“关闭主程序/重启主程序”时，会按需求选择是否走该路径。
BOOL RC_AdminTaskkill(const char *processName)
{
    char cmdLine[MAX_PATH];
    sprintf_s(cmdLine, sizeof(cmdLine), "taskkill /im %s /f", processName);
    char params[MAX_PATH * 2];
    sprintf_s(params, sizeof(params), "/c %s", cmdLine);
    return RC_AdminRunCmd(params, SW_HIDE);
}

/**
 * 检查当前进程是否具有管理员权限（是否已提升）
 *
 * 实现：
 * - OpenProcessToken + GetTokenInformation(TokenElevation)
 * - TokenIsElevated=1 表示当前进程处于提升态（UAC 已通过）。
 */
BOOL RC_IsUserAdmin(void)
{
    BOOL isAdmin = FALSE;
    HANDLE hToken = NULL;

    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &hToken))
    {
        TOKEN_ELEVATION elevation;
        DWORD cbSize = sizeof(TOKEN_ELEVATION);

        if (GetTokenInformation(hToken, TokenElevation, &elevation, sizeof(elevation), &cbSize))
        {
            isAdmin = elevation.TokenIsElevated;
        }

        CloseHandle(hToken);
    }

    return isAdmin;
}

/**
 * 检查指定的程序是否正在运行
 *
 * 策略（双通道）：
 * 1) 进程快照扫描：CreateToolhelp32Snapshot + Process32First/Next，比较 exe 文件名。
 * 2) 互斥体检测（可选）：若提供 mutexName，则尝试 OpenMutexW。
 *
 * 设计动机：
 * - 仅靠进程名：在极端情况下可能误判（同名不同路径）、或主进程尚未出现在快照时漏判。
 * - 增加互斥体：当主程序创建了稳定的互斥体（例如 "RC-main"），可提高准确性。
 */
BOOL RC_IsProcessRunning(const char *processName, const char *mutexName, LogFunction logFunc, const char *logMsgFound,
                         const char *logMsgFoundMutex, const char *logMsgNotFound)
{
    // 方法1：通过进程名检查
    HANDLE hSnapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (hSnapshot == INVALID_HANDLE_VALUE)
    {
        if (logFunc)
            logFunc("ERROR", "Failed to create process snapshot");
        return FALSE;
    }

    PROCESSENTRY32W pe32;
    pe32.dwSize = sizeof(PROCESSENTRY32W);

    wchar_t processNameW[MAX_PATH];
    if (!RC_Utf8ToWide(processName, processNameW, MAX_PATH))
    {
        CloseHandle(hSnapshot);
        return FALSE;
    }

    BOOL isRunning = FALSE;

    // 检查可执行文件版本
    if (Process32FirstW(hSnapshot, &pe32))
    {
        do
        {
            if (_wcsicmp(pe32.szExeFile, processNameW) == 0)
            {
                isRunning = TRUE;
                if (logFunc)
                {
                    char exeUtf8[MAX_PATH * 3] = {0};
                    RC_WideToUtf8(pe32.szExeFile, exeUtf8, (int)sizeof(exeUtf8));
                    logFunc("INFO", logMsgFound, exeUtf8[0] ? exeUtf8 : processName);
                }
                break;
            }
        } while (Process32NextW(hSnapshot, &pe32));
    }

    CloseHandle(hSnapshot);

    // 如果通过进程名已确认在运行，直接返回
    if (isRunning)
    {
        return TRUE;
    }

    // 方法2：通过互斥体检查
    if (mutexName != NULL && mutexName[0] != '\0')
    {
        wchar_t mutexNameW[256];
        if (!RC_Utf8ToWide(mutexName, mutexNameW, (int)(sizeof(mutexNameW) / sizeof(mutexNameW[0]))))
        {
            if (logFunc)
                logFunc("INFO", logMsgNotFound);
            return FALSE;
        }
        HANDLE hMutex = OpenMutexW(MUTEX_ALL_ACCESS, FALSE, mutexNameW);
        if (hMutex)
        {
            if (logFunc)
                logFunc("INFO", logMsgFoundMutex, mutexName);
            CloseHandle(hMutex);
            return TRUE;
        }
    }

    if (logFunc)
        logFunc("INFO", logMsgNotFound);
    return FALSE;
}

/**
 * 以管理员权限启动程序（触发 UAC 提示）
 *
 * 重要约定：
 * - 返回 TRUE 表示“成功发起了提升启动”（不代表子进程已完成初始化）。
 * - ERROR_CANCELLED 表示用户在 UAC 对话框中取消。
 *
 * UI 与日志：
 * - 通过 notifyFunc 将“用户取消/启动失败”等信息反馈给上层（托盘气泡/弹窗）。
 * - 通过 logFunc 输出更详细的错误码（GetLastError）。
 */
BOOL RC_RunAsAdmin(const char *exePath, LogFunction logFunc,
                   const char *logMsgAttempt, const char *logMsgCancelled,
                   const char *logMsgStartFailed, const char *logMsgStartSuccess,
                   NotifyFunction notifyFunc, const char *promptTitle,
                   const char *userCancelledUAC, const char *errorPromptTitle,
                   const char *startFailed)
{
    SHELLEXECUTEINFOW sei = {0};

    sei.cbSize = sizeof(SHELLEXECUTEINFOW);
    sei.lpVerb = L"runas";

    wchar_t exeW[MAX_PATH];
    if (!RC_Utf8ToWide(exePath, exeW, MAX_PATH))
        return FALSE;

    sei.lpFile = exeW;
    sei.nShow = SW_HIDE;
    sei.fMask = SEE_MASK_NOCLOSEPROCESS;

    if (logFunc)
        logFunc("INFO", logMsgAttempt, exePath);

    if (!ShellExecuteExW(&sei))
    {
        DWORD error = GetLastError();
        if (error == ERROR_CANCELLED)
        {
            if (logFunc)
                logFunc("WARNING", logMsgCancelled);
            if (notifyFunc)
                notifyFunc(promptTitle, userCancelledUAC);
        }
        else
        {
            if (logFunc)
                logFunc("ERROR", logMsgStartFailed, error);
            if (notifyFunc)
                notifyFunc(errorPromptTitle, startFailed);
        }
        return FALSE;
    }

    if (sei.hProcess)
    {
        CloseHandle(sei.hProcess);
    }
    if (logFunc)
        logFunc("INFO", logMsgStartSuccess);
    return TRUE;
}

/**
 * 启动程序（通用函数，可用于启动主程序或 GUI 等）
 *
 * 行为概览：
 * - 若提供 isRunningFunc 且检测为“已运行”，则提示并返回。
 * - 若 exe 不存在（PathFileExistsW 失败），提示“文件不存在”。
 * - useAdminRights=TRUE：使用 RC_RunAsAdmin 触发 UAC 提升启动。
 * - useAdminRights=FALSE：使用 CreateProcessW 以当前权限启动（隐藏窗口）。
 *
 * 注意：
 * - CreateProcessW 的第二参数为命令行，这里传 NULL 表示不附带参数。
 * - RC_RunAsAdmin 内部使用 ShellExecuteExW，并不会等待子进程运行结束。
 */
void RC_StartProgram(const char *exePath, BOOL (*isRunningFunc)(void),
                     LogFunction logFunc, NotifyFunction notifyFunc,
                     const char *logMsgFuncName, const char *logMsgAlreadyRunning,
                     const char *logMsgStartSuccess, const char *logMsgStartFailed,
                     const char *logMsgNotExists, const char *promptTitle,
                     const char *notifyAlreadyRunning, const char *startingMsg,
                     const char *errorPromptTitle, const char *notExistsMsg,
                     BOOL useAdminRights)
{
    if (logFunc)
        logFunc("INFO", logMsgFuncName);

    // 如果提供了检查函数，且程序已在运行，则提示并返回
    if (isRunningFunc && isRunningFunc())
    {
        if (logFunc)
            logFunc("INFO", logMsgAlreadyRunning);
        if (notifyFunc)
            notifyFunc(promptTitle, notifyAlreadyRunning);
        return;
    }

    // 检查可执行文件是否存在
    wchar_t exeW[MAX_PATH];
    if (!RC_Utf8ToWide(exePath, exeW, MAX_PATH))
    {
        if (logFunc)
            logFunc("ERROR", logMsgNotExists, exePath);
        if (notifyFunc)
            notifyFunc(errorPromptTitle, notExistsMsg);
        return;
    }

    if (PathFileExistsW(exeW))
    {
        if (notifyFunc && startingMsg)
            notifyFunc(promptTitle, startingMsg);

        if (useAdminRights)
        {
            // 以管理员权限启动程序（复用 RC_RunAsAdmin）
            if (!RC_RunAsAdmin(exePath, logFunc,
                               "Attempting to run as admin: %s", "UAC elevation was cancelled by the user",
                               "Failed to start process, error code: %d", "Successfully started program",
                               notifyFunc, promptTitle,
                               "用户取消了UAC提升权限请求", errorPromptTitle,
                               "启动失败"))
            {
                if (logFunc)
                    logFunc("ERROR", logMsgStartFailed);
                return;
            }
        }
        else
        {
            // 普通权限启动程序
            STARTUPINFOW si = {0};
            PROCESS_INFORMATION pi = {0};
            si.cb = sizeof(STARTUPINFOW);
            si.dwFlags = STARTF_USESHOWWINDOW;
            si.wShowWindow = SW_HIDE;

            if (CreateProcessW(exeW, NULL, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi))
            {
                CloseHandle(pi.hProcess);
                CloseHandle(pi.hThread);
            }
            else
            {
                if (logFunc)
                    logFunc("ERROR", "Failed to start process, error code: %d", GetLastError());
                if (notifyFunc)
                    notifyFunc(errorPromptTitle, "启动失败");
                if (logFunc)
                    logFunc("ERROR", logMsgStartFailed);
                return;
            }
        }

        if (logFunc)
            logFunc("INFO", logMsgStartSuccess);
    }
    else
    {
        if (logFunc)
            logFunc("ERROR", logMsgNotExists, exePath);
        if (notifyFunc)
            notifyFunc(errorPromptTitle, notExistsMsg);
    }
}

/**
 * 关闭程序
 */
void RC_CloseMainProgram(const char *processName, BOOL (*isRunningFunc)(void),
                         LogFunction logFunc, NotifyFunction notifyFunc,
                         const char *logMsgFuncName, const char *logMsgMainNotRunning,
                         const char *logMsgTaskkillCmd, const char *logMsgTaskkillExitCode,
                         const char *logMsgTaskkillFailed, const char *logMsgCloseRequested,
                         const char *promptTitle, const char *notifyMainNotRunning,
                         const char *errorPromptTitle, const char *closeFailed,
                         const char *closingMain)
{
    // 关闭主程序的统一实现：
    // - 组装 taskkill 命令：taskkill /im <processName> /f
    // - 若当前未提升：用 runas 启动 cmd.exe /c taskkill（触发 UAC）。
    // - 若已提升：直接 CreateProcessW 执行 taskkill，并等待最多 5 秒取退出码。
    if (logFunc)
        logFunc("INFO", logMsgFuncName);

    if (isRunningFunc && !isRunningFunc())
    {
        if (logFunc)
            logFunc("INFO", logMsgMainNotRunning);
        if (notifyFunc)
            notifyFunc(promptTitle, notifyMainNotRunning);
        return;
    }

    // 根据权限选择关闭方式：未提权则用 runas 执行 cmd 关闭
    char cmdLine[MAX_PATH];
    sprintf_s(cmdLine, sizeof(cmdLine), "taskkill /im %s /f", processName);
    if (logFunc)
        logFunc("INFO", logMsgTaskkillCmd, cmdLine);

    if (!RC_IsUserAdmin())
    {
        char params[MAX_PATH * 2];
        sprintf_s(params, sizeof(params), "/c %s", cmdLine);
        if (!RC_AdminRunCmd(params, SW_HIDE))
        {
            if (logFunc)
                logFunc("ERROR", logMsgTaskkillFailed, GetLastError());
            if (notifyFunc)
                notifyFunc(errorPromptTitle, closeFailed);
            return;
        }
    }
    else
    {
        wchar_t cmdW[MAX_PATH * 2];
        if (!RC_Utf8ToWide(cmdLine, cmdW, (int)(sizeof(cmdW) / sizeof(cmdW[0]))))
        {
            if (logFunc)
                logFunc("ERROR", logMsgTaskkillFailed, GetLastError());
            if (notifyFunc)
                notifyFunc(errorPromptTitle, closeFailed);
            return;
        }

        STARTUPINFOW si = {0};
        PROCESS_INFORMATION pi = {0};
        si.cb = sizeof(STARTUPINFOW);
        si.dwFlags = STARTF_USESHOWWINDOW;
        si.wShowWindow = SW_HIDE;
        if (CreateProcessW(NULL, cmdW, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi))
        {
            WaitForSingleObject(pi.hProcess, 5000);
            DWORD exitCode = 0;
            GetExitCodeProcess(pi.hProcess, &exitCode);
            if (logFunc)
                logFunc("INFO", logMsgTaskkillExitCode, exitCode);
            CloseHandle(pi.hProcess);
            CloseHandle(pi.hThread);
        }
        else
        {
            if (logFunc)
                logFunc("ERROR", logMsgTaskkillFailed, GetLastError());
            if (notifyFunc)
                notifyFunc(errorPromptTitle, closeFailed);
            return;
        }
    }

    if (logFunc)
        logFunc("INFO", logMsgCloseRequested);
    if (notifyFunc)
        notifyFunc(promptTitle, closingMain);
}

/**
 * 检查程序管理员权限状态
 */
void RC_CheckMainAdminStatus(const char *logsDir, BOOL (*isRunningFunc)(void),
                             LogFunction logFunc, NotifyFunction notifyFunc,
                             const char *logMsgFuncName, const char *promptTitle,
                             const char *notifyMainNotRunning, const char *adminCheckYes,
                             const char *adminCheckNo, const char *adminCheckUnknown,
                             const char *adminCheckReadError, const char *adminCheckFileNotExists)
{
    // 主程序管理员权限状态：由主程序写入 logs\admin_status.txt。
    // 该文件通常形如："admin=1" 或 "admin=0"。
    // 托盘读取后以通知形式反馈给用户。
    if (logFunc)
        logFunc("INFO", logMsgFuncName);

    if (isRunningFunc && !isRunningFunc())
    {
        if (notifyFunc)
            notifyFunc(promptTitle, notifyMainNotRunning);
        return;
    }

    // 检查状态文件
    char statusFile[MAX_PATH];
    sprintf_s(statusFile, MAX_PATH, "%s\\admin_status.txt", logsDir);

    wchar_t statusW[MAX_PATH];
    if (!RC_Utf8ToWide(statusFile, statusW, MAX_PATH))
    {
        if (notifyFunc)
            notifyFunc(promptTitle, adminCheckFileNotExists);
        return;
    }

    if (PathFileExistsW(statusW))
    {
        FILE *file = fopen(statusFile, "r");
        if (file)
        {
            char content[32] = {0};
            fgets(content, sizeof(content), file);
            fclose(file);

            if (strstr(content, "admin=1"))
            {
                if (notifyFunc)
                    notifyFunc(promptTitle, adminCheckYes);
            }
            else if (strstr(content, "admin=0"))
            {
                if (notifyFunc)
                    notifyFunc(promptTitle, adminCheckNo);
            }
            else
            {
                if (notifyFunc)
                    notifyFunc(promptTitle, adminCheckUnknown);
            }
        }
        else
        {
            if (notifyFunc)
                notifyFunc(promptTitle, adminCheckReadError);
        }
    }
    else
    {
        if (notifyFunc)
            notifyFunc(promptTitle, adminCheckFileNotExists);
    }
}

/**
 * 重启程序
 */
void RC_RestartMainProgram(const char *processName, const char *mainExePath,
                           BOOL (*isRunningFunc)(void),
                           LogFunction logFunc, NotifyFunction notifyFunc,
                           const char *logMsgFuncName, const char *restartingMainMsg,
                           const char *mainNotRunning, const char *promptTitle)
{
    // 重启策略：
    // 1) 若检测主程序在运行：先 taskkill 结束（必要时提权），再 Sleep(1000) 给系统收尾。
    // 2) 再以管理员权限启动主程序（RC_StartProgram, useAdminRights=TRUE）。
    //
    // 备注：这里的启动日志模板使用了一组通用英文字符串，
    // 上层（tray/main）如需完全本地化，可将这些模板也通过参数传入。
    if (logFunc)
        logFunc("INFO", logMsgFuncName);

    if (notifyFunc)
        notifyFunc(promptTitle, restartingMainMsg);

    // 先关闭程序
    // 如果程序未运行，则跳过关闭步骤，直接启动
    if (isRunningFunc && isRunningFunc())
    {
        char cmdLine[MAX_PATH];
        sprintf_s(cmdLine, sizeof(cmdLine), "taskkill /im %s /f", processName);
        if (logFunc)
            logFunc("INFO", "Executing command: %s", cmdLine);

        if (!RC_IsUserAdmin())
        {
            char params[MAX_PATH * 2];
            sprintf_s(params, sizeof(params), "/c %s", cmdLine);
            if (!RC_AdminRunCmd(params, SW_HIDE))
            {
                if (logFunc)
                    logFunc("ERROR", "Failed to execute taskkill, error code: %lu", GetLastError());
            }
        }
        else
        {
            wchar_t cmdW[MAX_PATH * 2];
            BOOL cmdOk = RC_Utf8ToWide(cmdLine, cmdW, (int)(sizeof(cmdW) / sizeof(cmdW[0])));

            STARTUPINFOW si = {0};
            PROCESS_INFORMATION pi = {0};
            si.cb = sizeof(STARTUPINFOW);
            si.dwFlags = STARTF_USESHOWWINDOW;
            si.wShowWindow = SW_HIDE;
            if (cmdOk && CreateProcessW(NULL, cmdW, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi))
            {
                WaitForSingleObject(pi.hProcess, 5000);
                CloseHandle(pi.hProcess);
                CloseHandle(pi.hThread);
                Sleep(1000);
            }
            else
            {
                if (logFunc)
                    logFunc("ERROR", "Failed to execute taskkill, error code: %lu", GetLastError());
            }
        }
    }
    else
    {
        if (logFunc)
            logFunc("INFO", mainNotRunning);
    }

    // 然后启动程序
    RC_StartProgram(mainExePath, NULL, logFunc, notifyFunc,
                    "Function: StartProgram", NULL,
                    "Program started successfully", "Failed to start program",
                    "Program does not exist", promptTitle,
                    NULL, NULL, "Error", "Program executable does not exist",
                    TRUE); // 使用管理员权限启动
}
