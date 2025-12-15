/*
 * rc_main_tray.c
 *
 * 主程序内置最小托盘（fallback tray）实现。
 *
 * 目标：当外部托盘 RC-tray.exe 未运行时，仍能给用户提供最基本的托盘入口（状态/打开配置/退出）。
 *
 * 关键点：
 * - 托盘通过隐藏窗口 + NOTIFYICONDATAW 实现。
 * - 通过 Toolhelp32Snapshot/Process32FirstW/Process32NextW 枚举进程，判断 RC-tray.exe 是否已运行。
 * - “退出”通过将 *stopFlag 置为 true 通知主循环结束。
 */

#include "rc_main_tray.h"

#include "rc_log.h"

#include <windows.h>
#include <shellapi.h>
#include <shlwapi.h>
#include <tlhelp32.h>
#include <process.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WM_RCMAIN_TRAYICON (WM_USER + 100)
#define RCMAIN_TRAY_ICON_ID 1

#define IDM_STATUS 2001
#define IDM_OPEN_CONFIG 2002
#define IDM_EXIT 2003

typedef struct
{
    wchar_t appDirW[MAX_PATH];
    char versionUtf8[64];
    volatile bool *stopFlag;
    bool langEnglish;
} MainTrayParams;

/*
 * UTF-8 -> UTF-16 小工具（用于托盘 tooltip 等 UI 字符串）。
 * - dstCount 以 wchar_t 计数。
 * - src 允许为 NULL（当作空字符串）。
 */
static BOOL utf8_to_wide(const char *src, wchar_t *dst, int dstCount)
{
    if (!dst || dstCount <= 0)
        return FALSE;
    dst[0] = L'\0';
    if (!src)
        return TRUE;
    return MultiByteToWideChar(CP_UTF8, 0, src, -1, dst, dstCount) > 0;
}

static BOOL is_user_admin(void)
{
    // 使用 shell32!IsUserAnAdmin（老 API，但足够用于托盘显示状态）。
    HMODULE shell32 = GetModuleHandleW(L"shell32.dll");
    if (!shell32)
        return FALSE;
    typedef BOOL(WINAPI * IsUserAnAdminFn)(void);
    IsUserAnAdminFn fn = (IsUserAnAdminFn)GetProcAddress(shell32, "IsUserAnAdmin");
    if (!fn)
        return FALSE;
    return fn();
}

/*
 * 判断指定进程名是否正在运行（仅按 exe 文件名匹配，不含路径）。
 * - 基于 Toolhelp32Snapshot 进程枚举；开销较低，适合托盘初始化时做一次判断。
 */
static BOOL is_process_running_w(const wchar_t *exeNameW)
{
    if (!exeNameW || !*exeNameW)
        return FALSE;

    // 创建系统进程快照并遍历，判断指定 exeName 是否存在。
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap == INVALID_HANDLE_VALUE)
        return FALSE;

    PROCESSENTRY32W pe;
    pe.dwSize = sizeof(pe);

    BOOL running = FALSE;
    if (Process32FirstW(snap, &pe))
    {
        do
        {
            if (_wcsicmp(pe.szExeFile, exeNameW) == 0)
            {
                running = TRUE;
                break;
            }
        } while (Process32NextW(snap, &pe));
    }

    CloseHandle(snap);
    return running;
}

static HICON load_tray_icon(const wchar_t *appDirW)
{
    // Prefer res\\icon.ico if present, else fall back to default.
    wchar_t iconPathW[MAX_PATH] = {0};
    _snwprintf(iconPathW, MAX_PATH, L"%s\\res\\icon.ico", appDirW ? appDirW : L"");
    iconPathW[MAX_PATH - 1] = 0;

    if (PathFileExistsW(iconPathW))
    {
        HICON h = (HICON)LoadImageW(NULL, iconPathW, IMAGE_ICON, 16, 16, LR_LOADFROMFILE);
        if (h)
            return h;
    }

    return LoadIconW(NULL, IDI_APPLICATION);
}

/*
 * 打开配置界面：优先启动 RC-GUI.exe。
 * - 这是“内置最小托盘”的设计选择：只提供最基础的入口，不在此处实现复杂的兜底逻辑。
 */
static void open_config_gui(const wchar_t *appDirW, bool langEnglish)
{
    wchar_t guiPathW[MAX_PATH] = {0};
    _snwprintf(guiPathW, MAX_PATH, L"%s\\RC-GUI.exe", appDirW ? appDirW : L"");
    guiPathW[MAX_PATH - 1] = 0;

    if (PathFileExistsW(guiPathW))
    {
        ShellExecuteW(NULL, L"open", guiPathW, NULL, appDirW, SW_SHOWNORMAL);
        return;
    }

    if (langEnglish)
        MessageBoxW(NULL, L"RC-GUI.exe not found.", L"RC-main", MB_ICONERROR);
    else
        MessageBoxW(NULL, L"未找到 RC-GUI.exe。", L"RC-main", MB_ICONERROR);
}

/*
 * 托盘气泡提示（Balloon）。
 * - 这里通过 NIM_MODIFY + NIF_INFO 更新气泡字段。
 * - 注意：不同 Windows 版本对气泡显示策略不同，可能被系统策略/勿扰模式抑制。
 */
static void show_info_balloon(NOTIFYICONDATAW *nid, const wchar_t *titleW, const wchar_t *msgW)
{
    if (!nid)
        return;

    nid->uFlags = NIF_INFO;
    wcsncpy_s(nid->szInfoTitle, _countof(nid->szInfoTitle), titleW ? titleW : L"RC-main", _TRUNCATE);
    wcsncpy_s(nid->szInfo, _countof(nid->szInfo), msgW ? msgW : L"", _TRUNCATE);
    nid->dwInfoFlags = NIIF_INFO;
    Shell_NotifyIconW(NIM_MODIFY, nid);
}

typedef struct
{
    HWND hWnd;
    NOTIFYICONDATAW nid;
    MainTrayParams *params;
} MainTrayState;

static LRESULT CALLBACK main_tray_wndproc(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam)
{
    MainTrayState *st = (MainTrayState *)GetWindowLongPtrW(hWnd, GWLP_USERDATA);

    switch (msg)
    {
    case WM_CREATE:
    {
        // WM_CREATE 时从 CREATESTRUCTW::lpCreateParams 取回 state 指针。
        // 该指针来自 CreateWindowExW 的最后一个参数。
        CREATESTRUCTW *cs = (CREATESTRUCTW *)lParam;
        st = (MainTrayState *)cs->lpCreateParams;
        SetWindowLongPtrW(hWnd, GWLP_USERDATA, (LONG_PTR)st);
        st->hWnd = hWnd;

        ZeroMemory(&st->nid, sizeof(st->nid));
        st->nid.cbSize = sizeof(st->nid);
        st->nid.hWnd = hWnd;
        st->nid.uID = RCMAIN_TRAY_ICON_ID;
        st->nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
        st->nid.uCallbackMessage = WM_RCMAIN_TRAYICON;
        st->nid.hIcon = load_tray_icon(st->params ? st->params->appDirW : NULL);

        wchar_t tipW[128] = {0};
        if (st->params && st->params->versionUtf8[0])
        {
            char tipUtf8[128] = {0};
            if (st->params && st->params->langEnglish)
                _snprintf(tipUtf8, sizeof(tipUtf8), "Remote Controls-%s", st->params->versionUtf8);
            else
                _snprintf(tipUtf8, sizeof(tipUtf8), "远程控制-%s", st->params->versionUtf8);
            utf8_to_wide(tipUtf8, tipW, (int)_countof(tipW));
        }
        else
        {
            if (st->params && st->params->langEnglish)
                wcsncpy_s(tipW, _countof(tipW), L"Remote Controls", _TRUNCATE);
            else
                wcsncpy_s(tipW, _countof(tipW), L"远程控制", _TRUNCATE);
        }
        wcsncpy_s(st->nid.szTip, _countof(st->nid.szTip), tipW, _TRUNCATE);

        Shell_NotifyIconW(NIM_ADD, &st->nid);

        // Match Python main.py behavior: notify that fallback tray is used.
        // Notify that fallback tray is used.
        if (st->params && st->params->langEnglish)
            show_info_balloon(&st->nid, L"RC-main", L"Tray not running. Using built-in tray.");
        else
            show_info_balloon(&st->nid, L"RC-main", L"托盘未启动，将使用自带托盘");
        return 0;
    }

    case WM_DESTROY:
        if (st)
        {
            Shell_NotifyIconW(NIM_DELETE, &st->nid);
        }
        PostQuitMessage(0);
        return 0;

    case WM_RCMAIN_TRAYICON:
        if (lParam == WM_RBUTTONUP)
        {
            // 右键弹出菜单：提供“打开配置/退出”。
            POINT pt;
            GetCursorPos(&pt);

            HMENU menu = CreatePopupMenu();
            if (menu)
            {
                const bool en = (st && st->params && st->params->langEnglish);
                const wchar_t *statusTextW = is_user_admin() ? (en ? L"[Admin: Yes]" : L"【已获得管理员权限】")
                                                             : (en ? L"[Admin: No]" : L"【未获得管理员权限】");
                InsertMenuW(menu, -1, MF_BYPOSITION | MF_STRING | MF_GRAYED, IDM_STATUS, statusTextW);
                InsertMenuW(menu, -1, MF_BYPOSITION | MF_STRING, IDM_OPEN_CONFIG, en ? L"Open config" : L"打开配置");
                InsertMenuW(menu, -1, MF_BYPOSITION | MF_SEPARATOR, 0, NULL);
                InsertMenuW(menu, -1, MF_BYPOSITION | MF_STRING, IDM_EXIT, en ? L"Exit" : L"退出");

                SetForegroundWindow(hWnd);
                TrackPopupMenu(menu, TPM_LEFTALIGN | TPM_RIGHTBUTTON, pt.x, pt.y, 0, hWnd, NULL);
                DestroyMenu(menu);
            }
        }
        else if (lParam == WM_LBUTTONDBLCLK)
        {
            // 双击：快捷打开 GUI。
            open_config_gui(st && st->params ? st->params->appDirW : NULL,
                            (st && st->params) ? st->params->langEnglish : false);
        }
        return 0;

    case WM_COMMAND:
        switch (LOWORD(wParam))
        {
        case IDM_OPEN_CONFIG:
            open_config_gui(st && st->params ? st->params->appDirW : NULL,
                            (st && st->params) ? st->params->langEnglish : false);
            break;
        case IDM_EXIT:
            // “退出”语义：置 stopFlag=true 通知 MQTT 主循环退出，然后销毁托盘窗口。
            if (st && st->params && st->params->stopFlag)
            {
                *st->params->stopFlag = true;
            }
            DestroyWindow(hWnd);
            break;
        default:
            break;
        }
        return 0;

    default:
        break;
    }

    return DefWindowProcW(hWnd, msg, wParam, lParam);
}

static unsigned __stdcall main_tray_thread(void *arg)
{
    MainTrayParams *p = (MainTrayParams *)arg;
    if (!p)
        return 0;

    // 与 Python 版本行为对齐：延迟一小段时间后再判断 RC-tray.exe。
    // 目的：给外部托盘一个“先启动”的机会，避免启动瞬间竞态导致重复托盘。
    Sleep(1000);

    if (is_process_running_w(L"RC-tray.exe"))
    {
        if (p->langEnglish)
            RC_LogInfo("RC-tray.exe detected; skip built-in tray");
        else
            RC_LogInfo("检测到 RC-tray.exe；跳过主程序自带托盘");
        free(p);
        return 0;
    }

    WNDCLASSEXW wc;
    ZeroMemory(&wc, sizeof(wc));
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = main_tray_wndproc;
    wc.hInstance = GetModuleHandleW(NULL);
    wc.lpszClassName = L"RCMainFallbackTrayClass";

    if (!RegisterClassExW(&wc))
    {
        if (p->langEnglish)
            RC_LogWarn("Built-in tray RegisterClassExW failed");
        else
            RC_LogWarn("主程序自带托盘 RegisterClassExW 失败");
        free(p);
        return 0;
    }

    MainTrayState st;
    ZeroMemory(&st, sizeof(st));
    st.params = p;

    // 重要：st 是线程栈变量，但窗口消息循环也在本线程内运行，
    // 且线程不会在窗口销毁前返回，因此 st 的生命周期覆盖整个托盘窗口生命周期。

    HWND hWnd = CreateWindowExW(
        0,
        wc.lpszClassName,
        L"RC-main",
        WS_OVERLAPPED,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        NULL,
        NULL,
        wc.hInstance,
        &st);

    if (!hWnd)
    {
        RC_LogWarn("主程序自带托盘 CreateWindowExW 失败");
        free(p);
        return 0;
    }

    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0) > 0)
    {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }

    free(p);
    return 0;
}

void RC_MainTrayStartDelayed(const wchar_t *appDirW, const char *versionUtf8, volatile bool *stopFlag, bool langEnglish)
{
    if (!appDirW || !*appDirW)
        return;

    // 参数打包后交给后台线程：避免阻塞主线程（MQTT 连接/订阅/接收）。
    // stopFlag 是外部共享状态，线程只写 true，不做复杂同步。

    MainTrayParams *p = (MainTrayParams *)calloc(1, sizeof(*p));
    if (!p)
        return;

    wcsncpy_s(p->appDirW, _countof(p->appDirW), appDirW, _TRUNCATE);
    if (versionUtf8 && *versionUtf8)
        strncpy_s(p->versionUtf8, sizeof(p->versionUtf8), versionUtf8, _TRUNCATE);
    p->stopFlag = stopFlag;
    p->langEnglish = langEnglish;

    uintptr_t th = _beginthreadex(NULL, 0, main_tray_thread, p, 0, NULL);
    if (th)
    {
        CloseHandle((HANDLE)th);
    }
    else
    {
        free(p);
    }
}
