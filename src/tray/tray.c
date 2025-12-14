/*
 * tray.c（外部托盘程序 RC-tray.exe）
 *
 * 主要职责：
 * 1) 提供系统托盘图标与右键菜单：打开配置、检查主程序权限、启动/重启/关闭主程序、切换语言、退出。
 * 2) 与主程序协作：
 *    - 通过进程/互斥体检测主程序是否在运行。
 *    - 通过读取 logs\admin_status.txt 判断主程序是否以管理员运行。
 * 3) 日志：写入 logs\tray.log
 *    - 以共享方式打开（CreateFileW + FILE_SHARE_READ|WRITE|DELETE），保证“托盘运行时日志文件可查看”。
 *    - 体积上限 200KB：写入前检查，达到/超过则先清空再写入。
 * 4) 在线版本检查：通过 WinHTTP 请求 GitHub releases/latest，解析 tag_name 并提示。
 *
 * 说明：对外的文本/路径参数多为 UTF-8；内部会按需转 UTF-16 调用 Win32 W 系列 API。
 */

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
#include <ctype.h>
#include <winhttp.h>
#include <io.h>
#include <fcntl.h>
#include "language.h"     // 添加语言支持头文件
#include "log_messages.h" // 添加日志消息头文件
#include "../rc_utils.h"  // 添加工具函数库头文件

// 版本信息：支持在编译时通过 -DRC_TRAY_VERSION=\"Vx.y.z\" 指定
#ifndef RC_TRAY_VERSION
#define RC_TRAY_VERSION "V0.0.0"
#endif
#define BANBEN RC_TRAY_VERSION
#define TRAY_ICON_ID 1
#define WM_TRAYICON (WM_USER + 1)
#define MUTEX_NAME "RC-main"

// 资源ID
#define IDI_TRAYICON 101

// 托盘菜单项ID
#define IDM_CONFIG 1001
#define IDM_CHECK_ADMIN 1002
#define IDM_START_MAIN 1003
#define IDM_RESTART_MAIN 1004
#define IDM_CLOSE_MAIN 1005
#define IDM_EXIT 1006
#define IDM_VERSION_INFO 1007
#define IDM_TRAY_STATUS 1008
#define IDM_SWITCH_LANG 1009

#define PROJECT_URL "https://github.com/spacjoy/Remote-Controls"
#define RANDOM_IMAGE_URL "https://rad.spacejoy.top/bz"
#define REPO_HOST L"api.github.com"
#define REPO_LATEST_PATH L"/repos/Spacjoy/Remote-Controls/releases/latest"

// 全局变量
HWND g_hWnd = NULL;
NOTIFYICONDATAW g_nid;
BOOL g_isTrayAdmin = FALSE;
char g_appDir[MAX_PATH];
char g_logsDir[MAX_PATH];
char g_mainExePath[MAX_PATH];
char g_guiExePath[MAX_PATH];
FILE *g_logFile = NULL;
const LanguageStrings *g_lang = NULL; // 语言字符串
const LogMessages *g_logMsg = NULL;   // 日志消息

#define TRAY_LOG_MAX_BYTES (200 * 1024)

static BOOL Utf8ToWide(const char *src, wchar_t *dst, int dstCount)
{
    if (!dst || dstCount <= 0)
        return FALSE;
    dst[0] = L'\0';
    if (!src)
        return TRUE;
    int n = MultiByteToWideChar(CP_UTF8, 0, src, -1, dst, dstCount);
    return n > 0;
}

static BOOL WideToUtf8(const wchar_t *src, char *dst, int dstCount)
{
    if (!dst || dstCount <= 0)
        return FALSE;
    dst[0] = '\0';
    if (!src)
        return TRUE;
    int n = WideCharToMultiByte(CP_UTF8, 0, src, -1, dst, dstCount, NULL, NULL);
    return n > 0;
}

/*
 * 以“可共享读取”的方式打开日志文件（追加）。
 *
 * 直接用 _wfopen_s 有时会导致其它程序无法在运行时读取该文件（表现为“日志文件无法查看/被占用”）。
 * 这里改用：
 * - CreateFileW(FILE_APPEND_DATA, FILE_SHARE_READ|WRITE|DELETE, OPEN_ALWAYS)
 *   允许记事本/编辑器在托盘运行时打开并读取。
 * - _open_osfhandle + _fdopen：把 Win32 HANDLE 转换为 CRT FILE*，以复用 fprintf/vfprintf。
 */
static FILE *OpenLogFileSharedAppendWEx(const wchar_t *pathW, DWORD *outLastError)
{
    if (outLastError)
        *outLastError = 0;
    if (!pathW || !pathW[0])
        return NULL;

    HANDLE h = CreateFileW(pathW,
                           FILE_APPEND_DATA,
                           FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                           NULL,
                           OPEN_ALWAYS,
                           FILE_ATTRIBUTE_NORMAL,
                           NULL);
    if (h == INVALID_HANDLE_VALUE)
    {
        if (outLastError)
            *outLastError = GetLastError();
        return NULL;
    }

    int fd = _open_osfhandle((intptr_t)h, _O_WRONLY | _O_APPEND | _O_TEXT);
    if (fd == -1)
    {
        CloseHandle(h);
        return NULL;
    }

    FILE *f = _fdopen(fd, "a");
    if (!f)
    {
        _close(fd);
        return NULL;
    }

    return f;
}

static BOOL EnsureDirW(const wchar_t *dirW)
{
    if (!dirW || !dirW[0])
        return FALSE;
    if (CreateDirectoryW(dirW, NULL))
        return TRUE;
    DWORD err = GetLastError();
    return err == ERROR_ALREADY_EXISTS;
}

static BOOL GetWritableTrayLogsDirW(wchar_t *outDirW, int outCount)
{
    if (!outDirW || outCount <= 0)
        return FALSE;
    outDirW[0] = L'\0';

    wchar_t baseW[MAX_PATH] = {0};
    DWORD n = GetEnvironmentVariableW(L"LOCALAPPDATA", baseW, MAX_PATH);
    if (n == 0 || n >= MAX_PATH)
    {
        DWORD tn = GetTempPathW(MAX_PATH, baseW);
        if (tn == 0 || tn >= MAX_PATH)
            return FALSE;
    }

    wchar_t dirW[MAX_PATH] = {0};
    wcsncpy_s(dirW, MAX_PATH, baseW, _TRUNCATE);

    // %LOCALAPPDATA%\Remote-Controls\logs
    if (!PathAppendW(dirW, L"Remote-Controls"))
        return FALSE;
    (void)EnsureDirW(dirW);

    if (!PathAppendW(dirW, L"logs"))
        return FALSE;
    (void)EnsureDirW(dirW);

    wcsncpy_s(outDirW, outCount, dirW, _TRUNCATE);
    return TRUE;
}

/*
 * 日志上限控制（200KB）：
 * - 写入前检查 _filelengthi64(fd)。
 * - 达到/超过上限时：fflush -> _chsize_s(fd,0) 清空 -> fseek(SEEK_END) 继续按追加写。
 */
static void TruncateLogIfNeeded(FILE *f)
{
    if (!f)
        return;
    int fd = _fileno(f);
    if (fd < 0)
        return;

    __int64 size = _filelengthi64(fd);
    if (size < 0)
        return;

    if (size >= TRAY_LOG_MAX_BYTES)
    {
        fflush(f);
        (void)_chsize_s(fd, 0);
        (void)fseek(f, 0, SEEK_END);
    }
}

static BOOL GetModuleDirUtf8(char *outDir, size_t outLen)
{
    if (!outDir || outLen == 0)
        return FALSE;
    outDir[0] = '\0';

    wchar_t fullPathW[MAX_PATH];
    DWORD n = GetModuleFileNameW(NULL, fullPathW, MAX_PATH);
    if (n == 0 || n >= MAX_PATH)
        return FALSE;

    wchar_t *lastSlash = wcsrchr(fullPathW, L'\\');
    if (lastSlash)
        *lastSlash = L'\0';

    char tmp[MAX_PATH * 3] = {0};
    if (!WideToUtf8(fullPathW, tmp, (int)sizeof(tmp)))
        return FALSE;

    strncpy_s(outDir, outLen, tmp, _TRUNCATE);
    return TRUE;
}

typedef enum
{
    VERSION_PENDING = 0,
    VERSION_CHECKING,
    VERSION_OK,
    VERSION_ERROR
} VersionStatus;

static volatile VersionStatus g_versionStatus = VERSION_PENDING;
static char g_latestVersion[64] = {0};
static time_t g_versionCheckedTime = 0;

// 函数声明
BOOL InitTray(HINSTANCE hInstance);
void LogMessage(const char *level, const char *format, ...);
void CreateTrayIcon(HWND hWnd);
void ShowNotificationDirect(const char *title, const char *message);
void ShowTrayNotification(const char *title, const char *message); // 添加函数声明
BOOL IsMainRunning(void);
void RestartMainProgram(void);
void StopTray(HWND hWnd); // 添加函数声明
LRESULT CALLBACK WindowProc(HWND hWnd, UINT uMsg, WPARAM wParam, LPARAM lParam);
void StartVersionCheck(void);
void OpenProjectPage(void);
void OpenRandomImage(void);
void RefreshTrayLanguage(void);
BOOL EnsureTrayAdmin(void);

/*
 * 日志函数：写入 logs\tray.log。
 * - 先执行 200KB 上限检查（TruncateLogIfNeeded）。
 * - 时间戳使用 localtime_s + strftime。
 * - 输出格式：YYYY-mm-dd HH:MM:SS [LEVEL] file:line - message
 */
void LogMessage(const char *level, const char *format, ...)
{
    if (!g_logFile)
        return;

    TruncateLogIfNeeded(g_logFile);

    time_t now;
    struct tm timeinfo;
    char timeStr[20];

    time(&now);
    localtime_s(&timeinfo, &now);
    strftime(timeStr, sizeof(timeStr), "%Y-%m-%d %H:%M:%S", &timeinfo);

    // 获取调用者文件名和行号
    const char *file = __FILE__;
    int line = __LINE__;

    // 打印日志格式: 时间 [级别] 文件名:行号 - 消息
    fprintf(g_logFile, "%s [%s] %s:%d - ", timeStr, level, file, line);

    va_list args;
    va_start(args, format);
    vfprintf(g_logFile, format, args);
    va_end(args);

    fprintf(g_logFile, "\n");
    fflush(g_logFile);
}

static int ParseVersionParts(const char *v, int *out, int maxParts)
{
    // 版本号解析（宽松）：
    // - 从字符串中提取连续数字段，最多提取 maxParts 段。
    // - 允许带前缀/后缀（例如 "V1.2.3"、"v2.0"、"release-1.2.3"）。
    //
    // 示例：
    // - "V1.2.3" => [1,2,3]
    // - "1.2" => [1,2]
    // - "1.2.3.4" => [1,2,3,4]
    // - "foo" => []
    int count = 0;
    const char *p = v;
    while (*p && count < maxParts)
    {
        while (*p && !isdigit((unsigned char)*p))
        {
            p++;
        }
        if (!*p)
        {
            break;
        }
        int val = 0;
        while (*p && isdigit((unsigned char)*p))
        {
            val = val * 10 + (*p - '0');
            p++;
        }
        out[count++] = val;
    }
    return count;
}

static int CompareVersions(const char *a, const char *b)
{
    // 版本比较：按“数字段”逐段比较（最多 4 段）。
    // - 缺失段按 0 处理，因此 "1.2" 等价于 "1.2.0.0"。
    // - 返回值：-1 表示 a<b，0 表示相等，1 表示 a>b。
    int va[4] = {0};
    int vb[4] = {0};
    ParseVersionParts(a, va, 4);
    ParseVersionParts(b, vb, 4);
    for (int i = 0; i < 4; ++i)
    {
        if (va[i] < vb[i])
        {
            return -1;
        }
        if (va[i] > vb[i])
        {
            return 1;
        }
    }
    return 0;
}

static BOOL ExtractTagName(const char *json, char *out, size_t len)
{
    // 从 GitHub releases/latest 的 JSON 响应中提取 "tag_name" 字段。
    //
    // 说明：
    // - 这里采用非常轻量的字符串查找，而不是完整 JSON 解析库。
    // - 适用于当前接口返回结构稳定的情况；若 GitHub 返回格式变化，可能提取失败。
    // - 失败时返回 FALSE，上层会显示“检查更新失败”。
    //
    // 安全性：
    // - out 始终以 NUL 结尾。
    // - len 为 0 时由调用方提前拦截。
    const char *tag = strstr(json, "\"tag_name\"");
    if (!tag)
    {
        return FALSE;
    }
    const char *colon = strchr(tag, ':');
    if (!colon)
    {
        return FALSE;
    }
    const char *start = strchr(colon, '"');
    if (!start)
    {
        return FALSE;
    }
    start++;
    const char *end = strchr(start, '"');
    if (!end || end <= start)
    {
        return FALSE;
    }
    size_t copy = (size_t)(end - start);
    if (copy >= len)
    {
        copy = len - 1;
    }
    memcpy(out, start, copy);
    out[copy] = '\0';
    return TRUE;
}

static BOOL FetchLatestReleaseTag(char *outTag, size_t outLen)
{
    // 通过 WinHTTP 拉取 GitHub API：/releases/latest
    //
    // WinHTTP 调用链：
    // - WinHttpOpen：创建 session（这里设置了 User-Agent）
    // - WinHttpConnect：连接到 api.github.com:443
    // - WinHttpOpenRequest：构造 HTTPS GET 请求
    // - WinHttpSendRequest + WinHttpReceiveResponse
    // - WinHttpQueryDataAvailable/WinHttpReadData 循环读取 body
    //
    // Header 说明：
    // - Accept: application/vnd.github+json 让 GitHub 返回标准 JSON
    // - User-Agent: GitHub API 要求提供 UA（否则可能被拒绝）
    //
    // 返回：
    // - TRUE：成功提取 tag_name 并写入 outTag
    // - FALSE：网络/解析失败
    if (!outTag || outLen == 0)
    {
        return FALSE;
    }

    BOOL success = FALSE;
    HINTERNET hSession = NULL;
    HINTERNET hConnect = NULL;
    HINTERNET hRequest = NULL;
    char *resp = NULL;

    // 将当前托盘版本拼入 UA，便于 GitHub 侧识别/排查。
    wchar_t userAgent[64] = {0};
    _snwprintf(userAgent, sizeof(userAgent) / sizeof(userAgent[0]), L"RC-tray/%S", BANBEN);

    hSession = WinHttpOpen(userAgent, WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                           WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!hSession)
    {
        goto cleanup;
    }

    hConnect = WinHttpConnect(hSession, REPO_HOST, INTERNET_DEFAULT_HTTPS_PORT, 0);
    if (!hConnect)
    {
        goto cleanup;
    }

    hRequest = WinHttpOpenRequest(hConnect, L"GET", REPO_LATEST_PATH, NULL,
                                  WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES,
                                  WINHTTP_FLAG_SECURE);
    if (!hRequest)
    {
        goto cleanup;
    }

    // 备注：这里 headers 中额外带了 User-Agent，是为了兼容某些代理/策略对 UA 的要求。
    // 实际 UA 同时也在 WinHttpOpen 的 userAgent 参数里设置。
    const wchar_t headers[] = L"Accept: application/vnd.github+json\r\nUser-Agent: RC-tray\r\n";
    if (!WinHttpSendRequest(hRequest, headers, (DWORD)-1L, WINHTTP_NO_REQUEST_DATA, 0, 0, 0))
    {
        goto cleanup;
    }

    if (!WinHttpReceiveResponse(hRequest, NULL))
    {
        goto cleanup;
    }

    DWORD dwSize = 0;
    size_t used = 0;
    size_t cap = 0;

    do
    {
        // WinHTTP 读数据是“按块”进行的：先查询可读字节，再 read。
        // 这里逐块扩容 resp 缓冲区，并最终追加 NUL 作为 C 字符串。
        if (!WinHttpQueryDataAvailable(hRequest, &dwSize) || dwSize == 0)
        {
            break;
        }

        if (used + dwSize + 1 > cap)
        {
            size_t newCap = (cap == 0) ? (dwSize + 1) : (cap + dwSize + 1);
            char *newBuf = (char *)realloc(resp, newCap);
            if (!newBuf)
            {
                goto cleanup;
            }
            resp = newBuf;
            cap = newCap;
        }

        DWORD dwRead = 0;
        if (!WinHttpReadData(hRequest, resp + used, dwSize, &dwRead))
        {
            goto cleanup;
        }
        used += dwRead;
    } while (dwSize > 0);

    if (resp)
    {
        resp[used] = '\0';
        if (ExtractTagName(resp, outTag, outLen))
        {
            success = TRUE;
        }
    }

cleanup:
    if (resp)
    {
        free(resp);
    }
    if (hRequest)
    {
        WinHttpCloseHandle(hRequest);
    }
    if (hConnect)
    {
        WinHttpCloseHandle(hConnect);
    }
    if (hSession)
    {
        WinHttpCloseHandle(hSession);
    }

    return success;
}

static void BuildVersionMenuText(char *buffer, size_t len)
{
    // 构造“版本菜单项”显示文本。
    // 文案结构：
    // - 主体：g_lang->menuVersionInfo（包含当前版本 BANBEN）
    // - 后缀：根据 g_versionStatus 追加“检查中/最新/有更新/错误”等提示
    //
    // 注意：这里的 buffer 是 UTF-8，后续会转为 UTF-16 传给 InsertMenuW。
    if (!buffer || len == 0 || !g_lang)
    {
        return;
    }

    _snprintf(buffer, len, g_lang->menuVersionInfo, BANBEN);
    size_t used = strlen(buffer);
    if (used + 1 >= len)
    {
        return;
    }

    switch (g_versionStatus)
    {
    case VERSION_CHECKING:
        if (len - strlen(buffer) > 1)
        {
            strncat(buffer, g_lang->versionCheckingSuffix, len - strlen(buffer) - 1);
        }
        break;
    case VERSION_OK:
        if (g_latestVersion[0] != '\0')
        {
            char suffix[96] = {0};
            int cmp = CompareVersions(BANBEN, g_latestVersion);
            if (cmp < 0)
            {
                _snprintf(suffix, sizeof(suffix), g_lang->versionSuffixNew, g_latestVersion);
            }
            else if (cmp == 0)
            {
                strncpy(suffix, g_lang->versionSuffixLatest, sizeof(suffix) - 1);
            }
            else
            {
                strncpy(suffix, g_lang->versionSuffixAhead, sizeof(suffix) - 1);
            }
            if (len - strlen(buffer) > 1)
            {
                strncat(buffer, suffix, len - strlen(buffer) - 1);
            }
        }
        break;
    case VERSION_ERROR:
        if (len - strlen(buffer) > 1)
        {
            strncat(buffer, g_lang->versionSuffixError, len - strlen(buffer) - 1);
        }
        break;
    case VERSION_PENDING:
    default:
        break;
    }
}

static unsigned __stdcall VersionCheckThread(void *arg)
{
    // 后台线程：查询 GitHub 最新版本并给出一次提示。
    //
    // 线程模型：
    // - 由 _beginthreadex 创建，避免与 CRT 资源管理冲突。
    // - 线程结束后不需要 join，StartVersionCheck 中会 CloseHandle。
    //
    // UI 注意：
    // - 这里直接调用 ShowNotificationDirect 更新托盘提示。
    //   Win32 托盘提示本质上通过 Shell_NotifyIconW 发送消息，通常可在非 UI 线程调用。
    //   若未来遇到兼容性问题，可改为 PostMessage 回主线程处理。
    (void)arg;
    char latest[64] = {0};
    BOOL ok = FetchLatestReleaseTag(latest, sizeof(latest));

    if (ok)
    {
        // 避免 strncpy 截断告警，同时保证 NUL 结尾
        _snprintf(g_latestVersion, sizeof(g_latestVersion), "%s", latest);
        g_versionStatus = VERSION_OK;
        g_versionCheckedTime = time(NULL);

        char notifyMsg[160] = {0};
        int cmp = CompareVersions(BANBEN, latest);
        if (cmp < 0)
        {
            _snprintf(notifyMsg, sizeof(notifyMsg), g_lang->versionNotifyNew, latest, BANBEN);
        }
        else if (cmp == 0)
        {
            _snprintf(notifyMsg, sizeof(notifyMsg), g_lang->versionNotifyLatest, BANBEN);
        }
        else
        {
            _snprintf(notifyMsg, sizeof(notifyMsg), g_lang->versionNotifyAhead, latest);
        }
        ShowNotificationDirect(g_lang->promptTitle, notifyMsg);
    }
    else
    {
        g_versionStatus = VERSION_ERROR;
        g_versionCheckedTime = time(NULL);
        ShowNotificationDirect(g_lang->promptTitle, g_lang->versionCheckFailed);
    }

    return 0;
}

void StartVersionCheck(void)
{
    // 触发版本检查（带简单节流）：
    // - 若当前正在检查：直接返回。
    // - 若刚刚检查成功且间隔 < 5 秒：避免频繁请求 GitHub API。
    //
    // 说明：
    // - 这里的 5 秒属于“最小限流”，主要防止用户连续点击菜单造成刷屏/重复请求。
    // - 并不做长期缓存；下次打开项目页/菜单仍可能触发检查。
    time_t now = time(NULL);
    if (g_versionStatus == VERSION_CHECKING)
    {
        return;
    }
    if (g_versionStatus == VERSION_OK && now - g_versionCheckedTime < 5)
    {
        return;
    }

    g_versionStatus = VERSION_CHECKING;
    g_latestVersion[0] = '\0';

    uintptr_t hThread = _beginthreadex(NULL, 0, VersionCheckThread, NULL, 0, NULL);
    if (hThread)
    {
        CloseHandle((HANDLE)hThread);
    }
}

void OpenProjectPage(void)
{
    // 打开项目主页。
    // 同时触发一次版本检查：用户点进项目页通常也关心是否有更新。
    ShellExecuteW(NULL, L"open", L"https://github.com/spacjoy/Remote-Controls", NULL, NULL, SW_SHOWNORMAL);
    StartVersionCheck();
}

void OpenRandomImage(void)
{
    // 彩蛋：打开一个随机图片链接。
    // ShellExecuteW 返回值 <= 32 表示失败（常见原因：默认浏览器不可用/被策略拦截）。
    HINSTANCE res = ShellExecuteW(NULL, L"open", L"https://rad.spacejoy.top/bz", NULL, NULL, SW_SHOWNORMAL);
    if ((INT_PTR)res <= 32)
    {
        ShowNotificationDirect(g_lang->promptTitle, g_lang->randomImageFailed);
    }
    else
    {
        ShowNotificationDirect(g_lang->promptTitle, g_lang->randomImageOpened);
    }
}

void RefreshTrayLanguage(void)
{
    // 刷新托盘语言（切换语言后的 UI 更新入口）。
    // - 更新 g_lang/g_logMsg 指针。
    // - 更新托盘悬停提示文本（NIF_TIP）。
    //
    // 说明：菜单文本在弹出时动态构建，因此无需在这里提前重建菜单。
    // 更新语言指针
    g_lang = GetLanguageStrings();
    g_logMsg = GetLogMessages();

    // 更新托盘提示文本
    if (g_lang)
    {
        char tipText[128];
        sprintf_s(tipText, sizeof(tipText), g_lang->trayTip, BANBEN);
        Utf8ToWide(tipText, g_nid.szTip, (int)(sizeof(g_nid.szTip) / sizeof(g_nid.szTip[0])));
        g_nid.uFlags = NIF_TIP;
        Shell_NotifyIconW(NIM_MODIFY, &g_nid);
    }
}

BOOL EnsureTrayAdmin(void)
{
    char selfPath[MAX_PATH];
    if (!GetModuleFileNameA(NULL, selfPath, MAX_PATH))
    {
        return FALSE;
    }

    BOOL started = RC_RunAsAdmin(selfPath, LogMessage,
                                 g_logMsg->runasAttempt, g_logMsg->uacCancelled,
                                 g_logMsg->startFailed, g_logMsg->startSuccess,
                                 ShowNotificationDirect, g_lang->promptTitle,
                                 g_lang->userCancelledUAC, g_lang->errorPromptTitle,
                                 g_lang->requestAdminFailed);

    if (started)
    {
        LogMessage("INFO", "已请求管理员权限，退出当前进程等待新进程");
        ExitProcess(0);
        return TRUE;
    }

    // RC_RunAsAdmin 内部已经根据取消/失败给出通知，这里避免重复弹窗
    return FALSE;
}

// 通用：以管理员权限执行命令（通过 cmd /c 参数）
// 已统一的管理员辅助函数移动到 rc_utils，托盘侧不再定义重复代码

/**
 * 初始化应用程序路径和日志
 */
BOOL InitApplication(void)
{
    // 初始化语言与“日志模板文案”。
    // 说明：
    // - language.c 负责 UI 文案（菜单、提示、通知）。
    // - log_messages.c 负责日志模板（固定结构 + 可本地化的内容）。
    // - 先初始化语言，再初始化日志模板，保证日志模板选择与语言一致。
    // 初始化语言支持
    InitializeLanguage();
    g_lang = GetLanguageStrings();

    // 初始化日志消息
    InitializeLogMessages();
    g_logMsg = GetLogMessages();

    // 获取应用程序目录（UTF-8，支持中文路径）。
    // g_appDir 用于拼接 logs、主程序、GUI、资源文件等路径。
    if (!GetModuleDirUtf8(g_appDir, sizeof(g_appDir)))
    {
        return FALSE;
    }

    // 检查管理员权限（并在需要时先提权）。
    // 说明：
    // - 托盘常驻安装目录（例如 Program Files）时，普通权限可能无法创建 logs\tray.log。
    // - 这里先尝试提权，再进行日志文件创建，避免“无权限创建日志导致启动失败”。
    g_isTrayAdmin = RC_IsUserAdmin();
    if (!g_isTrayAdmin)
    {
        if (EnsureTrayAdmin())
        {
            // EnsureTrayAdmin 成功时会启动新的管理员进程并退出当前进程。
            return FALSE;
        }
    }

    // 共享日志目录：用于与主程序协作（读取 logs\admin_status.txt）。
    // 这里保持固定为安装目录下的 logs。
    sprintf_s(g_logsDir, MAX_PATH, "%s\\logs", g_appDir);

    // 打开托盘自身日志文件（共享 + 追加）。
    // 优先写入安装目录 logs\tray.log；若无权限则回退到用户可写目录。
    {
        char logPathA[MAX_PATH] = {0};
        sprintf_s(logPathA, MAX_PATH, "%s\\tray.log", g_logsDir);

        wchar_t logPathW[MAX_PATH] = {0};
        if (!Utf8ToWide(logPathA, logPathW, MAX_PATH))
            return FALSE;

        // best-effort 创建 logs 目录（可能因权限失败）。
        _mkdir(g_logsDir);

        DWORD openErr = 0;
        g_logFile = OpenLogFileSharedAppendWEx(logPathW, &openErr);
        if (!g_logFile)
        {
            wchar_t writableLogsDirW[MAX_PATH] = {0};
            if (GetWritableTrayLogsDirW(writableLogsDirW, MAX_PATH))
            {
                wchar_t fallbackLogPathW[MAX_PATH] = {0};
                wcsncpy_s(fallbackLogPathW, MAX_PATH, writableLogsDirW, _TRUNCATE);
                if (PathAppendW(fallbackLogPathW, L"tray.log"))
                {
                    g_logFile = OpenLogFileSharedAppendWEx(fallbackLogPathW, NULL);
                }
            }
        }

        if (!g_logFile)
        {
            // 使用当前语言显示错误信息
            wchar_t msgW[256];
            wchar_t titleW[64];
            Utf8ToWide(g_lang->logCreateError, msgW, (int)(sizeof(msgW) / sizeof(msgW[0])));
            Utf8ToWide(g_lang->errorTitle, titleW, (int)(sizeof(titleW) / sizeof(titleW[0])));
            MessageBoxW(NULL, msgW, titleW, MB_ICONERROR);
            return FALSE;
        }
    }

    // 记录启动信息（写入 tray.log）。
    LogMessage("INFO", "=================================================");
    LogMessage("INFO", g_logMsg->appStarted);
    LogMessage("INFO", g_logMsg->appPath, g_appDir);
    LogMessage("INFO", g_logMsg->systemInfo);

    // 记录语言设置信息
    Language currentLang = GetCurrentLanguage();
    const char *langName = (currentLang == TRAY_LANG_CHINESE) ? "中文" : "English";
    LogMessage("INFO", "当前使用的语言: %s (语言ID: %d)", langName, currentLang);

    LogMessage("INFO", "=================================================");

    LogMessage("INFO", g_logMsg->trayAdminStatus, g_isTrayAdmin ? g_logMsg->adminYes : g_logMsg->adminNo);
    if (!g_isTrayAdmin)
    {
        LogMessage("INFO", "未获得管理员权限，托盘将继续以普通权限运行（部分功能可能受限）");
    }

    // 设置主程序和GUI程序的路径
    sprintf_s(g_mainExePath, MAX_PATH, "%s\\RC-main.exe", g_appDir);
    sprintf_s(g_guiExePath, MAX_PATH, "%s\\RC-GUI.exe", g_appDir);

    // 记录路径信息
    LogMessage("INFO", g_logMsg->mainPath, g_mainExePath);

    return TRUE;
}

/**
 * 检查程序是否正在运行
 */
BOOL IsMainRunning(void)
{
    // 主程序运行检测采用“双通道”：
    // 1) 进程名扫描（RC-main.exe）
    // 2) 互斥体检测（MUTEX_NAME = "RC-main"）
    // 这样可以在进程名被改动/拉起速度慢时提升鲁棒性。
    return RC_IsProcessRunning("RC-main.exe", MUTEX_NAME, LogMessage,
                               g_logMsg->mainFound, g_logMsg->mainFoundMutex, g_logMsg->mainNotFound);
}

/**
 * 创建系统托盘图标
 */
void CreateTrayIcon(HWND hWnd)
{
    // NOTIFYICONDATAW 结构决定托盘图标的行为：
    // - uCallbackMessage：托盘交互消息（右键、双击等）将以该消息号回到窗口过程。
    // - NIF_TIP：悬停提示文本。
    ZeroMemory(&g_nid, sizeof(NOTIFYICONDATAW));

    g_nid.cbSize = sizeof(NOTIFYICONDATAW);
    g_nid.hWnd = hWnd;
    g_nid.uID = TRAY_ICON_ID;
    g_nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
    g_nid.uCallbackMessage = WM_TRAYICON;

    // 图标加载策略：
    // 1) 优先从资源（.rc）内加载：便于打包发布。
    // 2) 若资源加载失败，再从磁盘 res\icon.ico 加载：便于用户替换图标。
    // 3) 再失败则使用系统默认图标。
    //
    // 注意：资源 IDI_TRAYICON 与 windres 编译的资源脚本保持一致。
    HICON hIcon = LoadIcon(GetModuleHandle(NULL), MAKEINTRESOURCE(IDI_TRAYICON));

    // 如果资源加载失败，尝试从文件加载
    if (!hIcon)
    {
        char iconPath[MAX_PATH];
        sprintf_s(iconPath, MAX_PATH, "%s\\res\\icon.ico", g_appDir);
        wchar_t iconPathW[MAX_PATH];
        if (Utf8ToWide(iconPath, iconPathW, MAX_PATH) && PathFileExistsW(iconPathW))
        {
            hIcon = (HICON)LoadImageW(NULL, iconPathW, IMAGE_ICON, 16, 16, LR_LOADFROMFILE);
            LogMessage("INFO", g_logMsg->iconLoadedFile, iconPath);
        }

        // 如果仍然失败，使用系统默认图标
        if (!hIcon)
        {
            hIcon = LoadIcon(NULL, IDI_APPLICATION);
            LogMessage("WARNING", g_logMsg->iconLoadFailed);
        }
    }
    else
    {
        LogMessage("INFO", g_logMsg->iconLoadedResource);
    }

    g_nid.hIcon = hIcon;

    // 设置提示文本 - 使用当前语言
    char tipText[128];
    sprintf_s(tipText, sizeof(tipText), g_lang->trayTip, BANBEN);
    Utf8ToWide(tipText, g_nid.szTip, (int)(sizeof(g_nid.szTip) / sizeof(g_nid.szTip[0])));

    Shell_NotifyIconW(NIM_ADD, &g_nid);
}

/**
 * 显示气泡通知 - 使用当前语言
 */
void ShowNotificationDirect(const char *title, const char *message)
{
    // 通知实现说明：
    // - 使用 Shell_NotifyIconW(NIM_MODIFY) 更新 NIF_INFO 字段。
    // - 先发送一次“空通知”再发送新内容，是为了规避 Windows 有时忽略更新的问题。
    //   （尤其在旧气泡仍显示时，直接覆盖可能不生效）
    // 强制覆盖旧通知：先清空当前气泡/Toast，再发送新内容。
    // Windows 在旧通知仍显示时，直接更新内容有时会被忽略。
    g_nid.uFlags = NIF_INFO;
    g_nid.szInfoTitle[0] = L'\0';
    g_nid.szInfo[0] = L'\0';
    g_nid.dwInfoFlags = NIIF_NONE;
    Shell_NotifyIconW(NIM_MODIFY, &g_nid);
    Sleep(10);

    g_nid.uFlags = NIF_INFO;
    Utf8ToWide(title, g_nid.szInfoTitle, (int)(sizeof(g_nid.szInfoTitle) / sizeof(g_nid.szInfoTitle[0])));
    Utf8ToWide(message, g_nid.szInfo, (int)(sizeof(g_nid.szInfo) / sizeof(g_nid.szInfo[0])));
    g_nid.dwInfoFlags = NIIF_INFO;

    Shell_NotifyIconW(NIM_MODIFY, &g_nid);
    LogMessage("INFO", g_logMsg->notification, title, message);
}

/**
 * 显示托盘通知 (ShowNotificationDirect的别名，保持接口一致性)
 */
void ShowTrayNotification(const char *title, const char *message)
{
    ShowNotificationDirect(title, message);
}

/**
 * 启动主程序（包装rc_utils中的函数）
 */
void StartMainProgram(void)
{
    // 启动主程序：统一走 rc_utils 的通用启动函数。
    // 这里传入：
    // - IsMainRunning：避免重复启动。
    // - 日志模板/通知文案：保证不同语言下的提示一致。
    RC_StartProgram(g_mainExePath, IsMainRunning, LogMessage, ShowNotificationDirect,
                    g_logMsg->funcStartMain, g_logMsg->mainRunning,
                    g_logMsg->mainStartSuccess, g_logMsg->mainStartFailed,
                    g_logMsg->mainNotExists, g_lang->promptTitle,
                    g_lang->notifyMainRunning, g_lang->restartingMain,
                    g_lang->errorPromptTitle, g_lang->mainNotExists,
                    TRUE); // 使用管理员权限启动主程序
}

/**
 * 关闭主程序（包装rc_utils中的函数）
 */
void CloseMainProgram(void)
{
    // 关闭主程序：
    // - 若托盘未提权：用 runas 提权执行 taskkill（避免权限不足导致关闭失败）。
    // - 若托盘已提权：走 rc_utils 的通用关闭流程（可记录更多日志与退出码）。
    // 若未提权，使用 runas 提权执行 taskkill
    if (!g_isTrayAdmin)
    {
        LogMessage("INFO", g_logMsg->funcCloseMain);

        if (!IsMainRunning())
        {
            ShowNotificationDirect(g_lang->promptTitle, g_lang->notifyMainNotRunning);
            return;
        }

        if (!RC_AdminTaskkill("RC-main.exe"))
        {
            ShowNotificationDirect(g_lang->errorPromptTitle, g_lang->closeFailed);
            LogMessage("ERROR", g_logMsg->taskkillFailed, GetLastError());
            return;
        }

        ShowNotificationDirect(g_lang->promptTitle, g_lang->closingMain);
        LogMessage("INFO", g_logMsg->closeRequested);
        return;
    }

    // 已提权，走原有关闭流程
    RC_CloseMainProgram("RC-main.exe", IsMainRunning, LogMessage, ShowNotificationDirect,
                        g_logMsg->funcCloseMain, g_logMsg->mainNotRunning,
                        g_logMsg->taskkillCommand, g_logMsg->taskkillExitCode,
                        g_logMsg->taskkillFailed, g_logMsg->closeRequested,
                        g_lang->promptTitle, g_lang->notifyMainNotRunning,
                        g_lang->errorPromptTitle, g_lang->closeFailed,
                        g_lang->closingMain);
}

/**
 * 检查主程序管理员权限状态（包装rc_utils中的函数）
 */
void CheckMainAdminStatus(void)
{
    RC_CheckMainAdminStatus(g_logsDir, IsMainRunning, LogMessage, ShowNotificationDirect,
                            g_logMsg->funcCheckAdmin, g_lang->promptTitle,
                            g_lang->notifyMainNotRunning, g_lang->adminCheckYes,
                            g_lang->adminCheckNo, g_lang->adminCheckUnknown,
                            g_lang->adminCheckReadError, g_lang->adminCheckFileNotExists);
}

/**
 * 打开配置GUI（包装rc_utils中的函数）
 */
void OpenConfigGui(void)
{
    // 优先启动 RC-GUI.exe；若不存在，则用系统默认程序打开 config.json。
    wchar_t guiPathW[MAX_PATH] = {0};
    if (Utf8ToWide(g_guiExePath, guiPathW, MAX_PATH) && PathFileExistsW(guiPathW))
    {
        RC_StartProgram(g_guiExePath, NULL, LogMessage, ShowNotificationDirect,
                        g_logMsg->funcOpenConfig, NULL, // 无需检查GUI是否已在运行
                        g_logMsg->configOpened, g_logMsg->configOpenFailed,
                        g_logMsg->configNotExists, g_lang->promptTitle,
                        NULL, NULL, // 无需通知程序已在运行或者正在启动
                        g_lang->errorPromptTitle, g_lang->configNotExists,
                        FALSE); // 不使用管理员权限启动GUI
        return;
    }

    LogMessage("WARNING", g_logMsg->configNotExists, g_guiExePath);

    // 回退：打开 config.json（使用系统默认 JSON 打开方式）。
    char configPathA[MAX_PATH] = {0};
    sprintf_s(configPathA, MAX_PATH, "%s\\config.json", g_appDir);
    wchar_t configPathW[MAX_PATH] = {0};
    if (!Utf8ToWide(configPathA, configPathW, MAX_PATH) || !PathFileExistsW(configPathW))
    {
        ShowNotificationDirect(g_lang->errorPromptTitle, g_lang->configNotExists);
        return;
    }

    HINSTANCE res = ShellExecuteW(NULL, L"open", configPathW, NULL, NULL, SW_SHOWNORMAL);
    if ((INT_PTR)res <= 32)
    {
        ShowNotificationDirect(g_lang->errorPromptTitle, g_lang->openConfigFailed);
        LogMessage("ERROR", g_logMsg->configOpenFailed, (unsigned long)(ULONG_PTR)res);
        return;
    }

    ShowNotificationDirect(g_lang->promptTitle, g_lang->openingConfig);
    LogMessage("INFO", "已使用默认程序打开配置文件: %s", configPathA);
}

/**
 * 窗口消息处理函数
 */
LRESULT CALLBACK WindowProc(HWND hWnd, UINT uMsg, WPARAM wParam, LPARAM lParam)
{
    // 托盘窗口过程：
    // - 本窗口通常不可见，仅用于接收托盘回调与菜单命令。
    // - WM_TRAYICON：托盘图标交互（右键弹菜单、双击打开配置）。
    // - WM_COMMAND：菜单项点击后的分发。
    switch (uMsg)
    {
    case WM_CREATE:
        CreateTrayIcon(hWnd);
        LogMessage("INFO", g_logMsg->trayCreated);
        return 0;

    case WM_DESTROY:
        // 移除托盘图标
        Shell_NotifyIconW(NIM_DELETE, &g_nid);
        PostQuitMessage(0);
        return 0;

    case WM_TRAYICON:
        if (lParam == WM_RBUTTONUP)
        {
            // 右键菜单：
            // - 菜单文本来自 language.c（支持中英文）。
            // - 这里在弹出菜单时“动态创建”，便于切换语言后立即生效。
            // - 会根据主程序是否运行禁用/启用部分菜单项。
            POINT pt;
            GetCursorPos(&pt);

            HMENU hMenu = CreatePopupMenu();
            if (hMenu)
            {
                // 菜单显示文本构造：
                // - versionText：本地版本 +（可选）更新状态后缀（检查中/最新/有更新/错误）。
                // - trayStatusText：托盘状态（这里主要展示是否管理员）。
                //
                // 这些字符串先以 UTF-8 生成，随后统一转换为 UTF-16 供 InsertMenuW 使用。
                char versionText[128] = {0};
                char trayStatusText[128] = {0};
                const char *adminText = g_isTrayAdmin ? g_lang->notifyAdminYes : g_lang->notifyAdminNo;
                BuildVersionMenuText(versionText, sizeof(versionText));
                _snprintf(trayStatusText, sizeof(trayStatusText), g_lang->menuTrayStatus, adminText);

                wchar_t versionTextW[128] = {0};
                wchar_t trayStatusTextW[128] = {0};
                wchar_t versionFallbackW[128] = {0};
                wchar_t trayStatusFmtW[128] = {0};

                // InsertMenuW 需要宽字符：
                // - versionText/trayStatusText 是动态拼装的文本
                // - versionFallback/trayStatusFmt 是兜底格式/固定文本
                Utf8ToWide(versionText, versionTextW, (int)(sizeof(versionTextW) / sizeof(versionTextW[0])));
                Utf8ToWide(trayStatusText, trayStatusTextW, (int)(sizeof(trayStatusTextW) / sizeof(trayStatusTextW[0])));
                Utf8ToWide(g_lang->menuVersionFallback, versionFallbackW, (int)(sizeof(versionFallbackW) / sizeof(versionFallbackW[0])));
                Utf8ToWide(g_lang->menuTrayStatus, trayStatusFmtW, (int)(sizeof(trayStatusFmtW) / sizeof(trayStatusFmtW[0])));

                char exitText[128] = {0};
                if (IsMainRunning())
                {
                    strncpy(exitText, g_lang->menuExit, sizeof(exitText) - 1);
                }
                else
                {
                    strncpy(exitText, g_lang->menuExitStandalone, sizeof(exitText) - 1);
                }

                // 退出菜单项文案会根据主程序是否运行而变化：
                // - 主程序运行：强调“退出外部托盘，并让主程序内置托盘接管”。
                // - 主程序未运行：以 standalone 版本提示“仅退出托盘”。

                wchar_t exitTextW[128] = {0};
                wchar_t menuOpenConfigW[128] = {0};
                wchar_t menuCheckAdminW[128] = {0};
                wchar_t menuStartMainW[128] = {0};
                wchar_t menuRestartMainW[128] = {0};
                wchar_t menuCloseMainW[128] = {0};
                wchar_t menuSwitchLanguageW[192] = {0};
                Utf8ToWide(exitText, exitTextW, (int)(sizeof(exitTextW) / sizeof(exitTextW[0])));
                Utf8ToWide(g_lang->menuOpenConfig, menuOpenConfigW, (int)(sizeof(menuOpenConfigW) / sizeof(menuOpenConfigW[0])));
                Utf8ToWide(g_lang->menuCheckAdmin, menuCheckAdminW, (int)(sizeof(menuCheckAdminW) / sizeof(menuCheckAdminW[0])));
                Utf8ToWide(g_lang->menuStartMain, menuStartMainW, (int)(sizeof(menuStartMainW) / sizeof(menuStartMainW[0])));
                Utf8ToWide(g_lang->menuRestartMain, menuRestartMainW, (int)(sizeof(menuRestartMainW) / sizeof(menuRestartMainW[0])));
                Utf8ToWide(g_lang->menuCloseMain, menuCloseMainW, (int)(sizeof(menuCloseMainW) / sizeof(menuCloseMainW[0])));
                Utf8ToWide(g_lang->menuSwitchLanguage, menuSwitchLanguageW, (int)(sizeof(menuSwitchLanguageW) / sizeof(menuSwitchLanguageW[0])));

                // 菜单项插入顺序：
                // 1) 版本信息（点击打开项目页，并触发更新检查）
                // 2) 托盘状态（这里绑定“随机图片/彩蛋”）
                // 3) 配置/权限检查
                // 4) 启动/重启/关闭主程序
                // 5) 切换语言
                // 6) 退出
                InsertMenuW(hMenu, -1, MF_BYPOSITION | MF_STRING, IDM_VERSION_INFO, versionTextW[0] ? versionTextW : versionFallbackW);
                InsertMenuW(hMenu, -1, MF_BYPOSITION | MF_STRING, IDM_TRAY_STATUS, trayStatusTextW[0] ? trayStatusTextW : trayStatusFmtW);
                InsertMenuW(hMenu, -1, MF_BYPOSITION | MF_SEPARATOR, 0, NULL);
                // 使用当前语言添加菜单项
                InsertMenuW(hMenu, -1, MF_BYPOSITION | MF_STRING, IDM_CONFIG, menuOpenConfigW);
                InsertMenuW(hMenu, -1, MF_BYPOSITION | MF_STRING, IDM_CHECK_ADMIN, menuCheckAdminW);
                InsertMenuW(hMenu, -1, MF_BYPOSITION | MF_SEPARATOR, 0, NULL);
                InsertMenuW(hMenu, -1, MF_BYPOSITION | MF_STRING, IDM_START_MAIN, menuStartMainW);
                InsertMenuW(hMenu, -1, MF_BYPOSITION | MF_STRING, IDM_RESTART_MAIN, menuRestartMainW);
                InsertMenuW(hMenu, -1, MF_BYPOSITION | MF_STRING, IDM_CLOSE_MAIN, menuCloseMainW);
                InsertMenuW(hMenu, -1, MF_BYPOSITION | MF_SEPARATOR, 0, NULL);
                InsertMenuW(hMenu, -1, MF_BYPOSITION | MF_STRING, IDM_SWITCH_LANG, menuSwitchLanguageW);
                InsertMenuW(hMenu, -1, MF_BYPOSITION | MF_SEPARATOR, 0, NULL);
                InsertMenuW(hMenu, -1, MF_BYPOSITION | MF_STRING, IDM_EXIT, exitTextW);

                // 禁用已经运行的程序的开始按钮
                if (IsMainRunning())
                {
                    // 主程序已运行：Start 置灰，避免重复启动。
                    EnableMenuItem(hMenu, IDM_START_MAIN, MF_BYCOMMAND | MF_GRAYED);
                }
                else
                {
                    // 主程序未运行：Restart/Close 置灰，避免对不存在的进程执行操作。
                    EnableMenuItem(hMenu, IDM_RESTART_MAIN, MF_BYCOMMAND | MF_GRAYED);
                    EnableMenuItem(hMenu, IDM_CLOSE_MAIN, MF_BYCOMMAND | MF_GRAYED);
                }

                // 设置前台窗口以接收菜单命令。
                // 这是 Win32 托盘菜单的常见惯例：避免菜单点击后消息丢失。
                SetForegroundWindow(hWnd);

                // 在鼠标位置显示菜单
                // TrackPopupMenu 会阻塞直到菜单关闭；用户点击后会产生 WM_COMMAND 回到本窗口。
                TrackPopupMenu(hMenu, TPM_LEFTALIGN | TPM_RIGHTBUTTON,
                               pt.x, pt.y, 0, hWnd, NULL);

                // 销毁菜单
                DestroyMenu(hMenu);
            }
        }
        else if (lParam == WM_LBUTTONDBLCLK)
        {
            // 双击左键 - 打开配置
            OpenConfigGui();
        }
        return 0;

    case WM_COMMAND:
        // 菜单命令分发：
        // - 通过 LOWORD(wParam) 取得菜单项 ID（IDM_*）。
        // - 每个分支尽量只做“薄封装”：真正的逻辑在 Start/Close/Restart/OpenConfig 等函数内。
        switch (LOWORD(wParam))
        {
        case IDM_VERSION_INFO:
            OpenProjectPage();
            break;

        case IDM_TRAY_STATUS:
            OpenRandomImage();
            break;

        case IDM_CONFIG:
            OpenConfigGui();
            break;

        case IDM_CHECK_ADMIN:
            CheckMainAdminStatus();
            break;

        case IDM_START_MAIN:
            StartMainProgram();
            break;

        case IDM_RESTART_MAIN:
            RestartMainProgram();
            break;

        case IDM_CLOSE_MAIN:
            CloseMainProgram();
            break;

        case IDM_SWITCH_LANG:
            ToggleLanguage();
            RefreshTrayLanguage();
            ShowNotificationDirect(g_lang->promptTitle, g_lang->menuSwitchLanguage);
            break;

        case IDM_EXIT:
            // 不直接销毁窗口，而是调用StopTray函数
            StopTray(hWnd);
            break;
        }
        return 0;
    }

    return DefWindowProcW(hWnd, uMsg, wParam, lParam);
}

/**
 * 初始化托盘应用程序
 */
BOOL InitTray(HINSTANCE hInstance)
{
    // 注册窗口类：
    // - 托盘程序需要一个“消息窗口”来接收 WM_TRAYICON 回调与 WM_COMMAND 菜单命令。
    // - 窗口本身不显示（隐藏窗口），但必须存在并有稳定的 WindowProc。
    WNDCLASSEXW wc = {0};
    wc.cbSize = sizeof(WNDCLASSEXW);
    wc.lpfnWndProc = WindowProc;
    wc.hInstance = hInstance;
    wc.lpszClassName = L"RemoteControlTrayClass";

    if (!RegisterClassExW(&wc))
    {
        LogMessage("ERROR", g_logMsg->registerClassFailed);
        return FALSE;
    }

    // 创建隐藏窗口：
    // - 选择 WS_OVERLAPPED 并用 CW_USEDEFAULT 占位；窗口不会显示在任务栏。
    // - 窗口标题用于调试与某些系统 UI（这里使用当前语言的 appTitle）。
    wchar_t titleW[64] = {0};
    Utf8ToWide(g_lang ? g_lang->appTitle : "Remote Control Tray", titleW, (int)(sizeof(titleW) / sizeof(titleW[0])));
    g_hWnd = CreateWindowExW(
        0,
        L"RemoteControlTrayClass",
        titleW,
        WS_OVERLAPPED,
        CW_USEDEFAULT, CW_USEDEFAULT,
        CW_USEDEFAULT, CW_USEDEFAULT,
        NULL, NULL, hInstance, NULL);

    if (!g_hWnd)
    {
        LogMessage("ERROR", g_logMsg->createWindowFailed);
        return FALSE;
    }

    return TRUE;
}

/**
 * 检查主程序并在未运行时自动启动
 */
void CheckAndStartMainProgram(void)
{
    // 启动策略：
    // - 若主程序未运行：直接启动。
    // - 若主程序已运行：这里选择重启（确保主程序读取最新配置/恢复状态）。
    //   如果未来希望更温和的策略，可调整为“仅提示用户/不自动重启”。
    // 检查主程序是否在运行
    if (!IsMainRunning())
    {
        // 如果主程序未运行，则尝试启动它
        LogMessage("INFO", g_logMsg->trayStartNoMain);
        StartMainProgram();
    }
    else
    {
        // 如果主程序正在运行，则尝试重启它
        LogMessage("INFO", g_logMsg->trayStartMainRunning);
        RestartMainProgram();
    }
}

/**
 * 重启主程序（包装rc_utils中的函数）
 */
void RestartMainProgram(void)
{
    // 未提权时，先用 runas 提权执行 taskkill，再以管理员权限启动主程序
    if (!g_isTrayAdmin)
    {
        LogMessage("INFO", g_logMsg->funcRestartMain);
        ShowNotificationDirect(g_lang->promptTitle, g_lang->restartingMain);

        if (IsMainRunning())
        {
            if (!RC_AdminTaskkill("RC-main.exe"))
            {
                LogMessage("ERROR", g_logMsg->taskkillFailed, GetLastError());
            }
            Sleep(1000);
        }
        else
        {
            LogMessage("INFO", g_logMsg->mainNotRunning);
        }

        // 以管理员权限启动主程序
        RC_StartProgram(g_mainExePath, NULL, LogMessage, ShowNotificationDirect,
                        g_logMsg->funcStartMain, NULL,
                        g_logMsg->mainStartSuccess, g_logMsg->mainStartFailed,
                        g_logMsg->mainNotExists, g_lang->promptTitle,
                        NULL, g_lang->restartingMain, g_lang->errorPromptTitle,
                        g_lang->mainNotExists, TRUE);
        return;
    }

    // 已提权，走通用重启流程
    RC_RestartMainProgram("RC-main.exe", g_mainExePath, IsMainRunning,
                          LogMessage, ShowNotificationDirect,
                          g_logMsg->funcRestartMain, g_lang->restartingMain,
                          g_logMsg->mainNotRunning, g_lang->promptTitle);
}

/**
 * 退出托盘程序，并确保主程序已重启（启用主程序的内置托盘）
 */
void StopTray(HWND hWnd)
{
    // 退出策略：
    // - 本项目存在两种托盘：外部托盘 RC-tray.exe 与主程序内置托盘。
    // - 当用户退出外部托盘时，这里会“尽量确保主程序已重启”，
    //   从而让主程序内置托盘接管（避免完全失去托盘入口）。
    LogMessage("INFO", "执行函数: StopTray");
    LogMessage("INFO", "==============================");
    LogMessage("INFO", "正在关闭托盘程序，启用主程序内置托盘");
    LogMessage("INFO", "==============================");

    // 显示通知
    ShowNotificationDirect(g_lang->promptTitle, g_lang->exitingTray);

    // 若主程序在运行：这里会尝试重启主程序，让主程序内置托盘“重新上线”。
    // Sleep(1250) 是一个经验等待时间，给主程序启动与托盘初始化留出余量。
    BOOL mainRunning = IsMainRunning();
    if (mainRunning)
    {
        RestartMainProgram();
        Sleep(1250);
    }

    // 记录日志并销毁窗口，这将导致退出消息循环
    LogMessage("INFO", g_logMsg->userRequestExit);
    DestroyWindow(hWnd);
}

/**
 * 程序入口点
 */
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, LPSTR lpCmdLine, int nCmdShow)
{
    // 入口点说明：
    // - RC-tray.exe 是一个典型 Win32 GUI 子系统程序（-mwindows），不使用控制台。
    // - 主逻辑：初始化 -> 创建隐藏窗口与托盘图标 ->（按策略）启动/重启主程序 -> 消息循环。
    // 初始化顺序：
    // 1) InitApplication：语言/日志/路径/（可能）提权
    // 2) InitTray：注册窗口类 + 创建隐藏窗口（WM_CREATE 中创建托盘图标）
    // 3) CheckAndStartMainProgram：按策略启动/重启主程序
    // 4) 消息循环：处理托盘回调与菜单命令
    // 5) 退出清理：关闭日志文件
    //
    // 备注：hPrevInstance/lpCmdLine/nCmdShow 在本程序中未使用。
    // 初始化应用程序
    if (!InitApplication())
    {
        return 1;
    }

    // 初始化托盘
    if (!InitTray(hInstance))
    {
        LogMessage("ERROR", g_logMsg->initTrayFailed);
        return 1;
    }

    // 检查并启动主程序
    CheckAndStartMainProgram();

    // 消息循环：
    // - GetMessage 返回 0 表示 WM_QUIT（由 PostQuitMessage 发出）。
    // - TranslateMessage/DispatchMessage 将消息派发到 WindowProc。
    MSG msg;
    while (GetMessage(&msg, NULL, 0, 0))
    {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    // 退出清理：
    // - 这里关闭日志文件（FILE*）。
    // - 托盘图标的删除发生在 WM_DESTROY 分支中（Shell_NotifyIconW(NIM_DELETE)）。
    if (g_logFile)
    {
        LogMessage("INFO", g_logMsg->trayExit);
        fclose(g_logFile);
    }

    return (int)msg.wParam;
}
