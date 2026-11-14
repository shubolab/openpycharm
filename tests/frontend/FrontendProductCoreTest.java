package dev.openpycharm.frontend;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayDeque;
import java.util.HexFormat;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;
import javax.swing.JCheckBox;
import javax.swing.JPanel;
import javax.swing.SwingUtilities;

/** Headless actual-SDK controls. No IDE, Node or language server is launched. */
public final class FrontendProductCoreTest {
  private static int checks;
  private static void check(boolean condition, String message) { checks++; if (!condition) throw new AssertionError(message); }
  private interface Operation { void run() throws Exception; }
  private static void rejected(Operation operation, String message) throws Exception {
    try { operation.run(); throw new AssertionError("Accepted: " + message); } catch (IOException | IllegalArgumentException expected) { checks++; }
  }

  public static void main(String[] args) throws Exception {
    Path root = Path.of(args[0]).toAbsolutePath().normalize(); Files.createDirectories(root);
    try {
      scope(); lifecycle(); settings(); bundle(root);
      System.out.println("{\"status\":\"pass\",\"checks\":" + checks + ",\"ideStarted\":false,\"nodeStarted\":false}");
    } finally {
      try (var paths = Files.walk(root)) { for (Path path : paths.sorted(java.util.Comparator.reverseOrder()).toList()) Files.deleteIfExists(path); }
    }
  }

  private static void scope() throws Exception {
    for (String name : new String[]{"x.ts", "types.d.ts", "x.TS", "x.mts", "x.cts"}) check("typescript".equals(FrontendProductScope.languageId(name)), name);
    for (String name : new String[]{"x.js", "x.mjs", "x.cjs"}) check("javascript".equals(FrontendProductScope.languageId(name)), name);
    check("typescriptreact".equals(FrontendProductScope.languageId("组件.tsx")), "tsx");
    check("javascriptreact".equals(FrontendProductScope.languageId("组件.jsx")), "jsx");
    for (String name : new String[]{"x.ts.map", "x.py", "typescript", "x.json", "x.html", "x.css"}) check(FrontendProductScope.languageId(name) == null, name);
    check("macos-arm64".equals(FrontendProductScope.target("Mac OS X", "aarch64")), "mac target");
    check("windows-x64".equals(FrontendProductScope.target("Windows 11", "amd64")), "win target");
    check(FrontendProductScope.target("Linux", "amd64") == null && FrontendProductScope.target("Mac OS X", "x86_64") == null, "unsupported target");
    for (String value : new String[]{"", " ", "..", "a/b", "a\\b", "C:abc", "a\n"}) rejected(() -> FrontendProductScope.locationComponent(value), "location component");
    check(FrontendProductScope.locationComponent("中文 project_abc123").contains("中文"), "normal project hashes");
  }

  private static void lifecycle() {
    ArrayDeque<Runnable> queue = new ArrayDeque<>(); AtomicInteger runs = new AtomicInteger();
    var lifecycle = new FrontendSettingsLifecycle(queue::add, runs::incrementAndGet);
    for (int i = 0; i < 1000; i++) lifecycle.request();
    check(queue.size() == 1 && lifecycle.pending(), "coalesced restart"); queue.remove().run();
    check(runs.get() == 1 && !lifecycle.pending(), "latest state restarts once");
    lifecycle.request(); lifecycle.close(); queue.remove().run(); check(runs.get() == 1, "disposed queued restart suppressed");
    AtomicInteger submissions = new AtomicInteger();
    var retry = new FrontendSettingsLifecycle(command -> { if (submissions.incrementAndGet() == 1) throw new RejectedExecutionException(); queue.add(command); }, runs::incrementAndGet);
    try { retry.request(); throw new AssertionError("submission accepted"); } catch (RejectedExecutionException expected) { }
    check(retry.pending() && retry.failure() != null, "rejected restart remains pending"); retry.request(); queue.remove().run();
    check(submissions.get() == 2 && !retry.pending() && retry.failure() == null, "rejected worker retried");
    AtomicInteger attempts = new AtomicInteger();
    var callbackRetry = new FrontendSettingsLifecycle(queue::add, () -> { if (attempts.incrementAndGet() == 1) throw new IllegalStateException(); });
    callbackRetry.request(); queue.remove().run(); check(callbackRetry.pending(), "restart failure pending");
    callbackRetry.request(); queue.remove().run(); check(!callbackRetry.pending() && attempts.get() == 2, "restart failure retried");
  }

  private static void settings() throws Exception {
    ArrayDeque<Runnable> queue = new ArrayDeque<>(); AtomicInteger restarts = new AtomicInteger();
    var settings = new FrontendProjectSettings(queue::add, restarts::incrementAndGet);
    check(settings.enabled() && settings.getState().enabled, "product enabled by default");
    long revision = settings.generation(); settings.setEnabled(false);
    check(!settings.active(revision) && settings.restartPending() && queue.size() == 1, "disable invalidates pending startup");
    settings.setEnabled(true); check(!settings.active(revision), "old descriptor remains cancelled after reenable");
    queue.remove().run(); check(restarts.get() == 1, "coalesced settings restart");
    var copy = settings.getState(); copy.enabled = false; check(settings.enabled(), "persistent state defensive copy");
    settings.loadState(copy); check(!settings.enabled() && settings.restartPending(), "external project state reload restarts provider"); queue.remove().run();
    SwingUtilities.invokeAndWait(() -> {
      var configurable = new FrontendProjectConfigurable(settings); var component = (JPanel) configurable.createComponent();
      JCheckBox checkbox = (JCheckBox) ((JPanel) component.getComponent(0)).getComponent(0);
      check(!checkbox.isSelected() && !configurable.isModified(), "native panel reset"); checkbox.setSelected(true);
      check(configurable.isModified(), "native panel modified");
      try { configurable.apply(); } catch (Exception error) { throw new AssertionError(error); }
      check(settings.enabled(), "native panel applies"); configurable.disposeUIResources();
    });
    settings.dispose(); queue.remove().run(); check(restarts.get() == 2 && !settings.enabled(), "settings dispose suppresses queued callback");
    AtomicInteger calls = new AtomicInteger();
    var rejection = new FrontendProjectSettings(command -> { if (calls.incrementAndGet() == 1) throw new RejectedExecutionException(); queue.add(command); }, () -> {});
    try { rejection.setEnabled(false); throw new AssertionError("accepted rejected pool"); } catch (RejectedExecutionException expected) { }
    check(!rejection.enabled() && rejection.restartPending(), "disabled state retained on rejection");
    rejection.setEnabled(false); queue.remove().run(); check(!rejection.restartPending() && calls.get() == 2, "same-value Apply retries");
  }

  private static void bundle(Path root) throws Exception {
    Path plugin = root.resolve("plugin"), system = root.resolve("system"), project = root.resolve("project 中文🚀");
    Files.createDirectories(system); Files.createDirectories(project);
    var layout = FrontendBundledRuntime.layout(plugin, system, "project_0123", project, "macos-arm64");
    JsonObject files = new JsonObject();
    for (String name : new String[]{"node/bin/node", "typescript-language-server/lib/cli.mjs", "typescript/lib/tsserver.js"}) {
      Path path = layout.runtime().resolve(name); Files.createDirectories(path.getParent());
      byte[] data = ("owned inert test payload " + name).getBytes(StandardCharsets.UTF_8); Files.write(path, data);
      JsonObject value = new JsonObject(); value.addProperty("size", data.length); value.addProperty("sha256", HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data))); files.add(name, value);
    }
    check(layout.node().toFile().setExecutable(true, true), "owned inert executable flag");
    JsonObject expected = new JsonObject(); expected.add("files", files);
    expected.add("entries", JsonParser.parseString("{\"node\":\"node/bin/node\",\"typescriptLanguageServer\":\"typescript-language-server/lib/cli.mjs\",\"typescriptServer\":\"typescript/lib/tsserver.js\"}"));
    JsonObject manifest = expected.deepCopy(); manifest.addProperty("schema", 1); manifest.addProperty("target", layout.target());
    manifest.addProperty("owner", FrontendBundledRuntime.OWNER); manifest.addProperty("lockSha256", FrontendBundledRuntime.LOCK_SHA256);
    Path receipt = layout.runtime().resolve("bundled-runtime.json"); write(receipt, manifest);
    check(FrontendBundledRuntime.authenticate(layout, expected, () -> true).equals(layout), "complete owned payload authenticated");
    check(Files.isDirectory(layout.state().resolve("cache/npm")) && !Files.exists(project.resolve(".m0-runtime")), "state exclusively in IDE system");
    var environment = FrontendBundledRuntime.environment(layout);
    check(environment.get("HOME").startsWith(system.toString()) && environment.get("TMPDIR").startsWith(system.toString())
        && environment.get("NODE_OPTIONS").isEmpty() && !environment.containsKey("GITHUB_TOKEN") && !environment.containsKey("NPM_TOKEN")
        && !environment.containsKey("SSH_AUTH_SOCK") && !environment.containsKey("NODE_EXTRA_CA_CERTS"), "isolated analysis environment");
    check(FrontendBundledRuntime.initializationOptions(layout).toString().contains("disableAutomaticTypingAcquisition=true")
        && FrontendBundledRuntime.initializationOptions(layout).toString().contains(layout.tsserver().toString()), "explicit pinned TS without ATA");
    var command = FrontendBundledRuntime.command(layout);
    check(command.getExePath().equals(layout.node().toString()) && command.getCommandLineList(null).contains(layout.server().toString()), "explicit bundled command constructed only");
    rejected(() -> FrontendBundledRuntime.authenticate(layout, expected, () -> false), "cancelled start");
    AtomicInteger cancellation = new AtomicInteger(); BooleanSupplier limited = () -> cancellation.incrementAndGet() < 12;
    rejected(() -> FrontendBundledRuntime.authenticate(layout, expected, limited), "cancel during payload scan/hash");
    SwingUtilities.invokeAndWait(() -> {
      try { rejected(() -> FrontendBundledRuntime.authenticate(layout, expected, () -> true), "EDT filesystem work"); }
      catch (Exception error) { throw new AssertionError(error); }
      FrontendBundledRuntime.layout(plugin, system, "memory_only", project, "macos-arm64");
      FrontendBundledRuntime.initializationOptions(layout);
    });
    manifest.addProperty("runtimeRoot", layout.runtime().toString()); write(receipt, manifest);
    rejected(() -> FrontendBundledRuntime.authenticate(layout, expected, () -> true), "absolute runtimeRoot/extra metadata"); manifest.remove("runtimeRoot");
    manifest.addProperty("schema", 1.0); write(receipt, manifest); rejected(() -> FrontendBundledRuntime.authenticate(layout, expected, () -> true), "nonliteral schema"); manifest.addProperty("schema", 1);
    manifest.addProperty("target", "windows-x64"); write(receipt, manifest); rejected(() -> FrontendBundledRuntime.authenticate(layout, expected, () -> true), "wrong native target"); manifest.addProperty("target", layout.target());
    manifest.addProperty("lockSha256", "0".repeat(64)); write(receipt, manifest); rejected(() -> FrontendBundledRuntime.authenticate(layout, expected, () -> true), "wrong lock"); manifest.addProperty("lockSha256", FrontendBundledRuntime.LOCK_SHA256); write(receipt, manifest);
    Path extra = layout.runtime().resolve("unexpected.txt"); Files.writeString(extra, "extra");
    rejected(() -> FrontendBundledRuntime.authenticate(layout, expected, () -> true), "extra runtime file"); Files.delete(extra);
    Path server = layout.server(); byte[] original = Files.readAllBytes(server); Files.writeString(server, "mutated");
    rejected(() -> FrontendBundledRuntime.authenticate(layout, expected, () -> true), "mutated payload"); Files.write(server, original);
    Files.delete(server); Files.createSymbolicLink(server, root.resolve("external"));
    rejected(() -> FrontendBundledRuntime.authenticate(layout, expected, () -> true), "payload symlink"); Files.delete(server); Files.write(server, original);
    Path tmp = layout.state().resolve("tmp"); Files.delete(tmp); Files.createSymbolicLink(tmp, project);
    rejected(() -> FrontendBundledRuntime.authenticate(layout, expected, () -> true), "state symlink"); Files.delete(tmp);
    check(FrontendBundledRuntime.authenticate(layout, expected, () -> true).equals(layout), "recovery after rejected mutations");
    rejected(() -> FrontendBundledRuntime.authenticate(layout, () -> true), "missing authenticated JAR resources");
    check(!FrontendBundledRuntime.exact(JsonParser.parseString("{\"n\":[9007199254740992]}"), JsonParser.parseString("{\"n\":[9007199254740993]}")), "exact nested large-number identity");
    check(!FrontendBundledRuntime.exact(JsonParser.parseString("1"), JsonParser.parseString("\"1\"")), "numeric/string identity");
    check(!FrontendBundledRuntime.exact(JsonParser.parseString("{\"a\":null}"), JsonParser.parseString("{}")), "null/absent identity");
  }
  private static void write(Path path, JsonObject value) throws IOException { Files.writeString(path, value.toString()); }
}
