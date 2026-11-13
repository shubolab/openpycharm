package dev.openpycharm.markdown.probe;

import com.google.gson.GsonBuilder;
import com.intellij.ide.AppLifecycleListener;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.application.ex.ApplicationEx;
import com.intellij.openapi.util.Disposer;
import com.intellij.ui.jcef.JBCefApp;
import com.intellij.ui.jcef.JBCefJSQuery;
import com.intellij.util.concurrency.AppExecutorUtil;
import com.intellij.util.net.HttpConfigurable;
import com.intellij.util.net.internal.ProxyMigrationService;
import org.intellij.plugins.markdown.ui.preview.jcef.MarkdownJCEFHtmlPanel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import javax.swing.JFrame;

/** Test-only actual Markdown/JCEF panel. No project, user file, proxy setting or credentials are changed. */
@SuppressWarnings("removal")
public final class MarkdownStartupProbe implements AppLifecycleListener {
  private final AtomicBoolean scheduled = new AtomicBoolean();
  @Override public void appFrameCreated(List<String> arguments) { request(); }
  @Override public void appStarted() { request(); }
  @Override public void welcomeScreenDisplayed() { request(); }

  private void request() {
    String destination = System.getProperty("openpycharm.markdown.probe.report");
    String boundary = System.getProperty("openpycharm.markdown.probe.root");
    if (destination == null || boundary == null || !scheduled.compareAndSet(false, true)) return;
    Path report = Path.of(destination).toAbsolutePath().normalize();
    if (!report.startsWith(Path.of(boundary).toAbsolutePath().normalize())) return;
    AppExecutorUtil.getAppExecutorService().execute(() -> run(report));
  }

  private static void run(Path report) {
    Map<String, Object> result = new LinkedHashMap<>();
    String nonce = System.getProperty("openpycharm.markdown.probe.nonce");
    result.put("invocationId", nonce);
    result.put("scope", "Cold actual MarkdownJCEFHtmlPanel construction and browser DOM rendering; no restored project/UI workflow");
    AtomicReference<MarkdownJCEFHtmlPanel> panelRef = new AtomicReference<>();
    AtomicReference<JBCefJSQuery> queryRef = new AtomicReference<>();
    AtomicReference<JFrame> frameRef = new AtomicReference<>();
    AtomicReference<String> rendered = new AtomicReference<>();
    try {
      ApplicationManager.getApplication().invokeAndWait(() -> {
        var application = ApplicationManager.getApplication();
        boolean httpCold = application.getServiceIfCreated(HttpConfigurable.class) == null;
        boolean migrationCold = application.getServiceIfCreated(ProxyMigrationService.class) == null;
        result.put("httpSettingsColdBefore", httpCold);
        result.put("migrationServiceColdBefore", migrationCold);
        require(httpCold && migrationCold, "Proxy dependencies were already warm; cannot claim a cold Markdown construction");
        require(!JBCefApp.isStarted(), "JCEF was already started before the cold control");
        MarkdownJCEFHtmlPanel panel = new MarkdownJCEFHtmlPanel();
        panelRef.set(panel);
        JBCefJSQuery query = JBCefJSQuery.create(panel);
        query.addHandler(text -> { rendered.set(text); return null; });
        queryRef.set(query);
        JFrame frame = new JFrame("OpenPyCharm Markdown startup check");
        frameRef.set(frame);
        frame.setContentPane(panel.getComponent());
        frame.setSize(640, 420);
        frame.setVisible(true);
        result.put("panelClass", panel.getClass().getName());
        result.put("jcefStartedAfterConstruction", JBCefApp.isStarted());
        result.put("httpSettingsCreatedAfter", application.getServiceIfCreated(HttpConfigurable.class) != null);
        result.put("migrationServiceCreatedAfter", application.getServiceIfCreated(ProxyMigrationService.class) != null);
      });
      String sourceAttribute = org.intellij.markdown.html.HtmlGenerator.Companion.getSRC_ATTRIBUTE_NAME();
      String html = "<div " + sourceAttribute + "=\"0..256\"><h1>Markdown preview 中文</h1><p>" + nonce + "</p></div>";
      // The SDK's test-only await helper uses the real preview resource load,
      // IncrementalDOMBuilder and browser JS; wait on the worker, never the EDT.
      kotlinx.coroutines.BuildersKt.runBlocking(kotlin.coroutines.EmptyCoroutineContext.INSTANCE,
          (scope, continuation) -> panelRef.get().setHtmlAndWait(html, continuation));
      result.put("renderAwaitApi", "MarkdownJCEFHtmlPanel.setHtmlAndWait (test-only, actual browser)");
      long deadline = System.nanoTime() + 40_000_000_000L;
      while (rendered.get() == null && System.nanoTime() < deadline) {
        ApplicationManager.getApplication().invokeAndWait(() -> {
          String script = "if(document.body&&document.body.textContent.includes('" + nonce + "')){" +
                          queryRef.get().inject("document.body.textContent") + ";}";
          panelRef.get().runJavaScript(script);
        });
        Thread.sleep(200);
      }
      require(rendered.get() != null && rendered.get().contains(nonce) && rendered.get().contains("Markdown preview 中文"),
              "Actual Markdown browser did not render the expected DOM before timeout");
      result.put("renderedText", rendered.get());
      result.put("nativeBrowserRendered", true);
      result.put("status", "pass");
    } catch (Throwable error) {
      result.put("status", "fail"); result.put("failure", error.toString());
      result.put("stack", Arrays.stream(error.getStackTrace()).limit(20).map(Object::toString).toList());
    } finally {
      try {
        ApplicationManager.getApplication().invokeAndWait(() -> {
          if (panelRef.get() != null && !panelRef.get().isDisposed()) Disposer.dispose(panelRef.get());
          if (queryRef.get() != null && !queryRef.get().isDisposed()) Disposer.dispose(queryRef.get());
          if (frameRef.get() != null) frameRef.get().dispose();
        });
      } catch (Throwable error) { result.put("status", "fail"); result.put("cleanupFailure", error.toString()); }
      try {
        Path temporary = Files.createTempFile(report.getParent(), ".markdown-startup-", ".json");
        Files.writeString(temporary, new GsonBuilder().setPrettyPrinting().create().toJson(result));
        Files.move(temporary, report, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
      } catch (Exception ignored) { }
      ApplicationManager.getApplication().invokeLater(() -> ((ApplicationEx)ApplicationManager.getApplication()).exit(true, true));
    }
  }

  private static void require(boolean condition, String message) {
    if (!condition) throw new IllegalStateException(message);
  }
}
