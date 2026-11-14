# Static native notebook rich output

This branch adds independent native Swing PNG/JPEG images, static HTML/DataFrame tables, styled Markdown output and Markdown cell previews. Python code cells still use the IntelliJ editor and Python PSI. A worker prepares inert text/table data and decoded images; no HTML editor kit, JCEF, browser, script engine or URL loader receives notebook markup. Opening a notebook still does not execute Python.

Project Safe Mode shows plain-text fallback instead of rich output. A stored notebook `trusted` flag never authorizes active content, and rendering preserves it. The output MIME bundle and unknown metadata remain in nbformat; the renderer only limits previews. Session `display_id` updates replace existing output data/metadata before ordinary save, while transient display IDs remain in memory.

The prepared-image ledger caps each decoded image at one megapixel and the notebook's cached plans at four megapixels. Encoded image data, source dimensions, text, markup, rows, columns, cell strings and native block counts have separate bounds documented in `plugins/notebooks/README.md`. One worker and latest-only cell/result queues coalesce updates. Superseded inputs are cancelled; removed cells and closed editors release scheduler/viewer image references. Static HTML ignores resource/event/style attributes, scripts and active elements; table renderers cannot invoke JLabel's implicit HTML handling. Existing open-source JetBrains Markdown is used from the authenticated SDK, with its exact JAR hash and Apache-2.0 attribution retained.

The accepted save fix is included as commit `34dd8e6`, equivalent to `28378bd`: enter the pinned platform save manager from an unlocked worker and confine the entire parent-document reload entry to the EDT. Dirty-state, three-way merge, exact-number semantics and independent owned-kernel disposal remain intact. Save/Undo desktop acceptance is still the root-controlled native gate, not a conclusion of this branch's headless controls.

Shift+Enter now uses `DumbAwareAction.registerCustomShortcutSet` on the IntelliJ cell content component, scoped to that cell's disposable. Code guards stale/disposed cells, and execution still checks project trust and the selected local interpreter. The observed Swing InputMap path was replaced, but the actual shortcut has not been pressed in an IDE by this agent. Ordinary Python exceptions now have separate last-cell status text while the kernel is idle; actual native label appearance remains unverified.

Both actual Python **3.14.0** and **3.11.15** owned kernels passed the same rich workflow with unchanged `jupyter_client==8.6.3` and `ipykernel==6.29.5` pins. The kernels produced real Matplotlib PNG, Pillow JPEG, pandas HTML tables and IPython Markdown. Real `display_id` updates changed chart bytes and the table value from 42 to 99. The complete captured nbformat JSON survived actual file write/parse/reopen unchanged, including rich and unknown metadata, large integers and stored trust state. Reopened MIME data created native headless Swing image components, `JTable` and styled `JTextPane`; actual image painting was checked. These are test controls, not native IDE screenshots or feature-demo captures.

Reproduction from this branch, with an already provisioned test-owned interpreter:

```sh
python3.11 scripts/build_notebook_plugin.py --sdk /absolute/authenticated/PyCharm.app --tests
python3.11 scripts/notebook_rich_probe.py --sdk /absolute/authenticated/PyCharm.app \
  --python /absolute/test-owned/python --output .tools/new-rich-report.json \
  --notebook .tools/new-rich-capture.ipynb
```

The external producer pins are `tests/notebooks/rich-requirements-314.txt` and `rich-requirements-311.txt`; they are not IDE dependencies or redistributed Python packages. Exact selected runtimes, plugin/test source hashes, JAR receipt, actual notebook digests and bounded controls are recorded in `notebook-rich-20261114.json`. Root's newer `notebook_session_probe.py` CLI/source is not replaced by this rich change.

Native UI layout/theme/scrolling, actual keyboard dispatch, ordinary project-trust interaction, installed editor save/undo/project close, Windows native execution/rendering, installers and a real installed demo GIF remain separate gates. Multi-row HTML header/rowspan fidelity is limited. Arbitrary HTML/CSS layout, SVG, MathJax, Markdown attachment images, widget communication, remote kernels, interactive input and notebook debugging remain outside this bounded addition. This is not full PyCharm parity.

中文：本分支新增原生 Swing 图像、静态 HTML/DataFrame 表格、Markdown 输出及单元预览，保留原 IntelliJ 桌面、编辑器和 Python PSI。解析、Markdown/HTML 处理及图片解码均在后台；界面只接收有界、惰性的样式文本、表格和图片，不执行输出脚本或加载外部资源。Safe Mode 仅显示纯文本，不自动执行 notebook；stored trust 和未知元数据按原值保留。

真实 Python 3.14.0 与 3.11.15 的内核产物及更新保存往返已验证，完整捕获的 nbformat JSON 保持一致；headless 原生控件及图片绘制通过，外部请求为零。Shift+Enter 已改为原生 Action 并随单元释放，但本代理未启动 IDE，也未宣称桌面快捷键、保存、布局、Windows、安装包或 GIF 验收通过。根流程负责这些原生门，不能用此处测试代替完整 1:1 验收。
