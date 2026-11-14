package dev.openpycharm.frontend;

import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import javax.swing.SwingUtilities;

/** Independent shutdown never waits for an LSP write or holds its pipe lock. */
final class FrontendProcessLifetime implements AutoCloseable {
  private record Identity(ProcessHandle handle, Instant started) {
    boolean alive() { return started != null && handle.isAlive() && handle.info().startInstant().filter(started::equals).isPresent(); }
  }
  private final Process process;
  private final Identity root;
  private final ConcurrentMap<Long, Identity> owned = new ConcurrentHashMap<>();
  private final ScheduledExecutorService control = Executors.newSingleThreadScheduledExecutor(r -> {
    Thread thread = new Thread(r, "OpenPyCharm frontend lifecycle"); thread.setDaemon(true); return thread;
  });
  private final AtomicBoolean closing = new AtomicBoolean(), processLimitExceeded = new AtomicBoolean(), identityIncomplete = new AtomicBoolean();
  private final CompletableFuture<Map<String, Object>> completion = new CompletableFuture<>();
  private final ScheduledFuture<?> tracking;
  private volatile FrontendBoundedOutput input;

  FrontendProcessLifetime(Process process) {
    if (SwingUtilities.isEventDispatchThread()) throw new IllegalStateException("Frontend process tracking requires a worker");
    this.process = process; ProcessHandle handle = process.toHandle();
    root = new Identity(handle, handle.info().startInstant().orElse(null));
    if (root.started() == null && process.isAlive()) {
      process.destroyForcibly(); // Exact Process object just created by our handler, never a supplied PID.
      throw new IllegalStateException("Frontend process has no verifiable start identity");
    }
    owned.put(handle.pid(), root);
    snapshot(); tracking = control.scheduleWithFixedDelay(this::snapshot, 100, 100, TimeUnit.MILLISECONDS);
  }
  void input(FrontendBoundedOutput value) { input = value; }
  private void snapshot() {
    if (!root.alive()) return;
    owned.entrySet().removeIf(entry -> entry.getValue() != root && !entry.getValue().alive());
    try (var descendants = root.handle().descendants()) {
      var iterator = descendants.iterator();
      while (iterator.hasNext()) {
        ProcessHandle handle = iterator.next();
        if (!owned.containsKey(handle.pid()) && owned.size() >= 128) { processLimitExceeded.set(true); break; }
        var start = handle.info().startInstant();
        if (start.isPresent()) owned.putIfAbsent(handle.pid(), new Identity(handle, start.get()));
        else if (handle.isAlive()) identityIncomplete.set(true);
      }
    }
  }
  @Override public void close() {
    if (!closing.compareAndSet(false, true)) return;
    FrontendBoundedOutput writer = input; if (writer != null) writer.stop();
    // Scheduling is the only operation allowed on the disposing caller/EDT.
    try { control.execute(this::disposeOwned); }
    catch (RejectedExecutionException rejected) {
      Thread fallback = new Thread(this::disposeOwned, "OpenPyCharm frontend fallback disposal"); fallback.setDaemon(true); fallback.start();
    }
  }
  private void disposeOwned() {
    long started = System.nanoTime(), deadline = started + TimeUnit.SECONDS.toNanos(8);
    Map<String, Object> report = new LinkedHashMap<>();
    try {
      snapshot(); tracking.cancel(false);
      // Capture descendants before terminating their parent; signal only the
      // exact PID+start-time identities discovered under this spawned process.
      List<Identity> targets = new ArrayList<>(owned.values()); targets.sort(Comparator.comparingLong(value -> value.handle().pid()));
      for (Identity value : targets) if (value != root && value.alive()) value.handle().destroy();
      if (root.alive()) root.handle().destroy();
      waitGone(started + TimeUnit.SECONDS.toNanos(1));
      for (Identity value : targets) if (value.alive()) value.handle().destroyForcibly();
      waitGone(Math.min(deadline, System.nanoTime() + TimeUnit.SECONDS.toNanos(3)));
      FrontendBoundedOutput writer = input;
      if (writer != null) writer.awaitStopped(Math.max(1, Math.min(1000, TimeUnit.NANOSECONDS.toMillis(deadline - System.nanoTime()))));
      // Native ProcessHandler owns stdout/stderr readers; killing the process
      // unblocks them. These independent closers never run on the EDT.
      List<Thread> closers = new ArrayList<>();
      for (var stream : List.of(process.getInputStream(), process.getErrorStream())) {
        Thread close = new Thread(() -> { try { stream.close(); } catch (Exception ignored) { } }, "OpenPyCharm frontend stream close");
        close.setDaemon(true); closers.add(close); close.start();
      }
      for (Thread close : closers) close.join(Math.max(1, Math.min(500, TimeUnit.NANOSECONDS.toMillis(deadline - System.nanoTime()))));
      report.put("remainingOwnedPids", owned.values().stream().filter(Identity::alive).map(value -> value.handle().pid()).sorted().toList());
      report.put("writerAlive", writer != null && writer.writerAlive()); report.put("streamClosersAlive", closers.stream().anyMatch(Thread::isAlive));
      report.put("processLimitExceeded", processLimitExceeded.get()); report.put("identityIncomplete", identityIncomplete.get());
      report.put("cleanupComplete", !processLimitExceeded.get() && !identityIncomplete.get() && ((List<?>)report.get("remainingOwnedPids")).isEmpty() && !Boolean.TRUE.equals(report.get("writerAlive")) && !Boolean.TRUE.equals(report.get("streamClosersAlive")));
    } catch (Throwable failure) { report.put("cleanupComplete", false); report.put("failure", failure.toString()); }
    finally {
      report.put("ownershipScope", "Spawned root Process and observed descendants verified by PID/start time; no native job/session is installed");
      report.put("unexpectedParentCrashReparentingVerified", false);
      report.put("ownedPid", root.handle().pid()); report.put("observedOwnedPids", owned.keySet().stream().sorted().toList());
      report.put("cleanupMillis", TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started));
      control.shutdownNow(); completion.complete(Map.copyOf(report));
    }
  }
  private void waitGone(long deadline) throws InterruptedException {
    while (System.nanoTime() < deadline && owned.values().stream().anyMatch(Identity::alive)) Thread.sleep(20);
  }
  CompletableFuture<Map<String, Object>> completion() { return completion; }
}
