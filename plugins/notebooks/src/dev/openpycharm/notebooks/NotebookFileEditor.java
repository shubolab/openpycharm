package dev.openpycharm.notebooks;

import com.google.gson.*;
import com.intellij.ide.impl.TrustedProjects;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.command.WriteCommandAction;
import com.intellij.openapi.editor.*;
import com.intellij.openapi.editor.event.DocumentEvent;
import com.intellij.openapi.editor.event.DocumentListener;
import com.intellij.openapi.fileEditor.*;
import com.intellij.openapi.fileTypes.*;
import com.intellij.openapi.module.Module;
import com.intellij.openapi.module.ModuleUtilCore;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.projectRoots.Sdk;
import com.intellij.openapi.roots.ProjectRootManager;
import com.intellij.openapi.util.UserDataHolderBase;
import com.intellij.openapi.util.Disposer;
import com.intellij.openapi.Disposable;
import com.intellij.openapi.vfs.VirtualFile;
import com.intellij.psi.*;
import com.intellij.ui.components.*;
import com.intellij.util.concurrency.AppExecutorUtil;
import com.jetbrains.python.PythonFileType;
import com.jetbrains.python.sdk.legacy.PythonSdkUtil;
import java.awt.*;
import java.awt.event.*;
import java.beans.*;
import java.util.*;
import java.util.List;
import javax.swing.*;

/** Native IntelliJ editors and Python PSI for cells; no browser or notebook server. */
public final class NotebookFileEditor extends UserDataHolderBase implements FileEditor {
  private final Project project;
  private final VirtualFile file;
  private final Document document;
  private final NotebookPersistence persistence;
  private NotebookModel.Snapshot baseline;
  record PendingState(NotebookModel.Snapshot baseline, NotebookModel.Snapshot local) { }
  private NotebookModel model;
  private final JPanel component = new JPanel(new BorderLayout());
  private final JPanel body = new JPanel();
  private final JBLabel status = new JBLabel("Kernel stopped — runs only when you execute a cell");
  private final JBLabel interpreter = new JBLabel();
  private final PropertyChangeSupport changes = new PropertyChangeSupport(this);
  private final List<Cell> cells = new ArrayList<>();
  private final Map<String, Cell> executing = new HashMap<>();
  private final ArrayDeque<Cell> queue = new ArrayDeque<>();
  private final Map<String, List<DisplayReference>> displays = new HashMap<>();
  private record DisplayReference(Cell cell, JsonObject output) { }
  private NotebookKernelSession session;
  private String sessionPython;
  private volatile boolean writing, disposed, reloading;
  private boolean busy, restarting, saveRequested, persistenceFailed;
  private long expectedDocumentStamp;
  private NotebookModel conflictText, conflictMerged;
  private String conflictProblem;
  private boolean conflicted;
  private final JButton keepNotebook = new JButton("Keep Notebook Edits");
  private final JButton useText = new JButton("Discard Notebook Edits and Use Text");
  private long reloadGeneration;
  private long kernelGeneration;

  public NotebookFileEditor(Project project, VirtualFile file, Document document, NotebookModel model, String problem) {
    this.project = project; this.file = file; this.document = document;
    PendingState restored = NotebookProjectCloseHandler.takePending(project, file);
    this.model = restored == null ? model : restored.local().mutableModel();
    baseline = restored == null ? model == null ? null : model.snapshot() : restored.baseline();
    persistence = new NotebookPersistence(AppExecutorUtil.getAppExecutorService(), action ->
        ApplicationManager.getApplication().invokeLater(action), this::applyPersistence);
    if (restored != null) persistence.markDirty();
    NotebookProjectCloseHandler.register(this);
    body.setLayout(new BoxLayout(body, BoxLayout.Y_AXIS));
    JPanel toolbar = new JPanel(new FlowLayout(FlowLayout.LEFT, 8, 4));
    button(toolbar, "Run All", () -> { if (!canExecute()) return; queue.clear(); queue.addAll(cells.stream().filter(cell -> cell.kind.equals("code")).toList()); next(); });
    button(toolbar, "Interrupt", () -> { queue.clear(); if (session != null) session.request(UUID.randomUUID().toString(), "interrupt", null); });
    button(toolbar, "Restart Kernel", () -> { queue.clear(); restart(); });
    button(toolbar, "+ Code", () -> add("code"));
    button(toolbar, "+ Markdown", () -> add("markdown"));
    button(toolbar, "Save", this::save);
    keepNotebook.setVisible(false); useText.setVisible(false);
    keepNotebook.setToolTipText("Keep notebook values for overlapping fields and preserve independent text changes");
    keepNotebook.addActionListener(event -> resolveConflict(true));
    useText.addActionListener(event -> resolveConflict(false));
    toolbar.add(keepNotebook); toolbar.add(useText);
    button(toolbar, "Clear Outputs", () -> {
      if (model == null || busy || reloading) return;
      displays.clear(); cells.forEach(cell -> cell.clearBeforeOutput = false);
      for (int i = 0; i < model.size(); i++) if (model.kind(i).equals("code")) model.clearOutputs(i);
      sync(); for (Cell cell : cells) cell.refreshOutput();
    });
    JPanel heading = new JPanel(new BorderLayout());
    heading.add(toolbar, BorderLayout.NORTH);
    JPanel information = new JPanel(new GridLayout(0, 1)); information.add(interpreter); information.add(status);
    information.setBorder(BorderFactory.createEmptyBorder(2, 10, 7, 10));
    heading.add(information, BorderLayout.CENTER); component.add(heading, BorderLayout.NORTH);
    component.add(new JBScrollPane(body), BorderLayout.CENTER);
    refreshInterpreter();
    if (this.model == null) showProblem(problem); else rebuild();
    if (document != null) document.addDocumentListener(new DocumentListener() {
      @Override public void documentChanged(DocumentEvent event) {
        if (writing || disposed) return;
        // A platform background save can normalize the parent document while
        // holding its own write action. Keep all mutable editor/model state on
        // the EDT; never wait for that thread from a document callback.
        if (ApplicationManager.getApplication().isDispatchThread()) reloadFromDocument();
        else ApplicationManager.getApplication().invokeLater(() -> { if (!disposed && !writing) reloadFromDocument(); });
      }
    }, this);
    if (restored != null && document != null) reloadFromDocument();
  }

  private void reloadFromDocument() {
    ApplicationManager.getApplication().assertIsDispatchThread();
    boolean dirty = persistence.isDirty();
    NotebookModel.Snapshot local = dirty && model != null ? model.snapshot() : null;
    NotebookModel.Snapshot base = baseline;
    persistence.suspend(); reloading = true;
    String text = document.getText(); long generation = ++reloadGeneration;
    long stamp = document.getModificationStamp();
    Runnable pause = () -> {
      if (disposed || generation != reloadGeneration) return;
      conflicted = false; keepNotebook.setVisible(false); useText.setVisible(false);
      conflictText = null; conflictMerged = null; conflictProblem = null;
      queue.clear(); if (session != null) { ++kernelGeneration; session.close(); session = null; }
      executing.clear(); displays.clear(); busy = false; restarting = false;
      cells.forEach(cell -> ((com.intellij.openapi.editor.ex.EditorEx)cell.editor).setViewer(true));
      status.setText("Preparing notebook changes from the text document…");
    };
    if (ApplicationManager.getApplication().isDispatchThread()) pause.run();
    else ApplicationManager.getApplication().invokeLater(pause);
    AppExecutorUtil.getAppExecutorService().execute(() -> {
      NotebookModel incoming = null, merged = null; String failure = null; List<String> conflicts = List.of();
      try {
        incoming = NotebookModel.parse(text);
        if (dirty && local != null && base != null) {
          NotebookMerge.Result result = NotebookMerge.merge(base.tree(), local.tree(), incoming.snapshot().tree());
          merged = NotebookModel.fromTree(result.merged()); conflicts = result.conflicts();
        } else merged = incoming;
      } catch (RuntimeException error) { failure = error.getMessage(); }
      NotebookModel received = incoming, replacement = merged; String message = failure; List<String> overlaps = conflicts;
      ApplicationManager.getApplication().invokeLater(() -> {
        if (disposed || generation != reloadGeneration || document.getModificationStamp() != stamp) return;
        if (dirty && (message != null || !overlaps.isEmpty())) {
          conflicted = true; conflictText = received; conflictMerged = replacement; conflictProblem = message;
          keepNotebook.setVisible(true); useText.setVisible(true);
          status.setText(message != null ? "Text changes cannot be merged: " + message
              : "Notebook and text both changed " + String.join(", ", overlaps.stream().limit(3).toList()) + ". Choose which values to keep.");
          return; // Local edits remain dirty and available until explicit resolution.
        }
        conflicted = false; keepNotebook.setVisible(false); useText.setVisible(false);
        reloading = false; model = replacement; baseline = received == null ? null : received.snapshot();
        if (replacement == null) { persistence.invalidate(); showProblem(message); }
        else { rebuild(); if (dirty) sync(); else persistence.invalidate(); }
      });
    });
  }

  private void resolveConflict(boolean keepLocal) {
    if (!conflicted) return;
    conflicted = false; reloading = false; keepNotebook.setVisible(false); useText.setVisible(false);
    if (keepLocal) {
      if (conflictMerged != null) model = conflictMerged;
      if (conflictText != null) baseline = conflictText.snapshot();
      rebuild(); sync();
    } else {
      persistence.invalidate(); model = conflictText; baseline = model == null ? null : model.snapshot();
      if (model == null) showProblem(conflictProblem); else rebuild();
      status.setText("Notebook edits discarded; using the text document");
    }
    conflictText = null; conflictMerged = null; conflictProblem = null;
  }

  private static void button(JPanel panel, String text, Runnable action) {
    JButton button = new JButton(text); button.addActionListener(event -> action.run()); panel.add(button);
  }
  private void showProblem(String problem) {
    releaseCells(); body.removeAll();
    JTextArea text = new JTextArea("Cannot open this notebook: " + problem + "\nUse the JSON editor tab to inspect or repair it.");
    text.setEditable(false); text.setLineWrap(true); text.setWrapStyleWord(true); body.add(text);
    body.revalidate(); body.repaint();
  }
  private void rebuild() {
    displays.clear(); releaseCells(); body.removeAll();
    for (int i = 0; i < model.size(); i++) { Cell cell = new Cell(i); cells.add(cell); body.add(cell.panel); }
    body.revalidate(); body.repaint();
  }
  private void releaseCells() {
    for (Cell cell : cells) { Disposer.dispose(cell.lifetime); EditorFactory.getInstance().releaseEditor(cell.editor); }
    cells.clear();
  }
  private Sdk selectedSdk() {
    Module module = ModuleUtilCore.findModuleForFile(file, project);
    Sdk sdk = module == null ? null : PythonSdkUtil.findPythonSdk(module);
    if (sdk == null) sdk = ProjectRootManager.getInstance(project).getProjectSdk();
    return sdk != null && PythonSdkUtil.isPythonSdk(sdk) && !PythonSdkUtil.isRemote(sdk) ? sdk : null;
  }
  private String refreshInterpreter() {
    Sdk sdk = selectedSdk(); String path = sdk == null ? null : sdk.getHomePath();
    interpreter.setText(path == null ? "Interpreter: configure a local Python interpreter in Project Settings" : "Interpreter: " + path);
    interpreter.setToolTipText("Uses this notebook's module Python SDK, then the project Python SDK. Kernel dependencies must be installed in this interpreter.");
    return path;
  }
  private boolean canExecute() {
    if (model == null || disposed || reloading) return false;
    if (!TrustedProjects.isTrusted(project)) { status.setText("Trust this project before executing notebook code"); return false; }
    String python = refreshInterpreter();
    if (python == null) { status.setText("Select a local project Python interpreter before executing cells"); return false; }
    if (session != null && !python.equals(sessionPython)) {
      queue.clear(); ++kernelGeneration; session.close(); session = null; executing.clear(); displays.clear(); busy = false; restarting = false;
    }
    if (session == null) {
      sessionPython = python;
      String cwd = file.getParent() == null ? project.getBasePath() : file.getParent().getPath();
      if (cwd == null) { status.setText("Notebook needs a local working directory"); return false; }
      long generation = ++kernelGeneration;
      NotebookKernelSession created = new NotebookKernelSession(python, cwd, event ->
          ApplicationManager.getApplication().invokeLater(() -> { if (!disposed && generation == kernelGeneration) handle(event); }));
      session = created;
    }
    return true;
  }
  private void execute(Cell cell) {
    if (busy) { status.setText("Kernel busy — interrupt it or wait for this cell to finish"); return; }
    if (!canExecute()) return;
    int index = cells.indexOf(cell); if (index < 0) return;
    clearCellOutputs(cell, index); model.executionCount(index, null); cell.refreshOutput(); sync();
    String id = UUID.randomUUID().toString(); executing.put(id, cell); busy = true;
    cell.label.setText("Python [*]"); status.setText("Kernel running");
    session.request(id, "execute", cell.editor.getDocument().getText());
  }
  private void next() { if (!busy && !queue.isEmpty()) execute(queue.removeFirst()); }
  private void restart() {
    if (!canExecute()) return;
    if (restarting) return;
    busy = true; restarting = true; status.setText("Restarting kernel…");
    session.request("restart-" + UUID.randomUUID(), "restart", null);
  }
  private void handle(JsonObject event) {
    if (reloading) return;
    String kind = NotebookKernelSession.string(event, "event");
    String id = NotebookKernelSession.string(event, "id");
    if (kind.equals("ready")) { status.setText("Kernel ready — " + NotebookKernelSession.string(event, "python")); return; }
    if (kind.equals("diagnostic")) { status.setToolTipText(NotebookKernelSession.string(event, "text")); return; }
    if (kind.equals("session_error")) {
      queue.clear(); executing.clear(); displays.clear(); busy = false; restarting = false; status.setText(NotebookKernelSession.string(event, "message"));
      if (session != null) { ++kernelGeneration; session.close(); session = null; }
      return;
    }
    JsonObject content = event.has("content") && event.get("content").isJsonObject() ? event.getAsJsonObject("content") : new JsonObject();
    Cell cell = executing.get(id); int index = cells.indexOf(cell);
    if (index >= 0) {
      switch (kind) {
        case "stream", "display_data", "execute_result", "error" -> {
          if (cell.clearBeforeOutput) clearCellOutputs(cell, index);
          JsonObject captured = model.output(index, kind, content);
          if (content.has("transient") && content.get("transient").isJsonObject()) {
            String displayId = NotebookKernelSession.string(content.getAsJsonObject("transient"), "display_id");
            if (!displayId.isEmpty()) displays.computeIfAbsent(displayId, key -> new ArrayList<>()).add(new DisplayReference(cell, captured));
          }
          cell.refreshOutput(); sync();
        }
        case "update_display_data" -> {
          if (cell.clearBeforeOutput) clearCellOutputs(cell, index);
          if (content.has("transient") && content.get("transient").isJsonObject()) {
            String displayId = NotebookKernelSession.string(content.getAsJsonObject("transient"), "display_id");
            for (DisplayReference reference : displays.getOrDefault(displayId, List.of())) {
              if (content.has("data")) reference.output().add("data", content.get("data").deepCopy());
              if (content.has("metadata")) reference.output().add("metadata", content.get("metadata").deepCopy());
              reference.cell().refreshOutput();
            }
            sync();
          }
        }
        case "clear_output" -> {
          if (content.has("wait") && content.get("wait").getAsBoolean()) cell.clearBeforeOutput = true;
          else { clearCellOutputs(cell, index); cell.refreshOutput(); sync(); }
        }
        case "execute_input" -> { model.executionCount(index, content.get("execution_count")); sync(); }
        case "output_limit" -> {
          if (cell.clearBeforeOutput) clearCellOutputs(cell, index);
          JsonObject notice = new JsonObject(); notice.addProperty("name", "stderr");
          notice.addProperty("text", "\n[" + NotebookKernelSession.string(content, "text") + "]\n");
          model.output(index, "stream", notice); cell.refreshOutput(); sync();
        }
        default -> { }
      }
    }
    if (kind.equals("done")) {
      if (cell != null) {
        if (event.has("execution_count")) model.executionCount(index, event.get("execution_count"));
        cell.refreshLabel(); executing.remove(id); sync(); busy = restarting;
        status.setText("Kernel " + NotebookKernelSession.string(event, "status"));
        next();
      } else if (id.startsWith("restart-")) {
        executing.clear(); displays.clear(); busy = false; restarting = false; status.setText("ok".equals(NotebookKernelSession.string(event, "status"))
            ? "Kernel restarted — variables cleared" : "Kernel restart failed: " + NotebookKernelSession.string(event, "message"));
      } else if (id.isEmpty() && "error".equals(NotebookKernelSession.string(event, "status"))) {
        busy = false; restarting = false; queue.clear(); status.setText("Install jupyter_client==8.6.3 and ipykernel==6.29.5 in the selected interpreter, then restart the kernel");
      }
    }
  }
  private void clearCellOutputs(Cell cell, int index) {
    model.cell(index).add("outputs", new JsonArray()); cell.clearBeforeOutput = false;
    displays.values().forEach(references -> references.removeIf(reference -> reference.cell() == cell));
    displays.values().removeIf(List::isEmpty);
  }
  private void add(String kind) {
    if (model == null || busy || reloading || document == null || !document.isWritable()) return;
    try { model.add(kind); sync(); rebuild(); } catch (RuntimeException error) { status.setText(error.getMessage()); }
  }
  private void sync() {
    if (reloading) return;
    if (document == null || !document.isWritable()) { status.setText("Notebook is read-only"); return; }
    ++reloadGeneration; // Any queued external parse predates this newer model edit.
    expectedDocumentStamp = document.getModificationStamp();
    persistenceFailed = false;
    persistence.markDirty();
    changes.firePropertyChange(FileEditor.getPropModified(), false, true);
    try { persistence.submit(model.snapshot()); }
    catch (RuntimeException error) { persistenceFailed = true; status.setText("Notebook edits are still unsaved: " + error.getMessage()); }
  }
  private void applyPersistence(NotebookPersistence.Result result) {
    if (!persistence.isCurrent(result.generation())) return;
    if (document.getModificationStamp() != expectedDocumentStamp) {
      // Preserve pending edits until an external version can be merged or resolved.
      persistence.suspend();
      if (!disposed) reloadFromDocument();
      return;
    }
    if (result.failure() != null) {
      persistenceFailed = true;
      status.setText("Notebook edits are still unsaved: " + result.failure().getMessage());
      return; // Keep dirty and retain the model; project-close guard remains active.
    }
    try {
      writing = true; ++reloadGeneration;
      WriteCommandAction.runWriteCommandAction(project, "Edit Notebook", null, () -> document.setText(result.text()));
      expectedDocumentStamp = document.getModificationStamp();
      baseline = model.snapshot();
      persistence.applied(result.generation());
      changes.firePropertyChange(FileEditor.getPropModified(), true, isModified());
      if (result.text().length() > NotebookModel.MAX_CHARS && !disposed)
        status.setText("Notebook saved as JSON beyond the native size limit; use the text editor after reopening");
      if (saveRequested || disposed) { saveRequested = false; saveDocument(); }
      if (disposed) NotebookProjectCloseHandler.unregister(this);
    } catch (RuntimeException error) { persistenceFailed = true; status.setText("Notebook edits are still unsaved: " + error.getMessage()); }
    finally { writing = false; }
  }
  private void save() {
    if (document == null) return;
    if (persistence.isDirty()) {
      saveRequested = true;
      if (persistenceFailed && !reloading) sync();
      return;
    }
    saveDocument();
  }
  private void saveDocument() {
    NotebookDocumentSave.request(document, message -> { if (!disposed) status.setText("Save failed: " + message); });
  }

  private final class Cell {
    final String kind;
    final JPanel panel = new JPanel(new BorderLayout());
    final Editor editor;
    final JLabel label = new JBLabel();
    final JTextArea output = new JTextArea();
    final JBScrollPane outputScroll = new JBScrollPane(output);
    final Disposable lifetime = Disposer.newDisposable("OpenPyCharm notebook cell");
    boolean clearBeforeOutput;
    Cell(int index) {
      kind = model.kind(index);
      FileType type = kind.equals("code") ? PythonFileType.INSTANCE : FileTypeManager.getInstance().getFileTypeByExtension(kind.equals("markdown") ? "md" : "txt");
      PsiFile psi = PsiFileFactory.getInstance(project).createFileFromText("notebook-cell-" + index + (kind.equals("code") ? ".py" : ".md"), type, model.source(index));
      Document source = PsiDocumentManager.getInstance(project).getDocument(psi);
      if (source == null) source = EditorFactory.getInstance().createDocument(model.source(index));
      editor = EditorFactory.getInstance().createEditor(source, project, type, false);
      if (document == null || !document.isWritable()) ((com.intellij.openapi.editor.ex.EditorEx)editor).setViewer(true);
      editor.getSettings().setLineNumbersShown(kind.equals("code"));
      editor.getSettings().setFoldingOutlineShown(false); editor.getSettings().setUseSoftWraps(true);
      editor.getComponent().setPreferredSize(new Dimension(800, Math.max(82, Math.min(360, 26 * (source.getLineCount() + 1)))));
      editor.getDocument().addDocumentListener(new DocumentListener() {
        @Override public void documentChanged(DocumentEvent event) {
          int current = cells.indexOf(Cell.this); if (current < 0 || disposed || reloading) return;
          model.source(current, event.getDocument().getText()); sync();
        }
      }, lifetime);
      JPanel header = new JPanel(new FlowLayout(FlowLayout.LEFT, 6, 2)); header.add(label);
      if (kind.equals("code")) button(header, "Run Cell", () -> execute(this));
      button(header, "Delete Cell", () -> {
        int current = cells.indexOf(this); if (current < 0 || busy || reloading || document == null || !document.isWritable()) return;
        model.remove(current); sync(); rebuild();
      });
      panel.setBorder(BorderFactory.createCompoundBorder(BorderFactory.createEmptyBorder(5, 9, 9, 9), BorderFactory.createLineBorder(UIManager.getColor("Component.borderColor") == null ? Color.GRAY : UIManager.getColor("Component.borderColor"))));
      panel.add(header, BorderLayout.NORTH); panel.add(editor.getComponent(), BorderLayout.CENTER);
      output.setEditable(false); output.setLineWrap(true); output.setWrapStyleWord(true);
      output.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 12)); output.setBorder(BorderFactory.createEmptyBorder(5, 8, 5, 8));
      panel.add(outputScroll, BorderLayout.SOUTH); panel.setMaximumSize(new Dimension(Integer.MAX_VALUE, 900));
      // cells list is populated immediately after this constructor.
      renderOutput(index); renderLabel(index);
      editor.getContentComponent().getInputMap().put(KeyStroke.getKeyStroke(KeyEvent.VK_ENTER, InputEvent.SHIFT_DOWN_MASK), "notebook-run-cell");
      editor.getContentComponent().getActionMap().put("notebook-run-cell", new AbstractAction() {
        @Override public void actionPerformed(ActionEvent event) { if (kind.equals("code")) execute(Cell.this); }
      });
    }
    void refreshLabel() { int i = cells.indexOf(this); if (i >= 0) renderLabel(i); }
    void renderLabel(int i) {
      JsonElement count = model.cell(i).get("execution_count");
      label.setText(kind.equals("code") ? "Python [" + (count == null || count.isJsonNull() ? " " : count.getAsString()) + "]" : kind.equals("markdown") ? "Markdown" : "Raw");
    }
    void refreshOutput() { int i = cells.indexOf(this); if (i >= 0) renderOutput(i); }
    void renderOutput(int i) {
      if (!kind.equals("code")) { outputScroll.setVisible(false); return; }
      StringBuilder text = new StringBuilder();
      for (JsonElement item : model.outputs(i)) {
        JsonObject value = item.getAsJsonObject(); String type = NotebookKernelSession.string(value, "output_type");
        if (type.equals("stream")) text.append(NotebookModel.sourceText(value.get("text")));
        else if (type.equals("error")) {
          if (value.has("traceback")) for (JsonElement line : value.getAsJsonArray("traceback")) text.append(line.getAsString().replaceAll("\u001B\\[[;\\d]*m", "")).append('\n');
          else text.append(NotebookKernelSession.string(value, "ename")).append(": ").append(NotebookKernelSession.string(value, "evalue")).append('\n');
        } else if (value.has("data") && value.get("data").isJsonObject()) {
          JsonObject data = value.getAsJsonObject("data");
          if (data.has("text/plain")) text.append(NotebookModel.sourceText(data.get("text/plain"))).append('\n');
          else text.append("[Rich output preserved in notebook; native text renderer supports text/plain]\n");
        }
        if (text.length() > 200000) { text.setLength(200000); text.append("\n[Output display truncated; full captured output is saved in notebook]\n"); break; }
      }
      output.setText(text.toString()); outputScroll.setVisible(!text.isEmpty());
      outputScroll.setPreferredSize(new Dimension(800, Math.min(320, Math.max(42, 20 * (output.getLineCount() + 1)))));
      panel.revalidate();
    }
  }
  @Override public JComponent getComponent() { return component; }
  @Override public JComponent getPreferredFocusedComponent() { return cells.isEmpty() ? component : cells.getFirst().editor.getContentComponent(); }
  @Override public String getName() { return "Notebook"; }
  @Override public void setState(FileEditorState state) { }
  @Override public boolean isModified() { return persistence.isDirty() || document != null && FileDocumentManager.getInstance().isDocumentUnsaved(document); }
  @Override public boolean isValid() { return !disposed && file.isValid(); }
  @Override public VirtualFile getFile() { return file; }
  @Override public void addPropertyChangeListener(PropertyChangeListener listener) { changes.addPropertyChangeListener(listener); }
  @Override public void removePropertyChangeListener(PropertyChangeListener listener) { changes.removePropertyChangeListener(listener); }
  boolean ownsProject(Project value) { return project == value; }
  boolean hasPendingEdits() { return persistence.isDirty(); }
  boolean canRestorePending() { return disposed && persistence.isDirty(); }
  PendingState detachPending() {
    PendingState state = new PendingState(baseline, model.snapshot()); persistence.invalidate(); return state;
  }
  void pendingCloseNotice() {
    status.setText("Notebook edits are still preparing or need conflict resolution");
    if (disposed) ApplicationManager.getApplication().invokeLater(() -> {
      if (!project.isDisposed() && persistence.isDirty()) FileEditorManager.getInstance(project).openFile(file, true);
    });
  }
  @Override public void dispose() {
    disposed = true; queue.clear(); if (session != null) session.close(); releaseCells();
    if (!persistence.isDirty()) NotebookProjectCloseHandler.unregister(this);
    // A pending immutable snapshot still reaches the ordinary document after tab close.
  }
}
