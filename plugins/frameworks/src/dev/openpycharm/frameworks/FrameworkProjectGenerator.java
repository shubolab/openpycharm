package dev.openpycharm.frameworks;

import com.jetbrains.python.newProjectWizard.PyV3ProjectBaseGenerator;
import com.jetbrains.python.newProjectWizard.PyV3BaseProjectSettings;
import com.jetbrains.python.parser.icons.PythonParserIcons;
import com.intellij.openapi.module.Module;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.vfs.VirtualFile;
import javax.swing.Icon;

public abstract class FrameworkProjectGenerator extends PyV3ProjectBaseGenerator<FrameworkProjectSettings> {
  private final FrameworkKind framework;
  private final FrameworkProjectSettings settings;

  protected FrameworkProjectGenerator(FrameworkKind framework) {
    this(framework, new FrameworkProjectSettings(framework));
  }

  private FrameworkProjectGenerator(FrameworkKind framework, FrameworkProjectSettings settings) {
    super(settings, new FrameworkProjectUi(), framework.displayName() + "Project", false);
    this.framework = framework;
    this.settings = settings;
  }
  @Override public String getName() { return framework.displayName(); }
  @Override public Icon getLogo() { return PythonParserIcons.PythonFile; }
  public final FrameworkProjectSettings projectSettings() { return settings; }

  @Override public void generateProject(Project project, VirtualFile baseDir, PyV3BaseProjectSettings baseSettings, Module module) {
    settings.captureInstallChoice(module);
    super.generateProject(project, baseDir, snapshotBaseSettings(baseSettings), module);
  }

  static PyV3BaseProjectSettings snapshotBaseSettings(PyV3BaseProjectSettings selected) {
    PyV3BaseProjectSettings snapshot = new PyV3BaseProjectSettings(selected.getCreateGitRepository());
    snapshot.setSdkCreator(selected.getSdkCreator());
    return snapshot;
  }
}
