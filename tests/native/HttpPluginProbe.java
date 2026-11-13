package dev.openpycharm.probe;

import com.google.gson.GsonBuilder;
import com.intellij.execution.services.ServiceViewContributor;
import com.intellij.ide.plugins.IdeaPluginDescriptor;
import com.intellij.ide.plugins.PluginManagerCore;
import com.intellij.ide.AppLifecycleListener;
import com.intellij.lang.LanguageParserDefinitions;
import com.intellij.lexer.Lexer;
import com.intellij.openapi.actionSystem.ActionManager;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.application.PathManager;
import com.intellij.openapi.application.ReadAction;
import com.intellij.openapi.extensions.PluginId;
import com.intellij.openapi.fileTypes.FileTypeManager;
import com.intellij.openapi.fileTypes.SyntaxHighlighterFactory;
import com.intellij.openapi.project.DumbService;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.project.ProjectManager;
import com.intellij.psi.PsiFileFactory;
import com.intellij.util.concurrency.AppExecutorUtil;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/** Read-only plugin-loading/PSI evidence. Does not run HTTP or invoke an action. */
public final class HttpPluginProbe implements AppLifecycleListener {
  private final AtomicBoolean scheduled = new AtomicBoolean();
  public void appFrameCreated(List<String> arguments) { schedule(); }
  public void welcomeScreenDisplayed() { schedule(); }
  public void appStarted() { schedule(); }
  private void schedule() {
    if (!"http".equals(System.getProperty("openpycharm.probe.mode"))) return;
    if (!scheduled.compareAndSet(false, true)) return;
    String destination = System.getProperty("openpycharm.probe.report");
    String root = System.getProperty("openpycharm.probe.output.root");
    if (destination == null || root == null) return;
    Path report = Path.of(destination).toAbsolutePath().normalize();
    if (!report.startsWith(Path.of(root).toAbsolutePath().normalize())) return;
    AppExecutorUtil.getAppScheduledExecutorService().schedule(() -> {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("capturedAt", Instant.now().toString());
        result.put("invocationId", System.getProperty("openpycharm.probe.invocation.id"));
        result.put("pluginId", "dev.openpycharm.native.probe");
        result.put("pluginEnabled", PluginManagerCore.getPlugin(PluginId.getId("dev.openpycharm.native.probe")) != null);
        result.put("readOnlyProbe", true);
        result.put("isDispatchThread", ApplicationManager.getApplication().isDispatchThread());
        try {
          result.putAll(ReadAction.compute(() -> inspect(ProjectManager.getInstance().getDefaultProject())));
        } catch (Throwable error) {
          result.put("failure", error.toString());
        }
        try {
          Files.createDirectories(report.getParent());
          Path temporary = Files.createTempFile(report.getParent(), ".http-probe-", ".json");
          try {
            Files.writeString(temporary, new GsonBuilder().setPrettyPrinting().serializeNulls().create().toJson(result));
            Files.move(temporary, report, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
          } finally { Files.deleteIfExists(temporary); }
        } catch (Exception ignored) { }
      }, Math.max(0, Math.min(Integer.getInteger("openpycharm.probe.delay.seconds", 5), 120)), TimeUnit.SECONDS);
  }

  private static Map<String, Object> inspect(Project project) throws Exception {
    Map<String, Object> result = new LinkedHashMap<>();
    result.put("isReadAccessAllowed", ApplicationManager.getApplication().isReadAccessAllowed());
    result.put("isDumbAtCapture", DumbService.getInstance(project).isDumb());
    result.put("projectBasePath", project.getBasePath());
    result.put("inspectionMode", "application-registration-and-default-project-in-memory-PSI");
    result.put("applicationHome", PathManager.getHomePath());
    result.put("pluginPathProperty", System.getProperty("plugin.path"));
    IdeaPluginDescriptor descriptor = PluginManagerCore.getPlugin(PluginId.getId("dev.openpycharm.http"));
    if (descriptor == null) throw new IllegalStateException("Packaged HTTP plugin was not discovered");
    Map<String, Object> plugin = new LinkedHashMap<>();
    plugin.put("id", descriptor.getPluginId().getIdString());
    plugin.put("version", descriptor.getVersion());
    plugin.put("enabled", descriptor.isEnabled());
    plugin.put("bundled", descriptor.isBundled());
    plugin.put("path", descriptor.getPluginPath().toAbsolutePath().normalize().toString());
    Path jar = descriptor.getPluginPath().resolve("lib/openpycharm-http.jar");
    plugin.put("jar", jar.toString());
    MessageDigest digest = MessageDigest.getInstance("SHA-256");
    try (var input = Files.newInputStream(jar)) {
      byte[] buffer = new byte[65536];
      for (int count; (count = input.read(buffer)) != -1;) digest.update(buffer, 0, count);
    }
    plugin.put("jarSha256", HexFormat.of().formatHex(digest.digest()));
    plugin.put("implementationClass", descriptor.getPluginClassLoader().loadClass("dev.openpycharm.http.HttpServicesContributor").getName());
    result.put("httpPlugin", plugin);

    var type = FileTypeManager.getInstance().getFileTypeByFileName("acceptance.http");
    result.put("fileType", type.getClass().getName());
    Path fixture = Path.of(System.getProperty("openpycharm.probe.file"));
    if (Files.size(fixture) > 2 * 1024 * 1024) throw new IllegalStateException("Probe fixture exceeds its bound");
    result.put("fixture", fixture.toString());
    var psi = PsiFileFactory.getInstance(project).createFileFromText(fixture.getFileName().toString(), type, Files.readString(fixture));
    result.put("psiClass", psi.getClass().getName());
    result.put("language", psi.getLanguage().getID());
    var parser = LanguageParserDefinitions.INSTANCE.forLanguage(psi.getLanguage());
    result.put("parserDefinition", parser == null ? null : parser.getClass().getName());
    var highlighter = SyntaxHighlighterFactory.getSyntaxHighlighter(psi.getLanguage(), project, null);
    result.put("syntaxHighlighter", highlighter == null ? null : highlighter.getClass().getName());
    if (highlighter != null) {
      Lexer lexer = highlighter.getHighlightingLexer();
      lexer.start(psi.getText());
      List<String> tokens = new ArrayList<>();
      while (lexer.getTokenType() != null) {
        tokens.add(lexer.getTokenType().toString());
        lexer.advance();
      }
      result.put("tokens", tokens);
    }
    Map<String, String> actions = new LinkedHashMap<>();
    for (String id : List.of("OpenPyCharm.Http.RunRequest", "OpenPyCharm.Http.RunAllRequests", "OpenPyCharm.Http.SaveResponse")) {
      var action = ActionManager.getInstance().getAction(id);
      actions.put(id, action == null ? null : action.getClass().getName());
    }
    result.put("actions", actions);
    result.put("servicesContributor", ServiceViewContributor.CONTRIBUTOR_EP_NAME.getExtensionList().stream()
      .map(item -> item.getClass().getName()).filter(name -> name.equals("dev.openpycharm.http.HttpServicesContributor")).toList());
    return result;
  }
}
