package dev.openpycharm.database.nativeprobe;

import com.google.gson.GsonBuilder;
import com.intellij.codeInsight.completion.*;
import com.intellij.codeInsight.lookup.*;
import com.intellij.codeInsight.lookup.impl.LookupImpl;
import com.intellij.ide.DataManager;
import com.intellij.ide.impl.TrustedProjects;
import com.intellij.ide.plugins.PluginManagerCore;
import com.intellij.openapi.actionSystem.*;
import com.intellij.openapi.actionSystem.ex.ActionUtil;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.application.PathManager;
import com.intellij.openapi.command.WriteCommandAction;
import com.intellij.openapi.editor.Editor;
import com.intellij.openapi.extensions.PluginId;
import com.intellij.openapi.fileEditor.*;
import com.intellij.openapi.project.*;
import com.intellij.openapi.progress.ProcessCanceledException;
import com.intellij.openapi.startup.StartupActivity;
import com.intellij.openapi.vfs.*;
import com.intellij.openapi.wm.*;
import com.intellij.psi.PsiDocumentManager;
import com.intellij.lang.LanguageParserDefinitions;
import com.intellij.openapi.fileTypes.FileTypeManager;
import com.intellij.ui.EditorTextField;
import com.intellij.util.concurrency.AppExecutorUtil;
import dev.openpycharm.database.*;
import java.awt.*;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import java.util.List;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import javax.swing.*;
import org.jetbrains.annotations.NotNull;

/** Actual-platform, owned-fixture probe. Observers never contribute items or create a lookup. */
public final class DatabaseCompletionNativeProbe implements StartupActivity.DumbAware {
  private static final AtomicBoolean REQUESTED=new AtomicBoolean();
  private static volatile Capture active;
  private record Capture(String name,Project project,Editor editor,Queue<Map<String,Object>> events,AtomicInteger count) {}
  private record Case(String name,String marked,String lookup,String type,String expected,boolean console,boolean handlerDiagnostic) {}
  public static final class BeforeObserver extends CompletionContributor implements com.intellij.openapi.project.DumbAware {
    @Override public void beforeCompletion(@NotNull CompletionInitializationContext c){safely(()->observeBefore("first-before",c));}
    @Override public void fillCompletionVariants(@NotNull CompletionParameters p,@NotNull CompletionResultSet r){safely(()->observeFill("first-fill",p,r));}
  }
  public static final class AfterObserver extends CompletionContributor implements com.intellij.openapi.project.DumbAware {
    @Override public void beforeCompletion(@NotNull CompletionInitializationContext c){safely(()->observeBefore("last-before",c));}
    @Override public void fillCompletionVariants(@NotNull CompletionParameters p,@NotNull CompletionResultSet r){safely(()->observeFill("last-fill",p,r));}
  }
  private static void safely(Runnable observation){try{observation.run();}catch(ProcessCanceledException e){throw e;}catch(Throwable error){Capture c=active;if(c!=null&&c.count.incrementAndGet()<=96)c.events.add(Map.of("event","observer-error","failure",limit(error.toString(),400)));}}
  private final AtomicInteger heartbeat=new AtomicInteger();
  private final AtomicReference<String> stage=new AtomicReference<>("startup");
  private Project project;
  private Path root,report,database,source;
  private DatabaseToolWindow.Panel panel;
  private DatabaseService service;
  private javax.swing.Timer timer;

  @Override public void runActivity(@NotNull Project project){
    String output=System.getProperty("openpycharm.database.completion.report"),boundary=System.getProperty("openpycharm.database.completion.root"),expectedProject=System.getProperty("openpycharm.database.completion.project");
    if(output==null||boundary==null||expectedProject==null||project.getBasePath()==null||!Path.of(project.getBasePath()).toAbsolutePath().normalize().equals(Path.of(expectedProject).toAbsolutePath().normalize())||!REQUESTED.compareAndSet(false,true))return;
    this.project=project;root=Path.of(boundary).toAbsolutePath().normalize();report=Path.of(output).toAbsolutePath().normalize();
    database=Path.of(System.getProperty("openpycharm.database.completion.database")).toAbsolutePath().normalize();source=Path.of(System.getProperty("openpycharm.database.completion.source")).toAbsolutePath().normalize();
    if(!report.startsWith(root)||!database.startsWith(root.resolve("project"))||!source.startsWith(root.resolve("project")))return;
    AppExecutorUtil.getAppExecutorService().execute(this::run);
  }
  private void run(){
    Map<String,Object> result=new LinkedHashMap<>();List<Map<String,Object>> cases=new ArrayList<>();
    result.put("invocationId",System.getProperty("openpycharm.database.completion.invocation"));result.put("capturedAt",Instant.now().toString());result.put("ownedPid",ProcessHandle.current().pid());result.put("applicationHome",PathManager.getHomePath());
    result.put("ownedFixtureOnly",true);result.put("artificialSnapshotInjected",false);result.put("lookupCreatedByProbe",false);result.put("observerContributedItems",false);result.put("projectTrustBypassed",false);result.put("keyboardInputTested",false);result.put("cases",cases);
    try{
      require(database.toRealPath().startsWith(root.toRealPath())&&source.toRealPath().startsWith(root.toRealPath()),"Fixture path escaped owned boundary");
      result.put("plugin",observePlugin());
      edt(()->{timer=new javax.swing.Timer(25,e->heartbeat.incrementAndGet());timer.start();return null;});
      stage.set("waiting-project-trust-and-smart-mode");await(()->TrustedProjects.isTrusted(project),45,"Root must trust this disposable project through the ordinary flow");result.put("projectTrusted",true);
      require(DumbService.getInstance(project).waitForSmartMode(30_000),"Project did not become smart within 30 seconds");
      stage.set("opening-real-database-tool-window");
      edt(()->{ToolWindow window=ToolWindowManager.getInstance(project).getToolWindow("Database");require(window!=null,"Database tool window is not registered");window.activate(null);return null;});
      await(()->edt(()->findPanel()!=null),15,"Actual Database panel did not initialize");
      panel=edt(this::findPanel);service=edt(()->field(panel,"service",DatabaseService.class));
      result.put("startupProject",projectInfo(project));result.put("panelServiceIdentity",id(service));result.put("createdServiceMatchesPanel",DatabaseService.created(project)==service);
      DatabaseProfile profile=new DatabaseProfile();profile.name="Native completion probe";profile.file=database.toString();service.save(profile,new char[0],false);
      stage.set("real-panel-connect");
      edt(()->{var method=panel.getClass().getDeclaredMethod("reload",String.class);method.setAccessible(true);method.invoke(panel,profile.id);JButton connect=field(panel,"connect",JButton.class);require(connect.isEnabled(),"Actual Connect button disabled");connect.doClick(0);return null;});
      await(()->!service.busy()&&service.completionSnapshot()!=null,25,"Actual Connect did not publish a metadata snapshot");
      result.put("connectedSnapshot",snapshotInfo(service));result.put("panelTableRows",edt(()->field(panel,"tables",JList.class).getModel().getSize()));
      result.put("registeredContributors",edt(()->CompletionContributor.forLanguage(SqlLanguage.INSTANCE).stream().map(c->c.getClass().getName()).toList()));
      VirtualFile virtual=LocalFileSystem.getInstance().refreshAndFindFileByNioFile(source);require(virtual!=null,"Owned SQL source missing from actual VFS");
      result.put("sqlFileTypeByName",FileTypeManager.getInstance().getFileTypeByFileName(source.getFileName().toString()).getClass().getName());result.put("actualVirtualFileType",virtual.getFileType().getClass().getName());
      Editor fileEditor=edt(()->FileEditorManager.getInstance(project).openTextEditor(new OpenFileDescriptor(project,virtual),true));require(fileEditor!=null,"Actual native text editor did not open");
      List<Case> definitions=List.of(
        new Case("source-table","SELECT * FROM pro|;","products","table/view","SELECT * FROM \"main\".\"products\";",false,false),
        new Case("source-alias","SELECT p.na| FROM main.products p;","name","column","SELECT p.\"name\" FROM main.products p;",false,false),
        new Case("source-quoted","SELECT p.\"列 |名\" FROM main.products p;","列 名","column","SELECT p.\"列 名\" FROM main.products p;",false,false),
        new Case("console-table","SELECT * FROM pro|;","products","table/view","SELECT * FROM \"main\".\"products\";",true,false),
        new Case("console-alias","SELECT p.na| FROM main.products p;","name","column","SELECT p.\"name\" FROM main.products p;",true,false),
        new Case("console-quoted","SELECT p.\"列 |名\" FROM main.products p;","列 名","column","SELECT p.\"列 名\" FROM main.products p;",true,false),
        new Case("source-handler-diagnostic","SELECT * FROM pro|;","products","table/view","SELECT * FROM \"main\".\"products\";",false,true));
      for(Case c:definitions){
        stage.set(c.name);Editor editor=fileEditor;
        if(c.console){
          edt(()->{ToolWindowManager.getInstance(project).getToolWindow("Database").activate(null);showSqlTab(panel);return null;});
          await(()->edt(()->field(panel,"sql",EditorTextField.class).getEditor()!=null),10,"Embedded SQL editor not initialized");editor=edt(()->field(panel,"sql",EditorTextField.class).getEditor());
        }
        cases.add(exercise(c,editor));
      }
      boolean accepted=cases.stream().filter(c->!Boolean.TRUE.equals(c.get("handlerDiagnostic"))).allMatch(c->Boolean.TRUE.equals(c.get("nativePopupShown"))&&Boolean.TRUE.equals(c.get("nativeInsertionMatched")));
      result.put("status",accepted?"pass":"fail");result.put("nativeBasicActionGatePassed",accepted);
    }catch(Throwable error){result.put("status","fail");result.put("failure",error.toString());result.put("stack",Arrays.stream(error.getStackTrace()).limit(20).map(Object::toString).toList());}
    finally{
      active=null;result.put("stage",stage.get());result.put("heartbeatTicks",heartbeat.get());
      try{if(service!=null&&!service.busy()){edt(()->{JButton disconnect=field(panel,"disconnect",JButton.class);if(disconnect.isEnabled())disconnect.doClick(0);return null;});await(()->!service.busy()&&service.completionSnapshot()==null,10,"Owned database disconnect did not complete");result.put("ownedConnectionDisconnected",true);}}
      catch(Throwable e){result.put("cleanupFailure",e.toString());}
      if(!"pass".equals(result.get("status")))try{StringBuilder dump=new StringBuilder();for(var t:ManagementFactory.getThreadMXBean().dumpAllThreads(true,true,40)){dump.append(t).append('\n');if(dump.length()>2_000_000)break;}Files.writeString(report.resolveSibling("completion-native-threads.txt"),dump.toString());}catch(Exception ignored){}
      try{Files.createDirectories(report.getParent());Path temp=Files.createTempFile(report.getParent(),".completion-native-",".json");Files.writeString(temp,new GsonBuilder().setPrettyPrinting().serializeNulls().create().toJson(result));Files.move(temp,report,StandardCopyOption.REPLACE_EXISTING);}catch(Exception ignored){}
      ApplicationManager.getApplication().invokeLater(()->{if(timer!=null)timer.stop();});
    }
  }
  private Map<String,Object> exercise(Case c,Editor editor)throws Exception{
    Map<String,Object> result=new LinkedHashMap<>();Queue<Map<String,Object>> events=new ConcurrentLinkedQueue<>();String text=c.marked.replace("|","");int caret=c.marked.indexOf('|');
    result.put("name",c.name);result.put("handlerDiagnostic",c.handlerDiagnostic);result.put("expectedAfter",c.expected);result.put("nativeEntryPoint",c.handlerDiagnostic?"CodeCompletionHandlerBase.invokeCompletion (diagnostic only)":"ActionUtil.invokeAction:CodeCompletion");
    edt(()->{LookupEx old=LookupManager.getActiveLookup(editor);if(old!=null)old.hideLookup(false);WriteCommandAction.runWriteCommandAction(project,"Owned native SQL completion fixture",null,()->editor.getDocument().setText(text));editor.getCaretModel().moveToOffset(caret);PsiDocumentManager.getInstance(project).commitDocument(editor.getDocument());editor.getContentComponent().requestFocusInWindow();return null;});
    Thread.sleep(250);
    Capture capture=new Capture(c.name,project,editor,events,new AtomicInteger());active=capture;
    result.put("before",edt(()->editorInfo(editor)));int ticks=heartbeat.get();
    edt(()->{
      if(c.handlerDiagnostic)CodeCompletionHandlerBase.createHandler(CompletionType.BASIC).invokeCompletion(project,editor);
      else{AnAction action=ActionManager.getInstance().getAction("CodeCompletion");require(action!=null,"Actual Basic CodeCompletion action missing");DataContext context=DataManager.getInstance().getDataContext(editor.getContentComponent());result.put("actionContextEditorMatches",CommonDataKeys.EDITOR.getData(context)==editor);result.put("actionContextProject",projectInfo(CommonDataKeys.PROJECT.getData(context)));ActionUtil.invokeAction(action,editor.getContentComponent(),"OpenPyCharm.Database.NativeCompletionProbe",null,()->{});}
      return null;
    });
    LookupElement[] selected=new LookupElement[1];LookupImpl[] chosen=new LookupImpl[1];
    long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(8);
    while(System.nanoTime()<deadline){
      boolean found=edt(()->{LookupEx lookup=LookupManager.getActiveLookup(editor);if(lookup==null)return false;result.put("observedLookupClass",lookup.getClass().getName());result.put("observedItems",lookupItems(lookup));
        for(LookupElement item:lookup.getItems()){LookupElementPresentation p=new LookupElementPresentation();item.renderElement(p);if(item.getLookupString().equals(c.lookup)&&Objects.equals(p.getTypeText(),c.type)&&lookup instanceof LookupImpl impl){selected[0]=item;chosen[0]=impl;return true;}}return false;});
      if(found)break;Thread.sleep(100);
    }
    if(chosen[0]!=null){
      edt(()->{result.put("nativePopupShown",chosen[0].isShown()&&chosen[0].getComponent().isShowing());result.put("lookupStart",chosen[0].getLookupStart());result.put("selectedItem",selected[0].getLookupString());result.put("nativeSelectionMethod","LookupImpl.finishLookup");chosen[0].finishLookup(Lookup.NORMAL_SELECT_CHAR,selected[0]);return null;});
      Thread.sleep(150);
    }else result.put("nativePopupShown",false);
    result.put("after",edt(()->editor.getDocument().getText()));result.put("afterEditor",edt(()->editorInfo(editor)));result.put("nativeInsertionMatched",Objects.equals(result.get("after"),c.expected));result.put("heartbeatTicksDuringCase",heartbeat.get()-ticks);result.put("events",List.copyOf(events));result.put("endSnapshot",snapshotInfo(service));
    edt(()->{LookupEx lookup=LookupManager.getActiveLookup(editor);if(lookup!=null)lookup.hideLookup(false);return null;});active=null;return result;
  }
  private DatabaseToolWindow.Panel findPanel(){ToolWindow w=ToolWindowManager.getInstance(project).getToolWindow("Database");if(w!=null)for(var content:w.getContentManager().getContents())if(content.getComponent() instanceof DatabaseToolWindow.Panel p)return p;return null;}
  private static void showSqlTab(Container container){for(Component c:container.getComponents()){if(c instanceof DatabaseContentLayout layout&&layout.isTabbed())layout.tabs().setSelectedIndex(1);if(c instanceof Container nested)showSqlTab(nested);}}
  private static void observeBefore(String event,CompletionInitializationContext c){
    Capture capture=active;if(capture==null||c.getEditor().getDocument()!=capture.editor.getDocument()||capture.count.incrementAndGet()>96)return;
    Map<String,Object> row=new LinkedHashMap<>();row.put("event",event);row.put("initProject",projectInfo(c.getProject()));row.put("editor",editorInfo(c.getEditor()));row.put("startOffset",c.getStartOffset());row.put("selectionEndOffset",c.getSelectionEndOffset());row.put("identifierEndOffset",c.getIdentifierEndOffset());row.put("fileLanguage",c.getFile().getLanguage().getID());row.put("snapshot",snapshotInfo(DatabaseService.created(c.getProject())));capture.events.add(row);
  }
  private static void observeFill(String event,CompletionParameters p,CompletionResultSet result){
    Capture capture=active;if(capture==null||p.getEditor().getDocument()!=capture.editor.getDocument()||capture.count.incrementAndGet()>96)return;
    Map<String,Object> row=new LinkedHashMap<>();row.put("event",event);row.put("parameterOffset",p.getOffset());row.put("editor",editorInfo(p.getEditor()));row.put("originalProject",projectInfo(p.getOriginalFile().getProject()));row.put("originalLanguage",p.getOriginalFile().getLanguage().getID());row.put("positionLanguage",p.getPosition().getLanguage().getID());row.put("positionText",limit(p.getPosition().getText(),100));row.put("positionRange",p.getPosition().getTextRange().toString());row.put("contributors",CompletionContributor.forParameters(p).stream().map(c->c.getClass().getName()).toList());
    String text=p.getEditor().getDocument().getText();var atParameters=SqlCompletionContext.analyze(text,p.getOffset());var atCaret=SqlCompletionContext.analyze(text,p.getEditor().getCaretModel().getOffset());row.put("diagnosticContextAtParameter",contextInfo(atParameters));row.put("diagnosticContextAtCaret",contextInfo(atCaret));row.put("nativeResultPrefix",result.getPrefixMatcher().getPrefix());row.put("resultStopped",result.isStopped());row.put("snapshot",snapshotInfo(DatabaseService.created(p.getOriginalFile().getProject())));capture.events.add(row);
  }
  private static Map<String,Object> contextInfo(SqlCompletionContext.Context c){return Map.of("mode",c.mode().name(),"prefix",c.prefix(),"replaceStart",c.replaceStart(),"replaceEnd",c.replaceEnd());}
  private static Map<String,Object> editorInfo(Editor e){Map<String,Object> m=new LinkedHashMap<>();m.put("editorIdentity",id(e));m.put("documentIdentity",id(e.getDocument()));m.put("project",projectInfo(e.getProject()));m.put("caret",e.getCaretModel().getOffset());m.put("documentText",limit(e.getDocument().getText(),300));if(e.getProject()!=null){var psi=PsiDocumentManager.getInstance(e.getProject()).getCachedPsiFile(e.getDocument());m.put("psiPresent",psi!=null);if(psi!=null){m.put("psiClass",psi.getClass().getName());m.put("psiLanguage",psi.getLanguage().getID());m.put("psiFileType",psi.getFileType().getClass().getName());m.put("psiViewProvider",psi.getViewProvider().getClass().getName());var parser=LanguageParserDefinitions.INSTANCE.forLanguage(psi.getLanguage());m.put("parserDefinition",parser==null?"none":parser.getClass().getName());}}boolean dispatch=ApplicationManager.getApplication().isDispatchThread();m.put("isDispatchThread",dispatch);if(dispatch){m.put("showing",e.getContentComponent().isShowing());Component focus=KeyboardFocusManager.getCurrentKeyboardFocusManager().getFocusOwner();m.put("focusOwner",id(focus));m.put("focusWithinEditor",focus!=null&&(focus==e.getContentComponent()||SwingUtilities.isDescendingFrom(focus,e.getContentComponent())));}return m;}
  private static Map<String,Object> projectInfo(Project p){if(p==null)return Map.of("null",true);return Map.of("identity",id(p),"class",p.getClass().getName(),"basePath",Objects.toString(p.getBasePath(),""),"default",p.isDefault());}
  private static Map<String,Object> snapshotInfo(DatabaseService service){Map<String,Object> m=new LinkedHashMap<>();m.put("createdServiceIdentity",id(service));if(service==null){m.put("present",false);return m;}var s=service.completionSnapshot();m.put("present",s!=null);if(s!=null){m.put("identity",id(s));m.put("tableCount",s.tables().size());m.put("columnCount",s.tables().stream().mapToInt(t->t.columns().size()).sum());m.put("tables",s.tables().stream().limit(16).map(t->Objects.toString(t.schema(),"")+"."+t.name()).toList());m.put("truncated",s.truncated());}return m;}
  private static List<Map<String,Object>> lookupItems(Lookup lookup){List<Map<String,Object>> out=new ArrayList<>();for(LookupElement item:lookup.getItems().stream().limit(30).toList()){LookupElementPresentation p=new LookupElementPresentation();item.renderElement(p);Map<String,Object> row=new LinkedHashMap<>();row.put("lookup",item.getLookupString());row.put("type",p.getTypeText());row.put("tail",p.getTailText());out.add(row);}return out;}
  private Map<String,Object> observePlugin()throws Exception{var d=PluginManagerCore.getPlugin(PluginId.getId("dev.openpycharm.database"));require(d!=null,"Actual Database plugin not discovered");Path jar=d.getPluginPath().resolve("lib/database.jar");String hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(jar)));require(hash.equals(System.getProperty("openpycharm.database.completion.expected.jar")),"Actual Database JAR differs from prepared production receipt");return Map.of("id",d.getPluginId().getIdString(),"version",Objects.toString(d.getVersion(),""),"path",d.getPluginPath().toString(),"jarSha256",hash,"classLoader",d.getPluginClassLoader().toString());}
  private static String id(Object o){return o==null?"null":o.getClass().getName()+"@"+Integer.toHexString(System.identityHashCode(o));}
  private static String limit(String s,int length){return s.length()<=length?s:s.substring(0,length)+"…";}
  private static <T>T field(Object target,String name,Class<T> type)throws Exception{Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);return type.cast(f.get(target));}
  private static void require(boolean condition,String message){if(!condition)throw new IllegalStateException(message);}
  private static <T>T edt(Callable<T> task)throws Exception{if(ApplicationManager.getApplication().isDispatchThread())return task.call();FutureTask<T> future=new FutureTask<>(task);ApplicationManager.getApplication().invokeLater(future);return future.get(12,TimeUnit.SECONDS);}
  private interface CheckedBoolean {boolean get()throws Exception;}
  private static void await(CheckedBoolean condition,int seconds,String failure)throws Exception{long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(seconds);while(System.nanoTime()<deadline){if(condition.get())return;Thread.sleep(100);}throw new IllegalStateException(failure);}
}
