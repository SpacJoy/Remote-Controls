#pragma once

#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C"
{
#endif

    /*
     * 轻量 JSON 解析/构建工具（UTF-8）。
     *
     * 设计要点：
     * - 解析：RC_JsonParse(textUtf8, &err)
     * - 内存：所有节点由 RC_JsonFree 统一释放；对象 set 操作会“接管(value 的所有权)”。
     * - 访问：提供类型判断与常用取值（string/int/bool）
     * - 序列化：RC_JsonPrintPretty 返回 malloc 字符串，调用方 free。
     */

    typedef enum RC_JsonType
    {
        RC_JSON_NULL = 0,
        RC_JSON_BOOL,
        RC_JSON_NUMBER,
        RC_JSON_STRING,
        RC_JSON_ARRAY,
        RC_JSON_OBJECT,
    } RC_JsonType;

    typedef struct RC_Json RC_Json;

    typedef struct RC_JsonError
    {
        size_t offset; // byte offset in input (UTF-8)
        const char *message;
    } RC_JsonError;

    /*
     * 解析 JSON 文本（UTF-8）。
     * - 成功：返回根节点（调用方负责 RC_JsonFree）。
     * - 失败：返回 NULL，并尽量填充 err（offset 为 UTF-8 字节偏移，message 为错误描述）。
     */
    RC_Json *RC_JsonParse(const char *text, RC_JsonError *err);

    /*
     * 释放节点（递归释放子节点）。
     */
    void RC_JsonFree(RC_Json *node);

    RC_JsonType RC_JsonGetType(const RC_Json *node);

    bool RC_JsonIsObject(const RC_Json *node);
    bool RC_JsonIsArray(const RC_Json *node);
    bool RC_JsonIsString(const RC_Json *node);
    bool RC_JsonIsNumber(const RC_Json *node);
    bool RC_JsonIsBool(const RC_Json *node);

    const char *RC_JsonGetString(const RC_Json *node);
    int RC_JsonGetInt(const RC_Json *node, int defVal);
    bool RC_JsonGetBool(const RC_Json *node, bool defVal);

    /*
     * 对象取字段：
     * - obj 必须是 object；key 为 UTF-8。
     * - 不存在返回 NULL。
     */
    RC_Json *RC_JsonObjectGet(const RC_Json *obj, const char *key);

    /*
     * 对象写字段（仅 object）。
     * - 若 key 已存在，行为由实现决定（通常为覆盖）。
     * - 返回 true 表示写入成功。
     */
    bool RC_JsonObjectSetString(RC_Json *obj, const char *key, const char *val);
    bool RC_JsonObjectSetNumber(RC_Json *obj, const char *key, double val);
    bool RC_JsonObjectSetBool(RC_Json *obj, const char *key, bool val);

    /*
     * 序列化为可读 JSON（pretty）。
     * - 返回 malloc 字符串，调用方 free。
     */
    char *RC_JsonPrintPretty(const RC_Json *node);

#ifdef __cplusplus
}
#endif
