package dev.openpycharm.database;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;
import java.sql.SQLException;
import javax.swing.SwingUtilities;
import static dev.openpycharm.database.DatabaseMetadataCache.*;

/** Real SQLite metadata plus pure native-completion context/candidate controls. No IDE launch. */
public final class DatabaseCompletionProbe {
  private static int checks;
  private static void check(boolean condition,String message){checks++;if(!condition)throw new AssertionError(message);}
  private static SqlCompletionContext.Context context(String marked){int caret=marked.indexOf("<caret>");return SqlCompletionContext.analyze(marked.replace("<caret>",""),caret);}
  private static List<SqlCompletionCandidates.Candidate> candidates(Snapshot snapshot,String marked){return SqlCompletionCandidates.suggest(snapshot,context(marked));}
  private static SqlCompletionCandidates.Candidate named(Snapshot snapshot,String marked,String name){return candidates(snapshot,marked).stream().filter(c->c.name().equals(name)).findFirst().orElseThrow(()->new AssertionError("Missing "+name+" in "+marked));}
  private static String inserted(Snapshot snapshot,String marked,String name){String text=marked.replace("<caret>","");var c=context(marked);return text.substring(0,c.replaceStart())+named(snapshot,marked,name).insertion()+text.substring(c.replaceEnd());}
  public static void main(String[] args)throws Exception{
    Path root=Path.of(args[0]).toAbsolutePath();if(!Files.isDirectory(root)||!root.getFileName().toString().startsWith("owned-sqlite-"))throw new IllegalArgumentException("Owned disposable directory required");
    DatabaseProfile p=new DatabaseProfile();p.file=root.resolve("completion-原生.sqlite").toString();
    JdbcSession session=new JdbcSession();
    try {
      session.connect(p,null);check(session.completionSnapshot()==null,"connection does not expose previous endpoint metadata before explicit refresh");
      session.execute("CREATE TABLE products(id INTEGER, name TEXT, \"display name\" TEXT, \"列 名\" TEXT, \"quote\"\"column\" TEXT, \"select\" TEXT)");
      session.execute("CREATE TABLE orders(id INTEGER, product_id INTEGER)");
      session.execute("CREATE TABLE \"订单 表\"(\"编号\" INTEGER, \"商品 名\" TEXT)");
      session.execute("CREATE TABLE \"odd\"\"table\"(\"col\"\"umn\" TEXT)");
      session.execute("CREATE TABLE \"has.dot\"(\"dot column\" TEXT)");
      StringBuilder wide=new StringBuilder("CREATE TABLE wide(");for(int i=0;i<70;i++){if(i>0)wide.append(',');wide.append("c").append(i).append(" INTEGER");}session.execute(wide.append(')').toString());
      session.refreshMetadata();Snapshot snapshot=session.completionSnapshot();check(snapshot!=null&&snapshot.tables().size()==6,"snapshot comes from real connected SQLite metadata");
      check(snapshot.tables().stream().filter(t->t.name().equals("products")).findFirst().orElseThrow().columns().size()==6,"real column names captured");
      check(snapshot.tables().stream().filter(t->t.name().equals("wide")).findFirst().orElseThrow().columns().size()==64&&snapshot.truncated(),"wide table columns are bounded and truncation recorded");
      check(named(snapshot,"SELECT * FROM pro<caret>","products").insertion().equals("\"main\".\"products\""),"FROM proposes a quoted SQLite main table");
      check(named(snapshot,"SELECT * FROM ma<caret>","main").kind().equals("schema"),"real SQLite default main namespace is available");
      check(named(snapshot,"SELECT * FROM main.pro<caret>","products").insertion().equals("\"products\""),"SQLite schema-qualified table completion");
      check(named(snapshot,"SELECT main.products.na<caret>","name").kind().equals("column"),"SQLite main.table.column completion");
      check(named(snapshot,"SELECT * FROM products p JOIN ord<caret> ON p.id=1","orders").kind().equals("table/view"),"JOIN proposes a table");
      check(named(snapshot,"UPDATE pro<caret> SET name='x'","products").kind().equals("table/view"),"UPDATE proposes a table");
      check(named(snapshot,"INSERT INTO pro<caret>(id) VALUES(1)","products").kind().equals("table/view"),"INTO proposes a table");
      check(named(snapshot,"SELECT p.na<caret> FROM products AS p","name").insertion().equals("\"name\""),"alias-qualified columns resolve metadata");
      check(named(snapshot,"SELECT <caret> FROM products p","display name").kind().equals("column"),"SELECT sees FROM bindings after caret");
      check(named(snapshot,"SELECT p<caret> FROM products p","p").insertion().equals("\"p\"."),"alias itself is a completion candidate");
      check(inserted(snapshot,"SELECT p<caret>.name FROM products p","p").equals("SELECT \"p\".name FROM products p"),"alias completion does not duplicate an existing dot");
      check(named(snapshot,"SELECT * FROM products p WHERE p.na<caret>","name").kind().equals("column"),"WHERE alias completion");
      check(named(snapshot,"SELECT * FROM products p JOIN orders o ON o.pro<caret> = p.id","product_id").kind().equals("column"),"ON join alias completion");
      var ambiguous=candidates(snapshot,"SELECT id<caret> FROM products p JOIN orders o ON p.id=o.product_id");
      check(ambiguous.stream().anyMatch(c->c.insertion().equals("\"p\".\"id\""))&&ambiguous.stream().anyMatch(c->c.insertion().equals("\"o\".\"id\"")),"ambiguous joined columns are qualified with their aliases");
      check(candidates(snapshot,"SELECT products.<caret> FROM products p").isEmpty(),"explicit alias does not fall back to original table qualifier");
      check(candidates(snapshot,"SELECT missing.<caret> FROM products p").isEmpty(),"unknown qualifier does not leak arbitrary table columns");
      check(named(snapshot,"SELECT \"别名\".商<caret> FROM \"订单 表\" AS \"别名\"","商品 名").insertion().equals("\"商品 名\""),"quoted Unicode table and alias");
      String unicode=inserted(snapshot,"SELECT * FROM \"订单<caret> 表\"","订单 表");
      check(unicode.equals("SELECT * FROM \"main\".\"订单 表\""),"quoted table replacement consumes existing closing quote");
      check(session.execute(unicode).columns().contains("商品 名"),"completed Unicode table SQL executes on real SQLite");
      String column=inserted(snapshot,"SELECT p.\"列 <caret>名\" FROM products p","列 名");
      check(column.equals("SELECT p.\"列 名\" FROM products p")&&session.execute(column).columns().contains("列 名"),"partial quoted Unicode column replacement executes");
      String escaped=inserted(snapshot,"SELECT * FROM \"odd<caret>\"","odd\"table");
      check(escaped.contains("\"odd\"\"table\"")&&session.execute(escaped).columns().contains("col\"umn"),"embedded quote table insertion executes");
      check(inserted(snapshot,"SELECT * FROM `pro<caret>`","products").equals("SELECT * FROM \"main\".\"products\""),"backtick prefix replaced with driver-safe identifier quoting");
      check(inserted(snapshot,"SELECT * FROM [pro<caret>]","products").equals("SELECT * FROM \"main\".\"products\""),"bracket prefix replaced without dangling close");
      check(named(snapshot,"SELECT \"has.dot\".<caret>","dot column").insertion().equals("\"dot column\""),"dot inside quoted table name remains one identifier");
      check(named(snapshot,"SELECT p.quo<caret> FROM products p","quote\"column").insertion().equals("\"quote\"\"column\""),"column quotes escaped");
      check(session.execute(inserted(snapshot,"SELECT sel<caret> FROM products","select")).columns().contains("select"),"reserved-word column is inserted as a valid quoted identifier");
      check(new com.intellij.codeInsight.completion.PlainPrefixMatcher("列 ",true).prefixMatches("列 名"),"actual native matcher handles quoted Unicode space prefixes");
      check(context("SELECT <caret>FROM products").replaceEnd()=="SELECT ".length(),"empty completion does not consume following FROM keyword");
      for(String inert:List.of("SELECT 'pro<caret>' FROM products","SELECT $$ pro<caret> $$ FROM products","SELECT 1 -- pro<caret>\n FROM products","SELECT /* pro<caret> */ 1 FROM products","SELECT 'unfinished<caret>","SELECT /* unfinished<caret>"))check(candidates(snapshot,inert).isEmpty(),"comments and literals are inert: "+inert);
      check(candidates(snapshot,"SELECT E'not\\'a pro<caret>' FROM products").isEmpty(),"backslash-escaped quote cannot expose literal content as a completion context");
      check(candidates(snapshot,"SELECT p.<caret> FROM products p; SELECT * FROM orders p").stream().noneMatch(c->c.name().equals("product_id")),"another statement cannot overwrite current alias");
      check(candidates(snapshot,"WITH p AS (SELECT * FROM products) SELECT p.<caret> FROM p").isEmpty(),"unsupported CTE scopes are conservative");
      check(candidates(snapshot,"SELECT * FROM products p WHERE EXISTS(SELECT p.<caret> FROM orders p)").isEmpty(),"unsupported nested scope cannot reuse outer alias");
      for(String compound:List.of("UNION","INTERSECT","EXCEPT"))check(candidates(snapshot,"SELECT o.<caret> FROM products p "+compound+" SELECT id FROM orders o").isEmpty(),"compound query cannot import another arm's alias");
      check(candidates(snapshot,"SELECT <caret> FROM products p UNION SELECT id FROM orders o").isEmpty(),"compound arms cannot mix unqualified column candidates");
      check(named(snapshot,"SELECT p.na<caret>, 'UNION' FROM products p","name")!=null,"compound keyword in string does not disable a plain SELECT");
      check(SqlCompletionContext.analyze("x".repeat(SqlCompletionContext.MAX_TEXT+1),1).mode()==SqlCompletionContext.Mode.NONE,"completion document bound");
      List<Table> qualified=new ArrayList<>();for(Table t:snapshot.tables())qualified.add(new Table(null,"public",t.name(),t.columns()));
      qualified.add(new Table(null,"other","products",List.of(new Column("foreign_column","TEXT"))));
      qualified.add(new Table(null,"数据 模式","库存 表",List.of(new Column("库存 编号","INTEGER"))));
      Snapshot schemas=new Snapshot("\"",qualified,false,1);
      check(named(schemas,"SELECT * FROM pub<caret>","public").insertion().equals("\"public\"."),"schema completion");
      check(inserted(schemas,"SELECT * FROM pub<caret>.products","public").equals("SELECT * FROM \"public\".products"),"schema completion does not duplicate an existing dot");
      check(named(schemas,"SELECT * FROM public.pro<caret>","products").insertion().equals("\"products\""),"schema-qualified relation completion");
      check(candidates(schemas,"SELECT * FROM missing.<caret>").isEmpty(),"wrong schema has no fallback tables");
      check(named(schemas,"SELECT p.na<caret> FROM public.products p","name").kind().equals("column"),"schema-qualified table binds alias");
      check(named(schemas,"SELECT public.products.na<caret>","name").kind().equals("column"),"schema.table.column qualifier");
      check(candidates(schemas,"SELECT p.<caret> FROM products p").isEmpty(),"ambiguous unqualified relation across schemas stays unresolved");
      check(named(schemas,"SELECT * FROM \"数据 模式\".库<caret>","库存 表").insertion().equals("\"库存 表\""),"quoted Unicode schema context");
      var duplicates=candidates(schemas,"SELECT * FROM pro<caret>").stream().filter(c->c.name().equals("products")).toList();
      check(duplicates.size()==2&&duplicates.stream().allMatch(c->c.insertion().startsWith("\"public\".")||c.insertion().startsWith("\"other\".")),"duplicate relation names insert their full schema to avoid a wrong namespace");
      check(candidates(schemas,"SELECT \"Products\".<caret>").isEmpty(),"quoted identifier matching preserves case");
      Snapshot mysql=new Snapshot("`",List.of(new Table(null,null,"t",List.of(new Column("odd`name","TEXT")))),false,1);
      check(named(mysql,"SELECT t.od<caret>","odd`name").insertion().equals("`odd``name`"),"driver-specific backtick escaping");
      Snapshot beforeDdl=session.completionSnapshot();check(beforeDdl!=null,"query does not invalidate unchanged metadata");
      session.execute("ALTER TABLE products ADD COLUMN refreshed_column TEXT");check(session.completionSnapshot()==null,"DDL invalidates cached schema immediately");
      session.refreshMetadata();check(named(session.completionSnapshot(),"SELECT p.ref<caret> FROM products p","refreshed_column")!=null,"explicit refresh publishes new real column");
      session.setAutoCommit(false);session.execute("CREATE TABLE transaction_only(temporary_column TEXT)");session.refreshMetadata();
      check(named(session.completionSnapshot(),"SELECT * FROM transaction_<caret>","transaction_only")!=null,"metadata can reflect current transaction's own schema");
      session.rollback();session.setAutoCommit(true);check(session.completionSnapshot()==null,"rollback invalidates a snapshot captured after uncommitted DDL");
      session.refreshMetadata();check(candidates(session.completionSnapshot(),"SELECT * FROM transaction_<caret>").isEmpty(),"rolled-back table cannot remain in refreshed candidates");
      session.execute("PRAGMA foreign_keys=ON");session.execute("CREATE TABLE fk_parent(id INTEGER PRIMARY KEY)");session.execute("CREATE TABLE fk_child(parent_id INTEGER REFERENCES fk_parent(id) DEFERRABLE INITIALLY DEFERRED)");
      session.setAutoCommit(false);session.execute("CREATE TABLE failed_commit_table(temporary_column TEXT)");session.execute("INSERT INTO fk_child VALUES(999)");session.refreshMetadata();
      boolean failedCommit=false;try{session.commit();}catch(SQLException expected){failedCommit=true;}
      check(failedCommit&&!session.autoCommit()&&session.completionSnapshot()==null,"deferred FK rejects COMMIT without ending schema transaction or retaining snapshot");
      session.refreshMetadata();check(named(session.completionSnapshot(),"SELECT * FROM failed_commit_<caret>","failed_commit_table")!=null,"failed COMMIT transaction still exposes its own uncommitted table");
      session.rollback();session.setAutoCommit(true);check(session.completionSnapshot()==null,"failed COMMIT retains dirty flag so later rollback invalidates refreshed metadata");
      session.refreshMetadata();boolean tableGone=false;try{session.execute("SELECT * FROM failed_commit_table");}catch(SQLException expected){tableGone=true;}
      check(tableGone&&candidates(session.completionSnapshot(),"SELECT * FROM failed_commit_<caret>").isEmpty(),"rolled-back failed-COMMIT table is absent in actual SQLite and candidates");
      Snapshot readOnEdt=session.completionSnapshot();SwingUtilities.invokeAndWait(()->check(!candidates(readOnEdt,"SELECT p.na<caret> FROM products p").isEmpty(),"completion is in-memory and safe to read on EDT"));
      session.close();check(session.completionSnapshot()==null,"disconnect discards snapshot");
      DatabaseProfile other=p.copy();other.file=root.resolve("other-endpoint.sqlite").toString();session.connect(other,null);check(session.completionSnapshot()==null,"new endpoint cannot see old snapshot");
      session.execute("CREATE TABLE only_new_endpoint(new_column INTEGER)");session.refreshMetadata();
      check(candidates(session.completionSnapshot(),"SELECT * FROM pro<caret>").isEmpty()&&named(session.completionSnapshot(),"SELECT * FROM only<caret>","only_new_endpoint")!=null,"new endpoint publishes only its own metadata");
      for(int i=0;i<140;i++)session.execute("CREATE TABLE \"zz_table_"+i+"\"(n INTEGER)");session.refreshMetadata();
      check(session.completionSnapshot().tables().size()<=128&&session.completionSnapshot().truncated(),"real oversized schema is bounded");
      check(candidates(session.completionSnapshot(),"SELECT * FROM <caret>").size()<=SqlCompletionCandidates.MAX_CANDIDATES,"candidate count is bounded");
      List<Table> numerous=new ArrayList<>();for(int i=0;i<240;i++)numerous.add(new Table(null,"schema_"+i,"candidate_"+i,List.of()));
      check(candidates(new Snapshot("\"",numerous,false,1),"SELECT * FROM <caret>").size()==200,"candidate limit is applied when alternatives exceed the cap");
      check(SqlCompletionContext.analyze("SELECT "+"? ".repeat(12001),7).mode()==SqlCompletionContext.Mode.NONE,"completion token bound");
      DatabaseProfile totalProfile=p.copy();totalProfile.file=root.resolve("bounded-total-columns.sqlite").toString();session.connect(totalProfile,null);
      for(int t=0;t<80;t++){StringBuilder definition=new StringBuilder("CREATE TABLE t"+t+"(");for(int c=0;c<70;c++){if(c>0)definition.append(',');definition.append("c").append(c).append(" TEXT");}session.execute(definition.append(')').toString());}
      session.refreshMetadata();Snapshot bounded=session.completionSnapshot();int columnCount=bounded.tables().stream().mapToInt(t->t.columns().size()).sum();
      check(columnCount>0&&columnCount<=4096&&bounded.truncated(),"real 5600-column schema obeys total metadata budget");
    }finally{session.dispose();}
    AtomicLong clock=new AtomicLong(1);DatabaseMetadataCache cache=new DatabaseMetadataCache(clock::get);
    check(cache.current()==null,"fresh cache does not connect or populate itself");cache.connected();Token old=cache.beginRefresh();cache.disconnected();cache.connected();Token newer=cache.beginRefresh();
    check(!cache.publish(old,"\"",List.of(new Table(null,null,"wrong_endpoint",List.of())),false),"old endpoint refresh cannot publish after reconnect");
    check(cache.publish(newer,"\"",List.of(new Table(null,null,"right_endpoint",List.of())),false),"current connection refresh publishes");
    clock.set(DatabaseMetadataCache.MAX_AGE_NANOS+2);check(cache.current()==null,"expired schema snapshot returns no suggestions without auto-refresh");
    Token first=cache.beginRefresh(),second=cache.beginRefresh();check(!cache.publish(first,"\"",List.of(),false)&&cache.publish(second,"\"",List.of(),false),"late refresh cannot replace newer snapshot");
    cache.disconnected();check(!cache.publish(second,"\"",List.of(),false)&&cache.current()==null,"close rejects late publication");
    Map<Object,Object> userData=new HashMap<>();
    com.intellij.openapi.project.Project project=(com.intellij.openapi.project.Project)java.lang.reflect.Proxy.newProxyInstance(DatabaseCompletionProbe.class.getClassLoader(),new Class[]{com.intellij.openapi.project.Project.class},(proxy,method,arguments)->switch(method.getName()){
      case "getUserData"->userData.get(arguments[0]);
      case "putUserData"->{if(arguments[1]==null)userData.remove(arguments[0]);else userData.put(arguments[0],arguments[1]);yield null;}
      case "getService","getServiceIfCreated"->throw new AssertionError("Completion must never create or request a project service");
      case "isDisposed"->false;
      case "hashCode"->System.identityHashCode(proxy);
      case "equals"->proxy==arguments[0];
      case "toString"->"owned completion project proxy";
      default->throw new AssertionError("Unexpected project call: "+method.getName());
    });
    check(DatabaseService.created(project)==null,"completion lookup does not initialize an absent service");
    DatabaseService service=new DatabaseService(project);
    try{SwingUtilities.invokeAndWait(()->check(DatabaseService.created(project)==service&&service.completionSnapshot()==null,"EDT completion lookup uses only project memory"));}finally{service.dispose();}
    check(DatabaseService.created(project)==null,"disposed project service no longer supplies a completion cache");
    System.out.println("{\"status\":\"pass\",\"checks\":"+checks+",\"realSqliteMetadata\":true,\"quotedUnicodeAliasAndSchemaContexts\":true,\"schemaNamespacesUseInMemoryControls\":true,\"disconnectAndStaleSnapshots\":true,\"nativeCompletionUiTested\":false,\"networkServersTested\":false}");
  }
}
