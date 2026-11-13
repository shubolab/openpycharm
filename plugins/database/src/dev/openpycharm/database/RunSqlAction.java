package dev.openpycharm.database;

import com.intellij.openapi.actionSystem.*;
import com.intellij.openapi.editor.Editor;
import com.intellij.openapi.wm.ToolWindowManager;
import com.intellij.openapi.ui.Messages;
import org.jetbrains.annotations.NotNull;

/** Run the selected SQL or statement at the caret through the connected native console. */
public final class RunSqlAction extends AnAction {
  @Override public @NotNull ActionUpdateThread getActionUpdateThread(){return ActionUpdateThread.BGT;}
  @Override public void update(@NotNull AnActionEvent e){var file=e.getData(CommonDataKeys.VIRTUAL_FILE);e.getPresentation().setEnabledAndVisible(e.getProject()!=null&&e.getData(CommonDataKeys.EDITOR)!=null&&file!=null&&"sql".equalsIgnoreCase(file.getExtension()));}
  @Override public void actionPerformed(@NotNull AnActionEvent e){
    var project=e.getProject();Editor editor=e.getData(CommonDataKeys.EDITOR);if(project==null||editor==null)return;
    try {
      if(editor.getDocument().getTextLength()>SqlText.MAX_SQL)throw new IllegalArgumentException("SQL exceeds the 1 MiB console limit");
      String selection=editor.getSelectionModel().getSelectedText();
      String query=selection==null?SqlText.atCaret(editor.getDocument().getText(),editor.getCaretModel().getOffset()):SqlText.single(selection);
      var window=ToolWindowManager.getInstance(project).getToolWindow("Database");if(window==null)return;
      window.activate(()->{for(var content:window.getContentManager().getContents())if(content.getComponent() instanceof DatabaseToolWindow.Panel panel){panel.runSql(query);return;}});
    }catch(RuntimeException ex){Messages.showErrorDialog(project,ex.getMessage(),"Run SQL statement");}
  }
}
