/*
 * rc_router.c
 *
 * Router 实现：
 * - 解析配置 JSON，抽取需要订阅的 topic 列表。
 * - 将不同类型的功能（电脑/屏幕/音量/媒体/应用/命令/服务/热键）统一抽象成：topic + on/off 行为。
 * - 收到 MQTT 消息后，根据 payload（on/off/on#xx 等）选择分支并调用 rc_actions 执行。
 *
 * 重要说明：
 * - 本文件把 config.json 中的大量键名（例如 application1、command2、serve3...）映射为内部结构数组。
 * - 许多动作都可能带延迟（*_delay 字段）或带“preset”策略（kill/stop/custom 等）。
 */

#include "rc_router.h"

#include "rc_actions.h"
#include "rc_log.h"

#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WM_RCMAIN_NOTIFYICON (WM_USER + 201)
#define RCMAIN_NOTIFY_ICON_ID 2

static HWND g_notifyHwnd = NULL;
static NOTIFYICONDATAW g_notifyNid;
static bool g_notifyInited = false;

static BOOL utf8_to_wide0(const char *src, wchar_t *dst, int dstCount)
{
    if (!dst || dstCount <= 0)
        return FALSE;
    dst[0] = L'\0';
    if (!src)
        return TRUE;
    return MultiByteToWideChar(CP_UTF8, 0, src, -1, dst, dstCount) > 0;
}

static LRESULT CALLBACK notify_wndproc(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam)
{
    (void)wParam;
    (void)lParam;
    return DefWindowProcW(hWnd, msg, wParam, lParam);
}

static bool notify_ensure_icon(void)
{
    if (g_notifyInited)
        return true;

    HINSTANCE hInst = GetModuleHandleW(NULL);
    const wchar_t *cls = L"RCMainNotifyClass";

    WNDCLASSEXW wc;
    ZeroMemory(&wc, sizeof(wc));
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = notify_wndproc;
    wc.hInstance = hInst;
    wc.lpszClassName = cls;

    // RegisterClassExW 可能因已注册返回失败（ERROR_CLASS_ALREADY_EXISTS）。
    if (!RegisterClassExW(&wc))
    {
        DWORD e = GetLastError();
        if (e != ERROR_CLASS_ALREADY_EXISTS)
        {
            RC_LogWarn("通知窗口类注册失败：%lu", e);
            return false;
        }
    }

    // 使用 message-only window，避免出现在 Alt-Tab / 任务栏。
    g_notifyHwnd = CreateWindowExW(0, cls, L"RC-main-notify", 0, 0, 0, 0, 0, HWND_MESSAGE, NULL, hInst, NULL);
    if (!g_notifyHwnd)
    {
        RC_LogWarn("通知窗口创建失败：%lu", GetLastError());
        return false;
    }

    ZeroMemory(&g_notifyNid, sizeof(g_notifyNid));
    g_notifyNid.cbSize = sizeof(g_notifyNid);
    g_notifyNid.hWnd = g_notifyHwnd;
    g_notifyNid.uID = RCMAIN_NOTIFY_ICON_ID;
    g_notifyNid.uCallbackMessage = WM_RCMAIN_NOTIFYICON;
    g_notifyNid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_STATE;
    g_notifyNid.hIcon = LoadIconW(NULL, IDI_APPLICATION);
    wcsncpy_s(g_notifyNid.szTip, _countof(g_notifyNid.szTip), L"RC-main", _TRUNCATE);
    g_notifyNid.dwStateMask = NIS_HIDDEN;
    g_notifyNid.dwState = NIS_HIDDEN;

    if (!Shell_NotifyIconW(NIM_ADD, &g_notifyNid))
    {
        RC_LogWarn("通知图标添加失败：%lu", GetLastError());
        DestroyWindow(g_notifyHwnd);
        g_notifyHwnd = NULL;
        return false;
    }

    g_notifyInited = true;
    return true;
}

static void notify_shutdown(void)
{
    if (g_notifyInited)
    {
        Shell_NotifyIconW(NIM_DELETE, &g_notifyNid);
    }
    if (g_notifyHwnd)
    {
        DestroyWindow(g_notifyHwnd);
        g_notifyHwnd = NULL;
    }
    g_notifyInited = false;
}

static void notify_show_utf8(const char *titleUtf8, const char *messageUtf8)
{
    if (!notify_ensure_icon())
        return;

    // 与托盘端一致：先发“空通知”再发新内容，规避 Windows 忽略更新。
    g_notifyNid.uFlags = NIF_INFO;
    g_notifyNid.szInfoTitle[0] = L'\0';
    g_notifyNid.szInfo[0] = L'\0';
    g_notifyNid.dwInfoFlags = NIIF_NONE;
    Shell_NotifyIconW(NIM_MODIFY, &g_notifyNid);
    Sleep(10);

    g_notifyNid.uFlags = NIF_INFO;
    utf8_to_wide0(titleUtf8, g_notifyNid.szInfoTitle, (int)_countof(g_notifyNid.szInfoTitle));
    utf8_to_wide0(messageUtf8, g_notifyNid.szInfo, (int)_countof(g_notifyNid.szInfo));
    g_notifyNid.dwInfoFlags = NIIF_INFO;
    Shell_NotifyIconW(NIM_MODIFY, &g_notifyNid);
}

typedef struct
{
    char *topic;
    char *displayName; // optional: applicationN_name
    char *onPath;
    char *offPath;
    char *offPreset; // kill/none/custom
} RcApp;

typedef struct
{
    char *topic;
    char *displayName; // optional: commandN_name
    char *value;       // legacy value
    char *onValue;
    char *offValue;
    char *offPreset; // interrupt/kill/none/custom
    char *window;    // show/hide
} RcCommand;

typedef struct
{
    char *topic;
    char *displayName; // optional: serveN_name
    char *serviceName;
    char *offPreset; // stop/none/custom
    char *offValue;
} RcServe;

typedef struct
{
    char *topic;
    char *displayName; // optional: hotkeyN_name
    char *onType;
    char *onValue;
    char *offType;
    char *offValue;
    int charDelayMs;
} RcHotkey;

typedef struct
{
    char *topic;
    unsigned long *pids;
    int count;
    int cap;
} RcCmdProc;

struct RC_Router
{
    RC_Json *config; // owned

    bool notifyEnabled;

    // 内置功能对应的 topic（直接从 config 中读取的字符串）。
    char *topicComputer;
    char *topicScreen;
    char *topicVolume;
    char *topicSleep;
    char *topicMedia;

    bool checkedComputer;
    bool checkedScreen;
    bool checkedVolume;
    bool checkedSleep;
    bool checkedMedia;

    RcApp *apps;
    int appsCount;

    RcCommand *cmds;
    int cmdsCount;

    RcServe *serves;
    int servesCount;

    RcHotkey *hotkeys;
    int hotkeysCount;

    RcCmdProc *cmdProcs;
    int cmdProcsCount;

    const char **topics; // pointers to owned strings above
    int topicsCount;
};

static char *dupstr0(const char *s);

/*
 * 命令 PID 跟踪表（cmdProcs）：
 *
 * 背景：Commands 分支会启动 PowerShell 子进程；当收到 off 消息且 off_preset=kill/interrupt 时，
 * 需要“定向结束”之前启动的进程，而不是全局 taskkill。
 *
 * 设计：
 * - 以 topic 为 key，为每个 command topic 维护一个 PID 列表（RcCmdProc）。
 * - 列表允许重复（同一 topic 被多次触发会记录多个 pid），不做去重；
 *   后续通过 pid_is_alive/cleanup_dead 做一次“存活过滤”。
 * - cmdProcs 的内存由 Router 管理，在 RC_RouterDestroy 中统一释放。
 */
static RcCmdProc *cmd_proc_get_or_create(RC_Router *r, const char *topic)
{
    if (!r || !topic || !*topic)
        return NULL;
    for (int i = 0; i < r->cmdProcsCount; i++)
    {
        if (r->cmdProcs[i].topic && strcmp(r->cmdProcs[i].topic, topic) == 0)
            return &r->cmdProcs[i];
    }

    RcCmdProc item;
    ZeroMemory(&item, sizeof(item));
    item.topic = dupstr0(topic);
    if (!item.topic)
        return NULL;

    RcCmdProc *narr = (RcCmdProc *)realloc(r->cmdProcs, (size_t)(r->cmdProcsCount + 1) * sizeof(RcCmdProc));
    if (!narr)
    {
        free(item.topic);
        return NULL;
    }
    r->cmdProcs = narr;
    r->cmdProcs[r->cmdProcsCount++] = item;
    return &r->cmdProcs[r->cmdProcsCount - 1];
}

static void cmd_proc_add_pid(RcCmdProc *p, unsigned long pid)
{
    // 追加 pid 到跟踪表。
    // - cap 采用 4 起步、倍增扩容，保持追加开销均摊。
    // - pid==0 视为无效（CreateProcess 获取失败或未返回 pid）。
    if (!p || pid == 0)
        return;
    if (p->count >= p->cap)
    {
        int newCap = (p->cap == 0) ? 4 : (p->cap * 2);
        unsigned long *np = (unsigned long *)realloc(p->pids, (size_t)newCap * sizeof(unsigned long));
        if (!np)
            return;
        p->pids = np;
        p->cap = newCap;
    }
    p->pids[p->count++] = pid;
}

static void cmd_proc_clear(RcCmdProc *p)
{
    // 清空跟踪表：释放 pid 数组并复位计数。
    // 用于 off_preset=kill 后，避免下一次 off 误杀“上一轮已经处理过的 pid”。
    if (!p)
        return;
    free(p->pids);
    p->pids = NULL;
    p->count = 0;
    p->cap = 0;
}

static char *dupstr0(const char *s)
{
    if (!s)
        s = "";
    size_t n = strlen(s);
    char *out = (char *)malloc(n + 1);
    if (!out)
        return NULL;
    memcpy(out, s, n + 1);
    return out;
}

static const char *cfg_str(const RC_Json *obj, const char *key)
{
    return RC_JsonGetString(RC_JsonObjectGet(obj, key));
}

static int cfg_int(const RC_Json *obj, const char *key, int defVal)
{
    return RC_JsonGetInt(RC_JsonObjectGet(obj, key), defVal);
}

static bool cfg_bool(const RC_Json *obj, const char *key, bool defVal)
{
    return RC_JsonGetBool(RC_JsonObjectGet(obj, key), defVal);
}

static void free_apps(RcApp *arr, int n)
{
    for (int i = 0; i < n; i++)
    {
        free(arr[i].topic);
        free(arr[i].displayName);
        free(arr[i].onPath);
        free(arr[i].offPath);
        free(arr[i].offPreset);
    }
    free(arr);
}

static void free_cmds(RcCommand *arr, int n)
{
    for (int i = 0; i < n; i++)
    {
        free(arr[i].topic);
        free(arr[i].displayName);
        free(arr[i].value);
        free(arr[i].onValue);
        free(arr[i].offValue);
        free(arr[i].offPreset);
        free(arr[i].window);
    }
    free(arr);
}

static void free_serves(RcServe *arr, int n)
{
    for (int i = 0; i < n; i++)
    {
        free(arr[i].topic);
        free(arr[i].displayName);
        free(arr[i].serviceName);
        free(arr[i].offPreset);
        free(arr[i].offValue);
    }
    free(arr);
}

static void free_hotkeys(RcHotkey *arr, int n)
{
    for (int i = 0; i < n; i++)
    {
        free(arr[i].topic);
        free(arr[i].displayName);
        free(arr[i].onType);
        free(arr[i].onValue);
        free(arr[i].offType);
        free(arr[i].offValue);
    }
    free(arr);
}

static void topics_add(RC_Router *r, const char *topic)
{
    // 维护“需要订阅的 topic 列表”。
    // 注意：
    // - 这里保存的是指针（const char*），指向 r 内部拥有的字符串（dupstr0 的结果）。
    // - 因此 r->topics 只需要 free 指针数组本身，不需要逐个 free 字符串。
    if (!topic || !*topic)
        return;

    const char **narr = (const char **)realloc(r->topics, (size_t)(r->topicsCount + 1) * sizeof(const char *));
    if (!narr)
        return;
    r->topics = narr;
    r->topics[r->topicsCount++] = topic;
}

static bool is_on_off_payload(const char *payload)
{
    // payload 协议：
    // - "on" / "off" / "pause"
    // - "on#<n>" / "off#<n>"：携带一个整数值（主要用于亮度/音量/占位符替换等）。
    //
    // 注意：这里仅做“快速过滤”，严格格式校验由 parse_percent_payload_strict 完成。
    if (!payload)
        return false;
    return (_stricmp(payload, "on") == 0 || _stricmp(payload, "off") == 0 || _stricmp(payload, "pause") == 0 ||
            _strnicmp(payload, "on#", 3) == 0 || _strnicmp(payload, "off#", 4) == 0);
}

static bool parse_percent_payload_strict(const char *payload, const char **outBase, int *outValue, bool *outHasValue)
{
    // 严格解析 payload：
    // - 将 "on#42" 解析为 base="on", value=42, hasValue=true
    // - 将 "on" 解析为 base="on", hasValue=false
    // - 若是 "on#"、"on#abc" 等非法格式，返回 false。
    //
    // 设计动机：
    // - RouterHandle 的不同分支会复用 hasValue/value（例如亮度/音量百分比，或 {value} 占位符）。
    if (outBase)
        *outBase = payload ? payload : "";
    if (outValue)
        *outValue = 0;
    if (outHasValue)
        *outHasValue = false;

    if (!payload)
        return true;

    // Normalize simple commands.
    if (_stricmp(payload, "on") == 0)
    {
        if (outBase)
            *outBase = "on";
        return true;
    }
    if (_stricmp(payload, "off") == 0)
    {
        if (outBase)
            *outBase = "off";
        return true;
    }
    if (_stricmp(payload, "pause") == 0)
    {
        if (outBase)
            *outBase = "pause";
        return true;
    }

    if (_strnicmp(payload, "on#", 3) == 0)
    {
        if (outBase)
            *outBase = "on";
        const char *p = payload + 3;
        char *endp = NULL;
        long v = strtol(p, &endp, 10);
        if (!endp || endp == p || *endp != '\0')
            return false;
        if (outHasValue)
            *outHasValue = true;
        if (outValue)
            *outValue = (int)v;
        return true;
    }
    if (_strnicmp(payload, "off#", 4) == 0)
    {
        if (outBase)
            *outBase = "off";
        const char *p = payload + 4;
        char *endp = NULL;
        long v = strtol(p, &endp, 10);
        if (!endp || endp == p || *endp != '\0')
            return false;
        if (outHasValue)
            *outHasValue = true;
        if (outValue)
            *outValue = (int)v;
        return true;
    }

    return true;
}

static bool pid_is_alive(unsigned long pid)
{
    /*
     * 判断 pid 是否仍存活：
     * - OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) 成功且 GetExitCodeProcess==STILL_ACTIVE 视为存活。
     * - 若无权限/进程已退出导致 OpenProcess 失败，则认为不存活。
     */
    if (pid == 0)
        return false;
    HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, (DWORD)pid);
    if (!h)
        return false;
    DWORD code = 0;
    BOOL ok = GetExitCodeProcess(h, &code);
    CloseHandle(h);
    if (!ok)
        return false;
    return code == STILL_ACTIVE;
}

static void cmd_proc_cleanup_dead(RcCmdProc *p)
{
    // 原地压缩：移除已退出的 pid，保留仍存活的 pid。
    // 说明：不会收缩 cap（保持后续追加效率）。
    if (!p || p->count <= 0)
        return;
    int w = 0;
    for (int i = 0; i < p->count; i++)
    {
        if (pid_is_alive(p->pids[i]))
            p->pids[w++] = p->pids[i];
    }
    p->count = w;
}

static char *apply_value_placeholder(const char *in, bool hasValue, int value)
{
    // 将命令模板中的 "{value}" 替换为具体数值字符串。
    // 用途：
    // - command/serve 的 on/off 命令可写成："set-volume {value}"，再用 on#30 传入 30。
    //
    // 约束：
    // - 仅在 hasValue=true 时替换；否则原样复制。
    if (!in)
        in = "";

    if (!hasValue)
        return dupstr0(in);

    const char *needle = "{value}";
    size_t needleLen = strlen(needle);

    char valBuf[32];
    _snprintf(valBuf, sizeof(valBuf), "%d", value);
    valBuf[sizeof(valBuf) - 1] = 0;
    size_t valLen = strlen(valBuf);

    // Count occurrences
    size_t count = 0;
    for (const char *p = in; (p = strstr(p, needle)) != NULL; p += needleLen)
        count++;

    if (count == 0)
        return dupstr0(in);

    size_t inLen = strlen(in);
    size_t outLen = inLen + count * (valLen - needleLen);

    char *out = (char *)malloc(outLen + 1);
    if (!out)
        return NULL;

    const char *src = in;
    char *dst = out;
    while (1)
    {
        const char *hit = strstr(src, needle);
        if (!hit)
        {
            size_t tail = strlen(src);
            memcpy(dst, src, tail);
            dst += tail;
            break;
        }
        size_t seg = (size_t)(hit - src);
        memcpy(dst, src, seg);
        dst += seg;
        memcpy(dst, valBuf, valLen);
        dst += valLen;
        src = hit + needleLen;
    }
    *dst = 0;
    return out;
}

static char *normalize_powershell_command(const char *cmd)
{
    // PowerShell 命令最小规范化。
    // 典型坑：PowerShell 中 `curl` 是 Invoke-WebRequest 的别名，
    // 会导致用户写的 curl 命令与期望的 curl.exe 不一致。
    // 这里做一个最小替换：以 "curl " 或 "curl\t" 开头时改成 "curl.exe"。
    if (!cmd)
        cmd = "";

    // Minimal normalization: avoid PowerShell 'curl' alias.
    if (_strnicmp(cmd, "curl ", 5) == 0 || _strnicmp(cmd, "curl\t", 5) == 0)
    {
        size_t n = strlen(cmd);
        char *out = (char *)malloc(n + 5); // "curl.exe" adds 4 chars
        if (!out)
            return dupstr0(cmd);
        strcpy(out, "curl.exe");
        strcat(out, cmd + 4);
        return out;
    }

    return dupstr0(cmd);
}

static void load_builtins(RC_Router *r)
{
    // 加载内置功能的 topic 与启用开关。
    // - checkedXxx：来自 <name>_checked 布尔字段，决定是否订阅对应 topic。
    // - topicXxx：来自 <name> 字符串字段。
    //
    // 备注：
    // - 这里对字符串统一 dupstr0，确保 Router 生命周期内指针稳定。
    r->checkedComputer = cfg_bool(r->config, "Computer_checked", false);
    r->checkedScreen = cfg_bool(r->config, "screen_checked", false);
    r->checkedVolume = cfg_bool(r->config, "volume_checked", false);
    r->checkedSleep = cfg_bool(r->config, "sleep_checked", false);
    r->checkedMedia = cfg_bool(r->config, "media_checked", false);

    r->topicComputer = dupstr0(cfg_str(r->config, "Computer"));
    r->topicScreen = dupstr0(cfg_str(r->config, "screen"));
    r->topicVolume = dupstr0(cfg_str(r->config, "volume"));
    r->topicSleep = dupstr0(cfg_str(r->config, "sleep"));
    r->topicMedia = dupstr0(cfg_str(r->config, "media"));

    if (r->checkedComputer)
        topics_add(r, r->topicComputer);
    if (r->checkedScreen)
        topics_add(r, r->topicScreen);
    if (r->checkedVolume)
        topics_add(r, r->topicVolume);
    if (r->checkedSleep)
        topics_add(r, r->topicSleep);
    if (r->checkedMedia)
        topics_add(r, r->topicMedia);
}

static void load_applications(RC_Router *r)
{
    // 加载 application1..application49：
    // - applicationN: topic
    // - applicationN_checked: 是否启用
    // - applicationN_on_value / applicationN_off_value: 启动/关闭时执行路径或命令
    // - applicationN_off_preset: off 行为（kill/none/custom），默认 kill
    // - applicationN_directoryN: 兼容旧版 GUI 的字段命名（legacy）
    for (int i = 1; i < 50; i++)
    {
        char key[64];
        _snprintf(key, sizeof(key), "application%d", i);
        const char *topic = cfg_str(r->config, key);
        if (!topic || !*topic)
            continue;

        char checkedKey[80];
        _snprintf(checkedKey, sizeof(checkedKey), "%s_checked", key);
        if (!cfg_bool(r->config, checkedKey, false))
            continue;

        char onKey[96];
        char offKey[96];
        char offPresetKey[96];
        char dirKey[96];
        char nameKey[96];
        _snprintf(onKey, sizeof(onKey), "%s_on_value", key);
        _snprintf(offKey, sizeof(offKey), "%s_off_value", key);
        _snprintf(offPresetKey, sizeof(offPresetKey), "%s_off_preset", key);
        _snprintf(dirKey, sizeof(dirKey), "%s_directory%d", key, i); // legacy per-GUI naming
        _snprintf(nameKey, sizeof(nameKey), "%s_name", key);

        const char *onPath = cfg_str(r->config, onKey);
        const char *offPath = cfg_str(r->config, offKey);
        const char *offPreset = cfg_str(r->config, offPresetKey);
        const char *dirLegacy = cfg_str(r->config, dirKey);
        const char *dispName = cfg_str(r->config, nameKey);

        RcApp item;
        ZeroMemory(&item, sizeof(item));
        item.topic = dupstr0(topic);
        item.displayName = dupstr0(dispName);
        item.onPath = dupstr0((onPath && *onPath) ? onPath : (dirLegacy ? dirLegacy : ""));
        item.offPath = dupstr0(offPath);
        item.offPreset = dupstr0((offPreset && *offPreset) ? offPreset : "kill");

        RcApp *narr = (RcApp *)realloc(r->apps, (size_t)(r->appsCount + 1) * sizeof(RcApp));
        if (!narr)
        {
            free(item.topic);
            free(item.displayName);
            free(item.onPath);
            free(item.offPath);
            free(item.offPreset);
            continue;
        }
        r->apps = narr;
        r->apps[r->appsCount++] = item;

        topics_add(r, r->apps[r->appsCount - 1].topic);
    }
}

static void load_commands(RC_Router *r)
{
    // 加载 command1..command49（通常是 PowerShell 命令）：
    // - commandN: topic
    // - commandN_checked
    // - commandN_value: 兼容旧版（legacy）命令
    // - commandN_on_value / commandN_off_value: on/off 对应命令
    // - commandN_off_preset: interrupt/kill/none/custom，默认 kill
    // - commandN_window: show/hide，默认 show（决定 PowerShell 窗口行为）
    for (int i = 1; i < 50; i++)
    {
        char key[64];
        _snprintf(key, sizeof(key), "command%d", i);
        const char *topic = cfg_str(r->config, key);
        if (!topic || !*topic)
            continue;

        char checkedKey[80];
        _snprintf(checkedKey, sizeof(checkedKey), "%s_checked", key);
        if (!cfg_bool(r->config, checkedKey, false))
            continue;

        char valueKey[96];
        char onKey[96];
        char offKey[96];
        char offPresetKey[96];
        char windowKey[96];
        char nameKey[96];
        _snprintf(valueKey, sizeof(valueKey), "%s_value", key);
        _snprintf(onKey, sizeof(onKey), "%s_on_value", key);
        _snprintf(offKey, sizeof(offKey), "%s_off_value", key);
        _snprintf(offPresetKey, sizeof(offPresetKey), "%s_off_preset", key);
        _snprintf(windowKey, sizeof(windowKey), "%s_window", key);
        _snprintf(nameKey, sizeof(nameKey), "%s_name", key);

        RcCommand item;
        ZeroMemory(&item, sizeof(item));
        item.topic = dupstr0(topic);
        item.displayName = dupstr0(cfg_str(r->config, nameKey));
        item.value = dupstr0(cfg_str(r->config, valueKey));
        item.onValue = dupstr0(cfg_str(r->config, onKey));
        item.offValue = dupstr0(cfg_str(r->config, offKey));
        item.offPreset = dupstr0(cfg_str(r->config, offPresetKey));
        item.window = dupstr0(cfg_str(r->config, windowKey));
        if (!item.offPreset || !*item.offPreset)
        {
            free(item.offPreset);
            item.offPreset = dupstr0("kill");
        }
        if (!item.window || !*item.window)
        {
            free(item.window);
            item.window = dupstr0("show");
        }

        RcCommand *narr = (RcCommand *)realloc(r->cmds, (size_t)(r->cmdsCount + 1) * sizeof(RcCommand));
        if (!narr)
        {
            free(item.topic);
            free(item.displayName);
            free(item.value);
            free(item.onValue);
            free(item.offValue);
            free(item.offPreset);
            free(item.window);
            continue;
        }
        r->cmds = narr;
        r->cmds[r->cmdsCount++] = item;

        topics_add(r, r->cmds[r->cmdsCount - 1].topic);
    }
}

static void load_serves(RC_Router *r)
{
    // 加载 serve1..serve49（Windows 服务控制）：
    // - serveN: topic
    // - serveN_checked
    // - serveN_value: 服务名
    // - serveN_off_preset: stop/none/custom，默认 stop
    // - serveN_off_value: preset=custom 时执行的命令（可包含 {value}）
    for (int i = 1; i < 50; i++)
    {
        char key[64];
        _snprintf(key, sizeof(key), "serve%d", i);
        const char *topic = cfg_str(r->config, key);
        if (!topic || !*topic)
            continue;

        char checkedKey[80];
        _snprintf(checkedKey, sizeof(checkedKey), "%s_checked", key);
        if (!cfg_bool(r->config, checkedKey, false))
            continue;

        char valueKey[96];
        char offPresetKey[96];
        char offValueKey[96];
        char nameKey[96];
        _snprintf(valueKey, sizeof(valueKey), "%s_value", key);
        _snprintf(offPresetKey, sizeof(offPresetKey), "%s_off_preset", key);
        _snprintf(offValueKey, sizeof(offValueKey), "%s_off_value", key);
        _snprintf(nameKey, sizeof(nameKey), "%s_name", key);

        RcServe item;
        ZeroMemory(&item, sizeof(item));
        item.topic = dupstr0(topic);
        item.displayName = dupstr0(cfg_str(r->config, nameKey));
        item.serviceName = dupstr0(cfg_str(r->config, valueKey));
        item.offPreset = dupstr0(cfg_str(r->config, offPresetKey));
        item.offValue = dupstr0(cfg_str(r->config, offValueKey));
        if (!item.offPreset || !*item.offPreset)
        {
            free(item.offPreset);
            item.offPreset = dupstr0("stop");
        }

        RcServe *narr = (RcServe *)realloc(r->serves, (size_t)(r->servesCount + 1) * sizeof(RcServe));
        if (!narr)
        {
            free(item.topic);
            free(item.displayName);
            free(item.serviceName);
            free(item.offPreset);
            free(item.offValue);
            continue;
        }
        r->serves = narr;
        r->serves[r->servesCount++] = item;

        topics_add(r, r->serves[r->servesCount - 1].topic);
    }
}

static void load_hotkeys(RC_Router *r)
{
    // 加载 hotkey1..hotkey49（模拟键盘/热键）：
    // - hotkeyN: topic
    // - hotkeyN_checked
    // - hotkeyN_on_type/on_value: on 时执行的输入类型与内容
    // - hotkeyN_off_type/off_value: off 时执行（可为 "none"）
    // - hotkeyN_char_delay_ms: 字符间延迟（用于避免某些目标应用丢键）
    for (int i = 1; i < 50; i++)
    {
        char key[64];
        _snprintf(key, sizeof(key), "hotkey%d", i);
        const char *topic = cfg_str(r->config, key);
        if (!topic || !*topic)
            continue;

        char checkedKey[80];
        _snprintf(checkedKey, sizeof(checkedKey), "%s_checked", key);
        if (!cfg_bool(r->config, checkedKey, false))
            continue;

        char onTypeKey[96];
        char onValueKey[96];
        char offTypeKey[96];
        char offValueKey[96];
        char delayKey[96];
        char nameKey[96];
        _snprintf(onTypeKey, sizeof(onTypeKey), "%s_on_type", key);
        _snprintf(onValueKey, sizeof(onValueKey), "%s_on_value", key);
        _snprintf(offTypeKey, sizeof(offTypeKey), "%s_off_type", key);
        _snprintf(offValueKey, sizeof(offValueKey), "%s_off_value", key);
        _snprintf(delayKey, sizeof(delayKey), "%s_char_delay_ms", key);
        _snprintf(nameKey, sizeof(nameKey), "%s_name", key);

        RcHotkey item;
        ZeroMemory(&item, sizeof(item));
        item.topic = dupstr0(topic);
        item.displayName = dupstr0(cfg_str(r->config, nameKey));
        item.onType = dupstr0(cfg_str(r->config, onTypeKey));
        item.onValue = dupstr0(cfg_str(r->config, onValueKey));
        item.offType = dupstr0(cfg_str(r->config, offTypeKey));
        item.offValue = dupstr0(cfg_str(r->config, offValueKey));
        item.charDelayMs = cfg_int(r->config, delayKey, 0);

        if (!item.onType || !*item.onType)
        {
            free(item.onType);
            item.onType = dupstr0("keyboard");
        }
        if (!item.offType || !*item.offType)
        {
            free(item.offType);
            item.offType = dupstr0("none");
        }

        RcHotkey *narr = (RcHotkey *)realloc(r->hotkeys, (size_t)(r->hotkeysCount + 1) * sizeof(RcHotkey));
        if (!narr)
        {
            free(item.topic);
            free(item.displayName);
            free(item.onType);
            free(item.onValue);
            free(item.offType);
            free(item.offValue);
            continue;
        }
        r->hotkeys = narr;
        r->hotkeys[r->hotkeysCount++] = item;

        topics_add(r, r->hotkeys[r->hotkeysCount - 1].topic);
    }
}

RC_Router *RC_RouterCreate(RC_Json *configRoot)
{
    // 创建 Router：
    // - 入参 configRoot 由上层解析得到（RC_Json*）。
    // - Router 接管该 JSON 的所有权（Destroy 时会 RC_JsonFree）。
    // - 创建时一次性把所有订阅 topic 与动作表加载到内存，运行期只做匹配与执行。
    if (!configRoot || !RC_JsonIsObject(configRoot))
        return NULL;

    RC_Router *r = (RC_Router *)calloc(1, sizeof(RC_Router));
    if (!r)
        return NULL;

    r->config = configRoot;

    // notify: 0/1（由 RC-GUI 的“通知提示”开关写入）
    r->notifyEnabled = (cfg_int(r->config, "notify", 1) != 0);

    load_builtins(r);
    load_applications(r);
    load_commands(r);
    load_serves(r);
    load_hotkeys(r);

    return r;
}

void RC_RouterNotifyUtf8(RC_Router *r, const char *titleUtf8, const char *messageUtf8)
{
    if (!r || !r->notifyEnabled)
        return;
    notify_show_utf8(titleUtf8 ? titleUtf8 : "", messageUtf8 ? messageUtf8 : "");
}

void RC_RouterDestroy(RC_Router *r)
{
    // 释放 Router：
    // - 释放 config（owned）
    // - 释放各类动作表（applications/commands/serves/hotkeys）中 dup 出来的字符串
    // - 释放命令 PID 跟踪表（用于 off_preset=kill/interrupt）
    // - 释放 topics 指针数组
    if (!r)
        return;

    RC_JsonFree(r->config);

    free(r->topicComputer);
    free(r->topicScreen);
    free(r->topicVolume);
    free(r->topicSleep);
    free(r->topicMedia);

    free_apps(r->apps, r->appsCount);
    free_cmds(r->cmds, r->cmdsCount);
    free_serves(r->serves, r->servesCount);
    free_hotkeys(r->hotkeys, r->hotkeysCount);

    for (int i = 0; i < r->cmdProcsCount; i++)
    {
        free(r->cmdProcs[i].topic);
        free(r->cmdProcs[i].pids);
    }
    free(r->cmdProcs);

    free(r->topics);
    // best-effort：主程序退出前清理通知图标，避免托盘残留。
    notify_shutdown();
    free(r);
}

static int clamp0_100(int v)
{
    if (v < 0)
        return 0;
    if (v > 100)
        return 100;
    return v;
}

static void router_notify_action(const RC_Router *r, const char *topicUtf8, const char *payloadUtf8)
{
    if (!r || !r->notifyEnabled)
        return;

    const char *base = NULL;
    int value = 0;
    bool hasValue = false;
    bool payloadOk = parse_percent_payload_strict(payloadUtf8 ? payloadUtf8 : "", &base, &value, &hasValue);
    if (!payloadOk)
    {
        base = payloadUtf8 ? payloadUtf8 : "";
        hasValue = false;
        value = 0;
    }

    char title[64];
    char msg[256];
    strncpy_s(title, sizeof(title), "远程控制", _TRUNCATE);
    msg[0] = 0;

    // ===== 内置主题：更友好文本 =====
    if (r->checkedComputer && r->topicComputer && topicUtf8 && strcmp(topicUtf8, r->topicComputer) == 0)
    {
        const char *onAction = cfg_str(r->config, "computer_on_action");
        const char *offAction = cfg_str(r->config, "computer_off_action");
        int onDelay = cfg_int(r->config, "computer_on_delay", 0);
        int offDelay = cfg_int(r->config, "computer_off_delay", 60);

        const char *act = (_stricmp(base, "on") == 0) ? (onAction ? onAction : "lock") : (offAction ? offAction : "none");
        int delay = (_stricmp(base, "on") == 0) ? onDelay : offDelay;

        const char *actZh = "动作";
        if (_stricmp(act, "lock") == 0)
            actZh = "锁屏";
        else if (_stricmp(act, "shutdown") == 0)
            actZh = "关机";
        else if (_stricmp(act, "restart") == 0)
            actZh = "重启";
        else if (_stricmp(act, "logoff") == 0)
            actZh = "注销";
        else if (_stricmp(act, "none") == 0)
            actZh = "无动作";

        if (delay > 0 && _stricmp(act, "none") != 0)
            _snprintf(msg, sizeof(msg), "电脑：%s（延迟 %d 秒）", actZh, delay);
        else
            _snprintf(msg, sizeof(msg), "电脑：%s", actZh);
    }
    else if (r->checkedScreen && r->topicScreen && topicUtf8 && strcmp(topicUtf8, r->topicScreen) == 0)
    {
        int percent = 0;
        if (_stricmp(base, "off") == 0)
            percent = 0;
        else if (_stricmp(base, "on") == 0)
            percent = hasValue ? clamp0_100(value) : 100;
        _snprintf(msg, sizeof(msg), "屏幕亮度：%d%%", percent);
    }
    else if (r->checkedVolume && r->topicVolume && topicUtf8 && strcmp(topicUtf8, r->topicVolume) == 0)
    {
        int percent = 0;
        if (_stricmp(base, "off") == 0 || _stricmp(base, "pause") == 0)
            percent = 0;
        else if (_stricmp(base, "on") == 0)
            percent = hasValue ? clamp0_100(value) : 100;
        _snprintf(msg, sizeof(msg), "音量：%d%%", percent);
    }
    else if (r->checkedSleep && r->topicSleep && topicUtf8 && strcmp(topicUtf8, r->topicSleep) == 0)
    {
        const char *onAction = cfg_str(r->config, "sleep_on_action");
        const char *offAction = cfg_str(r->config, "sleep_off_action");
        int onDelay = cfg_int(r->config, "sleep_on_delay", 0);
        int offDelay = cfg_int(r->config, "sleep_off_delay", 0);

        const char *act = (_stricmp(base, "on") == 0) ? (onAction ? onAction : "sleep") : (offAction ? offAction : "none");
        int delay = (_stricmp(base, "on") == 0) ? onDelay : offDelay;

        const char *actZh = "动作";
        if (_stricmp(act, "sleep") == 0)
            actZh = "睡眠";
        else if (_stricmp(act, "hibernate") == 0)
            actZh = "休眠";
        else if (_stricmp(act, "display_off") == 0)
            actZh = "关闭显示器";
        else if (_stricmp(act, "display_on") == 0)
            actZh = "开启显示器";
        else if (_stricmp(act, "lock") == 0)
            actZh = "锁屏";
        else if (_stricmp(act, "none") == 0)
            actZh = "无动作";

        if (delay > 0 && _stricmp(act, "none") != 0)
            _snprintf(msg, sizeof(msg), "睡眠：%s（延迟 %d 秒）", actZh, delay);
        else
            _snprintf(msg, sizeof(msg), "睡眠：%s", actZh);
    }
    else if (r->checkedMedia && r->topicMedia && topicUtf8 && strcmp(topicUtf8, r->topicMedia) == 0)
    {
        const char *mediaZh = "媒体";
        if (_stricmp(base, "off") == 0)
            mediaZh = "下一首";
        else if (_stricmp(base, "on") == 0)
        {
            if (hasValue)
            {
                int v = clamp0_100(value);
                if (v <= 33)
                    mediaZh = "下一首";
                else if (v <= 66)
                    mediaZh = "播放/暂停";
                else
                    mediaZh = "上一首";
            }
            else
            {
                mediaZh = "上一首";
            }
        }
        else if (_stricmp(base, "pause") == 0)
            mediaZh = "播放/暂停";
        _snprintf(msg, sizeof(msg), "媒体：%s", mediaZh);
    }
    else
    {
        // ===== 可配置主题：apps/cmds/services/hotkeys =====
        const char *kind = NULL;
        const char *label = NULL;

        if (!kind)
        {
            for (int i = 0; i < r->appsCount; i++)
            {
                if (r->apps[i].topic && topicUtf8 && strcmp(topicUtf8, r->apps[i].topic) == 0)
                {
                    kind = "应用";
                    label = (r->apps[i].displayName && *r->apps[i].displayName) ? r->apps[i].displayName : r->apps[i].topic;
                    break;
                }
            }
        }

        if (!kind)
        {
            for (int i = 0; i < r->cmdsCount; i++)
            {
                if (r->cmds[i].topic && topicUtf8 && strcmp(topicUtf8, r->cmds[i].topic) == 0)
                {
                    kind = "命令";
                    label = (r->cmds[i].displayName && *r->cmds[i].displayName) ? r->cmds[i].displayName : r->cmds[i].topic;
                    break;
                }
            }
        }

        if (!kind)
        {
            for (int i = 0; i < r->servesCount; i++)
            {
                if (r->serves[i].topic && topicUtf8 && strcmp(topicUtf8, r->serves[i].topic) == 0)
                {
                    kind = "服务";
                    if (r->serves[i].displayName && *r->serves[i].displayName)
                        label = r->serves[i].displayName;
                    else
                        label = (r->serves[i].serviceName && *r->serves[i].serviceName) ? r->serves[i].serviceName : r->serves[i].topic;
                    break;
                }
            }
        }

        if (!kind)
        {
            for (int i = 0; i < r->hotkeysCount; i++)
            {
                if (r->hotkeys[i].topic && topicUtf8 && strcmp(topicUtf8, r->hotkeys[i].topic) == 0)
                {
                    kind = "热键";
                    label = (r->hotkeys[i].displayName && *r->hotkeys[i].displayName) ? r->hotkeys[i].displayName : r->hotkeys[i].topic;
                    break;
                }
            }
        }

        if (kind)
        {
            const char *opZh = "触发";
            if (_stricmp(base, "on") == 0)
                opZh = "开启";
            else if (_stricmp(base, "off") == 0)
                opZh = "关闭";
            else if (_stricmp(base, "pause") == 0)
                opZh = "暂停";

            if (hasValue)
                _snprintf(msg, sizeof(msg), "%s：%s（%s %d%%）", kind, label ? label : "", opZh, clamp0_100(value));
            else
                _snprintf(msg, sizeof(msg), "%s：%s（%s）", kind, label ? label : "", opZh);
        }
        else
        {
            _snprintf(msg, sizeof(msg), "主题：%s（%s）", topicUtf8 ? topicUtf8 : "", payloadUtf8 ? payloadUtf8 : "");
        }
    }

    msg[sizeof(msg) - 1] = 0;
    title[sizeof(title) - 1] = 0;
    notify_show_utf8(title, msg);
}

const char *const *RC_RouterGetTopics(const RC_Router *r, int *outCount)
{
    // 返回需要订阅的 topic 列表（指针数组）。
    // 说明：
    // - 返回的指针在 Router 生命周期内有效。
    // - outCount 返回数组长度。
    if (outCount)
        *outCount = r ? r->topicsCount : 0;
    return r ? (const char *const *)r->topics : NULL;
}

typedef struct
{
    char *action;
    int delay;
} SleepTask;

static DWORD WINAPI sleep_thread(LPVOID p)
{
    SleepTask *t = (SleepTask *)p;
    if (!t)
        return 0;
    if (t->delay > 0)
        Sleep((DWORD)t->delay * 1000);
    RC_ActionPerformSleep(t->action);
    free(t->action);
    free(t);
    return 0;
}

static void schedule_sleep_action(const char *action, int delaySeconds)
{
    // sleep_* 动作支持延迟执行：
    // - 通过 CreateThread 在后台 Sleep(delay) 后执行 RC_ActionPerformSleep。
    // - 线程句柄立即 CloseHandle，不做 join（fire-and-forget）。
    //
    // 注意：
    // - 这里不做任务去重；如果短时间收到多次消息，会排队多个线程。
    SleepTask *t = (SleepTask *)calloc(1, sizeof(SleepTask));
    if (!t)
        return;
    t->action = dupstr0(action);
    t->delay = delaySeconds;

    HANDLE h = CreateThread(NULL, 0, sleep_thread, t, 0, NULL);
    if (h)
        CloseHandle(h);
    else
    {
        free(t->action);
        free(t);
    }
}

static bool topic_eq(const char *a, const char *b)
{
    if (!a || !b)
        return false;
    return strcmp(a, b) == 0;
}

void RC_RouterHandle(RC_Router *r, const char *topicUtf8, const char *payloadUtf8)
{
    // RouterHandle：根据 topic 与 payload 分发动作。
    //
    // payload 解析：
    // - base: "on"/"off"/"pause"
    // - hasValue/value: 来自 "on#<n>" / "off#<n>" 的数值
    //
    // 分发顺序（从可配置到内置）：
    // 1) Applications：启动/关闭应用（off 可 preset=kill 或自定义脚本）
    // 2) Commands：PowerShell 命令（支持 window=hide 与 PID 跟踪，off 可 interrupt/kill）
    // 3) Services：Windows 服务 start/stop 或自定义命令
    // 4) Built-ins：电脑/屏幕/音量/睡眠/媒体等内置功能（读取对应 *_action 与 *_delay）
    // 5) Hotkeys：模拟输入
    //
    // 设计要点：
    // - 匹配到某个 topic 后立即 return，保证同一消息只触发一个动作。
    // - 对不认识的 payload/topic 输出告警日志，便于排障。
    if (!r || !topicUtf8 || !payloadUtf8)
        return;

    if (!is_on_off_payload(payloadUtf8))
    {
        RC_LogWarn("已忽略 payload：%s (topic=%s)", payloadUtf8, topicUtf8);
        return;
    }

    const char *base = NULL;
    int value = 0;
    bool hasValue = false;
    if (!parse_percent_payload_strict(payloadUtf8, &base, &value, &hasValue))
    {
        RC_LogWarn("payload 格式无效：%s (topic=%s)", payloadUtf8, topicUtf8);
        return;
    }

    // 1) Applications
    for (int i = 0; i < r->appsCount; i++)
    {
        RcApp *a = &r->apps[i];
        if (!topic_eq(topicUtf8, a->topic))
            continue;

        if (_stricmp(base, "on") == 0)
        {
            RC_LogInfo("应用开启：%s => %s", a->topic, a->onPath);
            RC_ActionRunProgramUtf8(a->onPath);
        }
        else if (_stricmp(base, "off") == 0)
        {
            if (a->offPath && *a->offPath)
            {
                RC_LogInfo("应用关闭(自定义)：%s => %s", a->topic, a->offPath);
                RC_ActionRunProgramUtf8(a->offPath);
            }
            else
            {
                const char *preset = (a->offPreset && *a->offPreset) ? a->offPreset : "kill";
                if (_stricmp(preset, "none") == 0 || _stricmp(preset, "custom") == 0)
                {
                    RC_LogInfo("应用关闭预设=none：%s", a->topic);
                }
                else
                {
                    RC_LogInfo("应用关闭(kill)：%s => %s", a->topic, a->onPath);
                    RC_ActionKillByPathUtf8(a->onPath);
                }
            }
        }
        else
        {
            // For matched app topics, ignore unknown payloads.
            RC_LogInfo("已忽略应用 payload：%s (topic=%s)", payloadUtf8, a->topic);
        }

        router_notify_action(r, topicUtf8, payloadUtf8);
        return;
    }

    // 2) Commands (PowerShell)
    for (int i = 0; i < r->cmdsCount; i++)
    {
        RcCommand *c = &r->cmds[i];
        if (!topic_eq(topicUtf8, c->topic))
            continue;

        // window 字段：决定 PowerShell 窗口行为。
        // - hide：隐藏窗口（更像后台任务）；keep=false 表示不保持窗口。
        // - show：显示窗口（便于调试）。
        const char *window = (c->window && *c->window) ? c->window : "show";
        bool hide = (_stricmp(window, "hide") == 0);
        bool keep = !hide;

        if (_stricmp(base, "on") == 0)
        {
            if (hasValue && (value < 0 || value > 100))
            {
                RC_LogWarn("命令百分比超出范围 0-100：%d (topic=%s)", value, c->topic);
                return;
            }
            // 命令选择优先级：on_value 优先，其次 fallback 到 legacy value。
            const char *raw = (c->onValue && *c->onValue) ? c->onValue : c->value;
            char *applied = apply_value_placeholder(raw, hasValue, value);
            char *norm = normalize_powershell_command(applied);
            RC_LogInfo("命令开启：%s (window=%s)", c->topic, window);
            unsigned long pid = 0;
            bool ok = RC_ActionRunPowershellCommandUtf8Ex(norm, hide, keep, &pid);
            if (ok && pid != 0)
            {
                // 记录子进程 PID：用于 off_preset=kill/interrupt 时进行“定向结束”。
                // 注意：这里按 topic 维度累计 pid，不做去重；
                // 这是为了支持“同一 topic 多次启动多个实例”，off 时可按策略逐个处理。
                RcCmdProc *p = cmd_proc_get_or_create(r, c->topic);
                cmd_proc_add_pid(p, pid);
            }
            free(norm);
            free(applied);
        }
        else if (_stricmp(base, "off") == 0)
        {
            if (hasValue && (value < 0 || value > 100))
            {
                RC_LogWarn("命令百分比超出范围 0-100：%d (topic=%s)", value, c->topic);
                return;
            }
            if (c->offValue && *c->offValue)
            {
                char *applied = apply_value_placeholder(c->offValue, hasValue, value);
                char *norm = normalize_powershell_command(applied);
                RC_LogInfo("命令关闭(自定义)：%s (window=%s)", c->topic, window);
                unsigned long pid = 0;
                bool ok = RC_ActionRunPowershellCommandUtf8Ex(norm, hide, keep, &pid);
                if (ok && pid != 0)
                {
                    RcCmdProc *p = cmd_proc_get_or_create(r, c->topic);
                    cmd_proc_add_pid(p, pid);
                }
                free(norm);
                free(applied);
            }
            else
            {
                // off_preset 说明：
                // - none：不做任何事
                // - custom：应提供 off_value（否则警告）
                // - interrupt：优先向最新 PID 发送 CTRL_BREAK（适合 Python/控制台程序）
                // - kill（默认）：结束所有记录的 PID（Terminate/Taskkill /F）
                const char *preset = (c->offPreset && *c->offPreset) ? c->offPreset : "kill";

                if (_stricmp(preset, "none") == 0)
                {
                    RC_LogInfo("命令关闭预设=none：%s", c->topic);
                }
                else if (_stricmp(preset, "custom") == 0)
                {
                    RC_LogWarn("命令关闭预设=custom 但 off_value 为空：%s", c->topic);
                }
                else
                {
                    RcCmdProc *p = cmd_proc_get_or_create(r, c->topic);
                    if (!p)
                    {
                        RC_LogWarn("命令关闭预设=%s 但没有已登记的 PID：%s", preset, c->topic);
                    }
                    else
                    {
                        // off_preset=kill/interrupt：依赖 cmdProcs 表。
                        // 先清理“已经退出”的 pid，避免对已退出进程反复尝试终止。
                        cmd_proc_cleanup_dead(p);
                        if (p->count == 0)
                        {
                            RC_LogInfo("命令[%s] 记录的所有 PID 都已退出", c->topic);
                        }
                        else if (_stricmp(preset, "interrupt") == 0)
                        {
                            // Python: interrupt only the latest alive pid.
                            unsigned long targetPid = p->pids[p->count - 1];
                            RC_LogInfo("命令[%s] 中断最新 PID=%lu", c->topic, targetPid);

                            bool sent = RC_ActionSendCtrlBreak(targetPid);
                            if (!sent)
                                sent = RC_ActionSendCtrlBreakNoAttach(targetPid);

                            if (sent)
                            {
                                // Python: if CTRL_BREAK was sent, don't escalate to kill here.
                                cmd_proc_cleanup_dead(p);

                                router_notify_action(r, topicUtf8, payloadUtf8);
                                return;
                            }

                            // Python fallback chain: terminate -> taskkill (no /F)
                            if (!RC_ActionTerminatePid(targetPid))
                                RC_ActionTaskkillPid(targetPid);
                            cmd_proc_cleanup_dead(p);
                        }
                        else
                        {
                            // Default: kill all recorded pids.
                            RC_LogInfo("命令关闭(kill)：%s (pids=%d)", c->topic, p->count);
                            for (int k = 0; k < p->count; k++)
                            {
                                unsigned long pid = p->pids[k];
                                RC_LogInfo("命令[%s] kill PID=%lu", c->topic, pid);
                                if (RC_ActionTerminatePid(pid))
                                {
                                    RC_LogInfo("命令[%s] 终止成功 PID=%lu", c->topic, pid);
                                }
                                else
                                {
                                    bool ok = RC_ActionTaskkillPidForce(pid);
                                    RC_LogInfo("命令[%s] taskkill /F %s PID=%lu", c->topic, ok ? "成功" : "失败", pid);
                                }
                            }
                            // kill 分支执行完毕后清空表：避免下一次 off 误处理旧 pid。
                            cmd_proc_clear(p);
                        }
                    }
                }
            }
        }
        else
        {
            RC_LogInfo("已忽略命令 payload：%s (topic=%s)", payloadUtf8, c->topic);
        }

        router_notify_action(r, topicUtf8, payloadUtf8);
        return;
    }

    // 3) Services
    for (int i = 0; i < r->servesCount; i++)
    {
        RcServe *s = &r->serves[i];
        if (!topic_eq(topicUtf8, s->topic))
            continue;

        if (_stricmp(base, "on") == 0)
        {
            RC_LogInfo("服务启动：%s => %s", s->topic, s->serviceName);
            RC_ActionServiceStartUtf8(s->serviceName);
        }
        else if (_stricmp(base, "off") == 0)
        {
            const char *preset = (s->offPreset && *s->offPreset) ? s->offPreset : "stop";
            if (_stricmp(preset, "none") == 0)
            {
                RC_LogInfo("服务关闭预设=none：%s", s->topic);
            }
            else if (_stricmp(preset, "custom") == 0)
            {
                if (s->offValue && *s->offValue)
                {
                    char *applied = apply_value_placeholder(s->offValue, hasValue, value);
                    char *norm = normalize_powershell_command(applied);
                    RC_LogInfo("服务关闭：执行自定义命令：%s", s->topic);
                    RC_ActionRunPowershellCommandUtf8(norm, false, true);
                    free(norm);
                    free(applied);
                }
                else
                {
                    RC_LogWarn("服务关闭预设=custom 但命令为空：%s", s->topic);
                }
            }
            else
            {
                RC_LogInfo("服务停止：%s => %s", s->topic, s->serviceName);
                RC_ActionServiceStopUtf8(s->serviceName);
            }
        }
        else
        {
            RC_LogInfo("已忽略服务 payload：%s (topic=%s)", payloadUtf8, s->topic);
        }

        router_notify_action(r, topicUtf8, payloadUtf8);
        return;
    }

    // 4) Built-ins
    if (r->checkedComputer && r->topicComputer && topic_eq(topicUtf8, r->topicComputer))
    {
        // 电脑内置动作：
        // - computer_on_action / computer_off_action：例如 lock/shutdown/restart/sleep...
        // - computer_on_delay / computer_off_delay：延迟秒数
        //
        // 注意：这里会给 off_delay 一个默认值 60 秒（与原项目行为一致）。
        const char *onAction = cfg_str(r->config, "computer_on_action");
        const char *offAction = cfg_str(r->config, "computer_off_action");
        int onDelay = cfg_int(r->config, "computer_on_delay", 0);
        int offDelay = cfg_int(r->config, "computer_off_delay", 60);
        if (_stricmp(base, "on") == 0)
            RC_ActionPerformComputer(onAction ? onAction : "lock", onDelay);
        else if (_stricmp(base, "off") == 0)
            RC_ActionPerformComputer(offAction ? offAction : "none", offDelay);
        else
            RC_LogWarn("未知电脑指令：%s", payloadUtf8);

        router_notify_action(r, topicUtf8, payloadUtf8);
        return;
    }

    if (r->checkedScreen && r->topicScreen && topic_eq(topicUtf8, r->topicScreen))
    {
        const char *mode = cfg_str(r->config, "brightness_mode");

        if (_stricmp(base, "off") == 0)
        {
            if (mode && _stricmp(mode, "twinkle_tray") == 0)
            {
                const char *path = cfg_str(r->config, "twinkle_tray_path");
                const char *tmode = cfg_str(r->config, "twinkle_tray_target_mode");
                const char *tval = cfg_str(r->config, "twinkle_tray_target_value");
                bool overlay = cfg_bool(r->config, "twinkle_tray_overlay", true);
                bool panel = cfg_bool(r->config, "twinkle_tray_panel", false);
                if (RC_ActionSetBrightnessTwinkleTrayPercentUtf8(0, path, tmode, tval, overlay, panel))
                {
                    router_notify_action(r, topicUtf8, payloadUtf8);
                    return;
                }
                RC_LogWarn("Twinkle Tray 亮度调整失败；回退到 DDC/CI");
            }
            RC_ActionSetBrightnessPercent(0);
        }
        else if (_stricmp(base, "on") == 0)
        {
            if (hasValue)
            {
                if (value < 0 || value > 100)
                {
                    RC_LogWarn("亮度百分比超出范围 0-100：%d (topic=%s)", value, r->topicScreen);
                    return;
                }

                if (mode && _stricmp(mode, "twinkle_tray") == 0)
                {
                    const char *path = cfg_str(r->config, "twinkle_tray_path");
                    const char *tmode = cfg_str(r->config, "twinkle_tray_target_mode");
                    const char *tval = cfg_str(r->config, "twinkle_tray_target_value");
                    bool overlay = cfg_bool(r->config, "twinkle_tray_overlay", true);
                    bool panel = cfg_bool(r->config, "twinkle_tray_panel", false);
                    if (RC_ActionSetBrightnessTwinkleTrayPercentUtf8(value, path, tmode, tval, overlay, panel))
                    {
                        router_notify_action(r, topicUtf8, payloadUtf8);
                        return;
                    }
                    RC_LogWarn("Twinkle Tray 亮度调整失败；回退到 DDC/CI");
                }

                RC_ActionSetBrightnessPercent(value);
            }
            else
            {
                if (mode && _stricmp(mode, "twinkle_tray") == 0)
                {
                    const char *path = cfg_str(r->config, "twinkle_tray_path");
                    const char *tmode = cfg_str(r->config, "twinkle_tray_target_mode");
                    const char *tval = cfg_str(r->config, "twinkle_tray_target_value");
                    bool overlay = cfg_bool(r->config, "twinkle_tray_overlay", true);
                    bool panel = cfg_bool(r->config, "twinkle_tray_panel", false);
                    if (RC_ActionSetBrightnessTwinkleTrayPercentUtf8(100, path, tmode, tval, overlay, panel))
                    {
                        router_notify_action(r, topicUtf8, payloadUtf8);
                        return;
                    }
                    RC_LogWarn("Twinkle Tray 亮度调整失败；回退到 DDC/CI");
                }

                RC_ActionSetBrightnessPercent(100);
            }
        }
        else
            RC_LogWarn("未知屏幕指令：%s", payloadUtf8);

        router_notify_action(r, topicUtf8, payloadUtf8);
        return;
    }

    if (r->checkedVolume && r->topicVolume && topic_eq(topicUtf8, r->topicVolume))
    {
        if (_stricmp(base, "off") == 0)
            RC_ActionSetVolumePercent(0);
        else if (_stricmp(base, "on") == 0)
        {
            if (hasValue)
            {
                if (value < 0 || value > 100)
                {
                    RC_LogWarn("音量百分比超出范围 0-100：%d (topic=%s)", value, r->topicVolume);
                    return;
                }
                RC_ActionSetVolumePercent(value);
            }
            else
                RC_ActionSetVolumePercent(100);
        }
        else if (_stricmp(base, "pause") == 0)
            RC_ActionSetVolumePercent(0);
        else
            RC_LogWarn("未知音量指令：%s", payloadUtf8);

        router_notify_action(r, topicUtf8, payloadUtf8);
        return;
    }

    if (r->checkedSleep && r->topicSleep && topic_eq(topicUtf8, r->topicSleep))
    {
        const char *onAction = cfg_str(r->config, "sleep_on_action");
        const char *offAction = cfg_str(r->config, "sleep_off_action");
        int onDelay = cfg_int(r->config, "sleep_on_delay", 0);
        int offDelay = cfg_int(r->config, "sleep_off_delay", 0);

        if (_stricmp(base, "on") == 0)
        {
            if (onDelay > 0)
                schedule_sleep_action(onAction ? onAction : "sleep", onDelay);
            else
                RC_ActionPerformSleep(onAction ? onAction : "sleep");
        }
        else if (_stricmp(base, "off") == 0)
        {
            if (offDelay > 0)
                schedule_sleep_action(offAction ? offAction : "none", offDelay);
            else
                RC_ActionPerformSleep(offAction ? offAction : "none");
        }
        else
            RC_LogWarn("未知睡眠指令：%s", payloadUtf8);

        router_notify_action(r, topicUtf8, payloadUtf8);
        return;
    }

    if (r->checkedMedia && r->topicMedia && topic_eq(topicUtf8, r->topicMedia))
    {
        RC_ActionMediaCommand(payloadUtf8);

        router_notify_action(r, topicUtf8, payloadUtf8);
        return;
    }

    // 5) Hotkeys
    for (int i = 0; i < r->hotkeysCount; i++)
    {
        RcHotkey *h = &r->hotkeys[i];
        if (!topic_eq(topicUtf8, h->topic))
            continue;

        if (_stricmp(base, "on") == 0)
            RC_ActionHotkey(h->onType, h->onValue, h->charDelayMs);
        else if (_stricmp(base, "off") == 0)
            RC_ActionHotkey(h->offType, h->offValue, h->charDelayMs);
        else
            RC_LogInfo("已忽略热键 payload：%s (topic=%s)", payloadUtf8, h->topic);

        router_notify_action(r, topicUtf8, payloadUtf8);
        return;
    }

    RC_LogWarn("未知主题：%s", topicUtf8);
}
