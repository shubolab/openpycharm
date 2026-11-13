/*
 * OpenPyCharm packaging helper. Uses IntelliJ's public Apache-2.0 runtime
 * repository serializer (source commit 456919a9624bae72ac12efafc35d2b916cb0c5c5).
 * Based on the verified module-repository workflow in shubolab/opengoland.
 */
import com.intellij.platform.runtime.repository.RuntimeModuleId;
import com.intellij.platform.runtime.repository.serialization.RawRuntimeModuleDescriptor;
import com.intellij.platform.runtime.repository.serialization.RawRuntimeModuleRepositoryData;
import com.intellij.platform.runtime.repository.serialization.RuntimeModuleRepositorySerialization;
import java.io.DataInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

public final class LocalModuleRepository {
  record Descriptor(List<String> resources, List<String> dependencies) {}
  static Map<String, Descriptor> graph(RawRuntimeModuleRepositoryData data) {
    Map<String, Descriptor> result = new TreeMap<>();
    for (RuntimeModuleId id : data.getAllModuleIds()) {
      RawRuntimeModuleDescriptor item = Objects.requireNonNull(data.findDescriptor(id));
      result.put(id.getStringId(), new Descriptor(List.copyOf(item.getResourcePaths()),
        item.getDependencyIds().stream().map(RuntimeModuleId::getStringId).toList()));
    }
    return result;
  }
  public static void main(String[] args) throws Exception {
    if (args.length != 5) throw new IllegalArgumentException("input.dat filtered.jar output.dat removed-ids.txt removed-edges.txt");
    Path input = Path.of(args[0]), filteredJar = Path.of(args[1]), output = Path.of(args[2]);
    Set<String> removed = new HashSet<>(Files.readAllLines(Path.of(args[3])));
    Set<String> edges = new HashSet<>(Files.readAllLines(Path.of(args[4])));
    var before = graph(RuntimeModuleRepositorySerialization.loadFromCompactFile(input));
    Map<String, Descriptor> expected = new TreeMap<>();
    for (var entry : before.entrySet()) {
      if (removed.contains(entry.getKey())) continue;
      expected.put(entry.getKey(), new Descriptor(entry.getValue().resources,
        entry.getValue().dependencies.stream().filter(id -> !edges.contains(entry.getKey() + "\t" + id)).toList()));
    }
    var filtered = RuntimeModuleRepositorySerialization.loadFromJar(filteredJar);
    if (!expected.equals(graph(filtered))) throw new IllegalStateException("Filtered XML graph differs from declared removals");
    String bootstrap = "intellij.platform.bootstrap";
    var oldBootstrap = RuntimeModuleRepositorySerialization.loadBootstrapClasspath(input, bootstrap);
    if (!Arrays.equals(oldBootstrap, RuntimeModuleRepositorySerialization.loadBootstrapClasspath(filteredJar, bootstrap)))
      throw new IllegalStateException("Bootstrap classpath changed");
    int generator;
    try (var stream = new DataInputStream(Files.newInputStream(input))) {
      if (stream.readInt() != 2) throw new IllegalStateException("Unknown compact repository format");
      generator = stream.readInt();
    }
    List<RawRuntimeModuleDescriptor> descriptors = new ArrayList<>();
    for (RuntimeModuleId id : filtered.getAllModuleIds()) descriptors.add(Objects.requireNonNull(filtered.findDescriptor(id)));
    RuntimeModuleRepositorySerialization.saveToCompactFile(descriptors, bootstrap, output, generator);
    if (!expected.equals(graph(RuntimeModuleRepositorySerialization.loadFromCompactFile(output))))
      throw new IllegalStateException("Generated compact graph differs from XML");
    if (!Arrays.equals(oldBootstrap, RuntimeModuleRepositorySerialization.loadBootstrapClasspath(output, bootstrap)))
      throw new IllegalStateException("Generated compact bootstrap classpath changed");
    System.out.println("{\"graphsEqual\":true,\"bootstrapPreserved\":true,\"modulesBefore\":" + before.size()
      + ",\"modulesAfter\":" + expected.size() + "}");
  }
}
