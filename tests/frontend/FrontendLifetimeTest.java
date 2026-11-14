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
    Map<String,Object> incompleteReport = incomplete.completion().get(6, TimeUnit.SECONDS);
    require(Boolean.TRUE.equals(incompleteReport.get("identityIncomplete")) && Boolean.FALSE.equals(incompleteReport.get("cleanupComplete"))
        && unidentified.kills == 0, "Unverifiable descendant was killed or claimed completely cleaned");
    Handle lostRoot = new Handle(105, Instant.ofEpochSecond(5));
    FrontendProcessLifetime rootLost = new FrontendProcessLifetime(new FakeProcess(lostRoot)); lostRoot.started = null; rootLost.close();
    Map<String,Object> rootLostReport = rootLost.completion().get(6, TimeUnit.SECONDS);
    require(Boolean.FALSE.equals(rootLostReport.get("cleanupComplete")) && Boolean.TRUE.equals(rootLostReport.get("identityIncomplete"))
        && ((List<?>)rootLostReport.get("uncertainLivePids")).contains(105L) && lostRoot.kills == 0 && lostRoot.alive,
        "Known root that lost metadata was reported gone or signalled");
    Handle childRoot = new Handle(106, Instant.ofEpochSecond(6)); Handle lostChild = new Handle(107, Instant.ofEpochSecond(7));
    childRoot.descendants = List.of(lostChild); FrontendProcessLifetime childLost = new FrontendProcessLifetime(new FakeProcess(childRoot));
    lostChild.started = null; childLost.close(); Map<String,Object> childLostReport = childLost.completion().get(6, TimeUnit.SECONDS);
    require(Boolean.FALSE.equals(childLostReport.get("cleanupComplete")) && Boolean.TRUE.equals(childLostReport.get("identityIncomplete"))
        && ((List<?>)childLostReport.get("uncertainLivePids")).contains(107L) && !childRoot.alive && lostChild.kills == 0 && lostChild.alive,
        "Known child that lost metadata was evicted or signalled");
    Handle enumerationRoot = new Handle(108, Instant.ofEpochSecond(8));
    FrontendProcessLifetime enumeration = new FrontendProcessLifetime(new FakeProcess(enumerationRoot)); enumerationRoot.enumerationFails = true;
    enumeration.close(); Map<String,Object> enumerationReport = enumeration.completion().get(3, TimeUnit.SECONDS);
    require(!enumerationRoot.alive && Boolean.TRUE.equals(enumerationReport.get("discoveryIncomplete")) && Boolean.FALSE.equals(enumerationReport.get("cleanupComplete")),
        "Failed descendant enumeration skipped verified root disposal or claimed full cleanup");
    System.out.println("{\"status\":\"pass\",\"missingRootIdentityFailsClosed\":true,\"reusedPidNotSignalled\":true,\"rejectedSchedulingDisposesIndependently\":true,\"unverifiableChildNotClaimedClean\":true,\"knownRootIdentityLossNotGone\":true,\"knownChildIdentityLossNotGone\":true,\"enumerationFailureStillDisposesVerifiedRoot\":true,\"nativeIdeStarted\":false}");
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
    volatile boolean enumerationFails;
    Handle(long pid, Instant started) { this.pid = pid; this.started = started; }
    public long pid() { return pid; }
    public Optional<ProcessHandle> parent() { return Optional.empty(); }
    public Stream<ProcessHandle> children() { return descendants.stream().map(value -> value); }
    public Stream<ProcessHandle> descendants() { if (enumerationFails) throw new IllegalStateException("owned test enumeration failure"); return children(); }
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
