/* Read every probe entry with the actual product's IntelliJ ZIP reader. */
import com.intellij.util.lang.ImmutableZipFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.zip.ZipFile;

public final class VerifyProbeArchive {
  public static void main(String[] arguments) throws Exception {
    if (arguments.length != 1) throw new IllegalArgumentException("Supply one absolute plugin JAR path");
    Path path = Path.of(arguments[0]);
    if (!path.isAbsolute() || !Files.isRegularFile(path)) throw new IllegalArgumentException("Expected a regular absolute JAR path");
    int count = 0;
    String reader;
    HashSet<String> names = new HashSet<>();
    try (var standard = new ZipFile(path.toFile()); var nativeZip = ImmutableZipFile.load(path)) {
      reader = nativeZip.getClass().getSimpleName();
      var entries = standard.entries();
      while (entries.hasMoreElements()) {
        var entry = entries.nextElement();
        if (!names.add(entry.getName())) throw new IllegalStateException("Duplicate entry");
        if (entry.isDirectory()) continue;
        var resource = nativeZip.getResource(entry.getName());
        if (resource == null) throw new IllegalStateException("Missing native-reader resource " + entry.getName());
        try (var input = standard.getInputStream(entry)) {
          if (!Arrays.equals(input.readAllBytes(), resource.getData())) throw new IllegalStateException("Native-reader payload mismatch");
        }
        count++;
      }
    }
    if (!names.contains("META-INF/plugin.xml") || !names.contains("dev/openpycharm/probe/DiagnosticProbe.class")) {
      throw new IllegalStateException("Probe descriptor or implementation missing");
    }
    String sha256 = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
    System.out.println("{\"status\":\"pass\",\"reader\":\"" + reader + "\",\"entryCount\":" + count + ",\"closed\":true,\"sha256\":\"" + sha256 + "\"}");
  }
}
