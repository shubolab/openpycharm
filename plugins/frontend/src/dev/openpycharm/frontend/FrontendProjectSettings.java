package dev.openpycharm.frontend;

import com.intellij.openapi.Disposable;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.components.PersistentStateComponent;
import com.intellij.openapi.components.Service;
import com.intellij.openapi.components.State;
import com.intellij.openapi.components.Storage;
import com.intellij.openapi.components.StoragePathMacros;
import com.intellij.openapi.project.Project;
import com.intellij.platform.lsp.api.LspClientManager;
import java.util.concurrent.Executor;

/** Project-local opt-out; unrelated Git, npm and service authentication is never changed. */
@Service(Service.Level.PROJECT)
@State(name = "OpenPyCharmFrontend", storages = @Storage(StoragePathMacros.WORKSPACE_FILE))
public final class FrontendProjectSettings implements PersistentStateComponent<FrontendProjectSettings.Bean>, Disposable {
  public static final class Bean { public boolean enabled = true; }
  private volatile boolean enabled = true, observed, disposed;
  private long generation;
  private final FrontendSettingsLifecycle lifecycle;

  public FrontendProjectSettings(Project project) {
    this(command -> ApplicationManager.getApplication().executeOnPooledThread(command), () -> {
      if (!project.isDisposed()) LspClientManager.getInstance(project).stopAndRestartClientsIfNeeded(FrontendProductLspProvider.class);
    });
  }

  FrontendProjectSettings(Executor executor, Runnable restart) { lifecycle = new FrontendSettingsLifecycle(executor, restart); }

  static FrontendProjectSettings getInstance(Project project) { return project.getService(FrontendProjectSettings.class); }
  boolean enabled() { observed = true; return !disposed && enabled; }
  synchronized long generation() { return generation; }
  boolean restartPending() { return lifecycle.pending(); }
  synchronized boolean active(long revision) { return enabled() && revision == generation; }

  @Override public Bean getState() { Bean state = new Bean(); state.enabled = enabled; return state; }
  @Override public void loadState(Bean state) {
    boolean restart;
    synchronized (this) {
      boolean changed = enabled != state.enabled;
      enabled = state.enabled;
      if (changed) generation++;
      restart = changed && observed && !disposed;
    }
    // Persisted state still loads if the application pool is closing. Apply can retry pending work.
    if (restart) try { lifecycle.request(); } catch (RuntimeException rejected) { }
  }

  void setEnabled(boolean value) {
    boolean changed;
    synchronized (this) {
      if (disposed) return;
      changed = enabled != value;
      enabled = value;
      if (changed) generation++;
    }
    if (changed || lifecycle.pending()) lifecycle.request();
  }

  @Override public void dispose() { synchronized (this) { disposed = true; generation++; } lifecycle.close(); }
}
