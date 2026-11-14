package dev.openpycharm.notebooks;

import com.google.gson.JsonObject;
import java.util.*;

/** Session-only display_id bindings; transient identifiers never enter saved nbformat. */
public final class NotebookDisplayState<K> {
  private record Reference<K>(K key, JsonObject output) { }
  private final Map<String, List<Reference<K>>> displays = new HashMap<>();
  private static String id(JsonObject content) {
    return content.has("transient") && content.get("transient").isJsonObject()
        ? NotebookKernelSession.string(content.getAsJsonObject("transient"), "display_id") : "";
  }
  public void capture(K key, JsonObject output, JsonObject content) {
    String id = id(content);
    if (!id.isEmpty()) displays.computeIfAbsent(id, ignored -> new ArrayList<>()).add(new Reference<>(key, output));
  }
  public Set<K> update(JsonObject content) {
    Set<K> changed = new LinkedHashSet<>();
    for (Reference<K> reference : displays.getOrDefault(id(content), List.of())) {
      if (content.has("data")) reference.output().add("data", content.get("data").deepCopy());
      if (content.has("metadata")) reference.output().add("metadata", content.get("metadata").deepCopy());
      changed.add(reference.key());
    }
    return changed;
  }
  public void clear(K key) {
    displays.values().forEach(references -> references.removeIf(reference -> Objects.equals(reference.key(), key)));
    displays.values().removeIf(List::isEmpty);
  }
  public void clear() { displays.clear(); }
}
