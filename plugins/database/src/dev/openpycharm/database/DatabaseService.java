package dev.openpycharm.database;

import com.intellij.openapi.Disposable;
import com.intellij.openapi.components.*;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.application.ApplicationManager;
import com.intellij.openapi.util.Key;
import com.intellij.credentialStore.CredentialAttributes;
import com.intellij.credentialStore.Credentials;
import com.intellij.ide.passwordSafe.PasswordSafe;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;
import org.jetbrains.annotations.NotNull;

@Service(Service.Level.PROJECT)
@State(name="OpenPyCharmDatabaseProfiles",storages=@Storage(StoragePathMacros.WORKSPACE_FILE))
public final class DatabaseService implements PersistentStateComponent<DatabaseService.Profiles>, Disposable {
  private static final Key<DatabaseService> CREATED=Key.create("OpenPyCharm.database.createdService");
  public static final class Profiles { public List<DatabaseProfile> connections=new ArrayList<>(); }
  private Profiles state=new Profiles();
  private final Project project;
  public final JdbcSession session=new JdbcSession();
  private final ExecutorService worker=Executors.newSingleThreadExecutor(r->{Thread t=new Thread(r,"OpenPyCharm-JDBC");t.setDaemon(true);return t;});
  private final ExecutorService control=Executors.newSingleThreadExecutor(r->{Thread t=new Thread(r,"OpenPyCharm-JDBC-cancel");t.setDaemon(true);return t;});
  private final AtomicBoolean busy=new AtomicBoolean();
  private volatile boolean disposed;
  public DatabaseService(Project project) {this.project=project;if(project!=null)project.putUserData(CREATED,this);}
  public static DatabaseService get(Project p) {return p.getService(DatabaseService.class);}
  /** Memory-only lookup: unlike ComponentManager's default, never creates a service. */
  public static DatabaseService created(Project p){return p.getUserData(CREATED);}
  @Override public synchronized @NotNull Profiles getState() {Profiles p=new Profiles();for(DatabaseProfile v:state.connections)p.connections.add(v.copy());return p;}
  @Override public synchronized void loadState(@NotNull Profiles p) {
    // Retain unsupported/invalid profiles for repair instead of deleting them on load.
    state=new Profiles();if(p.connections!=null)for(DatabaseProfile v:p.connections)if(v!=null)state.connections.add(v.copy());
  }
  public synchronized List<DatabaseProfile> profiles() {return getState().connections;}
  private CredentialAttributes credentials(DatabaseProfile p) {
    JdbcSession.background();
    String root=project.getBasePath();
    if(root==null)root=project.getProjectFilePath();
    if(root==null)root=System.getProperty("user.home")+"/.openpycharm-default-project/"+project.getLocationHash();
    return new CredentialAttributes(CredentialScope.key(root,p),p.user);
  }
  public void save(DatabaseProfile p,char[] password,boolean forget) {
    JdbcSession.background();p.validate();
    try {
      DatabaseProfile old=profiles().stream().filter(v->Objects.equals(v.id,p.id)).findFirst().orElse(null);
      if(old==null&&profiles().size()>=100)throw new IllegalArgumentException("Maximum 100 connection profiles");
      if(old!=null) {
        boolean valid=true;try{old.validate();}catch(RuntimeException e){valid=false;}
        if(valid&&old.kind()!=DatabaseProfile.Engine.SQLITE&&!credentials(old).equals(credentials(p)))PasswordSafe.getInstance().set(credentials(old),null);
      }
      if(p.kind()!=DatabaseProfile.Engine.SQLITE){
        if(forget)PasswordSafe.getInstance().set(credentials(p),null);
        else if(password.length>0)PasswordSafe.getInstance().set(credentials(p),new Credentials(p.user,password));
      }
      synchronized(this) {state.connections.removeIf(v->Objects.equals(v.id,p.id));state.connections.add(p.copy());}
    } finally {Arrays.fill(password,'\0');}
  }
  public void remove(DatabaseProfile p) {
    JdbcSession.background();boolean valid=true;try{p.validate();}catch(RuntimeException e){valid=false;}
    if(valid&&p.kind()!=DatabaseProfile.Engine.SQLITE)PasswordSafe.getInstance().set(credentials(p),null);
    synchronized(this) {state.connections.removeIf(v->Objects.equals(v.id,p.id));}
  }
  public List<JdbcSession.Table> connect(DatabaseProfile p) throws Exception {
    JdbcSession.background();
    // A pending endpoint switch must not retain the old connection's schema
    // while PasswordSafe waits for its configured provider.
    session.close();
    String value=p.kind()==DatabaseProfile.Engine.SQLITE?null:PasswordSafe.getInstance().getPassword(credentials(p));
    char[] password=value==null?null:value.toCharArray();
    try {session.connect(p,password);return session.refreshMetadata();}finally {if(password!=null)Arrays.fill(password,'\0');}
  }
  public DatabaseMetadataCache.Snapshot completionSnapshot(){return disposed?null:session.completionSnapshot();}
  public boolean busy() {return busy.get();}
  public <T> void submit(Callable<T> operation,Consumer<T> success,Consumer<Throwable> failure) {
    if(disposed || !busy.compareAndSet(false,true)) {failure.accept(new IllegalStateException("Wait for the current database operation or cancel it"));return;}
    worker.execute(()->{
      T value=null;Throwable error=null;
      try {if(!disposed)value=operation.call();}catch(Exception e){error=e;}
      T result=value;Throwable problem=error;
      ApplicationManager.getApplication().invokeLater(()->{busy.set(false);if(!disposed&&!project.isDisposed()){if(problem==null)success.accept(result);else failure.accept(problem);}});
    });
  }
  public void cancel(Consumer<Throwable> failure) {
    if(disposed)return;
    JdbcSession.CancelTicket ticket=session.cancellation();if(ticket==null)return;
    control.execute(()->{try{session.cancel(ticket);}catch(Exception e){ApplicationManager.getApplication().invokeLater(()->{if(!disposed&&!project.isDisposed())failure.accept(e);});}});
  }
  @Override public void dispose() {
    disposed=true;
    if(project!=null&&project.getUserData(CREATED)==this)project.putUserData(CREATED,null);
    control.execute(()->{try{session.cancel();}catch(Exception ignored){}});
    worker.execute(()->{try{session.dispose();}catch(Exception ignored){}});
    worker.shutdown();control.shutdown();
  }
}
