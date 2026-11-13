# 真实框架示例

三个小项目都提供 `GET /`，返回框架名称和 `OPENPYCHARM_FRAMEWORK_PROBE` 环境变量的值。它们使用真实 Django、Flask、FastAPI/Uvicorn 包，不是 HTTP 模拟服务器。

此目录是带环境标记的独立测试用例。原生 New Project 生成的项目使用普通 Hello 响应，不含这些测试字段。检查生成项目时给 `framework_server_smoke.py` 传入 `--projects`；省略该参数才会启用本目录的环境标记控制。

在一个明确选择的测试环境中安装依赖，例如在本仓库根目录执行：

```sh
python3 -m venv .tools/framework-venv
.tools/framework-venv/bin/python -m pip install -r fixtures/frameworks/requirements.txt
```

Windows 对应的解释器是 `.tools\framework-venv\Scripts\python.exe`。以上依赖版本用于这个可复现示例，没有宣称它们是最新版本。

分别用已加载框架插件的 OpenPyCharm 打开 `django`、`flask` 或 `fastapi` 目录，选择这个 venv 的解释器。各目录的 `.run` 文件给出对应原生运行配置。运行后访问控制台中的本机地址；调试时在 `index` 函数的 `marker = ...` 一行设置断点，再请求 `/`。

对原生配置的 Run、Debug、环境设置、断点、变量和 Stop，必须用真实桌面分别验收。命令模型的独立进程检查可以这样运行，`--sdk` 应指向经过本项目校验的开源 PyCharm SDK：

```sh
python3 scripts/framework_server_smoke.py \
  --sdk /absolute/path/to/authenticated/PyCharm.app \
  --python .tools/framework-venv/bin/python \
  --output build/framework-server-check
```

此检查从编译后的 Java 模型取得参数，给每个服务器分配本机临时端口，核对响应中的唯一环境标记，再停止本次启动的进程。它保留 venv 解释器的符号链接路径，避免误用基础 Python；它不代替 IDE 的原生 Run/Debug 验收。
