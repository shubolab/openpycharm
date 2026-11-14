# M0 协议 harness：背压下的 deadline 与清理

源码修复固定为 `e9d4d461f3d52bbf000fd937cbb610d4625f8a61`。本次只改协议 harness 与测试，没有改 Java provider、工具 pin、生产 package、root 或参考文件，没有启动 IDE/CUA。完整原始结果见 [收据](frontend-protocol-cancellation-20261114.json)。

独立 review 在旧 HEAD `623561a` 复现了具体 P2：初始化真实自有 TLS 后 SIGSTOP 整个 owned group，向 stdin 填入65,536字节直到 EAGAIN，再调用 close。原逻辑先同步 write/flush，之后才建立 response deadline；12.004秒后仍堵在 flush。reviewer 外部结束该自有组才释放调用，而 stdin.close 的 BrokenPipeError 又跳过其他流关闭与 reader join。

修复采用与 Notebook lifecycle 相同的独立 disposal 原则。一个有界 FIFO writer 独占 stdin；绝对请求 deadline 在入队之前建立，并覆盖 write、flush、response 以及 server-request ACK。写入超时后该 transport 进入终止态，不继续复用不确定的字节流。close 的协议尝试有独立的短预算，随后直接管理自有进程；它不取得 BufferedWriter/Reader 的锁。writer 和 reader 分别在各自 finally 关闭 stdin/stdout，stderr 用独立任务关闭，各步骤错误与 join 状态都记录。共享默认8秒 cleanup预算耗尽会报告不完整，而不会以一个无限 flush 阻断生命周期。

固定源码的同一真实控制通过：SIGSTOP +65,536字节满管道，close 在约2.6秒返回，外部 watchdog 没有解围。harness 对自己的组升级 SIGTERM/SIGKILL；stdin.close **确实再次抛出 BrokenPipeError**，但三条流均关闭、writer/reader/stderrCloser 全部结束、live owned group为空。这个故障注入控制的 exit=-9 和 forced signals 是预期取消结果，不能写成正常协议退出。

正常真实 Node/TLS 的原9项 stdio 控制也通过：同一固定 Node24.22.3/TLS6.1.0/TS6.0.3，未保存 TS/JS、UTF-16、诊断/补全/定义与工具/源码不变。正常 close 为0.089秒，exit0、没有强制信号，三流与辅助线程全部完成。

全量 Python 单测102/102、无跳过；frontend focused18项。新增三项分别验证：阻塞写入不能绕过 RPC 总 deadline、server-request 回复不能另起更长预算、stdin 关闭异常不跳过其他流和线程收尾。独立真实回归入口为 `tests/frontend/protocol_backpressure_probe.py`，必须显式提供已认证的工具 receipt；普通单测不会自动下载或启动 Node。

Java插件的 sourceInputs 与原构建完全相同，原 JAR SHA `96cf635db5381148001a5f21f19a20409095e3c32172dccd62d0e123621bbaff` 再次认证一致，因此本次没有重建/更改插件。旧 M0 证据仍归属于其原 source；本页只追加 harness修复证据。

独立 bootstrap 原case窄复测仍由 root 在释放并发槽后安排。Native PC 模块/service/stdio/editor、原生项目关闭生命周期、Windows运行及生产集成均保持未验收；本修复不改变已发布 dev2。
