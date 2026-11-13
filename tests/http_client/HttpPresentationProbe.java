package dev.openpycharm.http;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

/** Pure presentation/raw-save checks; no IDE window, HTTP server or chooser is started. */
public final class HttpPresentationProbe {
  public static void main(String[] arguments) throws Exception {
    Path directory = Path.of(arguments[0]);
    byte[] raw = "{\"message\":\"你好😀\",\"amount\":1.00}".getBytes(StandardCharsets.UTF_8);
    var response = new HttpRequestResponse(201, Map.of("content-type", List.of("application/json; charset=UTF-8")), raw, 42);
    var display = HttpResponsePresentation.Companion.prepare(response);
    if (!display.getFormatted() || !display.getBodyText().contains("\n")) throw new AssertionError("JSON response was not prepared for the native editor");
    if (!display.getHeadersText().contains("HTTP 201") || !display.getHeadersText().contains("42 ms")) throw new AssertionError("Status/timing missing");
    if (!Arrays.equals(response.getBody(), raw)) throw new AssertionError("Presentation changed response bytes");
    var binary = HttpResponsePresentation.Companion.prepare(new HttpRequestResponse(200, Map.of("content-type", List.of("image/png")), new byte[]{0, -1, 1}, 0));
    if (!binary.getBinary() || !binary.getBodyText().contains("Binary response")) throw new AssertionError("Binary bytes rendered as text");
    Path target = directory.resolve("saved-response.bin");
    Files.writeString(target, "previous file");
    try {
      HttpResponseFiles.INSTANCE.save(target, raw);
      if (!Arrays.equals(Files.readAllBytes(target), raw)) throw new AssertionError("Raw response save changed bytes");
      try (var files = Files.list(directory)) {
        if (files.anyMatch(path -> path.getFileName().toString().startsWith(".http-response-"))) throw new AssertionError("Temporary save file leaked");
      }
    } finally { Files.deleteIfExists(target); }
    System.out.println("{\"status\":\"pass\",\"nativeEditorPresentationPrepared\":true,\"binaryPreserved\":true,\"atomicRawSaveBytesMatch\":true,\"temporarySaveFilesCleaned\":true}");
  }
}
