package dev.openpycharm.notebooks;

import com.google.gson.JsonObject;
import java.lang.reflect.Field;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;

/** Actual pipe backpressure and startup/disposal races using test-owned helpers. */
public final class NotebookSessionDisposalTest {
  private record Helper(ProcessHandle handle, Instant start) {
    void forceIfStillOwned() {
      if (handle.isAlive() && handle.info().startInstant().filter(start::equals).isPresent()) handle.destroyForcibly();
    }
  }

  private static void require(boolean condition, String message) {
    if (!condition) throw new AssertionError(message);
  }

  private static Process sessionProcess(NotebookKernelSession session) throws Exception {
    Field field = NotebookKernelSession.class.getDeclaredField("process");
    field.setAccessible(true);
    return (Process)field.get(session);
  }

  private static Process awaitProcess(NotebookKernelSession session) throws Exception {
    long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
    Process process;
    while ((process = sessionProcess(session)) == null && System.nanoTime() < deadline) Thread.sleep(10);
    require(process != null, "The test-owned fake interpreter did not launch");
    return process;
  }

  private static List<Helper> ownedHelpers(Process process) {
    List<Helper> helpers = new ArrayList<>();
    process.toHandle().info().startInstant().ifPresent(start -> helpers.add(new Helper(process.toHandle(), start)));
    process.descendants().forEach(handle -> handle.info().startInstant().ifPresent(start -> helpers.add(new Helper(handle, start))));
    return helpers;
  }

  private static String shellQuote(String value) { return "'" + value.replace("'", "'\"'\"'") + "'"; }

  private static Path fakeInterpreter(String python, Path directory) throws Exception {
    Path helper = directory.resolve("non-reading-interpreter.py");
    Files.writeString(helper, """
        import json, os, signal, subprocess, sys, time
        # Ignore TERM to require the independent disposal task's force deadline.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        child = subprocess.Popen([sys.executable, '-c',
            'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(120)'])
        os.write(1, (json.dumps({'id':None,'event':'ready','kernel_pid':child.pid})+'\\n').encode())
        # Deliberately never read stdin. A 400 KiB request fills the OS pipe.
        time.sleep(120)
        """);
    Path launcher = directory.resolve("non-reading-python");
    Files.writeString(launcher, "#!/bin/sh\nexec " + shellQuote(python) + " " + shellQuote(helper.toString()) + " \"$@\"\n");
    Files.setPosixFilePermissions(launcher, PosixFilePermissions.fromString("rwx------"));
    return launcher;
  }

  private static void awaitBlockedWrite() throws Exception {
    long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
    while (System.nanoTime() < deadline) {
      for (StackTraceElement[] stack : Thread.getAllStackTraces().values()) {
        boolean session = false, pipe = false;
        for (StackTraceElement frame : stack) {
          session |= frame.getClassName().equals(NotebookKernelSession.class.getName());
          pipe |= frame.getClassName().equals("java.io.FileOutputStream") && frame.getMethodName().startsWith("write");
        }
        if (session && pipe) return;
      }
      Thread.sleep(10);
    }
    throw new AssertionError("The fake interpreter did not produce actual pipe-write backpressure");
  }

  private static long closeAndAwait(NotebookKernelSession session, Process process, List<Helper> helpers) throws Exception {
    long before = System.nanoTime();
    session.close();
    session.close();
    long callMillis = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - before);
    require(callMillis < 1000, "close() blocked the caller for " + callMillis + " ms");
    require(process.waitFor(9, TimeUnit.SECONDS), "Owned non-reading interpreter survived bounded disposal");
    long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);
    while (helpers.stream().anyMatch(helper -> helper.handle().isAlive()) && System.nanoTime() < deadline) Thread.sleep(20);
    require(helpers.stream().noneMatch(helper -> helper.handle().isAlive()), "An owned helper descendant survived disposal");
    session.close();
    return TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - before);
  }

  public static JsonObject run(String python, Path directory) throws Exception {
    JsonObject result = new JsonObject();
    if (System.getProperty("os.name").startsWith("Windows")) {
      result.addProperty("status", "unverified");
      result.addProperty("reason", "The fake interpreter fixture needs a native Windows executable wrapper");
      return result;
    }
    Path fixture = Files.createDirectory(directory.resolve("disposal helpers"));
    Path fake = fakeInterpreter(python, fixture);
    NotebookKernelSession beforeStart = new NotebookKernelSession(fake.toString(), fixture.toString(), event -> { });
    beforeStart.close();
    beforeStart.close();
    beforeStart.request("ignored", "execute", "x".repeat(400000));
    Thread.sleep(100);
    require(sessionProcess(beforeStart) == null, "A request after close launched an interpreter");

    BlockingQueue<JsonObject> events = new LinkedBlockingQueue<>();
    NotebookKernelSession blocked = new NotebookKernelSession(fake.toString(), fixture.toString(), events::add);
    List<Helper> blockedHelpers = List.of();
    long blockedMillis;
    try {
      blocked.request("blocked", "execute", "x".repeat(400000));
      Process process = awaitProcess(blocked);
      JsonObject ready = events.poll(5, TimeUnit.SECONDS);
      require(ready != null && "ready".equals(NotebookKernelSession.string(ready, "event")), "Fake interpreter readiness was not observed");
      blockedHelpers = ownedHelpers(process);
      require(blockedHelpers.size() >= 2, "Owned fake child was not captured before disposal");
      awaitBlockedWrite();
      blockedMillis = closeAndAwait(blocked, process, blockedHelpers);
    } finally {
      blocked.close();
      for (Helper helper : blockedHelpers.reversed()) helper.forceIfStillOwned();
    }

    // Close as soon as a process is published, while start()/the first request
    // are still in progress. No readiness event or pipe-drain is required.
    NotebookKernelSession starting = new NotebookKernelSession(fake.toString(), fixture.toString(), event -> { });
    List<Helper> startupHelpers = List.of();
    long startupMillis;
    try {
      starting.request("startup", "execute", "x".repeat(400000));
      Process process = awaitProcess(starting);
      startupHelpers = ownedHelpers(process);
      startupMillis = closeAndAwait(starting, process, startupHelpers);
    } finally {
      starting.close();
      for (Helper helper : startupHelpers.reversed()) helper.forceIfStillOwned();
    }
    result.addProperty("status", "pass");
    result.addProperty("actualBlockedPipe", true);
    result.addProperty("closeBeforeRequest", true);
    result.addProperty("closeDuringStartup", true);
    result.addProperty("doubleClose", true);
    result.addProperty("boundedOwnedProcessAndDescendantCleanup", true);
    result.addProperty("blockedWriterCloseMillis", blockedMillis);
    result.addProperty("startupCloseMillis", startupMillis);
    return result;
  }
}
