/*
 * RC-main（主程序）入口
 *
 * 主要职责：
 * 1) 定位程序目录并切换工作目录（SetCurrentDirectoryW），保证相对路径稳定。
 * 2) 初始化日志（logs\main.log）与管理员状态输出（logs\admin_status.txt）。
 * 3) 读取并解析配置文件 config.json（UTF-8），构建路由（RC_RouterCreate）。
 * 4) 连接 MQTT 并进入主循环（RC_MqttRunLoop）。
 * 5) 若外部托盘 RC-tray.exe 未运行，则启用主程序内置最小托盘（RC_MainTrayStartDelayed）。
 *
 * 配置错误/缺失时的回退策略：
 * - 优先启动 RC-GUI.exe 让用户修复；
 * - 若 GUI 存在但启动失败（ShellExecuteW 返回值 <= 32）或 GUI 不存在，则回退用记事本打开 config.json；
 *   若 config.json 不存在则先创建（OPEN_ALWAYS）并写入最小 JSON "{}"。
 */

#include <windows.h>
#include <shlwapi.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>

#include "../rc_json.h"

#include "rc_log.h"
#include "rc_router.h"
#include "rc_mqtt.h"
#include "rc_main_tray.h"

#define RC_STR2(x) #x
#define RC_STR(x) RC_STR2(x)

#ifndef RC_MAIN_VERSION
#define RC_MAIN_VERSION V0.0.0
#endif

#define MUTEX_NAME L"RC-main"

static bool StrIsEnglishLang(const char *s)
{
    if (!s || !*s)
        return false;
    if (_strnicmp(s, "en", 2) != 0)
        return false;
    return (s[2] == '\0' || s[2] == '-' || s[2] == '_');
}

static bool IsSystemEnglishUI(void)
{
    // 按托盘侧策略：中文 => 中文，其它语言 => 英文。
    LANGID langID = GetUserDefaultUILanguage();
    WORD primary = PRIMARYLANGID(langID);
    if (primary == LANG_CHINESE)
        return false;
    return true;
}

/*
 * 获取当前可执行文件所在目录。
 * - 使用 GetModuleFileNameW 获取完整路径（失败返回 0）。
 * - 使用 PathRemoveFileSpecW 去掉文件名，仅保留目录。
 */
static bool GetModuleDirW(wchar_t *outDir, size_t outCount)
{
    if (!outDir || outCount == 0)
        return false;

    wchar_t path[MAX_PATH] = {0};
    DWORD n = GetModuleFileNameW(NULL, path, MAX_PATH);
    if (n == 0 || n >= MAX_PATH)
        return false;

    if (!PathRemoveFileSpecW(path))
        return false;

    wcsncpy_s(outDir, outCount, path, _TRUNCATE);
    return true;
}

/*
 * 拼接路径 dir\name（简单拼接，不做规范化；dir/name 为空时按空字符串处理）。
 */
static void BuildPathW(wchar_t *out, size_t outCount, const wchar_t *dir, const wchar_t *name)
{
    if (!out || outCount == 0)
        return;
    out[0] = L'\0';
    if (!dir)
        dir = L"";
    if (!name)
        name = L"";
    _snwprintf(out, outCount, L"%s\\%s", dir, name);
}

/*
 * 以二进制方式读取文件到内存，并以 UTF-8 字符串返回（末尾强制补 '\0'）。
 * - 返回值由调用方 free。
 * - 读取失败返回 NULL。
 */
static char *ReadFileUtf8Alloc(const wchar_t *path)
{
    FILE *f = NULL;
    _wfopen_s(&f, path, L"rb");
    if (!f)
        return NULL;

    if (fseek(f, 0, SEEK_END) != 0)
    {
        fclose(f);
        return NULL;
    }
    long sz = ftell(f);
    if (sz < 0)
    {
        fclose(f);
        return NULL;
    }
    rewind(f);

    char *buf = (char *)malloc((size_t)sz + 1);
    if (!buf)
    {
        fclose(f);
        return NULL;
    }

    size_t rd = fread(buf, 1, (size_t)sz, f);
    buf[rd] = '\0';
    fclose(f);
    return buf;
}

/*
 * 确保目录存在：CreateDirectoryW 在目录已存在时会失败并返回 FALSE，
 * 这里按 best-effort 处理，不把 "already exists" 当成致命错误。
 */
static void EnsureDirW(const wchar_t *path)
{
    if (!path || !*path)
        return;
    CreateDirectoryW(path, NULL);
}

/*
 * 输出当前管理员状态到 logs\admin_status.txt。
 * - 通过 shell32!IsUserAnAdmin 获取（老 API，但足够满足托盘侧读取/提示）。
 * - 写入内容为 "admin=1" 或 "admin=0"。
 */
static void WriteAdminStatusFile(const wchar_t *logsDir)
{
    wchar_t statusPath[MAX_PATH] = {0};
    BuildPathW(statusPath, MAX_PATH, logsDir, L"admin_status.txt");

    BOOL isAdmin = FALSE;
    HMODULE shell32 = GetModuleHandleW(L"shell32.dll");
    if (shell32)
    {
        typedef BOOL(WINAPI * IsUserAnAdminFn)(void);
        IsUserAnAdminFn fn = (IsUserAnAdminFn)GetProcAddress(shell32, "IsUserAnAdmin");
        if (fn)
            isAdmin = fn();
    }

    FILE *f = NULL;
    _wfopen_s(&f, statusPath, L"wb");
    if (!f)
        return;
    const char *txt = isAdmin ? "admin=1" : "admin=0";
    fwrite(txt, 1, strlen(txt), f);
    fclose(f);
}

/*
 * 确保 config.json 存在；如果文件不存在则创建；如果文件为空则写入最小 JSON："{}"。
 *
 * - CreateFileW 使用 OPEN_ALWAYS：
 *   - 文件存在：打开。
 *   - 文件不存在：创建。
 * - 共享模式：FILE_SHARE_READ|WRITE|DELETE，方便 GUI/用户/编辑器同时访问。
 */
static bool EnsureConfigFileExists(const wchar_t *configPath)
{
    if (!configPath || !*configPath)
        return false;

    // OPEN_ALWAYS: create if missing.
    HANDLE h = CreateFileW(configPath,
                           GENERIC_READ | GENERIC_WRITE,
                           FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                           NULL,
                           OPEN_ALWAYS,
                           FILE_ATTRIBUTE_NORMAL,
                           NULL);
    if (h == INVALID_HANDLE_VALUE)
        return false;

    LARGE_INTEGER sz;
    sz.QuadPart = 0;
    if (GetFileSizeEx(h, &sz) && sz.QuadPart == 0)
    {
        const char *defaultJson = "{}\r\n";
        DWORD wr = 0;
        WriteFile(h, defaultJson, (DWORD)strlen(defaultJson), &wr, NULL);
    }

    CloseHandle(h);
    return true;
}

/*
 * 若 RC-GUI.exe 存在则尝试启动。
 *
 * - PathFileExistsW：快速判断文件是否存在。
 * - ShellExecuteW：返回值 (HINSTANCE) <= 32 表示失败（如 ERROR_FILE_NOT_FOUND、SE_ERR_ACCESSDENIED 等）。
 *   这里将失败情况记录到主日志，便于排查“被杀软拦截/损坏/无权限”等问题。
 */
static bool OpenGuiIfExists(const wchar_t *appDir)
{
    wchar_t guiPath[MAX_PATH] = {0};
    BuildPathW(guiPath, MAX_PATH, appDir, L"RC-GUI.exe");
    if (PathFileExistsW(guiPath))
    {
        HINSTANCE h = ShellExecuteW(NULL, L"open", guiPath, NULL, appDir, SW_SHOWNORMAL);
        if ((INT_PTR)h <= 32)
        {
            RC_LogError("启动 RC-GUI.exe 失败 (ShellExecuteW rc=%ld)", (long)(INT_PTR)h);
            return false;
        }
        return true;
    }
    return false;
}

/*
 * 配置异常时的统一回退策略：
 * 1) 优先启动 GUI（成功即返回）。
 * 2) GUI 不存在或启动失败 -> （可选）创建 config.json -> 使用 notepad.exe 打开。
 */
static void OpenGuiOrNotepadConfig(const wchar_t *appDir, const wchar_t *configPath, bool createIfMissing)
{
    if (OpenGuiIfExists(appDir))
        return;

    if (createIfMissing)
        EnsureConfigFileExists(configPath);

    if (configPath && *configPath)
        ShellExecuteW(NULL, L"open", L"notepad.exe", configPath, appDir, SW_SHOWNORMAL);
}

/*
 * 主程序入口（GUI-less Win32 应用）：
 *
 * 执行顺序（高层）：
 * 1) 单实例互斥（CreateMutexW + ERROR_ALREADY_EXISTS）。
 * 2) 获取 exe 目录并 SetCurrentDirectoryW（保证相对路径读写稳定）。
 * 3) 初始化日志与 admin 状态文件（供托盘读取/提示）。
 * 4) 读取 config.json（UTF-8）并解析为 RC_Json。
 * 5) 基于 JSON 创建 Router（RC_RouterCreate）：Router 接管 configRoot 所有权。
 * 6) 启动内置最小托盘（若外部 RC-tray.exe 未运行）。
 * 7) 进入 MQTT 阻塞式主循环（RC_MqttRunLoop）：负责 connect/subscribe/receive/dispatch。
 * 8) MQTT 循环返回：若不是用户主动退出，则引导用户打开 GUI/记事本修复配置。
 *
 * 重要约定：
 * - RC_RouterCreate 成功后，root 的释放由 RC_RouterDestroy 负责（Destroy 时会 RC_JsonFree）。
 * - jsonText 仅用于 RC_JsonParse 输入，解析后即可释放；但这里为了便于排查/保持一致，
 *   选择在 Router 生命周期结束后再 free(jsonText)。
 */

int WINAPI wWinMain(HINSTANCE hInstance, HINSTANCE hPrev, LPWSTR lpCmdLine, int nShowCmd)
{
    (void)hInstance;
    (void)hPrev;
    (void)lpCmdLine;
    (void)nShowCmd;

    // 互斥体：防止重复启动多个 RC-main 实例。
    // - CreateMutexW 成功后，GetLastError()==ERROR_ALREADY_EXISTS 表示已有实例在运行。
    HANDLE hMutex = CreateMutexW(NULL, FALSE, MUTEX_NAME);
    if (!hMutex)
        return 1;
    if (GetLastError() == ERROR_ALREADY_EXISTS)
    {
        CloseHandle(hMutex);
        return 0;
    }

    wchar_t appDir[MAX_PATH] = {0};
    if (!GetModuleDirW(appDir, MAX_PATH))
    {
        CloseHandle(hMutex);
        return 1;
    }
    // 固定工作目录：后续读写 logs\、config.json 等使用相对路径时更可靠。
    SetCurrentDirectoryW(appDir);

    RC_LogInit(appDir);
    RC_LogInfo("RC-main 启动 (%s)", RC_STR(RC_MAIN_VERSION));

    wchar_t logsDir[MAX_PATH] = {0};
    BuildPathW(logsDir, MAX_PATH, appDir, L"logs");
    EnsureDirW(logsDir);
    WriteAdminStatusFile(logsDir);

    wchar_t configPath[MAX_PATH] = {0};
    BuildPathW(configPath, MAX_PATH, appDir, L"config.json");

    const bool sysEnglish = IsSystemEnglishUI();

    if (!PathFileExistsW(configPath))
    {
        // 配置缺失：提示 + 打开 GUI；若 GUI 不可用则记事本打开（并创建空配置）。
        if (sysEnglish)
            MessageBoxW(NULL, L"config.json not found. Please open RC-GUI to configure.", L"RC-main", MB_ICONERROR);
        else
            MessageBoxW(NULL, L"配置文件不存在，请先打开 RC-GUI 进行配置。", L"RC-main", MB_ICONERROR);
        OpenGuiOrNotepadConfig(appDir, configPath, true);
        CloseHandle(hMutex);
        return 1;
    }

    char *jsonText = ReadFileUtf8Alloc(configPath);
    if (!jsonText)
    {
        // 读取失败：可能是权限/占用/损坏。回退到 GUI/记事本让用户修复。
        if (sysEnglish)
            MessageBoxW(NULL, L"Failed to read config.json.", L"RC-main", MB_ICONERROR);
        else
            MessageBoxW(NULL, L"读取配置文件失败。", L"RC-main", MB_ICONERROR);
        OpenGuiOrNotepadConfig(appDir, configPath, true);
        CloseHandle(hMutex);
        return 1;
    }

    RC_JsonError jerr = {0};
    RC_Json *root = RC_JsonParse(jsonText, &jerr);
    if (!root || !RC_JsonIsObject(root))
    {
        // JSON 解析失败或根不是对象：提示并让用户修复。
        free(jsonText);
        if (root)
            RC_JsonFree(root);
        if (sysEnglish)
            MessageBoxW(NULL, L"Invalid config.json format. Please fix it in RC-GUI.", L"RC-main", MB_ICONERROR);
        else
            MessageBoxW(NULL, L"配置文件格式错误，请使用 RC-GUI 修复。", L"RC-main", MB_ICONERROR);
        OpenGuiOrNotepadConfig(appDir, configPath, true);
        CloseHandle(hMutex);
        return 1;
    }

    // language: "zh"/"en"（由 RC-GUI 写入；缺省则中文）
    const char *lang = RC_JsonGetString(RC_JsonObjectGet(root, "language"));
    const bool langEnglish = StrIsEnglishLang(lang);

    // 基础字段读取（后续 MQTT/动作处理会用到）。
    // 注意：RC_JsonGetString 可能返回 NULL；后续会做必要的空值/合法性检查。
    const char *broker = RC_JsonGetString(RC_JsonObjectGet(root, "broker"));
    int port = RC_JsonGetInt(RC_JsonObjectGet(root, "port"), 0);
    const char *clientId = RC_JsonGetString(RC_JsonObjectGet(root, "client_id"));
    const char *authMode = RC_JsonGetString(RC_JsonObjectGet(root, "auth_mode"));
    const char *mqttUser = RC_JsonGetString(RC_JsonObjectGet(root, "mqtt_username"));
    const char *mqttPass = RC_JsonGetString(RC_JsonObjectGet(root, "mqtt_password"));
    int mqttTls = RC_JsonGetInt(RC_JsonObjectGet(root, "mqtt_tls"), 0);
    int testMode = RC_JsonGetInt(RC_JsonObjectGet(root, "test"), 0);

    if (!authMode || !*authMode)
        authMode = "private_key";

    if ((!broker || !*broker) || port <= 0)
    {
        // broker/port 是 MQTT 连接最低要求。
        if (langEnglish)
            MessageBoxW(NULL, L"Invalid MQTT config: broker/port.", L"RC-main", MB_ICONERROR);
        else
            MessageBoxW(NULL, L"MQTT 配置不完整：broker/port 无效。", L"RC-main", MB_ICONERROR);
        OpenGuiOrNotepadConfig(appDir, configPath, true);
        RC_JsonFree(root);
        free(jsonText);
        CloseHandle(hMutex);
        return 1;
    }

    if (_stricmp(authMode, "private_key") == 0)
    {
        if (!clientId || !*clientId)
        {
            // 私钥模式依赖 client_id。缺失时直接提示并回退到 GUI/记事本。
            if (langEnglish)
                MessageBoxW(NULL, L"In private_key mode, client_id is required. Please set it in RC-GUI.", L"RC-main", MB_ICONERROR);
            else
                MessageBoxW(NULL, L"私钥模式下 client_id 不能为空（请在 RC-GUI 中配置客户端ID/私钥）。", L"RC-main", MB_ICONERROR);
            OpenGuiOrNotepadConfig(appDir, configPath, true);
            RC_JsonFree(root);
            free(jsonText);
            CloseHandle(hMutex);
            return 1;
        }
    }

    RC_Router *router = RC_RouterCreate(root);
    if (!router)
    {
        // 路由初始化失败：通常是配置缺字段/结构异常导致。
        RC_JsonFree(root);
        free(jsonText);
        if (langEnglish)
            MessageBoxW(NULL, L"Failed to load configuration (router init failed).", L"RC-main", MB_ICONERROR);
        else
            MessageBoxW(NULL, L"配置加载失败（路由初始化失败）。", L"RC-main", MB_ICONERROR);
        OpenGuiOrNotepadConfig(appDir, configPath, true);
        CloseHandle(hMutex);
        return 1;
    }

    // 重要：Router 创建成功后，会接管 root 的所有权（Destroy 时负责 RC_JsonFree）。
    // 因此此处不再直接 RC_JsonFree(root)。

    int subCount = 0;
    const char *const *subs = RC_RouterGetTopics(router, &subCount);
    (void)subs;
    if (langEnglish)
        RC_LogInfo("Router ready. Topics=%d", subCount);
    else
        RC_LogInfo("路由已就绪。主题数=%d", subCount);

    if (subCount <= 0 && testMode != 1)
    {
        // 正常模式下必须至少订阅一个主题，否则主程序无事可做。
        if (langEnglish)
            MessageBoxW(NULL, L"No topics enabled. Please open RC-GUI and enable at least one theme (unless test mode is on).", L"RC-main", MB_ICONERROR);
        else
            MessageBoxW(NULL, L"主题不能一个都没有吧！（除非开启测试模式）\n请先打开 RC-GUI 勾选至少一个主题。", L"RC-main", MB_ICONERROR);
        OpenGuiOrNotepadConfig(appDir, configPath, true);
        RC_RouterDestroy(router);
        free(jsonText);
        CloseHandle(hMutex);
        return 1;
    }

    RC_MqttConfig mc;
    ZeroMemory(&mc, sizeof(mc));
    mc.brokerHost = broker;
    mc.port = port;
    mc.useTls = (mqttTls != 0);
    mc.authMode = authMode;
    mc.clientId = clientId;
    mc.username = mqttUser;
    mc.password = mqttPass;
    mc.keepAliveSeconds = 60;
    mc.reconnectMinSeconds = 2;
    mc.reconnectMaxSeconds = 30;

    if (langEnglish)
        RC_LogInfo("MQTT starting: broker=%s port=%d auth_mode=%s", broker, port, authMode);
    else
        RC_LogInfo("MQTT 启动：broker=%s port=%d auth_mode=%s", broker, port, authMode);

    volatile bool stopFlag = false;

    // 与 Python 版本行为保持一致：
    // - 若 RC-tray.exe 已运行：主程序不再创建自己的托盘 UI（避免重复）。
    // - 若未运行：主程序启动一个最小托盘（可用于退出等基础操作）。
    RC_MainTrayStartDelayed(appDir, RC_STR(RC_MAIN_VERSION), &stopFlag, langEnglish);

    // MQTT 主循环：内部负责连接/订阅/消息分发；stopFlag 被置为 true 时退出。
    RC_MqttRunLoop(&mc, router, &stopFlag);

    // If user requested exit (from built-in tray), do not pop GUI.
    if (!stopFlag)
    {
        // 鉴权失败或致命错误：引导用户修复配置。
        OpenGuiOrNotepadConfig(appDir, configPath, true);
    }
    RC_RouterDestroy(router);

    free(jsonText);

    CloseHandle(hMutex);
    return 0;
}
