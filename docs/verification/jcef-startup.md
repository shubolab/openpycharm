# JCEF 冷启动服务初始化修复

## 已观察的失败

根任务的已安装 `26da493` 候选在恢复 README 的 Markdown 预览时记录 SEVERE：`JBCefApp$Holder.<clinit>` 经 JCEF 代理设置首次取得 `HttpConfigurable`，其初始化再请求 `ProxyMigrationService`。原日志 3408–3519 行已保留为工作树 `.tools/markdown-startup-audit/installed-cold-markdown-severe.log`；这个候选仍是被拒绝的发布候选。

固定公开源码与栈一致：

- [JBCefApp.java](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/ui.jcef/jcef/JBCefApp.java) 的 Holder 字段初始化直接构造 JCEF。
- [HttpConfigurable.java](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/platform-api/src/com/intellij/util/net/HttpConfigurable.java) 的组件初始化请求迁移服务；[迁移服务接口](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/platform-api/src/com/intellij/util/net/internal/ProxyMigrationService.kt) 是普通 application service。
- [ComponentManagerImpl.kt](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/platform/service-container/src/com/intellij/serviceContainer/ComponentManagerImpl.kt) 对未创建服务检查调用栈中的类初始化；预热成功不能证明冷路径正确。

## 有界源码回放

补丁只重编译 `JBCefApp` 及其 6 个嵌套类。Holder 冷加载不再运行构造；首次构造移入 `getInstance()`，全部调用使用原有 `Holder.class` monitor，避免 test-mode 重入赋值在外层构造完成前被其他线程读取。首次意外失败清空中途实例并缓存原始 cause；后续访问仍失败，不自动重试。普通 null 结果缓存和现有 test-mode retry 分支保留。

这是有意的异常表现边界：离开 JVM 类初始化后，不再产生该类的 `ExceptionInInitializerError`/`NoClassDefFoundError` 包装，改为再次抛出原始 cause；不能声称异常类型完全兼容。warm 调用也会取得同一个短 monitor。构造函数中的两处既有取消包裹不变，没有增加整段 non-cancellable 包裹；原类初始化栈对冷 service 创建的隐式保护不再适用，未复现的取消时序差异保持为限制，控制用例只证明显式取消 cause 不被掩盖。

没有修改 Markdown、代理、凭据、服务注册、日志级别、用户配置或缓存策略，也没有添加 EDT 文件/进程操作。原 SDK 与参考安装保持只读。

## 编译与控制证据

Mac/Windows pin 绑定同一公开源码提交、源/补丁摘要及原始 JAR 摘要。回放器验证 7 个 class 和所有非替换 entry；`repairs.apply` 在两平台 CI 的组装阶段自动运行：实际 patched Holder 冷加载、原始 SDK 负对照、源码派生的并发/null/test-mode/reentry/exception 控制，以及不安全 fast-path 的负对照。控制 helper 位于 `product/patches`，纳入完整来源闭包；class SHA 和控制收据进入产品及安装器 provenance。

当前离线控制通过 68 项，原始 Holder 负对照与不安全发布负对照都按预期失败。它们不启动 IDE 或原生 CEF。真实冷 Markdown panel/DOM 和最终已安装 README 恢复仍是独立运行门槛；本页在实际运行完成前不宣称候选可发布。
