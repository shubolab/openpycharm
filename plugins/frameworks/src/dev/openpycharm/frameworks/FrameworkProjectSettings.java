package dev.openpycharm.frameworks;

import com.intellij.execution.ExecutionException;
import com.intellij.execution.RunManager;
import com.intellij.execution.configurations.ConfigurationType;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.application.ModalityState;
import com.intellij.openapi.application.WriteAction;
import com.intellij.openapi.module.Module;
import com.intellij.openapi.projectRoots.Sdk;
import com.intellij.openapi.util.Key;
import com.intellij.openapi.vfs.VirtualFile;
import com.jetbrains.python.Result;
import com.jetbrains.python.errorProcessing.MessageError;
import com.jetbrains.python.errorProcessing.PyError;
import com.jetbrains.python.newProjectWizard.PyV3ProjectTypeSpecificSettings;
import com.jetbrains.python.sdk.PythonSdkUtil;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CancellationException;
import kotlin.Unit;
import kotlin.coroutines.Continuation;
import kotlinx.coroutines.BuildersKt;
import kotlinx.coroutines.Dispatchers;
import kotlinx.coroutines.JobKt;

/** Called by the native Python wizard after its SDK/venv has been configured. */
public final class FrameworkProjectSettings implements PyV3ProjectTypeSpecificSettings {
  private static final Key<Boolean> INSTALL_CHOICE = Key.create("dev.openpycharm.frameworks.installChoice");
  private final FrameworkKind framework;
  private boolean installDependencies;

  public FrameworkProjectSettings(FrameworkKind framework) { this.framework = framework; }
  public FrameworkKind framework() { return framework; }
  public boolean installDependencies() { return installDependencies; }
  public void setInstallDependencies(boolean installDependencies) { this.installDependencies = installDependencies; }

  // The EP/settings object is shared. Capture before the native generator starts
  // asynchronous SDK creation so another wizard cannot change this project's choice.
  void captureInstallChoice(Module module) { module.putUserData(INSTALL_CHOICE, installDependencies); }
  boolean consumeInstallChoice(Module module) {
    Boolean captured = module.getUserData(INSTALL_CHOICE);
    module.putUserData(INSTALL_CHOICE, null);
    return captured == null ? installDependencies : captured;
  }

  @Override public Object generateProject(Module module, VirtualFile baseDir, Sdk sdk,
      Continuation<? super Result<Unit, ? extends PyError>> continuation) {
    final boolean requestedInstall = consumeInstallChoice(module);
    return BuildersKt.withContext(Dispatchers.getIO(), (scope, resumed) -> {
      Runnable check = () -> {
        JobKt.ensureActive(scope.getCoroutineContext());
        if (module.isDisposed() || module.getProject().isDisposed()) throw new CancellationException("The project was closed");
      };
      check.run();
      try {
        if (PythonSdkUtil.isRemote(sdk)) return new Result.Failure<PyError>(new MessageError("Framework creation currently supports a local Python interpreter or virtual environment"));
        if (sdk.getHomePath() == null || !Files.isRegularFile(Path.of(sdk.getHomePath()))) {
          return new Result.Failure<PyError>(new MessageError("The selected Python interpreter executable is unavailable"));
        }
        Path directory = Path.of(baseDir.getPath());
        FrameworkProjectFiles.write(directory, framework, check);
        check.run();
        if (requestedInstall) FrameworkDependencyInstaller.install(sdk, directory, check);
        check.run();
        baseDir.refresh(false, true);
        check.run();
        ApplicationManager.getApplication().invokeAndWait(() -> {
          check.run();
          WriteAction.run(() -> {
            check.run();
            createConfiguration(module, baseDir);
          });
        }, ModalityState.any());
        return new Result.Success<Unit>(Unit.INSTANCE);
      } catch (IOException | ExecutionException error) {
        return new Result.Failure<PyError>(new MessageError(error.getMessage() == null ? error.toString() : error.getMessage()));
      }
    }, continuation);
  }

  private void createConfiguration(Module module, VirtualFile baseDir) {
    RunManager manager = RunManager.getInstance(module.getProject());
    Class<? extends ConfigurationType> typeClass = switch (framework) {
      case DJANGO -> DjangoConfigurationType.class;
      case FLASK -> FlaskConfigurationType.class;
      case FASTAPI -> FastApiConfigurationType.class;
    };
    var settings = manager.createConfiguration(framework.displayName(), typeClass);
    FrameworkRunConfiguration configuration = (FrameworkRunConfiguration)settings.getConfiguration();
    configuration.getConfigurationModule().setModule(module);
    configuration.setUseModuleSdk(true);
    configuration.setWorkingDirectory(baseDir.getPath());
    configuration.setModuleMode(framework.moduleMode());
    configuration.setScriptName(framework.scriptName(baseDir.getPath()));
    configuration.setScriptParameters(FrameworkKind.encodeArguments(framework.arguments()));
    configuration.setName(manager.suggestUniqueName(framework.displayName(), configuration.getType()));
    manager.addConfiguration(settings);
    manager.setSelectedConfiguration(settings);
  }
}
