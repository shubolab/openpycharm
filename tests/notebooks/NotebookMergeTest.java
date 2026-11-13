package dev.openpycharm.notebooks;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.JsonElement;
import java.math.BigInteger;
import java.util.List;

/** Pure JVM tests cover large foreign metadata without a filesystem or IDE. */
public final class NotebookMergeTest {
  private static void require(boolean condition, String message) {
    if (!condition) throw new AssertionError(message);
  }
  private static JsonObject json(String value) { return JsonParser.parseString(value).getAsJsonObject(); }
  private static JsonObject cell(JsonObject notebook, int index) {
    return notebook.getAsJsonArray("cells").get(index).getAsJsonObject();
  }
  private static JsonObject notebook() {
    return json("""
        {"nbformat":4,"nbformat_minor":5,"metadata":{"foreign":{"keep":true}},"cells":[
          {"id":"first","cell_type":"code","metadata":{"tag":"before"},"source":["before\\n"],"outputs":[],"execution_count":null},
          {"id":"second","cell_type":"markdown","metadata":{},"source":["# Before"]}]}
        """);
  }

  private static void largeIndependentChanges() {
    JsonObject base = notebook();
    base.getAsJsonObject("metadata").getAsJsonObject("foreign").addProperty("payload", "x".repeat(2_600_000));
    JsonObject local = base.deepCopy();
    JsonObject incoming = base.deepCopy();
    cell(local, 0).addProperty("source", "print('local edit')\n");
    incoming.getAsJsonObject("metadata").addProperty("external", "external notebook metadata");
    cell(incoming, 0).getAsJsonObject("metadata").addProperty("tag", "external cell metadata");
    NotebookMerge.Result result = NotebookMerge.merge(base, local, incoming);
    require(!result.hasConflicts(), "Independent source/metadata edits conflicted");
    require(cell(result.merged(), 0).get("source").getAsString().equals("print('local edit')\n"), "Local source was lost");
    require(result.merged().getAsJsonObject("metadata").get("external").getAsString().equals("external notebook metadata"), "Incoming notebook metadata was lost");
    require(cell(result.merged(), 0).getAsJsonObject("metadata").get("tag").getAsString().equals("external cell metadata"), "Incoming cell metadata was lost");
    require(result.merged().getAsJsonObject("metadata").get("foreign") == incoming.getAsJsonObject("metadata").get("foreign"), "Unchanged large foreign metadata was copied");
    require(result.merged().getAsJsonObject("metadata").getAsJsonObject("foreign").get("payload").getAsString().length() == 2_600_000, "Foreign payload was changed");
    require(cell(base, 0).get("source").isJsonArray(), "Merge mutated base source");
    require(cell(incoming, 0).get("source").isJsonArray(), "Merge mutated incoming source");
    require(cell(local, 0).getAsJsonObject("metadata").get("tag").getAsString().equals("before"), "Merge mutated local metadata");
    require(!base.getAsJsonObject("metadata").has("external"), "Merge mutated base metadata");
  }

  private static void overlappingChanges() {
    JsonObject base = notebook(), local = base.deepCopy(), incoming = base.deepCopy();
    cell(local, 0).addProperty("source", "local");
    cell(incoming, 0).addProperty("source", "external");
    local.getAsJsonObject("metadata").addProperty("local", 1);
    incoming.getAsJsonObject("metadata").addProperty("external", 2);
    NotebookMerge.Result result = NotebookMerge.merge(base, local, incoming);
    require(result.conflicts().equals(List.of("/cells/0/source")), "Overlapping field conflict path is imprecise: " + result.conflicts());
    require(cell(result.merged(), 0).get("source").getAsString().equals("local"), "Conflict did not retain local value");
    require(result.merged().getAsJsonObject("metadata").has("local") && result.merged().getAsJsonObject("metadata").has("external"), "Independent changes were dropped from partial result");
    try { result.conflicts().add("mutation"); throw new AssertionError("Conflict list is mutable"); }
    catch (UnsupportedOperationException expected) { }
  }

  private static void structuralAndAtomicArrays() {
    JsonObject base = notebook(), local = base.deepCopy(), incoming = base.deepCopy();
    cell(local, 0).addProperty("source", "local");
    JsonArray reordered = new JsonArray();
    reordered.add(cell(incoming, 1)); reordered.add(cell(incoming, 0)); incoming.add("cells", reordered);
    NotebookMerge.Result reorderedResult = NotebookMerge.merge(base, local, incoming);
    require(reorderedResult.conflicts().equals(List.of("/cells")), "Cell reorder with concurrent edit must conflict");
    require(reorderedResult.merged().get("cells") == local.get("cells"), "Structural conflict did not retain local cells");
    incoming = base.deepCopy(); incoming.getAsJsonArray("cells").remove(1);
    require(NotebookMerge.merge(base, local, incoming).conflicts().equals(List.of("/cells")), "Cell deletion with concurrent edit must conflict");
    incoming = base.deepCopy(); cell(incoming, 0).addProperty("id", "replacement");
    require(NotebookMerge.merge(base, local, incoming).conflicts().equals(List.of("/cells")), "Cell identity replacement must conflict");
    incoming = base.deepCopy(); cell(incoming, 1).addProperty("id", "first");
    require(NotebookMerge.merge(base, local, incoming).conflicts().equals(List.of("/cells")), "Duplicate cell identities must conflict");
    incoming = base.deepCopy(); cell(incoming, 0).remove("id");
    require(NotebookMerge.merge(base, local, incoming).conflicts().equals(List.of("/cells")), "Missing cell identities must conflict");
    JsonObject arrayBase = json("{\"tags\":[1,2]}");
    JsonObject arrayLocal = json("{\"tags\":[3,2]}");
    JsonObject arrayIncoming = json("{\"tags\":[1,4]}");
    NotebookMerge.Result arrayResult = NotebookMerge.merge(arrayBase, arrayLocal, arrayIncoming);
    require(arrayResult.conflicts().equals(List.of("/tags")), "Non-cell arrays must be atomic");
    require(arrayResult.merged().equals(arrayLocal), "Atomic conflict did not retain local array");
  }

  private static void unchangedAndIdenticalChanges() {
    JsonObject base = notebook(), local = base.deepCopy(), incoming = base.deepCopy();
    cell(incoming, 0).addProperty("source", "external");
    require(NotebookMerge.merge(base, local, incoming).merged() == incoming, "Unchanged local did not choose incoming");
    require(NotebookMerge.merge(base, incoming, local).merged() == incoming, "Unchanged incoming did not choose local");
    JsonObject identical = incoming.deepCopy();
    NotebookMerge.Result result = NotebookMerge.merge(base, incoming, identical);
    require(!result.hasConflicts() && result.merged().equals(incoming), "Identical edits conflicted");
    incoming.getAsJsonArray("cells").remove(1);
    result = NotebookMerge.merge(base, incoming, incoming.deepCopy());
    require(!result.hasConflicts() && result.merged().equals(incoming), "Identical structural changes conflicted");
  }

  private static void additionsRemovalsAndNulls() {
    JsonObject base = json("{\"removeLocal\":1,\"removeIncoming\":2,\"removeNull\":null,\"keep\":true}");
    JsonObject local = json("{\"removeIncoming\":2,\"keep\":true,\"localNew\":1,\"newObject\":{\"left\":1}}");
    JsonObject incoming = json("{\"removeLocal\":1,\"removeNull\":null,\"keep\":true,\"incomingNull\":null,\"newObject\":{\"right\":2}}");
    NotebookMerge.Result result = NotebookMerge.merge(base, local, incoming);
    require(!result.hasConflicts(), "Independent additions/removals conflicted");
    require(!result.merged().has("removeLocal") && !result.merged().has("removeIncoming") && !result.merged().has("removeNull"), "A removal was converted into a value");
    require(result.merged().has("incomingNull") && result.merged().get("incomingNull").isJsonNull(), "Explicit null was mistaken for an absent property");
    require(result.merged().get("localNew").getAsInt() == 1, "Local addition was lost");
    require(result.merged().getAsJsonObject("newObject").size() == 2, "Independent new-object keys did not merge");
    result = NotebookMerge.merge(json("{\"item\":1}"), json("{}"), json("{\"item\":2}"));
    require(result.conflicts().equals(List.of("/item")) && !result.merged().has("item"), "Delete/edit conflict did not retain local absence");
    result = NotebookMerge.merge(json("{\"item\":1}"), json("{\"item\":2}"), json("{}"));
    require(result.conflicts().equals(List.of("/item")) && result.merged().get("item").getAsInt() == 2, "Edit/delete conflict did not retain local value");
    result = NotebookMerge.merge(json("{}"), json("{\"a/b~c\":1}"), json("{\"a/b~c\":2}"));
    require(result.conflicts().equals(List.of("/a~1b~0c")), "Conflict JSON Pointer escaping failed");
  }

  private static void numericChange(String before, String after) {
    JsonObject base = notebook();
    cell(base, 0).getAsJsonObject("metadata").add("timestamp", JsonParser.parseString(before));
    JsonObject local = base.deepCopy(), incoming = base.deepCopy();
    cell(local, 0).addProperty("source", "notebook-edit");
    cell(incoming, 0).getAsJsonObject("metadata").add("timestamp", JsonParser.parseString(after));
    NotebookMerge.Result result = NotebookMerge.merge(base, local, incoming);
    require(!result.hasConflicts(), "Independent source/numeric metadata change conflicted: " + before + " / " + after);
    require(cell(result.merged(), 0).get("source").getAsString().equals("notebook-edit"), "Numeric comparison lost local source");
    require(cell(result.merged(), 0).getAsJsonObject("metadata").get("timestamp").getAsString().equals(after),
        "Incoming numeric metadata was rounded away: " + before + " / " + after);
    require(!NotebookMerge.exactEquals(JsonParser.parseString(before), JsonParser.parseString(after)), "Distinct numeric primitives compared equal");
    require(!NotebookMerge.exactEquals(json("{\"nested\":[{\"value\":" + before + "}]}"), json("{\"nested\":[{\"value\":" + after + "}]}")),
        "Containing object/array bypassed exact numeric comparison");
  }

  private static void exactNumbers() {
    numericChange("9007199254740992", "9007199254740993");
    numericChange("-9007199254740992", "-9007199254740993");
    numericChange("9223372036854775807", "9223372036854775808");
    numericChange("1.00000000000000000000000000000001", "1.00000000000000000000000000000002");
    numericChange("1e400", "2e400");
    numericChange("0", "1e-4000");
    numericChange("1e2147483648", "2e2147483648");
    numericChange("1e-2147483649", "2e-2147483649");

    for (List<String> pair : List.of(List.of("1", "1.0"), List.of("1000e-3", "1.00"),
        List.of("0.00100", "1e-3"), List.of("-0", "0.000e999999999999999999999999"),
        List.of("1e2147483648", "10e2147483647"), List.of("1e-2147483649", "10e-2147483650"))) {
      JsonElement first = JsonParser.parseString(pair.get(0)), second = JsonParser.parseString(pair.get(1));
      require(NotebookMerge.exactEquals(first, second), "Equivalent finite decimals compared different: " + pair);
      NotebookMerge.Result sameValue = NotebookMerge.merge(json("{\"v\":0}"), json("{\"v\":" + pair.get(0) + "}"), json("{\"v\":" + pair.get(1) + "}"));
      require(!sameValue.hasConflicts(), "Equivalent decimal edits produced a false conflict: " + pair);
    }
    String huge = "9".repeat(300), next = new BigInteger(huge).add(BigInteger.ONE).toString();
    JsonElement expandedScale = JsonParser.parseString("10e" + huge), normalizedScale = JsonParser.parseString("1e" + next);
    require(expandedScale.getAsJsonPrimitive().isNumber() && normalizedScale.getAsJsonPrimitive().isNumber(),
        "Extreme-exponent fixture must use actual parsed numeric primitives");
    require(NotebookMerge.exactEquals(expandedScale, normalizedScale),
        "Extreme exponent normalization expanded/rounded the exponent");
    require(NotebookMerge.exactEquals(JsonParser.parseString("10e-" + next), JsonParser.parseString("1e-" + huge)),
        "Extreme negative exponent normalization lost exact borrow arithmetic");
    require(!NotebookMerge.exactEquals(JsonParser.parseString("1e" + huge), JsonParser.parseString("2e" + huge)),
        "Extreme exponent differences compared equal");

    JsonObject base = json("{\"v\":9007199254740991}"), local = json("{\"v\":9007199254740992}"), incoming = json("{\"v\":9007199254740993}");
    NotebookMerge.Result overlap = NotebookMerge.merge(base, local, incoming);
    require(overlap.conflicts().equals(List.of("/v")) && overlap.merged().get("v").getAsString().equals("9007199254740992"),
        "Concurrent adjacent large integer changes did not retain an exact local conflict");
    require(!NotebookMerge.exactEquals(JsonParser.parseString("1"), JsonParser.parseString("\"1\"")), "String and number compared equal");
    require(!NotebookMerge.exactEquals(JsonParser.parseString("true"), JsonParser.parseString("1")), "Boolean and number compared equal");
    require(!NotebookMerge.exactEquals(null, JsonParser.parseString("null")), "Missing and explicit null compared equal");
    require(NotebookMerge.exactEquals(json("{\"b\":[1.00],\"a\":null}"), json("{\"a\":null,\"b\":[10e-1]}")),
        "Object key order or nested equivalent decimals changed equality");
  }

  public static void main(String[] args) {
    largeIndependentChanges();
    overlappingChanges();
    structuralAndAtomicArrays();
    unchangedAndIdenticalChanges();
    additionsRemovalsAndNulls();
    exactNumbers();
    System.out.println("{\"status\":\"pass\",\"foreignMetadataChars\":2600000,\"independentSourceAndMetadata\":true,\"localRetainedOnConflict\":true,\"stableCellIdentities\":true,\"structuralAndAtomicArrays\":true,\"identicalChanges\":true,\"missingKeysAndNull\":true,\"immutableInputs\":true,\"structuralSharing\":true,\"exactLargeIntegersAndDecimals\":true,\"extremeExponents\":true,\"recursiveNumericEquality\":true}");
  }
}
