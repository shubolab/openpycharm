package dev.openpycharm.notebooks;

import java.util.*;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicInteger;
import com.google.gson.JsonObject;

/** Real renderer plans with deterministic worker/UI queues and explicit resource ownership. */
public final class NotebookPreviewSchedulerTest {
  private static void require(boolean value, String message) { if (!value) throw new AssertionError(message); }
  public static void main(String[] args) throws Exception {
    ArrayDeque<Runnable> workers = new ArrayDeque<>(), deliveries = new ArrayDeque<>();
    List<NotebookRichOutput.Plan> shown = new ArrayList<>();
    NotebookPreviewScheduler scheduler = new NotebookPreviewScheduler(workers::add, deliveries::add);
    Object key = new Object();
    java.util.function.Consumer<NotebookRichOutput.Plan> keep = plan -> shown.add(plan.retain());
    for (int i = 0; i < 50; i++) scheduler.request(key, NotebookRichOutput.Input.markdown("# Version " + i, true), keep);
    require(workers.size() == 1, "Per-cell input queue was not coalesced"); workers.removeFirst().run();
    require(deliveries.size() == 1, "Preview delivery was not bounded");
    for (int i = 50; i < 75; i++) {
      scheduler.request(key, NotebookRichOutput.Input.markdown("# Version " + i, true), keep); workers.removeFirst().run();
      require(deliveries.size() == 1, "Prepared completion queue grew beyond one delivery");
    }
    deliveries.removeFirst().run();
    require(shown.size() == 1 && NotebookRichOutputTest.text(shown.getFirst()).contains("Version 74"), "Stale preview replaced latest Markdown");
    scheduler.remove(key); require(!shown.getFirst().released(), "Scheduler flushed an image/document still owned by its UI");
    shown.removeFirst().close();

    JsonObject image = NotebookRichOutputTest.output("image/png", NotebookRichOutputTest.encoded("PNG", 1000, 1000));
    List<Object> keys = new ArrayList<>();
    for (int i = 0; i < 6; i++) {
      Object cell = new Object(); keys.add(cell);
      scheduler.request(cell, new NotebookRichOutput.Input(List.of(image), null, true), keep); workers.removeFirst().run();
      require(scheduler.reservedPixels() <= NotebookRichOutput.NOTEBOOK_PIXEL_BUDGET, "Notebook-level image reservation exceeded cap");
    }
    while (!deliveries.isEmpty()) deliveries.removeFirst().run();
    require(shown.stream().mapToLong(NotebookRichOutput.Plan::pixels).sum() == 4_000_000, "Decoded image quota did not apply across cells");
    scheduler.request(keys.getFirst(), new NotebookRichOutput.Input(List.of(image), null, true), keep); workers.removeFirst().run();
    scheduler.remove(keys.getFirst()); while (!deliveries.isEmpty()) deliveries.removeFirst().run();
    int before = shown.size(); Object disposed = new Object();
    scheduler.request(disposed, new NotebookRichOutput.Input(List.of(image), null, true), keep); scheduler.remove(disposed);
    while (!workers.isEmpty()) workers.removeFirst().run(); while (!deliveries.isEmpty()) deliveries.removeFirst().run();
    require(shown.size() == before, "Disposed cell received a stale plan");
    scheduler.close(); scheduler.close();
    require(scheduler.reservedPixels() == 0, "Disposed scheduler retained its decoded image reservation");
    for (var plan : shown) plan.close();
    require(shown.stream().allMatch(NotebookRichOutput.Plan::released), "Plan resources survived scheduler/UI disposal");

    AtomicInteger attempts = new AtomicInteger();
    NotebookPreviewScheduler rejected = new NotebookPreviewScheduler(command -> {
      if (attempts.incrementAndGet() == 1) throw new RejectedExecutionException("once"); workers.add(command);
    }, deliveries::add);
    try { rejected.request(key, NotebookRichOutput.Input.markdown("first", true), keep); throw new AssertionError("Expected first rejection"); }
    catch (RejectedExecutionException expected) { }
    rejected.request(key, NotebookRichOutput.Input.markdown("retried", true), plan -> { try { require(NotebookRichOutputTest.text(plan).contains("retried"), "Rejected worker did not recover"); } catch (Exception error) { throw new AssertionError(error); } });
    workers.removeFirst().run(); while (!deliveries.isEmpty()) deliveries.removeFirst().run(); rejected.close();

    List<NotebookRichOutput.Plan> failedCallback = new ArrayList<>();
    NotebookPreviewScheduler throwing = new NotebookPreviewScheduler(workers::add, deliveries::add);
    throwing.request(key, new NotebookRichOutput.Input(List.of(image), null, true), plan -> { failedCallback.add(plan); throw new IllegalStateException("expected UI callback failure"); });
    workers.removeFirst().run();
    try { deliveries.removeFirst().run(); throw new AssertionError("Expected callback failure"); }
    catch (IllegalStateException expected) { }
    throwing.close(); require(failedCallback.getFirst().released(), "A failed UI consumer stranded its borrowed image reference");

    AtomicInteger deliveryAttempts = new AtomicInteger(); List<String> recovered = new ArrayList<>();
    NotebookPreviewScheduler rejectedDelivery = new NotebookPreviewScheduler(workers::add, command -> {
      if (deliveryAttempts.incrementAndGet() == 1) throw new RejectedExecutionException("delivery once"); deliveries.add(command);
    });
    java.util.function.Consumer<NotebookRichOutput.Plan> read = plan -> { try { recovered.add(NotebookRichOutputTest.text(plan)); } catch (Exception error) { throw new AssertionError(error); } };
    rejectedDelivery.request(key, NotebookRichOutput.Input.markdown("before rejection", true), read); workers.removeFirst().run();
    rejectedDelivery.request(key, NotebookRichOutput.Input.markdown("after rejection", true), read); workers.removeFirst().run();
    while (!deliveries.isEmpty()) deliveries.removeFirst().run();
    require(deliveryAttempts.get() == 2 && recovered.size() == 1 && recovered.getFirst().contains("after rejection"), "Rejected delivery did not recover with the newest result");
    rejectedDelivery.close();
    System.out.println("{\"status\":\"pass\",\"latestInputAndDeliveryOnly\":true,\"aggregatePixelBudget\":true,\"staleDisposeRejected\":true,\"imageReferencesReleased\":true,\"workerRejectionRecovers\":true}");
  }
}
