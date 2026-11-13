import java.lang.reflect.Field;
import java.lang.reflect.Method;

/** Build-time control; reads the actual repaired Holder without an application or CEF. */
public final class HolderColdLoadProbe {
  public static void main(String[] arguments) throws Exception {
    Class<?> unsafeClass = Class.forName("jdk.internal.misc.Unsafe");
    Field field = unsafeClass.getDeclaredField("theUnsafe");
    field.setAccessible(true);
    Object unsafe = field.get(null);
    Method shouldInitialize = unsafeClass.getMethod("shouldBeInitialized", Class.class);
    ClassLoader loader = HolderColdLoadProbe.class.getClassLoader();
    Class<?> outer = Class.forName("com.intellij.ui.jcef.JBCefApp", false, loader);
    require((boolean)shouldInitialize.invoke(unsafe, outer), "Outer class was already initialized");
    Class<?> holder = Class.forName("com.intellij.ui.jcef.JBCefApp$Holder", true, loader);
    require((boolean)shouldInitialize.invoke(unsafe, outer), "Holder initialized JCEF/application state");
    require(read(holder, "INSTANCE") == null, "Holder constructed JCEF during class initialization");
    require(Boolean.FALSE.equals(read(holder, "initialized")), "Cold holder attempted construction");
    require(read(holder, "initializationFailure") == null, "Cold holder contains an unexpected failure");
    System.out.println("{\"status\":\"pass\",\"actualPatchedHolderColdLoad\":true,\"outerJcefClassUninitialized\":true,\"applicationStarted\":false}");
  }

  private static Object read(Class<?> type, String name) throws Exception {
    Field field = type.getDeclaredField(name);
    field.setAccessible(true);
    return field.get(null);
  }

  private static void require(boolean condition, String message) {
    if (!condition) throw new AssertionError(message);
  }
}
