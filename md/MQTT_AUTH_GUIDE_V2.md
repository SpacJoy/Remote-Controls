<!-- @format -->

# MQTT 认证配置指南

## 概述

本程序支持两种 MQTT 认证方式，可以兼容大多数 IoT 平台的 MQTT 服务器。

配置入口：推荐使用 `RC-GUI.exe` 配置并保存，程序会生成/更新同目录的 `config.json`。

重要说明：主程序默认使用 **TCP** 连接（`tcp://broker:port`），TLS（SSL）默认关闭。

如需连接 `8883/TLS` 端口：

- `mqtt_tls`: 1（启用 `ssl://`）
- `mqtt_tls_verify`: 0/1（是否校验证书）
- `mqtt_tls_ca_file`: CA 证书文件路径（用于证书校验）

注意：启用 TLS 需要构建时链接 Paho SSL 库（如 `paho-mqtt3cs`）。

## 方式一：私钥模式

这种方式主要兼容巴法云等使用私钥作为客户端 ID 的平台。

-   **适用平台**：巴法云、部分自定义 MQTT 服务器
-   **配置方式**：
    -   认证模式：选择"私钥模式"
    -   网站：填写 MQTT 服务器地址（如：bemfa.com）
    -   客户端 ID：填写私钥（会写入 `config.json` 的 `client_id`）
    -   端口：通常为 9501（巴法云）
-   **连接原理**：使用客户端 ID（私钥）进行连接，不设置用户名和密码

对应配置字段：

- `auth_mode`: `private_key`
- `client_id`: 你的私钥
- `mqtt_username` / `mqtt_password`: 留空

## 方式二：账号密码模式

这是标准的 MQTT 认证方式，适用于大多数 IoT 平台。

-   **适用平台**：阿里云 IoT、腾讯云 IoT、AWS IoT、华为云 IoT、小米 IoT、涂鸦智能等、部分自定义 MQTT 服务器
-   **配置方式**：
    -   认证模式：选择"账号密码模式"
    -   网站：填写 MQTT 服务器地址
    -   用户名：填写平台提供的用户名/设备 ID/AppID
    -   密码：填写平台提供的密码/密钥/SecretKey
    -   客户端 ID：填写设备 ID（建议按平台要求填写）
    -   端口：通常为 1883（非 TLS）

对应配置字段：

- `auth_mode`: `username_password`
- `mqtt_username`: 平台提供的用户名
- `mqtt_password`: 平台提供的密码
- `client_id`: 设备 ID（若平台允许，也可留空/自定义）

## 配置文件示例

### 巴法云配置（私钥模式）

```json
{
	"broker": "bemfa.com",
	"client_id": "your_private_key_here",
	"port": 9501,
	"auth_mode": "private_key"
}
```

### 其他平台配置（账号密码模式）

```json
{
	"broker": "your_iot_platform.com",
	"client_id": "your_device_id",
	"port": 1883,
	"auth_mode": "username_password",
	"mqtt_username": "your_username_or_device_id",
	"mqtt_password": "your_password_or_secret_key"
}
```

## 常见 IoT 平台配置参考

### 阿里云 IoT 平台

```json
{
	"broker": "your_product_key.iot-as-mqtt.cn-shanghai.aliyuncs.com",
	"port": 1883,
	"auth_mode": "username_password",
	"mqtt_username": "your_device_name&your_product_key",
	"mqtt_password": "your_device_secret",
	"client_id": "your_product_key.your_device_name"
}
```

### 腾讯云 IoT Hub

```json
{
	"broker": "your_product_id.iotcloud.tencentdevices.com",
	"port": 1883,
	"auth_mode": "username_password",
	"mqtt_username": "your_product_id;your_device_name",
	"mqtt_password": "your_device_secret",
	"client_id": "your_product_id;your_device_name"
}
```

### 华为云 IoT 平台

```json
{
	"broker": "your_platform_address",
	"port": 1883,
	"auth_mode": "username_password",
	"mqtt_username": "your_device_id",
	"mqtt_password": "your_device_secret",
	"client_id": "your_device_id"
}
```

## 使用说明

1. **GUI 配置**：

    - 打开 RC-GUI 配置程序
    - 在"系统配置"区域选择合适的认证模式
    - 在"MQTT 认证配置"区域填写相应的认证信息
    - 点击保存配置

2. **自动切换**：

    - 选择"私钥模式"时，账号密码配置会自动禁用
    - 选择"账号密码模式"时，账号密码配置会自动启用

3. **兼容性**：
    - 私钥模式兼容巴法云等特殊平台
    - 账号密码模式支持标准 MQTT 协议的各种 IoT 平台

## 故障排除

1. **连接失败**：

    - 检查网络连接是否正常
    - 确认服务器地址和端口正确（注意：默认版本不支持 TLS/8883）
    - 验证认证信息是否正确

2. **认证失败**：

    - 私钥模式：确认客户端 ID（私钥）格式和内容正确
    - 账号密码模式：确认用户名密码正确

3. **主题订阅失败**：
    - 检查主题名称是否正确
    - 确认平台控制台中已创建对应主题
    - 注意不同平台的主题命名规范

## 注意事项

1. **安全性**：

    - 密码在配置文件中以明文存储，请妥善保管配置文件
    - 建议设置适当的文件权限

2. **端口选择**：

    - 巴法云通常使用 9501 端口
    - 其他平台通常使用 1883 端口（未加密）

3. **客户端 ID**：

    - 私钥模式：客户端 ID 就是私钥值
    - 账号密码模式：客户端 ID 可以自定义，留空则使用用户名
    - 某些平台要求特定的客户端 ID 格式

4. **配置修改**：

    - 修改认证配置后需要重启程序才能生效
    - 建议先在对应平台的控制台测试连接

5. **兼容性说明**：
    - 新配置统一使用`client_id`字段
    - 旧版本升级需要重新配置客户端ID（私钥）
