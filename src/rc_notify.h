#pragma once

#include <windows.h>
#include <shellapi.h>

#ifdef __cplusplus
extern "C"
{
#endif

    // Show a balloon/notification on an existing NotifyIcon.
    //
    // Notes:
    // - The caller must have already added the icon via Shell_NotifyIconW(NIM_ADD, ...).
    // - To use NIF_INFO fields reliably, cbSize must be >= NOTIFYICONDATA_V3_SIZE.
    //   This module will bump cbSize up to sizeof(NOTIFYICONDATAW) if needed.
    // - clearFirst=TRUE sends an empty notification first, then the real content.
    BOOL RC_NotifyShowUtf8(NOTIFYICONDATAW *nid,
                           const char *titleUtf8,
                           const char *messageUtf8,
                           DWORD infoFlags,
                           BOOL clearFirst);

    BOOL RC_NotifyShowW(NOTIFYICONDATAW *nid,
                        const wchar_t *titleW,
                        const wchar_t *messageW,
                        DWORD infoFlags,
                        BOOL clearFirst);

#ifdef __cplusplus
}
#endif
