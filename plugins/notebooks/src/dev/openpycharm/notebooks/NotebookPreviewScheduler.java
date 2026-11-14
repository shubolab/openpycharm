package dev.openpycharm.notebooks;

import java.util.*;
import java.util.concurrent.*;
import java.util.function.Consumer;

/** One active worker, one latest input/result per cell, and an aggregate decoded-pixel budget. */
public final class NotebookPreviewScheduler implements AutoCloseable {
  private static final int MAX_CELLS = NotebookModel.MAX_CELLS;
  private final Executor worker, delivery;
  private final IdentityHashMap<Object, Cell> cells = new IdentityHashMap<>();
  private final ArrayDeque<Cell> pending = new ArrayDeque<>(), deliveries = new ArrayDeque<>();
  private boolean working, deliveryQueued, closed;
  private long pixels;
  private static final class Cell {
    final Object key;
    long generation, preparedGeneration;
    boolean queued, deliveryQueued;
    NotebookRichOutput.Input input;
    NotebookRichOutput.Cancellation cancellation;
    NotebookRichOutput.Plan plan;
    Consumer<NotebookRichOutput.Plan> consumer;
    Cell(Object key) { this.key = key; }
  }
  public NotebookPreviewScheduler(Executor worker, Executor delivery) { this.worker = worker; this.delivery = delivery; }
  /** The consumer borrows a Plan for this callback; a viewer must retain its own reference. */
  public synchronized void request(Object key, NotebookRichOutput.Input input, Consumer<NotebookRichOutput.Plan> consumer) {
    if (closed) return;
    Cell cell = cells.get(key);
    if (cell == null) {
      if (cells.size() >= MAX_CELLS) throw new IllegalStateException("Notebook preview cell limit reached");
      cell = new Cell(key); cells.put(key, cell);
    }
    if (cell.cancellation != null) cell.cancellation.cancel();
    cell.cancellation = new NotebookRichOutput.Cancellation();
    cell.input = input; cell.consumer = consumer; cell.generation++;
    if (!cell.queued) { cell.queued = true; pending.add(cell); }
    if (!working) {
      working = true;
      try { worker.execute(this::drain); }
      catch (RuntimeException error) { working = false; throw error; }
    }
  }
  private void drain() {
    while (true) {
      Cell cell; NotebookRichOutput.Input input; NotebookRichOutput.Cancellation cancellation; long generation, allowance;
      synchronized (this) {
        cell = pending.poll();
        if (cell == null) { working = false; return; }
        cell.queued = false;
        if (closed || cells.get(cell.key) != cell) continue;
        input = cell.input; cancellation = cell.cancellation; generation = cell.generation;
        allowance = NotebookRichOutput.NOTEBOOK_PIXEL_BUDGET - pixels + (cell.plan == null ? 0 : cell.plan.pixels());
      }
      NotebookRichOutput.Plan prepared;
      try { prepared = NotebookRichOutput.prepare(input, allowance, cancellation); }
      catch (CancellationException ignored) { continue; }
      catch (RuntimeException error) {
        try {
          var builder = new NotebookRichOutput.Builder(0, cancellation);
          builder.text("[Preview unavailable: " + error.getMessage() + "]\n"); prepared = builder.finish();
        } catch (CancellationException ignored) { continue; }
      }
      synchronized (this) {
        if (closed || cells.get(cell.key) != cell || cell.generation != generation) { prepared.close(); continue; }
        if (cell.plan != null) { pixels -= cell.plan.pixels(); cell.plan.close(); }
        cell.plan = prepared; cell.preparedGeneration = generation; pixels += prepared.pixels();
        if (pixels > NotebookRichOutput.NOTEBOOK_PIXEL_BUDGET) throw new IllegalStateException("Decoded preview pixel budget exceeded");
        if (!cell.deliveryQueued) { cell.deliveryQueued = true; deliveries.add(cell); }
        if (!deliveryQueued) { deliveryQueued = true; scheduleDelivery(); }
      }
    }
  }
  private void scheduleDelivery() {
    try { delivery.execute(this::deliver); }
    catch (RuntimeException ignored) { synchronized (this) { deliveryQueued = false; } }
  }
  private void deliver() {
    Cell cell; NotebookRichOutput.Plan plan = null; Consumer<NotebookRichOutput.Plan> consumer = null;
    synchronized (this) {
      cell = deliveries.poll();
      if (cell != null) {
        cell.deliveryQueued = false;
        if (!closed && cells.get(cell.key) == cell && cell.preparedGeneration == cell.generation && cell.plan != null) {
          plan = cell.plan.retain(); consumer = cell.consumer;
        }
      }
    }
    try { if (plan != null) consumer.accept(plan); }
    finally {
      if (plan != null) plan.close();
      synchronized (this) {
        deliveryQueued = false;
        if (!closed && !deliveries.isEmpty()) { deliveryQueued = true; scheduleDelivery(); }
      }
    }
  }
  public synchronized void remove(Object key) {
    Cell cell = cells.remove(key);
    if (cell == null) return;
    if (cell.cancellation != null) cell.cancellation.cancel();
    cell.input = null; cell.consumer = null;
    if (cell.plan != null) { pixels -= cell.plan.pixels(); cell.plan.close(); cell.plan = null; }
    pending.remove(cell); deliveries.remove(cell);
  }
  public synchronized long reservedPixels() { return pixels; }
  @Override public synchronized void close() {
    if (closed) return;
    closed = true;
    for (Object key : new ArrayList<>(cells.keySet())) remove(key);
    pending.clear(); deliveries.clear();
  }
}
