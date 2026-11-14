package dev.openpycharm.frontend;

import java.nio.file.Path;
import java.util.Locale;

/** Pure path/language decisions; no disk access in native file-open callbacks. */
final class FrontendProductScope {
  private FrontendProductScope() {}

  static String languageId(String name) {
    if (name == null) return null;
    int dot = name.lastIndexOf('.');
    if (dot < 0) return null;
    return switch (name.substring(dot).toLowerCase(Locale.ROOT)) {
      case ".js", ".mjs", ".cjs" -> "javascript";
      case ".jsx" -> "javascriptreact";
      case ".ts", ".mts", ".cts" -> "typescript";
      case ".tsx" -> "typescriptreact";
      default -> null;
    };
  }

  static String target(String os, String arch) {
    String cpu = arch.toLowerCase(Locale.ROOT);
    if (os.startsWith("Mac") && (cpu.equals("aarch64") || cpu.equals("arm64"))) return "macos-arm64";
    if (os.startsWith("Windows") && (cpu.equals("amd64") || cpu.equals("x86_64"))) return "windows-x64";
    return null;
  }

  static String locationComponent(String value) {
    if (value == null || value.isBlank() || value.length() > 200 || value.equals(".") || value.equals("..")
        || value.chars().anyMatch(c -> c < 32 || c == 127 || c == '/' || c == '\\' || c == ':'))
      throw new IllegalArgumentException("Invalid frontend project location hash");
    return value;
  }

  static Path absolute(Path path) {
    if (path == null || !path.isAbsolute() || !path.normalize().equals(path))
      throw new IllegalArgumentException("Expected a normalized absolute frontend path");
    return path;
  }
}
