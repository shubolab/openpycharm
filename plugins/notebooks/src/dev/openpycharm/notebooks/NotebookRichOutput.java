package dev.openpycharm.notebooks;

import com.google.gson.*;
import java.awt.image.BufferedImage;
import java.io.*;
import java.util.*;
import java.util.List;
import java.util.concurrent.CancellationException;
import java.util.concurrent.atomic.*;
import javax.imageio.*;
import javax.imageio.event.IIOReadProgressListener;
import javax.imageio.stream.MemoryCacheImageInputStream;
import javax.swing.SwingUtilities;
import javax.swing.text.*;

/** Pure, bounded MIME preparation. No browser, URL opener, ImageIO disk cache or script engine. */
public final class NotebookRichOutput {
  public static final int MAX_MIME_CHARS = 2 * 1024 * 1024;
  public static final int MAX_TEXT_CHARS = 200000, MAX_BLOCKS = 64, MAX_OUTPUTS = 128;
  public static final long MAX_SOURCE_PIXELS = 8_000_000, MAX_IMAGE_PIXELS = 1_000_000;
  public static final long NOTEBOOK_PIXEL_BUDGET = 4_000_000;
  public sealed interface Block permits Text, Table, Image { }
  public record Text(DefaultStyledDocument document) implements Block { }
  public record Table(List<String> headers, List<List<String>> rows) implements Block {
    public Table { headers = List.copyOf(headers); rows = rows.stream().map(List::copyOf).toList(); }
  }
  public record Image(BufferedImage image, int sourceWidth, int sourceHeight, int width, int height, String mime) implements Block { }
  public record Input(List<JsonObject> outputs, String markdown, boolean projectTrusted) {
    public Input { outputs = List.copyOf(outputs); }
    public static Input markdown(String source, boolean trusted) { return new Input(List.of(), source, trusted); }
  }
  public static final class Cancellation {
    private final AtomicBoolean cancelled = new AtomicBoolean();
    public void cancel() { cancelled.set(true); }
    public void check() { if (cancelled.get() || Thread.currentThread().isInterrupted()) throw new CancellationException(); }
  }
  /** Scheduler and Swing viewer hold separate references; stale results release their images. */
  public static final class Plan implements AutoCloseable {
    private final List<Block> blocks;
    private final long pixels;
    private final AtomicInteger references = new AtomicInteger(1);
    Plan(List<Block> blocks, long pixels) { this.blocks = List.copyOf(blocks); this.pixels = pixels; }
    public List<Block> blocks() { return blocks; }
    public long pixels() { return pixels; }
    public Plan retain() {
      int count;
      do { count = references.get(); if (count <= 0) throw new IllegalStateException("Preview already released"); }
      while (!references.compareAndSet(count, count + 1));
      return this;
    }
    public boolean released() { return references.get() == 0; }
    @Override public void close() {
      int count = references.decrementAndGet();
      if (count == 0) for (Block block : blocks) if (block instanceof Image image) image.image().flush();
      if (count < 0) throw new IllegalStateException("Preview released twice");
    }
  }

  static final class Builder {
    final List<Block> blocks = new ArrayList<>();
    final Cancellation cancellation;
    final long allowance;
    long pixels;
    int characters;
    boolean truncated;
    DefaultStyledDocument document = new DefaultStyledDocument();
    Builder(long allowance, Cancellation cancellation) { this.allowance = Math.max(0, allowance); this.cancellation = cancellation; }
    void text(String value) { text(value, 0, 13); }
    void text(String value, int flags, int size) {
      cancellation.check();
      int remaining = MAX_TEXT_CHARS - 128 - characters;
      if (remaining <= 0 || blocks.size() >= MAX_BLOCKS - 1) { truncated = true; return; }
      if (value.length() > remaining) { value = value.substring(0, remaining); truncated = true; }
      SimpleAttributeSet attributes = new SimpleAttributeSet();
      StyleConstants.setBold(attributes, (flags & 1) != 0);
      StyleConstants.setItalic(attributes, (flags & 2) != 0);
      StyleConstants.setFontFamily(attributes, (flags & 4) != 0 ? "Monospaced" : "Dialog");
      StyleConstants.setFontSize(attributes, size);
      try { document.insertString(document.getLength(), value, attributes); }
      catch (BadLocationException impossible) { throw new IllegalStateException(impossible); }
      characters += value.length();
    }
    void flush() {
      if (document.getLength() != 0) {
        if (blocks.size() < MAX_BLOCKS - 1) blocks.add(new Text(document)); else truncated = true;
      }
      document = new DefaultStyledDocument();
    }
    void table(Table table) { flush(); if (blocks.size() < MAX_BLOCKS - 1) blocks.add(table); else truncated = true; }
    void image(Image image) {
      flush();
      if (blocks.size() < MAX_BLOCKS - 1) { blocks.add(image); pixels += (long)image.image().getWidth() * image.image().getHeight(); }
      else { image.image().flush(); truncated = true; }
    }
    Plan finish() {
      flush();
      if (truncated) {
        DefaultStyledDocument notice = new DefaultStyledDocument();
        try { notice.insertString(0, "\n[Preview limited; complete output remains in the notebook]\n", null); }
        catch (BadLocationException impossible) { throw new IllegalStateException(impossible); }
        blocks.add(new Text(notice));
      }
      return new Plan(blocks, pixels);
    }
    void discard() { for (Block block : blocks) if (block instanceof Image image) image.image().flush(); }
  }

  public static Plan prepare(Input input, long pixelAllowance, Cancellation cancellation) {
    if (SwingUtilities.isEventDispatchThread()) throw new IllegalStateException("MIME parsing/image decoding must run outside the EDT");
    Builder out = new Builder(Math.min(pixelAllowance, NOTEBOOK_PIXEL_BUDGET), cancellation);
    try {
      if (input.markdown() != null) {
        if (input.projectTrusted()) NotebookStaticContent.markdown(input.markdown(), out);
        else out.text("Trust the project to show the static Markdown preview.\n");
      } else {
        int count = 0;
        for (JsonObject output : input.outputs()) {
          cancellation.check();
          if (count++ >= MAX_OUTPUTS || out.blocks.size() >= MAX_BLOCKS - 1) { out.truncated = true; break; }
          String type = NotebookKernelSession.string(output, "output_type");
          try {
            if (type.equals("stream")) out.text(previewText(output.get("text"), out));
            else if (type.equals("error")) {
              if (output.has("traceback") && output.get("traceback").isJsonArray())
                for (JsonElement line : output.getAsJsonArray("traceback")) out.text(previewText(line, out).replaceAll("\u001B\\[[;\\d]*m", "") + "\n");
              else out.text(NotebookKernelSession.string(output, "ename") + ": " + NotebookKernelSession.string(output, "evalue") + "\n");
            } else if (output.has("data") && output.get("data").isJsonObject()) bundle(output.getAsJsonObject("data"), output, input.projectTrusted(), out);
          } catch (IllegalArgumentException error) { out.text("\n[Preview unavailable: " + error.getMessage() + "]\n"); }
        }
      }
      if (out.characters >= MAX_TEXT_CHARS) out.flush();
      return out.finish();
    } catch (RuntimeException error) { out.discard(); throw error; }
  }

  private static void bundle(JsonObject data, JsonObject output, boolean trusted, Builder out) {
    if (!trusted) {
      if (data.has("text/plain")) out.text(previewText(data.get("text/plain"), out) + "\n");
      out.text("[Rich preview is disabled until the project is trusted]\n"); return;
    }
    // The nbformat trusted flag is never permission to execute active content.
    for (String mime : List.of("image/png", "image/jpeg")) if (data.has(mime)) {
      try {
        out.image(image(read(data.get(mime), MAX_MIME_CHARS), mime, output, out.allowance - out.pixels, out.cancellation));
        return;
      } catch (IllegalArgumentException error) { out.text("[" + mime + " preview unavailable: " + error.getMessage() + "]\n"); }
    }
    if (data.has("text/html")) { NotebookStaticContent.html(read(data.get("text/html"), NotebookStaticContent.MAX_MARKUP), out); return; }
    if (data.has("text/markdown")) { NotebookStaticContent.markdown(read(data.get("text/markdown"), NotebookStaticContent.MAX_MARKUP), out); return; }
    if (data.has("text/plain")) out.text(previewText(data.get("text/plain"), out) + "\n");
    else out.text("[Unsupported MIME data preserved in the notebook]\n");
  }

  private static String previewText(JsonElement value, Builder out) {
    if (value != null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isString()) {
      String text = value.getAsString();
      if (text.length() > MAX_TEXT_CHARS) { out.truncated = true; return text.substring(0, MAX_TEXT_CHARS); }
      return text;
    }
    if (value != null && value.isJsonArray()) {
      StringBuilder text = new StringBuilder();
      for (JsonElement part : value.getAsJsonArray()) {
        if (!part.isJsonPrimitive() || !part.getAsJsonPrimitive().isString()) throw new IllegalArgumentException("Text array contains a non-string");
        String line = part.getAsString(); int remaining = MAX_TEXT_CHARS - text.length();
        if (line.length() > remaining) { text.append(line, 0, remaining); out.truncated = true; break; }
        text.append(line);
      }
      return text.toString();
    }
    return read(value, MAX_TEXT_CHARS);
  }

  static String read(JsonElement value, int limit) {
    if (value == null) return "";
    if (value.isJsonPrimitive() && value.getAsJsonPrimitive().isString()) {
      String text = value.getAsString();
      if (text.length() > limit) throw new IllegalArgumentException("MIME/text data exceeds its preview limit");
      return text;
    }
    if (!value.isJsonArray()) throw new IllegalArgumentException("MIME data must be a string or string array");
    StringBuilder text = new StringBuilder();
    for (JsonElement part : value.getAsJsonArray()) {
      if (!part.isJsonPrimitive() || !part.getAsJsonPrimitive().isString()) throw new IllegalArgumentException("MIME string array contains a non-string");
      String line = part.getAsString();
      if (line.length() > limit - text.length()) throw new IllegalArgumentException("MIME/text data exceeds its preview limit");
      text.append(line);
    }
    return text.toString();
  }

  private static Image image(String encoded, String mime, JsonObject output, long remaining, Cancellation cancellation) {
    cancellation.check();
    if (remaining <= 0) throw new IllegalArgumentException("notebook decoded-pixel budget reached");
    StringBuilder clean = new StringBuilder(encoded.length());
    for (int i = 0; i < encoded.length(); i++) {
      char c = encoded.charAt(i);
      if (c == ' ' || c == '\n' || c == '\r' || c == '\t') continue;
      if (!(c >= 'A' && c <= 'Z' || c >= 'a' && c <= 'z' || c >= '0' && c <= '9' || c == '+' || c == '/' || c == '='))
        throw new IllegalArgumentException("invalid base64 image data");
      clean.append(c);
    }
    byte[] bytes;
    try { bytes = Base64.getDecoder().decode(clean.toString()); }
    catch (IllegalArgumentException error) { throw new IllegalArgumentException("invalid base64 image data"); }
    String format = mime.equals("image/png") ? "PNG" : "JPEG";
    Iterator<ImageReader> readers = ImageIO.getImageReadersByFormatName(format);
    if (!readers.hasNext()) throw new IllegalArgumentException("native " + format + " decoder unavailable");
    ImageReader reader = readers.next();
    try (var stream = new MemoryCacheImageInputStream(new ByteArrayInputStream(bytes))) {
      reader.setInput(stream, true, true);
      int width = reader.getWidth(0), height = reader.getHeight(0);
      long pixels = (long)width * height;
      if (width <= 0 || height <= 0 || width > 8192 || height > 8192 || pixels > MAX_SOURCE_PIXELS)
        throw new IllegalArgumentException("source image dimensions exceed the 8-megapixel/8192-side limit");
      long target = Math.min(MAX_IMAGE_PIXELS, remaining);
      int sampling = 1;
      while ((long)((width + sampling - 1) / sampling) * ((height + sampling - 1) / sampling) > target) sampling++;
      ImageReadParam parameters = reader.getDefaultReadParam(); parameters.setSourceSubsampling(sampling, sampling, 0, 0);
      reader.addIIOReadProgressListener(new IIOReadProgressListener() {
        public void imageStarted(ImageReader source, int index) { check(source); }
        public void imageProgress(ImageReader source, float percentage) { check(source); }
        private void check(ImageReader source) { try { cancellation.check(); } catch (CancellationException error) { source.abort(); } }
        public void imageComplete(ImageReader source) { }
        public void sequenceStarted(ImageReader source, int index) { }
        public void sequenceComplete(ImageReader source) { }
        public void thumbnailStarted(ImageReader source, int image, int thumbnail) { }
        public void thumbnailProgress(ImageReader source, float percentage) { check(source); }
        public void thumbnailComplete(ImageReader source) { }
        public void readAborted(ImageReader source) { }
      });
      BufferedImage decoded = reader.read(0, parameters);
      try {
        cancellation.check();
        if (decoded == null || (long)decoded.getWidth() * decoded.getHeight() > target) throw new IllegalArgumentException("decoded image exceeds its pixel allowance");
        int displayWidth = Math.min(1000, width), displayHeight = Math.max(1, (int)((long)height * displayWidth / width));
        JsonObject metadata = output.has("metadata") && output.get("metadata").isJsonObject() ? output.getAsJsonObject("metadata") : new JsonObject();
        if (metadata.has(mime) && metadata.get(mime).isJsonObject()) {
          int requested = dimension(metadata.getAsJsonObject(mime).get("width"));
          if (requested > 0) { displayWidth = requested; displayHeight = Math.max(1, (int)((long)height * displayWidth / width)); }
        }
        if (displayHeight > 1000) { displayWidth = Math.max(1, (int)((long)displayWidth * 1000 / displayHeight)); displayHeight = 1000; }
        return new Image(decoded, width, height, displayWidth, displayHeight, mime);
      } catch (RuntimeException error) { if (decoded != null) decoded.flush(); throw error; }
    } catch (IOException error) { throw new IllegalArgumentException("malformed " + format + " image"); }
    finally { reader.dispose(); }
  }
  private static int dimension(JsonElement value) {
    if (value == null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isNumber()) return 0;
    String text = value.getAsString();
    if (text.length() > 4 || text.isEmpty() || !text.chars().allMatch(Character::isDigit)) return 0;
    int number = Integer.parseInt(text); return number > 0 ? Math.min(1000, number) : 0;
  }
}
