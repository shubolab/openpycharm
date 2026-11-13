package dev.openpycharm.frameworks;

import com.intellij.execution.ExecutionException;
import com.intellij.execution.configurations.GeneralCommandLine;
import com.intellij.execution.process.OSProcessHandler;
import com.intellij.execution.process.OSProcessUtil;
import com.intellij.execution.process.ProcessAdapter;
import com.intellij.execution.process.ProcessEvent;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.projectRoots.Sdk;
import com.intellij.openapi.util.Key;
import com.jetbrains.python.sdk.PythonSdkType;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.locks.LockSupport;

/** Bounded, cancellable dependency work using only the selected SDK process. */
public final class FrameworkDependencyInstaller {
  public record ProcessResult(long ownedPid, int exitCode, List<String> command, List<Long> observedDescendants) { }
  private FrameworkDependencyInstaller() { }

  public static ProcessResult install(Sdk sdk, Path directory, Runnable cancellationCheck) throws IOException, ExecutionException {
    return run(sdk, directory, List.of("-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.txt"),
        cancellationCheck, 600_000L);
  }

  public static ProcessResult run(Sdk sdk, Path directory, List<String> parameters, Runnable cancellationCheck,
                                  long timeoutMillis) throws IOException, ExecutionException {
    var application = ApplicationManager.getApplication();
    if (application != null && application.isDispatchThread()) {
      throw new IllegalStateException("Framework processes must run outside the event dispatch thread");
    }
    if (sdk.getHomePath() == null || sdk.getHomePath().isBlank()) throw new IOException("The selected Python interpreter has no executable path");
    if (timeoutMillis < 1 || timeoutMillis > 600_000) throw new IllegalArgumentException("Invalid framework process timeout");
    cancellationCheck.run();
    List<String> arguments = new ArrayList<>();
    arguments.add(sdk.getHomePath());
    for (String argument : parameters) {
      if (argument == null || argument.indexOf('\0') >= 0 || argument.indexOf('\r') >= 0 || argument.indexOf('\n') >= 0) {
        throw new IllegalArgumentException("A process argument cannot contain NUL or a line break");
      }
      arguments.add(argument);
    }
    GeneralCommandLine command = new GeneralCommandLine(arguments).withWorkDirectory(directory.toFile()).withCharset(StandardCharsets.UTF_8);
    command.setRedirectErrorStream(true);
    PythonSdkType.patchCommandLineForVirtualenv(command, sdk);
    OSProcessHandler handler = new OSProcessHandler(command);
    handler.setShouldDestroyProcessRecursively(true);
    StringBuilder tail = new StringBuilder();
    handler.addProcessListener(new ProcessAdapter() {
      @Override public void onTextAvailable(ProcessEvent event, Key outputType) {
        synchronized (tail) {
          tail.append(event.getText());
          if (tail.length() > 65536) tail.delete(0, tail.length() - 65536);
        }
      }
    });
    long pid = handler.getProcess().pid();
    Map<Long, ProcessHandle> descendants = new LinkedHashMap<>();
    Throwable failure = null;
    try {
      handler.startNotify();
      long deadline = System.nanoTime() + timeoutMillis * 1_000_000L;
      while (true) {
        observeDescendants(handler.getProcess(), descendants);
        if (handler.waitFor(25)) break;
        cancellationCheck.run();
        if (System.nanoTime() >= deadline) throw new IOException("Framework dependency operation timed out");
      }
      cancellationCheck.run();
      Integer exit = handler.getExitCode();
      if (exit == null || exit != 0) {
        String output;
        synchronized (tail) { output = tail.toString(); }
        throw new IOException("Framework dependency operation failed (exit " + exit + "):\n" + output);
      }
      return new ProcessResult(pid, exit, List.copyOf(arguments), List.copyOf(descendants.keySet()));
    } catch (IOException | RuntimeException | Error error) {
      failure = error;
      throw error;
    } finally {
      observeDescendants(handler.getProcess(), descendants);
      IOException cleanupFailure = null;
      if (!handler.isProcessTerminated()) {
        handler.destroyProcess();
        if (!handler.waitFor(5000)) {
          OSProcessUtil.killProcessTree(handler.getProcess());
          if (!handler.waitFor(5000)) {
            cleanupFailure = new IOException("The owned framework dependency process could not be terminated");
          }
        }
      }
      // A normal root exit does not imply its previously observed children exited.
      // Retain ProcessHandles across reparenting and clean only those owned handles.
      for (ProcessHandle child : descendants.values()) if (child.isAlive()) child.destroy();
      awaitChildren(descendants, 2000);
      for (ProcessHandle child : descendants.values()) if (child.isAlive()) child.destroyForcibly();
      awaitChildren(descendants, 3000);
      List<Long> alive = descendants.values().stream().filter(ProcessHandle::isAlive).map(ProcessHandle::pid).toList();
      if (!alive.isEmpty()) {
        IOException children = new IOException("Owned framework helper children did not terminate: " + alive);
        if (cleanupFailure == null) cleanupFailure = children;
        else cleanupFailure.addSuppressed(children);
      }
      if (cleanupFailure != null) {
        if (failure != null) failure.addSuppressed(cleanupFailure);
        else throw cleanupFailure;
      }
    }
  }

  private static void observeDescendants(Process process, Map<Long, ProcessHandle> descendants) {
    process.descendants().forEach(child -> descendants.putIfAbsent(child.pid(), child));
    for (ProcessHandle child : List.copyOf(descendants.values())) {
      if (child.isAlive()) child.descendants().forEach(nested -> descendants.putIfAbsent(nested.pid(), nested));
    }
  }

  private static void awaitChildren(Map<Long, ProcessHandle> descendants, long millis) {
    long deadline = System.nanoTime() + millis * 1_000_000L;
    while (descendants.values().stream().anyMatch(ProcessHandle::isAlive) && System.nanoTime() < deadline) {
      LockSupport.parkNanos(10_000_000L);
    }
  }
}
