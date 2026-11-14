package dev.openpycharm.notebooks;

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/** Deterministic worker/commit races, independent of Swing or an IDE bootstrap. */
public final class NotebookPersistenceTest {
  private static void require(boolean value, String message) { if (!value) throw new AssertionError(message); }
  public static void main(String[] args) throws Exception {
    ExecutorService worker = Executors.newSingleThreadExecutor();
    try {
      BlockingQueue<NotebookPersistence.Result> results = new LinkedBlockingQueue<>();
      CountDownLatch started = new CountDownLatch(1), release = new CountDownLatch(1);
      AtomicInteger serialized = new AtomicInteger(); Thread submittingThread = Thread.currentThread();
      NotebookPersistence persistence = new NotebookPersistence(worker, results::add, snapshot -> {
        require(Thread.currentThread() != submittingThread, "Serialization ran on submitting/UI thread");
        if (serialized.incrementAndGet() == 1) {
          started.countDown();
          try { if (!release.await(10, TimeUnit.SECONDS)) throw new IllegalStateException("Test release missing"); }
          catch (InterruptedException error) { throw new IllegalStateException(error); }
        }
        return snapshot.json();
      });
      NotebookModel model = NotebookModel.empty(); model.add("code"); model.source(0, "first");
      long first = persistence.submit(model.snapshot());
      require(persistence.isDirty() && started.await(10, TimeUnit.SECONDS), "Edits were not dirty before serialization completed");
      long latest = first;
      for (int i = 0; i < 20; i++) { model.source(0, "latest-" + i); latest = persistence.submit(model.snapshot()); }
      release.countDown();
      NotebookPersistence.Result result = results.poll(10, TimeUnit.SECONDS);
      require(result != null && result.generation() == latest && result.failure() == null, "Stale/coalesced worker completion applied");
      require(serialized.get() == 2, "Pending queue did not coalesce to one latest snapshot");
      require(NotebookModel.parse(result.text()).source(0).equals("latest-19"), "Newest cell edit lost");
      require(!persistence.applied(first) && persistence.isDirty(), "Stale completion cleared dirty state");
      require(persistence.applied(latest) && !persistence.isDirty(), "Current document commit did not clear pending dirty state");
      persistence.invalidate();
      require(!persistence.isCurrent(latest) && !persistence.applied(latest), "External document invalidation accepted a stale completion");

      ArrayDeque<Runnable> queued = new ArrayDeque<>();
      List<NotebookPersistence.Result> callbacks = new ArrayList<>();
      NotebookPersistence delayed = new NotebookPersistence(queued::add, callbacks::add);
      long externalSnapshot = delayed.submit(model.snapshot()); delayed.invalidate();
      model.source(0, "newer-cell-edit"); long newEdit = delayed.submit(model.snapshot());
      queued.removeFirst().run();
      require(callbacks.size() == 1 && callbacks.getFirst().generation() == newEdit && !delayed.isCurrent(externalSnapshot), "Queued external-era snapshot overwrote a newer edit");

      NotebookPersistence failing = new NotebookPersistence(queued::add, (java.util.function.Consumer<NotebookPersistence.Result>)callbacks::add,
          snapshot -> { throw new IllegalStateException("expected failure"); });
      long failureGeneration = failing.submit(model.snapshot()); queued.removeFirst().run();
      require(failing.isDirty() && callbacks.getLast().generation() == failureGeneration && callbacks.getLast().failure() != null,
          "Serialization failure silently cleared dirty state");
      delayed.suspend();
      require(delayed.isDirty() && !delayed.isCurrent(newEdit), "External merge suspension discarded pending edits");

      AtomicInteger attempts = new AtomicInteger();
      NotebookPersistence retrying = new NotebookPersistence(command -> {
        if (attempts.incrementAndGet() == 1) throw new RejectedExecutionException("reject once");
        queued.add(command);
      }, callbacks::add);
      retrying.submit(model.snapshot()); require(retrying.isDirty(), "Rejected submission lost dirty state");
      long retried = retrying.submit(model.snapshot()); queued.removeFirst().run();
      require(attempts.get() == 2 && callbacks.getLast().generation() == retried && callbacks.getLast().failure() == null,
          "Rejected executor left the serializer worker permanently latched");

      ArrayDeque<Runnable> deliveries = new ArrayDeque<>(); List<NotebookPersistence.Result> delivered = new ArrayList<>();
      NotebookPersistence bounded = new NotebookPersistence(queued::add, deliveries::add, delivered::add);
      long boundedLatest = 0;
      for (int i = 0; i < 25; i++) {
        model.source(0, "delivery-" + i); boundedLatest = bounded.submit(model.snapshot()); queued.removeFirst().run();
        require(deliveries.size() == 1, "UI completion queue grew beyond one scheduled delivery");
      }
      deliveries.removeFirst().run();
      require(delivered.size() == 1 && delivered.getFirst().generation() == boundedLatest,
          "Prepared results were not coalesced to the newest UI completion");
      System.out.println("{\"status\":\"pass\",\"offSubmittingThread\":true,\"latestOnlyCoalescing\":true,\"dirtyBeforeCompletion\":true,\"staleCommitRejected\":true,\"externalGenerationInvalidated\":true,\"serializationFailureRemainsDirty\":true,\"mergeSuspensionKeepsDirty\":true,\"executorRejectionRecovers\":true,\"completionQueueBounded\":true}");
    } finally { worker.shutdownNow(); }
  }
}
