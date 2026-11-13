package dev.openpycharm.frameworks;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CancellationException;

/** Standalone filesystem checks; no IDE services or framework package installation. */
public final class FrameworkProjectFilesTest {
  private static int checks;
  private static void require(boolean condition, String message) {
    checks++;
    if (!condition) throw new AssertionError(message);
  }
  private static void failsIO(IORunnable action) throws Exception {
    try { action.run(); throw new AssertionError("Unsafe write succeeded"); }
    catch (IOException expected) { checks++; }
  }
  private interface IORunnable { void run() throws Exception; }

  public static void main(String[] arguments) throws Exception {
    Path temporary = Files.createTempDirectory("framework templates 中文 ").toRealPath();
    boolean symlinks = false;
    try {
      for (FrameworkKind kind : FrameworkKind.values()) {
        Map<String, String> plan = FrameworkProjectFiles.plan(kind);
        require(new ArrayList<>(plan.keySet()).equals(new ArrayList<>(FrameworkProjectFiles.plan(kind).keySet())), "Deterministic order");
        require(plan.equals(FrameworkProjectFiles.plan(kind)), "Deterministic content");
        try { plan.put("extra.py", ""); throw new AssertionError("Mutable plan"); }
        catch (UnsupportedOperationException expected) { checks++; }
        require(plan.containsKey("requirements.txt") && plan.containsKey("README.md"), "Dependencies and instructions");
        String app = plan.get(kind == FrameworkKind.DJANGO ? "project_config/urls.py" : "app.py");
        require(app.contains("OPENPYCHARM_FRAMEWORK_PROBE") && app.contains("\"marker\"")
            && app.contains("\"" + kind.name().toLowerCase(java.util.Locale.ROOT) + "\""), "Real endpoint and environment marker");
        Path project = temporary.resolve(kind.name());
        Files.createDirectories(project.resolve(".venv"));
        Files.createDirectories(project.resolve(".idea"));
        Files.writeString(project.resolve(".venv/keep"), "interpreter");
        Files.writeString(project.resolve("notes.txt"), "user content");
        FrameworkProjectFiles.write(project, kind, () -> { });
        for (Map.Entry<String, String> file : plan.entrySet()) {
          require(Files.readString(project.resolve(file.getKey())).equals(file.getValue()), "Exact template bytes " + file.getKey());
        }
        require(Files.readString(project.resolve(".venv/keep")).equals("interpreter"), "Existing interpreter preserved");
        require(Files.readString(project.resolve("notes.txt")).equals("user content"), "Unrelated content preserved");
        failsIO(() -> FrameworkProjectFiles.write(project, kind, () -> { }));
        require(Files.readString(project.resolve("notes.txt")).equals("user content"), "Retry never overwrites");
      }
      require(FrameworkProjectFiles.plan(FrameworkKind.DJANGO).get("requirements.txt").equals("Django==5.2.8\n"), "Django pin");
      require(FrameworkProjectFiles.plan(FrameworkKind.FLASK).get("requirements.txt").equals("Flask==3.1.2\n"), "Flask pin");
      require(FrameworkProjectFiles.plan(FrameworkKind.FASTAPI).get("requirements.txt").equals("fastapi==0.121.0\nuvicorn==0.38.0\n"), "ASGI pins");
      require(FrameworkProjectFiles.plan(FrameworkKind.DJANGO).get("manage.py").contains("project_config.settings"), "Django settings entry point");

      // A collision in the LAST planned file prevents even the first file from being created.
      Path collision = Files.createDirectory(temporary.resolve("collision"));
      Files.writeString(collision.resolve("README.md"), "existing readme");
      failsIO(() -> FrameworkProjectFiles.write(collision, FrameworkKind.DJANGO, () -> { }));
      require(!Files.exists(collision.resolve("requirements.txt")), "Whole-plan collision preflight");
      require(Files.readString(collision.resolve("README.md")).equals("existing readme"), "Collision unchanged");
      Path parentFile = Files.createDirectory(temporary.resolve("parent-file"));
      Files.writeString(parentFile.resolve("project_config"), "user file");
      failsIO(() -> FrameworkProjectFiles.write(parentFile, FrameworkKind.DJANGO, () -> { }));
      require(!Files.exists(parentFile.resolve("manage.py")), "Non-directory parent preflight");

      // Cancel at every callback boundary, including after directories/files were created.
      for (FrameworkKind kind : FrameworkKind.values()) {
        boolean reachedSuccess = false;
        for (int boundary = 1; boundary < 120; boundary++) {
          Path root = Files.createDirectory(temporary.resolve("cancel-" + kind + "-" + boundary));
          Files.createDirectory(root.resolve(".idea"));
          Files.writeString(root.resolve("keep.txt"), "keep");
          final int stop = boundary;
          final int[] calls = {0};
          try {
            FrameworkProjectFiles.write(root, kind, () -> {
              if (++calls[0] == stop) throw new CancellationException("test cancellation");
            });
            reachedSuccess = true;
            break;
          }
          catch (CancellationException expected) {
            require(Files.readString(root.resolve("keep.txt")).equals("keep"), "Cancellation preserves unrelated file");
            require(Files.isDirectory(root.resolve(".idea")), "Cancellation preserves IDE directory");
            try (var paths = Files.list(root)) {
              require(paths.count() == 2, "Cancellation removes only generated entries");
            }
          }
        }
        require(reachedSuccess, "Exercised every cancellation boundary for " + kind);
      }
      Path newRoot = temporary.resolve("new-parent/new-project");
      try {
        FrameworkProjectFiles.write(newRoot, FrameworkKind.DJANGO, () -> {
          if (Files.exists(newRoot.resolve("requirements.txt"))) throw new CancellationException("after first create");
        });
        throw new AssertionError("Expected cancellation");
      }
      catch (CancellationException expected) {
        require(!Files.exists(temporary.resolve("new-parent")), "Owned missing-root directories rolled back");
      }

      // Simulate a later external collision. Rollback must not remove the external file.
      Path late = Files.createDirectory(temporary.resolve("late-collision"));
      failsIO(() -> FrameworkProjectFiles.write(late, FrameworkKind.FLASK, () -> {
        if (Files.exists(late.resolve("requirements.txt")) && !Files.exists(late.resolve("app.py"))) {
          try { Files.writeString(late.resolve("app.py"), "external file"); }
          catch (IOException failure) { throw new RuntimeException(failure); }
        }
      }));
      require(Files.readString(late.resolve("app.py")).equals("external file"), "External collision preserved");
      require(!Files.exists(late.resolve("requirements.txt")), "Earlier owned file rolled back");

      Path destination = Files.createDirectory(temporary.resolve("symlink-target"));
      Path link = temporary.resolve("symlink-root");
      try {
        Files.createSymbolicLink(link, destination);
        symlinks = true;
      }
      catch (UnsupportedOperationException | IOException unavailable) { }
      if (symlinks) {
        failsIO(() -> FrameworkProjectFiles.write(link.resolve("project"), FrameworkKind.FLASK, () -> { }));
        require(!Files.exists(destination.resolve("project")), "Ancestor symlink never followed");
        Path nested = Files.createDirectory(temporary.resolve("nested-link"));
        Files.createSymbolicLink(nested.resolve("project_config"), destination);
        failsIO(() -> FrameworkProjectFiles.write(nested, FrameworkKind.DJANGO, () -> { }));
        require(!Files.exists(nested.resolve("requirements.txt")), "Nested symlink preflight");
        Path leaf = Files.createDirectory(temporary.resolve("leaf-link"));
        Files.createSymbolicLink(leaf.resolve("README.md"), destination.resolve("absent"));
        failsIO(() -> FrameworkProjectFiles.write(leaf, FrameworkKind.FLASK, () -> { }));
        require(Files.isSymbolicLink(leaf.resolve("README.md")), "Dangling leaf symlink preserved");
        require(!Files.exists(destination.resolve("absent")), "Dangling leaf never followed");
      }
      System.out.println("{\"status\":\"pass\",\"scope\":\"template plans and transactional filesystem writer\",\"checks\":"
          + checks + ",\"symlinksTested\":" + symlinks + "}");
    }
    finally {
      try (var paths = Files.walk(temporary)) {
        for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
      }
    }
  }
}
