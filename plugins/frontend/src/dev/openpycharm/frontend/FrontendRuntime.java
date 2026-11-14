package dev.openpycharm.frontend;

import com.google.gson.JsonObject;
import com.intellij.execution.configurations.GeneralCommandLine;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;
import javax.swing.SwingUtilities;

/** Worker-only authentication. It never downloads, installs, or writes a runtime cache. */
final class FrontendRuntime {
  static final String OWNER = "OpenPyCharm frontend M0";
  record Verified(Path node, Path server, Path tsserver, Path fixture, Path state) {}

  private FrontendRuntime() {}

  static Verified authenticate(FrontendFixtureScope.Configuration configuration) throws IOException {
    if (SwingUtilities.isEventDispatchThread()) throw new IOException("Frontend authentication requires a worker thread");
    Path fixture = noLinks(Path.of(configuration.fixture()));
    Path fixtureParent = noLinks(Path.of(FrontendBuildScope.FIXTURE_PARENT));
    if (!fixture.getParent().equals(fixtureParent) || !Files.isDirectory(fixture, LinkOption.NOFOLLOW_LINKS))
      throw new IOException("Frontend M0 fixture escaped its compiled owned boundary");
    JsonObject marker = json(fixture.resolve(".openpycharm-frontend-m0.json"));
    if (!OWNER.equals(string(marker, "owner")) || !configuration.nonce().equals(string(marker, "nonce"))
        || !configuration.fixture().equals(string(marker, "fixtureRoot"))
        || !configuration.receipt().equals(string(marker, "toolsReceipt"))
        || !configuration.receiptSha256().equals(string(marker, "toolsReceiptSha256"))
        || !FrontendBuildScope.LOCK_SHA256.equals(string(marker, "lockSha256")))
      throw new IOException("Frontend M0 fixture marker differs from its explicit activation");
    Path receipt = noLinks(Path.of(configuration.receipt()));
    Path cacheParent = noLinks(Path.of(FrontendBuildScope.CACHE_PARENT));
    if (!receipt.startsWith(cacheParent) || !Files.isRegularFile(receipt, LinkOption.NOFOLLOW_LINKS)
        || Files.size(receipt) > 1_000_000 || !sha(receipt).equals(configuration.receiptSha256()))
      throw new IOException("Frontend runtime receipt is outside the owned cache or changed");
    JsonObject tools = json(receipt);
    String target = string(tools, "target");
    String nativeTarget = System.getProperty("os.name").startsWith("Windows") ? "windows-x64" : "macos-arm64";
    if (!nativeTarget.equals(target) || !OWNER.equals(string(tools, "owner"))
        || !FrontendBuildScope.LOCK_SHA256.equals(string(tools, "lockSha256"))
        || tools.get("installationScriptsExecuted").getAsBoolean()) throw new IOException("Frontend tool source/target identity differs");
    Path runtime = noLinks(Path.of(string(tools, "runtimeRoot")));
    if (!runtime.startsWith(cacheParent) || !receipt.equals(runtime.resolve("frontend-tools.json")))
      throw new IOException("Frontend receipt runtime root differs from its owned location");
    JsonObject expected;
    try (InputStream stream = FrontendRuntime.class.getResourceAsStream("/META-INF/frontend-runtime-" + target + ".json")) {
      if (stream == null) throw new IOException("Missing compiled frontend payload manifest");
      expected = JsonParser.parseString(new String(stream.readNBytes(1_000_001), StandardCharsets.UTF_8)).getAsJsonObject();
    }
    JsonObject files = tools.getAsJsonObject("files");
    if (!expected.getAsJsonObject("files").equals(files) || !expected.getAsJsonObject("entries").equals(tools.getAsJsonObject("entries")))
      throw new IOException("Frontend receipt payload/entry closure differs from the compiled lock");
    Set<String> actual = new HashSet<>();
    try (var paths = Files.walk(runtime)) {
      var iterator = paths.iterator(); int visited = 0;
      while (iterator.hasNext()) {
        Path path = iterator.next();
        if (++visited > files.size() * 4 + 32) throw new IOException("Frontend runtime tree exceeds its pinned bound");
        noLinks(path);
        if (Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) actual.add(runtime.relativize(path).toString().replace('\\', '/'));
        else if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Special frontend runtime file");
      }
    }
    Set<String> wanted = new HashSet<>(files.keySet()); wanted.add("frontend-tools.json");
    if (!actual.equals(wanted)) throw new IOException("Frontend runtime payload set changed");
    for (String name : files.keySet()) {
      Path path = noLinks(runtime.resolve(relative(name)));
      JsonObject entry = files.getAsJsonObject(name);
      if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || Files.size(path) != entry.get("size").getAsLong()
          || !sha(path).equals(string(entry, "sha256"))) throw new IOException("Frontend runtime file differs from the compiled lock: " + name);
    }
    Path state = fixture.resolve(".m0-runtime");
    for (String name : new String[]{"home", "tmp", "cache", "cache/npm", "log"}) {
      if (!Files.isDirectory(noLinks(state.resolve(name)), LinkOption.NOFOLLOW_LINKS))
        throw new IOException("Frontend fixture state directories must be prepared explicitly");
    }
    JsonObject entries = tools.getAsJsonObject("entries");
    Path node = noLinks(runtime.resolve(relative(string(entries, "node"))));
    if (!Files.isExecutable(node)) throw new IOException("Pinned Node is not executable");
    return new Verified(node, runtime.resolve(relative(string(entries, "typescriptLanguageServer"))),
        runtime.resolve(relative(string(entries, "typescriptServer"))), fixture, state);
  }

  static GeneralCommandLine command(Verified verified) {
    return new GeneralCommandLine(verified.node().toString(), verified.server().toString(), "--stdio", "--log-level", "2")
        .withParentEnvironmentType(GeneralCommandLine.ParentEnvironmentType.NONE)
        .withEnvironment(environment(verified)).withWorkDirectory(verified.fixture().toString()).withCharset(StandardCharsets.UTF_8);
  }

  static Map<String, String> environment(Verified runtime) {
    Map<String, String> environment = new HashMap<>(); Path state = runtime.state();
    environment.put("PATH", runtime.node().getParent().toString());
    environment.put("HOME", state.resolve("home").toString()); environment.put("USERPROFILE", state.resolve("home").toString());
    for (String key : new String[]{"TMPDIR", "TMP", "TEMP"}) environment.put(key, state.resolve("tmp").toString());
    environment.put("XDG_CACHE_HOME", state.resolve("cache").toString()); environment.put("NPM_CONFIG_CACHE", state.resolve("cache/npm").toString());
    for (String key : new String[]{"NODE_OPTIONS", "NODE_PATH", "TSS_LOG"}) environment.put(key, "");
    for (String key : new String[]{"SystemRoot", "WINDIR", "COMSPEC"}) {
      String value = System.getenv(key); if (value != null) environment.put(key, value);
    }
    return environment;
  }

  private static String relative(String value) throws IOException {
    if (value.isEmpty() || value.startsWith("/") || value.contains("\\") || value.contains(":") || value.contains("\0")
        || value.contains("\r") || value.contains("\n") || !Path.of(value).normalize().toString().replace('\\', '/').equals(value))
      throw new IOException("Invalid frontend relative payload path");
    for (String part : value.split("/", -1)) if (part.isEmpty() || part.equals(".") || part.equals(".."))
      throw new IOException("Frontend payload path cannot traverse ancestors");
    return value;
  }

  private static Path noLinks(Path path) throws IOException {
    if (!path.isAbsolute() || !path.normalize().equals(path)) throw new IOException("Expected an absolute normalized frontend path");
    for (Path current = path; current != null; current = current.getParent())
      if (Files.isSymbolicLink(current)) throw new IOException("Frontend paths cannot contain symlinks");
    return path;
  }

  private static JsonObject json(Path path) throws IOException {
    noLinks(path);
    if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || Files.size(path) > 1_000_000)
      throw new IOException("Frontend metadata must be a bounded regular file");
    return JsonParser.parseString(Files.readString(path)).getAsJsonObject();
  }

  private static String string(JsonObject object, String key) throws IOException {
    if (object == null || !object.has(key) || !object.get(key).isJsonPrimitive() || !object.get(key).getAsJsonPrimitive().isString())
      throw new IOException("Missing frontend metadata string: " + key);
    return object.get(key).getAsString();
  }

  private static String sha(Path path) throws IOException {
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      try (InputStream stream = Files.newInputStream(path)) {
        byte[] block = new byte[65536]; int count;
        while ((count = stream.read(block)) != -1) digest.update(block, 0, count);
      }
      return HexFormat.of().formatHex(digest.digest());
    } catch (NoSuchAlgorithmException error) { throw new AssertionError(error); }
  }
}
