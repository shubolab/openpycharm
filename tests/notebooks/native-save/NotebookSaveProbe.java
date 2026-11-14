package dev.openpycharm.notebooks.saveprobe;

import com.google.gson.*;
import com.intellij.ide.impl.TrustedProjects;
import com.intellij.ide.plugins.PluginManagerCore;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.actionSystem.*;
import com.intellij.openapi.editor.ex.DocumentEx;
import com.intellij.openapi.application.PathManager;
import com.intellij.openapi.command.WriteCommandAction;
import com.intellij.openapi.command.undo.UndoManager;
import com.intellij.openapi.editor.*;
import com.intellij.openapi.extensions.PluginId;
import com.intellij.openapi.fileEditor.*;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.startup.StartupActivity;
import com.intellij.openapi.vfs.LocalFileSystem;
import com.intellij.openapi.vfs.VirtualFile;
import com.intellij.util.concurrency.AppExecutorUtil;
import dev.openpycharm.notebooks.NotebookFileEditor;
import dev.openpycharm.notebooks.NotebookModel;
import dev.openpycharm.notebooks.NotebookPersistence;
import java.awt.*;
import java.lang.management.ManagementFactory;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.function.BooleanSupplier;
import javax.swing.*;

/** Test-only actual-platform gate. Edits/saves only the explicitly owned fixture; no Python execution. */
public final class NotebookSaveProbe implements StartupActivity.DumbAware {
  private static final AtomicBoolean REQUESTED = new AtomicBoolean();
  private static final String INTERIM = "print('合并中的 Notebook 编辑')\nvalue = 2\n";
  private static final String TARGET = "print('真实原生保存 中文')\nvalue = 3\n";
  private final AtomicInteger heartbeat = new AtomicInteger();
  private final AtomicLong lastHeartbeat = new AtomicLong();
  private final AtomicReference<String> documentText = new AtomicReference<>("");
  private final AtomicReference<String> cellText = new AtomicReference<>("");
  private final AtomicBoolean editorModified = new AtomicBoolean();
  private final AtomicLong capturesCompleted = new AtomicLong();
  private record NativeState(long captureEpoch, boolean reloading, boolean conflicted, boolean persistenceDirty,
                             boolean modified, boolean cellViewer, String status,
                             long documentStamp, long modificationSequence) { }
  private final AtomicReference<NativeState> nativeState = new AtomicReference<>();
  private final AtomicReference<String> stage = new AtomicReference<>("startup");
  private javax.swing.Timer timer;
  private volatile NotebookFileEditor editor;
  private volatile VirtualFile virtual;
  private Project project;
  private Path fixture, report, boundary;

  @Override public void runActivity(Project project) {
    String destination = System.getProperty("openpycharm.notebook.save.report");
    String root = System.getProperty("openpycharm.notebook.save.root");
    String expectedProject = System.getProperty("openpycharm.notebook.save.project");
    if (destination == null || root == null || expectedProject == null || project.getBasePath() == null
        || !Path.of(project.getBasePath()).toAbsolutePath().normalize().equals(Path.of(expectedProject).toAbsolutePath().normalize())
        || !REQUESTED.compareAndSet(false, true)) return;
    this.project = project;
    report = Path.of(destination).toAbsolutePath().normalize(); boundary = Path.of(root).toAbsolutePath().normalize();
    fixture = Path.of(System.getProperty("openpycharm.notebook.save.file")).toAbsolutePath().normalize();
    if (!report.startsWith(boundary) || !fixture.startsWith(boundary.resolve("project"))) return;
    AppExecutorUtil.getAppExecutorService().execute(this::run);
  }
  private void run() {
    Map<String, Object> result = new LinkedHashMap<>();
    result.put("invocationId", System.getProperty("openpycharm.notebook.save.invocation"));
    result.put("kernelCodeExecuted", false); result.put("ownedFixtureOnly", true); result.put("projectTrustBypassed", false);
    result.put("expectedEditedCellSource", TARGET); result.put("nativeButtonDoClick", true);
    result.put("capturedAt", Instant.now().toString()); result.put("ownedPid", ProcessHandle.current().pid());
    try {
      require(fixture.toRealPath().startsWith(boundary.toRealPath()), "Fixture path escaped the owned boundary");
      result.put("projectTrusted", TrustedProjects.isTrusted(project));
      result.put("applicationHome", PathManager.getHomePath()); result.put("plugin", observePlugin());
      String initial = Files.readString(fixture); String initialHash = hash(Files.readAllBytes(fixture));
      String initialSource = NotebookModel.parse(initial).source(0);
      JsonObject expectedInitial = JsonParser.parseString(initial).getAsJsonObject();
      JsonObject external = JsonParser.parseString(initial).getAsJsonObject(); external.getAsJsonObject("metadata").addProperty("externalTextEdit", "kept");
      String externalText = new Gson().toJson(external) + "\n";
      virtual = LocalFileSystem.getInstance().refreshAndFindFileByPath(fixture.toString());
      require(virtual != null, "Owned notebook was not found by actual VFS");
      stage.set("opening-native-notebook");
      edt(() -> {
        timer = new javax.swing.Timer(25, event -> capture()); timer.start();
        FileEditorManager.getInstance(project).openFile(virtual, true); return null;
      });
      await(() -> editor != null && !cellText.get().isEmpty(), 30, "Native NotebookFileEditor did not finish opening");
      result.put("nativeEditorClass", editor.getClass().getName());
      stage.set("source-edit-undo");
      edt(() -> {
        Editor cell = firstCell(editor);
        WriteCommandAction.runWriteCommandAction(project, "Native notebook undo control", null, () -> cell.getDocument().setText(INTERIM)); return null;
      });
      await(() -> sourceIs(documentText.get(), INTERIM) && cellText.get().equals(INTERIM), 25, "First source edit did not reach the actual file document");
      String undoTarget = edt(() -> {
        UndoManager manager = UndoManager.getInstance(project); FileEditor target = editor;
        if (!manager.isUndoAvailable(target)) target = com.intellij.openapi.fileEditor.impl.text.TextEditorProvider.getInstance().getTextEditor(firstCell(editor));
        require(manager.isUndoAvailable(target), "No native undo available for notebook/cell editor");
        String type = target.getClass().getName(); manager.undo(target); return type;
      });
      await(() -> sourceIs(documentText.get(), initialSource) && cellText.get().equals(initialSource), 30, "Native source undo/reload did not restore both source and file document");
      result.put("nativeUndoRestored", true); result.put("undoTarget", undoTarget);
      result.put("stateAfterUndo", nativeState.get());
      stage.set("cell-edit-and-text-merge");
      edt(() -> {
        Editor cell = firstCell(editor);
        Document json = FileDocumentManager.getInstance().getCachedDocument(virtual);
        require(json != null, "No actual file document for notebook");
        WriteCommandAction.runWriteCommandAction(project, "Native notebook pending edit control", null, () -> cell.getDocument().setText(INTERIM));
        // Same EDT turn: source edit is still pending when the text document's
        // independent metadata changes. This exercises the real reload path.
        WriteCommandAction.runWriteCommandAction(project, "Native notebook text merge control", null, () -> json.setText(externalText));
        return null;
      });
      await(() -> sourceIs(documentText.get(), INTERIM) && documentText.get().contains("externalTextEdit") && cellText.get().equals(INTERIM),
          30, "Pending cell/text changes did not merge in the actual editor");
      result.put("pendingCellAndTextMerge", true);
      stage.set("native-save-request"); int before = heartbeat.get();
      edt(() -> {
        Editor cell = firstCell(editor);
        WriteCommandAction.runWriteCommandAction(project, "Native notebook Unicode edit control", null, () -> cell.getDocument().setText(TARGET));
        cellText.set(cell.getDocument().getText());
        JButton save = button(editor.getComponent(), "Save"); require(save != null, "Actual Notebook Save button missing"); save.doClick(0); return null;
      });
      await(() -> savedTarget() && heartbeat.get() - before >= 2, 35, "Native Save did not persist edits while continuing its EDT heartbeat");
      result.put("nativeSavePersisted", true); result.put("heartbeatTicksAfterSave", heartbeat.get() - before);
      require(heartbeat.get() - before >= 2, "EDT heartbeat did not continue through save");
      NotebookModel saved = NotebookModel.parse(Files.readString(fixture));
      assertPayload(saved, expectedInitial, false);
      stage.set("post-save-external-dirty-merge");
      JsonObject after = JsonParser.parseString(Files.readString(fixture)).getAsJsonObject(); after.getAsJsonObject("metadata").addProperty("externalAfterSave", "kept");
      String afterText = new Gson().toJson(after) + "\n";
      edt(() -> {
        Editor cell = firstCell(editor); Document json = FileDocumentManager.getInstance().getCachedDocument(virtual);
        WriteCommandAction.runWriteCommandAction(project, "Native notebook post-save cell control", null, () -> cell.getDocument().setText(INTERIM));
        WriteCommandAction.runWriteCommandAction(project, "Native notebook post-save text control", null, () -> json.setText(afterText)); return null;
      });
      await(() -> sourceIs(documentText.get(), INTERIM) && documentText.get().contains("externalAfterSave") && cellText.get().equals(INTERIM), 30, "External JSON/pending edit after save did not merge");
      edt(() -> {
        Editor cell = firstCell(editor); WriteCommandAction.runWriteCommandAction(project, "Native notebook final edit", null, () -> cell.getDocument().setText(TARGET));
        cellText.set(cell.getDocument().getText()); button(editor.getComponent(), "Save").doClick(0); return null;
      });
      await(() -> savedTarget() && fileHas("externalAfterSave") && !editorModified.get(), 35, "Second native save lost post-save text metadata or source, or remained dirty");
      result.put("postSaveExternalDirtyMerge", true);
      assertPayload(NotebookModel.parse(Files.readString(fixture)), expectedInitial, true);
      stage.set("platform-save-all");
      // Exercise a real parent-document reload, then the ordinary SaveAll
      // action used by Cmd+S. Status text is checked separately from flags.
      long reloadTick = edt(() -> {
        Document json = FileDocumentManager.getInstance().getCachedDocument(virtual);
        WriteCommandAction.runWriteCommandAction(project, "Native SaveAll formatting control", null,
            () -> json.setText(json.getText() + "  \n")); return capturesCompleted.get();
      });
      await(() -> nativeState.get() != null && nativeState.get().captureEpoch() > reloadTick && settled() && sourceIs(documentText.get(), TARGET), 30, "Parent-document reload did not finish before platform SaveAll");
      edt(() -> {
        Editor cell = firstCell(editor); require(!cell.isViewer(), "Reload left the cell read-only");
        WriteCommandAction.runWriteCommandAction(project, "Native SaveAll source edit", null, () -> cell.getDocument().setText(INTERIM)); return null;
      });
      await(() -> settled() && sourceIs(documentText.get(), INTERIM) && cellText.get().equals(INTERIM), 30,
          "Reloaded notebook could not prepare a new edit before SaveAll");
      result.put("stateBeforePlatformSaveAll", nativeState.get()); int beforeSaveAll = heartbeat.get();
      String saveAllClass = edt(this::platformSaveAll);
      await(() -> savedSource(INTERIM) && settled() && !editorModified.get() && heartbeat.get() - beforeSaveAll >= 2, 35,
          "Platform SaveAll did not persist source with settled editor flags and live EDT heartbeat");
      result.put("platformSaveAllActionClass", saveAllClass); result.put("platformSaveAllPersisted", true);
      result.put("stateAfterPlatformSaveAll", nativeState.get());
      require(nativeState.get().status().startsWith("Kernel stopped"), "Successful reload kept stale Preparing status");
      result.put("successfulReloadStatusRestored", true); result.put("successfulReloadStateClean", true);
      stage.set("edit-after-platform-save-all");
      edt(() -> {
        Editor cell = firstCell(editor); require(!cell.isViewer(), "SaveAll left the cell read-only");
        WriteCommandAction.runWriteCommandAction(project, "Native followup edit after SaveAll", null, () -> cell.getDocument().setText(TARGET)); return null;
      });
      await(() -> settled() && sourceIs(documentText.get(), TARGET) && cellText.get().equals(TARGET), 30,
          "Notebook could not accept and prepare another edit after platform SaveAll");
      edt(this::platformSaveAll);
      await(() -> savedTarget() && settled() && !editorModified.get(), 35, "Followup source edit did not persist through platform SaveAll");
      assertPayload(NotebookModel.parse(Files.readString(fixture)), expectedInitial, true);
      result.put("postSaveAllCanEdit", true); result.put("stateAfterFollowupSaveAll", nativeState.get());
      String savedHash = hash(Files.readAllBytes(fixture)); require(!savedHash.equals(initialHash), "Saved file bytes did not change");
      result.put("savedBytesSha256", savedHash); result.put("savedBytes", Files.size(fixture));
      result.put("metadataAndExistingOutputsPreserved", true);
      stage.set("close-and-reopen"); NotebookFileEditor previous = editor;
      edt(() -> { FileEditorManager.getInstance(project).closeFile(virtual); editor = null; cellText.set(""); FileEditorManager.getInstance(project).openFile(virtual, true); return null; });
      await(() -> editor != null && editor != previous && cellText.get().equals(TARGET), 30, "Closed notebook did not reopen with the saved source");
      require(edt(() -> !editor.isModified()), "Reopened saved editor is unexpectedly dirty");
      result.put("closeReopenSourcePreserved", true); result.put("status", "pass"); stage.set("complete");
    } catch (Throwable error) {
      result.put("status", "fail"); result.put("failure", error.toString());
      result.put("stack", Arrays.stream(error.getStackTrace()).limit(20).map(Object::toString).toList());
      try {
        StringBuilder dump = new StringBuilder();
        for (var thread : ManagementFactory.getThreadMXBean().dumpAllThreads(true, true, 50)) { dump.append(thread).append('\n'); if (dump.length() > 2_000_000) break; }
        Path threadDump = report.resolveSibling("notebook-save-native-timeout-threads.txt"); Files.writeString(threadDump, dump.toString()); result.put("threadDump", threadDump.toString());
      } catch (Exception dumpError) { result.put("threadDumpFailure", dumpError.toString()); }
    } finally {
      result.put("stage", stage.get()); result.put("heartbeatTicks", heartbeat.get());
      result.put("heartbeatAgeMillis", lastHeartbeat.get() == 0 ? -1 : TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - lastHeartbeat.get()));
      result.put("lastCapturedCellSource", cellText.get()); result.put("lastCapturedDocumentText", documentText.get());
      result.put("lastCapturedEditorModified", editorModified.get());
      result.put("lastCapturedNativeState", nativeState.get());
      try {
        Files.createDirectories(report.getParent()); Path temporary = Files.createTempFile(report.getParent(), ".notebook-save-native-", ".json");
        Files.writeString(temporary, new GsonBuilder().setPrettyPrinting().create().toJson(result));
        Files.move(temporary, report, StandardCopyOption.REPLACE_EXISTING);
      } catch (Exception ignored) { }
      ApplicationManager.getApplication().invokeLater(() -> { if (timer != null) timer.stop(); });
    }
  }
  private void capture() {
    heartbeat.incrementAndGet(); lastHeartbeat.set(System.nanoTime());
    for (FileEditor candidate : FileEditorManager.getInstance(project).getAllEditors(virtual))
      if (candidate instanceof NotebookFileEditor notebook) { editor = notebook; break; }
    try { if (editor != null) { cellText.set(firstCell(editor).getDocument().getText()); editorModified.set(editor.isModified()); } } catch (Exception ignored) { }
    Document document = FileDocumentManager.getInstance().getCachedDocument(virtual);
    if (document != null && document.getTextLength() < 200000) documentText.set(document.getText());
    try {
      if (editor != null && document != null) nativeState.set(new NativeState(capturesCompleted.incrementAndGet(),
          (boolean)field(editor, "reloading"), (boolean)field(editor, "conflicted"),
          ((NotebookPersistence)field(editor, "persistence")).isDirty(), editor.isModified(), firstCell(editor).isViewer(),
          ((JLabel)field(editor, "status")).getText(), document.getModificationStamp(), ((DocumentEx)document).getModificationSequence()));
    } catch (Exception failure) { nativeState.set(null); }
  }
  private boolean savedTarget() { return savedSource(TARGET); }
  private boolean savedSource(String source) {
    try { NotebookModel value = NotebookModel.parse(Files.readString(fixture)); return value.source(0).equals(source) && value.snapshot().json().contains("externalTextEdit"); }
    catch (Exception ignored) { return false; }
  }
  private boolean settled() {
    NativeState value = nativeState.get();
    return value != null && !value.reloading() && !value.conflicted() && !value.persistenceDirty() && !value.cellViewer();
  }
  private String platformSaveAll() {
    AnAction action = ActionManager.getInstance().getAction("SaveAll"); require(action != null, "Platform SaveAll action is absent");
    DataContext context = dataId -> CommonDataKeys.PROJECT.is(dataId) ? project : null;
    action.actionPerformed(AnActionEvent.createFromAnAction(action, null, ActionPlaces.UNKNOWN, context));
    return action.getClass().getName();
  }
  private static Object field(Object target, String name) throws Exception {
    var field = target.getClass().getDeclaredField(name); field.setAccessible(true); return field.get(target);
  }
  private boolean fileHas(String key) { try { return Files.readString(fixture).contains(key); } catch (Exception ignored) { return false; } }
  private static boolean sourceIs(String text, String expected) { try { return NotebookModel.parse(text).source(0).equals(expected); } catch (Exception ignored) { return false; } }
  private static void assertPayload(NotebookModel model, JsonObject initial, boolean afterSecondSave) {
    JsonObject actual = JsonParser.parseString(model.json()).getAsJsonObject();
    require(model.source(0).equals(TARGET), "Saved Unicode/source value changed");
    JsonObject expected = initial.deepCopy();
    // Source string/array layout is not a persistence invariant; every other
    // immutable root/cell/output/metadata field must exactly match the fixture.
    expected.getAsJsonArray("cells").get(0).getAsJsonObject().add("source", actual.getAsJsonArray("cells").get(0).getAsJsonObject().get("source"));
    expected.getAsJsonObject("metadata").addProperty("externalTextEdit", "kept");
    if (afterSecondSave) expected.getAsJsonObject("metadata").addProperty("externalAfterSave", "kept");
    require(immutableEquals(expected, actual), "Saved notebook changed immutable fixture fields/outputs or lost external metadata");
  }
  private static boolean immutableEquals(JsonElement expected, JsonElement actual) {
    if (expected == null || actual == null) return expected == actual;
    if (expected.isJsonObject() && actual.isJsonObject()) {
      JsonObject left = expected.getAsJsonObject(), right = actual.getAsJsonObject();
      if (!left.keySet().equals(right.keySet())) return false;
      for (String key : left.keySet()) if (!immutableEquals(left.get(key), right.get(key))) return false;
      return true;
    }
    if (expected.isJsonArray() && actual.isJsonArray()) {
      JsonArray left = expected.getAsJsonArray(), right = actual.getAsJsonArray();
      if (left.size() != right.size()) return false;
      for (int index = 0; index < left.size(); index++) if (!immutableEquals(left.get(index), right.get(index))) return false;
      return true;
    }
    // Literal JSON comparison never coerces large numbers to doubles. For
    // unchanged fixture values, even the original numeric spelling is retained.
    return expected.isJsonPrimitive() == actual.isJsonPrimitive()
        && expected.isJsonNull() == actual.isJsonNull() && expected.toString().equals(actual.toString());
  }
  private Map<String, Object> observePlugin() throws Exception {
    var descriptor = PluginManagerCore.getPlugin(PluginId.getId("dev.openpycharm.notebooks")); require(descriptor != null && descriptor.isEnabled(), "Actual production notebook plugin missing");
    Path jar = descriptor.getPluginPath().resolve("lib/notebooks.jar"); String digest = hash(Files.readAllBytes(jar));
    require(digest.equals(System.getProperty("openpycharm.notebook.save.expected.jar")), "Loaded notebook JAR differs from selected actual product");
    return Map.of("id", descriptor.getPluginId().getIdString(), "version", descriptor.getVersion(), "path", descriptor.getPluginPath().toString(), "jarSha256", digest);
  }
  private static Editor firstCell(NotebookFileEditor notebook) throws Exception {
    var field = NotebookFileEditor.class.getDeclaredField("cells"); field.setAccessible(true);
    List<?> cells = (List<?>)field.get(notebook); require(!cells.isEmpty(), "Native cell list not initialized");
    var nativeEditor = cells.getFirst().getClass().getDeclaredField("editor"); nativeEditor.setAccessible(true); return (Editor)nativeEditor.get(cells.getFirst());
  }
  private static JButton button(Component component, String label) {
    if (component instanceof JButton button && button.getText().equals(label)) return button;
    if (component instanceof Container parent) for (Component child : parent.getComponents()) { JButton found = button(child, label); if (found != null) return found; }
    return null;
  }
  private <T> T edt(Callable<T> call) throws Exception {
    CompletableFuture<T> result = new CompletableFuture<>();
    ApplicationManager.getApplication().invokeLater(() -> { try { result.complete(call.call()); } catch (Throwable error) { result.completeExceptionally(error); } });
    return result.get(12, TimeUnit.SECONDS);
  }
  private void await(BooleanSupplier condition, int seconds, String message) throws Exception {
    long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(seconds);
    while (System.nanoTime() < deadline) {
      if (condition.getAsBoolean()) return;
      if (lastHeartbeat.get() != 0 && System.nanoTime() - lastHeartbeat.get() > TimeUnit.SECONDS.toNanos(7)) throw new IllegalStateException(message + " (EDT heartbeat stalled)");
      Thread.sleep(50);
    }
    throw new IllegalStateException(message + " (deadline)");
  }
  private static String hash(byte[] bytes) throws Exception { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); }
  private static void require(boolean value, String message) { if (!value) throw new IllegalStateException(message); }
}
