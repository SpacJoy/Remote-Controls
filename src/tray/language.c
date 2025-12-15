/**
 * 远程控制托盘程序 - 语言支持实现
 * Remote Control Tray - Language Support Implementation
 *
 * 设计目标（方案B）：
 * - 将“UI显示文案”（菜单文本、提示语、通知文本等）从业务逻辑中分离出来，
 *   统一通过 `LanguageStrings` 结构体按语言取值，避免散落的硬编码字符串。
 * - 语言选择策略尽量简单：默认跟随系统 UI 语言（GetUserDefaultUILanguage）。
 * - 该模块只负责：语言枚举、字符串表、语言检测与当前语言切换；
 *   不负责 UI 刷新与重绘（由 tray.c 在合适时机重新构建菜单/刷新提示）。
 *
 * 线程与初始化说明：
 * - 当前实现使用一个全局变量 `g_currentLanguage`，并未做并发保护。
 *   托盘程序主流程通常单线程（消息循环线程）调用，因此足够。
 * - `InitializeLanguage()` 会在日志系统初始化之前被调用，因此这里只做检测，
 *   不直接写日志（避免初始化顺序耦合）。
 */

#include "language.h"
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <shlwapi.h> // 用于PathRemoveFileSpecA函数

// 全局变量 / Global variables
// 当前语言（默认中文）。程序启动时会在 InitializeLanguage() 中覆盖为“系统检测结果”。
static Language g_currentLanguage = TRAY_LANG_CHINESE;

// 中文字符串 / Chinese strings
static const LanguageStrings g_chineseStrings = {
    // 应用程序信息 / Application info
    .appTitle = "远程控制托盘",
    .trayTip = "远程控制托盘-%s",

    // 消息框文本 / MessageBox text
    .errorTitle = "错误",
    .logCreateError = "无法创建日志文件",

    // 托盘通知文本 / Tray notification text
    .notifyAppStarted = "远程控制托盘程序已启动",
    .notifyMainRunning = "主程序已在运行",
    .notifyMainNotRunning = "主程序未在运行",
    .notifyTrayStatus = "托盘状态: %s",
    .notifyAdminYes = "以管理员权限运行",
    .notifyAdminNo = "以普通权限运行",

    // 主程序状态文本 / Main program status text
    .mainStatusRunning = "主程序状态: 正在运行",
    .mainStatusNotRunning = "主程序状态: 未运行",

    // 主程序管理操作文本 / Main program management text    .startingMain = "正在启动主程序...",
    .closingMain = "正在关闭主程序...",
    .restartingMain = "正在重启主程序...",
    .exitingTray = "正在退出托盘程序，主程序将继续运行...",
    .mainNotExists = "主程序不存在",
    .userCancelledUAC = "用户取消了权限请求",
    .startFailed = "无法启动程序，请检查路径",
    .closeFailed = "无法关闭主程序",

    // GUI相关文本 / GUI related text
    .openingConfig = "正在打开配置界面",
    .configNotExists = "配置界面不存在",
    .openConfigFailed = "无法打开配置界面",

    // 管理员权限检查文本 / Admin rights check text
    .adminCheckYes = "主程序已获得管理员权限",
    .adminCheckNo = "主程序未获得管理员权限",
    .adminCheckUnknown = "无法确定主程序权限状态",
    .adminCheckReadError = "无法读取主程序权限状态",
    .adminCheckFileNotExists = "主程序权限状态文件不存在", // 托盘菜单项文本 / Tray menu item text
    .menuOpenConfig = "打开配置界面",
    .menuCheckAdmin = "检查主程序管理员权限",
    .menuStartMain = "启动主程序",
    .menuRestartMain = "重启主程序",
    .menuCloseMain = "关闭主程序",
    .menuExit = "退出托盘（使用主程序自带托盘）",
    .menuExitStandalone = "退出托盘",
    .menuTrayStatus = "托盘状态: 【%s】",
    .menuVersionInfo = "版本-%s",
    .menuSwitchLanguage = "切换语言 (当前: 中文)",
    .menuVersionFallback = "版本信息",

    // 提示和标题 / Prompts and titles
    .promptTitle = "提示",
    .errorPromptTitle = "错误",

    // 版本检查提示 / Version check text
    .versionCheckingSuffix = "（检查中...）",
    .versionSuffixNew = "（发现新版本 %s）",
    .versionSuffixLatest = "（已是最新）",
    .versionSuffixAhead = "（当前版本较新）",
    .versionSuffixError = "（检查失败）",
    .versionNotifyNew = "发现新版本 %s，当前 %s",
    .versionNotifyLatest = "已是最新版本 %s",
    .versionNotifyAhead = "当前版本新于远端 %s",
    .versionCheckFailed = "检查更新失败",

    // 彩蛋链接提示 / Easter egg text
    .randomImageOpened = "已打开随机彩蛋",
    .randomImageFailed = "无法打开随机彩蛋",

    // 提权提示 / Elevation prompt
    .requestAdminPrompt = "托盘未获得管理员权限，是否立即申请并重启托盘？",
    .requestAdminFailed = "申请管理员权限失败"};

// 英文字符串 / English strings
static const LanguageStrings g_englishStrings = {
    // 应用程序信息 / Application info
    .appTitle = "Remote Control Tray",
    .trayTip = "Remote Control Tray-%s",

    // 消息框文本 / MessageBox text
    .errorTitle = "Error",
    .logCreateError = "Cannot create log file",

    // 托盘通知文本 / Tray notification text
    .notifyAppStarted = "Remote Control Tray has started",
    .notifyMainRunning = "Main program is already running",
    .notifyMainNotRunning = "Main program is not running",
    .notifyTrayStatus = "Tray status: %s",
    .notifyAdminYes = "Running with admin rights",
    .notifyAdminNo = "Running without admin rights",

    // 主程序状态文本 / Main program status text
    .mainStatusRunning = "Main program: Running",
    .mainStatusNotRunning = "Main program: Not running",

    // 主程序管理操作文本 / Main program management text    .startingMain = "Starting main program...",
    .closingMain = "Closing main program...",
    .restartingMain = "Restarting main program...",
    .exitingTray = "Exiting tray program, main program will continue running...",
    .mainNotExists = "Main program does not exist",
    .userCancelledUAC = "User cancelled permission request",
    .startFailed = "Cannot start program, please check path",
    .closeFailed = "Cannot close main program",

    // GUI相关文本 / GUI related text
    .openingConfig = "Opening configuration interface",
    .configNotExists = "Configuration interface does not exist",
    .openConfigFailed = "Cannot open configuration interface",

    // 管理员权限检查文本 / Admin rights check text
    .adminCheckYes = "Main program has admin rights",
    .adminCheckNo = "Main program does not have admin rights",
    .adminCheckUnknown = "Cannot determine main program admin status",
    .adminCheckReadError = "Cannot read main program admin status",
    .adminCheckFileNotExists = "Main program admin status file does not exist", // 托盘菜单项文本 / Tray menu item text
    .menuOpenConfig = "Open Configuration",
    .menuCheckAdmin = "Check Main Program Admin Rights",
    .menuStartMain = "Start Main Program",
    .menuRestartMain = "Restart Main Program",
    .menuCloseMain = "Close Main Program",
    .menuExit = "Exit Tray (Use Main Program's Tray)",
    .menuExitStandalone = "Exit Tray",
    .menuTrayStatus = "Tray Status: [%s]",
    .menuVersionInfo = "Version-%s",
    .menuSwitchLanguage = "Switch Language (Current: English)",
    .menuVersionFallback = "Version Info",

    // 提示和标题 / Prompts and titles
    .promptTitle = "Info",
    .errorPromptTitle = "Error",

    // 版本检查提示 / Version check text
    .versionCheckingSuffix = " (checking...)",
    .versionSuffixNew = " (new version %s)",
    .versionSuffixLatest = " (up to date)",
    .versionSuffixAhead = " (ahead of remote)",
    .versionSuffixError = " (check failed)",
    .versionNotifyNew = "New version %s found, current %s",
    .versionNotifyLatest = "Already up to date %s",
    .versionNotifyAhead = "Current version is newer than %s",
    .versionCheckFailed = "Failed to check updates",

    // 彩蛋链接提示 / Easter egg text
    .randomImageOpened = "Random image opened",
    .randomImageFailed = "Failed to open random image",

    // 提权提示 / Elevation prompt
    .requestAdminPrompt = "Tray is not elevated. Request admin rights and restart now?",
    .requestAdminFailed = "Failed to obtain admin rights"};

/**
 * 检测系统语言
 * Detect system language
 *
 * 返回值：
 * - TRAY_LANG_CHINESE：系统 UI 主语言为中文（任何中文变体：简体/繁体/港澳台等）
 * - TRAY_LANG_ENGLISH：系统 UI 主语言为英文，或无法识别/不支持的其它语言（默认英文）
 *
 * 备注：
 * - 这里使用 GetUserDefaultUILanguage() 获取“用户界面语言”，它更贴近实际 UI 显示语言。
 * - PRIMARYLANGID()/SUBLANGID() 用于从 LANGID 提取主语言/子语言。
 */
Language DetectSystemLanguage(void)
{
    // 获取用户界面语言ID
    // Get user interface language ID
    LANGID langID = GetUserDefaultUILanguage();

    // 获取主语言ID
    // Get primary language ID
    WORD primaryLangID = PRIMARYLANGID(langID);

    // 获取子语言ID（用于区分不同的中文变体）
    // Get sublanguage ID (used to distinguish different Chinese variants)
    WORD subLangID = SUBLANGID(langID);

    // 生成调试信息（目前仅用于开发排查；未输出到日志/调试器，避免引入初始化依赖）
    char debugInfo[100];
    snprintf(debugInfo, sizeof(debugInfo), "系统语言ID: 0x%04X, 主语言ID: 0x%04X, 子语言ID: 0x%04X",
             langID, primaryLangID, subLangID);

    // 根据主语言ID确定使用哪种语言
    // Determine which language to use based on primary language ID
    if (primaryLangID == LANG_CHINESE)
    {
        // 任何中文变体都使用中文
        // Any Chinese variant uses Chinese
        return TRAY_LANG_CHINESE;
    }
    else if (primaryLangID == LANG_ENGLISH)
    {
        // 任何英文变体都使用英文
        // Any English variant uses English
        return TRAY_LANG_ENGLISH;
    }
    else
    {
        // 其他语言默认使用英文
        // Other languages default to English
        return TRAY_LANG_ENGLISH;
    }
}

/**
 * 获取当前语言的字符串表
 * Get strings for current language
 *
 * 返回：
 * - 指向静态只读的 `LanguageStrings` 表（无需释放；整个进程生命周期内有效）。
 */
const LanguageStrings *GetLanguageStrings(void)
{
    if (g_currentLanguage == TRAY_LANG_CHINESE)
    {
        return &g_chineseStrings;
    }
    else
    {
        return &g_englishStrings;
    }
}

/**
 * 初始化语言支持
 * Initialize language support
 *
 * 作用：
 * - 将 `g_currentLanguage` 设置为系统检测结果。
 *
 * 注意：
 * - 这里不直接调用 LogMessage/写文件日志，因为托盘的日志系统可能尚未初始化。
 */
void InitializeLanguage(void)
{
    // 直接使用系统语言
    // Directly use system language
    g_currentLanguage = DetectSystemLanguage();

    // 记录检测到的语言（仅生成字符串，避免初始化顺序耦合）
    char *langName = (g_currentLanguage == TRAY_LANG_CHINESE) ? "中文" : "English";
    char logMsg[100];
    snprintf(logMsg, sizeof(logMsg), "系统语言检测结果: %s", langName);
    // 这里无法直接调用LogMessage，因为日志系统可能还未初始化
}

/**
 * 获取当前语言
 * Get current language
 */
Language GetCurrentLanguage(void)
{
    return g_currentLanguage;
}

/**
 * 设置当前语言
 *
 * 说明：
 * - 这是一个“纯状态更新”函数，不会主动触发 UI 刷新。
 * - 调用方（tray.c）在切换后通常需要重新构建菜单/刷新托盘提示文本。
 */
void SetLanguage(Language lang)
{
    g_currentLanguage = lang;
}

/**
 * 中英文切换
 *
 * 说明：
 * - 仅在 TRAY_LANG_CHINESE 与 TRAY_LANG_ENGLISH 之间切换。
 * - 同样不做 UI 刷新；由调用方决定何时重绘。
 */
void ToggleLanguage(void)
{
    if (g_currentLanguage == TRAY_LANG_CHINESE)
    {
        g_currentLanguage = TRAY_LANG_ENGLISH;
    }
    else
    {
        g_currentLanguage = TRAY_LANG_CHINESE;
    }
}
