<!-- @format -->

# GitHub Actions 更新日志生成指南

## 📋 当前实现

已在 `build-and-release.yml` 中实现了自动更新日志生成功能：

### 🔧 基础功能

-   **Commit 历史分析**: 自动比较当前标签与上一个标签之间的提交
-   **结构化输出**: 生成包含构建信息、下载链接、使用说明的完整 Release Notes
-   **智能链接**: 自动生成指向构建页面、提交记录的链接

### 📝 生成内容示例

```markdown
## Remote Controls V<版本号>

**自动构建发布** - 2025-08-20 10:30:00 UTC

### 📦 构建信息

-   **Python 版本**: 3.12.10
-   **构建环境**: Windows (GitHub Actions)
-   **构建 ID**: [12345](链接到构建页面)
-   **提交 SHA**: [`abc123`](链接到提交)

### 🎯 包含文件

-   `RC-main.exe` - 主程序
-   `RC-GUI.exe` - 图形界面程序
-   `RC-tray.exe` - 系统托盘程序
-   `Remote-Controls-Installer-<版本号>.exe` - 完整安装包

### 🔄 更新内容

-   修复安装器运行中程序处理问题 (abc123)
-   优化 GitHub Actions 工作流 (def456)
-   更新文档和说明 (ghi789)
```

## 🚀 高级功能启用

### 1. 第三方 Action 生成器

在 workflow 中已预置了 `mikepenz/release-changelog-builder-action`，可通过设置 `if: true` 启用：

```yaml
- name: Generate Release Notes with GitHub API
  if: true # 改为 true 启用
  id: release_notes
  uses: mikepenz/release-changelog-builder-action@v4
```

此 Action 支持：

-   基于 PR 标签自动分类
-   自定义模板和格式
-   更丰富的元数据提取

### 2. GitHub 原生自动生成

可以替换现有的 `actions/create-release@v1` 为更新的 API：

```yaml
- name: Create Release with Auto-Generated Notes
  uses: softprops/action-gh-release@v1
  with:
      tag_name: ${{ steps.version.outputs.tag_name }}
      name: Remote Controls ${{ steps.version.outputs.tag_name }}
      generate_release_notes: true # 启用原生生成
      files: |
          installer/dist/*.exe
          installer/dist/installer/*.exe
```

### 3. 基于 Conventional Commits

如果使用规范化提交格式，可以集成：

```yaml
- name: Generate Changelog
  uses: conventional-changelog/conventional-changelog-action@v3
  with:
      github-token: ${{ secrets.GITHUB_TOKEN }}
    version-file: src/python/version_info.py
```

## 🎯 定制化选项

### 提交消息分类

可以根据提交消息前缀自动分类：

-   `feat:` → 🚀 新功能
-   `fix:` → 🐛 Bug 修复
-   `docs:` → 📖 文档更新
-   `build:` → 🔧 构建优化

### PR 标签映射

如果使用 PR 工作流，可以基于标签分类：

-   `enhancement` → 🚀 新功能
-   `bug` → 🐛 Bug 修复
-   `documentation` → 📖 文档
-   `dependencies` → 📦 依赖更新

## 🔧 自定义模板

可以创建 `.github/release-template.md` 来定制 Release 格式：

```markdown
## 🎉 {{RELEASE_NAME}}

{{DESCRIPTION}}

### 📋 更新内容

{{CHANGELOG}}

### 📦 下载

{{ASSETS}}

### 🔗 相关链接

-   [完整更新日志](链接)
-   [问题反馈](链接)
```

## ⚡ 快速测试

1. **测试当前实现**:

    ```bash
    # 创建测试标签
    git tag V3.0.0-test
    git push origin V3.0.0-test
    ```

2. **手动触发验证**:

    - 访问 GitHub Actions 页面
    - 运行"Build and Release Remote Controls"
    - 查看生成的 Release Notes

3. **检查输出质量**:
    - Commit 历史是否正确提取
    - 链接是否有效
    - 格式是否美观

## 💡 改进建议

1. **集成更多元数据**: Issues 关闭、PR 合并信息
2. **多语言支持**: 根据仓库语言生成对应语言的更新日志
3. **版本对比**: 生成详细的版本差异对比
4. **自动更新**: 同步更新到项目的 `up.md` 文件
