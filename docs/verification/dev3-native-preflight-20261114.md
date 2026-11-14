# dev.3 原生桌面预验收（2026-11-14）

结论：候选暂不具备发版条件。真实桌面数据库流程通过了下述有界检查，Notebook 保存出现阻塞，正在修复。已发布版本仍为 dev.2，README 演示 GIF 仍对应其真实安装版。

本次运行的是未安装的 macOS arm64 四插件候选，生产输入为 `e2ddbfd980d69e1f5da852088aeca6c9c59656fc` 的 129 项文件，manifest SHA-256 为 `224d416a3d43dad51022c50d338788cafbd92924ccaef47576731ad48ecef051`。开始预验收时与开发分支的生产输入逐项一致；随后数据库布局修复已合入，需要重新构建并复测。原有安装版 dev.2 未被替换。

## 数据库

任务专用 SQLite 项目通过真实 UI 添加连接、手动连接、展示 7 个表和视图、生成并执行 SELECT。3 行产品数据包含中文、NULL 和二进制预览；`a_b` 的 Columns 只返回其 `exact_column`，未混入 `axb`。

事务实测为库存 12→11→Rollback→重新查询 12；第二次事务 Commit 后查询为 11，再恢复为 12。未提交更新后 Disconnect，重新连接查询仍为 12。650 行查询显示 500 行且明确标记截断。取消长查询后可继续查询得到 42；直接执行 COMMIT 会提示使用事务按钮。关闭并重新打开项目后，连接资料保留且没有自动连接。退出后的只读 SQLite 检查确认最终库存为 12。

默认窄面板存在按钮裁切：Connect、Commit、Rollback 被 FlowLayout 排到可见区域外。最大化工具窗口后完成了上述流程。独立复核接受了后续 `1d9bc97` 布局修复的 725 项有界几何检查，但真实桌面复测仍待进行。SQLite 没有验证网络数据库、TLS、真实 PasswordSafe 提供方和 Windows 桌面行为。

## Notebook

使用正常 SDK 选择流程指定任务专用 Python **3.14.0** 环境，已安装 `jupyter_client==8.6.3` 与 `ipykernel==6.29.5`。打开 Notebook 没有自动运行；点击 Run All 后实际返回解释器路径、项目 cwd、42、跨单元格状态、中文输出及预期 ValueError traceback。普通单元格异常后 UI 使用了误导性的 “Kernel error” 标签，实际内核进程仍在。

在任务副本中修改最后一个单元格，原生 Undo 恢复了原代码。再次修改为包含中文和 emoji 的代码后，Shift+Return 没有建立执行证据，UI 停在 “Preparing notebook changes from the text document…”。点击 Save 后界面失去辅助功能响应，磁盘文件仍为原始 1,364 字节，不能声称保存、重新打开或后续内核控制通过。

两份现场线程转储显示：后台 `NotebookFileEditor.saveDocument` 在 `WriteIntentReadAction.run` 中调用 `FileDocumentManager.saveDocument`；平台 `FileDocumentManagerListenerBackgroundableBridge.beforeAnyDocumentSaving` 同步等待 EDT，EDT 停在 `NonBlockingFlushQueue`。这给出了锁与跨线程保存路径的明确调查方向，尚需修复和真实平台复测。

截图、AX 文本、待保存代码、两份线程转储与 PID 所有权收据保留在本机 `.tools/ci/dev3-preflight/`，逐文件哈希列于同名 JSON。仅对本次候选 PID 9045 发送 SIGTERM 后正常退出，未使用 SIGKILL；本次内核 PID 13601/13602 已退出，未停止其他任务的内核。原始跟踪 Notebook fixture 未修改。

仓库 112 项检查已通过，其中真实内核检查使用 Python 3.11.15；这与桌面使用的 Python 3.14.0 是两组证据。无头检查不能替代原生保存、窗口响应与重新打开验收。

## 后续 CI 检查

构建工作流新增任务专用内核 venv，显式安装两项可选依赖并导出解释器路径，使仓库检查运行真实内核案例。平台专用信号案例仍按实际系统保留跳过。另新增真实 JVM session 检查，要求版本、生产输入和 JAR 摘要匹配同次安装包插件编译收据；Windows 尚不支持的阻塞管道 disposal fixture 明确记为未验证。

本机使用非默认版本 `0.1.0-dev.3-ci-controls` 验证了该绑定：实际编译 JAR 与 session 收据摘要一致，真实内核与 POSIX 背压清理通过；篡改编译报告 JAR 摘要时在启动 session 前被拒绝。[检查收据](dev3-kernel-ci-controls-20261114.json)。远程双平台结果仍待运行。这项检查不覆盖上述原生保存故障。

结构化收据：[dev3-native-preflight-20261114.json](dev3-native-preflight-20261114.json)。这些结果不代表完整 PyCharm 1:1，也不代表 dev.3 已发布。
