<!-- @format -->

# GitHub Actions 构建与发布

本项目使用 GitHub Actions 自动化构建和发布流程。

## 🚀 使用方法

### 1. 标签发布（推荐）

```bash
# 创建并推送新标签
git tag V2.2.8
git push origin V2.2.8
```

这将：

-   自动提取版本号（去掉 V 前缀）
-   更新版本文件到 2.2.8
-   构建所有程序和安装包
-   创建 GitHub Release
-   上传构建产物

### 2. 手动触发（测试用）

1. 访问 [GitHub Actions](https://github.com/chen6019/Remote-Controls/actions)
2. 选择 "Build and Release Remote Controls" workflow
3. 点击 "Run workflow"
4. 输入版本号（如：2.2.8）
5. 选择是否更新版本文件
6. 点击运行

## 📦 构建产物

每次构建会生成：

-   `RC-main.exe` - 主程序
-   `RC-GUI.exe` - 图形界面
-   `RC-tray.exe` - 托盘程序
-   `Remote-Controls-Installer-{version}.exe` - 完整安装包

## 🔧 构建环境

-   **操作系统**: Windows (windows-latest)
-   **Python 版本**: 3.12.10
-   **打包工具**: PyInstaller (主要) + Nuitka (备用)
-   **依赖管理**: 虚拟环境 + requirements.txt

## ⚡ 快速测试

```bash
# 测试版本号提取
git tag V2.2.9-test
git push origin V2.2.9-test

# 手动删除测试标签
git tag -d V2.2.9-test
git push origin :refs/tags/V2.2.9-test
```

## 📋 注意事项

1. **标签格式**: 必须以 `V` 开头（如 V2.2.8）
2. **版本文件**: 自动更新 `version_info.py` 和相关文件
3. **构建失败**: 查看 Actions 日志获取详细错误信息
4. **权限要求**: 需要仓库的 push 权限来创建 Release

## 🛠️ 故障排除

### 构建失败

-   检查依赖是否正确安装
-   查看构建日志中的错误信息
-   确认 Python 版本兼容性

### 发布失败

-   检查 GITHUB_TOKEN 权限
-   确认标签格式正确
-   验证构建产物是否生成

### 版本冲突

-   确保标签版本唯一
-   手动触发时可以覆盖现有版本
