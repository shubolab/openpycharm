package dev.openpycharm.frameworks;

import com.intellij.util.execution.ParametersListUtil;
import com.google.gson.Gson;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Standalone SDK-JVM checks; native config lifecycle is exercised separately in the IDE. */
public final class FrameworkCommandTest {
  private static void require(boolean condition, String message) {
    if (!condition) throw new AssertionError(message);
  }
  public static void main(String[] arguments) {
    String project = Path.of("example project 中文").toAbsolutePath().toString();
    require(!FrameworkKind.DJANGO.moduleMode(), "Django must run manage.py with the selected interpreter");
    require(FrameworkKind.DJANGO.scriptName(project).equals(Path.of(project, "manage.py").toString()), "Django path");
    require(FrameworkKind.DJANGO.arguments().contains("--noreload"), "Django reload is opt-in");
    require(FrameworkKind.FLASK.moduleMode() && FrameworkKind.FLASK.scriptName(project).equals("flask"), "Flask module");
    require(FrameworkKind.FLASK.arguments().contains("--no-debugger"), "No browser debugger in native IDE Debug");
    require(FrameworkKind.FLASK.arguments().contains("--no-reload"), "Flask reload is opt-in");
    require(FrameworkKind.FASTAPI.moduleMode() && FrameworkKind.FASTAPI.scriptName(project).equals("uvicorn"), "ASGI module");
    require(!FrameworkKind.FASTAPI.arguments().contains("--reload"), "ASGI reload is opt-in");
    List<String> literal = List.of("space value", "中文", "semi;colon", "$(touch SHOULD_NOT_RUN)", "&", "a\"b", "", "C:\\dir with space\\file");
    require(ParametersListUtil.parse(FrameworkKind.encodeArguments(literal)).equals(literal), "Argument boundaries must round-trip without shell interpretation");
    for (String invalid : List.of("a\nb", "a\rb", "a\0b")) {
      try { FrameworkKind.encodeArguments(List.of(invalid)); throw new AssertionError("Control character accepted"); }
      catch (IllegalArgumentException expected) { }
    }
    for (FrameworkKind kind : FrameworkKind.values()) {
      require(ParametersListUtil.parse(FrameworkKind.encodeArguments(kind.arguments())).equals(kind.arguments()), kind + " argument boundaries");
    }
    List<Map<String, Object>> commands = new ArrayList<>();
    for (FrameworkKind kind : FrameworkKind.values()) {
      Map<String, Object> command = new LinkedHashMap<>();
      command.put("framework", kind.name().toLowerCase(java.util.Locale.ROOT));
      command.put("moduleMode", kind.moduleMode());
      command.put("scriptName", kind.scriptName(null));
      command.put("arguments", kind.arguments());
      commands.add(command);
    }
    System.out.println(new Gson().toJson(Map.of("status", "pass", "frameworks", 3,
        "scope", "default commands and native argument codec", "commands", commands)));
  }
}
