# 框架配置 API 与验证范围

固定基础为开源 PyCharm `PC-261.26222.68`，上游提交 `456919a9624bae72ac12efafc35d2b916cb0c5c5`。以下签名由固定 SDK 的 class 文件和该提交的公开源码交叉核对；实际 Java 编译使用 SDK 自带 `javac 25.0.3 --release 21`，无需下载 Gradle 或复制 SDK。

## 已核对的原生配置 API

主要类位于 `plugins/python-ce/lib/modules/intellij.python.community.impl.jar`。

```java
// com.jetbrains.python.run.PythonRunConfiguration
protected PythonRunConfiguration(Project project, ConfigurationFactory factory);
public RunProfileState getState(Executor executor, ExecutionEnvironment env) throws ExecutionException;
public void setScriptName(String scriptName);
public void setScriptParameters(String scriptParameters);
public void setModuleMode(boolean moduleMode);

// com.jetbrains.python.run.AbstractPythonRunConfiguration
public void setSdkHome(String sdkHome);
public void setSdk(Sdk sdk);
public void setUseModuleSdk(boolean useModuleSdk);
public void setWorkingDirectory(String workingDirectory);
public final SettingsEditor<T> getConfigurationEditor();
public static void copyParams(AbstractPythonRunConfigurationParams source,
                              AbstractPythonRunConfigurationParams target);

// com.intellij.execution.configuration.AbstractRunConfiguration
public void setEnvs(Map<String, String> envs);
public void setPassParentEnvs(boolean passParentEnvs);

// com.jetbrains.python.run.PythonConfigurationFactoryBase
protected PythonConfigurationFactoryBase(ConfigurationType type);
public boolean isApplicable(Project project);
public boolean isEditableInDumbMode();

// com.intellij.execution.configurations.ConfigurationTypeBase
public ConfigurationTypeBase(String id, String displayName, String description, Icon icon);
protected final void addFactory(ConfigurationFactory factory);

// com.intellij.util.execution.ParametersListUtil
public static String join(List<? extends CharSequence> arguments);
public static List<String> parse(String parameters);
```

公开源码：

- [PythonRunConfiguration.java](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/src/com/jetbrains/python/run/PythonRunConfiguration.java)：构造函数是 `protected`，独立 Java 子类可以正常调用；`getState` 返回 `PythonScriptCommandLineState`。没有使用标记为 TestOnly 的配置工厂捷径。
- [AbstractPythonRunConfiguration.java](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/src/com/jetbrains/python/run/AbstractPythonRunConfiguration.java)：保存/恢复解释器、模块、工作目录、环境等；SDK 选择遵循模块或明确指定的 SDK。
- [PythonRunner.kt](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/src/com/jetbrains/python/run/PythonRunner.kt)：Run executor 接受 `AbstractPythonRunConfiguration`，Python command-line state 的执行安排在后台。
- [PyDebugRunner.java](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/src/com/jetbrains/python/debugger/PyDebugRunner.java)：Debug executor 接受没有主动禁用调试的 `AbstractPythonRunConfiguration`。
- [PythonScriptCommandLineState.java](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/src/com/jetbrains/python/run/PythonScriptCommandLineState.java)：区分模块/脚本，通过原生参数解析、宏展开及命令行对象构建执行参数。

## 这个切片的实现

独立插件 ID 为 `dev.openpycharm.frameworks`。三个 `configurationType` 是 `OpenPyCharmDjango`、`OpenPyCharmFlask`、`OpenPyCharmFastAPI`，各自有工厂，共用 `FrameworkRunConfiguration extends PythonRunConfiguration`。构造只设置默认入口和参数，没有替换原生编辑器、持久化、运行状态、Run runner 或 Debug runner。

参数由 `List<String>` 构建，用 `ParametersListUtil.join` 保存；没有 shell 插值、`sh -c`、PowerShell 命令拼接或从 PATH 偷换 Python。原生编辑器仍保留 PythonCore 的参数宏语义。多模块项目不替用户挑选任意模块；单模块项目默认关联其模块 SDK。模板可能早于模块创建，工厂在创建真实配置时只补上尚未选择的唯一模块；明确的解释器和尚未加载的序列化模块名称都继续保留。

构建命令：

```sh
python3 scripts/build_framework_plugin.py --sdk /absolute/path/to/authenticated/PyCharm.app --test
```

构建目录与来源清单位于本工作树 `.tools/framework-plugin`，只读使用传入 SDK。编译来源、SDK receipt、编译器、插件摘要都有构建清单。生产 JAR 包含三种配置类型和许可证，不包含测试探针。

## 已观察到的证据与尚未通过项

- 实际 SDK 编译与 SDK JVM 参数测试通过：参数中的空格、中文、引号、空参数、反斜线和 shell 字符保持参数边界；禁止 NUL/换行。
- 三个真实框架的本机 HTTP 测试通过：从编译后的 Java 默认模型取参数，选用独立 venv、项目工作目录与唯一环境标记，收到预期 JSON，再终止本次拥有的进程。
- 实际原生 API 探针已经观察到三个 EP，使用 `PythonConfigurationFragmentedEditor`、`PythonRunner`、`PyDebugRunner` 和 `PythonScriptCommandLineState`，并通过 SDK 路径、环境、父环境选择、工作目录、参数及模式的 XML 往返。
- **安全修复后的原生 API 探针通过。** 首次无参数启动自动创建了上游欢迎工作区；隔离 JVM `user.home` 后未再触及共享工作区，但正常退出时欢迎 SDK skeleton 取消仍记录 SEVERE。三个失败记录继续保留。主线精确移除自动创建该欢迎项目的 provider 后，第四次检查在普通欢迎页通过：三个工厂可用，原生配置各项往返正确，通过原生 API 退出（code 0），日志没有 ERROR/SEVERE。没有过滤前三次的错误。
- 真正点击 IDE Run/Debug、断点/步进/变量/Stop、安装包内集成和 Windows 桌面行为尚未由这一切片证明；框架模板语言/ORM 智能分析、自动重载和完整向导桌面验收也尚未完成。

工作树内原始证据位于 `.tools/framework-build-final.json`、`.tools/framework-server-final/framework-servers.json`、`.state/framework-native-sealed` 和保留的前三次失败目录；精简记录见 [framework-core-20261114.json](framework-core-20261114.json)。最终原生检查也验证了工厂克隆保留解释器及未加载模块的选择。这些是可清理的本地测试路径；对外报告应保留精简来源与摘要，不把历史路径当作永远存在的文件。

## 新建项目向导

固定 PythonCore 已提供原生解释器/venv UI 和 SDK 创建生命周期：

```java
// com.jetbrains.python.newProjectWizard.PyV3ProjectBaseGenerator<T>
public PyV3ProjectBaseGenerator(T settings, PyV3ProjectTypeSpecificUI<T> ui,
                               String defaultProjectName, boolean supportsNotEmptyModuleStructure);
public void generateProject(Project project, VirtualFile baseDir,
                            PyV3BaseProjectSettings settings, Module module);

// com.jetbrains.python.newProjectWizard.PyV3ProjectTypeSpecificSettings
Object generateProject(Module module, VirtualFile baseDir, Sdk sdk,
    Continuation<? super com.jetbrains.python.Result<Unit, ? extends PyError>> continuation);
```

注册使用 `com.intellij.directoryProjectGenerator`；`AbstractNewProjectStep.EP_NAME` 拥有该 EP。`PyV3NewProjectStepAction` 将该基类归入原生 Python 向导。基类先在 SDK 配置锁下完成解释器/venv 配置，再调用框架设置的 suspend 方法；不需要再实现一套解释器选择器。

Java 使用现有 Kotlin/coroutines ABI 实现回调：`BuildersKt.withContext(Dispatchers.getIO(), ..., continuation)`，同步返回 `new com.jetbrains.python.Result.Success<Unit>(Unit.INSTANCE)`，由库管理挂起/恢复。三个独立 `directoryProjectGenerator` 现已实现并通过固定 SDK 编译。`FrameworkProjectUi.configureUpperPanel` 在原生 `PyV3GeneratorPeer` 的 Python UI 中添加默认关闭的依赖安装选项，没有另外实现解释器选择器。

`FrameworkProjectSettings` 在 IO 回调中预检文件冲突、生成独立模板，并按用户选择安装所选 SDK 的固定依赖，然后在 EDT 的模型写操作中创建真实运行配置。原生基类会先异步配置 SDK，因此生成器在同步入口按模块保存依赖安装选择，并复制当次的 SDK creator 和创建 Git 仓库选项；回调消费安装快照。后续向导不会改变已经提交项目的这些选择。

`FrameworkDependencyInstaller` 使用 `GeneralCommandLine` 和 SDK 的 virtualenv 环境补丁，参数从列表传入；后台等待轮询协程取消，超时或取消时终止本次根进程并等待退出。它保留已观察到的后代 `ProcessHandle`，即使根进程正常/失败退出，也回收这些后代。没有分离任务后提前返回成功。**当前跨平台实现尚无原生 Job Object/进程组容器，无法证明根进程在观察前立即创建并遗留的孤儿进程也被回收。** 这是进程生命周期验收的剩余边界。`supportsNotEmptyModuleStructure=false`，尚不支持 uv/Hatch/Poetry 生成的模块结构。

本切片在 macOS arm64 上观察到：

- 固定 SDK 的 Java 编译、原生参数编码、254 项模板写入检查和 16 项并发请求快照检查通过；工作树 Python 单元测试 52 项、hello-python 示例 9 项通过。
- 实际 OpenPyCharm 进程加载三个注册的 `PyV3GeneratorPeer`，返回原生 `DialogPanel`；默认关闭的复选框能正确更新对应设置。
- 两个全新真实 venv 由测试启动器创建。受控 `PySdkCreator` 将其交给原生 `PyV3BaseProjectSettings.generateAndGetSdk`，观察到模块绑定了所选 SDK，再调用真实框架生成回调。这里验证了选择已有 venv 的原生 SDK/模块阶段，**没有证明用户操作解释器 UI 或原生新建 venv 按钮的流程**。
- 三个选择安装的项目实际安装了 Django 5.2.8、Flask 3.1.2、FastAPI 0.121.0、Uvicorn 0.38.0；第四个项目关闭安装后，其独立 venv 中四个包均不存在。项目文件、模块 SDK、工作目录和原生运行配置都正确；重复生成拒绝覆盖文件且不添加第二个运行配置。
- 取消、非零退出、超时，以及根进程正常/失败退出后已观察到的后代清理均通过真实进程检查。最终原生进程通过 API 正常退出（code 0），日志 ERROR/SEVERE 为 0。首次测试探针处置项目时遗漏 WriteAction 的失败记录保留，没有过滤该错误。
- 从三个刚生成的项目使用所选 venv 和编译后默认参数启动真实 HTTP 服务，三者均返回 200 和对应唯一环境标记；随后仅停止本次进程会话。

原生宿主是预览 app `0.1.0-dev.1`、源码 `9c5343e9b30ce5254fdd28383e4e28776c1507fa`，框架插件为独立加载的 `0.1.0-dev.2`，没有宣称已集成发布安装包。精简证据见 [framework-generators-20261114.json](framework-generators-20261114.json)；原始记录在 `.state/framework-generators-sealed` 与 `.tools/framework-generator-servers-sealed`。真正点击 New Project/Create/Cancel、原生 Run/Debug 的框架断点、安装包集成、Windows/Linux 仍单列验收。

可复现检查：

```sh
python3 scripts/framework_probe.py --generators --timeout 180 \
  --app /absolute/path/to/OpenPyCharm.app \
  --sdk /absolute/path/to/authenticated/PyCharm.app \
  --python /absolute/path/to/python3 \
  --profile .state/new-disposable-generator-check
python3 scripts/framework_server_smoke.py \
  --sdk /absolute/path/to/authenticated/PyCharm.app \
  --python .state/new-disposable-generator-check/selected-venv/bin/python \
  --projects '.state/new-disposable-generator-check/generated projects 中文' \
  --output .tools/new-generated-server-check
```

相关源码：[PyV3ProjectBaseGenerator.kt](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/src/com/jetbrains/python/newProjectWizard/PyV3ProjectBaseGenerator.kt)、[PyV3BaseProjectSettings.kt](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/src/com/jetbrains/python/newProjectWizard/PyV3BaseProjectSettings.kt)、[PyV3ProjectTypeSpecificSettings.kt](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/src/com/jetbrains/python/newProjectWizard/PyV3ProjectTypeSpecificSettings.kt)。

## 产品集成检查

框架分支已基于原生 HTTP Client 的构建流水线集成。`package.py` 将两个独立插件放入产品 `third-party-plugins`，框架路径为 `openpycharm-frameworks/lib/frameworks.jar`。生产 JAR 的版本由产品版本参数填写；编译和 IntelliJ 实际 archive reader 校验使用经过完整收据验证的固定 OSS SDK。跨平台检查可以用 `--host-sdk` 选经过验证的本机 JBR，在 Windows SDK 的 classpath 上编译；这不能证明 Windows 运行通过。

产品 `plugins[]` 清单记录 id、名称、版本、相对目录、JAR 与摘要及完整构建收据。来源闭包包含全部 `plugins/`。安装器与启动检查复用 `verify_product_plugins`，框架与 HTTP JAR 任一字节变化均被拒绝。`framework_probe.py --packaged` 在创建配置或启动之前检查来源和两份 JAR；只注入测试监听器，要求原生 descriptor 的 bundled 标记、版本、路径、JAR 摘要及应用 home 都与产品一致。生产插件没有通过 `plugin.path` 注入。探针编译和临时文件始终位于工作树 `.tools` 或隔离 profile，不写入签名产品。

集成候选 `0.1.0-dev.2`、来源提交 `80cea80c27623d76859d14b19f35b4ca5427c52b` 已在 macOS arm64 通过实际原生 API 检查。HTTP 和框架插件均由原生产品目录加载，框架 descriptor 的 bundled 状态、路径、版本、JAR 摘要完全匹配清单；只额外注入测试监听器。三个原生 peer、四个生成项目、所选真实 venv 的依赖安装/关闭安装、原生 SDK/模块配置和运行配置，以及取消/超时/失败/已观察后代清理均通过。三个刚生成项目的真实 HTTP 路由均返回预期 200 和环境标记。

原生进程 PID 8506 正常退出（code 0），日志 ERROR/SEVERE 为 0；一个已知上游 ConfigurationScript WARN 保留。完整应用文件树在测试前后摘要相同，`codesign --verify --deep --strict` 和来源/JAR 校验在测试后仍通过。精简证据见 [framework-integration-20261114.json](framework-integration-20261114.json)。77 项 Python 控制、9 项基础示例测试、254 项模板检查和 16 项请求隔离检查通过；Windows SDK 的 classpath 编译/检查使用 macOS 宿主 JBR，不能当作 Windows 原生运行证据。

这些证据支持原生产品加载与生成器 API 集成；前面的独立加载历史记录继续单列。实际向导 Create/Cancel、框架 Run/Debug 桌面操作、Windows native CI、正式安装包及发布 GIF 仍由后续主线候选验收，瞬时未观察孤儿进程的容器边界也仍开放。

## 模板输出清理（2026-11-14）

根任务随后报告在来源 `80cea80c27623d76859d14b19f35b4ca5427c52b` 的真实桌面完成 FastAPI Create、Python 3.14 venv 创建、选择安装依赖及 Run `/` 返回 200，并发现旧生成文件将内部环境标记显示给用户。该桌面记录仍对应旧模板；上面的历史记录和响应内容没有重写。

新模板首页只返回框架名称与普通问候，例如 `{"framework":"fastapi","message":"Hello from FastAPI!"}`。生成的 Python 文件与 README 不含探针变量或内部响应字段。测试脚本对明确传入 `--projects` 的生成项目直接校验这个正常响应；只有省略该参数、使用独立测试用例时才启用环境标记控制，不修改用户生成的项目来添加测试字段。

本修复使用固定 SDK 编译后的生产模板类直接写出三个新项目，三个真实本机服务器均返回预期 Hello JSON；原有三个环境标记测试用例也分别通过。257 项模板写入/输出检查、16 项请求隔离检查和 83 项 Python 控制通过，六个测试服务器均由自己的会话清理。精简记录见 [framework-template-cleanup-20261114.json](framework-template-cleanup-20261114.json)。本修复没有启动 IDE 或操作桌面；新模板的原生 UI、调试和安装包验收仍需要重建候选后执行，不能沿用旧模板的桌面证据。
