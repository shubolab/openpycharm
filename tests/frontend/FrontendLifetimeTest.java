package dev.openpycharm.frontend;

import java.io.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.stream.Stream;

/** Deterministic identity/rejected-executor controls; real owned Node is tested separately. */
public final class FrontendLifetimeTest {
  private static void require(boolean value, String message) { if (!value) throw new AssertionError(message); }
  public static void main(String[] args) throws Exception {
    FakeProcess unknown = new FakeProcess(new Handle(100, null));
    try { new FrontendProcessLifetime(unknown); throw new AssertionError("Live process without identity was accepted"); }
    catch (IllegalStateException expected) { require(!unknown.isAlive() && unknown.handle.kills == 1, "Exact newly spawned Process object was not stopped on missing identity"); }
    Handle root = new Handle(101, Instant.ofEpochSecond(1)); Handle child = new Handle(102, Instant.ofEpochSecond(2));
    root.descendants = List.of(child); FakeProcess process = new FakeProcess(root);
    FrontendProcessLifetime lifetime = new FrontendProcessLifetime(process);
    // The old owned child exited, its PID is now reused outside our tree.
    root.descendants = List.of(); child.started = Instant.ofEpochSecond(3);
    var controlField = FrontendProcessLifetime.class.getDeclaredField("control"); controlField.setAccessible(true);
    ((ScheduledExecutorService)controlField.get(lifetime)).shutdownNow();
    lifetime.close(); lifetime.close(); Map<String,Object> report = lifetime.completion().get(3, TimeUnit.SECONDS);
    require(Boolean.TRUE.equals(report.get("cleanupComplete")), "Independent rejected-scheduling cleanup failed: " + report);
    require(!root.alive && child.alive && child.kills == 0, "Reused unowned PID was terminated");
    Handle incompleteRoot = new Handle(103, Instant.ofEpochSecond(4)); Handle unidentified = new Handle(104, null);
    incompleteRoot.descendants = List.of(unidentified);
    FrontendProcessLifetime incomplete = new FrontendProcessLifetime(new FakeProcess(incompleteRoot)); incomplete.close();
    Map<String,Object> incompleteReport = incomplete.completion().get(3, TimeUnit.SECONDS);
    require(Boolean.TRUE.equals(incompleteReport.get("identityIncomplete")) && Boolean.FALSE.equals(incompleteReport.get("cleanupComplete"))
        && unidentified.kills == 0, "Unverifiable descendant was killed or claimed completely cleaned");
    System.out.println("{\"status\":\"pass\",\"missingRootIdentityFailsClosed\":true,\"reusedPidNotSignalled\":true,\"rejectedSchedulingDisposesIndependently\":true,\"unverifiableChildNotClaimedClean\":true,\"nativeIdeStarted\":false}");
  }
  private static final class FakeProcess extends Process {
    final Handle handle; FakeProcess(Handle handle) { this.handle = handle; }
    public OutputStream getOutputStream() { return OutputStream.nullOutputStream(); }
    public InputStream getInputStream() { return InputStream.nullInputStream(); }
    public InputStream getErrorStream() { return InputStream.nullInputStream(); }
    public int waitFor() { return 0; }
    public int exitValue() { if (isAlive()) throw new IllegalThreadStateException(); return 0; }
    public void destroy() { handle.destroy(); }
    public Process destroyForcibly() { handle.destroyForcibly(); return this; }
    public boolean isAlive() { return handle.alive; }
    public ProcessHandle toHandle() { return handle; }
  }
  private static final class Handle implements ProcessHandle {
    final long pid; volatile Instant started; volatile boolean alive = true; volatile int kills;
    volatile List<Handle> descendants = List.of();
    Handle(long pid, Instant started) { this.pid = pid; this.started = started; }
    public long pid() { return pid; }
    public Optional<ProcessHandle> parent() { return Optional.empty(); }
    public Stream<ProcessHandle> children() { return descendants.stream().map(value -> value); }
    public Stream<ProcessHandle> descendants() { return children(); }
    public Info info() { return new Info() {
      public Optional<String> command() { return Optional.empty(); }
      public Optional<String> commandLine() { return Optional.empty(); }
      public Optional<String[]> arguments() { return Optional.empty(); }
      public Optional<Instant> startInstant() { return Optional.ofNullable(started); }
      public Optional<java.time.Duration> totalCpuDuration() { return Optional.empty(); }
      public Optional<String> user() { return Optional.empty(); }
    }; }
    public CompletableFuture<ProcessHandle> onExit() { return new CompletableFuture<>(); }
    public boolean supportsNormalTermination() { return true; }
    public boolean destroy() { kills++; alive = false; return true; }
    public boolean destroyForcibly() { return destroy(); }
    public boolean isAlive() { return alive; }
    public int compareTo(ProcessHandle other) { return Long.compare(pid, other.pid()); }
  }
}
