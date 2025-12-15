<!-- @format -->

# 动态版本管理系统

## 概述

实现了完全动态的版本管理系统，不再需要在源代码和打包脚本中硬编码版本号。

## 主要改进

### 1. Inno Setup 脚本动态版本 (`installer/Remote-Controls.iss`)

-   **问题**: 早期版本号曾硬编码为类似 `#define MyAppVersion "2.x.x"`
-   **解决**: 实现动态版本读取机制
-   **方法**: 打包脚本生成临时 Inno Setup 文件，在文件头部添加版本定义

### 2. 打包脚本改进 (`installer/build_installer.ps1`)

-   **版本读取逻辑**:

    1. 优先使用命令行参数指定的版本号
    2. 如无参数，自动从 `src/python/version_info.py` 读取版本
    3. 备用默认版本 "0.0.0"

-   **文件处理**:
    -   创建临时 `Remote-Controls-temp.iss` 文件包含版本信息
    -   构建完成后自动清理临时文件

### 3. 进程检测逻辑修复

-   **问题**: 安装时误报程序正在运行
-   **原因**: `tasklist` 命令返回码判断逻辑错误
-   **解决**: 使用 `findstr` 确认进程输出中实际包含目标进程名

### 4. 文件管理

-   **临时文件**: 添加到 `.gitignore` 避免误提交
    -   `installer/version.tmp`
    -   `installer/Remote-Controls-temp.iss`

## 使用方法

### 指定版本构建

```powershell
pwsh -File installer/build_installer.ps1 "3.0.0"  # 示例：也可以换成你的版本号
```

### 自动版本构建

```powershell
pwsh -File installer/build_installer.ps1
# 将自动从 src/python/version_info.py 读取当前版本
```

## 技术实现

### 版本检测代码

```pascal
function IsProcessRunning(ProcessName: String): Boolean;
begin
  Result := Exec('cmd', '/C tasklist /FI "IMAGENAME eq ' + ProcessName + '" | findstr /I "' + ProcessName + '"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := Result and (ResultCode = 0);
end;
```

### 动态 Inno Setup 文件生成

```powershell
$IssContentWithVersion = "#define MyAppVersion `"$FinalVersion`"`r`n" + $IssContent
Set-Content -Path $TempIssPath -Value $IssContentWithVersion -Encoding UTF8
```

## 兼容性

-   ✅ 本地构建: 完全支持
-   ✅ GitHub Actions: 已在工作流中集成
-   ✅ 手动构建: 支持交互式版本输入
-   ✅ 自动构建: 从版本文件自动读取

## 优势

1. **无需手动修改**: 打包时不修改源文件
2. **版本一致性**: 所有组件使用统一版本号
3. **自动化友好**: 适配 CI/CD 流程
4. **错误检测**: 进程检测更准确，减少误报
