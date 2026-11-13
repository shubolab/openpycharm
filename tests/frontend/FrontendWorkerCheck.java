package dev.openpycharm.frontend;

/** Actual pinned cache authentication on a helper JVM worker, never an IDE or Node process. */
public final class FrontendWorkerCheck {
  public static void main(String[] args) throws Exception {
    if (args.length != 4) throw new IllegalArgumentException("Supply owned fixture/nonce/receipt/hash");
    var configuration = new FrontendFixtureScope.Configuration(args[0],args[1],args[2],args[3]);
    var runtime = FrontendRuntime.authenticate(configuration);
    var environment = FrontendRuntime.environment(runtime);
    if (!environment.get("HOME").startsWith(args[0]+"/") || !environment.get("NODE_OPTIONS").isEmpty()
        || environment.containsKey("GITHUB_TOKEN") || environment.containsKey("NPM_TOKEN") || environment.containsKey("SSH_AUTH_SOCK"))
      throw new AssertionError("Worker environment leaked external credentials/options");
    try {
      FrontendRuntime.authenticate(new FrontendFixtureScope.Configuration(args[0],args[1],args[2],"0".repeat(64)));
      throw new AssertionError("Changed receipt activation was accepted");
    } catch (java.io.IOException expected) { }
    System.out.println("{\"status\":\"pass\",\"actualPinnedCacheAuthenticated\":true,\"changedReceiptActivationRejected\":true,"+
        "\"credentialIsolation\":true,\"nativeIdeStarted\":false,\"languageServerStarted\":false}");
  }
}
