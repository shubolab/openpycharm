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

      NotebookPersistence failing = new NotebookPersistence(queued::add, callbacks::add, snapshot -> { throw new IllegalStateException("expected failure"); });
      long failureGeneration = failing.submit(model.snapshot()); queued.removeFirst().run();
      require(failing.isDirty() && callbacks.getLast().generation() == failureGeneration && callbacks.getLast().failure() != null,
          "Serialization failure silently cleared dirty state");
      System.out.println("{\"status\":\"pass\",\"offSubmittingThread\":true,\"latestOnlyCoalescing\":true,\"dirtyBeforeCompletion\":true,\"staleCommitRejected\":true,\"externalGenerationInvalidated\":true,\"serializationFailureRemainsDirty\":true}");
    } finally { worker.shutdownNow(); }
  }
}
