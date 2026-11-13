package dev.openpycharm.frontend;

import java.util.Optional;

/** Pure memory scope checks. A default-off M0 can only target its compiled owned fixture parent. */
public final class FrontendFixtureScope {
  public record Configuration(String fixture, String nonce, String receipt, String receiptSha256) {}

  private FrontendFixtureScope() {}

  public static Optional<Configuration> evaluate(boolean enabled, String fixtureParent, String cacheParent,
      String projectBase, String filePath, String fixture, String nonce, String receipt, String receiptSha256) {
    if (!enabled || !absolute(fixtureParent) || !absolute(cacheParent) || !absolute(projectBase)
        || !absolute(filePath) || !absolute(fixture) || !absolute(receipt)
        || nonce == null || !nonce.matches("[0-9a-f]{32}")
        || receiptSha256 == null || !receiptSha256.matches("[0-9a-f]{64}")) return Optional.empty();
    if (!fixture.equals(fixtureParent + "/fixture-" + nonce) || !projectBase.equals(fixture)
        || !filePath.startsWith(fixture + "/") || !receipt.startsWith(cacheParent + "/")
        || !receipt.endsWith("/frontend-tools.json") || languageId(filePath) == null) return Optional.empty();
    return Optional.of(new Configuration(fixture, nonce, receipt, receiptSha256));
  }

  public static String languageId(String path) {
    if (path == null) return null;
    if (path.endsWith(".tsx")) return "typescriptreact";
    if (path.endsWith(".jsx")) return "javascriptreact";
    if (path.endsWith(".ts")) return "typescript";
    if (path.endsWith(".js")) return "javascript";
    return null;
  }

  private static boolean absolute(String value) {
    if (value == null || value.isEmpty() || !(value.startsWith("/") || value.matches("[A-Za-z]:/.*"))
        || value.endsWith("/") || value.contains("//") || value.contains("/./") || value.contains("/../")
        || value.endsWith("/..") || value.endsWith("/.") || value.indexOf('\\') >= 0) return false;
    for (int index = 0; index < value.length(); index++) {
      char c = value.charAt(index);
      if (c < 32 || c == 127 || c == ':' && index != 1) return false;
    }
    return true;
  }
}
