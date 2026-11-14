package dev.openpycharm.notebooks;

import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.editor.Document;
import com.intellij.openapi.fileEditor.FileDocumentManager;
import com.intellij.util.concurrency.AppExecutorUtil;
import java.util.concurrent.Executor;
import java.util.function.BooleanSupplier;
import java.util.function.Consumer;
import javax.swing.SwingUtilities;

/** The fixed 261 implementation supports background saves, as used by its own
 * SaveAndSyncHandlerImpl. Its initial bridge invokesAndWait BEFORE taking its
 * internal write action. No caller read/write/write-intent lock may span that
 * callback. This is a pinned implementation contract, not a general guarantee
 * of the public FileDocumentManager API (whose annotations differ).
 */
public final class NotebookDocumentSave {
  private NotebookDocumentSave() { }
  public static void request(Document document, Consumer<String> failure) {
    var application = ApplicationManager.getApplication();
    submit(AppExecutorUtil.getAppExecutorService(),
        () -> application.isReadAccessAllowed() || application.isWriteAccessAllowed() || application.isWriteIntentLockAcquired(),
        () -> FileDocumentManager.getInstance().saveDocument(document),
        error -> application.invokeLater(() -> failure.accept(error.getMessage())));
  }
  static void submit(Executor worker, BooleanSupplier hasOuterLock, Runnable platformSave, Consumer<RuntimeException> failure) {
    try {
      worker.execute(() -> {
        try {
          if (SwingUtilities.isEventDispatchThread() || hasOuterLock.getAsBoolean())
            throw new IllegalStateException("Notebook save requires an unlocked background thread");
          // FileDocumentManager owns the write lock and transfer-to-EDT phases.
          platformSave.run();
        } catch (RuntimeException error) { failure.accept(error); }
      });
    } catch (RuntimeException error) { failure.accept(error); }
  }
}
