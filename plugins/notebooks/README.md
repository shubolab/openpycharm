# Native notebooks / 原生 Notebook

Independent native IntelliJ `FileEditor` for nbformat 4 `.ipynb` files. Python cells use IntelliJ editors and PythonCore PSI; Markdown and raw cells are editable native text. Opening a file does not execute code. Execution requires a trusted project and its selected local module/project Python SDK.

在原生 IntelliJ 编辑器内编辑 nbformat 4 格式的 `.ipynb`。Python 单元使用 PythonCore PSI，Markdown 和 raw 单元可编辑。打开文件不会执行代码；运行前必须信任项目，并配置本地项目或模块 Python 解释器。

Install the optional open-source dependencies in that selected interpreter:

```sh
/absolute/path/to/selected/python -m pip install jupyter_client==8.6.3 ipykernel==6.29.5
```

请把上面的路径换成项目所选解释器。IDE 不会自动安装依赖，也不要求 IDE 账号。仅启动此解释器的本地内核，不连接现有或远程 Jupyter 服务。连接密钥存放在当前会话独立的临时目录。

Use **Run Cell**, **Shift+Enter**, **Run All**, **Interrupt**, and **Restart Kernel**. Variables persist until restart. The notebook's parent directory is the working directory. Stream output, plain-text results and Python tracebacks are shown natively. Output metadata and unsupported rich data survive ordinary saves; captured transient display IDs stay in memory. Live display updates and deferred `clear_output(wait=True)` are handled in the active session. Source, outputs and counts update the ordinary IntelliJ file document for normal saving/undo. A **Save** button requests saving on a background worker.

使用 **Run Cell**、**Shift+Enter**、**Run All**、**Interrupt** 和 **Restart Kernel**。变量在重启前保留，工作目录为 notebook 所在目录。原生界面显示标准输出、文本结果和 Python 错误。普通保存保留元数据及未支持的富媒体数据。源码、输出和执行次数写入 IntelliJ 文档；可使用标准保存/撤销操作。

The fixture `fixtures/notebooks/native-demo.ipynb` has empty outputs until actually run. Bounds are 1,000 cells, 8 Mi characters per notebook, 512 KiB execution source, 1 MiB per kernel event and 4 MiB per execution. Reaching the output cap interrupts the owned kernel and displays a real limit notice. Only processes launched by this notebook session, verified by PID and start time, are cleanup candidates.

Current verified scope: authenticated SDK compilation, JAR-reader validation, nbformat persistence tests and actual local-kernel/process tests on macOS. Native editor desktop acceptance, installed-product saving/undo, Windows execution and installers are separate checks. Rich HTML/images, rendered Markdown preview, widget comms, remote kernels, interactive stdin and notebook debugging are not implemented. This is a bounded addition, not full PyCharm 1:1 acceptance.

目前已验证 macOS 的认证 SDK 编译、JAR 读取、nbformat 持久化和真实内核运行/进程清理。原生桌面交互、安装后保存与撤销、Windows 运行和安装包仍需分别验收。富媒体渲染、Markdown 预览、组件通信、远程内核、交互式输入与 notebook 调试尚未实现，不能据此宣称完整 1:1 对齐。
