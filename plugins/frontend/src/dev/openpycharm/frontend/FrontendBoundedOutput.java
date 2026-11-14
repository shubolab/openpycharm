package dev.openpycharm.frontend;

import java.io.*;
import java.util.Arrays;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import javax.swing.SwingUtilities;

/** One FIFO owns the OS stream. No caller closes a stream behind a blocked writer. */
final class FrontendBoundedOutput extends OutputStream {
  static final int MAX_WRITE_BYTES = 8 * 1024 * 1024, QUEUE_SIZE = 8;
  private final OutputStream stream;
  private final Runnable failed;
  private final long timeoutNanos;
  private final ArrayBlockingQueue<Write> queue = new ArrayBlockingQueue<>(QUEUE_SIZE);
  private final AtomicReference<IOException> terminal = new AtomicReference<>();
  private final AtomicBoolean stopped = new AtomicBoolean();
  private final Thread writer;
  private record Write(byte[] bytes, boolean flush, long deadline, CompletableFuture<Void> result) { }

  FrontendBoundedOutput(OutputStream stream, long timeoutMillis, Runnable failed) {
    this.stream = stream; this.failed = failed; timeoutNanos = TimeUnit.MILLISECONDS.toNanos(timeoutMillis);
    writer = new Thread(this::drain, "OpenPyCharm frontend stdin"); writer.setDaemon(true); writer.start();
  }
  @Override public void write(int value) throws IOException { write(new byte[]{(byte)value}); }
  @Override public void write(byte[] data, int offset, int length) throws IOException {
    requireWorker();
    java.util.Objects.checkFromIndexSize(offset, length, data.length);
    if (length > MAX_WRITE_BYTES) { fail(new IOException("Frontend write exceeds its 8 MiB limit")); throw terminal.get(); }
    send(Arrays.copyOfRange(data, offset, offset + length), false);
  }
  @Override public void flush() throws IOException { send(new byte[0], true); }
  private static void requireWorker() throws IOException {
    if (SwingUtilities.isEventDispatchThread()) throw new IOException("Frontend transport writes require a worker");
  }
  private void send(byte[] bytes, boolean flush) throws IOException {
    requireWorker();
    long deadline = System.nanoTime() + timeoutNanos;
    IOException error = terminal.get();
    if (error != null || stopped.get()) throw error == null ? new IOException("Frontend input is closed") : error;
    Write write = new Write(bytes, flush, deadline, new CompletableFuture<>());
    boolean interrupted = false;
    try {
      while (true) {
        long remaining = deadline - System.nanoTime();
        if (remaining <= 0) throw new TimeoutException();
        try { if (!queue.offer(write, remaining, TimeUnit.NANOSECONDS)) throw new TimeoutException(); break; }
        catch (InterruptedException cancellation) { interrupted = true; }
      }
      // Cancelling one IDE request must not truncate an accepted shared LSP
      // notification/frame. Preserve FIFO delivery or fail the whole transport
      // at its deadline; restore the caller's interrupt flag afterwards.
      while (true) {
        long remaining = deadline - System.nanoTime();
        if (remaining <= 0) throw new TimeoutException();
        try { write.result().get(remaining, TimeUnit.NANOSECONDS); return; }
        catch (InterruptedException cancellation) { interrupted = true; }
      }
    } catch (TimeoutException timeout) {
      IOException failure = new IOException("Frontend input write deadline exceeded", timeout); fail(failure); throw failure;
    } catch (ExecutionException failure) {
      throw new IOException("Frontend input write failed", failure.getCause());
    } finally { if (interrupted) Thread.currentThread().interrupt(); }
  }
  private void drain() {
    try {
      while (!stopped.get()) {
        Write write = queue.poll(100, TimeUnit.MILLISECONDS);
        if (write == null) continue;
        if (System.nanoTime() >= write.deadline()) {
          IOException timeout = new IOException("Queued frontend write expired"); write.result().completeExceptionally(timeout); fail(timeout); break;
        }
        try {
          if (write.flush()) stream.flush(); else stream.write(write.bytes());
          write.result().complete(null);
        } catch (IOException failure) { write.result().completeExceptionally(failure); fail(failure); break; }
      }
    } catch (InterruptedException stopped) { Thread.currentThread().interrupt(); }
    finally {
      rejectPending();
      try { stream.close(); } catch (IOException failure) { terminal.compareAndSet(null, failure); }
    }
  }
  private void fail(IOException failure) {
    if (terminal.compareAndSet(null, failure)) { stop(); failed.run(); }
  }
  private void rejectPending() {
    Write pending;
    while ((pending = queue.poll()) != null) pending.result().completeExceptionally(new IOException("Frontend transport stopped"));
  }
  void stop() { stopped.set(true); rejectPending(); }
  @Override public void close() { stop(); failed.run(); }
  boolean awaitStopped(long millis) throws InterruptedException { writer.join(Math.max(1, millis)); return !writer.isAlive(); }
  boolean writerAlive() { return writer.isAlive(); }
}
