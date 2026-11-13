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
  private final Function<NotebookModel.Snapshot, String> serializer;
  private long generation;
  private boolean dirty, working;
  private Pending pending;

  public NotebookPersistence(Executor executor, Consumer<Result> completion) {
    this(executor, completion, NotebookModel.Snapshot::json);
  }
  NotebookPersistence(Executor executor, Consumer<Result> completion, Function<NotebookModel.Snapshot, String> serializer) {
    this.executor = executor; this.completion = completion; this.serializer = serializer;
  }
  public synchronized long submit(NotebookModel.Snapshot snapshot) {
    long current = ++generation;
    dirty = true;
    pending = new Pending(current, snapshot);
    if (!working) { working = true; executor.execute(this::drain); }
    return current;
  }
  public synchronized void invalidate() { ++generation; pending = null; dirty = false; }
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
      if (isCurrent(next.generation())) completion.accept(result);
    }
  }
}
