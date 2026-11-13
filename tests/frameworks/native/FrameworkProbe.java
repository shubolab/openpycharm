package dev.openpycharm.frameworks.probe;

import com.google.gson.GsonBuilder;
import com.intellij.execution.configurations.ConfigurationFactory;
import com.intellij.execution.configurations.ConfigurationType;
import com.intellij.execution.configurations.ConfigurationTypeUtil;
import com.intellij.execution.executors.DefaultDebugExecutor;
import com.intellij.execution.executors.DefaultRunExecutor;
import com.intellij.execution.runners.ExecutionEnvironmentBuilder;
import com.intellij.execution.runners.ProgramRunner;
import com.intellij.ide.AppLifecycleListener;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.application.ex.ApplicationEx;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.project.ProjectManager;
import com.intellij.openapi.util.Disposer;
import com.intellij.util.concurrency.AppExecutorUtil;
import com.jetbrains.python.run.PythonScriptCommandLineState;
import dev.openpycharm.frameworks.*;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.jdom.Element;

/** Test-only app probe. Creates transient default-project configurations, never runs user code. */
public final class FrameworkProbe implements AppLifecycleListener {
  private final AtomicBoolean requested = new AtomicBoolean();

  @Override public void appStarted() { request(); }
  @Override public void welcomeScreenDisplayed() { request(); }

  private void request() {
    String destination = System.getProperty("openpycharm.framework.probe.report");
    String boundary = System.getProperty("openpycharm.framework.probe.output.root");
    if (destination == null || boundary == null || !requested.compareAndSet(false, true)) return;
    Path report = Path.of(destination).toAbsolutePath().normalize();
    if (!report.startsWith(Path.of(boundary).toAbsolutePath().normalize())) return;
    ApplicationManager.getApplication().invokeLater(() -> {
      Map<String, Object> result = new LinkedHashMap<>();
      result.put("invocationId", System.getProperty("openpycharm.framework.probe.invocation.id"));
      result.put("scope", "Native EP registration, Python runner/state/editor and persistence; no process execution");
      result.put("userCodeExecuted", false);
      try {
        Project project = ProjectManager.getInstance().getDefaultProject();
        List<Object> configurations = new ArrayList<>();
        configurations.add(inspect(project, DjangoConfigurationType.class));
        configurations.add(inspect(project, FlaskConfigurationType.class));
        configurations.add(inspect(project, FastApiConfigurationType.class));
        result.put("configurations", configurations);
        result.put("status", "pass");
      } catch (Throwable error) {
        result.put("status", "fail");
        result.put("failure", error.toString());
        result.put("stack", Arrays.stream(error.getStackTrace()).limit(15).map(Object::toString).toList());
      }
      String json = new GsonBuilder().setPrettyPrinting().create().toJson(result);
      // Filesystem output runs on a pooled thread, never the EDT callback.
      AppExecutorUtil.getAppExecutorService().execute(() -> {
        try {
          Files.createDirectories(report.getParent());
          Path temporary = Files.createTempFile(report.getParent(), ".framework-probe-", ".json");
          Files.writeString(temporary, json);
          Files.move(temporary, report, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
          // Ask the owned IDE to close normally first. Sending SIGTERM to its
          // whole session would interrupt SDK helpers before Java cancels them.
          ApplicationManager.getApplication().invokeLater(() ->
              ((ApplicationEx)ApplicationManager.getApplication()).exit(true, true));
        } catch (Exception ignored) { }
      });
    });
  }

  private static Object inspect(Project project, Class<? extends ConfigurationType> typeClass) throws Exception {
    ConfigurationType type = ConfigurationTypeUtil.findConfigurationType(typeClass);
    require(type != null, "Configuration type was not registered: " + typeClass);
    ConfigurationFactory factory = type.getConfigurationFactories()[0];
    require(factory.isApplicable(project), "Framework factory is hidden by applicability checks");
    FrameworkRunConfiguration configuration = (FrameworkRunConfiguration)factory.createTemplateConfiguration(project);
    require(configuration.framework().id().equals(type.getId()), "Framework/type identity changed");
    Map<String, Object> result = new LinkedHashMap<>();
    result.put("typeId", type.getId());
    result.put("typeClass", type.getClass().getName());
    result.put("factoryApplicable", factory.isApplicable(project));
    result.put("framework", configuration.framework().name());
    result.put("defaultModuleMode", configuration.isModuleMode());
    result.put("defaultScriptName", configuration.getScriptName());
    result.put("defaultParameters", configuration.getScriptParameters());
    configuration.setName("Transient framework verification");
    configuration.setSdkHome(System.getProperty("openpycharm.framework.probe.python"));
    configuration.setUseModuleSdk(false);
    configuration.setWorkingDirectory(System.getProperty("openpycharm.framework.probe.working.dir"));
    configuration.setPassParentEnvs(false);
    Map<String, String> environment = new LinkedHashMap<>(configuration.getEnvs());
    environment.put("OPENPYCHARM_FRAMEWORK_TEST", "中文 space;$(literal)");
    configuration.setEnvs(environment);
    List<String> arguments = List.of("space value", "a\"b", "semi;colon", "$(literal)", "中文");
    configuration.setScriptParameters(FrameworkKind.encodeArguments(arguments));
    Element serialized = new Element("configuration");
    configuration.writeExternal(serialized);
    FrameworkRunConfiguration restored = (FrameworkRunConfiguration)factory.createTemplateConfiguration(project);
    restored.readExternal(serialized);
    require(Objects.equals(restored.getSdkHome(), configuration.getSdkHome()), "Selected interpreter path did not persist");
    require(!restored.isUseModuleSdk(), "Explicit interpreter selection was lost");
    require(Objects.equals(restored.getWorkingDirectory(), configuration.getWorkingDirectory()), "Working directory did not persist");
    require(Objects.equals(restored.getEnvs(), environment), "Environment did not persist");
    require(!restored.isPassParentEnvs(), "Parent environment choice did not persist");
    require(Objects.equals(restored.getScriptParameters(), configuration.getScriptParameters()), "Arguments did not persist");
    require(restored.isModuleMode() == configuration.isModuleMode(), "Module/script selection did not persist");
    FrameworkRunConfiguration cloned = (FrameworkRunConfiguration)factory.createConfiguration("Cloned explicit interpreter", restored);
    require(!cloned.isUseModuleSdk() && Objects.equals(cloned.getSdkHome(), restored.getSdkHome()),
        "Factory clone changed the user's explicit interpreter selection");
    require(Objects.equals(cloned.getEnvs(), restored.getEnvs()) && Objects.equals(cloned.getWorkingDirectory(), restored.getWorkingDirectory()),
        "Factory clone changed environment or working directory");
    FrameworkRunConfiguration deferred = (FrameworkRunConfiguration)factory.createTemplateConfiguration(project);
    deferred.getConfigurationModule().setModuleName("explicit-module-not-loaded-yet");
    FrameworkRunConfiguration deferredClone = (FrameworkRunConfiguration)factory.createConfiguration("Cloned deferred module", deferred);
    require("explicit-module-not-loaded-yet".equals(deferredClone.getConfigurationModule().getModuleName()),
        "Factory clone changed a serialized module choice that has not loaded yet");
    ProgramRunner<?> run = ProgramRunner.getRunner(DefaultRunExecutor.EXECUTOR_ID, restored);
    ProgramRunner<?> debug = ProgramRunner.getRunner(DefaultDebugExecutor.EXECUTOR_ID, restored);
    require(run != null && run.getRunnerId().equals("PythonRunner"), "Native Python Run runner not selected");
    require(debug != null && debug.getRunnerId().equals("PyDebugRunner"), "Native Python Debug runner not selected");
    var executor = DefaultRunExecutor.getRunExecutorInstance();
    var execution = ExecutionEnvironmentBuilder.create(project, executor, restored).build();
    var state = restored.getState(executor, execution);
    require(state instanceof PythonScriptCommandLineState, "Native Python command state not retained");
    var editor = restored.getConfigurationEditor();
    result.put("nativeEditor", editor.getClass().getName());
    Disposer.dispose(editor);
    result.put("nativeRunRunner", run.getRunnerId());
    result.put("nativeDebugRunner", debug.getRunnerId());
    result.put("nativeState", state.getClass().getName());
    result.put("sdkHomePersisted", restored.getSdkHome());
    result.put("workingDirectoryPersisted", restored.getWorkingDirectory());
    result.put("environmentPersisted", restored.getEnvs());
    result.put("parentEnvironmentPersisted", restored.isPassParentEnvs());
    result.put("argumentPersistence", "pass");
    result.put("factoryClonePreservesSelection", true);
    result.put("status", "pass");
    return result;
  }

  private static void require(boolean condition, String message) {
    if (!condition) throw new IllegalStateException(message);
  }
}
