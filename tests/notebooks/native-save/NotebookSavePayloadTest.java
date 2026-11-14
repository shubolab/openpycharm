package dev.openpycharm.notebooks.saveprobe;

import com.google.gson.*;
import dev.openpycharm.notebooks.NotebookModel;
import java.lang.reflect.*;
import java.util.*;
import java.util.function.Consumer;

/** Actual native-gate assertion controls; does not initialize an IDE/save engine. */
public final class NotebookSavePayloadTest {
  public static void main(String[] args) throws Exception {
    JsonObject initial = JsonParser.parseString("""
        {"nbformat":4,"nbformat_minor":5,"metadata":{"large":9007199254740993,"foreign":{"keep":[1,"中文",true]}},
         "cells":[{"id":"save-probe","cell_type":"code","metadata":{"trusted":false,"foreignCell":"keep"},
         "source":["original\\n"],"execution_count":7,"outputs":[{"output_type":"display_data","data":{
         "text/plain":"Existing fixture output; not kernel evidence","application/x-save-probe":{"keep":true}},
         "metadata":{"foreignOutput":"keep"}}]}]}
        """).getAsJsonObject();
    JsonObject valid = initial.deepCopy();
    valid.getAsJsonArray("cells").get(0).getAsJsonObject().addProperty("source", "print('真实原生保存 中文')\nvalue = 3\n");
    valid.getAsJsonObject("metadata").addProperty("externalTextEdit", "kept");
    Method assertion = NotebookSaveProbe.class.getDeclaredMethod("assertPayload", NotebookModel.class, JsonObject.class, boolean.class); assertion.setAccessible(true);
    assertValid(assertion, valid, initial, false);
    JsonObject second = valid.deepCopy(); second.getAsJsonObject("metadata").addProperty("externalAfterSave", "kept");
    assertValid(assertion, second, initial, true);
    List<Consumer<JsonObject>> corruptions = List.of(
        tree -> tree.getAsJsonObject("metadata").remove("foreign"),
        tree -> tree.getAsJsonObject("metadata").getAsJsonObject("foreign").getAsJsonArray("keep").set(1, new JsonPrimitive("changed")),
        tree -> cell(tree).getAsJsonObject("metadata").remove("foreignCell"),
        tree -> cell(tree).getAsJsonObject("metadata").addProperty("foreignCell", "changed"),
        tree -> cell(tree).getAsJsonObject("metadata").addProperty("trusted", true),
        tree -> output(tree).getAsJsonObject("data").addProperty("text/plain", "changed"),
        tree -> output(tree).getAsJsonObject("data").remove("application/x-save-probe"),
        tree -> output(tree).getAsJsonObject("data").getAsJsonObject("application/x-save-probe").addProperty("keep", false),
        tree -> output(tree).getAsJsonObject("metadata").remove("foreignOutput"),
        tree -> output(tree).getAsJsonObject("metadata").addProperty("foreignOutput", "changed"),
        tree -> cell(tree).addProperty("execution_count", 8),
        tree -> tree.getAsJsonObject("metadata").addProperty("large", 9007199254740992L),
        tree -> tree.getAsJsonObject("metadata").remove("externalTextEdit"),
        tree -> tree.getAsJsonObject("metadata").addProperty("unexpected", "changed"),
        tree -> cell(tree).addProperty("cell_type", "raw"),
        tree -> cell(tree).addProperty("source", "wrong source"));
    for (Consumer<JsonObject> corruption : corruptions) {
      JsonObject broken = valid.deepCopy(); corruption.accept(broken);
      try { assertion.invoke(null, NotebookModel.parse(broken.toString()), initial, false); throw new AssertionError("Native gate accepted immutable payload corruption"); }
      catch (InvocationTargetException rejected) { if (!(rejected.getCause() instanceof IllegalStateException)) throw rejected; }
    }
    System.out.println("{\"status\":\"pass\",\"validSavePayloads\":2,\"immutableCorruptionsRejected\":" + corruptions.size() + ",\"actualIdeSaveEngineExercised\":false}");
  }
  private static JsonObject cell(JsonObject tree) { return tree.getAsJsonArray("cells").get(0).getAsJsonObject(); }
  private static JsonObject output(JsonObject tree) { return cell(tree).getAsJsonArray("outputs").get(0).getAsJsonObject(); }
  private static void assertValid(Method assertion, JsonObject valid, JsonObject initial, boolean second) throws Exception {
    assertion.invoke(null, NotebookModel.parse(valid.toString()), initial, second);
  }
}
