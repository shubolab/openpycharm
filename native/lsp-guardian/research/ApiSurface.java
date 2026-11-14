import java.lang.reflect.*;
import java.util.*;
public final class ApiSurface {
  public static void main(String[] args) {
    String[] names={"com.intellij.execution.process.OSProcessHandler","com.intellij.execution.process.ProcessTreeKiller","com.intellij.execution.process.ProcessWrapper","com.intellij.execution.process.UnixProcessManager","com.intellij.execution.process.WinProcessManager","com.intellij.execution.configurations.GeneralCommandLine","com.sun.jna.platform.win32.Kernel32","com.sun.jna.platform.win32.WinBase$STARTUPINFOEX","com.sun.jna.platform.win32.WinNT$JOBOBJECT_EXTENDED_LIMIT_INFORMATION","com.pty4j.PtyProcessBuilder","com.pty4j.unix.PtyHelpers$OSFacade","com.pty4j.windows.conpty.WinEx","com.pty4j.windows.conpty.WinEx$STARTUPINFOEX","com.intellij.jna.JnaLoader"};
    for(String name:names)try {
      Class<?> c=Class.forName(name,false,ApiSurface.class.getClassLoader());System.out.println("CLASS "+name+" "+Modifier.toString(c.getModifiers()));
      if(name.endsWith("OSProcessHandler")||name.endsWith("GeneralCommandLine"))for(var ctor:c.getConstructors())System.out.println("CTOR "+ctor.toGenericString());
      for(var m:c.getMethods())if(m.getName().matches(".*(?:CreateProcess|JobObject|ProcThreadAttribute|CreatePipe|DuplicateHandle|HandleInformation|CloseHandle|ReadFile|WriteFile|ResumeThread|WaitForSingleObject|ProcessTimes|createProcess|startProcess|setConsole|start|setEnvironment|setDirectory|killpg|setpgid|setsid|killProcessTree|isLoaded|isLoadable|killRecursively).*"))System.out.println("METHOD "+m.toGenericString());
    } catch(Throwable e){System.out.println("MISSING "+name+" "+e.getClass().getName()+" "+e.getMessage());}
  }
}
