#include "rc_notify.h"

#include <string.h>

#ifndef _countof
#define _countof(arr) (sizeof(arr) / sizeof((arr)[0]))
#endif

static BOOL utf8_to_wide0(const char *src, wchar_t *dst, int dstCount)
{
    if (!dst || dstCount <= 0)
        return FALSE;
    dst[0] = L'\0';
    if (!src)
        return TRUE;
    return MultiByteToWideChar(CP_UTF8, 0, src, -1, dst, dstCount) > 0;
}

static void ensure_cbsize_for_info(NOTIFYICONDATAW *nid)
{
    if (!nid)
        return;

    // Balloon fields (szInfoTitle/szInfo) were introduced with NOTIFYICONDATA V3.
    // If cbSize is too small, Shell_NotifyIcon will ignore those fields.
    if (nid->cbSize < NOTIFYICONDATA_V3_SIZE)
    {
        nid->cbSize = (DWORD)sizeof(NOTIFYICONDATAW);
    }
}

static BOOL clear_notification(NOTIFYICONDATAW *nid)
{
    if (!nid)
        return FALSE;

    ensure_cbsize_for_info(nid);

    nid->uFlags = NIF_INFO;
    nid->szInfoTitle[0] = L'\0';
    nid->szInfo[0] = L'\0';
    nid->dwInfoFlags = NIIF_NONE;
    return Shell_NotifyIconW(NIM_MODIFY, nid);
}

BOOL RC_NotifyShowUtf8(NOTIFYICONDATAW *nid,
                       const char *titleUtf8,
                       const char *messageUtf8,
                       DWORD infoFlags,
                       BOOL clearFirst)
{
    if (!nid)
        return FALSE;

    ensure_cbsize_for_info(nid);

    if (clearFirst)
    {
        (void)clear_notification(nid);
        Sleep(10);
    }

    nid->uFlags = NIF_INFO;
    utf8_to_wide0(titleUtf8, nid->szInfoTitle, (int)_countof(nid->szInfoTitle));
    utf8_to_wide0(messageUtf8, nid->szInfo, (int)_countof(nid->szInfo));
    nid->dwInfoFlags = infoFlags;

    return Shell_NotifyIconW(NIM_MODIFY, nid);
}

BOOL RC_NotifyShowW(NOTIFYICONDATAW *nid,
                    const wchar_t *titleW,
                    const wchar_t *messageW,
                    DWORD infoFlags,
                    BOOL clearFirst)
{
    if (!nid)
        return FALSE;

    ensure_cbsize_for_info(nid);

    if (clearFirst)
    {
        (void)clear_notification(nid);
        Sleep(10);
    }

    nid->uFlags = NIF_INFO;
    wcsncpy_s(nid->szInfoTitle, _countof(nid->szInfoTitle), titleW ? titleW : L"", _TRUNCATE);
    wcsncpy_s(nid->szInfo, _countof(nid->szInfo), messageW ? messageW : L"", _TRUNCATE);
    nid->dwInfoFlags = infoFlags;

    return Shell_NotifyIconW(NIM_MODIFY, nid);
}
