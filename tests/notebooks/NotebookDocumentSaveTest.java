package dev.openpycharm.notebooks;

import java.nio.file.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.ReentrantLock;
import javax.swing.SwingUtilities;

/** Thread-contract control, not an acceptance substitute for the actual IDE save engine. */
public final class NotebookDocumentSaveTest {
  private static void require(boolean value, String message) { if (!value) throw new AssertionError(message); }
  public static void main(String[] args) throws Exception {
    ExecutorService worker = Executors.newSingleThreadExecutor();
    ReentrantLock writeIntent = new ReentrantLock();
    Path directory = Files.createTempDirectory("openpycharm-save-contract-");
    try {
      NotebookModel model = NotebookModel.empty(); model.add("code"); model.source(0, "print('真实保存 中文')\nvalue = 3\n");
      String text = model.json(); Path file = directory.resolve("save.ipynb"); Files.writeString(file, "original");
      CountDownLatch complete = new CountDownLatch(1); AtomicInteger callbacks = new AtomicInteger(); AtomicReference<Throwable> failure = new AtomicReference<>();
      Runnable platformShapedSave = () -> {
        try {
          require(!SwingUtilities.isEventDispatchThread() && !writeIntent.isHeldByCurrentThread(), "Save entered with an outer UI/write-intent lock");
          // The actual 261 FileDocumentManager bridge makes this blocking EDT
          // callback before its internal write action. Exercise that topology.
          SwingUtilities.invokeAndWait(() -> {
            require(writeIntent.tryLock(), "Worker prevented the EDT from taking its lock");
            try { callbacks.incrementAndGet(); } finally { writeIntent.unlock(); }
          });
          require(!SwingUtilities.isEventDispatchThread(), "Filesystem write reached EDT"); Files.writeString(file, text);
          SwingUtilities.invokeAndWait(callbacks::incrementAndGet); complete.countDown();
        } catch (Exception error) { throw new IllegalStateException(error); }
      };
      SwingUtilities.invokeAndWait(() -> NotebookDocumentSave.submit(worker, writeIntent::isHeldByCurrentThread, platformShapedSave, error -> { failure.set(error); complete.countDown(); }));
      require(complete.await(5, TimeUnit.SECONDS) && failure.get() == null && callbacks.get() == 2, "Worker/EDT callback topology did not complete: " + failure.get());
      require(NotebookModel.parse(Files.readString(file)).source(0).contains("value = 3"), "Actual UTF-8 file round trip lost the pending edit");
      AtomicBoolean called = new AtomicBoolean(); CountDownLatch refused = new CountDownLatch(1);
      NotebookDocumentSave.submit(worker, () -> true, () -> called.set(true), error -> refused.countDown());
      require(refused.await(3, TimeUnit.SECONDS) && !called.get(), "Locked-worker entry was not refused before native callback");
      CountDownLatch rejected = new CountDownLatch(1);
      NotebookDocumentSave.submit(command -> { throw new RejectedExecutionException("owned test rejection"); }, () -> false, () -> called.set(true), error -> rejected.countDown());
      require(rejected.await(1, TimeUnit.SECONDS), "Rejected save scheduling was silently lost");
      System.out.println("{\"status\":\"pass\",\"unlockedWorker\":true,\"blockingEdtCallbacksComplete\":true,\"fileIoOffEdt\":true,\"utf8FileRoundTrip\":true,\"unsafeAndRejectedEntryReported\":true,\"actualIdeSaveEngineExercised\":false}");
    } finally { worker.shutdownNow(); Files.deleteIfExists(directory.resolve("save.ipynb")); Files.deleteIfExists(directory); }
  }
}
