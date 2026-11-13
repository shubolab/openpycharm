# Native frontend M0：编译与真实 stdio 验证

源码固定为 `8ac1372b63a2dc410b3761a33f9c1fbfb08ce591`，分支 `codex_frontend_m0`，基于 root `ced6c3f`。独立插件版本 `0.1.0-dev.4-m0`，**未接入生产 package，没有新发行声明**。完整摘要、来源与原始控制结果见 [JSON 收据](frontend-m0-20261114.json)。本轮未启动 IDE/CUA/浏览器，没有修改参考安装、root 生产文件或用户已有项目。

## 实现范围

新增 `plugins/frontend`、三个独立脚本及 `tests/frontend`。插件正常依赖 `com.intellij.modules.lsp`，注册公开 `com.intellij.platform.lsp.integrationProvider`，使用原生 `ProjectWideLspClientDescriptor`。没有 Ultimate alias、许可开关或 trust 绕过。

M0 默认关闭。只有五项显式属性匹配编译进插件的 owned fixture parent、随机 nonce 和固定工具 receipt 时才有资格请求 descriptor；非 fixture 文件先由纯内存条件拒绝，之后才检查正常 `TrustedProjects`。文件打开不下载工具、不读取磁盘、不启动子进程。完整 marker、receipt、payload 集合及逐文件 hash 认证只在 native API 的 worker `createCommandLine` 中进行；误在 Swing EDT 调用会直接拒绝。

`createInitializationOptions` 只组合不可变路径，避免依赖原生回调先后顺序。子进程用直接 argv、私有 HOME/temp/cache/log、固定 Node 与 TypeScript SDK，不继承 Git/npm/服务 tokens 或 Node 注入选项。它不删除、更改或接管用户在其他开发流程中选择的认证。

## 官方下载、闭包与声明

固定 Node `24.22.3` 的 Mac arm64 / Windows x64、TypeScript Language Server `6.1.0`、经典 TypeScript `6.0.3`。实际下载均为官方 HTTPS URL，所有 archive 验证精确 size + SHA-256；23 个 npm archive 另验 SHA-512 SRI。下载器禁止自动 redirect，任何未审查路线失败关闭，不打印 token/signed query。

TLS 发布 CLI 是 bundle：npm runtime dependencies 为空不代表没有内嵌依赖。认证 source map 的 236 个 source 指向 21 个精确 npm package/version，已全部纳入 lock；另外取得它们的官方原包，认证后保留完整 legal 文本，不安装或执行这些包。Node aggregate LICENSE、TLS 原 LICENSE、TypeScript LICENSE/ThirdPartyNoticeText 和 21 份原始 dependency license 均逐字节保留。

总计25个锁定 archive（两架构合计）；单平台24个 archive、191个固定 payload、25份原始 legal 文件。`tools.lock.json` 包括原 URL/manifest、SRI、SHA、size、每个解出文件摘要及 source-map/notice 闭包。cache receipt 无法通过同时改文件与自身 hash 重新授权新字节；编译插件中另包含相同的完整 expected payload manifest。没有调用 npm，没有执行 lifecycle/install/build scripts，也没有在 app bundle 写 cache。Node 发行包中的 npm 不使用、不复制。

实际包脚本验证采用显式 CLI，普通构建器和协议 probe 均离线：

```sh
python3 scripts/provision_frontend_tools.py --target macos-arm64
python3 scripts/frontend_protocol_probe.py --receipt /absolute/authenticated/frontend-tools.json
python3 scripts/build_frontend_plugin.py --sdk /absolute/authenticated/PC-SDK --test --worker-fixture /absolute/generated/owned-fixture
```

Python 需3.10+；本次实际使用3.14.3。以上命令不启动 IDE。未来原生窗口必须继续使用正常 trusted fixture 与隔离 profile，不在本轮执行。

## 已观察的验证

| 验证 | 实际结果与边界 |
|---|---|
| 全量 Python 检查 | 99 run / 99 pass / 0 skip；包含15项新增边界/篡改/闭包/协议 harness 回归 |
| hello-python fixture | 9 run / 9 pass / 0 skip |
| 实际 SDK 编译 | Mac PC261 SDK / JBR javac `--release21`，7 classes；不是 IDE 启动 |
| 实际 IntelliJ archive reader | HashMapZipFile 与 JDK reader 对比全部13个 JAR payload，关闭成功 |
| 纯 Java fixture scope | 42 checks，覆盖默认 off、非 fixture、路径越界、Python文件、错误 nonce/hash，以及 POSIX/Windows 形状与 Unicode 字符串；不是 Windows运行 |
| worker helper | 真实191文件工具 cache 全部认证、错误 activation receipt 拒绝、credential隔离；未启动 Node 或 IDE |
| 真实 Mac Node/TLS | Node `v24.22.3`、CLI `6.1.0`、server notification 确认 TS `6.0.3` / `user-setting` |

最终插件 JAR SHA-256：`96cf635db5381148001a5f21f19a20409095e3c32172dccd62d0e123621bbaff`。它位于工作树自有 `.tools/frontend-plugin`，没有复制进 app 或安装插件目录。

真实 stdio probe 使用新建自有 fixture，磁盘 `main.ts/main.js` 仍为 disk-only 内容，另发送不同的未保存 overlay。实际通过9项协议/文件控制：

1. `initialize` 协商 incremental sync 与 UTF-16。
2. 未保存 TS overlay 产生真实2322类型诊断。
3. 真实 property completion 返回 `total`。
4. emoji 后的 UTF-16 `(line1, character39)` 定义请求跨文件解析到 `quote.ts`。
5. 同行 emoji 后的增量位置把数字改为字符串，实际产生2345参数诊断。
6. 修复 overlay 后2322/2345消失；6133 unused-symbol hints 仍记录，没有隐藏告警。
7. 未保存 JavaScript overlay 获得 `id/note` 补全与 `receipt.js` 定义。
8. 四个磁盘源码摘要未变。
9. 退出后全部固定工具 payload、receipt 及磁盘源码再次认证未变。

最终自有 TLS/tsserver PIDs 为 `78102/78105/78106`。正常 `shutdown/exit`，exit0，未发送强制终止信号，live POSIX process group 无残留；这里的观察明确不把 transient zombie 视为正在运行的进程。该结果属于 Python 协议 harness 管理的进程，不是原生 IntelliJ client 的项目关闭证明。

Windows Node 原 archive 和191个解出 payload 均认证通过，包含原始25份 legal 文件；**没有执行 Windows Node/Java，没有 Windows SDK编译/IDE/安装验收**。

## 尚未验证

PC261 正常 module/EP/service 激活、原生 stdio 接线、实际 completion/diagnostic/navigation UI、native client 的取消/项目关闭与进程所有权仍须在 root 空闲窗口后验证。当前没有 HTML/CSS、模板、DAP/browser、生产 packaging 或 installer 功能。编译、worker 与独立服务器协议不能称为 Native UI 或完整 PyCharm 1:1 验收。

后续 M0 native gate 的五项 activation 属性与用途见 [插件说明](../../plugins/frontend/README.md)。本轮不会启动应用，不改变 dev2 发布/录制，不 push/merge/publish。
