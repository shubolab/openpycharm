package dev.openpycharm.notebooks;

import com.intellij.openapi.application.Application;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.fileTypes.PlainTextFileType;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.util.ThrowableComputable;
import com.intellij.psi.PsiFileFactory;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;
import javax.swing.JButton;
import javax.swing.SwingUtilities;

/** Ordinary Swing callback/read-action topology; actual PSI construction requires the native IDE gate. */
public final class NotebookCellReadAccessTest {
  private static final class ReachedPsiService extends RuntimeException { }
  private static void require(boolean value, String message) { if (!value) throw new AssertionError(message); }
  public static void main(String[] args) throws Exception {
    ThreadLocal<Integer> reads = ThreadLocal.withInitial(() -> 0);
    AtomicInteger entered = new AtomicInteger(), guarded = new AtomicInteger(), denied = new AtomicInteger();
    Application previous = ApplicationManager.getApplication();
    Application application = (Application)Proxy.newProxyInstance(Application.class.getClassLoader(), new Class[]{Application.class}, (proxy, method, arguments) -> {
      return switch (method.getName()) {
        case "isUnitTestMode", "isWriteAccessAllowed", "isWriteIntentLockAcquired" -> false;
        case "isDispatchThread" -> SwingUtilities.isEventDispatchThread();
        case "isReadAccessAllowed" -> reads.get() != 0;
        case "runReadAction" -> {
          require(SwingUtilities.isEventDispatchThread(), "Cell setup left its ordinary Swing callback");
          entered.incrementAndGet(); reads.set(reads.get() + 1);
          try { yield ((ThrowableComputable<?, ?>)arguments[0]).compute(); }
          finally { reads.set(reads.get() - 1); }
        }
        case "toString" -> "owned read-contract application";
        default -> throw new AssertionError("Unexpected application operation: " + method.getName());
      };
    });
    Project project = (Project)Proxy.newProxyInstance(Project.class.getClassLoader(), new Class[]{Project.class}, (proxy, method, arguments) -> {
      if (method.getName().equals("getService") && arguments[0] == PsiFileFactory.class) {
        if (reads.get() == 0) { denied.incrementAndGet(); throw new IllegalStateException("PSI service entered without read access"); }
        guarded.incrementAndGet(); throw new ReachedPsiService();
      }
      throw new AssertionError("Unexpected project operation: " + method.getName());
    });
    try {
      ApplicationManager.setApplication(application);
      SwingUtilities.invokeAndWait(() -> {
        JButton unguarded = new JButton("baseline");
        unguarded.addActionListener(event -> {
          require(!application.isReadAccessAllowed(), "Fixture supplied an implicit outer read action");
          try { PsiFileFactory.getInstance(project); throw new AssertionError("Unguarded baseline should fail"); }
          catch (IllegalStateException expected) { }
        });
        unguarded.doClick(0);
        for (String name : new String[]{"notebook-cell-0.py", "notebook-cell-1.md"}) {
          JButton add = new JButton(name);
          add.addActionListener(event -> {
            require(!application.isReadAccessAllowed(), "Button arrived with implicit read access");
            try {
              NotebookFileEditor.cellDocument(project, name, PlainTextFileType.INSTANCE, "value = '中文'\n");
              throw new AssertionError("Owned service sentinel did not run");
            } catch (ReachedPsiService expected) { }
            require(!application.isReadAccessAllowed() && !application.isWriteIntentLockAcquired(), "Read scope leaked into later button/save work");
          });
          add.doClick(0);
        }
      });
      require(denied.get() == 1 && entered.get() == 2 && guarded.get() == 2, "Ordinary callback regression was not exercised");
      System.out.println("{\"status\":\"pass\",\"unguardedSwingCallbackRejected\":true,\"cellPsiEntryHasReadAccess\":true,\"exceptionUnwindsReadScope\":true,\"outerWriteIntentAdded\":false,\"actualPsiCreationExercised\":false,\"nativeIdeLaunched\":false}");
    } finally { ApplicationManager.setApplication(previous); }
  }
}
