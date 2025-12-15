/*
 * rc_actions.c
 *
 * 动作执行实现：将配置/指令中的字符串动作映射为 Windows 行为。
 *
 * 核心实现手段：
 * - CreateProcessW：执行 cmd.exe /c ... 或 PowerShell，支持隐藏窗口（CREATE_NO_WINDOW）。
 * - ShellExecuteW：打开程序/URL（部分动作）。
 * - LockWorkStation：锁屏。
 * - Core Audio (MMDevice/IAudioEndpointVolume)：音量控制。
 * - Dxva2/MonitorConfiguration：部分亮度路径（硬件支持依赖较强）。
 * - Twinkle Tray CLI：在 Windows 下更稳定的亮度设置路径（需要安装/运行）。
 * - 服务控制：SCM API（OpenSCManager/OpenService/StartService/ControlService）。
 * - 进程终止：taskkill、TerminateProcess、CTRL_BREAK_EVENT。
 *
 * 注意：本文件大量与系统权限/UAC 相关；失败时会通过 rc_log 记录 GetLastError() 便于定位。
 */

#include "rc_actions.h"

#include "rc_log.h"
#include "rc_utf.h"

#include <windows.h>
#include <initguid.h>
#include <shellapi.h>
#include <mmdeviceapi.h>
#include <endpointvolume.h>
#include <physicalmonitorenumerationapi.h>
#include <highlevelmonitorconfigurationapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static bool create_process_ex(const wchar_t *exe, const wchar_t *args, bool hideWindow, bool newConsole, bool newProcessGroup, DWORD *outPid);
static bool create_process_capture_output(const wchar_t *exe,
                                          const wchar_t *args,
                                          DWORD timeoutMs,
                                          DWORD *outExitCode,
                                          char **outStdoutUtf8,
                                          char **outStderrUtf8);

/*
 * 展开环境变量（ExpandEnvironmentStringsW）。
 * - 输入允许为 NULL；NULL 会被当作空字符串。
 * - 返回 malloc 分配的宽字符串，调用方 free。
 */
static wchar_t *expand_env_wide_alloc(const wchar_t *in)
{
    if (!in)
        in = L"";
    DWORD needed = ExpandEnvironmentStringsW(in, NULL, 0);
    if (needed == 0)
        return _wcsdup(in);
    wchar_t *out = (wchar_t *)malloc((size_t)needed * sizeof(wchar_t));
    if (!out)
        return NULL;
    DWORD n = ExpandEnvironmentStringsW(in, out, needed);
    if (n == 0 || n > needed)
    {
        free(out);
        return _wcsdup(in);
    }
    return out;
}

/*
 * 跳过开头空白（仅处理空格/制表/换行）。
 * 用于解析配置里可能带空格的命令/路径。
 */
static const char *skip_spaces(const char *s)
{
    if (!s)
        return "";
    while (*s == ' ' || *s == '\t' || *s == '\r' || *s == '\n')
        s++;
    return s;
}

/*
 * 去除包裹引号（"..." 或 '...'），并剔除两端空白。
 * - 常见于 JSON 里路径带引号的情况（例如 "C:\\Program Files\\..."）。
 * - 返回 malloc 分配的字符串，调用方 free。
 */
static char *strip_wrapping_quotes_alloc(const char *s)
{
    const char *p = skip_spaces(s);
    size_t n = strlen(p);
    while (n > 0 && (p[n - 1] == ' ' || p[n - 1] == '\t' || p[n - 1] == '\r' || p[n - 1] == '\n'))
        n--;

    if (n >= 2 && ((p[0] == '"' && p[n - 1] == '"') || (p[0] == '\'' && p[n - 1] == '\'')))
    {
        p++;
        n -= 2;
    }

    char *out = (char *)malloc(n + 1);
    if (!out)
        return NULL;
    memcpy(out, p, n);
    out[n] = 0;
    return out;
}

/*
 * 将整数限制到 [lo, hi]，避免传入系统 API 的参数越界。
 */
static int clamp_int(int v, int lo, int hi)
{
    if (v < lo)
        return lo;
    if (v > hi)
        return hi;
    return v;
}

/*
 * 计算机级动作（lock/shutdown/restart/logoff）。
 *
 * 关机/重启采用：cmd.exe /c shutdown ...
 * - 使用 CreateProcessW + CREATE_NO_WINDOW：不弹控制台窗口。
 * - 增加 -f：强制关闭应用，避免锁屏时被“应用阻止关机”卡住。
 */
void RC_ActionPerformComputer(const char *action, int delaySeconds)
{
    const char *act = action ? action : "";
    int d = delaySeconds < 0 ? 0 : delaySeconds;

    if (_stricmp(act, "none") == 0)
        return;

    if (_stricmp(act, "lock") == 0)
    {
        RC_LogInfo("电脑动作：锁屏");
        // LockWorkStation：锁定当前会话，不需要管理员权限。
        LockWorkStation();
        return;
    }

    if (_stricmp(act, "shutdown") == 0)
    {
        RC_LogInfo("电脑动作：关机 (delay=%d)", d);
        // shutdown.exe 参数：
        // -s 关机；-t 延迟秒数；-f 强制关闭程序（更适配锁屏/无人值守场景）。
        STARTUPINFOW si;
        PROCESS_INFORMATION pi;
        ZeroMemory(&si, sizeof(si));
        ZeroMemory(&pi, sizeof(pi));
        si.cb = sizeof(si);
        wchar_t cmdline[160];
        _snwprintf(cmdline, (int)(sizeof(cmdline) / sizeof(cmdline[0])), L"cmd.exe /c shutdown -s -f -t %d", d);
        if (!CreateProcessW(NULL, cmdline, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi))
        {
            // 常见失败：权限不足/UAC、系统策略限制、路径解析异常等。
            RC_LogError("关机 CreateProcess 失败：%lu", GetLastError());
            return;
        }
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return;
    }

    if (_stricmp(act, "restart") == 0)
    {
        RC_LogInfo("电脑动作：重启 (delay=%d)", d);
        // shutdown.exe 参数：-r 重启；-t 延迟；-f 强制关闭程序。
        STARTUPINFOW si;
        PROCESS_INFORMATION pi;
        ZeroMemory(&si, sizeof(si));
        ZeroMemory(&pi, sizeof(pi));
        si.cb = sizeof(si);
        wchar_t cmdline[160];
        _snwprintf(cmdline, (int)(sizeof(cmdline) / sizeof(cmdline[0])), L"cmd.exe /c shutdown -r -f -t %d", d);
        if (!CreateProcessW(NULL, cmdline, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi))
        {
            RC_LogError("重启 CreateProcess 失败：%lu", GetLastError());
            return;
        }
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return;
    }

    if (_stricmp(act, "logoff") == 0)
    {
        RC_LogInfo("电脑动作：注销");
        STARTUPINFOW si;
        PROCESS_INFORMATION pi;
        ZeroMemory(&si, sizeof(si));
        ZeroMemory(&pi, sizeof(pi));
        si.cb = sizeof(si);
        wchar_t cmdline[64];
        _snwprintf(cmdline, (int)(sizeof(cmdline) / sizeof(cmdline[0])), L"cmd.exe /c shutdown -l");
        CreateProcessW(NULL, cmdline, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
        if (pi.hThread)
            CloseHandle(pi.hThread);
        if (pi.hProcess)
            CloseHandle(pi.hProcess);
        return;
    }

    RC_LogWarn("未知电脑动作：%s", act);
}

void RC_ActionSetDisplayPower(bool on)
{
    // 显示器电源控制：
    // - 通过广播 WM_SYSCOMMAND/SC_MONITORPOWER 发送到所有顶层窗口。
    // - lParam 含义（常用约定）：
    //   -1: power on（唤醒）
    //    2: power off（关闭显示器）
    LPARAM lp = on ? -1 : 2;
    SendMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, lp);
}

void RC_ActionPerformSleep(const char *action)
{
    const char *act = action ? action : "";
    if (_stricmp(act, "none") == 0)
        return;

    if (_stricmp(act, "sleep") == 0)
    {
        RC_LogInfo("睡眠动作：睡眠");
        // 通过 powrprof.dll 的 SetSuspendState 进入睡眠：
        // rundll32.exe powrprof.dll,SetSuspendState <Hibernate>,<ForceCritical>,<DisableWakeEvent>
        // 这里使用 0,1,0：尝试睡眠，并尽量强制进入。
        STARTUPINFOW si;
        PROCESS_INFORMATION pi;
        ZeroMemory(&si, sizeof(si));
        ZeroMemory(&pi, sizeof(pi));
        si.cb = sizeof(si);
        wchar_t cmdline[] = L"cmd.exe /c rundll32.exe powrprof.dll,SetSuspendState 0,1,0";
        CreateProcessW(NULL, cmdline, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
        if (pi.hThread)
            CloseHandle(pi.hThread);
        if (pi.hProcess)
            CloseHandle(pi.hProcess);
        return;
    }

    if (_stricmp(act, "hibernate") == 0)
    {
        RC_LogInfo("睡眠动作：休眠");
        // 休眠：调用 shutdown /h。
        STARTUPINFOW si;
        PROCESS_INFORMATION pi;
        ZeroMemory(&si, sizeof(si));
        ZeroMemory(&pi, sizeof(pi));
        si.cb = sizeof(si);
        wchar_t cmdline[] = L"cmd.exe /c shutdown /h";
        CreateProcessW(NULL, cmdline, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
        if (pi.hThread)
            CloseHandle(pi.hThread);
        if (pi.hProcess)
            CloseHandle(pi.hProcess);
        return;
    }

    if (_stricmp(act, "display_off") == 0)
    {
        RC_LogInfo("睡眠动作：关闭显示器");
        // 仅关闭显示器，不影响系统运行。
        RC_ActionSetDisplayPower(false);
        return;
    }

    if (_stricmp(act, "display_on") == 0)
    {
        RC_LogInfo("睡眠动作：开启显示器");
        RC_ActionSetDisplayPower(true);
        return;
    }

    if (_stricmp(act, "lock") == 0)
    {
        RC_LogInfo("睡眠动作：锁屏");
        // 仅锁屏，不睡眠。
        LockWorkStation();
        return;
    }

    RC_LogWarn("未知睡眠动作：%s", act);
}

static void send_vk(WORD vk)
{
    /*
     * 发送一个“虚拟键”按下 + 抬起。
     * - 使用 SendInput 注入键盘事件。
     * - 该函数主要用于多媒体键（VK_MEDIA_*）。
     */
    INPUT in[2];
    ZeroMemory(in, sizeof(in));

    in[0].type = INPUT_KEYBOARD;
    in[0].ki.wVk = vk;

    in[1].type = INPUT_KEYBOARD;
    in[1].ki.wVk = vk;
    in[1].ki.dwFlags = KEYEVENTF_KEYUP;

    SendInput(2, in, sizeof(INPUT));
}

void RC_ActionMediaCommand(const char *command)
{
    /*
     * 多媒体动作（与历史 Python 版本行为对齐）：
     * - "off"  ：下一首（VK_MEDIA_NEXT_TRACK）
     * - "on"   ：上一首（VK_MEDIA_PREV_TRACK）
     * - "pause": 播放/暂停（VK_MEDIA_PLAY_PAUSE）
     * - "on#<0~100>"：按值区间映射到上面三种动作（用于滑块/按钮复用场景）。
     *
     * 说明：命名看起来有些反直觉（on/off 对应上一首/下一首），这是为了兼容既有协议。
     */
    const char *cmd = command ? command : "";

    if (_stricmp(cmd, "off") == 0)
    {
        send_vk(VK_MEDIA_NEXT_TRACK);
        return;
    }
    if (_stricmp(cmd, "on") == 0)
    {
        send_vk(VK_MEDIA_PREV_TRACK);
        return;
    }
    if (_stricmp(cmd, "pause") == 0)
    {
        send_vk(VK_MEDIA_PLAY_PAUSE);
        return;
    }

    if (_strnicmp(cmd, "on#", 3) == 0)
    {
        int v = atoi(cmd + 3);
        if (v <= 33)
            send_vk(VK_MEDIA_NEXT_TRACK);
        else if (v <= 66)
            send_vk(VK_MEDIA_PLAY_PAUSE);
        else
            send_vk(VK_MEDIA_PREV_TRACK);
        return;
    }

    RC_LogWarn("未知媒体指令：%s", cmd);
}

typedef struct
{
    DWORD brightness;
    bool ok;
} BrightnessCtx;

/*
 * EnumDisplayMonitors 的回调：尝试为当前 HMONITOR 下的所有“物理显示器”设置亮度。
 *
 * 说明：
 * - HMONITOR 只是逻辑监视器句柄；Dxva2 API 需要先映射到 PHYSICAL_MONITOR。
 * - 并非所有显示器都支持 DDC/CI 亮度控制；不支持时 SetMonitorBrightness 会失败。
 * - 这里采用 best-effort：只要任意一个物理显示器设置成功，就把 ctx->ok 置为 true。
 */
static BOOL CALLBACK enum_monitors_set_brightness(HMONITOR hMonitor, HDC hdc, LPRECT lprc, LPARAM lp)
{
    (void)hdc;
    (void)lprc;
    BrightnessCtx *ctx = (BrightnessCtx *)lp;
    if (!ctx)
        return TRUE;

    DWORD count = 0;
    if (!GetNumberOfPhysicalMonitorsFromHMONITOR(hMonitor, &count) || count == 0)
        return TRUE;

    PHYSICAL_MONITOR *mons = (PHYSICAL_MONITOR *)calloc(count, sizeof(PHYSICAL_MONITOR));
    if (!mons)
        return TRUE;

    if (GetPhysicalMonitorsFromHMONITOR(hMonitor, count, mons))
    {
        for (DWORD i = 0; i < count; i++)
        {
            // Note: Some monitors may not support brightness control.
            if (SetMonitorBrightness(mons[i].hPhysicalMonitor, ctx->brightness))
                ctx->ok = true;
        }
        DestroyPhysicalMonitors(count, mons);
    }

    free(mons);
    return TRUE;
}

bool RC_ActionSetBrightnessPercent(int percent0to100)
{
    /*
     * 通过 Dxva2 的物理显示器 API 调整亮度（0~100）。
     *
     * 注意事项：
     * - 该路径依赖显示器/显卡驱动对 DDC/CI 等能力的支持；很多设备不支持或会失败。
     * - 本实现会枚举所有 HMONITOR，并尝试对每个物理显示器句柄调用 SetMonitorBrightness。
     * - 只要有任意一个显示器设置成功，就认为 ok=true。
     */
    int v = clamp_int(percent0to100, 0, 100);
    BrightnessCtx ctx;
    ctx.brightness = (DWORD)v;
    ctx.ok = false;

    EnumDisplayMonitors(NULL, NULL, enum_monitors_set_brightness, (LPARAM)&ctx);
    if (!ctx.ok)
        RC_LogWarn("设置亮度失败或不支持 (percent=%d)", v);
    return ctx.ok;
}

bool RC_ActionSetVolumePercent(int percent0to100)
{
    /*
     * 使用 Core Audio 设置默认渲染设备（eRender/eConsole）的主音量（0~100）。
     *
     * COM 初始化策略：
     * - CoInitializeEx(COINIT_APARTMENTTHREADED) 成功：函数末尾 CoUninitialize。
     * - 若返回 RPC_E_CHANGED_MODE：说明当前线程已用不同模型初始化 COM；
     *   这里继续调用 COM 接口，但不做 CoUninitialize（避免破坏外部初始化状态）。
     */
    int v = clamp_int(percent0to100, 0, 100);

    HRESULT hr = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    bool coInit = SUCCEEDED(hr);
    // If COM is already initialized with different mode, proceed but don't uninitialize.
    if (hr == RPC_E_CHANGED_MODE)
        coInit = false;

    IMMDeviceEnumerator *pEnum = NULL;
    IMMDevice *pDevice = NULL;
    IAudioEndpointVolume *pVol = NULL;

    HRESULT r = CoCreateInstance(&CLSID_MMDeviceEnumerator, NULL, CLSCTX_ALL, &IID_IMMDeviceEnumerator, (void **)&pEnum);
    if (FAILED(r) || !pEnum)
        goto done;

    r = pEnum->lpVtbl->GetDefaultAudioEndpoint(pEnum, eRender, eConsole, &pDevice);
    if (FAILED(r) || !pDevice)
        goto done;

    r = pDevice->lpVtbl->Activate(pDevice, &IID_IAudioEndpointVolume, CLSCTX_ALL, NULL, (void **)&pVol);
    if (FAILED(r) || !pVol)
        goto done;

    r = pVol->lpVtbl->SetMasterVolumeLevelScalar(pVol, (float)v / 100.0f, NULL);
    if (FAILED(r))
        goto done;

    if (pVol)
        pVol->lpVtbl->Release(pVol);
    if (pDevice)
        pDevice->lpVtbl->Release(pDevice);
    if (pEnum)
        pEnum->lpVtbl->Release(pEnum);
    if (coInit)
        CoUninitialize();
    return true;

done:
    if (pVol)
        pVol->lpVtbl->Release(pVol);
    if (pDevice)
        pDevice->lpVtbl->Release(pDevice);
    if (pEnum)
        pEnum->lpVtbl->Release(pEnum);
    if (coInit)
        CoUninitialize();
    RC_LogError("设置音量失败 (percent=%d)", v);
    return false;
}

static const char *file_ext_lower(const char *path)
{
    /*
     * 获取“扩展名”子串指针（包含 '.'），用于快速判断脚本类型。
     * - 返回的是指向 path 内部的指针，不分配内存。
     * - 本函数不做大小写转换，调用处使用 _stricmp 做大小写无关比较。
     * - 若没有 '.' 则返回空字符串 ""。
     */
    if (!path)
        return "";
    const char *dot = strrchr(path, '.');
    if (!dot)
        return "";
    return dot;
}

bool RC_ActionRunProgramUtf8(const char *pathUtf8)
{
    /*
     * 启动外部程序/脚本（UTF-8 路径）。
     *
     * 行为约定：
     * - 先做路径分隔符归一化（\/）。
     * - .ps1：用 powershell.exe -File 启动（隐藏窗口）。
     * - .bat/.cmd：用 cmd.exe /c 启动（隐藏窗口）。
     * - 其它：优先 ShellExecuteW("open")，失败则回退 CreateProcessW。
     *
     * 返回值：
     * - true：启动动作已成功发起（不代表子进程最终执行一定成功）。
     * - false：参数非法或启动失败。
     */
    if (!pathUtf8 || !*pathUtf8)
        return false;

    char *tmp = _strdup(pathUtf8);
    if (!tmp)
        return false;
    RC_NormalizePathSlashes(tmp);

    wchar_t *wpath = RC_Utf8ToWideAlloc(tmp);
    if (!wpath)
    {
        free(tmp);
        return false;
    }

    const char *ext = file_ext_lower(tmp);

    bool ok = true;
    if (_stricmp(ext, ".ps1") == 0)
    {
        wchar_t args[4096];
        _snwprintf(args, (int)(sizeof(args) / sizeof(args[0])), L"-NoProfile -ExecutionPolicy Bypass -File \"%s\"", wpath);
        DWORD pid = 0;
        ok = create_process_ex(L"powershell.exe", args, true, false, false, &pid);
    }
    else if (_stricmp(ext, ".bat") == 0 || _stricmp(ext, ".cmd") == 0)
    {
        wchar_t args[4096];
        _snwprintf(args, (int)(sizeof(args) / sizeof(args[0])), L"/c \"%s\"", wpath);
        DWORD pid = 0;
        ok = create_process_ex(L"cmd.exe", args, true, false, false, &pid);
    }
    else
    {
        HINSTANCE h = ShellExecuteW(NULL, L"open", wpath, NULL, NULL, SW_SHOWNORMAL);
        ok = ((INT_PTR)h > 32);
        if (!ok)
        {
            // Fallback to CreateProcess
            STARTUPINFOW si;
            PROCESS_INFORMATION pi;
            ZeroMemory(&si, sizeof(si));
            ZeroMemory(&pi, sizeof(pi));
            si.cb = sizeof(si);

            wchar_t *cmdline = _wcsdup(wpath);
            if (cmdline)
            {
                ok = !!CreateProcessW(NULL, cmdline, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi);
                free(cmdline);
            }
            if (pi.hThread)
                CloseHandle(pi.hThread);
            if (pi.hProcess)
                CloseHandle(pi.hProcess);
        }
    }

    free(wpath);
    free(tmp);
    return ok;
}

/*
 * CreateProcessW 轻量封装：用于本模块中“执行外部命令/工具”。
 *
 * 参数语义：
 * - exe：可执行文件名或路径（宽字符串）。这里会自动加引号，减少空格路径问题。
 * - args：参数字符串（宽字符串），由调用方负责拼接；可为 NULL/空。
 * - hideWindow：隐藏控制台窗口（一般用于后台执行）；
 *   注意：当 newConsole=true 时不能使用 CREATE_NO_WINDOW，否则不会获得控制台。
 * - newConsole：创建新控制台窗口（用于需要控制台语义的场景）。
 * - newProcessGroup：CREATE_NEW_PROCESS_GROUP，配合 CTRL_BREAK_EVENT 使用。
 * - outPid：输出子进程 pid（可为 NULL）。
 *
 * 典型用途：
 * - 后台执行 cmd.exe /c、powershell.exe 等。
 * - 为“中断（CTRL_BREAK）”类动作准备进程组语义。
 */
static bool create_process_ex(const wchar_t *exe, const wchar_t *args, bool hideWindow, bool newConsole, bool newProcessGroup, DWORD *outPid)
{
    if (outPid)
        *outPid = 0;

    wchar_t cmdline[8192];
    if (args && *args)
        _snwprintf(cmdline, (int)(sizeof(cmdline) / sizeof(cmdline[0])), L"\"%s\" %s", exe, args);
    else
        _snwprintf(cmdline, (int)(sizeof(cmdline) / sizeof(cmdline[0])), L"\"%s\"", exe);

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    ZeroMemory(&pi, sizeof(pi));
    si.cb = sizeof(si);

    DWORD flags = 0;
    if (hideWindow)
    {
        si.dwFlags |= STARTF_USESHOWWINDOW;
        si.wShowWindow = SW_HIDE;
        // If we create a new console, do NOT use CREATE_NO_WINDOW;
        // we need a console to support CTRL_BREAK interrupt semantics.
        if (!newConsole)
            flags |= CREATE_NO_WINDOW;
    }
    if (newConsole)
        flags |= CREATE_NEW_CONSOLE;
    if (newProcessGroup)
        flags |= CREATE_NEW_PROCESS_GROUP;

    // CreateProcessW expects a writable buffer.
    wchar_t *mutableCmd = _wcsdup(cmdline);
    if (!mutableCmd)
        return false;

    BOOL ok = CreateProcessW(NULL, mutableCmd, NULL, NULL, FALSE, flags, NULL, NULL, &si, &pi);
    DWORD err = ok ? 0 : GetLastError();
    free(mutableCmd);

    if (!ok)
    {
        RC_LogError("CreateProcess 失败 (exe=%ls, err=%lu)", exe ? exe : L"", (unsigned long)err);
        return false;
    }

    if (outPid)
        *outPid = pi.dwProcessId;

    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return true;
}

/*
 * 将一段原始字节流转成 UTF-8 字符串。
 *
 * 背景：部分系统工具（例如 taskkill.exe）的输出默认使用控制台/OEM code page。
 * 因此这里按 GetOEMCP() / GetACP() 尝试解码为 UTF-16，再转 UTF-8；
 * 若都失败，则把 bytes 当作“近似 UTF-8 的字节串”直接复制。
 *
 * 返回值：malloc 分配的 UTF-8 字符串，调用方 free()。
 */
static char *bytes_to_utf8_alloc(const unsigned char *bytes, size_t len)
{
    if (!bytes || len == 0)
    {
        char *s = (char *)malloc(1);
        if (s)
            s[0] = 0;
        return s;
    }

    // taskkill output is typically in the console/OEM code page.
    UINT cps[2] = {GetOEMCP(), GetACP()};
    for (int i = 0; i < 2; i++)
    {
        UINT cp = cps[i];
        int wlen = MultiByteToWideChar(cp, 0, (const char *)bytes, (int)len, NULL, 0);
        if (wlen <= 0)
            continue;
        wchar_t *w = (wchar_t *)malloc(((size_t)wlen + 1) * sizeof(wchar_t));
        if (!w)
            return NULL;
        int ok = MultiByteToWideChar(cp, 0, (const char *)bytes, (int)len, w, wlen);
        if (!ok)
        {
            free(w);
            continue;
        }
        w[wlen] = 0;
        char *u8 = RC_WideToUtf8Alloc(w);
        free(w);
        if (u8)
            return u8;
    }

    // Fallback: treat as already UTF-8-ish bytes.
    char *s = (char *)malloc(len + 1);
    if (!s)
        return NULL;
    memcpy(s, bytes, len);
    s[len] = 0;
    return s;
}

/*
 * 从匿名管道读取“当前可读”的字节并追加到缓冲区。
 *
 * 说明：
 * - PeekNamedPipe 用于查询当前可读字节数，避免 ReadFile 阻塞。
 * - cap 为上限（本实现用于日志/诊断，避免子进程输出过大导致无限增长）。
 * - ioBuf/ioLen 采用 realloc 逐步扩容（最多到 cap）。
 */
static void read_pipe_available(HANDLE hRead, unsigned char **ioBuf, size_t *ioLen, size_t cap)
{
    if (!hRead || hRead == INVALID_HANDLE_VALUE || !ioBuf || !ioLen)
        return;
    if (*ioLen >= cap)
        return;

    for (;;)
    {
        DWORD avail = 0;
        if (!PeekNamedPipe(hRead, NULL, 0, NULL, &avail, NULL))
            return;
        if (avail == 0)
            return;

        DWORD want = avail;
        size_t remaining = cap - *ioLen;
        if (want > remaining)
            want = (DWORD)remaining;

        unsigned char *nbuf = (unsigned char *)realloc(*ioBuf, *ioLen + want);
        if (!nbuf)
            return;
        *ioBuf = nbuf;

        DWORD read = 0;
        if (!ReadFile(hRead, *ioBuf + *ioLen, want, &read, NULL) || read == 0)
            return;
        *ioLen += (size_t)read;

        if (*ioLen >= cap)
            return;
    }
}

/*
 * 启动子进程并抓取 stdout/stderr（用于需要诊断输出的工具调用）。
 *
 * 行为：
 * - 为 stdout/stderr 创建匿名管道，并把 write 端继承给子进程（bInheritHandle=TRUE）。
 * - 父进程关闭 write 端，循环 WaitForSingleObject + PeekNamedPipe 读取。
 * - timeoutMs 到期后不强杀进程（仅记录 warn 并跳出等待），随后尽量读取现有输出。
 * - CAP=8192：输出上限（超过部分会被截断）。
 *
 * 返回值：
 * - true 表示 exit code == 0；false 表示非 0 或启动失败。
 * - outStdoutUtf8/outStderrUtf8 返回 malloc 字符串（可能为空字符串或 NULL），调用方 free()。
 */
static bool create_process_capture_output(const wchar_t *exe,
                                          const wchar_t *args,
                                          DWORD timeoutMs,
                                          DWORD *outExitCode,
                                          char **outStdoutUtf8,
                                          char **outStderrUtf8)
{
    if (outExitCode)
        *outExitCode = 0;
    if (outStdoutUtf8)
        *outStdoutUtf8 = NULL;
    if (outStderrUtf8)
        *outStderrUtf8 = NULL;

    SECURITY_ATTRIBUTES sa;
    ZeroMemory(&sa, sizeof(sa));
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;

    HANDLE outRead = NULL, outWrite = NULL;
    HANDLE errRead = NULL, errWrite = NULL;
    if (!CreatePipe(&outRead, &outWrite, &sa, 0))
        return false;
    if (!CreatePipe(&errRead, &errWrite, &sa, 0))
    {
        CloseHandle(outRead);
        CloseHandle(outWrite);
        return false;
    }

    // Parent must not leak inheritable read handles.
    SetHandleInformation(outRead, HANDLE_FLAG_INHERIT, 0);
    SetHandleInformation(errRead, HANDLE_FLAG_INHERIT, 0);

    wchar_t cmdline[8192];
    if (args && *args)
        _snwprintf(cmdline, (int)(sizeof(cmdline) / sizeof(cmdline[0])), L"\"%s\" %s", exe, args);
    else
        _snwprintf(cmdline, (int)(sizeof(cmdline) / sizeof(cmdline[0])), L"\"%s\"", exe);

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    ZeroMemory(&pi, sizeof(pi));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW | STARTF_USESTDHANDLES;
    si.wShowWindow = SW_HIDE;
    si.hStdOutput = outWrite;
    si.hStdError = errWrite;
    si.hStdInput = GetStdHandle(STD_INPUT_HANDLE);

    DWORD flags = CREATE_NO_WINDOW;

    wchar_t *mutableCmd = _wcsdup(cmdline);
    if (!mutableCmd)
    {
        CloseHandle(outRead);
        CloseHandle(outWrite);
        CloseHandle(errRead);
        CloseHandle(errWrite);
        return false;
    }

    BOOL ok = CreateProcessW(NULL, mutableCmd, NULL, NULL, TRUE, flags, NULL, NULL, &si, &pi);
    DWORD err = ok ? 0 : GetLastError();
    free(mutableCmd);

    // Parent closes write ends so ReadFile can complete.
    CloseHandle(outWrite);
    CloseHandle(errWrite);

    if (!ok)
    {
        RC_LogError("CreateProcess(捕获输出) 失败 (exe=%ls, args=%ls, err=%lu)", exe ? exe : L"", (args && *args) ? args : L"", (unsigned long)err);
        CloseHandle(outRead);
        CloseHandle(errRead);
        return false;
    }

    const size_t CAP = 8192;
    unsigned char *outBuf = NULL;
    unsigned char *errBuf = NULL;
    size_t outLen = 0;
    size_t errLen = 0;

    ULONGLONG start = GetTickCount64();
    for (;;)
    {
        read_pipe_available(outRead, &outBuf, &outLen, CAP);
        read_pipe_available(errRead, &errBuf, &errLen, CAP);

        DWORD wait = WaitForSingleObject(pi.hProcess, 50);
        if (wait == WAIT_OBJECT_0)
            break;

        if (timeoutMs != INFINITE)
        {
            ULONGLONG elapsed = GetTickCount64() - start;
            if (elapsed >= timeoutMs)
            {
                RC_LogWarn("进程超时(捕获输出) exe=%ls pid=%lu timeoutMs=%lu", exe ? exe : L"", (unsigned long)pi.dwProcessId,
                           (unsigned long)timeoutMs);
                break;
            }
        }
    }

    // Drain remaining.
    read_pipe_available(outRead, &outBuf, &outLen, CAP);
    read_pipe_available(errRead, &errBuf, &errLen, CAP);

    DWORD code = 0;
    if (!GetExitCodeProcess(pi.hProcess, &code))
        code = 1;
    if (outExitCode)
        *outExitCode = code;

    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    CloseHandle(outRead);
    CloseHandle(errRead);

    if (outStdoutUtf8)
        *outStdoutUtf8 = bytes_to_utf8_alloc(outBuf, outLen);
    if (outStderrUtf8)
        *outStderrUtf8 = bytes_to_utf8_alloc(errBuf, errLen);
    free(outBuf);
    free(errBuf);
    return (code == 0);
}

bool RC_ActionSetBrightnessTwinkleTrayPercentUtf8(int percent0to100,
                                                  const char *exePathUtf8,
                                                  const char *targetModeUtf8,
                                                  const char *targetValueUtf8,
                                                  bool overlay,
                                                  bool panel)
{
    /*
     * 通过 Twinkle Tray CLI 设置亮度（更稳定、覆盖面更广的一条路径）。
     *
     * 输入：
     * - percent0to100：亮度百分比（会 clamp 到 0~100）。
     * - exePathUtf8：可选，Twinkle Tray.exe 的路径（支持环境变量与引号包裹）。为空则尝试：
     *   1) %LocalAppData%\Programs\twinkle-tray\Twinkle Tray.exe
     *   2) Twinkle-Tray.exe（Store alias / PATH）
     * - targetModeUtf8/targetValueUtf8：选择目标显示器：
     *   - all：所有显示器
     *   - monitor_id + targetValue：--MonitorID=...
     *   - monitor_num + targetValue（默认）：--MonitorNum=...
     * - overlay/panel：附加 UI 参数（--Overlay/--Panel）。
     *
     * 输出：
     * - 通过 create_process_capture_output 抓 stdout/stderr 写入日志，便于诊断。
     * - 返回 true 表示 exit code == 0。
     */
    int v = clamp_int(percent0to100, 0, 100);

    const char *mode = skip_spaces(targetModeUtf8);
    if (!*mode)
        mode = "monitor_num";
    const char *tval = skip_spaces(targetValueUtf8);
    if (!*tval)
        tval = "1";

    // Resolve exe.
    char *exeCfgOwned = strip_wrapping_quotes_alloc(exePathUtf8);
    const char *exeCfg = exeCfgOwned ? exeCfgOwned : skip_spaces(exePathUtf8);
    wchar_t *exeW = NULL;
    wchar_t *tmpW = NULL;
    if (exeCfg && *exeCfg)
    {
        tmpW = RC_Utf8ToWideAlloc(exeCfg);
        if (tmpW)
        {
            exeW = expand_env_wide_alloc(tmpW);
            free(tmpW);
            tmpW = NULL;
        }
    }

    // Candidate fallback if path not provided.
    wchar_t *fallbackW = NULL;
    if (!exeW || !*exeW)
    {
        // Default install path (non-store) first.
        fallbackW = expand_env_wide_alloc(L"%LocalAppData%\\Programs\\twinkle-tray\\Twinkle Tray.exe");
        if (fallbackW && GetFileAttributesW(fallbackW) != INVALID_FILE_ATTRIBUTES)
        {
            free(exeW);
            exeW = fallbackW;
            fallbackW = NULL;
        }
        else
        {
            // Store alias (v1.17.1+) or PATH
            free(fallbackW);
            fallbackW = NULL;
            free(exeW);
            exeW = _wcsdup(L"Twinkle-Tray.exe");
        }
    }

    if (!exeW || !*exeW)
    {
        free(exeCfgOwned);
        free(exeW);
        return false;
    }

    wchar_t argsW[1024];
    argsW[0] = 0;

    // One monitor selector arg + one brightness arg are required.
    if (_stricmp(mode, "all") == 0)
    {
        _snwprintf(argsW, (int)(sizeof(argsW) / sizeof(argsW[0])), L"--All --Set=%d", v);
    }
    else if (_stricmp(mode, "monitor_id") == 0)
    {
        if (!tval || !*tval)
        {
            RC_LogWarn("Twinkle Tray：monitor_id 模式下 target_value 为空");
            free(exeW);
            return false;
        }
        char *tvalOwned = strip_wrapping_quotes_alloc(tval);
        const char *tval2 = tvalOwned ? tvalOwned : tval;
        wchar_t *idW0 = RC_Utf8ToWideAlloc(tval2);
        wchar_t *idW = idW0 ? expand_env_wide_alloc(idW0) : NULL;
        free(idW0);
        free(tvalOwned);
        if (!idW)
        {
            free(exeCfgOwned);
            free(exeW);
            return false;
        }
        _snwprintf(argsW, (int)(sizeof(argsW) / sizeof(argsW[0])), L"--MonitorID=\"%ls\" --Set=%d", idW, v);
        free(idW);
    }
    else
    {
        // Default: monitor_num
        char *tvalOwned = strip_wrapping_quotes_alloc(tval);
        const char *tval2 = tvalOwned ? tvalOwned : tval;
        wchar_t *numW0 = RC_Utf8ToWideAlloc(tval2);
        wchar_t *numW = numW0 ? expand_env_wide_alloc(numW0) : NULL;
        free(numW0);
        free(tvalOwned);
        if (!numW)
        {
            free(exeCfgOwned);
            free(exeW);
            return false;
        }
        _snwprintf(argsW, (int)(sizeof(argsW) / sizeof(argsW[0])), L"--MonitorNum=%ls --Set=%d", numW, v);
        free(numW);
    }

    // Optional UI flags.
    if (overlay)
        wcscat(argsW, L" --Overlay");
    if (panel)
        wcscat(argsW, L" --Panel");

    DWORD exitCode = 0;
    char *outTxt = NULL;
    char *errTxt = NULL;
    RC_LogInfo("Twinkle Tray 亮度：%d", v);
    bool ok = create_process_capture_output(exeW, argsW, 15000, &exitCode, &outTxt, &errTxt);

    if (ok)
        RC_LogInfo("Twinkle Tray 成功 (exit=%lu)", (unsigned long)exitCode);
    else
        RC_LogWarn("Twinkle Tray 失败 (exit=%lu)", (unsigned long)exitCode);

    if (outTxt && *outTxt)
        RC_LogInfo("Twinkle Tray 标准输出：%s", outTxt);
    if (errTxt && *errTxt)
        RC_LogWarn("Twinkle Tray 错误输出：%s", errTxt);

    free(outTxt);
    free(errTxt);
    free(exeCfgOwned);
    free(exeW);
    return ok;
}

static wchar_t *dup_and_escape_quotes_for_cmdline(const wchar_t *s)
{
    /*
     * 为命令行参数构造做最小转义：把输入中的 '"' 替换为 '\"'。
     *
     * 背景：
     * - PowerShell 的 -Command "..." 会经过命令行解析；
     * - 若原始命令内包含双引号，需要转义避免截断。
     *
     * 返回值：malloc 分配的宽字符串，调用方 free。
     */
    if (!s)
        s = L"";
    size_t inLen = wcslen(s);
    size_t extra = 0;
    for (size_t i = 0; i < inLen; i++)
    {
        if (s[i] == L'\"')
            extra++;
    }
    wchar_t *out = (wchar_t *)malloc((inLen + extra + 1) * sizeof(wchar_t));
    if (!out)
        return NULL;

    size_t j = 0;
    for (size_t i = 0; i < inLen; i++)
    {
        if (s[i] == L'\"')
            out[j++] = L'\\';
        out[j++] = s[i];
    }
    out[j] = 0;
    return out;
}

bool RC_ActionRunPowershellCommandUtf8(const char *commandUtf8, bool hideWindow, bool keepWindow)
{
    /*
     * 执行 PowerShell 命令（UTF-8 文本）。
     *
     * 参数：
     * - hideWindow：是否隐藏窗口（WindowStyle Hidden + CREATE_NO_WINDOW）。
     * - keepWindow：是否保留 PowerShell 窗口（-NoExit），用于交互/调试。
     *
     * 进程语义：
     * - 这里使用 create_process_ex(..., newProcessGroup=true)，为后续 CTRL_BREAK_EVENT
     *   “中断”类动作提供进程组基础（注意：是否能中断仍取决于控制台/会话条件）。
     */
    if (!commandUtf8)
        commandUtf8 = "";

    // Apply {value} is handled by caller.
    wchar_t *wcmd = RC_Utf8ToWideAlloc(commandUtf8);
    if (!wcmd)
        return false;

    wchar_t *escaped = dup_and_escape_quotes_for_cmdline(wcmd);
    if (!escaped)
    {
        free(wcmd);
        return false;
    }

    wchar_t args[8192];
    if (keepWindow)
    {
        _snwprintf(args, (int)(sizeof(args) / sizeof(args[0])),
                   L"-NoProfile -ExecutionPolicy Bypass -NoExit -Command \"%s\"", escaped);
    }
    else
    {
        // For hidden we also use -NonInteractive.
        if (hideWindow)
        {
            _snwprintf(args, (int)(sizeof(args) / sizeof(args[0])),
                       L"-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -Command \"%s\"", escaped);
        }
        else
        {
            _snwprintf(args, (int)(sizeof(args) / sizeof(args[0])),
                       L"-NoProfile -ExecutionPolicy Bypass -Command \"%s\"", escaped);
        }
    }

    // If we want to hide the window, do NOT create a new console.
    // A GUI parent without a console + CREATE_NO_WINDOW prevents the console from flashing.
    bool newConsole = !hideWindow;

    DWORD pid = 0;
    bool ok = create_process_ex(L"powershell.exe", args, hideWindow, newConsole, true, &pid);
    RC_LogInfo("PowerShell 已启动 (pid=%lu)", (unsigned long)pid);

    free(escaped);
    free(wcmd);
    return ok;
}

bool RC_ActionRunPowershellCommandUtf8Ex(const char *commandUtf8, bool hideWindow, bool keepWindow, unsigned long *outPid)
{
    /*
     * PowerShell 执行扩展版：在 RC_ActionRunPowershellCommandUtf8 的基础上返回 pid。
     * - outPid 可为 NULL；若启动失败或无法获取则为 0。
     * - 其余行为/参数含义与 RC_ActionRunPowershellCommandUtf8 一致。
     */
    if (outPid)
        *outPid = 0;

    if (!commandUtf8)
        commandUtf8 = "";

    wchar_t *wcmd = RC_Utf8ToWideAlloc(commandUtf8);
    if (!wcmd)
        return false;

    wchar_t *escaped = dup_and_escape_quotes_for_cmdline(wcmd);
    if (!escaped)
    {
        free(wcmd);
        return false;
    }

    wchar_t args[8192];
    if (keepWindow)
    {
        _snwprintf(args, (int)(sizeof(args) / sizeof(args[0])),
                   L"-NoProfile -ExecutionPolicy Bypass -NoExit -Command \"%s\"", escaped);
    }
    else
    {
        if (hideWindow)
        {
            _snwprintf(args, (int)(sizeof(args) / sizeof(args[0])),
                       L"-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -Command \"%s\"", escaped);
        }
        else
        {
            _snwprintf(args, (int)(sizeof(args) / sizeof(args[0])),
                       L"-NoProfile -ExecutionPolicy Bypass -Command \"%s\"", escaped);
        }
    }

    bool newConsole = !hideWindow;

    DWORD pid = 0;
    bool ok = create_process_ex(L"powershell.exe", args, hideWindow, newConsole, true, &pid);
    if (outPid)
        *outPid = (unsigned long)pid;
    RC_LogInfo("PowerShell 已启动 (pid=%lu)", (unsigned long)pid);

    free(escaped);
    free(wcmd);
    return ok;
}

bool RC_ActionKillByPathUtf8(const char *pathUtf8)
{
    /*
     * 通过“可执行路径”定位并结束进程（best-effort）。
     *
     * 实际策略：
     * - 仅取路径的 basename（例如 C:\a\b\foo.exe -> foo.exe），然后执行：
     *   taskkill.exe /F /IM "foo.exe"
     *
     * 风险/限制：
     * - 这会杀掉所有同名进程（不区分路径），因此仅适合“唯一进程名”的场景。
     */
    if (!pathUtf8 || !*pathUtf8)
        return false;

    char *tmp = _strdup(pathUtf8);
    if (!tmp)
        return false;
    RC_NormalizePathSlashes(tmp);

    const char *base = strrchr(tmp, '\\');
    base = base ? base + 1 : tmp;
    if (!*base)
    {
        free(tmp);
        return false;
    }

    wchar_t *wbase = RC_Utf8ToWideAlloc(base);
    if (!wbase)
    {
        free(tmp);
        return false;
    }

    wchar_t args[512];
    _snwprintf(args, (int)(sizeof(args) / sizeof(args[0])), L"/F /IM \"%s\"", wbase);
    DWORD pid = 0;
    bool ok = create_process_ex(L"taskkill.exe", args, true, false, false, &pid);
    RC_LogInfo("taskkill 已启动 (pid=%lu) 目标=%s", (unsigned long)pid, base);

    free(wbase);
    free(tmp);
    return ok;
}

static bool run_sc_command(const wchar_t *verb, const wchar_t *service)
{
    /*
     * sc.exe 封装：用于 start/stop 等最常用的服务控制。
     *
     * 说明：
     * - verb 典型值：L"start" / L"stop"。
     * - service 会被用引号包裹，尽量兼容包含空格的服务显示名/键名。
     * - 这里不解析 sc.exe 的 stdout/stderr，仅关注 CreateProcess 是否成功启动（best-effort）。
     */
    wchar_t args[512];
    _snwprintf(args, (int)(sizeof(args) / sizeof(args[0])), L"%s \"%s\"", verb, service);
    DWORD pid = 0;
    return create_process_ex(L"sc.exe", args, true, false, false, &pid);
}

bool RC_ActionTaskkillPidTree(unsigned long pid)
{
    // 强制结束 PID 及其子进程树：taskkill /F /T /PID <pid>
    // - 使用 capture_output 记录 stdout/stderr，便于定位失败原因（权限/不存在等）。
    if (pid == 0)
        return false;
    wchar_t args[128];
    _snwprintf(args, (int)(sizeof(args) / sizeof(args[0])), L"/F /T /PID %lu", pid);
    DWORD exitCode = 0;
    char *outTxt = NULL;
    char *errTxt = NULL;
    bool ok = create_process_capture_output(L"taskkill.exe", args, 15000, &exitCode, &outTxt, &errTxt);
    if (ok)
        RC_LogInfo("taskkill /F /T 成功 (pid=%lu)", pid);
    else
        RC_LogWarn("taskkill /F /T 失败 (pid=%lu, exit=%lu)", pid, (unsigned long)exitCode);
    if (outTxt && *outTxt)
        RC_LogInfo("taskkill 标准输出：%s", outTxt);
    if (errTxt && *errTxt)
        RC_LogWarn("taskkill 错误输出：%s", errTxt);
    free(outTxt);
    free(errTxt);
    return ok;
}

bool RC_ActionTaskkillPid(unsigned long pid)
{
    // 请求结束 PID（不强制、不杀子进程）：taskkill /PID <pid>
    if (pid == 0)
        return false;
    wchar_t args[128];
    _snwprintf(args, (int)(sizeof(args) / sizeof(args[0])), L"/PID %lu", pid);
    DWORD exitCode = 0;
    char *outTxt = NULL;
    char *errTxt = NULL;
    bool ok = create_process_capture_output(L"taskkill.exe", args, 15000, &exitCode, &outTxt, &errTxt);
    if (ok)
        RC_LogInfo("taskkill 成功 (pid=%lu)", pid);
    else
        RC_LogWarn("taskkill 失败 (pid=%lu, exit=%lu)", pid, (unsigned long)exitCode);
    if (outTxt && *outTxt)
        RC_LogInfo("taskkill 标准输出：%s", outTxt);
    if (errTxt && *errTxt)
        RC_LogWarn("taskkill 错误输出：%s", errTxt);
    free(outTxt);
    free(errTxt);
    return ok;
}

bool RC_ActionTaskkillPidForce(unsigned long pid)
{
    // 强制结束 PID（不杀子进程）：taskkill /PID <pid> /F
    if (pid == 0)
        return false;
    wchar_t args[128];
    _snwprintf(args, (int)(sizeof(args) / sizeof(args[0])), L"/PID %lu /F", pid);
    DWORD exitCode = 0;
    char *outTxt = NULL;
    char *errTxt = NULL;
    bool ok = create_process_capture_output(L"taskkill.exe", args, 15000, &exitCode, &outTxt, &errTxt);
    if (ok)
        RC_LogInfo("taskkill /F 成功 (pid=%lu)", pid);
    else
        RC_LogWarn("taskkill /F 失败 (pid=%lu, exit=%lu)", pid, (unsigned long)exitCode);
    if (outTxt && *outTxt)
        RC_LogInfo("taskkill 标准输出：%s", outTxt);
    if (errTxt && *errTxt)
        RC_LogWarn("taskkill 错误输出：%s", errTxt);
    free(outTxt);
    free(errTxt);
    return ok;
}

bool RC_ActionTerminatePid(unsigned long pid)
{
    /*
     * 直接调用 TerminateProcess 结束进程。
     * - 这是更“暴力”的路径：不会走优雅退出，不会让目标进程清理资源。
     * - 需要对目标进程拥有 PROCESS_TERMINATE 权限。
     */
    if (pid == 0)
        return false;
    HANDLE h = OpenProcess(PROCESS_TERMINATE, FALSE, (DWORD)pid);
    if (!h)
    {
        RC_LogWarn("OpenProcess(PROCESS_TERMINATE) 失败 pid=%lu err=%lu", pid, GetLastError());
        return false;
    }
    BOOL ok = TerminateProcess(h, 1);
    if (!ok)
        RC_LogWarn("TerminateProcess 失败 pid=%lu err=%lu", pid, GetLastError());
    CloseHandle(h);
    return ok ? true : false;
}

bool RC_ActionSendCtrlBreak(unsigned long pid)
{
    /*
     * 发送 CTRL_BREAK_EVENT：用于“中断”类场景（类似 Python os.kill(..., CTRL_BREAK_EVENT)）。
     *
     * Windows 限制：
     * - 控制台控制事件是发往“进程组（process group）”的。
     * - 通常要求目标进程以 CREATE_NEW_PROCESS_GROUP 启动，且双方共享/可附加到控制台。
     *
     * 本实现策略：
     * - AttachConsole(pid) 尝试附加到目标控制台；GenerateConsoleCtrlEvent(..., pid) 发送事件。
     * - SetConsoleCtrlHandler(NULL, TRUE) 防止本进程被事件波及。
     */
    if (pid == 0)
        return false;

    // Ensure we are not attached to another console.
    FreeConsole();

    if (!AttachConsole((DWORD)pid))
    {
        RC_LogWarn("AttachConsole 失败 pid=%lu err=%lu", pid, GetLastError());
        return false;
    }

    // Prevent this process from being terminated by the ctrl event.
    SetConsoleCtrlHandler(NULL, TRUE);

    BOOL ok = GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, (DWORD)pid);
    if (!ok)
        RC_LogWarn("GenerateConsoleCtrlEvent 失败 pid=%lu err=%lu", pid, GetLastError());

    Sleep(200);
    FreeConsole();
    SetConsoleCtrlHandler(NULL, FALSE);
    return ok ? true : false;
}

bool RC_ActionSendCtrlBreakNoAttach(unsigned long pid)
{
    /*
     * 不 AttachConsole 的 best-effort 版本。
     * - 在很多情况下会失败（例如未共享控制台/目标不在同一控制台会话）。
     * - 保留该函数是为了最大化兼容不同启动方式。
     */
    if (pid == 0)
        return false;

    // Best-effort: mimic Python os.kill(pid, CTRL_BREAK_EVENT).
    // This may fail if we are not attached to a console shared with the target process group.
    FreeConsole();
    SetConsoleCtrlHandler(NULL, TRUE);

    BOOL ok = GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, (DWORD)pid);
    if (!ok)
        RC_LogWarn("GenerateConsoleCtrlEvent(不附加控制台) 失败 pid=%lu err=%lu", pid, GetLastError());

    Sleep(200);
    FreeConsole();
    SetConsoleCtrlHandler(NULL, FALSE);
    return ok ? true : false;
}

bool RC_ActionServiceStartUtf8(const char *serviceNameUtf8)
{
    // 启动服务：sc start <service>
    wchar_t *w = RC_Utf8ToWideAlloc(serviceNameUtf8 ? serviceNameUtf8 : "");
    if (!w || !*w)
    {
        free(w);
        return false;
    }
    RC_LogInfo("服务启动：%S", serviceNameUtf8);
    bool ok = run_sc_command(L"start", w);
    free(w);
    return ok;
}

bool RC_ActionServiceStopUtf8(const char *serviceNameUtf8)
{
    // 停止服务：sc stop <service>
    wchar_t *w = RC_Utf8ToWideAlloc(serviceNameUtf8 ? serviceNameUtf8 : "");
    if (!w || !*w)
    {
        free(w);
        return false;
    }
    RC_LogInfo("服务停止：%S", serviceNameUtf8);
    bool ok = run_sc_command(L"stop", w);
    free(w);
    return ok;
}

static void input_key_down(WORD vk)
{
    /*
     * SendInput 封装：按下一个 VK。
     * - 仅发送键盘事件，不处理扫描码/扩展键细节；本项目场景以常见 VK 足够。
     */
    INPUT in;
    ZeroMemory(&in, sizeof(in));
    in.type = INPUT_KEYBOARD;
    in.ki.wVk = vk;
    SendInput(1, &in, sizeof(INPUT));
}

static void input_key_up(WORD vk)
{
    /*
     * SendInput 封装：抬起一个 VK。
     */
    INPUT in;
    ZeroMemory(&in, sizeof(in));
    in.type = INPUT_KEYBOARD;
    in.ki.wVk = vk;
    in.ki.dwFlags = KEYEVENTF_KEYUP;
    SendInput(1, &in, sizeof(INPUT));
}

static void input_key_press(WORD vk)
{
    /*
     * SendInput 封装：一次“按下 + 抬起”。
     */
    input_key_down(vk);
    input_key_up(vk);
}

static WORD map_key_token(const char *tok)
{
    /*
     * 把“热键 token”映射为 Virtual-Key (VK_*)。
     *
     * 支持：
     * - 修饰键：ctrl/alt/shift/win
     * - 常用键名：enter/esc/tab/space/backspace/delete/insert/home/end/方向键/pageup/pagedown
     * - F1~F24（"f1".."f24"）
     * - 单字符：使用 VkKeyScanA 映射到键盘布局对应的 VK。
     */
    if (!tok)
        return 0;

    if (_stricmp(tok, "ctrl") == 0 || _stricmp(tok, "control") == 0)
        return VK_CONTROL;
    if (_stricmp(tok, "alt") == 0)
        return VK_MENU;
    if (_stricmp(tok, "shift") == 0)
        return VK_SHIFT;
    if (_stricmp(tok, "win") == 0 || _stricmp(tok, "meta") == 0 || _stricmp(tok, "super") == 0)
        return VK_LWIN;

    if (_stricmp(tok, "enter") == 0 || _stricmp(tok, "return") == 0)
        return VK_RETURN;
    if (_stricmp(tok, "esc") == 0 || _stricmp(tok, "escape") == 0)
        return VK_ESCAPE;
    if (_stricmp(tok, "tab") == 0)
        return VK_TAB;
    if (_stricmp(tok, "space") == 0)
        return VK_SPACE;
    if (_stricmp(tok, "backspace") == 0)
        return VK_BACK;
    if (_stricmp(tok, "delete") == 0)
        return VK_DELETE;
    if (_stricmp(tok, "insert") == 0)
        return VK_INSERT;
    if (_stricmp(tok, "home") == 0)
        return VK_HOME;
    if (_stricmp(tok, "end") == 0)
        return VK_END;
    if (_stricmp(tok, "up") == 0)
        return VK_UP;
    if (_stricmp(tok, "down") == 0)
        return VK_DOWN;
    if (_stricmp(tok, "left") == 0)
        return VK_LEFT;
    if (_stricmp(tok, "right") == 0)
        return VK_RIGHT;
    if (_stricmp(tok, "pageup") == 0 || _stricmp(tok, "pgup") == 0)
        return VK_PRIOR;
    if (_stricmp(tok, "pagedown") == 0 || _stricmp(tok, "pgdn") == 0)
        return VK_NEXT;

    if ((tok[0] == 'f' || tok[0] == 'F') && tok[1])
    {
        int n = atoi(tok + 1);
        if (n >= 1 && n <= 24)
            return (WORD)(VK_F1 + (n - 1));
    }

    // Single ascii character
    if (tok[0] && !tok[1])
    {
        SHORT vk = VkKeyScanA((CHAR)tok[0]);
        if (vk != -1)
            return (WORD)(vk & 0xFF);
    }

    return 0;
}

static void sleep_ms(int ms)
{
    /*
     * Sleep 小封装：仅在 ms>0 时休眠。
     * - 避免负数/0 传入导致不必要的系统调用。
     */
    if (ms > 0)
        Sleep((DWORD)ms);
}

bool RC_ActionHotkey(const char *actionType, const char *actionValue, int charDelayMs)
{
    /*
     * 热键/键盘模拟：
     *
     * 输入协议：
     * - actionType 目前只支持 "keyboard"（或 "none"）。
     * - actionValue 两种模式：
     *   1) 不含 '+'：把字符串当作“逐字符按键”（忽略空白），用于输入短文本/字母。
     *   2) 含 '+'：按组合键解析，例如 "ctrl+alt+del"、"win+r"。
     *      - 会先移除空白后再 split（对齐 Python 行为）。
     *      - 修饰键按固定优先级按下：ctrl -> alt -> shift -> win。
     *      - 非修饰键按出现顺序逐个 press。
     * - charDelayMs：字符/按键之间的延迟（毫秒），用于提高某些窗口对输入的接受率。
     */
    const char *t = actionType ? actionType : "none";
    const char *v = actionValue ? actionValue : "";

    if (_stricmp(t, "none") == 0)
        return true;
    if (_stricmp(t, "keyboard") != 0)
    {
        RC_LogWarn("热键不支持的类型：%s", t);
        return false;
    }

    // No '+' => press each character.
    if (!strchr(v, '+'))
    {
        for (const char *p = v; p && *p; p++)
        {
            if (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')
                continue;
            char tok[2] = {*p, 0};
            WORD vk = map_key_token(tok);
            if (vk)
                input_key_press(vk);
            sleep_ms(charDelayMs);
        }
        return true;
    }

    // Split by '+', press modifiers then final keys.
    // Match python behavior: remove spaces before splitting.
    char *buf = _strdup(v);
    if (!buf)
        return false;

    // Remove spaces by compacting (do NOT insert NULs).
    {
        char *w = buf;
        for (const char *p = buf; *p; p++)
        {
            if (*p != ' ' && *p != '\t' && *p != '\r' && *p != '\n')
                *w++ = *p;
        }
        *w = 0;
    }

    // Tokenize
    const int MAX_TOK = 32;
    const char *toks[MAX_TOK];
    int nt = 0;
    char *save = NULL;
    for (char *p = strtok_s(buf, "+", &save); p && nt < MAX_TOK; p = strtok_s(NULL, "+", &save))
    {
        if (*p)
            toks[nt++] = p;
    }

    // Hold modifiers in fixed priority order: ctrl, alt, shift, win (to match python).
    bool needCtrl = false, needAlt = false, needShift = false, needWin = false;
    for (int i = 0; i < nt; i++)
    {
        WORD vk = map_key_token(toks[i]);
        if (vk == VK_CONTROL)
            needCtrl = true;
        else if (vk == VK_MENU)
            needAlt = true;
        else if (vk == VK_SHIFT)
            needShift = true;
        else if (vk == VK_LWIN)
            needWin = true;
    }

    bool heldCtrl = false, heldAlt = false, heldShift = false, heldWin = false;
    if (needCtrl)
    {
        input_key_down(VK_CONTROL);
        heldCtrl = true;
    }
    if (needAlt)
    {
        input_key_down(VK_MENU);
        heldAlt = true;
    }
    if (needShift)
    {
        input_key_down(VK_SHIFT);
        heldShift = true;
    }
    if (needWin)
    {
        input_key_down(VK_LWIN);
        heldWin = true;
    }

    // Press non-mod keys in order
    for (int i = 0; i < nt; i++)
    {
        WORD vk = map_key_token(toks[i]);
        if (vk == VK_CONTROL || vk == VK_MENU || vk == VK_SHIFT || vk == VK_LWIN)
            continue;

        if (vk)
        {
            input_key_press(vk);
            sleep_ms(charDelayMs);
        }
        else
        {
            // If token is alphabetic word, press each character like python.
            const char *s = toks[i];
            bool allAlpha = true;
            for (const char *p = s; *p; p++)
            {
                if ((*p < 'A' || *p > 'Z') && (*p < 'a' || *p > 'z'))
                {
                    allAlpha = false;
                    break;
                }
            }
            if (allAlpha)
            {
                for (const char *p = s; *p; p++)
                {
                    char tok[2] = {*p, 0};
                    WORD vkc = map_key_token(tok);
                    if (vkc)
                        input_key_press(vkc);
                    sleep_ms(charDelayMs);
                }
            }
        }
    }

    // Release modifiers
    if (heldWin)
        input_key_up(VK_LWIN);
    if (heldShift)
        input_key_up(VK_SHIFT);
    if (heldAlt)
        input_key_up(VK_MENU);
    if (heldCtrl)
        input_key_up(VK_CONTROL);

    free(buf);
    return true;
}
