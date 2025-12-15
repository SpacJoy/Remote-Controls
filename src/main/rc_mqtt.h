#pragma once

#include <stdbool.h>

#include "rc_router.h"

#ifdef __cplusplus
extern "C"
{
#endif

    /*
     * MQTT 通信模块：
     * - 负责连接 broker、订阅 topic、接收消息并转交给 Router。
     * - 内部包含自动重连（reconnectMinSeconds ~ reconnectMaxSeconds 退避）。
     *
     * 注意：本项目同时支持不同 MQTT 实现（例如 Paho），具体实现细节见 rc_mqtt.c。
     */

    typedef struct RC_MqttConfig
    {
        // broker 主机名（UTF-8），例如 "bemfa.com"；不能为空时才会尝试连接。
        const char *brokerHost;

        // broker 端口（明文 TCP），例如 9501。
        int port;

        // 是否启用 TLS/SSL 加密连接（Paho 模式下将使用 ssl://）。
        // 注意：这要求构建时链接 Paho SSL 版本库（例如 paho-mqtt3cs）。
        bool useTls;

        /*
         * 鉴权模式：
         * - "private_key"：由上层转换/填充为 username/password（如果实现需要）。
         * - "username_password"：直接使用 username/password。
         *
         * 具体模式支持范围由 rc_mqtt.c 的实现决定。
         */
        const char *authMode;

        // MQTT ClientId（UTF-8）。为空时实现会使用默认值（例如 "RC-main"）。
        const char *clientId;

        // 用户名/密码（UTF-8，可选）。当鉴权模式要求且两者都非空时才会携带。
        const char *username;
        const char *password;

        // keep-alive 秒数；<=0 时实现会使用默认值（例如 60）。
        int keepAliveSeconds;

        // 重连退避最小/最大秒数；<=0 时实现会使用默认值（例如 2~30）。
        int reconnectMinSeconds;
        int reconnectMaxSeconds;
    } RC_MqttConfig;

    /*
     * 阻塞式主循环：connect -> subscribe -> recv publish -> dispatch to router。
     * - shouldStop：外部可置为 true 以请求退出。
     * - 返回条件：
     *   1) 鉴权失败等“不可恢复”的错误；或
     *   2) shouldStop 变为 true。
     */
    void RC_MqttRunLoop(const RC_MqttConfig *cfg, RC_Router *router, volatile bool *shouldStop);

#ifdef __cplusplus
}
#endif
