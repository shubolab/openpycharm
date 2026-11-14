package dev.openpycharm.frontend;

import java.util.concurrent.Executor;

/** Coalesced worker restarts. A rejected submission remains retryable by the next Apply. */
final class FrontendSettingsLifecycle implements AutoCloseable {
  private final Executor executor;
  private final Runnable restart;
  private long requested, completed;
  private boolean working, closed;
  private volatile RuntimeException failure;

  FrontendSettingsLifecycle(Executor executor, Runnable restart) {
    this.executor = executor; this.restart = restart;
  }

  synchronized boolean pending() { return !closed && requested != completed; }
  RuntimeException failure() { return failure; }

  void request() {
    synchronized (this) {
      if (closed) return;
      requested++;
      if (working) return;
      working = true;
    }
    try { executor.execute(this::drain); }
    catch (RuntimeException rejected) {
      synchronized (this) { working = false; failure = rejected; }
      throw rejected;
    }
  }

  private void drain() {
    for (;;) {
      long revision;
      synchronized (this) {
        if (closed || requested == completed) { working = false; return; }
        revision = requested;
      }
      try { restart.run(); }
      catch (RuntimeException error) {
        synchronized (this) { working = false; failure = error; }
        return;
      }
      synchronized (this) { completed = revision; failure = null; }
    }
  }

  @Override public synchronized void close() { closed = true; }
}
