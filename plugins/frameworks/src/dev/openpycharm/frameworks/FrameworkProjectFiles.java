package dev.openpycharm.frameworks;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** Independent small project templates. Call write on a cancellable worker, never the EDT. */
public final class FrameworkProjectFiles {
  private FrameworkProjectFiles() { }

  public static Map<String, String> plan(FrameworkKind kind) {
    Objects.requireNonNull(kind, "kind");
    Map<String, String> files = new LinkedHashMap<>();
    switch (kind) {
      case DJANGO -> {
        files.put("requirements.txt", "Django==5.2.8\n");
        files.put("manage.py", """
            #!/usr/bin/env python3
            import os
            import sys

            if __name__ == "__main__":
                os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project_config.settings")
                from django.core.management import execute_from_command_line

                execute_from_command_line(sys.argv)
            """);
        files.put("project_config/__init__.py", "");
        files.put("project_config/settings.py", """
            import os

            # Local development only. Supply a private secret before deployment.
            SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "openpycharm-local-development-only")
            DEBUG = False
            ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
            ROOT_URLCONF = "project_config.urls"
            INSTALLED_APPS = []
            MIDDLEWARE = []
            """);
        files.put("project_config/urls.py", """
            import os

            from django.http import JsonResponse
            from django.urls import path


            def index(request):
                marker = os.environ.get("OPENPYCHARM_FRAMEWORK_PROBE", "manual")
                return JsonResponse({"framework": "django", "marker": marker})


            urlpatterns = [path("", index)]
            """);
      }
      case FLASK -> {
        files.put("requirements.txt", "Flask==3.1.2\n");
        files.put("app.py", """
            import os

            from flask import Flask

            app = Flask(__name__)


            @app.get("/")
            def index():
                marker = os.environ.get("OPENPYCHARM_FRAMEWORK_PROBE", "manual")
                return {"framework": "flask", "marker": marker}
            """);
      }
      case FASTAPI -> {
        files.put("requirements.txt", "fastapi==0.121.0\nuvicorn==0.38.0\n");
        files.put("app.py", """
            import os

            from fastapi import FastAPI

            app = FastAPI()


            @app.get("/")
            def index():
                marker = os.environ.get("OPENPYCHARM_FRAMEWORK_PROBE", "manual")
                return {"framework": "fastapi", "marker": marker}
            """);
      }
    }
    files.put("README.md", "# " + kind.displayName() + " project\n\n"
        + "Use the project interpreter selected in OpenPyCharm. Install the pinned dependencies with "
        + "`python -m pip install -r requirements.txt`, then use the " + kind.displayName()
        + " Run or Debug configuration.\n\n"
        + "GET `/` returns the framework name and the `OPENPYCHARM_FRAMEWORK_PROBE` environment "
        + "variable (default: `manual`). The development server binds to localhost.\n\n"
        + "This is a small local development starter, not a production deployment configuration.\n");
    return Collections.unmodifiableMap(files);
  }

  /** Never replaces a file. Existing interpreter and IDE metadata directories are left alone. */
  public static void write(Path root, FrameworkKind kind, Runnable cancellationCheck) throws IOException {
    Objects.requireNonNull(root, "root");
    Objects.requireNonNull(cancellationCheck, "cancellationCheck");
    Path absolute = root.toAbsolutePath();
    Path base = absolute.normalize();
    Map<String, String> files = plan(kind);
    List<OwnedPath> created = new ArrayList<>();
    cancellationCheck.run();
    // Preflight the whole plan before creating any part of a project.
    checkDirectoryAncestors(absolute);
    checkDirectoryAncestors(base);
    for (String relative : files.keySet()) {
      cancellationCheck.run();
      Path target = resolve(base, relative);
      checkDirectoryAncestors(target.getParent());
      if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)) throw new FileAlreadyExistsException(target.toString());
    }
    try {
      for (Map.Entry<String, String> file : files.entrySet()) {
        cancellationCheck.run();
        Path target = resolve(base, file.getKey());
        createDirectories(target.getParent(), created, cancellationCheck);
        checkDirectoryAncestors(target.getParent());
        // CREATE_NEW and NOFOLLOW_LINKS also reject a last-moment leaf collision/symlink.
        try (SeekableByteChannel channel = Files.newByteChannel(target,
            Set.of(StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS))) {
          recordCreated(target, created);
          ByteBuffer data = StandardCharsets.UTF_8.encode(file.getValue());
          while (data.hasRemaining()) {
            cancellationCheck.run();
            channel.write(data);
          }
        }
        cancellationCheck.run();
      }
    }
    catch (IOException | RuntimeException | Error failure) {
      rollback(created, failure);
      throw failure;
    }
  }

  private static Path resolve(Path base, String relative) throws IOException {
    Path part = Path.of(relative);
    Path target = base.resolve(part).normalize();
    if (part.isAbsolute() || !target.startsWith(base) || target.equals(base)) {
      throw new IOException("Template path escapes the project directory: " + relative);
    }
    return target;
  }

  private static void checkDirectoryAncestors(Path directory) throws IOException {
    for (Path path = directory; path != null; path = path.getParent()) {
      if (Files.exists(path, LinkOption.NOFOLLOW_LINKS)) {
        BasicFileAttributes attributes = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (attributes.isSymbolicLink() || !attributes.isDirectory()) {
          throw new IOException("Project ancestor must be a real directory: " + path);
        }
      }
    }
  }

  private static void createDirectories(Path directory, List<OwnedPath> created, Runnable check) throws IOException {
    check.run();
    checkDirectoryAncestors(directory);
    if (Files.exists(directory, LinkOption.NOFOLLOW_LINKS)) return;
    Path parent = directory.getParent();
    if (parent != null) createDirectories(parent, created, check);
    check.run();
    checkDirectoryAncestors(parent);
    try {
      Files.createDirectory(directory);
      recordCreated(directory, created);
    }
    catch (FileAlreadyExistsException collision) {
      // Another directory creator is harmless; files and symbolic links are not.
      checkDirectoryAncestors(directory);
    }
  }

  private record OwnedPath(Path path, Object fileKey) { }

  private static void recordCreated(Path path, List<OwnedPath> created) throws IOException {
    // Record ownership before reading metadata so even a metadata failure can roll back creation.
    int index = created.size();
    created.add(new OwnedPath(path, null));
    Object key = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS).fileKey();
    created.set(index, new OwnedPath(path, key));
  }

  private static void rollback(List<OwnedPath> created, Throwable failure) {
    for (int index = created.size() - 1; index >= 0; index--) {
      OwnedPath entry = created.get(index);
      try {
        checkDirectoryAncestors(entry.path().getParent());
        if (!Files.exists(entry.path(), LinkOption.NOFOLLOW_LINKS)) continue;
        BasicFileAttributes now = Files.readAttributes(entry.path(), BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        // Never delete a replacement path or traverse newly substituted symbolic links.
        if (now.isSymbolicLink() || (entry.fileKey() != null && !entry.fileKey().equals(now.fileKey()))) continue;
        Files.delete(entry.path()); // Nonempty directories are preserved, with the cleanup error attached.
      }
      catch (IOException cleanupFailure) { failure.addSuppressed(cleanupFailure); }
    }
  }
}
