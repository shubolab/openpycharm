package dev.openpycharm.notebooks;

import com.google.gson.*;
import java.util.List;

/** Real JVM persistence checks include foreign metadata, rich output, Unicode and invalid files. */
public final class NotebookModelTest {
  static void require(boolean condition, String message) { if (!condition) throw new AssertionError(message); }
  public static void main(String[] args) {
    String fixture = """
        {"nbformat":4,"nbformat_minor":5,"metadata":{"kernelspec":{"name":"foreign"},"custom":[1,"中文"]},"extension":{"preserve":true},"cells":[
          {"cell_type":"markdown","id":"md01","metadata":{"custom":1},"source":["# Notebook\\n","中文"],"attachments":{"image.png":{"image/png":"YWJj"}}},
          {"cell_type":"code","id":"code01","metadata":{"tags":["keep"]},"source":"print('before')","execution_count":7,"outputs":[{"output_type":"display_data","data":{"text/plain":["example"],"text/html":"<b>example</b>"},"metadata":{"custom":2},"foreign":true}]},
          {"cell_type":"raw","metadata":{},"source":[]}]}
        """;
    NotebookModel model = NotebookModel.parse(fixture);
    require(model.size() == 3 && model.source(0).equals("# Notebook\n中文"), "String-array sources did not load");
    model.source(1, "value = '中文'\nprint(value)\n");
    JsonObject saved = JsonParser.parseString(model.json()).getAsJsonObject();
    JsonObject original = JsonParser.parseString(fixture).getAsJsonObject();
    require(saved.get("metadata").equals(original.get("metadata")), "Notebook metadata changed");
    require(saved.get("extension").equals(original.get("extension")), "Unknown notebook key changed");
    require(saved.getAsJsonArray("cells").get(0).equals(original.getAsJsonArray("cells").get(0)), "Markdown attachments changed");
    require(model.outputs(1).equals(original.getAsJsonArray("cells").get(1).getAsJsonObject().get("outputs")), "Rich outputs changed on source edit");
    require(NotebookModel.parse(model.json()).source(1).equals("value = '中文'\nprint(value)\n"), "Source edit did not round trip");
    model.clearOutputs(1); require(model.outputs(1).isEmpty(), "Clear output failed");
    JsonObject stream = new JsonObject(); stream.addProperty("name", "stdout"); stream.addProperty("text", "real stream\n");
    model.output(1, "stream", stream); model.executionCount(1, new JsonPrimitive(8));
    JsonObject display = new JsonObject(); display.add("data", new JsonObject()); display.add("metadata", new JsonObject());
    JsonObject transientData = new JsonObject(); transientData.addProperty("display_id", "session-only"); display.add("transient", transientData);
    JsonObject captured = model.output(1, "display_data", display);
    require(!captured.has("transient") && display.has("transient"), "Transient display IDs were persisted or source content mutated");
    require(model.cell(1).get("execution_count").getAsInt() == 8, "Execution count did not persist");
    require(model.outputs(1).get(0).getAsJsonObject().get("output_type").getAsString().equals("stream"), "Output type absent");
    int added = model.add("code"); model.source(added, "2 + 2");
    require(model.cell(added).has("id") && model.outputs(added).isEmpty(), "New cell missing nbformat fields");
    model.remove(0); require(model.size() == 3, "Cell removal failed");
    for (String invalid : List.of("{}", "[]", "{\"nbformat\":3,\"cells\":[]}",
        "{\"nbformat\":4,\"cells\":[{\"cell_type\":\"code\",\"source\":[1]}]}",
        "{\"nbformat\":4,\"cells\":[{\"cell_type\":\"unknown\",\"source\":\"\"}]}")) {
      try { NotebookModel.parse(invalid); throw new AssertionError("Invalid notebook was accepted: " + invalid); }
      catch (IllegalArgumentException | IllegalStateException expected) { }
    }
    try { NotebookModel.parse(" ".repeat(NotebookModel.MAX_CHARS + 1)); throw new AssertionError("Oversized notebook accepted"); }
    catch (IllegalArgumentException expected) { }
    require(NotebookModel.parse(model.json()).size() == 3, "Edited notebook is not parseable");
    String large = "{\"nbformat\":4,\"metadata\":{\"foreign\":[" + "0,".repeat(1300000) + "0]},\"cells\":[{\"cell_type\":\"code\",\"source\":\"before\",\"metadata\":{},\"outputs\":[],\"execution_count\":null}]}";
    require(large.length() < NotebookModel.MAX_CHARS, "Large regression fixture exceeds admission bound");
    NotebookModel largeModel = NotebookModel.parse(large);
    NotebookModel.Snapshot beforeEdit = largeModel.snapshot();
    largeModel.source(0, "edited");
    String compact = largeModel.json();
    require(compact.length() < NotebookModel.MAX_CHARS, "Compact metadata expanded past admission bound");
    require(NotebookModel.parse(compact).source(0).equals("edited"), "Large metadata prevented source persistence");
    require(NotebookModel.parse(beforeEdit.json()).source(0).equals("before"), "Pending snapshot changed with mutable model");
    require(JsonParser.parseString(compact).getAsJsonObject().get("metadata").equals(JsonParser.parseString(large).getAsJsonObject().get("metadata")), "Large foreign metadata was stripped");
    largeModel.source(0, "x".repeat(NotebookModel.MAX_CHARS));
    String grown = largeModel.json();
    require(grown.length() > NotebookModel.MAX_CHARS && JsonParser.parseString(grown).getAsJsonObject().getAsJsonArray("cells").get(0).getAsJsonObject().get("source").getAsJsonArray().get(0).getAsString().length() == NotebookModel.MAX_CHARS,
        "Edited data beyond the native admission bound must remain serializable JSON, never silently unsaved");
    System.out.println("{\"status\":\"pass\",\"metadataAndAttachmentsPreserved\":true,\"richOutputsPreserved\":true,\"sourceRoundTrip\":true,\"outputsAndCount\":true,\"addDeleteCells\":true,\"malformedAndOversizedRejected\":true}");
  }
}
