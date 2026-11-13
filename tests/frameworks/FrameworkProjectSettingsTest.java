package dev.openpycharm.frameworks;

import com.intellij.openapi.module.Module;
import com.intellij.openapi.util.Key;
import com.intellij.openapi.util.UserDataHolderBase;
import com.jetbrains.python.newProjectWizard.PyV3BaseProjectSettings;
import com.jetbrains.python.sdk.add.v2.PySdkCreator;
import java.lang.reflect.Proxy;

/** Standalone request-isolation checks; no application, project, filesystem or GUI is created. */
public final class FrameworkProjectSettingsTest {
  private static int checks;

  private FrameworkProjectSettingsTest() { }

  public static void main(String[] args) {
    FrameworkProjectSettings settings = new FrameworkProjectSettings(FrameworkKind.DJANGO);
    Module first = module("first");
    Module second = module("second");

    require(!settings.consumeInstallChoice(first), "A direct callback must default to no installation");
    settings.setInstallDependencies(false);
    settings.captureInstallChoice(first);
    settings.setInstallDependencies(true);
    settings.captureInstallChoice(second);
    settings.setInstallDependencies(false);
    require(!settings.consumeInstallChoice(first), "First request lost its explicit opt-out");
    require(settings.consumeInstallChoice(second), "Second request lost its explicit opt-in");

    settings.setInstallDependencies(true);
    require(settings.consumeInstallChoice(first), "Consumed opt-out remained on the first module");
    settings.setInstallDependencies(false);
    require(!settings.consumeInstallChoice(second), "Consumed opt-in remained on the second module");

    settings.setInstallDependencies(true);
    settings.captureInstallChoice(first);
    settings.setInstallDependencies(false);
    require(settings.consumeInstallChoice(first), "A later capture reused the previously consumed opt-out");
    require(!settings.consumeInstallChoice(first), "Later consumption did not clear the captured value");

    settings.setInstallDependencies(false);
    settings.captureInstallChoice(first);
    settings.setInstallDependencies(true);
    settings.captureInstallChoice(first);
    settings.setInstallDependencies(false);
    require(settings.consumeInstallChoice(first), "A new capture did not replace the pending value");

    // Reverse consumption order and UI value to exercise both false snapshots
    // and true snapshots independently from the shared wizard's current state.
    settings.setInstallDependencies(true);
    settings.captureInstallChoice(first);
    settings.setInstallDependencies(false);
    settings.captureInstallChoice(second);
    settings.setInstallDependencies(true);
    require(!settings.consumeInstallChoice(second), "False snapshot fell through to the current true UI value");
    settings.setInstallDependencies(false);
    require(settings.consumeInstallChoice(first), "True snapshot fell through to the current false UI value");
    require(!settings.consumeInstallChoice(first), "Direct callback fallback did not use the current setting");
    settings.setInstallDependencies(true);
    require(settings.consumeInstallChoice(second), "Direct callback fallback ignored a current opt-in");

    PySdkCreator firstCreator = (PySdkCreator)Proxy.newProxyInstance(PySdkCreator.class.getClassLoader(),
        new Class<?>[]{PySdkCreator.class}, (proxy, method, arguments) -> { throw new AssertionError("A snapshot must not create an SDK"); });
    PySdkCreator secondCreator = (PySdkCreator)Proxy.newProxyInstance(PySdkCreator.class.getClassLoader(),
        new Class<?>[]{PySdkCreator.class}, (proxy, method, arguments) -> { throw new AssertionError("A snapshot must not create an SDK"); });
    PyV3BaseProjectSettings shared = new PyV3BaseProjectSettings(false);
    shared.setSdkCreator(firstCreator);
    PyV3BaseProjectSettings firstRequest = FrameworkProjectGenerator.snapshotBaseSettings(shared);
    shared.setSdkCreator(secondCreator);
    shared.setCreateGitRepository(true);
    PyV3BaseProjectSettings secondRequest = FrameworkProjectGenerator.snapshotBaseSettings(shared);
    require(firstRequest != shared && secondRequest != shared && firstRequest != secondRequest, "Native SDK requests share mutable settings");
    require(firstRequest.getSdkCreator() == firstCreator, "Another wizard replaced the first selected SDK creator");
    require(secondRequest.getSdkCreator() == secondCreator, "The second request lost its selected SDK creator");
    require(!firstRequest.getCreateGitRepository() && secondRequest.getCreateGitRepository(), "Another wizard changed the native Git creation choice");

    System.out.println("{\"status\":\"pass\",\"scope\":\"per-module dependency opt-in request isolation\",\"checks\":" + checks + "}");
  }

  @SuppressWarnings({"rawtypes", "unchecked"})
  private static Module module(String name) {
    UserDataHolderBase data = new UserDataHolderBase();
    return (Module)Proxy.newProxyInstance(Module.class.getClassLoader(), new Class<?>[]{Module.class}, (proxy, method, args) -> {
      return switch (method.getName()) {
        case "getUserData" -> data.getUserData((Key)args[0]);
        case "putUserData" -> { data.putUserData((Key)args[0], args[1]); yield null; }
        case "getName" -> name;
        case "isDisposed" -> false;
        case "equals" -> proxy == args[0];
        case "hashCode" -> System.identityHashCode(proxy);
        case "toString" -> "FrameworkSettingsTestModule(" + name + ")";
        default -> throw new AssertionError("Unexpected module access during request capture: " + method);
      };
    });
  }

  private static void require(boolean condition, String message) {
    checks++;
    if (!condition) throw new AssertionError(message);
  }
}
