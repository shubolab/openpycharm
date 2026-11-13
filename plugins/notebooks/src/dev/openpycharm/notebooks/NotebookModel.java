package dev.openpycharm.notebooks;

import com.google.gson.*;
import java.util.UUID;

/** nbformat v4 persistence. Unknown notebook, cell, metadata and output keys survive edits. */
public final class NotebookModel {
  public static final int MAX_CHARS = 8 * 1024 * 1024;
  public static final int MAX_CELLS = 1000;
  private static final Gson JSON = new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create();
  private final JsonObject root;
  private final JsonArray cells;

  private NotebookModel(JsonObject root) {
    this.root = root;
    this.cells = root.getAsJsonArray("cells");
  }

  public static NotebookModel parse(String text) {
    if (text.length() > MAX_CHARS) throw new IllegalArgumentException("Notebook exceeds the 8 MiB native editor limit; use the JSON editor");
    JsonObject root = JsonParser.parseString(text).getAsJsonObject();
    if (!root.has("nbformat") || root.get("nbformat").getAsInt() != 4)
      throw new IllegalArgumentException("Only nbformat 4 notebooks are supported");
    if (!root.has("cells") || !root.get("cells").isJsonArray() || root.getAsJsonArray("cells").size() > MAX_CELLS)
      throw new IllegalArgumentException("Notebook needs a cells array with at most 1000 cells");
    NotebookModel model = new NotebookModel(root);
    for (int i = 0; i < model.size(); i++) {
      JsonObject cell = model.cell(i);
      String kind = model.kind(i);
      if (!kind.equals("code") && !kind.equals("markdown") && !kind.equals("raw"))
        throw new IllegalArgumentException("Unsupported cell type: " + kind);
      sourceText(cell.get("source"));
      if (kind.equals("code") && cell.has("outputs") && !cell.get("outputs").isJsonArray())
        throw new IllegalArgumentException("Code cell outputs must be an array");
    }
    return model;
  }

  public static NotebookModel empty() {
    return parse("{\"nbformat\":4,\"nbformat_minor\":5,\"metadata\":{},\"cells\":[]}");
  }

  public int size() { return cells.size(); }
  public JsonObject cell(int i) { return cells.get(i).getAsJsonObject(); }
  public String kind(int i) { return cell(i).get("cell_type").getAsString(); }
  public String source(int i) { return sourceText(cell(i).get("source")); }
  public void source(int i, String text) { cell(i).add("source", lines(text)); }
  public JsonArray outputs(int i) {
    JsonObject cell = cell(i);
    if (!cell.has("outputs")) cell.add("outputs", new JsonArray());
    return cell.getAsJsonArray("outputs");
  }
  public void clearOutputs(int i) { cell(i).add("outputs", new JsonArray()); cell(i).add("execution_count", JsonNull.INSTANCE); }
  public void executionCount(int i, JsonElement count) { cell(i).add("execution_count", count == null ? JsonNull.INSTANCE : count.deepCopy()); }
  public JsonObject output(int i, String type, JsonObject content) {
    JsonObject output = content.deepCopy();
    output.remove("transient"); // Jupyter transient/display_id is never part of persisted nbformat.
    output.addProperty("output_type", type);
    // Protocol fields belong to execute_input/status, never saved as cell outputs.
    outputs(i).add(output);
    return output;
  }
  public int add(String kind) {
    if (size() >= MAX_CELLS) throw new IllegalArgumentException("Notebook already has 1000 cells");
    JsonObject cell = new JsonObject();
    cell.addProperty("cell_type", kind);
    cell.addProperty("id", UUID.randomUUID().toString().substring(0, 8));
    cell.add("metadata", new JsonObject());
    cell.add("source", new JsonArray());
    cells.add(cell);
    if (kind.equals("code")) clearOutputs(size() - 1);
    return size() - 1;
  }
  public void remove(int i) { cells.remove(i); }
  public String json() {
    String result = JSON.toJson(root) + "\n";
    if (result.length() > MAX_CHARS) throw new IllegalArgumentException("Notebook output exceeds the 8 MiB save limit; clear cell outputs");
    return result;
  }

  public static String sourceText(JsonElement source) {
    if (source == null) throw new IllegalArgumentException("Notebook cell has no source");
    if (source.isJsonPrimitive() && source.getAsJsonPrimitive().isString()) return source.getAsString();
    if (!source.isJsonArray()) throw new IllegalArgumentException("Cell source must be a string or string array");
    StringBuilder result = new StringBuilder();
    for (JsonElement line : source.getAsJsonArray()) {
      if (!line.isJsonPrimitive() || !line.getAsJsonPrimitive().isString()) throw new IllegalArgumentException("Cell source contains a non-string");
      result.append(line.getAsString());
    }
    return result.toString();
  }
  public static JsonArray lines(String source) {
    JsonArray lines = new JsonArray();
    int start = 0;
    for (int i = 0; i < source.length(); i++) {
      if (source.charAt(i) == '\n') { lines.add(source.substring(start, i + 1)); start = i + 1; }
    }
    if (start < source.length()) lines.add(source.substring(start));
    return lines;
  }
}
