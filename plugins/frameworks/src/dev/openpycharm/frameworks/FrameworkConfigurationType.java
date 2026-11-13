package dev.openpycharm.frameworks;

import com.intellij.execution.configurations.ConfigurationTypeBase;
import com.intellij.execution.configurations.RunConfiguration;
import com.intellij.openapi.project.Project;
import com.jetbrains.python.parser.icons.PythonParserIcons;
import com.jetbrains.python.run.PythonConfigurationFactoryBase;

public abstract class FrameworkConfigurationType extends ConfigurationTypeBase {
  protected FrameworkConfigurationType(FrameworkKind framework) {
    super(framework.id(), framework.displayName(),
        framework.displayName() + " development server with the selected Python interpreter",
        PythonParserIcons.PythonFile);
    addFactory(new PythonConfigurationFactoryBase(this) {
      @Override public RunConfiguration createTemplateConfiguration(Project project) {
        return new FrameworkRunConfiguration(project, this, framework);
      }
      @Override public RunConfiguration createConfiguration(String name, RunConfiguration template) {
        FrameworkRunConfiguration configuration = (FrameworkRunConfiguration)super.createConfiguration(name, template);
        configuration.associateSingleModuleIfNeeded();
        return configuration;
      }
      @Override public String getId() { return framework.id(); }
    });
  }

  @Override public boolean isDumbAware() { return true; }
}
