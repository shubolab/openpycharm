package com.intellij.ui.jcef;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.CancellationException;

/** Build-time control for exact repaired getInstance/Holder fields with a controlled constructor. */
public final class HolderLifecycleProbe {
  private static int checks;

  public static void main(String[] arguments) throws Exception {
    JBCefApp.reset(false);
    JBCefApp singleton = new JBCefApp(7);
    CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
    JBCefApp.factory = () -> {
      entered.countDown();
      try { if (!release.await(5, TimeUnit.SECONDS)) throw new AssertionError("Constructor control timed out"); }
      catch (InterruptedException error) { throw new AssertionError(error); }
      return singleton;
    };
    try (var executor = Executors.newFixedThreadPool(16)) {
      List<java.util.concurrent.Future<JBCefApp>> requests = new ArrayList<>();
      for (int index = 0; index < 32; index++) requests.add(executor.submit(JBCefApp::getInstance));
      require(entered.await(5, TimeUnit.SECONDS), "No first-use construction");
      require(JBCefApp.factoryCalls.get() == 1, "Concurrent first use started multiple constructions");
      release.countDown();
      for (var request : requests) require(request.get(5, TimeUnit.SECONDS) == singleton, "Publication changed instance identity");
    }
    require(JBCefApp.factoryCalls.get() == 1 && JBCefApp.wasAttempted(), "First-use flags changed");
    require(JBCefApp.getInstance() == singleton, "Warm access changed instance");

    JBCefApp.reset(false);
    JBCefApp.factory = () -> null;
    for (int index = 0; index < 3; index++) unsupported();
    require(JBCefApp.factoryCalls.get() == 1 && JBCefApp.wasAttempted(), "Normal cached-null access retried initialization");
    JBCefApp.testMode = true;
    JBCefApp.factory = () -> singleton;
    require(JBCefApp.getInstance() == singleton && JBCefApp.factoryCalls.get() == 2, "Later test-mode retry failed");

    JBCefApp.reset(true);
    JBCefApp.factory = () -> JBCefApp.factoryCalls.get() == 1 ? null : singleton;
    require(JBCefApp.getInstance() == singleton && JBCefApp.factoryCalls.get() == 2, "First test-mode call lost its existing immediate retry");
    JBCefApp.reset(true);
    JBCefApp.factory = () -> null;
    unsupported(); unsupported();
    require(JBCefApp.factoryCalls.get() == 3, "Test mode did not retry once per subsequent access");

    JBCefApp.reset(false);
    AtomicBoolean reentryRejected = new AtomicBoolean();
    JBCefApp.factory = () -> {
      try { JBCefApp.getInstance(); }
      catch (IllegalStateException expected) { reentryRejected.set(true); }
      return singleton;
    };
    require(JBCefApp.getInstance() == singleton && reentryRejected.get(), "Normal-mode reentry did not observe incomplete construction");
    require(JBCefApp.factoryCalls.get() == 1, "Reentry recursively constructed JCEF");

    for (Throwable failure : List.of(new IllegalArgumentException("constructor failure"), new LinkageError("native linkage failure"),
                                    new CancellationException("explicit constructor cancellation"))) {
      JBCefApp.reset(false);
      JBCefApp.factory = () -> sneaky(failure);
      require(thrown() == failure, "First unexpected failure lost its cause");
      require(thrown() == failure, "Cached failure was masked as unsupported");
      JBCefApp.testMode = true;
      require(thrown() == failure && JBCefApp.factoryCalls.get() == 1, "Test mode retried a terminal first-attempt failure");
      require(JBCefApp.wasAttempted(), "Failure lost attempted initialization flags");
    }

    // Reentry in test mode can publish an inner instance while the first
    // constructor is still running. No other thread may observe that instance.
    JBCefApp.reset(true);
    IllegalArgumentException outerFailure = new IllegalArgumentException("outer construction failed after reentry");
    CountDownLatch innerReturned = new CountDownLatch(1), failOuter = new CountDownLatch(1);
    JBCefApp.factory = () -> {
      if (JBCefApp.factoryCalls.get() == 1) {
        require(JBCefApp.getInstance() == singleton, "Controlled test-mode reentry did not return its inner instance");
        innerReturned.countDown();
        try { if (!failOuter.await(5, TimeUnit.SECONDS)) throw new AssertionError("Outer failure control timed out"); }
        catch (InterruptedException error) { throw new AssertionError(error); }
        throw outerFailure;
      }
      return singleton;
    };
    try (var executor = Executors.newFixedThreadPool(3)) {
      var first = executor.submit(HolderLifecycleProbe::thrown);
      require(innerReturned.await(5, TimeUnit.SECONDS), "No inner instance was published for the regression control");
      CountDownLatch readersStarted = new CountDownLatch(2);
      AtomicReference<Thread> threadOne = new AtomicReference<>(), threadTwo = new AtomicReference<>();
      var readerOne = executor.submit(() -> { threadOne.set(Thread.currentThread()); readersStarted.countDown(); return thrown(); });
      var readerTwo = executor.submit(() -> { threadTwo.set(Thread.currentThread()); readersStarted.countDown(); return thrown(); });
      require(readersStarted.await(5, TimeUnit.SECONDS), "Concurrent readers did not start");
      try {
        long blockedDeadline = System.nanoTime() + 2_000_000_000L;
        while (!readerOne.isDone() && !readerTwo.isDone() && !(blockedAtGetter(threadOne.get()) && blockedAtGetter(threadTwo.get()))
               && System.nanoTime() < blockedDeadline) Thread.sleep(1);
        require(blockedAtGetter(threadOne.get()) && blockedAtGetter(threadTwo.get()) && !readerOne.isDone() && !readerTwo.isDone(),
                "Reader observed premature test-mode publication");
      } finally { failOuter.countDown(); }
      require(first.get(5, TimeUnit.SECONDS) == outerFailure, "Outer failure cause changed");
      require(readerOne.get(5, TimeUnit.SECONDS) == outerFailure && readerTwo.get(5, TimeUnit.SECONDS) == outerFailure,
              "Concurrent readers did not see the terminal outer failure");
    }
    require(thrown() == outerFailure && JBCefApp.factoryCalls.get() == 2, "Failed outer attempt exposed or retried the inner instance");

    // The existing retry branch runs after an ordinary cached-null first attempt.
    // Its unexpected exception must propagate without becoming a terminal first-attempt failure.
    JBCefApp.reset(true);
    IllegalArgumentException retryFailure = new IllegalArgumentException("retry failure");
    JBCefApp.factory = () -> {
      int attempt = JBCefApp.factoryCalls.get();
      if (attempt == 1) return null;
      if (attempt == 2) throw retryFailure;
      return singleton;
    };
    require(thrown() == retryFailure, "Test-mode retry failure was swallowed");
    require(JBCefApp.getInstance() == singleton && JBCefApp.factoryCalls.get() == 3, "Retry exception changed the original retry policy");
    System.out.println("{\"status\":\"pass\",\"scope\":\"source-derived first-use, publication, null, test-mode, reentry and failure controls\",\"checks\":" + checks + "}");
  }

  @SuppressWarnings("unchecked") private static <T, E extends Throwable> T sneaky(Throwable error) throws E { throw (E)error; }
  private static boolean blockedAtGetter(Thread thread) {
    return thread != null && thread.getState() == Thread.State.BLOCKED &&
           java.util.Arrays.stream(thread.getStackTrace()).anyMatch(frame -> frame.getClassName().equals("com.intellij.ui.jcef.JBCefApp")
               && frame.getMethodName().equals("getInstance"));
  }
  private static Throwable thrown() {
    try { JBCefApp.getInstance(); return new AssertionError("Expected failure"); }
    catch (Throwable error) { return error; }
  }
  private static void unsupported() {
    require(thrown() instanceof IllegalStateException, "Cached null should report unsupported initialization");
  }
  private static void require(boolean condition, String message) {
    checks++;
    if (!condition) throw new AssertionError(message);
  }
}
