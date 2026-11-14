package dev.openpycharm.notebooks;

import java.io.*;
import java.util.*;
import java.util.List;
import javax.swing.text.*;
import javax.swing.text.html.*;
import javax.swing.text.html.parser.ParserDelegator;
import org.intellij.markdown.flavours.gfm.GFMFlavourDescriptor;
import org.intellij.markdown.html.HtmlGenerator;
import org.intellij.markdown.parser.MarkdownParser;

/** Converts markup to inert styled text and table data. Never installs an HTML editor kit. */
final class NotebookStaticContent {
  static final int MAX_MARKUP = 256 * 1024, MAX_ROWS = 200, MAX_COLUMNS = 40, MAX_CELL = 4000;
  private static final Set<String> BLOCKED = Set.of("script", "style", "iframe", "object", "embed", "form", "svg", "math", "video", "audio", "template", "canvas");

  static void markdown(String source, NotebookRichOutput.Builder out) {
    if (source.length() > MAX_MARKUP) throw new IllegalArgumentException("Markdown exceeds the 256 Ki-character preview limit");
    out.cancellation.check();
    source = source.replace("\r\n", "\n").replace('\r', '\n');
    var flavour = new GFMFlavourDescriptor();
    var tree = new MarkdownParser(flavour, false, out.cancellation::check).buildMarkdownTreeFromString(source);
    var generator = new HtmlGenerator(source, tree, flavour, false);
    String html = generator.generateHtml(new HtmlGenerator.DefaultTagRenderer((node, tag, attributes) -> attributes, false));
    out.cancellation.check();
    html(html, out);
  }

  static void html(String source, NotebookRichOutput.Builder out) {
    if (source.length() > MAX_MARKUP) throw new IllegalArgumentException("HTML exceeds the 256 Ki-character preview limit");
    StaticParser parser = new StaticParser(out);
    try { new ParserDelegator().parse(new StringReader(inertMarkup(source, out)), parser, true); }
    catch (Limit reached) { parser.truncated = true; }
    catch (IOException error) { throw new IllegalArgumentException("Malformed static markup"); }
    parser.finish();
  }

  /** Strip active raw-text elements before Swing's HTML3 parser can discard an
   * invalid-in-body opening tag while exposing its script/style text. This is
   * a bounded lexical filter, not a regex sanitizer or an HTML execution path.
   */
  private static String inertMarkup(String source, NotebookRichOutput.Builder out) {
    StringBuilder result = new StringBuilder(source.length());
    String blocked = null; int nested = 0, tokens = 0;
    for (int at = 0; at < source.length();) {
      out.cancellation.check();
      if (source.startsWith("<!--", at)) {
        int end = source.indexOf("-->", at + 4); at = end < 0 ? source.length() : end + 3; continue;
      }
      if (source.charAt(at) != '<') { if (blocked == null) result.append(source.charAt(at)); at++; continue; }
      if (++tokens > 20000) throw new IllegalArgumentException("Markup token limit reached");
      int nameAt = at + 1;
      while (nameAt < source.length() && Character.isWhitespace(source.charAt(nameAt))) nameAt++;
      boolean closing = nameAt < source.length() && source.charAt(nameAt) == '/';
      if (closing) nameAt++;
      int nameEnd = nameAt;
      while (nameEnd < source.length() && Character.isLetterOrDigit(source.charAt(nameEnd))) nameEnd++;
      String name = source.substring(nameAt, nameEnd).toLowerCase(Locale.ROOT);
      int end = nameEnd; char quote = 0;
      while (end < source.length()) {
        char c = source.charAt(end);
        if (quote != 0) { if (c == quote) quote = 0; }
        else if (c == '\'' || c == '"') quote = c;
        else if (c == '>') break;
        end++;
      }
      if (end >= source.length()) { if (blocked == null) result.append(source, at, source.length()); break; }
      boolean selfClosing = end > at && source.charAt(end - 1) == '/';
      if (blocked != null) {
        if (name.equals(blocked)) {
          if (closing && --nested == 0) blocked = null;
          else if (!closing && !selfClosing) nested++;
        }
      } else if (BLOCKED.contains(name)) {
        if (!closing && !selfClosing && !name.equals("embed")) { blocked = name; nested = 1; }
      } else result.append(source, at, end + 1);
      at = end + 1;
    }
    return result.toString();
  }

  private static final class Limit extends RuntimeException { }
  private record Style(String tag, int flags, int size) { }
  private static final class StaticParser extends HTMLEditorKit.ParserCallback {
    final NotebookRichOutput.Builder out;
    final List<Style> styles = new ArrayList<>();
    final List<List<String>> rows = new ArrayList<>();
    List<String> row;
    StringBuilder cell;
    int tokens, blocked, tableDepth, span = 1;
    boolean firstRowHeader, rowHeader, truncated;
    StaticParser(NotebookRichOutput.Builder out) { this.out = out; }
    private void tick() {
      out.cancellation.check();
      if (++tokens > 20000 || out.characters >= NotebookRichOutput.MAX_TEXT_CHARS - 128 || out.blocks.size() >= NotebookRichOutput.MAX_BLOCKS - 1) throw new Limit();
    }
    @Override public void handleStartTag(HTML.Tag tag, MutableAttributeSet attributes, int position) {
      tick(); String name = tag.toString().toLowerCase(Locale.ROOT);
      if (BLOCKED.contains(name)) { blocked++; return; }
      if (blocked != 0) return;
      if (name.equals("table")) { if (tableDepth++ == 0) { out.flush(); rows.clear(); firstRowHeader = false; } return; }
      if (tableDepth > 0) {
        if (tableDepth == 1 && name.equals("tr")) { endRow(); row = new ArrayList<>(); rowHeader = true; }
        else if (tableDepth == 1 && (name.equals("th") || name.equals("td"))) {
          endCell(); if (row == null) { row = new ArrayList<>(); rowHeader = true; } cell = new StringBuilder();
          rowHeader &= name.equals("th"); span = span(attributes.getAttribute(HTML.Attribute.COLSPAN));
        }
        return;
      }
      if (Set.of("p", "div", "pre", "blockquote").contains(name) || name.matches("h[1-6]")) out.text("\n");
      if (name.equals("li")) out.text("\n• ");
      int flags = flags(), size = size();
      if (Set.of("b", "strong").contains(name)) flags |= 1;
      if (Set.of("em", "i").contains(name)) flags |= 2;
      if (Set.of("code", "pre").contains(name)) flags |= 4;
      if (name.matches("h[1-6]")) { flags |= 1; size = Math.max(14, 26 - 2 * (name.charAt(1) - '1')); }
      styles.add(new Style(name, flags, size));
    }
    @Override public void handleEndTag(HTML.Tag tag, int position) {
      tick(); String name = tag.toString().toLowerCase(Locale.ROOT);
      if (BLOCKED.contains(name)) { if (blocked > 0) blocked--; return; }
      if (blocked != 0) return;
      if (name.equals("table") && tableDepth > 0) { if (--tableDepth == 0) emitTable(); return; }
      if (tableDepth > 0) {
        if (tableDepth == 1 && (name.equals("th") || name.equals("td"))) endCell();
        if (tableDepth == 1 && name.equals("tr")) endRow();
        return;
      }
      for (int i = styles.size() - 1; i >= 0; i--) if (styles.get(i).tag().equals(name)) { styles.subList(i, styles.size()).clear(); break; }
      if (Set.of("p", "div", "pre", "li", "blockquote").contains(name) || name.matches("h[1-6]")) out.text("\n");
    }
    @Override public void handleSimpleTag(HTML.Tag tag, MutableAttributeSet attributes, int position) {
      tick(); String name = tag.toString().toLowerCase(Locale.ROOT);
      if (blocked != 0 || BLOCKED.contains(name)) return;
      if (name.equals("br")) append("\n");
      if (name.equals("hr")) append("\n────────\n");
      // Ignore every URL/style/event attribute, including data: and attachment:.
      // No component ever receives this markup or an image source URL.
      if (name.equals("img")) {
        Object alt = attributes.getAttribute(HTML.Attribute.ALT);
        append("[Image omitted" + (alt == null ? "" : ": " + String.valueOf(alt)) + "]");
      }
    }
    @Override public void handleText(char[] data, int position) { tick(); if (blocked == 0) append(new String(data)); }
    @Override public void handleComment(char[] data, int position) { tick(); }
    private int flags() { return styles.isEmpty() ? 0 : styles.getLast().flags(); }
    private int size() { return styles.isEmpty() ? 13 : styles.getLast().size(); }
    private void append(String value) {
      if (tableDepth != 0) {
        if (cell != null) {
          int remaining = Math.min(MAX_CELL - cell.length(), NotebookRichOutput.MAX_TEXT_CHARS - 128 - out.characters);
          if (remaining <= 0) { truncated = true; return; }
          if (value.length() > remaining) { value = value.substring(0, remaining); truncated = true; }
          cell.append(value); out.characters += value.length();
        }
      } else out.text(value, flags(), size());
    }
    private static int span(Object value) {
      if (value == null) return 1;
      String raw = value.toString();
      if (raw.length() > 2 || raw.isEmpty() || !raw.chars().allMatch(Character::isDigit)) return 1;
      return Math.max(1, Math.min(MAX_COLUMNS, Integer.parseInt(raw)));
    }
    private void endCell() {
      if (cell == null) return;
      if (row == null) row = new ArrayList<>();
      if (row.size() < MAX_COLUMNS) { row.add(cell.toString()); for (int i = 1; i < span && row.size() < MAX_COLUMNS; i++) row.add(""); }
      else truncated = true;
      cell = null; span = 1;
    }
    private void endRow() {
      endCell();
      if (row != null) {
        if (rows.size() < MAX_ROWS + 1) { if (rows.isEmpty()) firstRowHeader = rowHeader; rows.add(row); }
        else truncated = true;
      }
      row = null;
    }
    private void emitTable() {
      endRow();
      if (rows.isEmpty()) return;
      int columns = rows.stream().mapToInt(List::size).max().orElse(0);
      if (columns == 0) { rows.clear(); return; }
      List<String> headers = new ArrayList<>();
      if (firstRowHeader) headers.addAll(rows.removeFirst());
      while (headers.size() < columns) headers.add(firstRowHeader ? "" : Integer.toString(headers.size() + 1));
      for (List<String> data : rows) while (data.size() < columns) data.add("");
      if (rows.size() > MAX_ROWS) { rows.subList(MAX_ROWS, rows.size()).clear(); truncated = true; }
      out.table(new NotebookRichOutput.Table(headers, rows)); rows.clear();
    }
    void finish() {
      if (tableDepth > 0) { tableDepth = 0; emitTable(); }
      if (truncated) out.text("\n[Static preview is limited; complete markup remains in the notebook]\n");
    }
  }
}
