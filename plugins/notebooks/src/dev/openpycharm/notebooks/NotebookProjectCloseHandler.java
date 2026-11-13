package dev.openpycharm.notebooks;

import com.intellij.openapi.project.Project;
import com.intellij.openapi.project.ProjectCloseHandler;
import com.intellij.openapi.vfs.VirtualFile;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/** Pending edits must reach the ordinary document before the platform closes/saves a project.
 * A closed tab remains registered only until its pending document update is applied.
 */
public final class NotebookProjectCloseHandler implements ProjectCloseHandler {
  private static final Set<NotebookFileEditor> EDITORS = ConcurrentHashMap.newKeySet();
  static void register(NotebookFileEditor editor) { EDITORS.add(editor); }
  static void unregister(NotebookFileEditor editor) { EDITORS.remove(editor); }
  static NotebookFileEditor.PendingState takePending(Project project, VirtualFile file) {
    for (NotebookFileEditor editor : EDITORS) {
      if (editor.ownsProject(project) && editor.getFile().equals(file) && editor.canRestorePending() && EDITORS.remove(editor))
        return editor.detachPending();
    }
    return null;
  }
  @Override public boolean canClose(Project project) {
    boolean ready = true;
    for (NotebookFileEditor editor : EDITORS) {
      if (editor.ownsProject(project) && editor.hasPendingEdits()) {
        editor.pendingCloseNotice(); ready = false;
      }
    }
    return ready;
  }
}
