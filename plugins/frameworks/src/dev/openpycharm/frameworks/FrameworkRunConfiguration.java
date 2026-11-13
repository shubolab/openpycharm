package dev.openpycharm.frameworks;

import com.intellij.execution.configurations.ConfigurationFactory;
import com.intellij.openapi.module.Module;
import com.intellij.openapi.module.ModuleManager;
import com.intellij.openapi.project.Project;
import com.jetbrains.python.run.PythonRunConfiguration;

/** Uses PythonCore's editor, persistence, command line state and debugger unchanged. */
public final class FrameworkRunConfiguration extends PythonRunConfiguration {
  private final FrameworkKind framework;

  public FrameworkRunConfiguration(Project project, ConfigurationFactory factory, FrameworkKind framework) {
    super(project, factory);
    this.framework = framework;
    setModuleMode(framework.moduleMode());
    setScriptName(framework.scriptName(project.getBasePath()));
    setScriptParameters(FrameworkKind.encodeArguments(framework.arguments()));
    if (project.getBasePath() != null) setWorkingDirectory(project.getBasePath());
    setUseModuleSdk(true);
    // The Python superclass may pick an arbitrary first module. A fresh
    // framework template can infer only a single unambiguous module.
    Module[] modules = ModuleManager.getInstance(project).getModules();
    getConfigurationModule().setModule(modules.length == 1 ? modules[0] : null);
  }

  /** Templates may have been created before project modules finished loading. */
  public void associateSingleModuleIfNeeded() {
    String moduleName = getConfigurationModule().getModuleName();
    if (!isUseModuleSdk() || getModule() != null || moduleName != null && !moduleName.isBlank()) return;
    // A multi-module project must let the user explicitly choose its module/SDK.
    Module[] modules = ModuleManager.getInstance(getProject()).getModules();
    if (modules.length == 1) getConfigurationModule().setModule(modules[0]);
  }

  public FrameworkKind framework() { return framework; }
}
