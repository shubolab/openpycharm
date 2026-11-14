package dev.openpycharm.notebooks;

import com.google.gson.*;
import com.sun.net.httpserver.HttpServer;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.io.*;
import java.net.InetSocketAddress;
import java.util.*;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.zip.CRC32;
import javax.imageio.ImageIO;
import javax.swing.*;
import javax.swing.text.*;
import javax.swing.text.html.HTMLEditorKit;

/** Actual in-memory decode and native Swing component controls, no IDE/window/server dependency. */
public final class NotebookRichOutputTest {
  static void require(boolean condition, String message) { if (!condition) throw new AssertionError(message); }
  static String encoded(String format, int width, int height) throws Exception {
    BufferedImage image = new BufferedImage(width, height, format.equals("JPEG") ? BufferedImage.TYPE_INT_RGB : BufferedImage.TYPE_INT_ARGB);
    Graphics2D drawing = image.createGraphics();
    drawing.setColor(Color.WHITE); drawing.fillRect(0, 0, width, height);
    drawing.setColor(Color.BLUE); drawing.drawLine(0, height - 1, width - 1, 0); drawing.dispose();
    ByteArrayOutputStream bytes = new ByteArrayOutputStream();
    require(ImageIO.write(image, format, bytes), "Test image encoder missing"); image.flush();
    return Base64.getEncoder().encodeToString(bytes.toByteArray());
  }
  static JsonObject output(String mime, String value) {
    JsonObject output = new JsonObject(), data = new JsonObject();
    output.addProperty("output_type", "display_data"); data.addProperty(mime, value); output.add("data", data);
    output.add("metadata", new JsonObject()); return output;
  }
  static NotebookRichOutput.Plan prepare(JsonObject output) {
    return NotebookRichOutput.prepare(new NotebookRichOutput.Input(List.of(output), null, true), NotebookRichOutput.NOTEBOOK_PIXEL_BUDGET, new NotebookRichOutput.Cancellation());
  }
  static String text(NotebookRichOutput.Plan plan) throws Exception {
    StringBuilder text = new StringBuilder();
    for (var block : plan.blocks()) if (block instanceof NotebookRichOutput.Text value) text.append(value.document().getText(0, value.document().getLength()));
    return text.toString();
  }
  static List<NotebookRichOutput.Image> images(NotebookRichOutput.Plan plan) {
    return plan.blocks().stream().filter(value -> value instanceof NotebookRichOutput.Image).map(value -> (NotebookRichOutput.Image)value).toList();
  }
  static List<NotebookRichOutput.Table> tables(NotebookRichOutput.Plan plan) {
    return plan.blocks().stream().filter(value -> value instanceof NotebookRichOutput.Table).map(value -> (NotebookRichOutput.Table)value).toList();
  }

  private static void imagesAndLimits() throws Exception {
    JsonObject png = output("image/png", encoded("PNG", 1600, 1000));
    JsonObject metadata = new JsonObject(); metadata.addProperty("width", 480); metadata.addProperty("foreign", "keep");
    png.getAsJsonObject("metadata").add("image/png", metadata);
    String original = png.toString();
    try (var plan = prepare(png)) {
      var image = images(plan).getFirst();
      require(image.sourceWidth() == 1600 && image.sourceHeight() == 1000 && image.width() == 480, "PNG dimensions/metadata not honored");
      require(plan.pixels() <= NotebookRichOutput.MAX_IMAGE_PIXELS, "PNG was not subsampled before decode");
      require(image.image().getRGB(image.image().getWidth() / 2, image.image().getHeight() / 2) != 0, "Actual image pixels were not decoded");
    }
    require(png.toString().equals(original), "Rendering mutated image bytes or foreign metadata");
    try (var jpeg = prepare(output("image/jpeg", encoded("JPEG", 96, 64)))) {
      require(images(jpeg).getFirst().sourceWidth() == 96 && images(jpeg).getFirst().mime().equals("image/jpeg"), "Actual JPEG decode failed");
    }
    JsonObject multiline = output("image/png", "unused");
    String base64 = encoded("PNG", 40, 30); JsonArray lines = new JsonArray(); lines.add(base64.substring(0, 20)); lines.add("\n" + base64.substring(20));
    multiline.getAsJsonObject("data").add("image/png", lines);
    try (var plan = prepare(multiline)) { require(images(plan).size() == 1, "nbformat multiline image data did not decode"); }
    try (var invalid = prepare(output("image/png", "https://invalid.example/image.png"))) {
      require(images(invalid).isEmpty() && text(invalid).contains("invalid base64"), "Image URL or malformed base64 was accepted");
    }
    try (var huge = prepare(output("image/png", oversizedPng()))) {
      require(images(huge).isEmpty() && text(huge).contains("dimensions"), "Pixel bomb was not rejected before decode");
    }
    JsonObject tiny = output("image/png", encoded("PNG", 1000, 1000));
    try (var budget = NotebookRichOutput.prepare(new NotebookRichOutput.Input(Collections.nCopies(7, tiny), null, true), 2_000_000, new NotebookRichOutput.Cancellation())) {
      require(budget.pixels() <= 2_000_000 && images(budget).size() == 2 && text(budget).contains("pixel budget"), "Aggregate image budget was not enforced");
    }
    try (var untrusted = NotebookRichOutput.prepare(new NotebookRichOutput.Input(List.of(png), null, false), 4_000_000, new NotebookRichOutput.Cancellation())) {
      require(images(untrusted).isEmpty() && text(untrusted).contains("disabled"), "Untrusted project decoded rich output");
    }
    NotebookRichOutput.Cancellation cancelled = new NotebookRichOutput.Cancellation(); cancelled.cancel();
    try { NotebookRichOutput.prepare(new NotebookRichOutput.Input(List.of(png), null, true), 4_000_000, cancelled); throw new AssertionError("Cancelled preview was prepared"); }
    catch (java.util.concurrent.CancellationException expected) { }
    SwingUtilities.invokeAndWait(() -> {
      try { prepare(png); throw new AssertionError("Image decode was allowed on EDT"); }
      catch (IllegalStateException expected) { }
    });
    JsonObject stream = new JsonObject(); stream.addProperty("output_type", "stream"); stream.addProperty("text", "prefix-" + "x".repeat(300000));
    try (var plan = prepare(stream)) { require(text(plan).startsWith("prefix-") && text(plan).contains("Preview limited"), "Bounded text lost its prefix/truncation notice"); }
  }
  private static void finalReferenceReservations() throws Exception {
    var ledger = new NotebookRichOutput.PixelLedger(4_000_000);
    JsonObject png = output("image/png", encoded("PNG", 1000, 1000));
    List<NotebookRichOutput.Plan> plans = new ArrayList<>();
    for (int i = 0; i < 4; i++) plans.add(NotebookRichOutput.prepare(new NotebookRichOutput.Input(List.of(png), null, true),
        4_000_000, new NotebookRichOutput.Cancellation(), ledger));
    var viewer = plans.getFirst().retain(); plans.removeFirst().close();
    require(ledger.reservedPixels() == 4_000_000, "Cache close returned pixels still owned by its viewer");
    try (var denied = NotebookRichOutput.prepare(new NotebookRichOutput.Input(List.of(png), null, true), 4_000_000,
        new NotebookRichOutput.Cancellation(), ledger)) {
      require(images(denied).isEmpty(), "Decode borrowed still-retained viewer pixels");
    }
    viewer.close(); require(ledger.reservedPixels() == 3_000_000, "Final viewer close did not release its pixels");
    plans.forEach(NotebookRichOutput.Plan::close);
    require(ledger.reservedPixels() == 0 && ledger.peakPixels() == 4_000_000, "Ledger peak/release did not include active decodes");
    byte[] complete = Base64.getDecoder().decode(encoded("PNG", 400, 300));
    JsonObject broken = output("image/png", Base64.getEncoder().encodeToString(Arrays.copyOf(complete, 33)));
    var failedLedger = new NotebookRichOutput.PixelLedger(4_000_000);
    try (var failed = NotebookRichOutput.prepare(new NotebookRichOutput.Input(List.of(broken), null, true), 4_000_000,
        new NotebookRichOutput.Cancellation(), failedLedger)) {
      require(images(failed).isEmpty(), "Truncated image decoded unexpectedly");
    }
    require(failedLedger.peakPixels() > 0 && failedLedger.reservedPixels() == 0, "Decode failure leaked or skipped its pre-read reservation");
  }
  private static String oversizedPng() throws Exception {
    ByteArrayOutputStream bytes = new ByteArrayOutputStream(); DataOutputStream data = new DataOutputStream(bytes);
    data.writeLong(0x89504e470d0a1a0aL);
    ByteArrayOutputStream header = new ByteArrayOutputStream(); DataOutputStream fields = new DataOutputStream(header);
    fields.writeInt(100000); fields.writeInt(100000); fields.write(new byte[]{8, 2, 0, 0, 0});
    byte[] type = "IHDR".getBytes(java.nio.charset.StandardCharsets.US_ASCII), payload = header.toByteArray();
    CRC32 crc = new CRC32(); crc.update(type); crc.update(payload);
    data.writeInt(payload.length); data.write(type); data.write(payload); data.writeInt((int)crc.getValue());
    return Base64.getEncoder().encodeToString(bytes.toByteArray());
  }

  private static void staticMarkupAndSwing() throws Exception {
    AtomicInteger fetched = new AtomicInteger();
    HttpServer trap = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
    trap.createContext("/", exchange -> { fetched.incrementAndGet(); exchange.sendResponseHeaders(200, 0); exchange.close(); }); trap.start();
    try {
      String url = "http://127.0.0.1:" + trap.getAddress().getPort() + "/must-not-fetch";
      String html = "<!DOCTYPE html SYSTEM '" + url + "'><h2>DataFrame</h2><script>forbidden script</script><style>forbidden style</style><iframe src='" + url + "'>iframe content</iframe>"
          + "<img src='" + url + "' alt='external'><link rel='stylesheet' href='" + url + "'>"
          + "<table><thead><tr><th>name</th><th>value</th></tr></thead><tbody><tr><td>&lt;html&gt;&lt;img src='" + url + "'&gt;</td><td>42</td></tr></tbody></table>";
      try (var plan = prepare(output("text/html", html))) {
        require(tables(plan).size() == 1 && tables(plan).getFirst().headers().equals(List.of("name", "value")), "Static HTML table was not parsed");
        require(tables(plan).getFirst().rows().getFirst().get(1).equals("42"), "DataFrame cell changed");
        require(!text(plan).contains("forbidden script") && !text(plan).contains("forbidden style"), "Active content was exposed as preview content");
        require(text(plan).contains("DataFrame") && text(plan).contains("Image omitted"), "Static text/image omission missing");
        SwingUtilities.invokeAndWait(() -> {
          NotebookOutputPanel panel = new NotebookOutputPanel(); panel.apply(plan.retain());
          List<Component> components = new ArrayList<>(); walk(panel, components);
          JTable table = components.stream().filter(value -> value instanceof JTable).map(value -> (JTable)value).findFirst().orElseThrow();
          require(table.getValueAt(0, 1).equals("42") && !table.isCellEditable(0, 1), "Native table model is incorrect/editable");
          JLabel rendered = (JLabel)table.prepareRenderer(table.getCellRenderer(0, 0), 0, 0);
          require(rendered.getText().startsWith(" <html>") && Boolean.TRUE.equals(rendered.getClientProperty("html.disable")), "Table cell could activate implicit JLabel HTML");
          for (Component component : components) if (component instanceof JTextPane pane) require(!(pane.getEditorKit() instanceof HTMLEditorKit), "Markup reached an active HTML Swing view");
          panel.setSize(900, 640); panel.doLayout(); BufferedImage painted = new BufferedImage(900, 640, BufferedImage.TYPE_INT_ARGB);
          Graphics2D graphics = painted.createGraphics(); panel.printAll(graphics); graphics.dispose(); painted.flush(); panel.close();
        });
      }
      try (var rowHeaders = prepare(output("text/html", "<table><tr><th>row one</th><td>alpha</td></tr><tr><th>row two</th><td>beta</td></tr></table>"))) {
        require(tables(rowHeaders).getFirst().rows().size() == 2 && tables(rowHeaders).getFirst().rows().getFirst().equals(List.of("row one", "alpha")),
            "A row-header TH caused the first actual data row to be mistaken for column headings");
      }
      String markdown = "# Notebook\n\n**bold** and *italic*, `code` [label](" + url + ")\n\n- item\n\n```python\nprint(42)\n```\n\n| A | B |\n|---|---|\n| one | two |\n\n![remote](" + url + ")\n<script>hidden script</script>";
      try (var plan = NotebookRichOutput.prepare(NotebookRichOutput.Input.markdown(markdown, true), 0, new NotebookRichOutput.Cancellation())) {
        require(text(plan).contains("Notebook") && text(plan).contains("print(42)") && !text(plan).contains("hidden script"), "Markdown preview text is wrong");
        require(tables(plan).size() == 1 && tables(plan).getFirst().rows().getFirst().equals(List.of("one", "two")), "GFM table preview missing");
        boolean bold = false, code = false;
        for (var block : plan.blocks()) if (block instanceof NotebookRichOutput.Text content) {
          String text = content.document().getText(0, content.document().getLength());
          int at = text.indexOf("bold"); if (at >= 0) bold |= StyleConstants.isBold(content.document().getCharacterElement(at).getAttributes());
          at = text.indexOf("print(42)"); if (at >= 0) code |= StyleConstants.getFontFamily(content.document().getCharacterElement(at).getAttributes()).equals("Monospaced");
        }
        require(bold && code, "Markdown did not produce actual styled heading/emphasis/code documents");
      }
      Thread.sleep(200); require(fetched.get() == 0, "Static HTML/Markdown/native components fetched an external resource");
    } finally { trap.stop(0); }
  }
  static void walk(Component component, List<Component> result) {
    result.add(component); if (component instanceof Container parent) for (Component child : parent.getComponents()) walk(child, result);
  }
  public static void main(String[] args) throws Exception {
    imagesAndLimits(); finalReferenceReservations(); staticMarkupAndSwing();
    System.out.println("{\"status\":\"pass\",\"actualPngJpegDecode\":true,\"metadataAndMultiline\":true,\"pixelAndTrustBounds\":true,\"offEdtGuard\":true,\"staticHtmlTable\":true,\"markdownStylesAndGfmTable\":true,\"actualNativeSwingComponents\":true,\"externalFetches\":0,\"preDecodeFinalReferenceReservations\":true,\"nativeIdeLaunched\":false}");
  }
}
