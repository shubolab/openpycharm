package dev.openpycharm.frontend;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.intellij.execution.configurations.GeneralCommandLine;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;
import java.util.function.BooleanSupplier;
import javax.swing.SwingUtilities;

/** Read-only bundled-tool authentication; all filesystem work is worker-only. */
final class FrontendBundledRuntime {
  static final String OWNER = "OpenPyCharm bundled frontend";
  static final String LOCK_SHA256 = "5a7b20ce2ce915a4012b4ea5dfa35b77c709bdbb19de00be87700404a6f6fff2";
  static final String VERSION_LABEL = "Bundled Node.js 24.22.3 · TypeScript 6.0.3 · typescript-language-server 6.1.0";
  private static final int METADATA_LIMIT = 1_000_000;
  private static final Set<String> MANIFEST_KEYS = Set.of("schema", "target", "owner", "lockSha256", "files", "entries");
  record Layout(Path plugin, Path runtime, Path node, Path server, Path tsserver, Path system, Path state, Path project, String target) {}

  private FrontendBundledRuntime() {}

  /** Path construction only: safe for fileOpened and initialize-options callbacks in either order. */
  static Layout layout(Path plugin, Path system, String projectHash, Path project, String target) {
    FrontendProductScope.absolute(plugin); FrontendProductScope.absolute(system); FrontendProductScope.absolute(project);
    if (!Set.of("macos-arm64", "windows-x64").contains(target)) throw new IllegalArgumentException("Unsupported frontend runtime target");
    Path runtime = plugin.resolve("runtime").resolve(target);
    return new Layout(plugin, runtime, runtime.resolve(target.equals("macos-arm64") ? "node/bin/node" : "node/node.exe"),
        runtime.resolve("typescript-language-server/lib/cli.mjs"), runtime.resolve("typescript/lib/tsserver.js"),
        system, system.resolve("frontend").resolve(FrontendProductScope.locationComponent(projectHash)), project, target);
  }

  static Layout authenticate(Layout layout, BooleanSupplier active) throws IOException {
    worker(); checkActive(active);
    byte[] lockBytes = resource("/META-INF/frontend-tools.lock.json");
    if (!sha(lockBytes).equals(LOCK_SHA256)) throw new IOException("Bundled frontend lock changed");
    JsonObject expected = expected(parse(lockBytes), layout.target());
    JsonObject supplied = parse(resource("/META-INF/frontend-runtime-" + layout.target() + ".json"));
    if (!exact(expected, supplied) || expected.getAsJsonObject("files").size() != 191)
      throw new IOException("Bundled frontend compiled payload closure differs from its pinned lock");
    return authenticate(layout, expected, active);
  }

  /** Package-private to exercise real filesystem rejection paths with small owned payloads. */
  static Layout authenticate(Layout layout, JsonObject expected, BooleanSupplier active) throws IOException {
    worker(); checkActive(active);
    Path runtime = noLinks(layout.runtime()); noLinks(layout.plugin());
    JsonObject manifest = json(runtime.resolve("bundled-runtime.json"));
    if (!manifest.keySet().equals(MANIFEST_KEYS) || !manifest.has("schema") || !manifest.get("schema").isJsonPrimitive()
        || !manifest.get("schema").getAsJsonPrimitive().isNumber() || !manifest.get("schema").getAsString().equals("1")
        || !layout.target().equals(string(manifest, "target")) || !OWNER.equals(string(manifest, "owner"))
        || !LOCK_SHA256.equals(string(manifest, "lockSha256")) || !exact(expected.get("files"), manifest.get("files"))
        || !exact(expected.get("entries"), manifest.get("entries")))
      throw new IOException("Bundled frontend runtime identity or complete payload manifest changed");
    JsonObject files = expected.getAsJsonObject("files");
    if (files == null || files.isEmpty() || files.size() > 191) throw new IOException("Invalid bundled frontend payload bound");
    JsonObject entries = expected.getAsJsonObject("entries");
    Map<String, String> names = Map.of("node", runtime.relativize(layout.node()).toString().replace('\\', '/'),
        "typescriptLanguageServer", "typescript-language-server/lib/cli.mjs", "typescriptServer", "typescript/lib/tsserver.js");
    if (entries == null || !entries.keySet().equals(names.keySet())) throw new IOException("Invalid bundled frontend entry points");
    for (var name : names.entrySet())
      if (!name.getValue().equals(string(entries, name.getKey())) || !files.has(name.getValue()))
        throw new IOException("Bundled frontend entry point changed");
    Set<String> actual = new HashSet<>();
    try (var paths = Files.walk(runtime)) {
      var iterator = paths.iterator(); int visited = 0;
      while (iterator.hasNext()) {
        checkActive(active); Path path = iterator.next();
        if (++visited > files.size() * 4 + 32) throw new IOException("Bundled frontend runtime tree exceeds its pinned bound");
        noLinks(path);
        if (Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) actual.add(runtime.relativize(path).toString().replace('\\', '/'));
        else if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Special bundled frontend file");
      }
    } catch (java.io.UncheckedIOException error) { throw error.getCause(); }
    Set<String> wanted = new HashSet<>(files.keySet()); wanted.add("bundled-runtime.json");
    if (!actual.equals(wanted)) throw new IOException("Bundled frontend payload set changed");
    for (String name : files.keySet()) {
      checkActive(active); Path path = noLinks(runtime.resolve(relative(name)));
      JsonObject entry = files.getAsJsonObject(name);
      if (entry == null || !entry.keySet().equals(Set.of("size", "sha256")) || !entry.get("size").isJsonPrimitive()
          || !entry.get("size").getAsJsonPrimitive().isNumber() || !entry.get("size").getAsString().matches("0|[1-9][0-9]{0,11}")
          || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || Files.size(path) != entry.get("size").getAsLong()
          || !sha(path, active).equals(string(entry, "sha256")))
        throw new IOException("Bundled frontend payload differs from its pinned lock: " + name);
    }
    if (!Files.isExecutable(layout.node())) throw new IOException("Bundled frontend Node is not executable");
    if (!Files.isDirectory(layout.project())) throw new IOException("Frontend project directory no longer exists");
    checkActive(active); prepareState(layout); checkActive(active);
    return layout;
  }

  static GeneralCommandLine command(Layout layout) {
    return new GeneralCommandLine(layout.node().toString(), layout.server().toString(), "--stdio", "--log-level", "2")
        .withParentEnvironmentType(GeneralCommandLine.ParentEnvironmentType.NONE).withEnvironment(environment(layout))
        .withWorkDirectory(layout.project().toString()).withCharset(StandardCharsets.UTF_8);
  }

  static Map<String, String> environment(Layout layout) {
    Map<String, String> result = new HashMap<>(); Path state = layout.state();
    result.put("PATH", layout.node().getParent().toString());
    result.put("HOME", state.resolve("home").toString()); result.put("USERPROFILE", state.resolve("home").toString());
    for (String key : new String[]{"TMPDIR", "TMP", "TEMP"}) result.put(key, state.resolve("tmp").toString());
    result.put("XDG_CACHE_HOME", state.resolve("cache").toString()); result.put("NPM_CONFIG_CACHE", state.resolve("cache/npm").toString());
    for (String key : new String[]{"NODE_OPTIONS", "NODE_PATH", "TSS_LOG"}) result.put(key, "");
    for (String key : new String[]{"SystemRoot", "WINDIR", "COMSPEC"}) {
      String value = System.getenv(key); if (value != null) result.put(key, value);
    }
    return result;
  }

  static Object initializationOptions(Layout layout) {
    return Map.of("hostInfo", "OpenPyCharm", "disableAutomaticTypingAcquisition", true,
        "tsserver", Map.of("path", layout.tsserver().toString(), "logDirectory", layout.state().resolve("log").toString()));
  }

  private static void prepareState(Layout layout) throws IOException {
    Path system = noLinks(layout.system());
    if (!Files.isDirectory(system, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Frontend IDE system directory is unavailable");
    directory(system.resolve("frontend")); directory(layout.state());
    for (String child : new String[]{"home", "tmp", "cache", "cache/npm", "log"}) directory(layout.state().resolve(child));
  }

  private static void directory(Path path) throws IOException {
    noLinks(path);
    try {
      if (!Files.exists(path, LinkOption.NOFOLLOW_LINKS)) {
        if (Files.getFileStore(path.getParent()).supportsFileAttributeView("posix"))
          Files.createDirectory(path, PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
        else Files.createDirectory(path);
      }
    } catch (java.nio.file.FileAlreadyExistsException concurrentCreate) { /* Recheck type below. */ }
    noLinks(path);
    if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Frontend state path is not a regular directory");
  }

  private static JsonObject expected(JsonObject lock, String target) throws IOException {
    JsonObject files = new JsonObject(); String node = null;
    if (!lock.has("artifacts") || !lock.get("artifacts").isJsonArray()) throw new IOException("Missing frontend lock artifacts");
    for (JsonElement element : lock.getAsJsonArray("artifacts")) {
      JsonObject artifact = element.getAsJsonObject();
      if (artifact.has("target") && !target.equals(string(artifact, "target"))) continue;
      JsonObject payload = artifact.getAsJsonObject("payload");
      for (String name : payload.keySet()) {
        relative(name); if (files.has(name)) throw new IOException("Overlapping frontend lock payload"); files.add(name, payload.get(name));
      }
      if (string(artifact, "id").startsWith("node-")) node = string(artifact, "nodeExecutable");
    }
    if (node == null) throw new IOException("Missing frontend Node entry point");
    JsonObject entries = lock.getAsJsonObject("runtimeEntries").deepCopy(); entries.addProperty("node", node);
    JsonObject result = new JsonObject(); result.add("files", files); result.add("entries", entries); return result;
  }

  /** Literal, recursive comparison: avoids Gson's lossy numeric equality at and above 2^53. */
  static boolean exact(JsonElement left, JsonElement right) {
    if (left == null || right == null) return left == right;
    if (left.isJsonNull() || right.isJsonNull()) return left.isJsonNull() && right.isJsonNull();
    if (left.isJsonObject() && right.isJsonObject()) {
      var a = left.getAsJsonObject(); var b = right.getAsJsonObject();
      if (!a.keySet().equals(b.keySet())) return false;
      for (String key : a.keySet()) if (!exact(a.get(key), b.get(key))) return false;
      return true;
    }
    if (left.isJsonArray() && right.isJsonArray()) {
      var a = left.getAsJsonArray(); var b = right.getAsJsonArray();
      if (a.size() != b.size()) return false;
      for (int i = 0; i < a.size(); i++) if (!exact(a.get(i), b.get(i))) return false;
      return true;
    }
    if (!left.isJsonPrimitive() || !right.isJsonPrimitive()) return false;
    var a = left.getAsJsonPrimitive(); var b = right.getAsJsonPrimitive();
    return a.isString() == b.isString() && a.isNumber() == b.isNumber() && a.isBoolean() == b.isBoolean()
        && a.getAsString().equals(b.getAsString());
  }

  private static void worker() throws IOException {
    if (SwingUtilities.isEventDispatchThread()) throw new IOException("Bundled frontend authentication requires a worker thread");
  }
  private static void checkActive(BooleanSupplier active) throws IOException {
    if (Thread.currentThread().isInterrupted() || !active.getAsBoolean()) throw new IOException("Frontend startup was cancelled");
  }
  private static Path noLinks(Path path) throws IOException {
    try { FrontendProductScope.absolute(path); } catch (IllegalArgumentException error) { throw new IOException(error); }
    for (Path current = path; current != null; current = current.getParent())
      if (Files.isSymbolicLink(current)) throw new IOException("Frontend paths cannot contain symlinks");
    return path;
  }
  private static String relative(String value) throws IOException {
    if (value.isBlank() || value.startsWith("/") || value.contains("\\") || value.contains(":")
        || value.chars().anyMatch(c -> c < 32 || c == 127)) throw new IOException("Invalid frontend payload path");
    for (String part : value.split("/", -1)) if (part.isEmpty() || part.equals(".") || part.equals(".."))
      throw new IOException("Frontend payload path traverses ancestors");
    return value;
  }
  private static byte[] resource(String name) throws IOException {
    try (InputStream stream = FrontendBundledRuntime.class.getResourceAsStream(name)) {
      if (stream == null) throw new IOException("Missing compiled frontend resource: " + name);
      return bounded(stream);
    }
  }
  private static byte[] bounded(InputStream stream) throws IOException {
    byte[] bytes = stream.readNBytes(METADATA_LIMIT + 1);
    if (bytes.length > METADATA_LIMIT) throw new IOException("Frontend metadata exceeds its bound"); return bytes;
  }
  private static JsonObject json(Path path) throws IOException {
    noLinks(path);
    if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || Files.size(path) > METADATA_LIMIT)
      throw new IOException("Frontend metadata must be a bounded regular file");
    try (InputStream stream = Files.newInputStream(path)) { return parse(bounded(stream)); }
  }
  private static JsonObject parse(byte[] bytes) throws IOException {
    try { return JsonParser.parseString(new String(bytes, StandardCharsets.UTF_8)).getAsJsonObject(); }
    catch (RuntimeException error) { throw new IOException("Invalid frontend metadata", error); }
  }
  private static String string(JsonObject object, String key) throws IOException {
    if (object == null || !object.has(key) || !object.get(key).isJsonPrimitive() || !object.get(key).getAsJsonPrimitive().isString())
      throw new IOException("Missing frontend metadata string: " + key); return object.get(key).getAsString();
  }
  private static MessageDigest digest() {
    try { return MessageDigest.getInstance("SHA-256"); } catch (NoSuchAlgorithmException error) { throw new AssertionError(error); }
  }
  private static String sha(byte[] bytes) { return HexFormat.of().formatHex(digest().digest(bytes)); }
  private static String sha(Path path, BooleanSupplier active) throws IOException {
    MessageDigest digest = digest();
    try (InputStream stream = Files.newInputStream(path)) {
      byte[] block = new byte[65536]; int count;
      while ((count = stream.read(block)) != -1) { checkActive(active); digest.update(block, 0, count); }
    }
    return HexFormat.of().formatHex(digest.digest());
  }
}
