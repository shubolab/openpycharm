package dev.openpycharm.frontend;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import javax.swing.SwingUtilities;

/** Thread/queue controls only; no IDE, language server or process. */
public final class FrontendBoundedOutputTest {
  private static void require(boolean value, String message) { if (!value) throw new AssertionError(message); }
  public static void main(String[] args) throws Exception {
    CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
    ByteArrayOutputStream captured = new ByteArrayOutputStream();
    OutputStream sink = new OutputStream() {
      @Override public void write(int value) throws IOException { write(new byte[]{(byte)value}); }
      @Override public void write(byte[] value, int offset, int length) throws IOException {
        entered.countDown(); try { if (!release.await(2, TimeUnit.SECONDS)) throw new IOException("test release timeout"); }
        catch (InterruptedException failure) { throw new IOException(failure); }
        captured.write(value, offset, length);
      }
    };
    FrontendBoundedOutput output = new FrontendBoundedOutput(sink, 1000, release::countDown);
    AtomicReference<Throwable> firstFailure = new AtomicReference<>(), secondFailure = new AtomicReference<>();
    AtomicBoolean interruptedPreserved = new AtomicBoolean();
    Thread first = new Thread(() -> {
      try { output.write("request😀".getBytes(StandardCharsets.UTF_8)); interruptedPreserved.set(Thread.currentThread().isInterrupted()); }
      catch (Throwable failure) { firstFailure.set(failure); }
    });
    Thread second = new Thread(() -> { try { output.write("shared-document-change".getBytes(StandardCharsets.UTF_8)); } catch (Throwable failure) { secondFailure.set(failure); } });
    first.start(); require(entered.await(1, TimeUnit.SECONDS), "Writer never entered actual blocking sink");
    second.start(); first.interrupt(); release.countDown(); first.join(2000); second.join(2000);
    require(!first.isAlive() && !second.isAlive() && firstFailure.get() == null && secondFailure.get() == null, "Interrupted request truncated shared FIFO output");
    require(interruptedPreserved.get() && captured.toString(StandardCharsets.UTF_8).equals("request😀shared-document-change"), "FIFO bytes or interrupt state changed");
    SwingUtilities.invokeAndWait(() -> {
      try { output.flush(); throw new AssertionError("Native transport allowed a blocking EDT flush"); }
      catch (IOException expected) { }
    });
    long before = System.nanoTime(); SwingUtilities.invokeAndWait(output::close);
    require(TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - before) < 1000 && output.awaitStopped(1000), "EDT close blocked on a pipe");

    CountDownLatch deadlineRelease = new CountDownLatch(1); AtomicInteger failed = new AtomicInteger();
    FrontendBoundedOutput timeout = new FrontendBoundedOutput(new OutputStream() {
      @Override public void write(int value) throws IOException { try { deadlineRelease.await(2, TimeUnit.SECONDS); } catch (InterruptedException error) { throw new IOException(error); } }
    }, 100, () -> { failed.incrementAndGet(); deadlineRelease.countDown(); });
    before = System.nanoTime();
    try { timeout.write(42); throw new AssertionError("Blocked write had no deadline"); } catch (IOException expected) { }
    require(TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - before) < 700 && failed.get() == 1 && timeout.awaitStopped(1000), "Deadline/independent release did not bound the OS owner");
    try { timeout.write(43); throw new AssertionError("Failed transport accepted another write"); } catch (IOException expected) { }
    System.out.println("{\"status\":\"pass\",\"fifoUtf8Preserved\":true,\"requestInterruptDoesNotTruncateSharedWrites\":true,\"deadlineTerminal\":true,\"edtCloseIsAsync\":true,\"edtWriteRejected\":true,\"nativeIdeStarted\":false}");
  }
}
