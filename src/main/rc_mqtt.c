/*
 * rc_mqtt.c
 *
 * MQTT 主循环实现（仅使用 Paho MQTT C）。
 * - 使用同步客户端 MQTTClient（阻塞式 connect/subscribe/receive）。
 * - 收到 publish 后把 topic/payload 交给 RC_RouterHandle。
 * - 对“不可恢复”的鉴权失败（BAD_USERNAME_OR_PASSWORD/NOT_AUTHORIZED）直接返回，
 *   让上层引导用户修复配置。
 */

#include "rc_mqtt.h"

// Safety limits for incoming MQTT data (payloads are expected to be small: on/off/on#n).
#define RC_MQTT_MAX_PAYLOAD_BYTES (4096)
#define RC_MQTT_LOG_PREVIEW_BYTES (128)

// 强制仅使用 Paho MQTT C：构建必须定义 RC_USE_PAHO_MQTT 并提供 Paho 头文件/库。
// 说明：为避免 VS Code IntelliSense 全红，这里跳过 __INTELLISENSE__ 分析场景。
#if !defined(RC_USE_PAHO_MQTT) && !defined(__INTELLISENSE__)
#error "This build requires Paho MQTT C. Please define RC_USE_PAHO_MQTT and link against paho-mqtt3c (or paho-mqtt3cs for SSL)."
#endif

#include "rc_log.h"

#include <windows.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <MQTTClient.h>

static const char *rc_title_for_notify(const RC_Router *router)
{
    return (router && RC_RouterIsEnglish(router)) ? "Remote Controls" : "远程控制";
}

static void notify_status_throttled(RC_Router *router, DWORD *pLastTick, DWORD minIntervalMs, const char *messageUtf8)
{
    if (!router || !messageUtf8 || !*messageUtf8)
        return;
    DWORD now = GetTickCount();
    if (pLastTick && *pLastTick != 0 && (now - *pLastTick) < minIntervalMs)
        return;
    if (pLastTick)
        *pLastTick = now;
    RC_RouterNotifyUtf8(router, rc_title_for_notify(router), messageUtf8);
}

static void mqtt_sanitize_preview(const char *in, char *out, size_t outLen)
{
    if (!out || outLen == 0)
        return;
    out[0] = '\0';
    if (!in)
        return;

    size_t j = 0;
    for (size_t i = 0; in[i] != '\0' && j + 1 < outLen; i++)
    {
        unsigned char c = (unsigned char)in[i];
        if (c == '\r' || c == '\n' || c == '\t')
            c = ' ';
        else if (c < 0x20)
            c = '?';
        out[j++] = (char)c;
    }
    out[j] = '\0';
}

static void log_mqtt_message(RC_Router *router, const char *topic, const char *payload)
{
    if (!topic)
        topic = "";
    if (!payload)
        payload = "";

    char preview[RC_MQTT_LOG_PREVIEW_BYTES];
    mqtt_sanitize_preview(payload, preview, sizeof(preview));
    unsigned int payloadLen = (unsigned int)strlen(payload);

    if (RC_RouterIsEnglish(router))
        RC_LogInfo("MQTT message topic='%s' payload='%s' (len=%u)", topic, preview, payloadLen);
    else
        RC_LogInfo("收到 MQTT 消息 topic='%s' payload='%s' (len=%u)", topic, preview, payloadLen);
}

/*
 * 将 MQTT payload（字节串）复制为 C 字符串，并做简单的首尾空白裁剪。
 *
 * 为什么需要：
 * - MQTT payload 在协议层是“字节数组 + 长度”，不保证以 '\0' 结尾。
 * - 上层路由/动作通常按字符串处理，因此这里统一做一次安全复制。
 *
 * 注意：
 * - 仅裁剪常见空白（space/\r/\n/\t），不做编码转换。
 * - 返回值需由调用方 free()。
 */
static char *utf8_dup_and_trim(const unsigned char *buf, int len)
{
    if (!buf || len <= 0)
        return _strdup("");

    if (len > RC_MQTT_MAX_PAYLOAD_BYTES)
        len = RC_MQTT_MAX_PAYLOAD_BYTES;

    int start = 0;
    int end = len;
    while (start < end && (buf[start] == ' ' || buf[start] == '\r' || buf[start] == '\n' || buf[start] == '\t'))
        start++;
    while (end > start && (buf[end - 1] == ' ' || buf[end - 1] == '\r' || buf[end - 1] == '\n' || buf[end - 1] == '\t'))
        end--;

    int outLen = end - start;
    char *s = (char *)malloc((size_t)outLen + 1);
    if (!s)
        return NULL;
    memcpy(s, buf + start, (size_t)outLen);
    s[outLen] = 0;
    return s;
}

/*
 * 自发布消息回环抑制（self-echo suppression）
 *
 * 背景：订阅 topic 后会立即发布默认状态（on/off）以同步服务器端主题状态。
 * 由于客户端本身也订阅了同一 topic，broker 会把这条消息回投给自己，
 * 导致程序把"自己发出的默认状态"当作外部指令执行（例如误杀应用）。
 *
 * 方案：发布默认状态时记录 (topic, payload, tick)；接收时若在时间窗口内
 * 匹配到完全相同的 (topic, payload)，则判定为自回环并跳过 RC_RouterHandle。
 * 匹配后立即消费该条目，避免误抑制后续合法的同 payload 指令。
 */
#define RC_MQTT_SELF_ECHO_MAX_ENTRIES 32
#define RC_MQTT_SELF_ECHO_TOPIC_LEN  127
#define RC_MQTT_SELF_ECHO_PAYLOAD_LEN 63
#define RC_MQTT_SELF_ECHO_WINDOW_MS  5000

typedef struct
{
    bool used;
    DWORD tick;
    char topic[RC_MQTT_SELF_ECHO_TOPIC_LEN + 1];
    char payload[RC_MQTT_SELF_ECHO_PAYLOAD_LEN + 1];
} SelfPublishEntry;

static SelfPublishEntry g_selfPublishEntries[RC_MQTT_SELF_ECHO_MAX_ENTRIES];

static void self_publish_record(const char *topic, const char *payload)
{
    if (!topic || !*topic || !payload || !*payload)
        return;

    DWORD now = GetTickCount();
    // 找一个空闲或已过期的槽位
    SelfPublishEntry *slot = NULL;
    for (int i = 0; i < RC_MQTT_SELF_ECHO_MAX_ENTRIES; i++)
    {
        if (!g_selfPublishEntries[i].used ||
            (now - g_selfPublishEntries[i].tick) > RC_MQTT_SELF_ECHO_WINDOW_MS)
        {
            slot = &g_selfPublishEntries[i];
            break;
        }
    }
    if (!slot)
        return; // 表满则放弃记录（极少发生）

    slot->used = true;
    slot->tick = now;
    strncpy(slot->topic, topic, RC_MQTT_SELF_ECHO_TOPIC_LEN);
    slot->topic[RC_MQTT_SELF_ECHO_TOPIC_LEN] = 0;
    strncpy(slot->payload, payload, RC_MQTT_SELF_ECHO_PAYLOAD_LEN);
    slot->payload[RC_MQTT_SELF_ECHO_PAYLOAD_LEN] = 0;
}

static bool self_publish_is_echo(const char *topic, const char *payload)
{
    if (!topic || !*topic || !payload || !*payload)
        return false;

    DWORD now = GetTickCount();
    for (int i = 0; i < RC_MQTT_SELF_ECHO_MAX_ENTRIES; i++)
    {
        if (!g_selfPublishEntries[i].used)
            continue;
        if ((now - g_selfPublishEntries[i].tick) > RC_MQTT_SELF_ECHO_WINDOW_MS)
        {
            g_selfPublishEntries[i].used = false; // 过期清理
            continue;
        }
        if (strcmp(g_selfPublishEntries[i].topic, topic) == 0 &&
            strcmp(g_selfPublishEntries[i].payload, payload) == 0)
        {
            g_selfPublishEntries[i].used = false; // 消费，避免误抑制后续合法指令
            return true;
        }
    }
    return false;
}

/*
 * 判断 Paho 返回码是否属于“鉴权类不可恢复错误”。
 *
 * 设计意图：
 * - 网络波动/临时不可达：应该重试。
 * - 用户名/密码错误、未授权：重试通常无意义，应直接退出循环，
 *   让上层引导用户修复配置（避免无休止刷日志/占用资源）。
 *
 * 兼容性：
 * - 不同 Paho 版本的宏名可能不同，因此使用 #ifdef 防护。
 */
static bool is_fatal_auth_failure(int rc)
{
    // 根据 Paho 返回码判断“鉴权类不可恢复错误”。
    // 注意：不同版本的 Paho 可能宏名不同，因此使用 #ifdef 保护。
#ifdef MQTTCLIENT_BAD_USERNAME_OR_PASSWORD
    if (rc == MQTTCLIENT_BAD_USERNAME_OR_PASSWORD)
        return true;
#endif
#ifdef MQTTCLIENT_NOT_AUTHORIZED
    if (rc == MQTTCLIENT_NOT_AUTHORIZED)
        return true;
#endif
    return false;
}

void RC_MqttRunLoop(const RC_MqttConfig *cfg, RC_Router *router, volatile bool *shouldStop)
{
    if (!cfg || !router)
        return;

    DWORD lastConnNotifyTick = 0;
    DWORD lastDiscNotifyTick = 0;
    DWORD lastFailNotifyTick = 0;

    const char *host = cfg->brokerHost ? cfg->brokerHost : "";
    int port = cfg->port;

    bool useTls = cfg->useTls;
#ifndef MQTTClient_SSLOptions_initializer
    if (useTls)
    {
        if (RC_RouterIsEnglish(router))
            RC_LogWarn("MQTT(Paho) TLS/SSL requested but this build/header has no SSL support. Falling back to tcp://");
        else
            RC_LogWarn("MQTT(Paho) 已请求 TLS/SSL，但当前构建/头文件不支持 SSL。将回退到 tcp://");
    }
    useTls = false;
#endif

    char address[512];
    const char *scheme = (useTls ? "ssl" : "tcp");
    _snprintf(address, sizeof(address), "%s://%s:%d", scheme, host, port);
    address[sizeof(address) - 1] = 0;

    const char *clientId = (cfg->clientId && *cfg->clientId) ? cfg->clientId : "RC-main";

    MQTTClient client;
    int rc = MQTTClient_create(&client, address, clientId, MQTTCLIENT_PERSISTENCE_NONE, NULL);
    if (rc != MQTTCLIENT_SUCCESS)
    {
        RC_LogError("Paho MQTTClient_create 失败 rc=%d", rc);
        return;
    }

    MQTTClient_connectOptions conn_opts = MQTTClient_connectOptions_initializer;
    conn_opts.cleansession = 1;
    conn_opts.keepAliveInterval = (cfg->keepAliveSeconds > 0 ? cfg->keepAliveSeconds : 60);
#ifdef MQTTVERSION_3_1_1
    conn_opts.MQTTVersion = MQTTVERSION_3_1_1;
#endif
    if (cfg->username && *cfg->username)
        conn_opts.username = cfg->username;
    if (cfg->password && *cfg->password)
        conn_opts.password = cfg->password;

    // TLS/SSL：只在 cfg->useTls 时启用。
    // 用户可通过 cfg->tlsVerifyServerCert 控制是否校验证书；
    // 如需校验，通常还应提供 cfg->tlsCaFile（CA 文件路径）。
#ifdef MQTTClient_SSLOptions_initializer
    MQTTClient_SSLOptions ssl_opts = MQTTClient_SSLOptions_initializer;
    if (useTls)
    {
        ssl_opts.enableServerCertAuth = (cfg->tlsVerifyServerCert ? 1 : 0);
        if (cfg->tlsCaFile && *cfg->tlsCaFile)
        {
            // Paho/OpenSSL: trustStore is a file containing trusted CA certificates.
            ssl_opts.trustStore = cfg->tlsCaFile;
        }
        else if (cfg->tlsVerifyServerCert)
        {
            if (RC_RouterIsEnglish(router))
                RC_LogWarn("MQTT(Paho) TLS verify is enabled but mqtt_tls_ca_file is empty; connection may fail if no default trust store is available.");
            else
                RC_LogWarn("MQTT(Paho) 已启用证书校验，但未配置 mqtt_tls_ca_file；若环境无默认信任库，连接可能失败。");
        }
#ifdef MQTT_SSL_VERSION_TLS_1_2
        ssl_opts.sslVersion = MQTT_SSL_VERSION_TLS_1_2;
#endif
        conn_opts.ssl = &ssl_opts;
    }
#else
    if (cfg->useTls)
    {
        if (RC_RouterIsEnglish(router))
            RC_LogWarn("MQTT(Paho) TLS/SSL requested but SSL options are not available in this build/header.");
        else
            RC_LogWarn("MQTT(Paho) 已请求 TLS/SSL，但当前构建/头文件不支持 SSL 选项。将按非 TLS 方式尝试连接。");
    }
#endif

    int backoff = (cfg->reconnectMinSeconds > 0 ? cfg->reconnectMinSeconds : 2);
    int backoffMax = (cfg->reconnectMaxSeconds > 0 ? cfg->reconnectMaxSeconds : 30);

    /*
     * 主循环（阻塞式）：
     * - connect 失败：按 backoff 退避重试；鉴权失败则直接退出。
     * - connect 成功：订阅路由提供的 topics，然后进入 receive 循环。
     * - receive 循环：每次最多阻塞 1s（MQTTClient_receive timeout=1000），
     *   期间会周期性检查 shouldStop。
     */
    while (!shouldStop || !*shouldStop)
    {
        if (RC_RouterIsEnglish(router))
            RC_LogInfo("MQTT(Paho) connecting %s", address);
        else
            RC_LogInfo("MQTT(Paho) 正在连接 %s", address);
        {
            char msg[256];
            if (RC_RouterIsEnglish(router))
                _snprintf(msg, sizeof(msg), "Connecting to server: %s", address);
            else
                _snprintf(msg, sizeof(msg), "正在连接服务器：%s", address);
            msg[sizeof(msg) - 1] = 0;
            notify_status_throttled(router, &lastConnNotifyTick, 30000, msg);
        }
        rc = MQTTClient_connect(client, &conn_opts);
        if (rc != MQTTCLIENT_SUCCESS)
        {
            if (RC_RouterIsEnglish(router))
                RC_LogWarn("MQTT(Paho) connect failed rc=%d, retry in %d s", rc, backoff);
            else
                RC_LogWarn("MQTT(Paho) 连接失败 rc=%d，%d 秒后重试", rc, backoff);
            {
                char msg[256];
                if (RC_RouterIsEnglish(router))
                    _snprintf(msg, sizeof(msg), "Failed to connect (rc=%d). Retrying in %d seconds.", rc, backoff);
                else
                    _snprintf(msg, sizeof(msg), "连接服务器失败(rc=%d)，%d 秒后重试", rc, backoff);
                msg[sizeof(msg) - 1] = 0;
                notify_status_throttled(router, &lastFailNotifyTick, 30000, msg);
            }
            if (is_fatal_auth_failure(rc))
            {
                if (RC_RouterIsEnglish(router))
                    RC_LogError("MQTT(Paho) auth failed rc=%d", rc);
                else
                    RC_LogError("MQTT(Paho) 鉴权失败 rc=%d", rc);
                {
                    char msg[256];
                    if (RC_RouterIsEnglish(router))
                        _snprintf(msg, sizeof(msg), "Authentication failed (rc=%d). Please check username/password or permissions.", rc);
                    else
                        _snprintf(msg, sizeof(msg), "服务器鉴权失败(rc=%d)，请检查账号/密码或权限", rc);
                    msg[sizeof(msg) - 1] = 0;
                    RC_RouterNotifyUtf8(router, rc_title_for_notify(router), msg);
                }
                break;
            }
            // 退避策略：指数增长并封顶（避免快速重连导致刷屏/资源浪费）。
            Sleep((DWORD)backoff * 1000);
            if (backoff < backoffMax)
                backoff = (backoff < backoffMax / 2) ? backoff * 2 : backoffMax;
            continue;
        }

        {
            char msg[256];
            if (RC_RouterIsEnglish(router))
                _snprintf(msg, sizeof(msg), "Connected: %s", address);
            else
                _snprintf(msg, sizeof(msg), "已连接服务器：%s", address);
            msg[sizeof(msg) - 1] = 0;
            RC_RouterNotifyUtf8(router, rc_title_for_notify(router), msg);
        }

        // 连接成功：重置 backoff，避免下一次断线重连延迟过大。
        backoff = (cfg->reconnectMinSeconds > 0 ? cfg->reconnectMinSeconds : 2);

        // 订阅列表由 Router 统一提供，MQTT 层不维护 topic 配置的来源。
        int topicCount = 0;
        const char *const *topics = RC_RouterGetTopics(router, &topicCount);
        for (int i = 0; i < topicCount; i++)
        {
            if (!topics[i] || !*topics[i])
                continue;
            int subrc = MQTTClient_subscribe(client, topics[i], 0);
            if (subrc == MQTTCLIENT_SUCCESS)
            {
                RC_LogInfo("MQTT(Paho) 订阅：%s", topics[i]);

                // 订阅成功后，发布默认状态以同步服务器端主题状态。
                const char *defaultState = RC_RouterGetDefaultState(router, topics[i]);
                if (defaultState && *defaultState)
                {
                    MQTTClient_message pubmsg = MQTTClient_message_initializer;
                    pubmsg.payload = (void *)defaultState;
                    pubmsg.payloadlen = (int)strlen(defaultState);
                    pubmsg.qos = 0;
                    pubmsg.retained = 0;
                    MQTTClient_deliveryToken dt = 0;
                    int pubrc = MQTTClient_publishMessage(client, topics[i], &pubmsg, &dt);
                    if (pubrc == MQTTCLIENT_SUCCESS)
                    {
                        RC_LogInfo("MQTT(Paho) 发布默认状态：topic=%s state=%s", topics[i], defaultState);
                        // 记录自发布，以便接收循环跳过 broker 回投的同一消息（防自回环）
                        self_publish_record(topics[i], defaultState);
                    }
                    else
                        RC_LogWarn("MQTT(Paho) 发布默认状态失败 rc=%d topic=%s", pubrc, topics[i]);
                }
            }
            else
                RC_LogWarn("MQTT(Paho) 订阅失败 rc=%d topic=%s", subrc, topics[i]);
        }

        /*
         * 接收循环：
         * - message==NULL：表示超时（无消息），继续循环。
         * - message!=NULL：提取 topic/payload，裁剪 payload，交给 Router 分发。
         * - 任意错误：break 触发 disconnect + 退避重连。
         *
         * 资源释放：
         * - MQTTClient_receive 返回的 topicName/message 必须用 MQTTClient_free / MQTTClient_freeMessage 释放。
         */
        while (!shouldStop || !*shouldStop)
        {
#ifdef MQTTClient_isConnected
            if (!MQTTClient_isConnected(client))
            {
                if (RC_RouterIsEnglish(router))
                {
                    RC_LogWarn("MQTT(Paho) disconnected");
                    notify_status_throttled(router, &lastDiscNotifyTick, 30000, "Disconnected. Reconnecting...");
                }
                else
                {
                    RC_LogWarn("MQTT(Paho) 已断开连接");
                    notify_status_throttled(router, &lastDiscNotifyTick, 30000, "连接已断开，正在重连...");
                }
                break;
            }
#endif

            char *topicName = NULL;
            int topicLen = 0;
            MQTTClient_message *message = NULL;

            int rcvrc = MQTTClient_receive(client, &topicName, &topicLen, &message, 1000);
            if (rcvrc != MQTTCLIENT_SUCCESS)
            {
                if (RC_RouterIsEnglish(router))
                    RC_LogWarn("MQTT(Paho) receive failed rc=%d", rcvrc);
                else
                    RC_LogWarn("MQTT(Paho) 接收失败 rc=%d", rcvrc);
                break;
            }

            if (!message)
                continue; // timeout

            const unsigned char *pl = (const unsigned char *)message->payload;
            int plLen = (int)message->payloadlen;

            char *payload = utf8_dup_and_trim(pl, plLen);
            if (!payload)
            {
                MQTTClient_freeMessage(&message);
                MQTTClient_free(topicName);
                break;
            }

            const char *msgTopic = topicName ? topicName : "";

            if (RC_RouterIsEnglish(router))
                log_mqtt_message(router, msgTopic, payload);
            else
                log_mqtt_message(router, msgTopic, payload);

            // 跳过自发布回环：broker 把刚发出的默认状态回投给本客户端，不应作为指令执行
            if (self_publish_is_echo(msgTopic, payload))
            {
                if (RC_RouterIsEnglish(router))
                    RC_LogInfo("MQTT(Paho) skip self-echo: topic=%s payload=%s", msgTopic, payload);
                else
                    RC_LogInfo("MQTT(Paho) 跳过自回环消息：topic=%s payload=%s", msgTopic, payload);
            }
            else
            {
                RC_RouterHandle(router, msgTopic, payload);
            }

            free(payload);
            MQTTClient_freeMessage(&message);
            MQTTClient_free(topicName);
        }

        // 主动断开：给 broker 一个有限的处理时间（timeout=1000ms）。
        MQTTClient_disconnect(client, 1000);
        // 断线后退避一段时间再重连（避免 tight-loop）。
        if (RC_RouterIsEnglish(router))
            notify_status_throttled(router, &lastDiscNotifyTick, 30000, "Disconnected. Reconnecting...");
        else
            notify_status_throttled(router, &lastDiscNotifyTick, 30000, "连接已断开，正在重连...");
        Sleep((DWORD)backoff * 1000);
        if (backoff < backoffMax)
            backoff = (backoff < backoffMax / 2) ? backoff * 2 : backoffMax;
    }

    MQTTClient_destroy(&client);
}
