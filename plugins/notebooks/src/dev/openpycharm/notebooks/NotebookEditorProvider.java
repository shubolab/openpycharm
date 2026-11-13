package dev.openpycharm.notebooks;

import com.intellij.openapi.editor.Document;
import com.intellij.openapi.fileEditor.*;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.vfs.VirtualFile;

/** The asynchronous provider loads and parses notebook files outside the Swing EDT. */
public final class NotebookEditorProvider implements AsyncFileEditorProvider {
  @Override public boolean accept(Project project, VirtualFile file) {
    return !file.isDirectory() && "ipynb".equalsIgnoreCase(file.getExtension());
  }
  @Override public Builder createEditorAsync(Project project, VirtualFile file) {
    Document document = FileDocumentManager.getInstance().getDocument(file);
    NotebookModel model = null; String problem = null;
    try {
      if (document == null) throw new IllegalArgumentException("Cannot load notebook as a text document");
      model = NotebookModel.parse(document.getText());
    } catch (RuntimeException error) { problem = error.getMessage(); }
    NotebookModel loaded = model; String message = problem;
    return new Builder() {
      @Override public FileEditor build() { return new NotebookFileEditor(project, file, document, loaded, message); }
    };
  }
  @Override public FileEditor createEditor(Project project, VirtualFile file) {
    // Legacy synchronous callers can display a bounded message, never read files on the EDT.
    return new NotebookFileEditor(project, file, FileDocumentManager.getInstance().getCachedDocument(file), null,
        "Notebook is loading. Reopen this tab if the asynchronous editor has not loaded; the JSON editor remains available.");
  }
  @Override public String getEditorTypeId() { return "openpycharm-notebook"; }
  @Override public FileEditorPolicy getPolicy() { return FileEditorPolicy.PLACE_BEFORE_DEFAULT_EDITOR; }
}
