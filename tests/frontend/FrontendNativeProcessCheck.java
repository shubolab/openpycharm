package dev.openpycharm.frontend;

import com.google.gson.*;
import com.intellij.execution.process.*;
import com.intellij.openapi.util.Key;
import com.intellij.openapi.util.Disposer;
import com.intellij.openapi.Disposable;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import org.eclipse.lsp4j.*;
import org.eclipse.lsp4j.jsonrpc.Launcher;
import org.eclipse.lsp4j.jsonrpc.services.JsonNotification;
import org.eclipse.lsp4j.services.*;
import javax.swing.SwingUtilities;

/** Actual public SDK process handler + pinned Node/TLS/TS. Not native IDE LSP service acceptance. */
public final class FrontendNativeProcessCheck {
  public interface NativeClient extends LanguageClient {
    @JsonNotification("$/typescriptVersion") void typescriptVersion(Map<String, Object> value);
  }
  public static void main(String[] args) throws Exception {
    int exit = 0; FrontendNativeProcess handler = null; Future<?> listener = null;
    Map<String, Object> report = new LinkedHashMap<>();
    try {
      var configuration = new FrontendFixtureScope.Configuration(args[0], args[1], args[2], args[3]);
      var runtime = FrontendRuntime.authenticate(configuration);
      handler = new FrontendNativeProcess(FrontendRuntime.command(runtime));
      Disposable parent = Disposer.newDisposable("owned native frontend parent control"); handler.register(parent);
      PipedOutputStream pipe = new PipedOutputStream(); PipedInputStream input = new PipedInputStream(pipe, 65536);
      OutputStreamWriter proxy = new OutputStreamWriter(pipe, StandardCharsets.UTF_8);
      handler.addProcessListener(new ProcessAdapter() {
        @Override public void onTextAvailable(ProcessEvent event, Key outputType) {
          if (ProcessOutputType.isStdout(outputType)) try { proxy.write(event.getText()); proxy.flush(); }
          catch (IOException closed) { }
        }
        @Override public void processTerminated(ProcessEvent event) { try { proxy.close(); pipe.close(); } catch (IOException ignored) { } }
      });
      LinkedBlockingQueue<PublishDiagnosticsParams> diagnostics = new LinkedBlockingQueue<>();
      CompletableFuture<Map<String, Object>> typescriptVersion = new CompletableFuture<>();
      NativeClient client = new NativeClient() {
        public void typescriptVersion(Map<String, Object> value) { typescriptVersion.complete(value); }
        public void telemetryEvent(Object value) { }
        public void publishDiagnostics(PublishDiagnosticsParams value) { diagnostics.add(value); }
        public void showMessage(MessageParams value) { }
        public CompletableFuture<MessageActionItem> showMessageRequest(ShowMessageRequestParams value) { return CompletableFuture.completedFuture(null); }
        public void logMessage(MessageParams value) { }
      };
      Launcher<LanguageServer> launcher = new Launcher.Builder<LanguageServer>().setLocalService(client).setRemoteInterface(LanguageServer.class)
          .setInput(input).setOutput(handler.getProcessInput()).create();
      handler.startNotify(); listener = launcher.startListening(); LanguageServer server = launcher.getRemoteProxy();
      InitializeParams initialize = new InitializeParams(); initialize.setProcessId((int)ProcessHandle.current().pid());
      initialize.setRootUri(runtime.fixture().toUri().toString()); initialize.setCapabilities(new ClientCapabilities());
      initialize.setInitializationOptions(FrontendLspProvider.initializationOptions(configuration));
      InitializeResult result = server.initialize(initialize).get(15, TimeUnit.SECONDS); server.initialized(new InitializedParams());
      Map<String, Object> actualVersion = typescriptVersion.get(15, TimeUnit.SECONDS);
      if (!"6.0.3".equals(actualVersion.get("version")) || !"user-setting".equals(actualVersion.get("source")))
        throw new AssertionError("Actual server did not use the explicitly pinned TypeScript SDK: " + actualVersion);
      String uri = runtime.fixture().resolve("main.ts").toUri().toString();
      String source = "const nativeItem = { amount: 42, label: '😀' };\nnativeItem.\n";
      server.getTextDocumentService().didOpen(new DidOpenTextDocumentParams(new TextDocumentItem(uri, "typescript", 1, source)));
      var completion = server.getTextDocumentService().completion(new CompletionParams(new TextDocumentIdentifier(uri), new Position(1, 11))).get(15, TimeUnit.SECONDS);
      List<CompletionItem> items = completion.isLeft() ? completion.getLeft() : completion.getRight().getItems();
      if (items.stream().noneMatch(item -> item.getLabel().equals("amount"))) throw new AssertionError("Actual native handler lost unsaved completion");
      report.put("actualPublicSdkProcessHandler", true); report.put("serverInfoProvided", result.getServerInfo() != null); report.put("actualTypeScriptVersion", actualVersion);
      report.put("unsavedTsCompletion", true); report.put("utf8FramingWithEmoji", true);
      int cancelled = 0;
      for (int attempt = 0; attempt < 4; attempt++) {
        var request = server.getTextDocumentService().completion(new CompletionParams(new TextDocumentIdentifier(uri), new Position(1, 11)));
        if (request.cancel(true)) cancelled++;
      }
      if (cancelled == 0) throw new AssertionError("Real request cancellation was not observed");
      String revised = "const nativeItem = { amount: 42, label: '😀', afterCancel: 99 };\nnativeItem.\n";
      server.getTextDocumentService().didChange(new DidChangeTextDocumentParams(new VersionedTextDocumentIdentifier(uri, 2),
          List.of(new TextDocumentContentChangeEvent(revised))));
      var afterCancel = server.getTextDocumentService().completion(new CompletionParams(new TextDocumentIdentifier(uri), new Position(1, 11))).get(15, TimeUnit.SECONDS);
      var revisedItems = afterCancel.isLeft() ? afterCancel.getLeft() : afterCancel.getRight().getItems();
      if (revisedItems.stream().noneMatch(item -> item.getLabel().equals("afterCancel"))) throw new AssertionError("Cancelled request dropped a shared document change");
      report.put("realCancelledRequests", cancelled); report.put("sharedDidChangeAfterCancellation", true);
      String jsUri = runtime.fixture().resolve("main.js").toUri().toString();
      server.getTextDocumentService().didOpen(new DidOpenTextDocumentParams(new TextDocumentItem(jsUri, "javascript", 1,
          "const jsItem = { nativeJs: true };\njsItem.\n")));
      var js = server.getTextDocumentService().completion(new CompletionParams(new TextDocumentIdentifier(jsUri), new Position(1, 7))).get(15, TimeUnit.SECONDS);
      var jsItems = js.isLeft() ? js.getLeft() : js.getRight().getItems();
      if (jsItems.stream().noneMatch(item -> item.getLabel().equals("nativeJs"))) throw new AssertionError("Real JavaScript completion did not use unsaved text");
      report.put("unsavedJsCompletion", true);
      boolean posix = !System.getProperty("os.name").startsWith("Windows");
      if (posix) {
        long pid = handler.getProcess().pid(); Process signal = new ProcessBuilder("/bin/kill", "-STOP", Long.toString(pid)).start();
        if (!signal.waitFor(2, TimeUnit.SECONDS) || signal.exitValue() != 0) throw new AssertionError("Could not stop exact owned Node for pipe test");
        byte[] fill = new byte[512 * 1024]; Arrays.fill(fill, (byte)'x');
        long before = System.nanoTime();
        try { handler.getProcessInput().write(fill); handler.getProcessInput().flush(); throw new AssertionError("Stopped owned server accepted an unbounded pipe write"); }
        catch (IOException expected) { }
        report.put("blockedWriteMillis", TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - before));
        report.put("ownedStoppedPipeDeadline", true);
      }
      long before = System.nanoTime(); SwingUtilities.invokeAndWait(() -> Disposer.dispose(parent));
      report.put("actualSdkDisposableTree", true);
      report.put("edtDisposeMillis", TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - before));
      Map<String, Object> cleanup = handler.cleanup().get(9, TimeUnit.SECONDS); report.put("cleanup", cleanup);
      if (!Boolean.TRUE.equals(cleanup.get("cleanupComplete"))) throw new AssertionError("Native handler owned cleanup incomplete: " + cleanup);
      FrontendRuntime.authenticate(configuration); report.put("pinnedToolPayloadUnchanged", true);
      FrontendNativeProcess replacement = new FrontendNativeProcess(FrontendRuntime.command(runtime));
      try {
        Disposable replacementParent = Disposer.newDisposable("owned replacement parent control");
        replacement.register(replacementParent); replacement.startNotify(); SwingUtilities.invokeAndWait(() -> Disposer.dispose(replacementParent));
        Map<String, Object> replacementCleanup = replacement.cleanup().get(9, TimeUnit.SECONDS);
        if (!Boolean.TRUE.equals(replacementCleanup.get("cleanupComplete"))) throw new AssertionError("Replacement process cleanup failed");
        report.put("replacementProcessCleanup", replacementCleanup);
      } finally { replacement.dispose(); }
      report.put("status", "pass"); report.put("nativeIdeStarted", false); report.put("nativeLspManagerExercised", false);
    } catch (Throwable failure) { exit = 1; report.put("status", "fail"); report.put("failure", failure.toString()); failure.printStackTrace(); }
    finally {
      if (handler != null) { handler.dispose(); try { report.put("finalCleanup", handler.cleanup().get(9, TimeUnit.SECONDS)); } catch (Exception failure) { report.put("finalCleanupFailure", failure.toString()); } }
      if (listener != null) listener.cancel(true);
      System.out.println(new Gson().toJson(report));
    }
    System.exit(exit); // Native SDK process I/O executors are outside the test's JVM lifetime.
  }
}
