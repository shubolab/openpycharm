package dev.openpycharm.notebooks.saveprobe;

import com.google.gson.GsonBuilder;
import com.intellij.ide.AppLifecycleListener;
import com.intellij.ide.impl.OpenProjectTask;
import com.intellij.ide.plugins.PluginManagerCore;
import com.intellij.ide.trustedProjects.TrustedProjects;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.application.PathManager;
import com.intellij.openapi.application.WriteAction;
import com.intellij.openapi.extensions.PluginId;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.project.ex.ProjectManagerEx;
import com.intellij.openapi.util.Disposer;
import com.intellij.util.concurrency.AppExecutorUtil;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.TimeUnit;

/** Test-only normal IDE new-project lifecycle, restricted to one fresh generated fixture. */
public final class NotebookSaveOwnedProject implements AppLifecycleListener {
  static final String MODE="normal-ide-new-owned-project";
  private static final AtomicBoolean REQUESTED=new AtomicBoolean();
  private static final AtomicReference<Created> CREATED=new AtomicReference<>();
  private static final AtomicBoolean FAILED=new AtomicBoolean();
  private static final AtomicReference<String> STAGE=new AtomicReference<>("validating-owned-project");
  record Owned(Path root,Path project,Path fixture,Path profile,Path application,Path report,String hash) {}
  private record Created(Project project,Map<String,Object> evidence) {}
  @Override public void appStarted(){request();}
  @Override public void welcomeScreenDisplayed(){request();}
  private static String property(String key){return System.getProperty("openpycharm.notebook.save."+key);}
  private static void request(){
    if(!MODE.equals(property("mode"))||!REQUESTED.compareAndSet(false,true))return;
    // App callbacks schedule only; all path/hash/project construction work stays off EDT.
    AppExecutorUtil.getAppExecutorService().execute(NotebookSaveOwnedProject::createAndOpen);
  }
  static Owned validate(Path root,Path project,Path fixture,Path profile,Path application,Path report,String hash)throws Exception{
    root=canonicalDirectory(root);project=canonicalDirectory(project);profile=canonicalDirectory(profile);application=canonicalDirectory(application);
    fixture=fixture.toAbsolutePath().normalize();report=report.toAbsolutePath().normalize();
    require(project.equals(root.resolve("project"))&&profile.equals(root.resolve("profile")),"Exact owned project/profile paths required");
    require(fixture.equals(project.resolve("native-save.ipynb"))&&report.equals(root.resolve("native-report.json")),"Exact owned fixture/report paths required");
    require(!root.startsWith(application)&&!application.startsWith(root),"Owned workspace and application overlap");
    require(Files.isRegularFile(fixture,LinkOption.NOFOLLOW_LINKS)&&!Files.isSymbolicLink(fixture)&&fixture.toRealPath().equals(fixture),"Fixture must be a regular owned file without symlinks");
    require(Files.size(fixture)<=256*1024&&hash!=null&&hash.matches("[a-f0-9]{64}")&&hash.equals(hash(fixture)),"Generated fixture hash or byte bound differs");
    try(var entries=Files.list(project)){require(entries.toList().equals(List.of(fixture)),"Only the generated fixture may precede normal newProject creation");}
    return new Owned(root,project,fixture,profile,application,report,hash);
  }
  private static Path canonicalDirectory(Path path)throws Exception{
    path=path.toAbsolutePath().normalize();require(Files.isDirectory(path,LinkOption.NOFOLLOW_LINKS)&&!Files.isSymbolicLink(path)&&path.toRealPath().equals(path),"Owned directories cannot contain symlinks");return path;
  }
  private static void createAndOpen(){
    Project created=null;
    var watchdog=AppExecutorUtil.getAppScheduledExecutorService().schedule(()->writeFailure(new IllegalStateException("Normal owned-project bootstrap timed out at "+STAGE.get())),75,TimeUnit.SECONDS);
    try {
      var app=ApplicationManager.getApplication();require(!app.isDispatchThread(),"Normal project construction must run on a worker");
      require(!app.isUnitTestMode()&&!app.isHeadlessEnvironment()&&!Boolean.getBoolean("idea.trust.all.projects")&&!Boolean.getBoolean("idea.trust.disabled"),"Native gate cannot use globally disabled trust checks");
      Owned owned=validate(Path.of(property("root")),Path.of(property("project")),Path.of(property("file")),Path.of(property("profile")),Path.of(property("application")),Path.of(property("report")),property("initial.sha256"));
      require(Path.of(PathManager.getHomePath()).toAbsolutePath().normalize().equals(owned.application),"Loaded product differs from selected application");
      for(var entry:Map.of("config",PathManager.getConfigPath(),"system",PathManager.getSystemPath(),"plugins",PathManager.getPluginsPath(),"log",PathManager.getLogPath()).entrySet()){
        Path actual=Path.of(entry.getValue()).toAbsolutePath().normalize();require(actual.equals(owned.profile.resolve(entry.getKey())),"Actual IDE profile is not isolated");
        if(Files.exists(actual,LinkOption.NOFOLLOW_LINKS))canonicalDirectory(actual);
      }
      ProjectManagerEx manager=ProjectManagerEx.getInstanceEx();require(manager.getOpenProjects().length==0,"Owned gate must start without CLI/open projects");
      boolean parentBefore=TrustedProjects.isProjectTrusted(owned.project.getParent());
      require(!parentBefore&&!TrustedProjects.isProjectTrusted(owned.project),"Fresh fixture or its parent was already trusted");
      // This API itself grants normal new-project trust, then constructs the project model.
      STAGE.set("normal-newProject");
      created=manager.newProject(owned.project,OpenProjectTask.build().asNewProject().withProjectName("Owned Notebook Save Gate"));
      require(!FAILED.get(),"Normal new-project construction exceeded the bounded gate");
      require(created!=null&&TrustedProjects.isProjectTrusted(created)&&TrustedProjects.isProjectTrusted(owned.project),"Normal IDE new-project trust was not established");
      boolean parentAfter=TrustedProjects.isProjectTrusted(owned.project.getParent());require(!parentAfter,"New-project trust widened to the parent");
      require(owned.hash.equals(hash(owned.fixture)),"New-project construction changed the generated fixture");
      Map<String,Object> observation=new LinkedHashMap<>();observation.put("normalIdeNewProjectCreation",true);observation.put("expectedInitialFixtureHash",owned.hash);
      observation.put("projectCreationMode",MODE);observation.put("manualTrustClicked",false);observation.put("projectTrustBypassed",false);
      observation.put("globalTrustChecksDisabled",false);observation.put("parentTrustedBefore",parentBefore);observation.put("parentTrustedAfter",parentAfter);
      observation.put("trustedProjectRoot",owned.project.toString());observation.put("trustScope","New owned project root and descendants; parent and siblings are not granted trust");
      CREATED.set(new Created(created,Map.copyOf(observation)));
      STAGE.set("normal-openProject-with-created-model");
      Project opened=manager.openProject(owned.project,OpenProjectTask.build().withProject(created).withForceOpenInNewFrame(true));
      require(opened==created&&opened.isOpen(),"Normal IDE open did not return the created project");
    } catch(Throwable failure){
      writeFailure(failure);
      if(created!=null&&!created.isOpen()&&!created.isDisposed()){
        Project dispose=created;ApplicationManager.getApplication().invokeLater(()->WriteAction.run(()->Disposer.dispose(dispose)));
      }
    } finally {watchdog.cancel(false);}
  }
  static Map<String,Object> evidence(Project project){
    Created created=CREATED.get();require(!FAILED.get()&&created!=null&&created.project==project,"Post-startup project differs from the normal new-project model or bootstrap failed");
    Map<String,Object> evidence=new LinkedHashMap<>(created.evidence);evidence.put("normalIdeProjectOpen",project.isOpen());return evidence;
  }
  private static void writeFailure(Throwable failure){
    FAILED.set(true);
    try {
      Path root=canonicalDirectory(Path.of(property("root"))),report=Path.of(property("report")).toAbsolutePath().normalize();require(report.equals(root.resolve("native-report.json")),"Failure report escaped owned root");
      Map<String,Object> result=new LinkedHashMap<>();result.put("status","fail");result.put("stage","normal-owned-project-bootstrap");result.put("failure",failure.toString());
      result.put("invocationId",property("invocation"));result.put("capturedAt",Instant.now().toString());result.put("ownedPid",ProcessHandle.current().pid());
      result.put("projectCreationMode",MODE);result.put("normalIdeNewProjectCreation",CREATED.get()!=null);result.put("kernelCodeExecuted",false);
      result.put("bootstrapStage",STAGE.get());result.put("expectedInitialFixtureHash",property("initial.sha256"));
      result.put("stack",Arrays.stream(failure.getStackTrace()).limit(20).map(Object::toString).toList());
      var plugin=PluginManagerCore.getPlugin(PluginId.getId("dev.openpycharm.notebooks"));
      if(plugin!=null)result.put("plugin",Map.of("jarSha256",hash(plugin.getPluginPath().resolve("lib/notebooks.jar")),"path",plugin.getPluginPath().toString()));
      Path temporary=Files.createTempFile(root,".owned-project-failure-",".json");
      try{Files.writeString(temporary,new GsonBuilder().setPrettyPrinting().create().toJson(result));Files.move(temporary,report,StandardCopyOption.REPLACE_EXISTING);}finally{Files.deleteIfExists(temporary);}
    }catch(Exception reportFailure){System.err.println("Owned notebook project bootstrap/report failed: "+failure+"; report: "+reportFailure);}
  }
  private static String hash(Path path)throws Exception{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));}
  private static void require(boolean value,String message){if(!value)throw new IllegalStateException(message);}
}
