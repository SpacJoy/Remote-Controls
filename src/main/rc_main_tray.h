#pragma once

#include <stdbool.h>
#include <wchar.h>

#ifdef __cplusplus
extern "C"
{
#endif

    /*
     * 主程序内置最小托盘（fallback tray）。
     *
     * 启用条件：当外部托盘 RC-tray.exe 未运行时，RC-main 启动一个最小托盘，
     * 用于提供“退出”等基础操作。
     *
     * 行为细节：
     * - 启动后先延迟约 1s 再检查 RC-tray.exe，保持与 Python 版本行为一致。
     * - 用户从托盘选择 Exit 时，将 *stopFlag 置为 true，通知 MQTT 主循环退出。
     */
    void RC_MainTrayStartDelayed(const wchar_t *appDirW, const char *versionUtf8, volatile bool *stopFlag);

#ifdef __cplusplus
}
#endif
