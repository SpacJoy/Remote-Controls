/**
 * 远程控制托盘程序 - 语言支持头文件
 * Remote Control Tray - Language Support Header
 *
 * 说明：
 * - 托盘 UI（菜单、提示、通知、MessageBox）所有文案集中在 LanguageStrings。
 * - 运行时可切换语言；切换后需调用托盘侧 RefreshTrayLanguage 更新提示与菜单文案。
 * - 文案常以 UTF-8 保存，托盘侧输出到 Win32 W API 前会转换为 UTF-16。
 */

#ifndef LANGUAGE_H
#define LANGUAGE_H

#include <windows.h>

// 语言类型定义 / Language type definition
typedef enum
{
    TRAY_LANG_CHINESE = 0, // 中文
    TRAY_LANG_ENGLISH = 1  // 英文
} Language;

// 语言文本结构 / Language text structure
typedef struct
{
    // 应用程序信息 / Application info
    const char *appTitle; // 应用程序标题 / Application title
    const char *trayTip;  // 托盘提示 / Tray tooltip

    // 消息框文本 / MessageBox text
    const char *errorTitle;     // 错误标题 / Error title
    const char *logCreateError; // 日志创建错误 / Log creation error

    // 托盘通知文本 / Tray notification text
    const char *notifyAppStarted;     // 程序启动通知 / App started notification
    const char *notifyMainRunning;    // 主程序运行中 / Main program running
    const char *notifyMainNotRunning; // 主程序未运行 / Main program not running
    const char *notifyTrayStatus;     // 托盘状态 / Tray status
    const char *notifyAdminYes;       // 已获得管理员权限 / Admin rights obtained
    const char *notifyAdminNo;        // 未获得管理员权限 / Admin rights not obtained

    // 主程序状态文本 / Main program status text
    const char *mainStatusRunning;    // 主程序状态：运行中 / Main program status: running
    const char *mainStatusNotRunning; // 主程序状态：未运行 / Main program status: not running

    // 主程序管理操作文本 / Main program management text    const char *startingMain;     // 正在启动主程序 / Starting main program
    const char *closingMain;      // 正在关闭主程序 / Closing main program
    const char *restartingMain;   // 正在重启主程序 / Restarting main program
    const char *exitingTray;      // 正在退出托盘程序 / Exiting tray program
    const char *mainNotExists;    // 主程序不存在 / Main program does not exist
    const char *userCancelledUAC; // 用户取消了UAC / User cancelled UAC
    const char *startFailed;      // 启动失败 / Start failed
    const char *closeFailed;      // 关闭失败 / Close failed

    // GUI相关文本 / GUI related text
    const char *openingConfig;    // 正在打开配置界面 / Opening configuration interface
    const char *configNotExists;  // 配置界面不存在 / Configuration interface does not exist
    const char *openConfigFailed; // 打开配置界面失败 / Failed to open configuration

    // 管理员权限检查文本 / Admin rights check text
    const char *adminCheckYes;           // 主程序已获得管理员权限 / Main program has admin rights
    const char *adminCheckNo;            // 主程序未获得管理员权限 / Main program does not have admin rights
    const char *adminCheckUnknown;       // 无法确定主程序权限状态 / Cannot determine admin status
    const char *adminCheckReadError;     // 无法读取主程序权限状态 / Cannot read admin status
    const char *adminCheckFileNotExists; // 主程序权限状态文件不存在 / Admin status file does not exist    // 托盘菜单项文本 / Tray menu item text
    const char *menuOpenConfig;          // 打开配置界面 / Open configuration
    const char *menuCheckAdmin;          // 检查主程序管理员权限 / Check main program admin rights
    const char *menuStartMain;           // 启动主程序 / Start main program
    const char *menuRestartMain;         // 重启主程序 / Restart main program
    const char *menuCloseMain;           // 关闭主程序 / Close main program
    const char *menuExit;                // 退出托盘 / Exit tray
    const char *menuTrayStatus;          // 托盘状态 / Tray status
    const char *menuVersionInfo;         // 版本信息 / Version info
    const char *menuSwitchLanguage;      // 切换语言 / Switch language
    const char *menuExitStandalone;      // 退出托盘 / Exit tray without restarting main
    const char *menuVersionFallback;     // 版本信息（兜底）/ Version info fallback

    // 提示和标题 / Prompts and titles
    const char *promptTitle;      // 提示标题 / Prompt title
    const char *errorPromptTitle; // 错误提示标题 / Error prompt title

    // 版本检查提示 / Version check text
    const char *versionCheckingSuffix; // 版本检查中 / checking suffix
    const char *versionSuffixNew;      // 发现新版本 / new version suffix
    const char *versionSuffixLatest;   // 已是最新 / latest suffix
    const char *versionSuffixAhead;    // 当前版本较新 / ahead suffix
    const char *versionSuffixError;    // 检查失败 / error suffix
    const char *versionNotifyNew;      // 新版本通知 / new version notification
    const char *versionNotifyLatest;   // 最新通知 / latest notification
    const char *versionNotifyAhead;    // 更高版本通知 / ahead notification
    const char *versionCheckFailed;    // 检查失败通知 / check failed notification

    // 彩蛋链接提示 / Easter egg text
    const char *randomImageOpened;
    const char *randomImageFailed;

    // 提权提示 / Elevation prompt
    const char *requestAdminPrompt;
    const char *requestAdminFailed;
} LanguageStrings;

// 检测系统语言 / Detect system language
// - 通常基于 GetUserDefaultUILanguage/GetSystemDefaultUILanguage 等判断。
Language DetectSystemLanguage(void);

// 获取当前语言的字符串 / Get strings for current language
// - 返回指针为静态存储或由模块持有，不需要调用方释放。
const LanguageStrings *GetLanguageStrings(void);

// 初始化语言支持 / Initialize language support
// - 程序启动时调用：选择初始语言并准备字符串表。
void InitializeLanguage(void);

// 获取当前语言 / Get current language
Language GetCurrentLanguage(void);

// 设置语言 / Set language
// - 设置后通常需要刷新托盘提示/菜单。
void SetLanguage(Language lang);

// 切换语言 / Toggle language
// - 在中/英之间切换。
void ToggleLanguage(void);

#endif /* LANGUAGE_H */
