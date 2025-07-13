<!-- @format -->

# MQTT 认证配置指南

## 概述

本程序支持两种 MQTT 认证方式，可以兼容大多数 IoT 平台的 MQTT 服务器。

## 方式一：私钥模式

这种方式主要兼容巴法云等使用私钥作为客户端 ID 的平台。

-   **适用平台**：巴法云、部分自定义 MQTT 服务器
-   **配置方式**：
    -   认证模式：选择"私钥模式"
    -   网站：填写 MQTT 服务器地址（如：bemfa.com）
    -   客户端 ID：填写私钥
    -   端口：通常为 9501（巴法云）
-   **连接原理**：使用客户端 ID（私钥）进行连接，不设置用户名和密码

## 方式二：账号密码模式

这是标准的 MQTT 认证方式，适用于大多数 IoT 平台。

-   **适用平台**：阿里云 IoT、腾讯云 IoT、AWS IoT、华为云 IoT、小米 IoT、涂鸦智能等
-   **配置方式**：
    -   认证模式：选择"账号密码模式"
    -   网站：填写 MQTT 服务器地址
    -   用户名：填写平台提供的用户名/设备 ID/AppID
    -   密码：填写平台提供的密码/密钥/SecretKey
    -   客户端 ID：填写设备 ID 或留空使用用户名
    -   端口：根据平台要求（通常为 1883 或 8883）

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
    - 确认服务器地址和端口正确
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
    - 其他平台通常使用 1883 端口（未加密）或 8883 端口（SSL 加密）

3. **客户端 ID**：

    - 私钥模式：客户端 ID 就是私钥值
    - 账号密码模式：客户端 ID 可以自定义，留空则使用用户名
    - 某些平台要求特定的客户端 ID 格式

4. **配置修改**：

    - 修改认证配置后需要重启程序才能生效
    - 建议先在对应平台的控制台测试连接

5. **兼容性说明**：
    - 程序会自动兼容旧配置文件中的`secret_id`字段
    - 新配置统一使用`client_id`字段
