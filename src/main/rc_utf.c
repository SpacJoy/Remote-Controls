/*
 * rc_utf.c
 *
 * UTF-8 <-> UTF-16（wchar_t）互转实现。
 *
 * - MultiByteToWideChar(CP_UTF8, ...)：UTF-8 -> UTF-16。
 * - WideCharToMultiByte(CP_UTF8, ...)：UTF-16 -> UTF-8。
 *
 * 说明：这里均采用“先查询所需长度，再分配，再转换”的安全写法。
 */

#include "rc_utf.h"

#include <stdlib.h>
#include <string.h>

wchar_t *RC_Utf8ToWideAlloc(const char *s)
{
    if (!s)
        s = "";
    // 第一次调用：needed 获取目标 wchar_t 数量（含结尾 L'\0'）。
    int needed = MultiByteToWideChar(CP_UTF8, 0, s, -1, NULL, 0);
    if (needed <= 0)
        return NULL;
    wchar_t *w = (wchar_t *)malloc((size_t)needed * sizeof(wchar_t));
    if (!w)
        return NULL;
    // 第二次调用：执行实际转换。
    if (!MultiByteToWideChar(CP_UTF8, 0, s, -1, w, needed))
    {
        free(w);
        return NULL;
    }
    return w;
}

char *RC_WideToUtf8Alloc(const wchar_t *w)
{
    if (!w)
        w = L"";
    // 第一次调用：needed 获取目标 UTF-8 字节数（含结尾 '\0'）。
    int needed = WideCharToMultiByte(CP_UTF8, 0, w, -1, NULL, 0, NULL, NULL);
    if (needed <= 0)
        return NULL;
    char *s = (char *)malloc((size_t)needed);
    if (!s)
        return NULL;
    // 第二次调用：执行实际转换。
    if (!WideCharToMultiByte(CP_UTF8, 0, w, -1, s, needed, NULL, NULL))
    {
        free(s);
        return NULL;
    }
    return s;
}

void RC_NormalizePathSlashes(char *s)
{
    if (!s)
        return;
    // Windows 路径兼容：把 URL/JSON 中常见的 '/' 统一替换为 '\\'。
    for (; *s; s++)
    {
        if (*s == '/')
            *s = '\\';
    }
}
