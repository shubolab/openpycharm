# OpenPyCharm

[English](README.md)

我们自己的原生 Python IDE，基于开源 PyCharm 和 IntelliJ Platform 构建，
以本机 **PyCharm 2026.1.4** 为对照。工作台、编辑器和 Python 代码分析沿用同版本
开源基础；本仓库负责独立产品身份、发行、集成修改和实际验收。

**当前正在开发，完整 1:1 对齐尚未完成。** [验收矩阵](docs/acceptance.md)保留了
待验证的原生工作流，以及框架、数据库、Notebook、前端与远程开发等工作。

首个原生预览版：[v0.1.0-dev.1](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.1)。

| 系统 | 安装包 |
| --- | --- |
| macOS Apple silicon | [DMG 下载](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.1/OpenPyCharm-0.1.0-dev.1-macos-arm64.dmg) |
| Windows x64 | [EXE 下载](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.1/OpenPyCharm-0.1.0-dev.1-windows-x64-setup.exe) |

见[安装说明](docs/installation.md)、[校验和](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.1/SHA256SUMS.txt)
与[本版验收记录](docs/verification/2026-11-14-preview-release.md)。macOS 实际安装版已通过
运行、unittest 和调试；Windows 已通过安装和原生启动，Python 桌面工作流仍待验收。
Mac 应用使用临时签名且未公证，Windows 安装器未签名。

![OpenPyCharm 原生功能演示](docs/demo/openpycharm-native.gif)

实际安装版 **0.1.0-dev.1**，系统 **macOS 27.2 arm64**，Python 3.14.0。
依次展示运行、unittest 结果、断点求值和单步执行，详见[拍摄记录](docs/demo/README.md)。
每个可发版版本会同步更新实际安装版的演示和版本标记。

## 本机构建

打包需要 Python 3.10 或更新版本，并在构建空间之外保留至少 20 GiB 可用磁盘。
应用内置 Java 运行时；Python 项目使用你选择的本机 Python 解释器。

```sh
python3 -m pip install -r requirements-build.txt
python3 -m unittest discover -s tests -v
python3 scripts/provision_http_compiler.py
python3 scripts/build.py --target macos-arm64
python3 scripts/launch.py --profile .state/development fixtures/hello-python
python3 scripts/installers.py --target macos-arm64 --version 0.1.0-dev.2 --product build/product/OpenPyCharm.app
```

Windows 使用 `python` 和 `--target windows-x64`，产物目录为
`build/product/OpenPyCharm`。安装器构建器按需取得并验证 Inno Setup 编译器。
详见[安装说明](docs/installation.md)。

基础包来自[官方开源发行页](https://github.com/JetBrains/intellij-community/releases/tag/pycharm/2026.1.4)，
下载时核对大小和 SHA-256，复用缓存时核对完整文件树。已安装的商业 IDE 及其用户
数据只用于只读比对，不作为分发输入。Git、GitHub 和私有仓库认证保留。

## 示例与验收

[hello-python](fixtures/hello-python) 提供补全、跨文件导航、重构、运行、unittest
和断点调试示例。命令行测试通过与桌面验收分开记录。参考版本和范围见
[本机观察记录](docs/reference/installed-pycharm.md)与[架构说明](docs/architecture.md)。

源码修改采用 Apache-2.0，保留上游及第三方声明。OpenPyCharm 由我们独立维护。
