package dev.openpycharm.notebooks;

import java.util.concurrent.Executor;
import java.util.function.Consumer;
import java.util.function.Function;

/** Single worker, one latest pending snapshot, and explicit dirty/generation state.
 * No IntelliJ application is required, so the race/dirty semantics are testable.
 */
public final class NotebookPersistence {
  public record Result(long generation, String text, RuntimeException failure) { }
  private record Pending(long generation, NotebookModel.Snapshot snapshot) { }
  private final Executor executor;
  private final Consumer<Result> completion;
  private final Executor delivery;
  private final Function<NotebookModel.Snapshot, String> serializer;
  private long generation;
  private boolean dirty, working;
  private Pending pending;
  private Result prepared;
  private boolean deliveryQueued;

  public NotebookPersistence(Executor executor, Consumer<Result> completion) {
    this(executor, Runnable::run, completion, NotebookModel.Snapshot::json);
  }
  public NotebookPersistence(Executor executor, Executor delivery, Consumer<Result> completion) {
    this(executor, delivery, completion, NotebookModel.Snapshot::json);
  }
  NotebookPersistence(Executor executor, Consumer<Result> completion, Function<NotebookModel.Snapshot, String> serializer) {
    this(executor, Runnable::run, completion, serializer);
  }
  private NotebookPersistence(Executor executor, Executor delivery, Consumer<Result> completion, Function<NotebookModel.Snapshot, String> serializer) {
    this.executor = executor; this.delivery = delivery; this.completion = completion; this.serializer = serializer;
  }
  public synchronized long submit(NotebookModel.Snapshot snapshot) {
    long current = ++generation;
    dirty = true;
    pending = new Pending(current, snapshot);
    if (!working) {
      working = true;
      try { executor.execute(this::drain); }
      catch (RuntimeException error) { working = false; post(new Result(current, null, error)); }
    }
    return current;
  }
  public synchronized void invalidate() { ++generation; pending = null; prepared = null; dirty = false; }
  /** Suspend stale commits without discarding edits while an external version is merged. */
  public synchronized void suspend() { ++generation; pending = null; prepared = null; }
  public synchronized void markDirty() { ++generation; pending = null; dirty = true; }
  public synchronized boolean isCurrent(long value) { return value == generation; }
  public synchronized boolean isDirty() { return dirty; }
  public synchronized boolean applied(long value) {
    if (value != generation) return false;
    dirty = false; return true;
  }
  private void drain() {
    while (true) {
      Pending next;
      synchronized (this) {
        next = pending; pending = null;
        if (next == null) { working = false; return; }
      }
      Result result;
      try { result = new Result(next.generation(), serializer.apply(next.snapshot()), null); }
      catch (RuntimeException error) { result = new Result(next.generation(), null, error); }
      post(result);
    }
  }
  private void post(Result result) {
    synchronized (this) {
      if (!isCurrent(result.generation())) return;
      prepared = result;
      if (deliveryQueued) return;
      deliveryQueued = true;
    }
    scheduleDelivery();
  }
  private void scheduleDelivery() {
    try { delivery.execute(this::deliver); }
    catch (RuntimeException ignored) { synchronized (this) { deliveryQueued = false; } }
  }
  private void deliver() {
    Result result;
    synchronized (this) { result = prepared; prepared = null; }
    try { if (result != null && isCurrent(result.generation())) completion.accept(result); }
    finally {
      boolean again;
      synchronized (this) { deliveryQueued = false; again = prepared != null; if (again) deliveryQueued = true; }
      if (again) scheduleDelivery();
    }
  }
}
