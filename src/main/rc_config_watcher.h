#pragma once

#include <windows.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C"
{
#endif

    /*
     * 配置文件监听模块（Config Watcher）：
     * - 使用 Windows ReadDirectoryChangesW 实时监控配置文件变化
     * - 当配置文件被修改时，触发回调函数
     * - 在独立后台线程运行，零 CPU 占用
     */

    /*
     * 配置变更回调函数类型
     * - configPath: 配置文件的完整路径（UTF-16）
     * - userContext: 用户自定义上下文指针
     */
    typedef void (*RC_ConfigChangedCallback)(const wchar_t *configPath, void *userContext);

    /* 不透明的监听器结构 */
    typedef struct RC_ConfigWatcher RC_ConfigWatcher;

    /*
     * 创建配置文件监听器
     * - configPath: 配置文件的完整路径（UTF-16）
     * - callback: 配置变更时的回调函数
     * - userContext: 传递给回调函数的用户上下文
     * 返回: 监听器实例，失败返回 NULL
     */
    RC_ConfigWatcher *RC_ConfigWatcherCreate(
        const wchar_t *configPath,
        RC_ConfigChangedCallback callback,
        void *userContext
    );

    /*
     * 销毁配置文件监听器
     * - 停止监听线程并释放资源
     */
    void RC_ConfigWatcherDestroy(RC_ConfigWatcher *w);

#ifdef __cplusplus
}
#endif
