package dev.openpycharm.frontend;

import java.nio.file.Path;
import javax.swing.SwingUtilities;

/** Authenticate a real prepared product bundle on a helper JVM, without executing its tools. */
public final class FrontendProductBundleCheck {
  public static void main(String[] args) throws Exception {
    if (args.length != 4) throw new IllegalArgumentException("Supply plugin root, owned system/project directories, and native target");
    var layout = FrontendBundledRuntime.layout(Path.of(args[0]), Path.of(args[1]), "owned_auth_control", Path.of(args[2]), args[3]);
    long start = System.nanoTime();
    FrontendBundledRuntime.authenticate(layout, () -> true);
    var command = FrontendBundledRuntime.command(layout);
    if (!command.getExePath().equals(layout.node().toString()) || command.getEnvironment().containsKey("GITHUB_TOKEN")
        || !command.getEnvironment().get("HOME").startsWith(Path.of(args[1]).toString())) throw new AssertionError("Bundle command/state identity differs");
    SwingUtilities.invokeAndWait(() -> {
      try { FrontendBundledRuntime.authenticate(layout, () -> true); throw new AssertionError("EDT authentication accepted"); }
      catch (java.io.IOException expected) { }
    });
    System.out.println("{\"status\":\"pass\",\"fullPinned191PayloadAuthenticated\":true,\"edtAuthenticationRejected\":true,\"milliseconds\":"
        + (System.nanoTime()-start)/1_000_000 + ",\"nativeIdeStarted\":false,\"nodeStarted\":false}");
  }
}
