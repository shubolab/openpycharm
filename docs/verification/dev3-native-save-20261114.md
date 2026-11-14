# dev.3 保存修复与原生复测（2026-11-14）

保存锁修复已在真实平台通过有界检查，完整 dev.3 发版验收尚未完成。

本次未安装候选的生产提交为 `83cf69aa4e52eb2740dc565f5945e28a4240c0da`，137 项生产输入与开发工作区逐项一致。Notebook JAR 为 `6f33f1470d94461b2309e8e9e48ad1ed6a62678ed135cbbd5ddb0053bef22970`，严格签名和四插件内容校验通过。已发布安装版 dev.2 保留未替换。

## 真实平台门

独立编译的探针绑定实际候选 Notebook JAR 和本次 nonce，在新建任务目录、独立四路径 profile 中运行实际 `NotebookFileEditor`、`UndoManager`、`FileDocumentManager` 与 Save 按钮。没有执行 Python，没有把夹具预置输出当成运行结果，没有写入信任绕过设置。

两次真实保存、原生撤销、单元格与 JSON 文本的并行合并、后续外部文本合并、完整未知元数据及输出保留、关闭重开均通过。保存后的 EDT 心跳继续，第一次保存后记录到 4 次心跳；最终 534 字节保存文件 SHA-256 为 `4e74959c78b8987997c16b1361bffe0138377c7f1c324c2f327bbe61bd19cb14`。探针 JAR 为 `87ad3036b8addaf64fe7dc45e81c653ec7146e0b5f0a27cf10584706bcb620c8`；针对字段丢失、大整数、类型及数组顺序变化的独立负例均能拒绝。

同一探针对修复前的 129 项输入候选执行了反例，实际 Notebook JAR 为 `4c3ff6c07e35e5f174fc25e5897e6cac37e40e9789b3d4d819035b5e5bafe8cf`。它在 `native-save-request` 阶段因保存未在截止时间前落盘被拒绝。本次反例的心跳仍正常，因此不能据此声称重现了此前手工操作中的 EDT 锁环。

两次探针各自的 launcher PID 为 35017、46669，均由自己的 POSIX session 清理，退出码 143；没有扫描或停止其他 IDE。完整本机收据分别位于 `.tools/native-save-fixed-83cf-1/` 和 `.tools/native-save-negative-original-1/`。

## 手工桌面复测与剩余问题

任务副本通过原生编辑和 Undo 恢复代码，再以系统保存快捷键将中文、emoji 和修改后的数值正确保存为 891 字节；关闭标签后重新打开，文本仍完整。界面保持响应。但系统 Save All 后的状态文字持续停在 “Preparing notebook changes”，重开后才恢复，仍需修正。源码复核确认成功 reload 分支没有重置这条文字，不能仅凭标签认定内部 `reloading` 一直为真；后续探针将同时观察字段状态和标签。

数据库窄面板中的 Begin transaction、Commit 已通过实际点击验证。连接任务专用 SQLite 后能展示元数据，但在 `completion.sql` 的正确 `2:18` 光标位置，以原生 Basic 动作调用补全，没有看到候选或插入；即使刷新元数据后也未建立成功证据。这是独立于纯上下文/缓存测试的原生接入问题，尚未接受补全功能。

手工阶段 PID 35245 在断开 JDBC、正常关闭项目后，以 SIGTERM 退出，没有使用 SIGKILL。其截图和 AX 文本位于 `.tools/ci/dev3-savefix-desktop/`。结束后校验了签名、实际插件与生产输入，未替换任何参考 PyCharm 配置或发行版安装。

工作流已加入实际候选上的原生保存门和失败日志留存，后续新生产提交需重新完成双平台检查。此次不代表富媒体组合验收、Windows 手工桌面验收或完整 PyCharm 1:1。

结构化收据：[dev3-native-save-20261114.json](dev3-native-save-20261114.json)。发版前仍须用最终安装版重新采集 README GIF。
