# 原生 Web 编辑与浏览器调试：有界 OSS 路线调研

日期：2026-11-14。目标参考为本机 PY-261.26222.68 / PyCharm 2026.1.4；实现输入仍是固定公开 PC SDK 和源码。本轮没有改 root 生产文件、参考安装或用户项目，没有启动 IDE、语言服务器或浏览器。仅在隔离工具目录编译了两类 Java 草稿。

建议优先验证 **SDK 已包含的原生 OSS LSP API/实现**。M0 先做一个真实 TypeScript stdio 闭环；通过后，再加入独立 CSS/HTML server 与 JavaScript 映射。LSP4IJ 0.21.0 保留为已具备兄弟项目经验的后备。浏览器调试是单独的 DAP/XDebugger 切片，不能从编辑补全通过推断完成。

## 已观察、推断与未知

已观察：固定公开提交 `456919a9624bae72ac12efafc35d2b916cb0c5c5` 有 Apache-2.0 的 `platform/lsp` API 和 `platform/lsp-impl`；认证 PC SDK 确实有对应 JAR。REA 静态归档核对：

| 归档 | SHA-256 | 完整归档成员数 |
|---|---|---:|
| `Contents/lib/intellij.platform.lsp.jar` | `31f9997c16f42c5491d96dc482da9507851844cc906bd79662440df6af2d8705` | 144 |
| `Contents/lib/intellij.platform.lsp.impl.jar` | `13db5f9fd6e5568fb026c6a0e292730d325f176bef3d419127343e92142eda3d` | 309 |

API 归档明确包含 `LspServerSupportProvider.class`、`LspServerDescriptor.class` 和 `intellij.platform.lsp.xml`。REA parent Evidence：`ev_5f5d82d9bf30b1f3e7f1c2c01059ab77fd16db08ee0b9714a2d431bfbd340313`、`ev_3b1022beadc4e66fea6ead94c22a9ca91d0d1af821c7e53aa58d37ba80cc4dc8`。归档枚举只证明这些成员存在；不证明模块已激活或功能可用。

最小 Java provider/descriptor 已用该 SDK 的 JBR javac、337 个现有 lib JAR、`--release 21 -proc:none` 编译通过；EP implementation 能对应到输出 class。草稿 JAR SHA 为 `69d39795359d3c6ce6ee9ada4b139b33c7d4d057dace903fe84d873da6027af5`。这是编译与描述符闭合证据，不是 plugin classloader、service、真实 stdio 或原生编辑验收。

推断：现有 SDK 有望直接承载独立前端语义插件，避免先引入另一整套 LSP 客户端和维护补丁。未知：实际 PC runtime 的模块/EP/service 注册、首个 server 连接、文档同步和全部编辑行为，均应留给后续正常 trusted 项目验证。[官方 LSP 帮助](https://plugins.jetbrains.com/docs/intellij/language-server-protocol.html)仍有商业发行覆盖/Ultimate dependency 的说明；本报告没有据此添加 Ultimate alias 或绕过条件，而是以固定公开源码、具体 PC 工件和后续运行门槛分别记录。

## 固定公开实现及门槛

并行只读审查完整读取 `platform/lsp`、`platform/lsp-impl` 中全部 **180 个生产 `.kt/.java/.xml/.properties` 文本，659,217 bytes**，排除测试；每个文件按固定 Git tree 的 blob SHA 验证，读取错误 0。在该范围内未发现产品、许可、订阅、Ultimate 或 PluginManager availability gate。这里没有保留逐文件 hash 清单，也不杜撰一个聚合 SHA；范围身份由上述固定 commit 和两棵公开源码树确定。

正常条件必须保留：

| 条件 | 固定源码 |
|---|---|
| 项目可信 | [LspClientManagerImpl.kt:89/146](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/lsp-impl/src/impl/LspClientManagerImpl.kt#L89)、[LspClientImpl.kt:208](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/lsp-impl/src/impl/LspClientImpl.kt#L208) |
| 文件本地且位于项目 content | [LspClientManagerImpl.kt:102](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/lsp-impl/src/impl/LspClientManagerImpl.kt#L102) |
| 有正常注册的 integration provider | [LspOpenedFilesService.kt:44](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/lsp-impl/src/impl/documentSync/LspOpenedFilesService.kt#L44) |
| descriptor/root 去重、最大 server 数限制 | [LspClientManagerImpl.kt:150](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/lsp-impl/src/impl/LspClientManagerImpl.kt#L150) |
| 支持的文件、服务端 capability 与 feature customizer | [LspCustomization.kt](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/lsp/src/api/customization/LspCustomization.kt) |

Registry 用于连接 timeout 和通信日志；该范围中的 ApplicationInfo 用途是初始化 clientInfo 版本，不是许可判断。on-type formatting 默认关闭，属于正常功能定制。连接/进程启动调度到 [LspClientImpl.kt:221](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/lsp-impl/src/impl/LspClientImpl.kt#L221) 的 pooled 工作；这不免除自有 provider 的线程责任。

正常声明可用 `com.intellij.modules.lsp`，对应[公开 impl 模块 XML](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/lsp-impl/resources/intellij.platform.lsp.impl.xml)。新 provider 使用 `com.intellij.platform.lsp.integrationProvider` EP、`LspIntegrationProvider.fileOpened`、`ProjectWideLspClientDescriptor(Project,String)`，实现 `isSupportedFile/createCommandLine/getLanguageId/createInitializationOptions`。`ensureClientStarted` 必须在 fileOpened 回调期间调用；回调内不能临时发现 SDK、下载工具或启动进程，参见[该 API 契约](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/lsp/src/api/LspIntegrationProvider.kt)。

## HTML、模板与缺失语义层

| 可复用部分 | 固定公开入口与边界 |
|---|---|
| 原生 HTML 文件类型、词法/语法、PSI | [HtmlFileType.java](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/xml/xml-psi-impl/src/com/intellij/ide/highlighter/HtmlFileType.java)、[HTMLParserDefinition.kt](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/xml/xml-psi-impl/src/com/intellij/lang/html/HTMLParserDefinition.kt)、`xml/xml-psi-api/.../psi/html/HtmlTag.java` |
| HTML 原生属性补全、XML/HTML 工程基础、Emmet | [HtmlCompletionContributor.java](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/xml/impl/src/com/intellij/codeInsight/completion/HtmlCompletionContributor.java)、`xml/emmet`；本轮没有验证实际编辑行为 |
| 多语言模板容器 API | [TemplateLanguageFileViewProvider.java](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/core-api/src/com/intellij/psi/templateLanguages/TemplateLanguageFileViewProvider.java)、同目录 `ITemplateDataElementType.java`；不是现成的完整 Django/Jinja 语义实现 |
| 原生调试 UI/脚本协议基础 | `platform/xdebugger-api`、`platform/script-debugger/backend`；这些基础 API 不能直接等同于商业 JavaScript browser debugger |

首切片应保留 HTML PSI，不用 LSP 或 TextMate 替换 IntelliJ 原生编辑器。CSS/JS/TS 可由独立 server 补语义，语法着色仍需正常文件类型/词法或许可明确的 TextMate grammar。LSP 结果不是完整 JS/TS PSI。HTML 中的 script/style、Django/Jinja 标签及源文件位置映射，必须单独设计和验证；先限制为独立文件，避免把这部分能力默认为完成。

## 当前官方版本与 pin 建议

以下是官方 metadata 查询结果；**本轮未下载和认证这些 server 发布字节**。详细 integrity、URL、Node SHA 和 metadata 限制见 [候选收据](../verification/frontend-route-20261114.json)。

| 组件 | 候选固定版本 / 许可 | 选择与限制 |
|---|---|---|
| Node | `24.22.3` LTS；MIT 及随包第三方声明 | [官方 SHASUMS](https://nodejs.org/dist/v24.22.3/SHASUMS256.txt)，分别锁 Mac arm64 / Windows x64；可供全部 server 与 DAP 共用 |
| TypeScript Language Server | `6.1.0`；Apache-2.0；Node `>=22.22.2` | [官方版本源码 manifest](https://github.com/typescript-language-server/typescript-language-server/blob/v6.1.0/package.json)、[发布记录](https://github.com/typescript-language-server/typescript-language-server/releases/tag/v6.1.0) |
| 经典 TypeScript SDK | `6.0.3`；Apache-2.0 | [官方 npm manifest](https://registry.npmjs.org/typescript/6.0.3)，有 `tsserver`；显式路径，避免 npm latest 已到 `7.0.2` 后静默切换到未验证 native 路线 |
| HTML/CSS language-service 库 | stable `5.6.2` / `6.3.10`；MIT | [HTML](https://github.com/microsoft/vscode-html-languageservice)、[CSS](https://github.com/microsoft/vscode-css-languageservice)；它们不是直接可运行的 stdio server |
| Microsoft HTML/CSS 真正 server | 各 `10.0.0`，VS Code `1.146.0` / commit `69047191fc427f2f92828279aae1d90d8eeda7ab`；MIT | [HTML manifest](https://github.com/microsoft/vscode/blob/1.146.0/extensions/html-language-features/server/package.json)、[CSS manifest](https://github.com/microsoft/vscode/blob/1.146.0/extensions/css-language-features/server/package.json)；分别构建 `src/node/htmlServerMain.ts` / `cssServerMain.ts` |
| Browser DAP | `vscode-js-debug 1.140.1`；[MIT](https://github.com/microsoft/vscode-js-debug/blob/v1.140.1/LICENSE) | [官方安全修复发布](https://github.com/microsoft/vscode-js-debug/releases/tag/v1.140.1)，使用 standalone `js-debug-dap`，不复制 VS Code/JetBrains 商业安装 |
| 后备 LSP4IJ | `0.21.0` / `b30f69dd1285f201d53ce360b7fad0bba96f0d58`；EPL-2.0 | [release](https://github.com/redhat-developer/lsp4ij/releases/tag/0.21.0)、[license](https://github.com/redhat-developer/lsp4ij/blob/0.21.0/LICENSE)、[Marketplace metadata](https://plugins.jetbrains.com/api/plugins/23257/updates?channel=&size=3)：update1157565，ZIP4,449,291 bytes，since242.0/until空 |

Microsoft server 的版本号不足以锁定可重复字节：该稳定 VS Code tag 的 manifests 实际依赖 HTML `^6.0.0-next.2` / CSS `^7.0.0-next.2` 等范围。不能把上表稳定 service 库直接代换进去。须选定官方 source entry、创建完整构建/运行依赖 lock、禁止安装脚本，再认证独立构建输出。`vscode-langservers-extracted 4.10.0` 是第三方提取包，不应称作 Microsoft 官方发行；本次不把它作为首选。

## opengoland 可复用经验

兄弟仓库的 `GoLanguageServerFactory.kt`、`GoTrackedConnectionProvider.kt` 和 `GoDocumentSync.kt` 提供 factory、进程连接、文档队列观察、UTF-16 与生命周期实践；`GoDebugAdapterFactory.kt` 提供原生 DAP descriptor 接线。Go-specific build tags、gopls 配置和 Delve 参数不能直接移植。

该仓库固定 LSP4IJ 0.21.0，并有公开源码回放修复：初始化期间未保存编辑的 didOpen/didChange 排序、删除取消、导航依赖 epoch、单请求取消/缓存、DAP pause/step 等。具体来源与回归见兄弟仓库 `product/patches/lsp4ij-0.21.0-document-sync.json`、`scripts/patch-lsp4ij.py` 和 `docs/verification/lsp-document-sync.md`。复用应按上游 hash/适用控制逐项回放，保留 EPL 对应源码及声明；不能把 Go 工作流证据改名为前端证据。若原生 LSP M0 通过，这些竞态用例仍可作为验证模型，不需要把整套补丁强加到另一个客户端。

## 最小实施顺序与验收矩阵

M0 草稿保存在工具 worktree 的 `.tools/frontend-api-audit/`，未加入产品：

* `probe/src/dev/openpycharm/frontend/probe/FrontendLspProbe.java`
* `probe/resources/META-INF/plugin.xml` 与 `probe/frontend-api-probe.jar`
* `compile-report.json`、`candidate-pins.json`、`README.md`

候选命令为 `node <TLS6.1.0>/lib/cli.mjs --stdio`，初始化显式指向 `<TypeScript6.0.3>/lib/tsserver.js`，选择 UTF-16。草稿默认关闭，仅对显式 owned fixture root/property 生效。Java 编译已通过，选项行为尚未做协议验证。

| 阶段 | 必须有的真实证据 | 当前状态 |
|---|---|---|
| M0 原生接线 | 正常 trusted isolated 项目；正常 module/EP/service；真实 stdio initialize；实际 server 身份；completion/diagnostics/跨文件 definition | 编译通过；全部 runtime 未测 |
| 文档正确性 | 未保存编辑、延迟 initialize、emoji/CRLF UTF-16、多 caret、取消、过期回包、双文件 rename/Undo、删除/重建、项目关闭 | 未测 |
| M1 独立 HTML/CSS/JS/TS | 原生 HTML PSI 无双重 completion/diagnostic；CSS hover/color/format；JS/TS imports、tsconfig、项目选择 SDK；正常无网失败与重启 | 未测 |
| M2 browser debug | pinned standalone DAP + 原生 XDebugger；真实断点命中、watch/evaluate、step/pause/continue、source map、重连；仅停止 owned 进程 | 未实现/未测 |
| 分发 | 两平台真实运行；空格/Unicode 项目与安装迁移；完整 payload/source/license receipt；签名前后及运行后 app 树/签名；DMG/EXE 安装 | 未测；不影响本次现有 release 的既有证据 |

DAP 源入口是公开 `src/dapDebugServer.ts`，接受 port/host 参数。候选是经归档确认后的对应 JS entry，显式 `0 127.0.0.1`，读取实际绑定地址；不是硬编码一个共享端口。浏览器由用户选择已安装可用的 Chrome/Edge/Chromium，launch 使用自有 userDataDir；attach 和 launch 的进程所有权不同，不能停止用户原有浏览器。源文件映射、workers/iframes、多 session 和浏览器认证需各自验证。

## 进程、认证与打包约束

工具发现、hash 校验、下载、子进程和等待全部放后台。provider 回调只使用已验证快照；缺工具时正常报告，不在打开文件时执行 npm install。项目选用的 TypeScript/plugin 属于代码执行面，保留正常 trust。首切片关闭自动 typing acquisition，避免未授权的 npm 网络与凭据传递；用户主动选择的 npm/Git/服务认证不删除、不改写、不写入日志或 provenance。

LSP 按 project/root/SDK/settings 生命周期管理，变更用客户端正常 restart；缓存只失效相关 server/document/settings，不清空 Python 索引。日志与 Node/TypeScript/DAP 临时目录指向自有 profile/system，运行时不写 app bundle。取消单个请求不能取消共享文档通知；只终止有 receipt 的本项目进程，Windows Job、POSIX owned group/身份或等效已验证的子进程树管理均须证明不留 orphan、不影响其他项目，禁止 killall node/browser。

额外平台 SDK 下载不是必要前提。主要新增成本是一个共享 Node、TypeScript 与 server/依赖包；已有原生 LSP JAR 无需再次分发。后备 LSP4IJ 增加约4.45MB ZIP及其依赖/修复维护。实际安装器体积应由闭包构建后测量，本报告不估计成已测大小。Mac Node 等可执行 payload 须先完成嵌套签名，再签最终 app；payload、独立 source/第三方 notices、架构与摘要均纳入现有多文件 receipt，运行后严格验签及 tree 不变是必要门槛。

仍不能称为 1:1：完整 JS/TS PSI 与重构、安全跨 Python/HTML/模板重命名、Django/Jinja 语义、HTML 内嵌 JS/CSS、React/Vue/Angular、npm/test/coverage 工作流、Live Edit、全部 source-map/browser 多目标交互均不由 LSP 接入自动获得。本报告只提出独立 OSS 路线及下一可验证切片，不作新发行或完整对齐声明。
