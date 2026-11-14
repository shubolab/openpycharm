package dev.openpycharm.frontend;

import com.intellij.execution.ExecutionException;
import com.intellij.execution.configurations.GeneralCommandLine;
import com.intellij.execution.process.*;
import com.intellij.openapi.Disposable;
import com.intellij.openapi.util.Disposer;
import com.intellij.util.io.BaseDataReader;
import com.intellij.util.io.BaseOutputReader;
import java.io.OutputStream;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import javax.swing.SwingUtilities;

/** Actual public SDK handler with bounded FIFO stdin and independently owned cleanup. */
final class FrontendNativeProcess extends OSProcessHandler implements Disposable {
  private final FrontendProcessLifetime lifetime;
  private final FrontendBoundedOutput input;
  FrontendNativeProcess(GeneralCommandLine command) throws ExecutionException {
    super(backgroundCommand(command));
    setShouldDestroyProcessRecursively(true);
    try { lifetime = new FrontendProcessLifetime(getProcess()); }
    catch (RuntimeException startupFailure) {
      getProcess().destroyForcibly(); throw new ExecutionException("Frontend process ownership initialization failed", startupFailure);
    }
    input = new FrontendBoundedOutput(super.getProcessInput(), 2000, lifetime::close); lifetime.input(input);
    addProcessListener(new ProcessAdapter() {
      @Override public void processTerminated(ProcessEvent event) { lifetime.close(); }
    });
  }
  private static GeneralCommandLine backgroundCommand(GeneralCommandLine command) throws ExecutionException {
    if (SwingUtilities.isEventDispatchThread()) throw new ExecutionException("Frontend process start requires a worker");
    return command;
  }
  @Override public OutputStream getProcessInput() { return input == null ? super.getProcessInput() : input; }
  @Override protected BaseOutputReader.Options readerOptions() {
    // Match the public LSP descriptor's framing requirement: preserve CR in CRLF.
    return new BaseOutputReader.Options() {
      @Override public boolean splitToLines() { return false; }
      @Override public BaseDataReader.SleepingPolicy policy() { return BaseOutputReader.Options.forMostlySilentProcess().policy(); }
    };
  }
  @Override protected void destroyProcessImpl() { lifetime.close(); }
  @Override protected void detachProcessImpl() { lifetime.close(); }
  void register(Disposable parent) {
    Disposer.register(parent, this);
    cleanup().whenComplete((report, failure) -> Disposer.dispose(this));
  }
  @Override public void dispose() { lifetime.close(); }
  CompletableFuture<Map<String, Object>> cleanup() { return lifetime.completion(); }
}
