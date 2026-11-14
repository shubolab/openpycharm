// Adapted from this repository's Apache-2.0 frontend archive-reader control.
import com.intellij.util.lang.ImmutableZipFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.zip.ZipFile;

/** Read every product entry through the actual IntelliJ and JDK readers. */
public final class VerifyFrontendProductArchive {
  public static void main(String[] arguments) throws Exception {
    if (arguments.length != 1) throw new IllegalArgumentException("Supply one absolute frontend product JAR");
    Path path = Path.of(arguments[0]);
    if (!path.isAbsolute() || !Files.isRegularFile(path)) throw new IllegalArgumentException("Expected an absolute regular JAR");
    var names = new HashSet<String>(); int count = 0; String reader;
    try (var jdk = new ZipFile(path.toFile()); var platform = ImmutableZipFile.load(path)) {
      reader = platform.getClass().getSimpleName(); var entries = jdk.entries();
      while (entries.hasMoreElements()) {
        var entry = entries.nextElement();
        if (!names.add(entry.getName())) throw new IllegalStateException("Duplicate product entry");
        if (entry.isDirectory()) continue;
        var resource = platform.getResource(entry.getName());
        if (resource == null) throw new IllegalStateException("Missing platform-reader entry " + entry.getName());
        try (var input = jdk.getInputStream(entry)) {
          if (!Arrays.equals(input.readAllBytes(), resource.getData())) throw new IllegalStateException("Reader payload mismatch");
        }
        count++;
      }
    }
    for (String name : new String[]{"FrontendNativeProcess", "FrontendBoundedOutput", "FrontendProcessLifetime",
        "FrontendProductLspProvider", "FrontendBundledRuntime", "FrontendProductScope", "FrontendProjectSettings",
        "FrontendSettingsLifecycle", "FrontendProjectConfigurable"}) {
      if (!names.contains("dev/openpycharm/frontend/" + name + ".class")) throw new IllegalStateException("Missing product class " + name);
    }
    for (String name : names) for (String forbidden : new String[]{"FrontendLspProvider", "FrontendRuntime", "FrontendFixtureScope", "FrontendBuildScope"}) {
      String prefix = "dev/openpycharm/frontend/" + forbidden;
      if (name.equals(prefix + ".class") || name.startsWith(prefix + "$")) throw new IllegalStateException("Fixture-only class in product");
    }
    for (String required : new String[]{"META-INF/plugin.xml", "META-INF/LICENSE", "META-INF/NOTICE",
        "META-INF/frontend-tools.lock.json", "META-INF/frontend-runtime-macos-arm64.json", "META-INF/frontend-runtime-windows-x64.json"}) {
      if (!names.contains(required)) throw new IllegalStateException("Missing product resource " + required);
    }
    String digest = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
    System.out.println("{\"status\":\"pass\",\"reader\":\"" + reader + "\",\"verifiedEntries\":" + count + ",\"closed\":true,\"sha256\":\"" + digest + "\"}");
  }
}
