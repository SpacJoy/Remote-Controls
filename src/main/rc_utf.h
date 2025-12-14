#pragma once

#include <windows.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C"
{
#endif

    /*
     * UTF 编码工具：
     * - Windows API 常用 UTF-16LE（wchar_t*）。
     * - 配置/网络消息常用 UTF-8（char*）。
     * 这里提供两者互转的 malloc 分配版本。
     */

    /*
     * UTF-8 -> UTF-16（wchar_t*）。
     * - 返回值需调用方 free。
     * - 失败返回 NULL。
     */
    wchar_t *RC_Utf8ToWideAlloc(const char *s);

    /*
     * UTF-16（wchar_t*）-> UTF-8。
     * - 返回值需调用方 free。
     * - 失败返回 NULL。
     */
    char *RC_WideToUtf8Alloc(const wchar_t *w);

    /*
     * 就地规范化路径分隔符：把 '/' 替换为 '\\'（best-effort）。
     * - 仅做字符替换，不做路径规范化/去重/绝对化。
     */
    void RC_NormalizePathSlashes(char *s);

#ifdef __cplusplus
}
#endif
