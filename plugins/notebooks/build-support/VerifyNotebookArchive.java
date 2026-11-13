import com.intellij.util.lang.ImmutableZipFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.zip.ZipFile;

/** Compares all independently emitted payloads through JDK and IntelliJ readers. */
public final class VerifyNotebookArchive {
  public static void main(String[] arguments) throws Exception {
    if (arguments.length != 1) throw new IllegalArgumentException("Supply one absolute notebook plugin JAR");
    Path path = Path.of(arguments[0]);
    if (!path.isAbsolute() || !Files.isRegularFile(path)) throw new IllegalArgumentException("Expected an absolute regular JAR");
    int count = 0;
    HashSet<String> names = new HashSet<>();
    String reader;
    try (var jdk = new ZipFile(path.toFile()); var platform = ImmutableZipFile.load(path)) {
      reader = platform.getClass().getSimpleName();
      var entries = jdk.entries();
      while (entries.hasMoreElements()) {
        var entry = entries.nextElement();
        if (!names.add(entry.getName())) throw new IllegalStateException("Duplicate notebook entry");
        if (entry.isDirectory()) continue;
        var resource = platform.getResource(entry.getName());
        if (resource == null) throw new IllegalStateException("Missing platform-reader entry " + entry.getName());
        try (var stream = jdk.getInputStream(entry)) {
          if (!Arrays.equals(stream.readAllBytes(), resource.getData())) throw new IllegalStateException("Reader payload mismatch");
        }
        count++;
      }
    }
    for (String required : new String[]{"META-INF/plugin.xml", "META-INF/LICENSE", "META-INF/NOTICE",
        "dev/openpycharm/notebooks/NotebookFileEditor.class",
        "dev/openpycharm/notebooks/NotebookEditorProvider.class", "kernel_bridge.py", "kernel-requirements.txt"}) {
      if (!names.contains(required)) throw new IllegalStateException("Missing required notebook resource " + required);
    }
    String digest = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
    System.out.println("{\"status\":\"pass\",\"reader\":\"" + reader + "\",\"verifiedEntries\":" + count + ",\"closed\":true,\"sha256\":\"" + digest + "\"}");
  }
}
