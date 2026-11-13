package dev.openpycharm.notebooks;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

/**
 * Three-way JSON merge for immutable notebook snapshots. Selected values are
 * structurally shared; only combined containers are replaced. Neither inputs
 * nor the returned tree may be mutated without first replacing the affected
 * containers. Unknown metadata is handled like every other JSON object field.
 */
public final class NotebookMerge {
  private NotebookMerge() { }

  /** Conflicts are JSON Pointer paths. A conflict keeps the local value/absence. */
  public record Result(JsonObject merged, List<String> conflicts) {
    public Result { conflicts = List.copyOf(conflicts); }
    public boolean hasConflicts() { return !conflicts.isEmpty(); }
  }

  public static Result merge(JsonObject base, JsonObject local, JsonObject incoming) {
    Objects.requireNonNull(base, "base");
    Objects.requireNonNull(local, "local");
    Objects.requireNonNull(incoming, "incoming");
    List<String> conflicts = new ArrayList<>();
    JsonElement merged = mergeValue(base, local, incoming, "", conflicts);
    return new Result(merged.getAsJsonObject(), conflicts);
  }

  // Java null is a missing property; JsonNull is an explicitly present null.
  private static JsonElement mergeValue(JsonElement base, JsonElement local, JsonElement incoming,
                                        String path, List<String> conflicts) {
    if (Objects.equals(local, base)) return incoming;
    if (Objects.equals(incoming, base) || Objects.equals(local, incoming)) return local;

    if (local != null && local.isJsonObject() && incoming != null && incoming.isJsonObject()
        && (base == null || base.isJsonObject())) {
      JsonObject baseObject = base == null ? null : base.getAsJsonObject();
      JsonObject localObject = local.getAsJsonObject();
      JsonObject incomingObject = incoming.getAsJsonObject();
      JsonObject combined = new JsonObject();
      Set<String> keys = new LinkedHashSet<>();
      if (baseObject != null) keys.addAll(baseObject.keySet());
      keys.addAll(localObject.keySet());
      keys.addAll(incomingObject.keySet());
      for (String key : keys) {
        JsonElement value = mergeValue(baseObject == null ? null : baseObject.get(key), localObject.get(key),
                                      incomingObject.get(key), path + "/" + escape(key), conflicts);
        if (value != null) combined.add(key, value);
      }
      return combined;
    }

    if (path.equals("/cells") && base != null && base.isJsonArray()
        && local != null && local.isJsonArray() && incoming != null && incoming.isJsonArray()
        && sameCellIdentities(base.getAsJsonArray(), local.getAsJsonArray(), incoming.getAsJsonArray())) {
      JsonArray combined = new JsonArray();
      JsonArray baseCells = base.getAsJsonArray();
      JsonArray localCells = local.getAsJsonArray();
      JsonArray incomingCells = incoming.getAsJsonArray();
      for (int index = 0; index < baseCells.size(); index++) {
        combined.add(mergeValue(baseCells.get(index), localCells.get(index), incomingCells.get(index),
                                path + "/" + index, conflicts));
      }
      return combined;
    }

    // Arrays other than the notebook's stable-identity cells array are atomic.
    // A removal versus an edit also conflicts here and retains local absence.
    conflicts.add(path.isEmpty() ? "/" : path);
    return local;
  }

  private static boolean sameCellIdentities(JsonArray base, JsonArray local, JsonArray incoming) {
    if (base.size() != local.size() || base.size() != incoming.size()) return false;
    Set<String> seen = new HashSet<>();
    for (int index = 0; index < base.size(); index++) {
      String id = cellId(base.get(index));
      if (id == null || !seen.add(id) || !id.equals(cellId(local.get(index))) || !id.equals(cellId(incoming.get(index)))) return false;
    }
    return true;
  }

  private static String cellId(JsonElement cell) {
    if (!cell.isJsonObject()) return null;
    JsonElement id = cell.getAsJsonObject().get("id");
    if (id == null || !id.isJsonPrimitive() || !id.getAsJsonPrimitive().isString()) return null;
    String text = id.getAsString();
    return text.isBlank() ? null : text;
  }

  private static String escape(String key) { return key.replace("~", "~0").replace("/", "~1"); }
}
