package dev.openpycharm.probe;

import com.google.gson.GsonBuilder;
import com.intellij.execution.actions.ConfigurationContext;
import com.intellij.execution.actions.RunConfigurationProducer;
import com.intellij.execution.configurations.RunConfiguration;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.application.ReadAction;
import com.intellij.openapi.application.ApplicationInfo;
import com.intellij.openapi.application.ApplicationNamesInfo;
import com.intellij.ide.plugins.PluginManagerCore;
import com.intellij.openapi.extensions.PluginId;
import com.intellij.openapi.module.Module;
import com.intellij.openapi.module.ModuleManager;
import com.intellij.openapi.project.DumbService;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.projectRoots.Sdk;
import com.intellij.openapi.roots.ModuleRootManager;
import com.intellij.openapi.roots.OrderRootType;
import com.intellij.openapi.roots.ProjectFileIndex;
import com.intellij.openapi.startup.StartupActivity;
import com.intellij.openapi.vfs.LocalFileSystem;
import com.intellij.openapi.vfs.VirtualFile;
import com.intellij.psi.PsiElement;
import com.intellij.psi.PsiFile;
import com.intellij.psi.PsiManager;
import com.intellij.psi.search.FilenameIndex;
import com.intellij.psi.search.GlobalSearchScope;
import com.intellij.util.ThreeState;
import com.intellij.util.concurrency.AppExecutorUtil;
import com.jetbrains.python.psi.*;
import com.jetbrains.python.psi.types.PyClassLikeType;
import com.jetbrains.python.psi.types.TypeEvalContext;
import com.jetbrains.python.psi.resolve.QualifiedNameFinder;
import com.jetbrains.python.sdk.PythonSdkUtil;
import com.jetbrains.python.testing.*;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

/** Read-only native acceptance probe. Never executes or saves a run configuration. */
public final class DiagnosticProbe implements StartupActivity.DumbAware {
  public void runActivity(Project project) {
    String destination = System.getProperty("openpycharm.probe.report");
    if (destination == null || destination.isBlank()) return;
    Path report = Path.of(destination).toAbsolutePath().normalize();
    String root = System.getProperty("openpycharm.probe.output.root");
    if (root == null) return;
    Path boundary = Path.of(root).toAbsolutePath().normalize();
    if (!report.startsWith(boundary)) return;
    DumbService.getInstance(project).runWhenSmart(() -> {
      long delay = Long.getLong("openpycharm.probe.delay.seconds", 10L);
      AppExecutorUtil.getAppScheduledExecutorService().schedule(() -> {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("capturedAt", Instant.now().toString());
        result.put("readOnlyProbe", true);
        result.put("probeVersion", 1);
        result.put("invocationId", System.getProperty("openpycharm.probe.invocation.id"));
        result.put("pluginId", "dev.openpycharm.native.probe");
        result.put("pluginEnabled", PluginManagerCore.getPlugin(PluginId.getId("dev.openpycharm.native.probe")) != null);
        result.put("applicationName", ApplicationNamesInfo.getInstance().getFullProductName());
        result.put("applicationBuild", ApplicationInfo.getInstance().getBuild().asString());
        try {
          if (project.isDisposed()) result.put("status", "project-disposed");
          else result.putAll(ReadAction.compute(() -> inspect(project)));
        } catch (Throwable error) {
          result.put("failure", failure(error));
        }
        try {
          Files.createDirectories(report.getParent());
          Path candidate = Files.createTempFile(report.getParent(), ".native-probe-", ".json");
          try {
            Files.writeString(candidate, new GsonBuilder().setPrettyPrinting().serializeNulls().create().toJson(result));
            Files.move(candidate, report, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
          } finally {
            Files.deleteIfExists(candidate);
          }
        } catch (Exception ignored) { }
      }, Math.max(0, Math.min(delay, 120)), TimeUnit.SECONDS);
    });
  }

  private static Map<String, Object> inspect(Project project) {
    Map<String, Object> result = new LinkedHashMap<>();
    result.put("projectName", project.getName());
    result.put("projectBasePath", project.getBasePath());
    result.put("isDumbAtCapture", DumbService.getInstance(project).isDumb());
    result.put("isReadAccessAllowed", ApplicationManager.getApplication().isReadAccessAllowed());
    List<Object> modules = new ArrayList<>();
    for (Module module : ModuleManager.getInstance(project).getModules()) {
      Map<String, Object> entry = new LinkedHashMap<>();
      ModuleRootManager roots = ModuleRootManager.getInstance(module);
      entry.put("name", module.getName());
      entry.put("moduleFilePath", module.getModuleFilePath());
      entry.put("contentRoots", Arrays.stream(roots.getContentRoots()).map(DiagnosticProbe::vfile).toList());
      entry.put("sourceRoots", Arrays.stream(roots.getSourceRoots()).map(DiagnosticProbe::vfile).toList());
      entry.put("excludedRoots", Arrays.stream(roots.getExcludeRoots()).map(DiagnosticProbe::vfile).toList());
      entry.put("sdkInherited", roots.isSdkInherited());
      entry.put("sdk", sdk(roots.getSdk()));
      entry.put("pythonSdk", safely(() -> sdk(PythonSdkUtil.findPythonSdk(module))));
      entry.put("testRunner", safely(() -> TestRunnerService.getInstance(module).getProjectConfiguration()));
      entry.put("testFactory", safely(() -> String.valueOf(TestRunnerService.getInstance(module).getSelectedFactory())));
      modules.add(entry);
    }
    result.put("modules", modules);
    List<Object> files = new ArrayList<>();
    String base = project.getBasePath();
    String target = System.getProperty("openpycharm.probe.file", base + "/tests/test_calculator.py");
    for (String name : new LinkedHashSet<>(List.of(target, base + "/hello_python/calculator.py"))) {
      files.add(safely(() -> inspectFile(project, name)));
    }
    result.put("files", files);
    return result;
  }

  private static Map<String, Object> inspectFile(Project project, String path) {
    Map<String, Object> result = new LinkedHashMap<>();
    result.put("path", path);
    VirtualFile virtual = LocalFileSystem.getInstance().findFileByPath(path);
    result.put("virtualFile", vfile(virtual));
    String filename = Path.of(path).getFileName().toString();
    result.put("projectFilenameIndex", safely(() -> FilenameIndex.getVirtualFilesByName(filename, GlobalSearchScope.projectScope(project)).stream().map(DiagnosticProbe::vfile).toList()));
    result.put("allScopeFilenameIndex", safely(() -> FilenameIndex.getVirtualFilesByName(filename, GlobalSearchScope.allScope(project)).stream().map(DiagnosticProbe::vfile).toList()));
    if (virtual == null) return result;
    ProjectFileIndex index = ProjectFileIndex.getInstance(project);
    Module module = index.getModuleForFile(virtual);
    result.put("inContent", index.isInContent(virtual));
    result.put("excluded", index.isExcluded(virtual));
    result.put("inSource", index.isInSource(virtual));
    result.put("inLibrary", index.isInLibrary(virtual));
    result.put("module", module == null ? null : module.getName());
    PsiFile psi = PsiManager.getInstance(project).findFile(virtual);
    result.put("psi", element(psi));
    result.put("pythonSdk", safely(() -> sdk(PythonSdkUtil.findPythonSdk(psi))));
    if (!(psi instanceof PyFile file)) return result;
    result.put("fileQualifiedName", safely(() -> QualifiedNameFinder.getQualifiedName(file)));
    TypeEvalContext context = TypeEvalContext.userInitiated(project, file);
    result.put("testFileBasic", safely(() -> PythonUnitTestDetectorsKt.isTestFile(file, context)));
    result.put("testFileBasedOnSettings", safely(() -> PythonUnitTestDetectorsBasedOnSettings.isTestFile(file, ThreeState.UNSURE, context)));
    result.put("testCaseClassRequired", safely(() -> PythonUnitTestDetectorsBasedOnSettings.isTestCaseClassRequired(file)));
    if (module != null) {
      result.put("pyTestSelected", safely(() -> PyTestDiscoveryUtil.isPyTestSelected(module)));
      result.put("pyTestAllowedForFile", safely(() -> PyTestDiscoveryUtil.isPyTestAllowedForFile(module, file)));
    }
    List<Object> classes = new ArrayList<>();
    for (PyClass cls : file.getTopLevelClasses()) {
      Map<String, Object> entry = new LinkedHashMap<>();
      entry.put("element", element(cls));
      entry.put("superExpressions", Arrays.stream(cls.getSuperClassExpressions()).map(PsiElement::getText).toList());
      entry.put("superResolved", Arrays.stream(cls.getSuperClassExpressions()).map(expression -> safely(() -> element(expression.getReference() == null ? null : expression.getReference().resolve()))).toList());
      entry.put("superTypes", safely(() -> cls.getSuperClassTypes(context).stream().map(type -> type == null ? null : type.getClassQName()).toList()));
      entry.put("ancestors", safely(() -> cls.getAncestorClasses(context).stream().map(DiagnosticProbe::element).toList()));
      entry.put("isUnitTestCaseClass", safely(() -> PythonUnitTestDetectorsKt.isUnitTestCaseClass(cls, context)));
      entry.put("isTestClassBasic", safely(() -> PythonUnitTestDetectorsKt.isTestClass(cls, context)));
      entry.put("isTestClassSettings", safely(() -> PythonUnitTestDetectorsBasedOnSettings.isTestClass(cls, ThreeState.UNSURE, context)));
      entry.put("inheritsUnittestTestCase", safely(() -> cls.isSubclass("unittest.TestCase", context)));
      entry.put("inheritsUnittestCaseTestCase", safely(() -> cls.isSubclass("unittest.case.TestCase", context)));
      List<Object> methods = new ArrayList<>();
      for (PyFunction function : cls.getMethods()) {
        Map<String, Object> method = new LinkedHashMap<>();
        method.put("name", function.getName());
        method.put("basicTest", safely(() -> PythonUnitTestDetectorsKt.isTestFunction(function)));
        method.put("settingsTest", safely(() -> PythonUnitTestDetectorsBasedOnSettings.isTestFunction(function, ThreeState.UNSURE, context)));
        methods.add(method);
      }
      entry.put("methods", methods);
      entry.put("lightProducers", lightProducers(project, cls));
      classes.add(entry);
    }
    result.put("classes", classes);
    result.put("fileLightProducers", lightProducers(project, file));
    return result;
  }

  private static List<Object> lightProducers(Project project, PsiElement element) {
    List<Object> values = new ArrayList<>();
    ConfigurationContext context = new ConfigurationContext(element);
    for (RunConfigurationProducer<?> producer : RunConfigurationProducer.getProducers(project)) {
      if (!producer.getClass().getName().startsWith("com.jetbrains.python.")) continue;
      Map<String, Object> entry = new LinkedHashMap<>();
      entry.put("producer", producer.getClass().getName());
      entry.put("contextModule", context.getModule() == null ? null : context.getModule().getName());
      entry.put("lightConfiguration", safely(() -> {
        RunConfiguration configuration = producer.createLightConfiguration(context);
        if (configuration == null) return null;
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("class", configuration.getClass().getName());
        summary.put("name", configuration.getName());
        summary.put("type", configuration.getType().getId());
        return summary;
      }));
      values.add(entry);
    }
    return values;
  }

  private static Object safely(Supplier<?> supplier) {
    try { return supplier.get(); }
    catch (Throwable error) { return Map.of("error", failure(error)); }
  }

  private static Object sdk(Sdk sdk) {
    if (sdk == null) return null;
    Map<String, Object> result = new LinkedHashMap<>();
    result.put("name", sdk.getName());
    result.put("homePath", sdk.getHomePath());
    result.put("version", sdk.getVersionString());
    result.put("type", sdk.getSdkType().getName());
    result.put("classRootUrls", Arrays.asList(sdk.getRootProvider().getUrls(OrderRootType.CLASSES)));
    result.put("classRootFiles", Arrays.stream(sdk.getRootProvider().getFiles(OrderRootType.CLASSES)).map(DiagnosticProbe::vfile).toList());
    return result;
  }

  private static Object vfile(VirtualFile file) {
    if (file == null) return null;
    return Map.of("url", file.getUrl(), "valid", file.isValid(), "exists", file.exists());
  }

  private static Object element(PsiElement element) {
    if (element == null) return null;
    Map<String, Object> value = new LinkedHashMap<>();
    value.put("class", element.getClass().getName());
    value.put("valid", element.isValid());
    if (element instanceof PyQualifiedNameOwner owner) value.put("qualifiedName", owner.getQualifiedName());
    if (element.getContainingFile() != null) value.put("file", vfile(element.getContainingFile().getVirtualFile()));
    return value;
  }

  private static String failure(Throwable error) {
    StringWriter buffer = new StringWriter();
    error.printStackTrace(new PrintWriter(buffer));
    String text = buffer.toString();
    return text.length() > 4000 ? text.substring(0, 4000) : text;
  }
}
