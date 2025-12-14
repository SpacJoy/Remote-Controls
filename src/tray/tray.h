/**
 * 远程控制托盘程序头文件
 *
 * 说明：托盘程序负责与主程序 RC-main.exe 协作，提供 UI 入口与进程/权限管理。
 * 部分能力通过共享工具库 rc_utils 实现（例如提权启动、taskkill、读取 admin_status.txt）。
 */

#ifndef TRAY_H
#define TRAY_H

#include <windows.h>
#include <shellapi.h>
#include <tlhelp32.h>

// 初始化应用程序
// - 初始化语言/日志/路径。
BOOL InitApplication(void);

// 检查用户是否拥有管理员权限
// - 常见实现：shell32!IsUserAnAdmin 或 TokenElevated。
BOOL IsUserAdmin(void);

// 检查主程序是否正在运行
// - 常见实现：进程名 + 互斥体（MUTEX_NAME）双重判断。
BOOL IsMainRunning(void);

// 创建系统托盘图标
// - 使用 NOTIFYICONDATAW + Shell_NotifyIconW。
void CreateTrayIcon(HWND hWnd);

// 显示气泡通知
// - 使用 NOTIFYICONDATAW 的 NIF_INFO。
void ShowNotificationDirect(const char *title, const char *message);

// 以管理员权限运行程序
// - 常见实现：ShellExecute("runas")。
BOOL RunAsAdmin(const char *exePath);

// 启动主程序
// - 通常会根据当前是否已提权选择不同启动路径。
void StartMainProgram(void);

// 关闭主程序
// - 通常使用 taskkill（可能需提权）。
void CloseMainProgram(void);

// 重启主程序
// - 关闭后等待片刻再启动。
void RestartMainProgram(void);

// 打开配置GUI
// - 启动 RC-GUI.exe。
void OpenConfigGui(void);

// 检查主程序的管理员权限状态
// - 读取 logs\admin_status.txt（由主程序写入）。
void CheckMainAdminStatus(void);

// 记录日志消息
// - 写入 logs\tray.log；本项目实现中支持运行时查看与 200KB 上限。
void LogMessage(const char *level, const char *format, ...);

#endif /* TRAY_H */
