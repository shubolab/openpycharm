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
    if (exactEquals(local, base)) return incoming;
    if (exactEquals(incoming, base) || exactEquals(local, incoming)) return local;

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

  /** Gson equality can compare lazily parsed numbers through double. Every
   * container must recurse here too, otherwise a containing object/array can
   * still hide an adjacent large integer or a high-precision decimal change.
   */
  static boolean exactEquals(JsonElement left, JsonElement right) {
    if (left == right) return true;
    if (left == null || right == null) return false;
    if (left.isJsonNull() || right.isJsonNull()) return left.isJsonNull() && right.isJsonNull();
    if (left.isJsonObject() && right.isJsonObject()) {
      JsonObject a = left.getAsJsonObject(), b = right.getAsJsonObject();
      if (a.size() != b.size()) return false;
      for (String key : a.keySet()) if (!b.has(key) || !exactEquals(a.get(key), b.get(key))) return false;
      return true;
    }
    if (left.isJsonArray() && right.isJsonArray()) {
      JsonArray a = left.getAsJsonArray(), b = right.getAsJsonArray();
      if (a.size() != b.size()) return false;
      for (int i = 0; i < a.size(); i++) if (!exactEquals(a.get(i), b.get(i))) return false;
      return true;
    }
    if (!left.isJsonPrimitive() || !right.isJsonPrimitive()) return false;
    var a = left.getAsJsonPrimitive(); var b = right.getAsJsonPrimitive();
    if (a.isNumber() && b.isNumber()) {
      String first = a.getAsString(), second = b.getAsString();
      if (first.equals(second)) return true;
      Decimal x = decimal(first), y = decimal(second);
      return x != null && x.equals(y);
    }
    if (a.isString() && b.isString()) return a.getAsString().equals(b.getAsString());
    return a.isBoolean() && b.isBoolean() && a.getAsBoolean() == b.getAsBoolean();
  }

  private record Decimal(boolean negative, String digits, String exponent) { }

  /** Exact finite decimal form without expanding exponents or converting to
   * binary floating point. Exponent arithmetic is linear string arithmetic,
   * including exponents outside BigDecimal's integer scale range.
   */
  private static Decimal decimal(String value) {
    if (value.isEmpty()) return null;
    boolean negative = value.charAt(0) == '-'; int start = negative ? 1 : 0;
    int end = start;
    while (end < value.length() && value.charAt(end) != 'e' && value.charAt(end) != 'E') end++;
    int dot = value.indexOf('.', start);
    if (dot < 0 || dot >= end) dot = end;
    if (dot == start || dot < end && dot + 1 == end || dot - start > 1 && value.charAt(start) == '0') return null;
    StringBuilder digits = new StringBuilder(end - start);
    for (int i = start; i < end; i++) {
      char c = value.charAt(i);
      if (i == dot) continue;
      if (c < '0' || c > '9') return null;
      digits.append(c);
    }
    if (digits.isEmpty()) return null;
    String exponent = "0";
    if (end < value.length()) {
      int at = end + 1; boolean minus = at < value.length() && value.charAt(at) == '-';
      if (at < value.length() && (value.charAt(at) == '+' || minus)) at++;
      if (at == value.length()) return null;
      for (int i = at; i < value.length(); i++) if (value.charAt(i) < '0' || value.charAt(i) > '9') return null;
      String magnitude = trimZeros(value.substring(at));
      exponent = minus && !magnitude.equals("0") ? "-" + magnitude : magnitude;
    }
    int first = 0, last = digits.length();
    while (first < last && digits.charAt(first) == '0') first++;
    if (first == last) return new Decimal(false, "0", "0");
    while (last > first && digits.charAt(last - 1) == '0') last--;
    int fraction = dot == end ? 0 : end - dot - 1;
    int shift = digits.length() - last - fraction;
    return new Decimal(negative, digits.substring(first, last), shiftExponent(exponent, shift));
  }

  private static String trimZeros(String value) {
    int first = 0;
    while (first + 1 < value.length() && value.charAt(first) == '0') first++;
    return value.substring(first);
  }
  private static String shiftExponent(String value, int shift) {
    if (shift == 0) return value;
    boolean aNegative = value.charAt(0) == '-', bNegative = shift < 0;
    String a = aNegative ? value.substring(1) : value, b = Long.toString(Math.abs((long)shift));
    if (aNegative == bNegative) {
      String sum = magnitude(a, b, false);
      return aNegative ? "-" + sum : sum;
    }
    int order = a.length() == b.length() ? a.compareTo(b) : Integer.compare(a.length(), b.length());
    if (order == 0) return "0";
    String difference = order > 0 ? magnitude(a, b, true) : magnitude(b, a, true);
    return (order > 0 ? aNegative : bNegative) ? "-" + difference : difference;
  }
  /** Decimal magnitude addition/subtraction; subtraction requires a > b. */
  private static String magnitude(String a, String b, boolean subtract) {
    StringBuilder result = new StringBuilder(Math.max(a.length(), b.length()) + 1);
    int left = a.length() - 1, right = b.length() - 1, carry = 0;
    while (left >= 0 || right >= 0) {
      int x = left >= 0 ? a.charAt(left--) - '0' : 0, y = right >= 0 ? b.charAt(right--) - '0' : 0;
      int digit = subtract ? x - y - carry : x + y + carry;
      carry = subtract ? digit < 0 ? 1 : 0 : digit / 10;
      if (subtract && digit < 0) digit += 10;
      result.append((char)('0' + digit % 10));
    }
    if (!subtract && carry != 0) result.append((char)('0' + carry));
    return trimZeros(result.reverse().toString());
  }
}
