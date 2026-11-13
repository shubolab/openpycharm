package dev.openpycharm.frameworks.probe;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.intellij.execution.RunManager;
import com.intellij.ide.util.projectWizard.AbstractNewProjectStep;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.application.ReadAction;
import com.intellij.openapi.application.WriteAction;
import com.intellij.openapi.application.ex.ApplicationEx;
import com.intellij.openapi.module.Module;
import com.intellij.openapi.module.ModuleManager;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.project.ex.ProjectManagerEx;
import com.intellij.openapi.projectRoots.ProjectJdkTable;
import com.intellij.openapi.projectRoots.Sdk;
import com.intellij.openapi.roots.ModuleRootManager;
import com.intellij.openapi.ui.TextFieldWithBrowseButton;
import com.intellij.openapi.util.Disposer;
import com.intellij.openapi.vfs.VirtualFile;
import com.intellij.openapi.vfs.VfsUtil;
import com.intellij.platform.DirectoryProjectGenerator;
import com.intellij.util.concurrency.AppExecutorUtil;
import com.jetbrains.python.PythonModuleTypeBase;
import com.jetbrains.python.Result;
import com.jetbrains.python.errorProcessing.PyError;
import com.jetbrains.python.newProject.collector.InterpreterStatisticsInfo;
import com.jetbrains.python.newProjectWizard.PyV3BaseProjectSettings;
import com.jetbrains.python.sdk.ModuleOrProject;
import com.jetbrains.python.sdk.PythonSdkType;
import com.jetbrains.python.sdk.PythonSdkUpdater;
import com.jetbrains.python.sdk.add.v2.PySdkCreator;
import com.jetbrains.python.statistics.InterpreterCreationMode;
import com.jetbrains.python.statistics.InterpreterTarget;
import com.jetbrains.python.statistics.InterpreterType;
import dev.openpycharm.frameworks.*;
import java.awt.Component;
import java.awt.Container;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.CancellationException;
import java.util.concurrent.atomic.AtomicReference;
import javax.swing.JCheckBox;
import kotlin.Pair;
import kotlin.Unit;
import kotlin.coroutines.Continuation;
import kotlin.coroutines.EmptyCoroutineContext;
import kotlinx.coroutines.BuildersKt;

/** Test-only native model/backend integration. It never opens or trusts an existing project. */
public final class FrameworkGeneratorProbe {
  private FrameworkGeneratorProbe() { }

  public static void start(Path report) {
    AppExecutorUtil.getAppExecutorService().execute(() -> {
      Map<String, Object> result = new LinkedHashMap<>();
      result.put("invocationId", System.getProperty("openpycharm.framework.probe.invocation.id"));
      result.put("scope", "Native generator peers, selected existing real venv/module setup, generation and dependency lifecycle");
      result.put("nativeGuiCreateClicked", false);
      List<Project> projects = new ArrayList<>();
      List<Sdk> sdks = new ArrayList<>();
      try {
        result.put("frameworkPlugin", FrameworkProbe.pluginObservation());
        Path root = Path.of(System.getProperty("openpycharm.framework.generator.probe.root")).toAbsolutePath().normalize();
        require(root.startsWith(report.getParent()), "Generator output escaped the disposable profile");
        Files.createDirectories(root);
        Map<FrameworkKind, FrameworkProjectGenerator> generators = inspectPeers(root, result);
        Sdk selected = sdk("Framework selected venv", System.getProperty("openpycharm.framework.probe.python"));
        Sdk optout = sdk("Framework no-install venv", System.getProperty("openpycharm.framework.generator.probe.optout.python"));
        sdks.add(selected); sdks.add(optout);
        List<Object> generated = new ArrayList<>();
        for (FrameworkKind kind : FrameworkKind.values()) {
          generated.add(generate(root.resolve(kind.name().toLowerCase(Locale.ROOT)), kind, selected, true, projects));
        }
        generated.add(generate(root.resolve("flask-no-install"), FrameworkKind.FLASK, optout, false, projects));
        result.put("projects", generated);
        result.put("processLifecycle", processChecks(root, selected));
        result.put("status", "pass");
      } catch (Throwable error) {
        result.put("status", "fail");
        result.put("failure", error.toString());
        result.put("stack", Arrays.stream(error.getStackTrace()).limit(20).map(Object::toString).toList());
      } finally {
        try {
          // Let ordinary SDK updates finish rather than create shutdown error noise.
          long deadline = System.nanoTime() + 90_000_000_000L;
          for (Sdk sdk : sdks) {
            while (PythonSdkUpdater.isUpdateScheduled(sdk) && System.nanoTime() < deadline) Thread.sleep(100);
            require(!PythonSdkUpdater.isUpdateScheduled(sdk), "SDK update did not settle before probe shutdown");
          }
          for (Project project : projects) {
            ApplicationManager.getApplication().invokeAndWait(() -> WriteAction.run(() -> Disposer.dispose(project)));
          }
          ApplicationManager.getApplication().invokeAndWait(() -> WriteAction.run(() -> {
            for (Sdk sdk : sdks) ProjectJdkTable.getInstance().removeJdk(sdk);
          }));
        } catch (Throwable cleanup) {
          result.put("status", "fail"); result.put("cleanupFailure", cleanup.toString());
        }
        try {
          Path temporary = Files.createTempFile(report.getParent(), ".framework-generator-", ".json");
          Files.writeString(temporary, new GsonBuilder().setPrettyPrinting().create().toJson(result));
          Files.move(temporary, report, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        } catch (Exception ignored) { }
        ApplicationManager.getApplication().invokeLater(() -> ((ApplicationEx)ApplicationManager.getApplication()).exit(true, true));
      }
    });
  }

  private static Map<FrameworkKind, FrameworkProjectGenerator> inspectPeers(Path root, Map<String, Object> result) {
    Map<FrameworkKind, FrameworkProjectGenerator> generators = new EnumMap<>(FrameworkKind.class);
    List<Object> peers = new ArrayList<>();
    ApplicationManager.getApplication().invokeAndWait(() -> {
      for (DirectoryProjectGenerator<?> entry : AbstractNewProjectStep.EP_NAME.getExtensionList()) {
        if (!(entry instanceof FrameworkProjectGenerator generator)) continue;
        FrameworkKind kind = generator.projectSettings().framework();
        require(generators.put(kind, generator) == null, "Duplicate native framework generator");
        var peer = generator.createPeer();
        TextFieldWithBrowseButton path = new TextFieldWithBrowseButton();
        path.setText(root.resolve(kind.name().toLowerCase(Locale.ROOT)).toString());
        var component = peer.getComponent(path, () -> { });
        JCheckBox install = checkbox(component, "Install " + kind.displayName() + " dependencies");
        require(install != null && !install.isSelected() && !generator.projectSettings().installDependencies(), "Dependency installation was not opt-in");
        install.doClick();
        require(generator.projectSettings().installDependencies(), "Native install checkbox did not update settings");
        install.doClick();
        require(!generator.projectSettings().installDependencies(), "Native install checkbox did not turn off");
        peers.add(Map.of("framework", kind.name(), "generator", generator.getClass().getName(), "nativePeer", peer.getClass().getName(),
            "nativeComponent", component.getClass().getName(), "dependencyCheckboxDefault", false, "dependencyCheckboxBinding", "pass"));
        Disposer.dispose(path);
      }
    });
    require(generators.size() == 3, "All three native project generators must be registered");
    result.put("generatorPeers", peers);
    return generators;
  }

  private static JCheckBox checkbox(Component component, String prefix) {
    if (component instanceof JCheckBox box && box.getText() != null && box.getText().startsWith(prefix)) return box;
    if (component instanceof Container container) {
      for (Component child : container.getComponents()) {
        JCheckBox found = checkbox(child, prefix);
        if (found != null) return found;
      }
    }
    return null;
  }

  private static Sdk sdk(String name, String home) {
    require(home != null, "The real venv interpreter was not supplied");
    AtomicReference<Sdk> result = new AtomicReference<>();
    ApplicationManager.getApplication().invokeAndWait(() -> WriteAction.run(() -> {
      Sdk sdk = ProjectJdkTable.getInstance().createSdk(name, PythonSdkType.getInstance());
      var change = sdk.getSdkModificator();
      change.setHomePath(home);
      change.setVersionString(System.getProperty("openpycharm.framework.generator.probe.python.version"));
      change.commitChanges();
      ProjectJdkTable.getInstance().addJdk(sdk);
      result.set(sdk);
    }));
    return result.get();
  }

  @SuppressWarnings({"unchecked", "rawtypes"})
  private static Object generate(Path directory, FrameworkKind kind, Sdk sdk, boolean install, List<Project> projects) throws Exception {
    Files.createDirectories(directory);
    Project project = ProjectManagerEx.getInstanceEx().newProject("Framework " + kind.name(), directory.toString(), false, false);
    require(project != null, "Native project model could not be created");
    projects.add(project);
    VirtualFile base = VfsUtil.findFile(directory, true);
    require(base != null, "Generated project has no native VFS root");
    AtomicReference<Module> moduleRef = new AtomicReference<>();
    ApplicationManager.getApplication().invokeAndWait(() -> WriteAction.run(() -> {
      Module module = ModuleManager.getInstance(project).newModule(directory.resolve(kind.name().toLowerCase(Locale.ROOT) + ".iml"), PythonModuleTypeBase.getInstance().getId());
      var roots = ModuleRootManager.getInstance(module).getModifiableModel();
      roots.addContentEntry(base);
      roots.commit();
      moduleRef.set(module);
    }));
    Module module = moduleRef.get();
    AtomicReference<String> sdkRequest = new AtomicReference<>();
    PyV3BaseProjectSettings common = new PyV3BaseProjectSettings();
    common.setSdkCreator(new PySdkCreator() {
      @Override public Object getSdk(ModuleOrProject context, Continuation continuation) {
        sdkRequest.set(context.getClass().getName());
        var statistics = new InterpreterStatisticsInfo(InterpreterType.VIRTUALENV, InterpreterTarget.LOCAL, false, false, true, false, InterpreterCreationMode.CUSTOM);
        return new Result.Success<>(new Pair<>(sdk, statistics));
      }
    });
    Object sdkResult = BuildersKt.runBlocking(EmptyCoroutineContext.INSTANCE,
        (scope, continuation) -> common.generateAndGetSdk(module, base, false, (Continuation)continuation));
    require(sdkResult instanceof Result.Success, "Native SDK configuration stage failed: " + sdkResult);
    String boundSdk = ReadAction.compute(() -> ModuleRootManager.getInstance(module).getSdk().getHomePath());
    require(Objects.equals(boundSdk, sdk.getHomePath()), "Native SDK stage did not retain the selected real venv on the module");
    FrameworkProjectSettings settings = new FrameworkProjectSettings(kind);
    require(!settings.installDependencies(), "Default generator installs dependencies without opt-in");
    settings.setInstallDependencies(install);
    Object generated = BuildersKt.runBlocking(EmptyCoroutineContext.INSTANCE,
        (scope, continuation) -> settings.generateProject(module, base, sdk, (Continuation)continuation));
    require(generated instanceof Result.Success, "Framework generation failed: " + generated);
    Map<String, String> hashes = new LinkedHashMap<>();
    for (String file : FrameworkProjectFiles.plan(kind).keySet()) hashes.put(file,
        HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(directory.resolve(file)))));
    Map<String, Object> configuration = new LinkedHashMap<>();
    ReadAction.run(() -> {
      var selected = RunManager.getInstance(project).getSelectedConfiguration();
      require(selected != null && selected.getConfiguration() instanceof FrameworkRunConfiguration, "Native generated Run configuration is absent");
      FrameworkRunConfiguration run = (FrameworkRunConfiguration)selected.getConfiguration();
      require(run.framework() == kind && run.getModule() == module && run.isUseModuleSdk(), "Generated Run configuration is not bound to the callback module");
      require(Objects.equals(run.getInterpreterPath(), sdk.getHomePath()), "Generated Run configuration changed interpreter");
      require(Objects.equals(run.getWorkingDirectory(), base.getPath()), "Generated Run configuration changed working directory");
      configuration.put("typeId", run.getType().getId());
      configuration.put("module", module.getName());
      configuration.put("interpreter", run.getInterpreterPath());
      configuration.put("workingDirectory", run.getWorkingDirectory());
      configuration.put("moduleSdk", run.isUseModuleSdk());
    });
    int before = ReadAction.compute(() -> RunManager.getInstance(project).getAllSettings().size());
    Object collision = BuildersKt.runBlocking(EmptyCoroutineContext.INSTANCE,
        (scope, continuation) -> settings.generateProject(module, base, sdk, (Continuation)continuation));
    require(collision instanceof Result.Failure, "Existing project files were silently overwritten");
    require(ReadAction.compute(() -> RunManager.getInstance(project).getAllSettings().size()) == before, "Collision added another Run configuration");
    Map<String, Object> result = new LinkedHashMap<>();
    result.put("framework", kind.name().toLowerCase(Locale.ROOT));
    result.put("path", directory.toString()); result.put("sdkHome", sdk.getHomePath());
    result.put("sdkCreatorContext", sdkRequest.get()); result.put("moduleSdkAfterNativeStage", boundSdk);
    result.put("installDependencies", install); result.put("files", hashes); result.put("runConfiguration", configuration);
    result.put("collisionRejected", true); result.put("status", "pass");
    return result;
  }

  @SuppressWarnings("unchecked")
  private static Object processChecks(Path root, Sdk sdk) throws Exception {
    Path ids = root.resolve("owned-cancellation-pids.json");
    String script = "import json,os,pathlib,subprocess,sys,time;child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);pathlib.Path(sys.argv[1]).write_text(json.dumps({'parent':os.getpid(),'child':child.pid}));time.sleep(60)";
    boolean cancelled = false;
    try {
      FrameworkDependencyInstaller.run(sdk, root, List.of("-c", script, ids.toString()), () -> {
        if (Files.isRegularFile(ids)) throw new CancellationException("Native probe cancellation");
      }, 10_000);
    } catch (CancellationException expected) { cancelled = true; }
    require(cancelled && Files.isRegularFile(ids), "Owned helper cancellation was not observed");
    Map<String, Number> pids = new Gson().fromJson(Files.readString(ids), Map.class);
    long deadline = System.nanoTime() + 5_000_000_000L;
    while (anyAlive(pids) && System.nanoTime() < deadline) Thread.sleep(50);
    require(!anyAlive(pids), "Cancellation left an owned helper or child alive");
    boolean failed = false, timedOut = false;
    try { FrameworkDependencyInstaller.run(sdk, root, List.of("-c", "import sys;sys.exit(23)"), () -> { }, 5000); }
    catch (IOException expected) { failed = expected.getMessage().contains("exit 23"); }
    try { FrameworkDependencyInstaller.run(sdk, root, List.of("-c", "import time;time.sleep(60)"), () -> { }, 200); }
    catch (IOException expected) { timedOut = expected.getMessage().contains("timed out"); }
    require(failed && timedOut, "Owned helper failure/timeout did not propagate");
    Map<String, Number> normalExit = rootExitChild(root, sdk, 0);
    Map<String, Number> failedExit = rootExitChild(root, sdk, 23);
    return Map.of("status", "pass", "cancellationPreserved", true, "ownedPids", pids,
        "ownedPidsAliveAfterCancellation", false, "nonzeroExitPropagated", true, "timeoutPropagated", true,
        "normalExitChildrenCleaned", true, "normalExitOwnedPids", normalExit,
        "failedExitChildrenCleaned", true, "failedExitOwnedPids", failedExit);
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Number> rootExitChild(Path root, Sdk sdk, int exit) throws Exception {
    Path ids = root.resolve("owned-root-exit-" + exit + "-pids.json");
    // Keep the root alive long enough for portable descendant observation, then
    // leave a child running. Unobservable instant-spawn orphans are not claimed.
    String script = "import json,os,pathlib,subprocess,sys,time;child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);pathlib.Path(sys.argv[1]).write_text(json.dumps({'parent':os.getpid(),'child':child.pid}));time.sleep(0.5);sys.exit(int(sys.argv[2]))";
    FrameworkDependencyInstaller.ProcessResult returned = null;
    IOException failure = null;
    try { returned = FrameworkDependencyInstaller.run(sdk, root, List.of("-c", script, ids.toString(), Integer.toString(exit)), () -> { }, 5000); }
    catch (IOException expected) { failure = expected; }
    require(exit == 0 ? returned != null && failure == null : failure != null && failure.getMessage().contains("exit " + exit), "Root exit result did not propagate");
    Map<String, Number> pids = new Gson().fromJson(Files.readString(ids), Map.class);
    if (returned != null) require(returned.observedDescendants().contains(pids.get("child").longValue()), "Child was not observed before root exit");
    long deadline = System.nanoTime() + 5_000_000_000L;
    while (anyAlive(pids) && System.nanoTime() < deadline) Thread.sleep(50);
    require(!anyAlive(pids), "Root exit left a previously observed owned child alive");
    return pids;
  }

  private static boolean anyAlive(Map<String, Number> pids) {
    return pids.values().stream().anyMatch(number -> ProcessHandle.of(number.longValue()).map(ProcessHandle::isAlive).orElse(false));
  }
  private static void require(boolean condition, String message) {
    if (!condition) throw new IllegalStateException(message);
  }
}
