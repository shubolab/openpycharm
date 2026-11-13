package dev.openpycharm.frameworks;

import com.intellij.util.execution.ParametersListUtil;
import java.nio.file.Path;
import java.util.List;

/** Independent local development-server presets, expressed as argument lists. */
public enum FrameworkKind {
  DJANGO("OpenPyCharmDjango", "Django", false, "manage.py",
      List.of("runserver", "127.0.0.1:8000", "--noreload")),
  FLASK("OpenPyCharmFlask", "Flask", true, "flask",
      List.of("--app", "app", "run", "--host", "127.0.0.1", "--port", "5000", "--no-reload", "--no-debugger")),
  FASTAPI("OpenPyCharmFastAPI", "FastAPI", true, "uvicorn",
      List.of("app:app", "--host", "127.0.0.1", "--port", "8000"));

  private final String id;
  private final String displayName;
  private final boolean moduleMode;
  private final String entryPoint;
  private final List<String> arguments;

  FrameworkKind(String id, String displayName, boolean moduleMode, String entryPoint, List<String> arguments) {
    this.id = id;
    this.displayName = displayName;
    this.moduleMode = moduleMode;
    this.entryPoint = entryPoint;
    this.arguments = arguments;
  }

  public String id() { return id; }
  public String displayName() { return displayName; }
  public boolean moduleMode() { return moduleMode; }
  public List<String> arguments() { return arguments; }

  public String scriptName(String projectDirectory) {
    return moduleMode || projectDirectory == null || projectDirectory.isBlank()
        ? entryPoint : Path.of(projectDirectory).resolve(entryPoint).toString();
  }

  public static String encodeArguments(List<String> arguments) {
    for (String argument : arguments) {
      if (argument == null || argument.indexOf('\0') >= 0 || argument.indexOf('\r') >= 0 || argument.indexOf('\n') >= 0) {
        throw new IllegalArgumentException("A process argument cannot contain NUL or a line break");
      }
    }
    // PythonCore's native configuration parser consumes this representation.
    // No shell, command string execution, executable discovery or user code runs here.
    return ParametersListUtil.join(arguments);
  }
}
