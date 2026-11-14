package dev.openpycharm.frontend;

import com.intellij.execution.ExecutionException;
import com.intellij.execution.configurations.GeneralCommandLine;
import com.intellij.execution.process.BaseProcessHandler;
import com.intellij.ide.plugins.PluginManagerCore;
import com.intellij.ide.trustedProjects.TrustedProjects;
import com.intellij.icons.AllIcons;
import com.intellij.openapi.application.PathManager;
import com.intellij.openapi.extensions.PluginId;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.roots.ProjectFileIndex;
import com.intellij.openapi.vfs.VirtualFile;
import com.intellij.platform.lsp.api.LspClient;
import com.intellij.platform.lsp.api.LspIntegrationProvider;
import com.intellij.platform.lsp.api.ProjectWideLspClientDescriptor;
import com.intellij.platform.lsp.api.lsWidget.LspClientWidgetItem;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.eclipse.lsp4j.ConfigurationItem;
import org.eclipse.lsp4j.GeneralClientCapabilities;
import org.eclipse.lsp4j.InitializeParams;

/** Distributable product provider. Opening a file queues only the public native LSP startup. */
public final class FrontendProductLspProvider implements LspIntegrationProvider {
  static final String ID = "dev.openpycharm.frontend";
  @Override public void fileOpened(Project project, VirtualFile file, LspClientStarter starter) {
    if (project.isDisposed() || project.isDefault() || !supported(file)
        || !FrontendProjectSettings.getInstance(project).enabled() || !TrustedProjects.isProjectTrusted(project)
        || !ProjectFileIndex.getInstance(project).isInContent(file)) return;
    String target = FrontendProductScope.target(System.getProperty("os.name", ""), System.getProperty("os.arch", ""));
    var plugin = PluginManagerCore.getPlugin(PluginId.getId(ID));
    if (target == null || plugin == null || project.getBasePath() == null) return;
    // Descriptor/plugin location and PathManager paths are in-memory platform metadata, never Files.* here.
    var layout = FrontendBundledRuntime.layout(plugin.getPluginPath(), Path.of(PathManager.getSystemPath()),
        project.getLocationHash(), Path.of(project.getBasePath()).normalize(), target);
    starter.ensureClientStarted(new Descriptor(project, FrontendProjectSettings.getInstance(project), layout));
  }

  @Override public LspClientWidgetItem createWidgetItem(LspClient client, VirtualFile file) {
    return new LspClientWidgetItem(client, file, AllIcons.FileTypes.JavaScript, FrontendProjectConfigurable.class);
  }

  static boolean supported(VirtualFile file) {
    return file.isValid() && file.isInLocalFileSystem() && !file.isDirectory() && FrontendProductScope.languageId(file.getName()) != null;
  }

  static final class Descriptor extends ProjectWideLspClientDescriptor {
    private final FrontendProjectSettings settings;
    private final FrontendBundledRuntime.Layout layout;
    private final long revision;
    Descriptor(Project project, FrontendProjectSettings settings, FrontendBundledRuntime.Layout layout) {
      super(project, "OpenPyCharm JavaScript and TypeScript");
      this.settings = settings; this.layout = layout; this.revision = settings.generation();
    }
    @Override public boolean isSupportedFile(VirtualFile file) { return supported(file); }
    @Override public String getLanguageId(VirtualFile file) {
      String language = FrontendProductScope.languageId(file.getName()); return language != null ? language : super.getLanguageId(file);
    }
    private boolean active() { return !getProject().isDisposed() && settings.active(revision) && TrustedProjects.isProjectTrusted(getProject()); }
    @Override public GeneralCommandLine createCommandLine() throws ExecutionException {
      try { return FrontendBundledRuntime.command(FrontendBundledRuntime.authenticate(layout, this::active)); }
      catch (Exception error) { throw new ExecutionException("Bundled frontend runtime authentication failed", error); }
    }
    @Override public BaseProcessHandler<?> startServerProcess() throws ExecutionException {
      GeneralCommandLine command = createCommandLine();
      if (!active()) throw new ExecutionException("Frontend analysis was disabled, cancelled, or the project is not trusted");
      FrontendNativeProcess handler = new FrontendNativeProcess(command);
      try {
        handler.register(getProject());
        if (!active()) { handler.dispose(); throw new ExecutionException("Frontend project changed during startup"); }
        return handler;
      } catch (RuntimeException closing) { handler.dispose(); throw new ExecutionException("Frontend project closed during startup", closing); }
    }
    @Override public InitializeParams createInitializeParams() {
      InitializeParams params = super.createInitializeParams();
      var general = params.getCapabilities().getGeneral();
      if (general == null) { general = new GeneralClientCapabilities(); params.getCapabilities().setGeneral(general); }
      general.setPositionEncodings(List.of("utf-16")); return params;
    }
    @Override public Object createInitializationOptions() { return FrontendBundledRuntime.initializationOptions(layout); }
    @Override public Object getWorkspaceConfiguration(ConfigurationItem item) {
      return "formattingOptions".equals(item.getSection()) ? Map.of("tabSize", 2, "insertSpaces", true) : Map.of();
    }
  }
}
