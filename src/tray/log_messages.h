/**
 * 远程控制托盘程序 - 日志信息
 * Remote Control Tray - Log Messages
 *
 * 说明：
 * - 这里存放的是“日志模板文案”，用于统一 LogMessage 输出内容。
 * - 与 LanguageStrings 类似，通常按当前语言返回一套常量字符串。
 * - 这样做的好处：日志内容随语言切换而变化，但日志结构/关键字段保持一致。
 */

#ifndef LOG_MESSAGES_H
#define LOG_MESSAGES_H

#include "language.h" // 导入语言类型定义

// 日志消息结构体定义
typedef struct
{
    // 应用程序启动相关
    const char *appStarted;
    const char *appPath;
    const char *systemInfo;
    const char *trayAdminStatus;
    const char *adminYes;
    const char *adminNo;
    const char *mainPath;

    // 进程检查相关
    const char *createSnapshotFailed;
    const char *mainFound;
    const char *mainFoundMutex;
    const char *mainNotFound;

    // 图标加载相关
    const char *iconLoadedFile;
    const char *iconLoadFailed;
    const char *iconLoadedResource;

    // 通知相关
    const char *notification;

    // 启动程序相关
    const char *runasAttempt;
    const char *uacCancelled;
    const char *startFailed;
    const char *startSuccess;

    // 函数执行和主程序管理相关
    const char *funcStartMain;
    const char *mainRunning;
    const char *mainStartSuccess;
    const char *mainStartFailed;
    const char *mainNotExists;
    const char *funcCloseMain;
    const char *mainNotRunning;
    const char *taskkillCommand;
    const char *taskkillExitCode;
    const char *taskkillFailed;
    const char *closeRequested;
    const char *funcRestartMain;

    // 配置界面相关
    const char *funcOpenConfig;
    const char *configOpened;
    const char *configOpenFailed;
    const char *configNotExists;

    // 管理员权限检查相关
    const char *funcCheckAdmin;

    // UI相关
    const char *createMenuFailed;
    const char *registerClassFailed;
    const char *createWindowFailed; // 托盘启动和退出相关
    const char *trayStartNoMain;
    const char *trayStartMainRunning;
    const char *initTrayFailed;
    const char *trayCreated;
    const char *userRequestExit;
    const char *trayExit;
} LogMessages;

// 获取当前语言的日志消息
// - 返回指针由模块持有，不需要释放。
const LogMessages *GetLogMessages(void);

// 初始化日志消息
// - 程序启动时调用；应在 InitializeLanguage 之后。
void InitializeLogMessages(void);

#endif /* LOG_MESSAGES_H */
