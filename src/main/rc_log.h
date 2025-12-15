#pragma once

#include <stdarg.h>
#include <wchar.h>

#ifdef __cplusplus
extern "C"
{
#endif

    /*
     * 主程序日志模块（logs\main.log）
     *
     * 设计目标：
     * - 运行时可被外部查看/跟踪（shared-open，不独占）。
     * - 写入即时可见（关闭缓冲或设置为无缓冲）。
     * - 体积上限：200KB，达到/超过上限时先清空再继续写入。
     */

    /*
     * 初始化日志。
     * - appDirW：主程序所在目录（可为 NULL；此时回退到当前目录下的 logs\main.log）。
     * - 内部使用 _wfsopen(..., _SH_DENYNO) 允许其它进程读取/写入/删除该日志文件。
     */
    void RC_LogInit(const wchar_t *appDirW);

    /*
     * 写 INFO/WARN/ERROR 级别日志。
     * - fmt 为 printf 风格格式化字符串。
     * - 内部会输出到调试器（OutputDebugStringA）以及文件（若初始化成功）。
     */
    void RC_LogInfo(const char *fmt, ...);
    void RC_LogWarn(const char *fmt, ...);
    void RC_LogError(const char *fmt, ...);

    /*
     * 可选：日志通知回调（用于将 WARN/ERROR 转发到 UI，例如 Windows toast）。
     *
     * 说明：
     * - 回调仅在 RC_LogWarn/RC_LogError 时触发（INFO 不触发）。
     * - msg 为格式化后的消息内容（不含时间戳/换行）。
     * - 回调在调用线程内同步执行；应尽量轻量，避免再次调用 RC_Log* 造成递归。
     */
    typedef enum
    {
        RC_LOG_LEVEL_INFO = 1,
        RC_LOG_LEVEL_WARN = 2,
        RC_LOG_LEVEL_ERROR = 3
    } RC_LogLevel;

    typedef void (*RC_LogNotifyCallback)(void *ctx, RC_LogLevel level, const char *msg);

    void RC_LogSetNotifyCallback(RC_LogNotifyCallback cb, void *ctx);

#ifdef __cplusplus
}
#endif
