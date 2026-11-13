package dev.openpycharm.notebooks;

import com.intellij.openapi.project.Project;
import com.intellij.openapi.project.ProjectCloseHandler;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/** Pending edits must reach the ordinary document before the platform closes/saves a project.
 * A closed tab remains registered only until its pending document update is applied.
 */
public final class NotebookProjectCloseHandler implements ProjectCloseHandler {
  private static final Set<NotebookFileEditor> EDITORS = ConcurrentHashMap.newKeySet();
  static void register(NotebookFileEditor editor) { EDITORS.add(editor); }
  static void unregister(NotebookFileEditor editor) { EDITORS.remove(editor); }
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
