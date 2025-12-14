#pragma once

#include <stdbool.h>

#include "../rc_json.h"

#ifdef __cplusplus
extern "C"
{
#endif

    /*
     * 路由模块（Router）：
     * - 根据配置文件中的“主题(topic) -> 动作(action)”映射，决定订阅哪些 MQTT topic。
     * - 收到消息后，根据 topic 和 payload（例如 on/off/on#xx）执行对应动作。
     *
     * 这里的 Router 持有配置树（RC_Json*），并在销毁时释放。
     */

    typedef struct RC_Router RC_Router;

    /*
     * 创建路由器。
     * - configRoot：配置 JSON 根对象（RC_Json*）。
     * - 所有权：Router 接管该指针，RC_RouterDestroy 时会 RC_JsonFree。
     */
    RC_Router *RC_RouterCreate(RC_Json *configRoot);

    /*
     * 销毁路由器并释放其持有资源（包括配置 JSON）。
     */
    void RC_RouterDestroy(RC_Router *r);

    /*
     * 获取需要订阅的 topic 列表。
     * - outCount：返回条目数。
     * - 返回指针由 Router 持有，生命周期直到 RC_RouterDestroy。
     */
    const char *const *RC_RouterGetTopics(const RC_Router *r, int *outCount);

    /*
     * 处理一条 MQTT 消息。
     * - topicUtf8：MQTT topic（UTF-8）。
     * - payloadUtf8：消息 payload 解析为 UTF-8 指令字符串（例如 "on" / "off" / "on#55"）。
     *
     * 典型流程：
     * 1) 找到 topic 对应的“设备/功能”配置项。
     * 2) 根据 payload 选择 on/off 动作与延迟。
     * 3) 调用 rc_actions 执行实际动作。
     */
    void RC_RouterHandle(RC_Router *r, const char *topicUtf8, const char *payloadUtf8);

#ifdef __cplusplus
}
#endif
