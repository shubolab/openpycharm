package dev.openpycharm.notebooks;

import com.intellij.icons.AllIcons;
import com.intellij.openapi.fileTypes.FileType;
import javax.swing.Icon;

/** Registers .ipynb as text so an unrecognized-extension prompt cannot block the provider. */
public final class NotebookFileType implements FileType {
  public static final NotebookFileType INSTANCE = new NotebookFileType();
  private NotebookFileType() { }
  @Override public String getName() { return "OpenPyCharm Notebook"; }
  @Override public String getDescription() { return "Jupyter notebook (nbformat 4)"; }
  @Override public String getDefaultExtension() { return "ipynb"; }
  @Override public Icon getIcon() { return AllIcons.FileTypes.Json; }
  @Override public boolean isBinary() { return false; }
}
