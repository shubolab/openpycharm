# OpenPyCharm

[English](README.md)

我们自己的原生 Python IDE，基于开源 PyCharm 和 IntelliJ Platform 构建，
以本机 **PyCharm 2026.1.4** 为对照。工作台、编辑器和 Python 代码分析沿用同版本
开源基础；本仓库负责独立产品身份、发行、集成修改和实际验收。

**当前正在开发，完整 1:1 对齐尚未完成。**

**0.1.0-dev.2 预览版**增加原生 HTTP 请求工具，以及我们独立实现的
Django、Flask、FastAPI 项目生成器和运行/调试配置：

- 编辑 `.http` 文件，运行当前请求或批量请求，在 Services 查看响应，保存原始响应
  字节，并停止正在执行的请求。
- 通过原生解释器/venv 选择器创建小型框架项目。依赖安装可选，默认关闭；运行与
  调试沿用所选 Python SDK、工作目录和环境变量。
- 修复 Markdown 预览冷启动初始化，保留正常渲染、代理配置及服务认证。

项目模板和运行/调试支持不代表完整框架语义支持：模板与 ORM 智能分析、框架导航
和更广的框架行为仍待补齐。**dev.2 不包含 Notebook 和数据库工具。**
详见[验收矩阵](docs/acceptance.md)与[dev.2 发行说明](docs/releases/v0.1.0-dev.2.md)。

最终 macOS 安装版已通过 Python 运行与 unittest、全新 FastAPI
创建与调试、HTTP 请求及 README 预览恢复；工作流结束后产品树未变，严格签名检查通过，
有界会话日志含 0 条错误、20 条保留警告。Windows 桌面工作流仍未验收。明确来源和
安装包摘要见 [dev.2 验收记录](docs/verification/2026-11-14-dev2-release.md)。

预览版：[v0.1.0-dev.2](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.2)。

| 系统 | 安装包 |
| --- | --- |
| macOS Apple silicon | [DMG 下载](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.2/OpenPyCharm-0.1.0-dev.2-macos-arm64.dmg) |
| Windows x64 | [EXE 下载](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.2/OpenPyCharm-0.1.0-dev.2-windows-x64-setup.exe) |

见[安装说明](docs/installation.md)、[校验和](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.2/SHA256SUMS.txt)
与[验收记录](docs/verification/2026-11-14-dev2-release.md)。Mac 应用使用临时签名且未公证，
Windows 安装器未签名。[上一预览版 dev.1](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.1)保留下载。

![OpenPyCharm 0.1.0-dev.2 实际安装版原生功能演示](docs/demo/v0.1.0-dev.2/openpycharm-native.gif)

实际安装版 **0.1.0-dev.2**，系统 **macOS 27.2 arm64**，Python **3.14.0**。
展示运行、unittest 结果、FastAPI 断点求值和 HTTP 批量/Unicode 响应。这是由真实
原生应用截屏组装的动画。
详见[拍摄清单](docs/demo/v0.1.0-dev.2/capture.json)。每个可发版版本都更新实际
安装版截屏和对应清单。

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

在 Python 示例自己的目录运行其测试：

```sh
cd fixtures/hello-python
python3 main.py
python3 -m unittest discover -s tests -v
```

Windows 使用 `python` 和 `--target windows-x64`，产物目录为
`build/product/OpenPyCharm`。安装器构建器按需取得并验证 Inno Setup 编译器。
详见[安装说明](docs/installation.md)。

基础包来自[官方开源发行页](https://github.com/JetBrains/intellij-community/releases/tag/pycharm/2026.1.4)，
下载时核对大小和 SHA-256，复用缓存时核对完整文件树。已安装的商业 IDE 及其用户
数据只用于只读比对，不作为分发输入。本地 IDE 使用不包含 IDE 账号、计费、订阅、
试用和升级推广流程；Git、GitHub、私有仓库及用户选择的开发服务认证保留。

## 示例与验收

[hello-python](fixtures/hello-python) 提供补全、跨文件导航、重构、运行、unittest
和断点调试示例。命令行测试通过与桌面验收分开记录。参考版本和范围见
[本机观察记录](docs/reference/installed-pycharm.md)与[架构说明](docs/architecture.md)。

源码修改采用 Apache-2.0，保留上游及第三方声明。OpenPyCharm 由我们独立维护。
