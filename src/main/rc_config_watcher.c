/*
 * rc_config_watcher.c
 *
 * 使用 Windows ReadDirectoryChangesW 实现配置文件实时监控。
 * 当 config.toml 文件被修改时，触发重新加载配置的回调函数。
 *
 * 设计要点：
 * - 使用独立后台线程运行，不阻塞主程序
 * - 内核级文件事件通知，零 CPU 轮询开销
 * - 防抖处理（debounce），避免文件写入中途触发
 * - 支持线程安全回调（通过回调函数通知主程序）
 */

#include "rc_config_watcher.h"
#include "rc_log.h"

#include <windows.h>
#include <shlwapi.h>
#include <stdlib.h>
#include <string.h>

#define CONFIG_WATCH_DEBOUNCE_MS 500

struct RC_ConfigWatcher
{
    wchar_t configPath[MAX_PATH];
    wchar_t configDir[MAX_PATH];
    char configFileNameUtf8[260];  // UTF-8 encoded filename for _stricmp comparison
    RC_ConfigChangedCallback callback;
    void *userContext;
    volatile bool running;
    HANDLE thread;
};

static DWORD WINAPI watch_thread(LPVOID p)
{
    RC_ConfigWatcher *w = (RC_ConfigWatcher *)p;
    if (!w)
        return 0;

    HANDLE hDir = CreateFileW(
        w->configDir,
        FILE_LIST_DIRECTORY,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        NULL,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS,
        NULL
    );

    if (hDir == INVALID_HANDLE_VALUE)
    {
        RC_LogWarn("配置文件监听：无法打开目录 [%ls] (错误码: %lu)", w->configDir, GetLastError());
        return 1;
    }

    char buffer[1024];
    DWORD bytesReturned = 0;

    while (w->running)
    {
        BOOL result = ReadDirectoryChangesW(
            hDir,
            buffer,
            sizeof(buffer),
            FALSE,
            FILE_NOTIFY_CHANGE_LAST_WRITE | FILE_NOTIFY_CHANGE_FILE_NAME,
            &bytesReturned,
            NULL,
            NULL
        );

        if (!result || !w->running)
            break;

        FILE_NOTIFY_INFORMATION *fni = (FILE_NOTIFY_INFORMATION *)buffer;
        bool targetChanged = false;

        while (fni)
        {
            // 将 Unicode 文件名转换为 ANSI 进行比较
            char fileName[260] = {0};
            int len = WideCharToMultiByte(CP_UTF8, 0, fni->FileName,
                                          fni->FileNameLength / sizeof(WCHAR),
                                          fileName, sizeof(fileName) - 1, NULL, NULL);
            if (len > 0)
            {
                if (_stricmp(fileName, w->configFileNameUtf8) == 0)
                {
                    targetChanged = true;
                    break;
                }
            }

            if (fni->NextEntryOffset == 0)
                break;
            fni = (FILE_NOTIFY_INFORMATION *)((char *)fni + fni->NextEntryOffset);
        }

        if (targetChanged && w->running)
        {
            // 防抖：等待一段时间，避免文件写入中途触发
            Sleep(CONFIG_WATCH_DEBOUNCE_MS);
            
            if (w->running && w->callback)
            {
                w->callback(w->configPath, w->userContext);
            }
        }
    }

    CloseHandle(hDir);
    return 0;
}

RC_ConfigWatcher *RC_ConfigWatcherCreate(
    const wchar_t *configPath,
    RC_ConfigChangedCallback callback,
    void *userContext
)
{
    if (!configPath || !callback)
        return NULL;

    RC_ConfigWatcher *w = (RC_ConfigWatcher *)calloc(1, sizeof(RC_ConfigWatcher));
    if (!w)
        return NULL;

    wcsncpy_s(w->configPath, MAX_PATH, configPath, _TRUNCATE);

    // 提取目录和文件名
    const wchar_t *lastBackslash = wcsrchr(configPath, L'\\');
    if (lastBackslash)
    {
        size_t dirLen = (size_t)(lastBackslash - configPath);
        wcsncpy_s(w->configDir, MAX_PATH, configPath, dirLen);
        // 将文件名转换为 UTF-8
        WideCharToMultiByte(CP_UTF8, 0, lastBackslash + 1, -1,
                            w->configFileNameUtf8, sizeof(w->configFileNameUtf8), NULL, NULL);
    }
    else
    {
        // 如果没有路径分隔符，使用当前目录
        GetCurrentDirectoryW(MAX_PATH, w->configDir);
        WideCharToMultiByte(CP_UTF8, 0, configPath, -1,
                            w->configFileNameUtf8, sizeof(w->configFileNameUtf8), NULL, NULL);
    }

    w->callback = callback;
    w->userContext = userContext;
    w->running = true;

    w->thread = CreateThread(NULL, 0, watch_thread, w, 0, NULL);
    if (!w->thread)
    {
        free(w);
        return NULL;
    }

    RC_LogInfo("配置文件监听已启动: %ls", configPath);
    return w;
}

void RC_ConfigWatcherDestroy(RC_ConfigWatcher *w)
{
    if (!w)
        return;

    w->running = false;

    // 等待线程退出（最多等待 2 秒）
    if (w->thread)
    {
        WaitForSingleObject(w->thread, 2000);
        CloseHandle(w->thread);
    }

    RC_LogInfo("配置文件监听已停止");
    free(w);
}
