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
- 真正点击 IDE Run/Debug、断点/步进/变量/Stop、安装包内集成和 Windows 桌面行为尚未由这一切片证明；框架语义分析、模板、ORM、自动重载和完整向导也尚未完成。

工作树内原始证据位于 `.tools/framework-build-final.json`、`.tools/framework-server-final/framework-servers.json`、`.state/framework-native-sealed` 和保留的前三次失败目录；精简记录见 [framework-core-20261114.json](framework-core-20261114.json)。最终原生检查也验证了工厂克隆保留解释器及未加载模块的选择。这些是可清理的本地测试路径；对外报告应保留精简来源与摘要，不把历史路径当作永远存在的文件。

## 新建项目向导的下一步

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

Java 可用现有 Kotlin/coroutines ABI 实现回调：`BuildersKt.withContext(Dispatchers.getIO(), ..., continuation)`，同步返回 `new com.jetbrains.python.Result.Success<Unit>(Unit.INSTANCE)`，由库管理挂起/恢复。这个 Java 桥已做固定 SDK 的编译证明，尚未实现或运行真实向导。

下一步应在该 IO 回调中验证空目录/冲突、生成独立模板、按用户选择安装所选 SDK 的依赖，再创建真实运行配置。进程等待必须轮询协程取消并回收自己启动的子进程；不能开脱离项目生命周期的后台任务后立即报告成功。`supportsNotEmptyModuleStructure` 初期应为 `false`，直到确实支持 uv/Hatch/Poetry 生成的项目结构。

相关源码：[PyV3ProjectBaseGenerator.kt](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/src/com/jetbrains/python/newProjectWizard/PyV3ProjectBaseGenerator.kt)、[PyV3BaseProjectSettings.kt](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/src/com/jetbrains/python/newProjectWizard/PyV3BaseProjectSettings.kt)、[PyV3ProjectTypeSpecificSettings.kt](https://github.com/JetBrains/intellij-community/blob/456919a9624bae72ac12efafc35d2b916cb0c5c5/python/src/com/jetbrains/python/newProjectWizard/PyV3ProjectTypeSpecificSettings.kt)。
