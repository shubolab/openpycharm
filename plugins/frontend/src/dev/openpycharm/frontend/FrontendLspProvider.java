package dev.openpycharm.frontend;

import com.intellij.execution.ExecutionException;
import com.intellij.execution.configurations.GeneralCommandLine;
import com.intellij.ide.trustedProjects.TrustedProjects;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.vfs.VirtualFile;
import com.intellij.platform.lsp.api.LspIntegrationProvider;
import com.intellij.platform.lsp.api.ProjectWideLspClientDescriptor;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.eclipse.lsp4j.ConfigurationItem;
import org.eclipse.lsp4j.GeneralClientCapabilities;
import org.eclipse.lsp4j.InitializeParams;

/** Independent native API M0. Default off; only explicitly prepared owned fixtures. */
public final class FrontendLspProvider implements LspIntegrationProvider {
  @Override public void fileOpened(Project project, VirtualFile file, LspClientStarter starter) {
    if (!Boolean.getBoolean("openpycharm.frontend.m0.enabled") || project.isDisposed()) return;
    var configuration = FrontendFixtureScope.evaluate(true, FrontendBuildScope.FIXTURE_PARENT, FrontendBuildScope.CACHE_PARENT,
        project.getBasePath(), file.getPath(), System.getProperty("openpycharm.frontend.m0.fixture"),
        System.getProperty("openpycharm.frontend.m0.nonce"), System.getProperty("openpycharm.frontend.m0.toolsReceipt"),
        System.getProperty("openpycharm.frontend.m0.toolsReceiptSha256"));
    // The native API queues process creation; authentication stays in its worker createCommandLine.
    if (configuration.isPresent() && TrustedProjects.isProjectTrusted(project))
      starter.ensureClientStarted(new Descriptor(project, configuration.get()));
  }

  private static final class Descriptor extends ProjectWideLspClientDescriptor {
    private final FrontendFixtureScope.Configuration configuration;
    Descriptor(Project project, FrontendFixtureScope.Configuration configuration) {
      super(project, "OpenPyCharm TypeScript/JavaScript M0 fixture"); this.configuration = configuration;
    }
    @Override public boolean isSupportedFile(VirtualFile file) {
      return file.getPath().startsWith(configuration.fixture() + "/") && FrontendFixtureScope.languageId(file.getPath()) != null;
    }
    @Override public String getLanguageId(VirtualFile file) {
      String language = FrontendFixtureScope.languageId(file.getPath());
      return language != null ? language : super.getLanguageId(file);
    }
    @Override public GeneralCommandLine createCommandLine() throws ExecutionException {
      try {
        FrontendRuntime.Verified verified = FrontendRuntime.authenticate(configuration);
        return new GeneralCommandLine(verified.node().toString(), verified.server().toString(), "--stdio", "--log-level", "2")
            .withParentEnvironmentType(GeneralCommandLine.ParentEnvironmentType.NONE)
            .withEnvironment(FrontendRuntime.environment(verified)).withWorkDirectory(verified.fixture().toString()).withCharset(StandardCharsets.UTF_8);
      } catch (Exception error) { throw new ExecutionException("Frontend M0 worker authentication failed", error); }
    }
    @Override public InitializeParams createInitializeParams() {
      InitializeParams params = super.createInitializeParams();
      var general = params.getCapabilities().getGeneral();
      if (general == null) { general = new GeneralClientCapabilities(); params.getCapabilities().setGeneral(general); }
      general.setPositionEncodings(List.of("utf-16")); return params;
    }
    @Override public Object createInitializationOptions() {
      // Prepare metadata without I/O or assumptions about native initialization callback order.
      // The only process entry point remains authenticated worker createCommandLine above.
      Path toolRoot = Path.of(configuration.receipt()).getParent();
      return Map.of("hostInfo", "OpenPyCharm native frontend M0", "disableAutomaticTypingAcquisition", true,
          "tsserver", Map.of("path", toolRoot.resolve("typescript/lib/tsserver.js").toString(),
                            "logDirectory", Path.of(configuration.fixture()).resolve(".m0-runtime/log").toString()));
    }
    @Override public Object getWorkspaceConfiguration(ConfigurationItem item) {
      return "formattingOptions".equals(item.getSection()) ? Map.of("tabSize", 2, "insertSpaces", true) : Map.of();
    }
  }
}
