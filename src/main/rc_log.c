/*
 * rc_log.c
 *
 * 主程序日志实现：
 * - 目标文件：默认 logs\main.log（位于 exe 同级 logs 目录）。
 * - 打开方式：_wfsopen + _SH_DENYNO（不拒绝共享），方便运行时查看/复制/删除。
 * - 输出：同时输出到 OutputDebugStringA（便于调试器/DebugView 观察）。
 * - 体积限制：200KB，达到/超过后先 truncate 再写入，避免日志无限增长。
 */

#include "rc_log.h"

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <share.h>
#include <io.h>

static FILE *g_log = NULL;

#define RC_LOG_MAX_BYTES (200 * 1024)

/*
 * 日志上限控制：
 * - 使用 _filelengthi64 获取当前文件大小。
 * - 当 size >= RC_LOG_MAX_BYTES：
 *   1) fflush 确保落盘；
 *   2) _chsize_s(fd, 0) 直接截断为 0；
 *   3) fseek(..., SEEK_END) 确保后续按追加方式写入。
 *
 * 注意：这里是“写入前检查”，因此超过上限时会先清空，再写入本条新日志，符合“先清空再写”。
 */
static void log_truncate_if_needed(FILE *f)
{
    if (!f)
        return;
    int fd = _fileno(f);
    if (fd < 0)
        return;

    __int64 size = _filelengthi64(fd);
    if (size < 0)
        return;

    if (size >= RC_LOG_MAX_BYTES)
    {
        fflush(f);
        (void)_chsize_s(fd, 0);
        (void)fseek(f, 0, SEEK_END);
    }
}

static void log_v(const char *level, const char *fmt, va_list ap)
{
    if (!fmt)
        fmt = "";

    SYSTEMTIME st;
    GetLocalTime(&st);

    char msg[4096];
    vsnprintf(msg, sizeof(msg), fmt, ap);
    msg[sizeof(msg) - 1] = '\0';

    char line[4600];
    snprintf(line, sizeof(line), "%04u-%02u-%02u %02u:%02u:%02u.%03u [%s] %s\n",
             (unsigned)st.wYear, (unsigned)st.wMonth, (unsigned)st.wDay,
             (unsigned)st.wHour, (unsigned)st.wMinute, (unsigned)st.wSecond, (unsigned)st.wMilliseconds,
             level ? level : "INFO", msg);

    // 始终输出到调试器（不依赖文件是否打开）。
    OutputDebugStringA(line);

    if (g_log)
    {
        // 写入前先执行 200KB 上限检查。
        log_truncate_if_needed(g_log);
        fputs(line, g_log);
        fflush(g_log);
    }
}

void RC_LogInit(const wchar_t *appDirW)
{
    if (g_log)
        return;

    wchar_t logPath[MAX_PATH] = {0};
    if (appDirW && *appDirW)
    {
        wchar_t logsDir[MAX_PATH] = {0};
        _snwprintf(logsDir, MAX_PATH, L"%s\\logs", appDirW);
        CreateDirectoryW(logsDir, NULL);
        _snwprintf(logPath, MAX_PATH, L"%s\\logs\\main.log", appDirW);
    }
    else
    {
        _snwprintf(logPath, MAX_PATH, L"logs\\main.log");
    }

    // 保障 logs 目录存在（相对路径情况下 best-effort）。
    CreateDirectoryW(L"logs", NULL);

    // shared-open：允许运行时 tail/view。
    g_log = _wfsopen(logPath, L"ab", _SH_DENYNO);
    if (!g_log)
    {
        // Fallback to current-directory logs\main.log
        g_log = _wfsopen(L"logs\\main.log", L"ab", _SH_DENYNO);
    }

    if (g_log)
    {
        // 关闭缓冲：让外部查看时更“实时”。
        setvbuf(g_log, NULL, _IONBF, 0);
    }
}

void RC_LogInfo(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    log_v("INFO", fmt, ap);
    va_end(ap);
}

void RC_LogWarn(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    log_v("WARN", fmt, ap);
    va_end(ap);
}

void RC_LogError(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    log_v("ERROR", fmt, ap);
    va_end(ap);
}
