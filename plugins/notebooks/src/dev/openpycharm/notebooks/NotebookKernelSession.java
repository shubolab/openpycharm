package dev.openpycharm.notebooks;

import com.google.gson.*;
import com.intellij.openapi.application.PathManager;
import com.intellij.util.concurrency.AppExecutorUtil;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

/** All extraction, pipe IO, process startup and owned-process disposal run off the EDT. */
public final class NotebookKernelSession implements AutoCloseable {
  private final ExecutorService commands = AppExecutorUtil.createBoundedApplicationPoolExecutor("OpenPyCharm notebook commands", 1);
  private final Consumer<JsonObject> events;
  private final String python;
  private final String cwd;
  private final List<OwnedProcess> owned = new CopyOnWriteArrayList<>();
  private volatile Process process;
  private volatile boolean closed;
  private final AtomicBoolean disposalScheduled = new AtomicBoolean();
  private BufferedWriter writer;
  private volatile Path temporary;

  private record OwnedProcess(ProcessHandle handle, Instant started) {
    boolean isOwnedAlive() {
      return handle.isAlive() && handle.info().startInstant().filter(started::equals).isPresent();
    }
    void destroy(boolean force) {
      if (isOwnedAlive()) {
        if (force) handle.destroyForcibly(); else handle.destroy();
      }
    }
  }

  public NotebookKernelSession(String python, String cwd, Consumer<JsonObject> events) {
    this.python = python;
    this.cwd = cwd;
    this.events = events;
  }

  public synchronized void request(String id, String operation, String code) {
    if (closed) return;
    commands.execute(() -> {
      try {
        if (closed) return;
        if (process == null) start();
        if (closed) return;
        if (!process.isAlive()) throw new IOException("Notebook kernel bridge exited; restart the kernel");
        JsonObject request = new JsonObject();
        request.addProperty("id", id);
        request.addProperty("op", operation);
        if (code != null) request.addProperty("code", code);
        writer.write(request.toString()); writer.newLine(); writer.flush();
      } catch (Exception error) { fail(id, error.getMessage()); }
    });
  }

  private void start() throws IOException {
    Path parent = PathManager.getSystemDir().resolve("openpycharm-notebooks");
    Files.createDirectories(parent);
    Path directory = Files.createTempDirectory(parent, "bridge-");
    temporary = directory;
    boolean launched = false;
    try {
      Path script = directory.resolve("kernel_bridge.py");
      try (InputStream stream = getClass().getResourceAsStream("/kernel_bridge.py")) {
        if (stream == null) throw new IOException("Notebook kernel bridge resource is missing");
        Files.copy(stream, script);
      }
      if (closed) return;
      ProcessBuilder builder = new ProcessBuilder(python, "-u", script.toString(), "--cwd", cwd);
      builder.directory(Path.of(cwd).toFile());
      builder.environment().put("PYTHONIOENCODING", "utf-8");
      Process started = builder.start();
      launched = true;
      writer = new BufferedWriter(new OutputStreamWriter(started.getOutputStream(), StandardCharsets.UTF_8));
      process = started;
      remember(started.toHandle());
      // close() may have run while ProcessBuilder.start() was still launching.
      // Publish first, then arrange the same independent bounded disposal path.
      if (closed) scheduleDisposal();
      AppExecutorUtil.getAppExecutorService().execute(() -> readEvents(started));
      AppExecutorUtil.getAppExecutorService().execute(() -> {
        try (Reader reader = new InputStreamReader(started.getErrorStream(), StandardCharsets.UTF_8)) {
          char[] buffer = new char[4096];
          int total = 0, count;
          while ((count = reader.read(buffer)) != -1) {
            if (!closed && total < 32768) {
              JsonObject message = new JsonObject(); message.addProperty("event", "diagnostic");
              message.addProperty("text", new String(buffer, 0, Math.min(count, 32768 - total)));
              events.accept(message);
            }
            total += count;
          }
        } catch (IOException ignored) { }
      });
    } finally {
      if (!launched) cleanupDirectory(directory);
    }
  }

  private void readEvents(Process started) {
    try (Reader input = new BufferedReader(new InputStreamReader(started.getInputStream(), StandardCharsets.UTF_8))) {
      StringBuilder line = new StringBuilder(); int next;
      while ((next = input.read()) != -1) {
        if (next != '\n') {
          if (line.length() >= 4 * 1024 * 1024) throw new IOException("Kernel response exceeds the 4 MiB protocol limit");
          line.append((char)next); continue;
        }
        if (line.isEmpty()) continue;
        JsonObject event = JsonParser.parseString(line.toString()).getAsJsonObject(); line.setLength(0);
        String kind = string(event, "event");
        if ("ready".equals(kind) || "done".equals(kind) && "ok".equals(string(event, "status")) && event.has("kernel_pid")) {
          // A restart replaces the owned kernel. Discover it from this bridge's
          // actual descendant tree rather than trusting a PID from JSON.
          started.descendants().forEach(this::remember);
        }
        if (!closed) events.accept(event);
      }
      if (!closed) fail(null, "Notebook kernel bridge stopped. Check that the selected interpreter has jupyter_client==8.6.3 and ipykernel==6.29.5 installed.");
    } catch (Exception error) { if (!closed) fail(null, error.getMessage()); }
  }

  private void remember(ProcessHandle handle) {
    handle.info().startInstant().ifPresent(start -> {
      if (owned.stream().noneMatch(value -> value.handle().pid() == handle.pid() && value.started().equals(start))) owned.add(new OwnedProcess(handle, start));
    });
  }
  private void fail(String id, String text) {
    JsonObject event = new JsonObject(); event.addProperty("event", "session_error");
    event.addProperty("id", id); event.addProperty("message", text == null ? "Notebook kernel failure" : text);
    if (!closed) events.accept(event);
  }
  public static String string(JsonObject object, String key) {
    return object.has(key) && !object.get(key).isJsonNull() ? object.get(key).getAsString() : "";
  }

  @Override public synchronized void close() {
    if (closed) return;
    closed = true;
    // Protocol cleanup is best effort and stays on the writer's executor. It
    // may be queued behind a blocked flush, so lifecycle disposal never waits
    // for this task or acquires any BufferedWriter/Process pipe lock.
    commands.execute(this::closeProtocol);
    commands.shutdown();
    scheduleDisposal();
  }

  private void closeProtocol() {
    BufferedWriter output = writer;
    if (output == null) return;
    try {
      if (process != null && process.isAlive()) {
        output.write("{\"id\":\"dispose\",\"op\":\"shutdown\"}\n");
        output.flush();
      }
    } catch (IOException ignored) { }
    finally { try { output.close(); } catch (IOException ignored) { } }
  }

  private void scheduleDisposal() {
    Process started = process;
    if (started != null && !disposalScheduled.compareAndSet(false, true)) return;
    Runnable dispose = () -> {
      try {
        if (started != null) disposeProcess(started);
      } finally {
        Path directory = temporary;
        if (directory != null) cleanupDirectory(directory);
      }
    };
    try { AppExecutorUtil.getAppExecutorService().execute(dispose); }
    catch (RejectedExecutionException ignored) {
      // Application shutdown must not strand this session's already-launched
      // process merely because the application pool no longer accepts work.
      Thread fallback = new Thread(dispose, "OpenPyCharm notebook disposal");
      fallback.setDaemon(true);
      fallback.start();
    }
  }

  private void snapshotOwned(Process started) {
    remember(started.toHandle());
    started.descendants().forEach(this::remember);
  }

  private void disposeProcess(Process started) {
    boolean interrupted = false;
    try {
      snapshotOwned(started);
      if (!started.waitFor(3, TimeUnit.SECONDS)) {
        snapshotOwned(started);
        // Terminate only a PID whose original start instant is still present.
        owned.stream().filter(value -> value.handle().pid() == started.pid()).forEach(value -> value.destroy(false));
        if (!started.waitFor(2, TimeUnit.SECONDS)) {
          snapshotOwned(started);
          owned.reversed().forEach(value -> value.destroy(true));
          started.waitFor(2, TimeUnit.SECONDS);
        }
      }
      owned.reversed().forEach(value -> value.destroy(false));
      long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(1);
      while (owned.stream().anyMatch(OwnedProcess::isOwnedAlive) && System.nanoTime() < deadline) Thread.sleep(20);
    } catch (InterruptedException ignored) {
      interrupted = true;
    } finally {
      // The writer may still be blocked. Killing the verified owned process
      // breaks its pipe; writer closure remains off this lifecycle task.
      owned.reversed().forEach(value -> value.destroy(true));
      if (interrupted) Thread.currentThread().interrupt();
    }
  }

  private static void cleanupDirectory(Path directory) {
    try {
      Files.deleteIfExists(directory.resolve("kernel_bridge.py"));
      Files.deleteIfExists(directory);
    } catch (IOException ignored) { }
  }
}
