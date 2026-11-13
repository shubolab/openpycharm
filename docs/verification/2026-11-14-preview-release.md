# OpenPyCharm 0.1.0-dev.1 原生预览版

这是首个可安装预览版，完整 1:1 对齐仍在进行。[验收矩阵](../acceptance.md)列出尚未完成的工作。
生产代码提交为 `3b45fda2ceb2a4d81c8eaf1169f953dd8b1b8b5e`；发版时的后续提交更新文档和演示，生产输入清单保持一致。

| 安装器 | SHA-256 |
| --- | --- |
| macOS arm64 DMG | `4b6954fb3a3116b5b05f6933d9e603840de28cce364e6fce42d0c35fda4b9c27` |
| Windows x64 EXE | `97249b3e261bf9d427a39cd1ad6652d780ea5d507e35a168cf8e2c490326d374` |

macOS 在 27.2 arm64、Python 3.14.0 上，从本版 DMG 安装到 `~/Applications`，通过原生界面打开自有示例并正常确认项目信任。运行输出 `34.00 / 2.04 / 36.04`，退出码为 0；原生 unittest 的 9 个方法和子测试共显示 20 个通过项。调试停在 `calculator.py:20`，表达式结果为 `Decimal('2.0400')`，F8 前进到 21 行，F9 完成并退出 0。About 显示 OpenPyCharm 和平台构建 `PC-261.26222.68`。

这些操作完成后，安装应用的完整文件树仍为 `b5888e27d7b389487839266675614243cfb3efe5974ce10d1051581cb0bd799a`，签名复验通过。前序候选的测试助手曾在包内新增字节码而使签名失效；本版将 Mac 包内助手资源目录设为只读，实际复测未再产生包内缓存，用户项目缓存仍可生成。没有修改参考 PyCharm 或它的用户数据。

本次 Mac 桌面会话没有 ERROR/SEVERE；22 条警告保留在结构化记录中，包括上游配置服务、主题兼容键、Python 探测、响应耗时和调试器提示。不将其描述为无警告运行。更早的应用路径迁移后解析/测试识别异常已在复测中恢复，根因仍未确定。

Windows 在 GitHub 的真实 Windows runner 上完成组装、原生启动、安装到含空格的临时路径、安装文件一致性核对、安装后原生启动及静默卸载进程。启动加载 Python、Git、Terminal，四类产品目录均独立，日志没有 ERROR/SEVERE。正常项目信任对话框没有绕过，因此本记录不证明 Windows Python Run/Test/Debug、文件关联或完整卸载残留检查。

[同源码 CI](https://github.com/shubolab/openpycharm/actions/runs/43470135186) 的 Mac 与 Windows 两项均成功，Mac 的 51 项仓库检查通过；Windows 的 49 项通过，2 项 POSIX 权限检查按平台跳过。两端均通过 9 个示例测试。交付的 Mac DMG 是上述本机实际安装与录制的产物；CI 另行验证同一源码，不声称两个独立构建逐字节相同。

- [Mac 结构化记录](macos-preview-20261114.json)
- [Windows 结构化记录](windows-preview-20261114.json)
- [实际安装版 GIF 与拍摄清单](../demo/README.md)
- [安装说明](../installation.md)

Mac 应用使用临时签名且未公证；Windows 安装器未签名。About 当前保留平台版本，发行版本以构建清单和安装器名称为准。框架、数据库、Notebook、前端、容器、远程开发与 HTTP 扩展的完整实现和验收仍在后续范围内。
