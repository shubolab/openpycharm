package dev.openpycharm.notebooks;

import com.google.gson.*;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.List;
import java.util.concurrent.*;
import javax.swing.*;

/** Actual Matplotlib/Pillow/pandas/IPython producers through the packaged bridge and renderer. */
public final class NotebookRichKernelTest {
  private static final String CODE = """
      import os, io, sys
      from pathlib import Path
      os.environ['MPLCONFIGDIR'] = str(Path.cwd() / '.matplotlib')
      os.environ['XDG_CACHE_HOME'] = str(Path.cwd() / '.cache')
      import matplotlib
      matplotlib.use('Agg', force=True)
      import matplotlib.pyplot as plt
      import pandas as pd
      from PIL import Image as PillowImage
      from IPython.display import display, update_display, Image, HTML, Markdown
      def chart(values):
          figure, axes = plt.subplots(figsize=(4, 3), dpi=100)
          axes.plot([1, 2, 3], values, marker='o')
          axes.set_title('Actual kernel chart')
          data = io.BytesIO()
          figure.savefig(data, format='png')
          plt.close(figure)
          return Image(data=data.getvalue(), format='png')
      display(chart([1, 4, 2]), display_id='chart', metadata={'image/png': {'width': 360}, 'foreign': {'phase': 1, 'large': 9007199254740993}})
      update_display(chart([3, 1, 5]), display_id='chart', metadata={'image/png': {'width': 360}, 'foreign': {'phase': 2, 'large': 9007199254740993}})
      frame = pd.DataFrame({'city': ['Beijing', 'Shanghai'], 'score': [42, 88]})
      display(frame, display_id='frame', metadata={'foreign': {'phase': 1}})
      frame.loc[0, 'score'] = 99
      update_display(frame, display_id='frame', metadata={'foreign': {'phase': 2}})
      image = PillowImage.new('RGB', (48, 32), '#2166ac')
      jpeg = io.BytesIO()
      image.save(jpeg, format='JPEG')
      display(Image(data=jpeg.getvalue(), format='jpeg'), metadata={'image/jpeg': {'width': 48}, 'foreignJPEG': True})
      display(Markdown('# Kernel Markdown\\n\\n**strong** and `code`\\n\\n| A | B |\\n|---|---|\\n| one | two |'))
      display({'text/plain': 'Unknown MIME kept', 'application/x-openpycharm-evidence+json': {'large': 9007199254740993}}, raw=True, metadata={'foreign': ['keep', 17]})
      print('actual-rich-kernel-complete', sys.version.split()[0], pd.__version__, matplotlib.__version__)
      """;
  private static void require(boolean condition, String message) { if (!condition) throw new AssertionError(message); }
  private static NotebookRichOutput.Plan render(JsonObject output) { return NotebookRichOutputTest.prepare(output); }
  private static String displayId(JsonObject content) {
    return content.has("transient") ? NotebookKernelSession.string(content.getAsJsonObject("transient"), "display_id") : "";
  }
  public static void main(String[] args) throws Exception {
    BlockingQueue<JsonObject> events = new LinkedBlockingQueue<>();
    NotebookKernelSession session = new NotebookKernelSession(args[0], args[1], events::add);
    ProcessHandle owned = null;
    int exit = 0;
    try {
      NotebookModel model = NotebookModel.parse("{\"nbformat\":4,\"nbformat_minor\":5,\"metadata\":{\"foreign\":{\"large\":9007199254740993}},\"cells\":[]}");
      int code = model.add("code"); model.source(code, CODE);
      model.cell(code).getAsJsonObject("metadata").addProperty("trusted", false);
      NotebookDisplayState<Integer> displays = new NotebookDisplayState<>();
      Map<String, JsonObject> live = new HashMap<>();
      String initialChart = null, updatedChart = null;
      boolean initialTable = false, updatedTable = false, jpeg = false, markdown = false, completed = false;
      session.request("rich", "execute", CODE);
      long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(90);
      while (!completed && System.nanoTime() < deadline) {
        JsonObject event = events.poll(1, TimeUnit.SECONDS); if (event == null) continue;
        String kind = NotebookKernelSession.string(event, "event");
        if (kind.equals("ready")) {
          require(args[0].equals(NotebookKernelSession.string(event, "python")), "Rich kernel used a different Python");
          owned = ProcessHandle.of(event.get("kernel_pid").getAsLong()).orElseThrow();
        }
        if (kind.equals("session_error")) throw new IllegalStateException(event.toString());
        if (!NotebookKernelSession.string(event, "id").equals("rich")) continue;
        JsonObject content = event.has("content") ? event.getAsJsonObject("content") : new JsonObject();
        if (Set.of("stream", "display_data", "execute_result", "error").contains(kind)) {
          JsonObject stored = model.output(code, kind, content); displays.capture(code, stored, content);
          String id = displayId(content); if (!id.isEmpty()) live.put(id, stored);
          if (kind.equals("error")) throw new IllegalStateException("Actual Python rich workflow failed: " + content);
          if (kind.equals("display_data")) try (var plan = render(stored)) {
            if (id.equals("chart")) { require(NotebookRichOutputTest.images(plan).size() == 1, "Actual kernel PNG did not decode"); initialChart = stored.getAsJsonObject("data").get("image/png").getAsString(); }
            if (id.equals("frame")) initialTable = NotebookRichOutputTest.tables(plan).stream().anyMatch(table -> table.rows().stream().anyMatch(row -> row.contains("42")));
            if (stored.getAsJsonObject("data").has("image/jpeg")) jpeg = NotebookRichOutputTest.images(plan).stream().anyMatch(image -> image.mime().equals("image/jpeg") && image.sourceWidth() == 48);
            if (stored.getAsJsonObject("data").has("text/markdown")) markdown = NotebookRichOutputTest.text(plan).contains("Kernel Markdown") && !NotebookRichOutputTest.tables(plan).isEmpty();
          }
        } else if (kind.equals("update_display_data")) {
          require(displays.update(content).contains(code), "Production display state did not update an existing output");
          String id = displayId(content); JsonObject changed = live.get(id);
          try (var plan = render(changed)) {
            if (id.equals("chart")) { updatedChart = changed.getAsJsonObject("data").get("image/png").getAsString(); require(NotebookRichOutputTest.images(plan).size() == 1, "Updated PNG did not decode"); }
            if (id.equals("frame")) updatedTable = NotebookRichOutputTest.tables(plan).stream().anyMatch(table -> table.rows().stream().anyMatch(row -> row.contains("99")));
          }
        } else if (kind.equals("execute_input")) model.executionCount(code, content.get("execution_count"));
        else if (kind.equals("done")) { require(NotebookKernelSession.string(event, "status").equals("ok"), "Rich execution returned error"); completed = true; }
      }
      require(completed && initialTable && updatedTable && jpeg && markdown, "Actual rich producer controls incomplete");
      require(initialChart != null && updatedChart != null && !initialChart.equals(updatedChart), "Real display_id update did not replace chart bytes");
      require(live.get("chart").getAsJsonObject("metadata").getAsJsonObject("foreign").get("large").getAsString().equals("9007199254740993"), "Unknown large metadata changed");
      String capturedNotebook = model.json();
      Path notebook = Path.of(args[2]); Files.createDirectories(notebook.getParent()); Files.writeString(notebook, capturedNotebook);
      NotebookModel reopened = NotebookModel.parse(Files.readString(notebook));
      require(capturedNotebook.equals(reopened.json()), "Complete captured nbformat tree changed during save/reopen");
      require(reopened.snapshot().tree().getAsJsonObject("metadata").getAsJsonObject("foreign").get("large").getAsString().equals("9007199254740993"), "Notebook metadata lost on save/reopen");
      require(!reopened.cell(0).getAsJsonObject("metadata").get("trusted").getAsBoolean(), "Viewer changed notebook trust metadata");
      boolean unknown = false, savedUpdatedPng = false;
      for (JsonElement value : reopened.outputs(0)) {
        JsonObject output = value.getAsJsonObject(); require(!output.has("transient"), "Session display IDs leaked into saved nbformat");
        if (output.has("data") && output.getAsJsonObject("data").has("application/x-openpycharm-evidence+json"))
          unknown = output.getAsJsonObject("data").getAsJsonObject("application/x-openpycharm-evidence+json").get("large").getAsString().equals("9007199254740993");
        if (output.has("data") && output.getAsJsonObject("data").has("image/png"))
          savedUpdatedPng |= output.getAsJsonObject("data").get("image/png").getAsString().equals(updatedChart);
      }
      require(unknown && savedUpdatedPng, "Unknown MIME or updated PNG bytes disappeared on save/reopen");
      List<JsonObject> outputs = new ArrayList<>(); reopened.outputs(0).forEach(value -> outputs.add(value.getAsJsonObject()));
      try (var plan = NotebookRichOutput.prepare(new NotebookRichOutput.Input(outputs, null, true), 4_000_000, new NotebookRichOutput.Cancellation())) {
        require(NotebookRichOutputTest.images(plan).size() == 2 && NotebookRichOutputTest.tables(plan).size() >= 2, "Reopened rich outputs do not prepare native images/tables");
        require(NotebookRichOutputTest.tables(plan).stream().anyMatch(table -> table.rows().stream().anyMatch(row -> row.contains("99"))), "Updated DataFrame value did not survive save/reopen");
        SwingUtilities.invokeAndWait(() -> {
          NotebookOutputPanel panel = new NotebookOutputPanel(); panel.apply(plan.retain());
          List<Component> components = new ArrayList<>(); NotebookRichOutputTest.walk(panel, components);
          require(components.stream().filter(value -> value instanceof JTable).count() >= 2, "Actual reopened MIME did not create native Swing table controls");
          boolean updatedNativeCell = false;
          for (Component component : components) if (component instanceof JTable table)
            for (int row = 0; row < table.getRowCount(); row++) for (int column = 0; column < table.getColumnCount(); column++)
              updatedNativeCell |= table.getValueAt(row, column).equals("99");
          require(updatedNativeCell, "Native reopened table did not contain the actual display update");
          require(components.stream().filter(value -> value instanceof JTextPane).count() >= 1, "Actual reopened MIME did not create native styled text");
          long painted = 0;
          for (Component component : components) if (component instanceof JComponent image && image.getToolTipText() != null && image.getToolTipText().startsWith("image/")) {
            Dimension size = image.getPreferredSize(); image.setSize(size);
            BufferedImage pixels = new BufferedImage(size.width, size.height, BufferedImage.TYPE_INT_ARGB); Graphics2D graphics = pixels.createGraphics(); image.printAll(graphics); graphics.dispose();
            for (int y = 0; y < pixels.getHeight(); y += 10) for (int x = 0; x < pixels.getWidth(); x += 10) if ((pixels.getRGB(x, y) >>> 24) != 0) painted++;
            pixels.flush();
          }
          require(painted > 100, "Actual image components did not paint decoded kernel image pixels"); panel.close();
        });
      }
      session.close(); long end = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
      while (owned != null && owned.isAlive() && System.nanoTime() < end) Thread.sleep(25);
      require(owned != null && !owned.isAlive(), "Owned rich kernel survived session disposal");
      String digest = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(notebook)));
      System.out.println("{\"status\":\"pass\",\"actualMatplotlibPng\":true,\"actualPillowJpeg\":true,\"actualPandasHtmlTable\":true,\"actualKernelMarkdown\":true,\"displayIdPngAndTableUpdate\":true,\"nbformatSaveReopen\":true,\"completeCapturedTreeRoundTrip\":true,\"unknownMimeMetadataAndTrustPreserved\":true,\"nativeSwingImagesTablesText\":true,\"ownedKernelStopped\":true,\"notebookSha256\":\"" + digest + "\",\"nativeIdeLaunched\":false}");
    } catch (Throwable error) { error.printStackTrace(); exit = 1; }
    finally {
      session.close(); long end = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
      while (owned != null && owned.isAlive() && System.nanoTime() < end) Thread.sleep(25);
    }
    System.exit(exit);
  }
}
