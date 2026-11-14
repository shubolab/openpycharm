# Native notebooks / 原生 Notebook

Independent native IntelliJ `FileEditor` for nbformat 4 `.ipynb` files. Python cells use IntelliJ editors and PythonCore PSI; Markdown and raw cells are editable native text. Opening a file does not execute code. Execution requires a trusted project and its selected local module/project Python SDK.

在原生 IntelliJ 编辑器内编辑 nbformat 4 格式的 `.ipynb`。Python 单元使用 PythonCore PSI，Markdown 和 raw 单元可编辑。打开文件不会执行代码；运行前必须信任项目，并配置本地项目或模块 Python 解释器。

Install the optional open-source dependencies in that selected interpreter:

```sh
/absolute/path/to/selected/python -m pip install jupyter_client==8.6.3 ipykernel==6.29.5
```

请把上面的路径换成项目所选解释器。IDE 不会自动安装依赖，也不要求 IDE 账号。仅启动此解释器的本地内核，不连接现有或远程 Jupyter 服务。连接密钥存放在当前会话独立的临时目录。

Use **Run Cell**, **Shift+Enter**, **Run All**, **Interrupt**, and **Restart Kernel**. Variables persist until restart. The notebook's parent directory is the working directory. Native output shows PNG/JPEG charts, static HTML/DataFrame tables, styled Markdown, text and Python tracebacks. Markdown source cells have a **Markdown Preview** toggle; **Refresh Previews** refreshes saved outputs after project trust changes. Output metadata and unsupported rich data survive ordinary saves; captured transient display IDs stay in memory. Live display updates and deferred `clear_output(wait=True)` are handled in the active session. Edits become dirty immediately, and a worker prepares compact JSON for the ordinary IntelliJ file document. **Save** waits for that prepared document before requesting background saving. A project close attempted during preparation is deferred; close again when preparation finishes.

使用 **Run Cell**、**Shift+Enter**、**Run All**、**Interrupt** 和 **Restart Kernel**。变量在重启前保留，工作目录为 notebook 所在目录。原生界面显示标准输出、文本结果和 Python 错误。普通保存保留元数据及未支持的富媒体数据。源码、输出和执行次数写入 IntelliJ 文档；可使用标准保存/撤销操作。

原生输出支持 PNG/JPEG 图表、静态 HTML/DataFrame 表格和带标题、强调、代码块、GFM 表格的 Markdown 预览。Markdown 单元可开关 **Markdown Preview**。项目处于不信任状态时仅显示纯文本，信任状态改变后可点 **Refresh Previews**。无论 notebook 的 trusted 元数据如何，预览都不运行脚本、不打开链接、不加载外部图片、样式或其它资源；该元数据按原值保存。

While edits are being prepared, changes in the text editor are merged against the last committed notebook. Independent cell and metadata changes are preserved. Overlapping changes remain dirty and show explicit **Keep Notebook Edits** / **Discard Notebook Edits and Use Text** choices. Closing a tab retains pending edits; reopening restores them for merging or conflict resolution. Both pending snapshots and prepared UI completions are coalesced to the latest value.

编辑内容在后台准备期间，文本编辑器中的改动会与 notebook 改动合并，保留互不冲突的源码和元数据。同一字段的冲突不会自动丢弃修改，界面提供保留 Notebook 或明确丢弃 Notebook、使用文本的选项。关闭标签仍保留待处理编辑，再次打开可继续合并或解决冲突。

The fixture `fixtures/notebooks/native-demo.ipynb` has empty outputs until actually run. Native admission bounds are 1,000 cells and 8 Mi characters. Existing metadata is preserved without pretty-print expansion. If edits grow a notebook beyond the admission bound, saving still preserves valid JSON; reopen it with the text editor. Execution bounds are 512 KiB source, 1 MiB per kernel event and 4 MiB per execution. Reaching the output cap interrupts the owned kernel and displays a real limit notice. Only processes launched by this notebook session, verified by PID and start time, are cleanup candidates. Disposal runs independently of protocol writes, including when an interpreter blocks without reading its input pipe.

Preview bounds: 128 output records and 64 native blocks per cell; 200,000 displayed text characters; 256 Ki characters per HTML/Markdown input; 200 table rows × 40 columns and 4,000 characters per table cell. PNG/JPEG encoded data is capped at 2 Mi characters, source images at 8 megapixels/8,192 pixels per side, and subsampled decoded images at 1 megapixel each. A notebook reserves at most 4 megapixels in total across active image decoding, cached plans and retained Swing viewers. Reservations are acquired before decoding and returned only after the final plan reference closes. An image update first clears its previous viewer before decoding its latest replacement; saved outputs remain complete. Superseded/current Swing plans have explicit references, so updates/disposal release old images; one worker and coalesced cell/UI queues prevent an update backlog. MIME parsing, Markdown/HTML processing and image decoding run off the Swing EDT.

预览对文本、表格、编码数据、原图尺寸和解码像素均设上限；超出部分保留在 notebook 中，不会为预览截断保存的数据。解析与图片解码在有界后台队列，原生控件仅接收准备好的图片、表格和样式文本。连续更新只保留最新任务及结果；图像在解码前预留像素，直到最后一个引用释放才归还，总额包括解码、缓存及当前界面，始终不超过 400 万像素。更新图像先清除旧预览再准备最新图像；保存的数据不变。删除单元或关闭编辑器会取消过期任务并释放图片引用。

Current verified scope: authenticated SDK compilation, JAR-reader validation, nbformat persistence, actual local-kernel/process tests on macOS, real PNG/JPEG/HTML/Markdown producers, and native headless Swing controls. Python 3.14.0 is exercised with the unchanged `jupyter_client==8.6.3` / `ipykernel==6.29.5` pins. Shift+Enter now uses a platform action scoped to the cell lifetime; actual desktop key dispatch remains unverified. Native editor desktop acceptance, installed-product saving/undo, Windows execution and installers are separate checks. Arbitrary HTML/CSS layout, scripts, external resources, SVG, MathJax, Markdown attachment images, widget comms, remote kernels, interactive stdin and notebook debugging are not rendered/implemented. This is a bounded addition, not full PyCharm 1:1 acceptance.

目前验证包括 macOS 认证 SDK/JAR、nbformat、真实内核运行与清理，以及真实内核产物进入 headless 原生 Swing 图像、表格、样式文本控件的链路。Python 3.14.0 使用原 kernel pins 实测。Shift+Enter 已改为原生平台 Action 并随 cell 释放，真实桌面按键仍待复测。IDE 桌面交互、安装后保存/撤销、Windows 和安装包仍需验收；不能将 headless 控件测试当作已运行 IDE 的截图或完整 1:1 对齐证据。
