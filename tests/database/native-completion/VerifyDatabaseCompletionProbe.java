import com.intellij.util.lang.ImmutableZipFile;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.ZipFile;

/** Compare the probe's exact entries through real IntelliJ and JDK readers. */
public final class VerifyDatabaseCompletionProbe {
  public static void main(String[] args)throws Exception{
    Path file=Path.of(args[0]);Set<String> names=new HashSet<>();int count=0;String reader;
    try(var jdk=new ZipFile(file.toFile());var platform=ImmutableZipFile.load(file)){
      reader=platform.getClass().getSimpleName();var entries=jdk.entries();
      while(entries.hasMoreElements()){var entry=entries.nextElement();if(!names.add(entry.getName()))throw new IllegalStateException("Duplicate entry");if(entry.isDirectory())continue;var resource=platform.getResource(entry.getName());if(resource==null)throw new IllegalStateException("Missing platform entry");try(var stream=jdk.getInputStream(entry)){if(!Arrays.equals(stream.readAllBytes(),resource.getData()))throw new IllegalStateException("Reader mismatch");}count++;}
    }
    for(String required:List.of("META-INF/plugin.xml","dev/openpycharm/database/nativeprobe/DatabaseCompletionNativeProbe.class","dev/openpycharm/database/nativeprobe/DatabaseCompletionNativeProbe$BeforeObserver.class","dev/openpycharm/database/nativeprobe/DatabaseCompletionNativeProbe$AfterObserver.class"))if(!names.contains(required))throw new IllegalStateException("Missing "+required);
    for(String name:names)if(name.endsWith(".class")&&!name.startsWith("dev/openpycharm/database/nativeprobe/"))throw new IllegalStateException("Replacement production class forbidden");
    String hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(file)));
    System.out.println("{\"status\":\"pass\",\"reader\":\""+reader+"\",\"entries\":"+count+",\"closed\":true,\"sha256\":\""+hash+"\"}");
  }
}
