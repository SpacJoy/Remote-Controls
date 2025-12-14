#pragma once

#include <stdbool.h>

#ifdef __cplusplus
extern "C"
{
#endif

    /*
     * 动作执行模块：把“字符串动作/参数”转换成实际的 Windows 行为。
     *
     * 涵盖：
     * - 计算机电源/会话：lock / shutdown / restart / logoff
     * - 睡眠/休眠/显示器电源
     * - 多媒体控制（播放/暂停/上一首/下一首等）
     * - 音量/亮度（含 Twinkle Tray CLI）
     * - 启动程序、执行 PowerShell
     * - 结束进程（taskkill/TerminateProcess/CTRL_BREAK）
     * - 服务启停（SCM：OpenSCManager/OpenService/StartService/ControlService）
     * - 热键模拟（键盘输入）
     */

    /*
     * 计算机级动作。
     * - action：动作字符串，例如 "lock"/"shutdown"/"restart"/"logoff"/"none"。
     * - delaySeconds：关机/重启延迟秒数（<0 会被当作 0）。
     */
    void RC_ActionPerformComputer(const char *action, int delaySeconds);

    /*
     * 睡眠相关动作。
     * - action："sleep"/"hibernate"/"display_off"/"display_on"/"lock"/"none"。
     */
    void RC_ActionPerformSleep(const char *action);

    /*
     * 控制显示器电源（通过广播 WM_SYSCOMMAND/SC_MONITORPOWER）。
     * - on=true：唤醒显示器；on=false：关闭显示器。
     */
    void RC_ActionSetDisplayPower(bool on);

    /*
     * 多媒体命令：
     * - command 示例："on"/"off"/"pause"/"on#xx"（具体解析规则见实现）。
     */
    void RC_ActionMediaCommand(const char *command);

    /*
     * 设置亮度（0~100）。
     * - 返回 true 表示调用链执行成功；false 表示失败（例如无权限/无设备/接口不可用）。
     */
    bool RC_ActionSetBrightnessPercent(int percent0to100);

    /*
     * 使用 Twinkle Tray CLI 设置亮度（Twinkle Tray 需已安装，通常也需要运行）。
     * - exePathUtf8：Twinkle Tray.exe 路径（UTF-8）。为空时会尝试常见安装路径。
     * - targetModeUtf8/targetValueUtf8：目标显示器选择策略（例如 all/idx/name 等，取决于 Twinkle Tray CLI）。
     * - overlay/panel：是否显示叠加/面板（参数含义以 Twinkle Tray CLI 实际支持为准）。
     */
    bool RC_ActionSetBrightnessTwinkleTrayPercentUtf8(int percent0to100,
                                                      const char *exePathUtf8,
                                                      const char *targetModeUtf8,
                                                      const char *targetValueUtf8,
                                                      bool overlay,
                                                      bool panel);

    /*
     * 设置系统主音量（0~100）。
     * - 使用 Core Audio (MMDevice/EndpointVolume)。
     */
    bool RC_ActionSetVolumePercent(int percent0to100);

    /*
     * 启动指定程序（UTF-8 路径），一般通过 CreateProcess/ShellExecute 的封装实现。
     */
    bool RC_ActionRunProgramUtf8(const char *pathUtf8);

    /*
     * 执行 PowerShell 命令（UTF-8），可隐藏窗口/保留窗口。
     */
    bool RC_ActionRunPowershellCommandUtf8(const char *commandUtf8, bool hideWindow, bool keepWindow);

    /*
     * 扩展版 PowerShell：额外返回启动的 pid（若无法获取则为 0）。
     */
    bool RC_ActionRunPowershellCommandUtf8Ex(const char *commandUtf8, bool hideWindow, bool keepWindow, unsigned long *outPid);

    /*
     * 按 PID 结束进程树：taskkill /F /T /PID <pid>
     */
    bool RC_ActionTaskkillPidTree(unsigned long pid);

    /*
     * 按 PID 请求进程退出（不强制）：taskkill /PID <pid>
     */
    bool RC_ActionTaskkillPid(unsigned long pid);

    /*
     * 按 PID 强制结束（不带 /T，不杀子进程）：taskkill /PID <pid> /F
     */
    bool RC_ActionTaskkillPidForce(unsigned long pid);

    /*
     * 使用 TerminateProcess 直接终止进程。
     */
    bool RC_ActionTerminatePid(unsigned long pid);

    /*
     * 发送 CTRL_BREAK_EVENT 到进程组。
     * - 需要目标进程以 CREATE_NEW_PROCESS_GROUP 启动，并且拥有控制台。
     */
    bool RC_ActionSendCtrlBreak(unsigned long pid);

    /*
     * 另一种 CTRL_BREAK 尝试：不 AttachConsole，行为更接近 Python os.kill(CTRL_BREAK_EVENT)。
     */
    bool RC_ActionSendCtrlBreakNoAttach(unsigned long pid);

    /*
     * 通过可执行路径（UTF-8）定位并结束进程。
     */
    bool RC_ActionKillByPathUtf8(const char *pathUtf8);

    /*
     * Windows 服务控制：启动/停止服务（UTF-8 服务名）。
     */
    bool RC_ActionServiceStartUtf8(const char *serviceNameUtf8);
    bool RC_ActionServiceStopUtf8(const char *serviceNameUtf8);

    /*
     * 热键动作：根据 actionType/actionValue 模拟键盘输入。
     * - charDelayMs：字符间延迟（毫秒），用于提高某些窗口对输入的接受率。
     */
    bool RC_ActionHotkey(const char *actionType, const char *actionValue, int charDelayMs);

#ifdef __cplusplus
}
#endif
