/*
 * rc_mqtt.c
 *
 * MQTT 主循环实现。
 *
 * 目前构建默认使用 Paho MQTT C（RC_USE_PAHO_MQTT）：
 * - 使用同步客户端 MQTTClient（阻塞式 connect/subscribe/receive）。
 * - 收到 publish 后把 topic/payload 交给 RC_RouterHandle。
 * - 对“不可恢复”的鉴权失败（BAD_USERNAME_OR_PASSWORD/NOT_AUTHORIZED）直接返回，
 *   让上层引导用户修复配置。
 */

#include "rc_mqtt.h"

#ifdef RC_USE_PAHO_MQTT

#include "rc_log.h"

#include <windows.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Paho MQTT C (synchronous client)
// Build notes:
// - Provide MQTTClient.h in include path
// - Link with paho-mqtt3c (non-SSL) or paho-mqtt3cs (SSL) as needed
#include "MQTTClient.h"

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

    const char *host = cfg->brokerHost ? cfg->brokerHost : "";
    int port = cfg->port;

    char address[512];
    _snprintf(address, sizeof(address), "tcp://%s:%d", host, port);
    address[sizeof(address) - 1] = 0;

    const char *clientId = (cfg->clientId && *cfg->clientId) ? cfg->clientId : "RC-main";

    MQTTClient client;
    int rc = MQTTClient_create(&client, address, clientId, MQTTCLIENT_PERSISTENCE_NONE, NULL);
    if (rc != MQTTCLIENT_SUCCESS)
    {
        RC_LogError("Paho MQTTClient_create failed rc=%d", rc);
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
        RC_LogInfo("MQTT(Paho) connecting to %s", address);
        rc = MQTTClient_connect(client, &conn_opts);
        if (rc != MQTTCLIENT_SUCCESS)
        {
            RC_LogWarn("MQTT(Paho) connect failed rc=%d. retry in %ds", rc, backoff);
            if (is_fatal_auth_failure(rc))
            {
                RC_LogError("MQTT(Paho) auth failure rc=%d", rc);
                break;
            }
            // 退避策略：指数增长并封顶（避免快速重连导致刷屏/资源浪费）。
            Sleep((DWORD)backoff * 1000);
            if (backoff < backoffMax)
                backoff = (backoff < backoffMax / 2) ? backoff * 2 : backoffMax;
            continue;
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
                RC_LogInfo("MQTT(Paho) subscribe: %s", topics[i]);
            else
                RC_LogWarn("MQTT(Paho) subscribe failed rc=%d topic=%s", subrc, topics[i]);
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
                RC_LogWarn("MQTT(Paho) disconnected");
                break;
            }
#endif

            char *topicName = NULL;
            int topicLen = 0;
            MQTTClient_message *message = NULL;

            int rcvrc = MQTTClient_receive(client, &topicName, &topicLen, &message, 1000);
            if (rcvrc != MQTTCLIENT_SUCCESS)
            {
                RC_LogWarn("MQTT(Paho) receive failed rc=%d", rcvrc);
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

            RC_LogInfo("MQTT recv topic='%s' payload='%s'", topicName ? topicName : "", payload);
            RC_RouterHandle(router, topicName ? topicName : "", payload);

            free(payload);
            MQTTClient_freeMessage(&message);
            MQTTClient_free(topicName);
        }

        // 主动断开：给 broker 一个有限的处理时间（timeout=1000ms）。
        MQTTClient_disconnect(client, 1000);
        // 断线后退避一段时间再重连（避免 tight-loop）。
        Sleep((DWORD)backoff * 1000);
        if (backoff < backoffMax)
            backoff = (backoff < backoffMax / 2) ? backoff * 2 : backoffMax;
    }

    MQTTClient_destroy(&client);
}

#else

#include "rc_log.h"

#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct
{
    SOCKET sock;
    uint16_t nextPacketId;
    DWORD lastTxTick;
    DWORD lastRxTick;
} MqttConn;

/*
 * 生成 MQTT Packet Identifier（用于 SUBSCRIBE 等需要 Packet Id 的报文）。
 *
 * 约束：
 * - MQTT 报文的 Packet Id 取值范围为 1..65535（0 为非法）。
 */
static uint16_t next_packet_id(MqttConn *c)
{
    c->nextPacketId++;
    if (c->nextPacketId == 0)
        c->nextPacketId = 1;
    return c->nextPacketId;
}

/*
 * 发送指定长度的数据，直到全部写出或发生错误。
 *
 * 说明：send() 可能只发送部分字节，因此这里做循环补齐。
 */
static bool send_all(SOCKET s, const void *buf, int len)
{
    const char *p = (const char *)buf;
    int left = len;
    while (left > 0)
    {
        int n = send(s, p, left, 0);
        if (n <= 0)
            return false;
        p += n;
        left -= n;
    }
    return true;
}

/*
 * 接收指定长度的数据，直到全部收到或发生错误/断开。
 *
 * 说明：recv() 可能只收到部分字节，因此这里做循环补齐。
 */
static bool recv_all(SOCKET s, void *buf, int len)
{
    char *p = (char *)buf;
    int left = len;
    while (left > 0)
    {
        int n = recv(s, p, left, 0);
        if (n <= 0)
            return false;
        p += n;
        left -= n;
    }
    return true;
}

// MQTT 使用 network byte order（大端）编码 16-bit 长度/标识。
static void write_u16(uint8_t *dst, uint16_t v)
{
    dst[0] = (uint8_t)((v >> 8) & 0xFF);
    dst[1] = (uint8_t)(v & 0xFF);
}

/*
 * 写入 MQTT UTF-8 String（两字节长度 + 字节串）。
 * - 这是 MQTT 协议规定的数据格式（并不是 C 的 '\0' 结尾字符串）。
 * - 返回写入字节数，失败返回 -1。
 */
static int mqtt_write_utf8_str(uint8_t *dst, int cap, const char *s)
{
    if (!s)
        s = "";
    size_t n = strlen(s);
    if (n > 0xFFFF)
        n = 0xFFFF;
    if (cap < (int)(2 + n))
        return -1;
    write_u16(dst, (uint16_t)n);
    memcpy(dst + 2, s, n);
    return (int)(2 + n);
}

/*
 * 编码 Remaining Length（MQTT 的可变长度整数），最多 4 字节。
 * - 返回写入字节数，失败返回 -1。
 */
static int mqtt_encode_remaining_length(uint8_t *dst, int cap, int len)
{
    // MQTT variable length encoding, max 4 bytes.
    int i = 0;
    do
    {
        if (i >= cap)
            return -1;
        int digit = len % 128;
        len /= 128;
        if (len > 0)
            digit |= 0x80;
        dst[i++] = (uint8_t)digit;
    } while (len > 0);
    return i;
}

/*
 * 从 socket 读取 Remaining Length。
 * - 按 MQTT 规范：最多读取 4 个字节。
 * - 读取失败或格式错误返回 false。
 */
static bool mqtt_read_remaining_length(SOCKET s, int *outLen)
{
    int multiplier = 1;
    int value = 0;
    for (int i = 0; i < 4; i++)
    {
        uint8_t digit = 0;
        if (!recv_all(s, &digit, 1))
            return false;
        value += (digit & 127) * multiplier;
        if ((digit & 128) == 0)
        {
            *outLen = value;
            return true;
        }
        multiplier *= 128;
    }
    return false;
}

/*
 * 使用 getaddrinfo + connect 建立 TCP 连接。
 * - host/port 使用 UTF-8 字符串；端口会被格式化为十进制字符串交给 getaddrinfo。
 * - 会尝试所有解析结果，直到 connect 成功。
 */
static SOCKET tcp_connect_utf8(const char *host, int port)
{
    if (!host || !*host)
        return INVALID_SOCKET;

    char portStr[16];
    _snprintf(portStr, sizeof(portStr), "%d", port);
    portStr[sizeof(portStr) - 1] = 0;

    struct addrinfo hints;
    ZeroMemory(&hints, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;

    struct addrinfo *res = NULL;
    if (getaddrinfo(host, portStr, &hints, &res) != 0 || !res)
        return INVALID_SOCKET;

    SOCKET s = INVALID_SOCKET;
    for (struct addrinfo *p = res; p; p = p->ai_next)
    {
        SOCKET t = socket(p->ai_family, p->ai_socktype, p->ai_protocol);
        if (t == INVALID_SOCKET)
            continue;
        if (connect(t, p->ai_addr, (int)p->ai_addrlen) == 0)
        {
            s = t;
            break;
        }
        closesocket(t);
    }
    freeaddrinfo(res);
    return s;
}

/*
 * 发送 MQTT CONNECT 报文（MQTT 3.1.1, protocol level=4）。
 *
 * 当前实现特性：
 * - Clean Session=1
 * - 可选 username/password（仅当 authMode=="username_password" 且两者都非空）
 * - 不支持 TLS/SSL、不支持 Will、不支持自定义 Connect Flags。
 */
static bool mqtt_send_connect(MqttConn *c, const RC_MqttConfig *cfg)
{
    const char *clientId = cfg->clientId ? cfg->clientId : "";

    bool useUserPass = false;
    if (cfg->authMode && _stricmp(cfg->authMode, "username_password") == 0)
    {
        if (cfg->username && *cfg->username && cfg->password && *cfg->password)
            useUserPass = true;
    }

    // Variable header
    uint8_t vh[16];
    int vhPos = 0;
    vhPos += mqtt_write_utf8_str(vh + vhPos, (int)sizeof(vh) - vhPos, "MQTT");
    vh[vhPos++] = 4; // protocol level

    uint8_t flags = 0;
    flags |= 0x02; // clean session
    if (useUserPass)
        flags |= 0x80; // username
    if (useUserPass)
        flags |= 0x40; // password
    vh[vhPos++] = flags;

    uint16_t ka = (uint16_t)(cfg->keepAliveSeconds > 0 ? cfg->keepAliveSeconds : 60);
    write_u16(vh + vhPos, ka);
    vhPos += 2;

    // Payload
    uint8_t payload[4096];
    int pPos = 0;
    int n = mqtt_write_utf8_str(payload + pPos, (int)sizeof(payload) - pPos, clientId);
    if (n < 0)
        return false;
    pPos += n;
    if (useUserPass)
    {
        n = mqtt_write_utf8_str(payload + pPos, (int)sizeof(payload) - pPos, cfg->username);
        if (n < 0)
            return false;
        pPos += n;
        n = mqtt_write_utf8_str(payload + pPos, (int)sizeof(payload) - pPos, cfg->password);
        if (n < 0)
            return false;
        pPos += n;
    }

    int remLen = vhPos + pPos;

    uint8_t header[8];
    header[0] = 0x10; // CONNECT
    int hl = mqtt_encode_remaining_length(header + 1, (int)sizeof(header) - 1, remLen);
    if (hl < 0)
        return false;

    if (!send_all(c->sock, header, 1 + hl))
        return false;
    if (!send_all(c->sock, vh, vhPos))
        return false;
    if (!send_all(c->sock, payload, pPos))
        return false;

    c->lastTxTick = GetTickCount();
    return true;
}

/*
 * 等待并解析 CONNACK。
 * - 返回码 outReturnCode：0=accepted；非 0 表示 broker 拒绝连接。
 * - 本项目用 rc==5（Not authorized）作为“鉴权不可恢复”的停止条件（对齐 python 行为）。
 */
static bool mqtt_wait_connack(MqttConn *c, int *outReturnCode)
{
    *outReturnCode = -1;

    uint8_t type = 0;
    if (!recv_all(c->sock, &type, 1))
        return false;
    if ((type & 0xF0) != 0x20)
        return false;

    int remLen = 0;
    if (!mqtt_read_remaining_length(c->sock, &remLen))
        return false;
    if (remLen != 2)
        return false;

    uint8_t data[2];
    if (!recv_all(c->sock, data, 2))
        return false;

    *outReturnCode = (int)data[1];
    c->lastRxTick = GetTickCount();
    return true;
}

/*
 * 发送单个 topic 的 SUBSCRIBE（QoS0）。
 *
 * 说明：
 * - 此处不等待 SUBACK；实现上接受“尽力而为”。
 * - topic 为空时直接当作成功（便于上层跳过空配置）。
 */
static bool mqtt_send_subscribe_one(MqttConn *c, const char *topic)
{
    if (!topic || !*topic)
        return true;

    uint8_t payload[1024];
    int pPos = 0;

    // Packet id
    uint16_t pid = next_packet_id(c);
    payload[pPos++] = (uint8_t)((pid >> 8) & 0xFF);
    payload[pPos++] = (uint8_t)(pid & 0xFF);

    // Topic filter + QoS0
    int n = mqtt_write_utf8_str(payload + pPos, (int)sizeof(payload) - pPos, topic);
    if (n < 0)
        return false;
    pPos += n;
    if (pPos >= (int)sizeof(payload))
        return false;
    payload[pPos++] = 0x00;

    uint8_t header[8];
    header[0] = 0x82; // SUBSCRIBE
    int hl = mqtt_encode_remaining_length(header + 1, (int)sizeof(header) - 1, pPos);
    if (hl < 0)
        return false;

    if (!send_all(c->sock, header, 1 + hl))
        return false;
    if (!send_all(c->sock, payload, pPos))
        return false;

    c->lastTxTick = GetTickCount();
    return true;
}

// 发送 PINGREQ，用于 keep-alive（维持连接存活）。
static bool mqtt_send_pingreq(MqttConn *c)
{
    uint8_t pkt[2] = {0xC0, 0x00};
    if (!send_all(c->sock, pkt, 2))
        return false;
    c->lastTxTick = GetTickCount();
    return true;
}

/*
 * 等待 socket 可读（select）。
 * - 返回值：>0 可读；0 超时；<0 出错。
 * - timeoutMs 用于在阻塞等待期间也能周期性检查 shouldStop。
 */
static int wait_socket_readable(SOCKET s, int timeoutMs)
{
    fd_set rfds;
    FD_ZERO(&rfds);
    FD_SET(s, &rfds);

    TIMEVAL tv;
    tv.tv_sec = timeoutMs / 1000;
    tv.tv_usec = (timeoutMs % 1000) * 1000;

    return select(0, &rfds, NULL, NULL, &tv);
}

/*
 * 与 Paho 分支同名工具：复制 + trim payload。
 * - 这里的输入是接收缓冲区中的 payload 段。
 */
static char *utf8_dup_and_trim(const uint8_t *buf, int len)
{
    if (!buf || len <= 0)
        return _strdup("");

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
 * 读取并处理一个 MQTT 数据包。
 *
 * 当前仅关心：
 * - PUBLISH：提取 topic 与 payload（容忍 QoS>0 的 Packet Id 字段），交给 Router。
 * - PINGRESP / SUBACK：忽略（仅用于维持连接/订阅确认）。
 * - 其他包：忽略。
 *
 * 安全限制：
 * - remLen 做上限保护（256KB），避免异常报文导致过度分配。
 */
static bool mqtt_process_one_packet(MqttConn *c, RC_Router *router)
{
    uint8_t type = 0;
    if (!recv_all(c->sock, &type, 1))
        return false;

    int remLen = 0;
    if (!mqtt_read_remaining_length(c->sock, &remLen))
        return false;
    if (remLen < 0 || remLen > (256 * 1024))
        return false;

    uint8_t *data = NULL;
    if (remLen > 0)
    {
        data = (uint8_t *)malloc((size_t)remLen);
        if (!data)
            return false;
        if (!recv_all(c->sock, data, remLen))
        {
            free(data);
            return false;
        }
    }

    c->lastRxTick = GetTickCount();

    uint8_t packetType = (type & 0xF0);
    if (packetType == 0x30)
    {
        // PUBLISH
        if (remLen < 2)
        {
            free(data);
            return true;
        }
        int pos = 0;
        uint16_t topicLen = (uint16_t)((data[pos] << 8) | data[pos + 1]);
        pos += 2;
        if (pos + topicLen > remLen)
        {
            free(data);
            return true;
        }
        char *topic = (char *)malloc((size_t)topicLen + 1);
        if (!topic)
        {
            free(data);
            return false;
        }
        memcpy(topic, data + pos, topicLen);
        topic[topicLen] = 0;
        pos += topicLen;

        // QoS>0 includes packet id; we only subscribe QoS0 but tolerate.
        int qos = (type & 0x06) >> 1;
        if (qos > 0)
        {
            if (pos + 2 <= remLen)
                pos += 2;
        }

        int payloadLen = remLen - pos;
        char *payload = utf8_dup_and_trim(data + pos, payloadLen);
        if (!payload)
        {
            free(topic);
            free(data);
            return false;
        }

        RC_LogInfo("MQTT recv topic='%s' payload='%s'", topic, payload);
        RC_RouterHandle(router, topic, payload);

        free(payload);
        free(topic);
    }
    else if (packetType == 0xD0)
    {
        // PINGRESP
    }
    else if (packetType == 0x90)
    {
        // SUBACK
    }
    else
    {
        // Ignore
    }

    free(data);
    return true;
}

// 关闭 socket 的小工具：确保 INVALID_SOCKET 语义一致，避免 double-close。
static void closesocket_safe(SOCKET *ps)
{
    if (!ps)
        return;
    if (*ps != INVALID_SOCKET)
    {
        closesocket(*ps);
        *ps = INVALID_SOCKET;
    }
}

void RC_MqttRunLoop(const RC_MqttConfig *cfg, RC_Router *router, volatile bool *shouldStop)
{
    if (!cfg || !router)
        return;

    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0)
    {
        RC_LogError("WSAStartup failed");
        return;
    }

    int backoff = (cfg->reconnectMinSeconds > 0 ? cfg->reconnectMinSeconds : 2);
    int backoffMax = (cfg->reconnectMaxSeconds > 0 ? cfg->reconnectMaxSeconds : 30);

    /*
     * 自实现 MQTT 连接循环（Winsock）：
     * - 先建 TCP，再发 CONNECT，等待 CONNACK。
     * - 成功后订阅所有 topics，进入接收循环。
     * - 断线/错误后按 backoff 退避重连；若 CONNACK return code==5（Not authorized）则停止重试。
     */
    while (!shouldStop || !*shouldStop)
    {
        RC_LogInfo("MQTT connecting to %s:%d...", cfg->brokerHost ? cfg->brokerHost : "", cfg->port);

        SOCKET s = tcp_connect_utf8(cfg->brokerHost, cfg->port);
        if (s == INVALID_SOCKET)
        {
            RC_LogWarn("MQTT connect failed. retry in %ds", backoff);
            Sleep((DWORD)backoff * 1000);
            if (backoff < backoffMax)
                backoff = (backoff < backoffMax / 2) ? backoff * 2 : backoffMax;
            continue;
        }

        // Reset backoff on TCP success.
        backoff = (cfg->reconnectMinSeconds > 0 ? cfg->reconnectMinSeconds : 2);

        MqttConn c;
        ZeroMemory(&c, sizeof(c));
        c.sock = s;
        c.nextPacketId = 1;
        c.lastTxTick = GetTickCount();
        c.lastRxTick = GetTickCount();

        if (!mqtt_send_connect(&c, cfg))
        {
            RC_LogWarn("MQTT CONNECT send failed");
            closesocket_safe(&s);
            continue;
        }

        int rc = -1;
        if (!mqtt_wait_connack(&c, &rc))
        {
            RC_LogWarn("MQTT CONNACK failed");
            closesocket_safe(&s);
            continue;
        }

        if (rc != 0)
        {
            RC_LogError("MQTT connect refused (code=%d)", rc);
            // Match python behavior: auth failure => stop retrying.
            if (rc == 5)
            {
                closesocket_safe(&s);
                break;
            }
            closesocket_safe(&s);
            continue;
        }

        // Subscribe topics from router
        int topicCount = 0;
        const char *const *topics = RC_RouterGetTopics(router, &topicCount);
        for (int i = 0; i < topicCount; i++)
        {
            if (!topics[i] || !*topics[i])
                continue;
            mqtt_send_subscribe_one(&c, topics[i]);
            RC_LogInfo("MQTT subscribe: %s", topics[i]);
        }

        // Main receive loop
        int keepAlive = (cfg->keepAliveSeconds > 0 ? cfg->keepAliveSeconds : 60);
        int pingIntervalMs = (keepAlive > 1 ? (keepAlive * 1000) / 2 : 1000);

        /*
         * 接收循环：
         * - 通过 select(500ms) 等待可读，保持对 shouldStop 的响应。
         * - 当长时间既未收包也未发包时，发送 PINGREQ 维持 keep-alive。
         */
        while (!shouldStop || !*shouldStop)
        {
            DWORD now = GetTickCount();
            DWORD sinceTx = now - c.lastTxTick;
            DWORD sinceRx = now - c.lastRxTick;

            if ((int)sinceTx >= pingIntervalMs && (int)sinceRx >= pingIntervalMs)
            {
                if (!mqtt_send_pingreq(&c))
                {
                    RC_LogWarn("MQTT ping failed");
                    break;
                }
            }

            int rdy = wait_socket_readable(s, 500);
            if (rdy < 0)
                break;
            if (rdy == 0)
                continue;

            if (!mqtt_process_one_packet(&c, router))
            {
                RC_LogWarn("MQTT recv failed");
                break;
            }
        }

        closesocket_safe(&s);
        RC_LogWarn("MQTT disconnected. reconnecting...");
    }

    WSACleanup();
}

#endif
