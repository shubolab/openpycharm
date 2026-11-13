package dev.openpycharm.database;

import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Driver;
import java.sql.SQLException;
import java.util.*;
import java.util.concurrent.*;
import javax.swing.SwingUtilities;

/** Real JDBC controls against an owned disposable SQLite file, never a user DB. */
public final class DatabaseIntegrationProbe {
  private static int checks;
  private static void check(boolean value,String message){checks++;if(!value)throw new AssertionError(message);}
  private static void rejects(Runnable task,String message){boolean rejected=false;try{task.run();}catch(IllegalArgumentException expected){rejected=true;}check(rejected,message);}
  public static void main(String[] args)throws Exception {
    Path directory=Path.of(args[0]).toAbsolutePath();
    if(!Files.isDirectory(directory)||!directory.getFileName().toString().startsWith("owned-sqlite-"))throw new IllegalArgumentException("Use an owned temporary database directory");
    DatabaseProfile p=new DatabaseProfile();p.file=directory.resolve("测试 database.sqlite").toString();
    check(!p.jdbcUrl().contains("password"),"SQLite URL has no credentials");
    p.validate();char[] password="disposable".toCharArray();
    String scope=CredentialScope.key(directory.toString(),p);
    check(scope.equals(CredentialScope.key(directory.resolve(".").toString(),p)),"canonical project path shares its own credential scope");
    DatabaseProfile changed=p.copy();changed.file=directory.resolve("other.sqlite").toString();
    check(!scope.equals(CredentialScope.key(directory.toString(),changed)),"edited endpoint cannot reuse saved credential");
    changed=p.copy();changed.user="another-user";check(!scope.equals(CredentialScope.key(directory.toString(),changed)),"different user cannot reuse saved credential");
    changed=p.copy();changed.id=UUID.randomUUID().toString();check(!scope.equals(CredentialScope.key(directory.toString(),changed)),"different profile cannot reuse saved credential");
    changed=p.copy();changed.verifyTls=false;check(!scope.equals(CredentialScope.key(directory.toString(),changed)),"TLS downgrade cannot reuse saved credential");
    check(!scope.equals(CredentialScope.key(directory.resolve("other-project").toString(),p)),"different project cannot reuse saved credential");
    DatabaseService stateService=new DatabaseService(null);
    try {
      DatabaseService.Profiles state=new DatabaseService.Profiles();DatabaseProfile unknown=p.copy();unknown.engine="FUTURE_DRIVER";unknown.metadata.put("future-setting","retained");state.connections.add(unknown);stateService.loadState(state);
      check(stateService.getState().connections.getFirst().engine.equals("FUTURE_DRIVER")&&stateService.getState().connections.getFirst().metadata.get("future-setting").equals("retained"),"unsupported engine and metadata survive project state");
      stateService.getState().connections.clear();check(stateService.getState().connections.size()==1,"persistent snapshots are isolated copies");
      var xml=com.intellij.util.xmlb.XmlSerializer.serialize(stateService.getState());
      check(xml.getChildren().size()>0,"real native project serializer accepts secret-free state");
    }finally{stateService.dispose();}
    JdbcSession session=new JdbcSession();session.connect(p,password);
    check(password[0]=='\0',"connect clears caller password");
    check(session.autoCommit(),"new connection auto commits");
    session.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, title TEXT, payload BLOB)");
    session.execute("INSERT INTO sample VALUES(1, '原生 SQL; console', X'0001FF')");
    session.execute("INSERT INTO sample VALUES(2, NULL, NULL)");
    var first=session.execute("SELECT title, payload FROM sample ORDER BY id;");
    check(first.rows().size()==2&&first.rows().getFirst().getFirst().equals("原生 SQL; console"),"Unicode and semicolon SQL");
    check(first.rows().get(1).getFirst()==null,"SQL NULL preserved");
    check(first.rows().getFirst().get(1).startsWith("0x0001ff"),"bounded binary preview");
    session.setAutoCommit(false);session.execute("INSERT INTO sample(id,title) VALUES(3,'rolled back')");session.rollback();session.setAutoCommit(true);
    check(session.execute("SELECT count(*) FROM sample").rows().getFirst().getFirst().equals("2"),"rollback changes nothing");
    session.setAutoCommit(false);session.execute("INSERT INTO sample(id,title) VALUES(3,'committed')");session.commit();session.setAutoCommit(true);
    check(session.execute("SELECT count(*) FROM sample").rows().getFirst().getFirst().equals("3"),"commit persists");
    session.setAutoCommit(false);session.execute("INSERT INTO sample(id,title) VALUES(4,'close rollback')");session.close();session.connect(p,null);
    check(session.execute("SELECT count(*) FROM sample").rows().getFirst().getFirst().equals("3"),"disconnect rolls back open transaction");
    var table=session.tables().stream().filter(t->t.name().equals("sample")).findFirst().orElseThrow();
    check(!session.columns(table).rows().isEmpty(),"real JDBC column metadata");
    check(session.selectSql(table).equals("SELECT * FROM \"sample\";"),"quoted generated SELECT");
    session.execute("CREATE TABLE \"odd\"\"name\"(n INTEGER)");
    var odd=session.tables().stream().filter(t->t.name().equals("odd\"name")).findFirst().orElseThrow();
    check(session.selectSql(odd).equals("SELECT * FROM \"odd\"\"name\";"),"identifier quoting escapes quote");
    var bounded=session.execute("WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<900) SELECT x FROM n");
    check(bounded.rows().size()==JdbcSession.MAX_ROWS&&bounded.truncated(),"500-row JDBC limit");
    var text=session.execute("SELECT replace(hex(zeroblob(3000)), '00', '字') AS large");
    check(text.rows().getFirst().getFirst().length()<=JdbcSession.MAX_CELL+1,"cell preview bounded");
    check(session.execute("UPDATE sample SET title='updated' WHERE id=1").updateCount()==1,"affected row count");
    boolean rejected=false;try{session.execute("DELETE FROM sample; DELETE FROM sample");}catch(IllegalArgumentException expected){rejected=true;}
    check(rejected&&session.execute("SELECT count(*) FROM sample").rows().getFirst().getFirst().equals("3"),"multiple statements rejected before execution");
    SwingUtilities.invokeAndWait(()->{boolean guarded=false;try{session.tables();}catch(IllegalStateException expected){guarded=true;}catch(Exception e){throw new RuntimeException(e);}check(guarded,"JDBC rejects EDT calls");});
    ExecutorService executor=Executors.newSingleThreadExecutor();
    try {
      CountDownLatch started=new CountDownLatch(1);
      Future<Boolean> query=executor.submit(()->{started.countDown();try{session.execute("WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000000000) SELECT sum(x) FROM n");return false;}catch(SQLException cancelled){return true;}});
      check(started.await(2,TimeUnit.SECONDS),"owned query started");
      Thread.sleep(200);session.cancel();check(query.get(5,TimeUnit.SECONDS),"Statement.cancel interrupts real SQLite CPU query");
      check(session.execute("SELECT 42").rows().getFirst().getFirst().equals("42"),"session usable after cancellation");
      long start=System.nanoTime();boolean timedOut=false;
      try{session.execute("WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000000000) SELECT sum(x) FROM n");}catch(SQLException expected){timedOut=true;}
      long elapsed=TimeUnit.NANOSECONDS.toSeconds(System.nanoTime()-start);
      check(timedOut&&elapsed>=14&&elapsed<22,"15-second watchdog cancels CPU query independently of SQLite busy timeout");
    }finally{executor.shutdownNow();session.dispose();}
    try(JdbcSession again=new JdbcSession()) {again.connect(p,null);check(again.execute("SELECT count(*) FROM sample").rows().getFirst().getFirst().equals("3"),"owned database reopens after close");again.dispose();}
    for(DatabaseProfile.Engine engine:List.of(DatabaseProfile.Engine.POSTGRESQL,DatabaseProfile.Engine.MYSQL)){
      DatabaseProfile network=new DatabaseProfile();network.engine=engine.name();network.database="db/name?password=bad";network.user="test";
      String url=network.jdbcUrl();check(url.contains("%2F")&&!url.contains("?"),"database name cannot inject JDBC properties");
      Driver driver=(Driver)Class.forName(engine==DatabaseProfile.Engine.POSTGRESQL?"org.postgresql.Driver":"org.mariadb.jdbc.Driver").getConstructor().newInstance();
      check(driver.acceptsURL(url),"bundled network driver recognizes generated URL without opening network");
      check(network.properties(null).getProperty(engine==DatabaseProfile.Engine.POSTGRESQL?"sslmode":"sslMode").equals("verify-full"),"network TLS hostname verification defaults on");
      network.host="localhost?password=secret";rejects(network::validate,"host URL injection rejected");
    }
    check(SqlText.statements("SELECT ';'; /* a; /* nested */ */ SELECT $$a;b$$;").size()==2,"SQL quote/comment/dollar boundaries");
    check(SqlText.single("-- comment;\nSELECT 'it''s;ok';").contains("it''s"),"escaped quotes preserved");
    check(SqlText.atCaret("SELECT 1; SELECT 2;",15).equals("SELECT 2"),"caret selects SQL statement");
    rejects(()->SqlText.single("SELECT 'unfinished"),"unclosed quote rejected");
    rejects(()->SqlText.single("SELECT 1 /* unfinished"),"unclosed comment rejected");
    rejects(()->SqlText.single("SELECT $$ unfinished"),"unclosed dollar string rejected");
    rejects(()->SqlText.single(" "),"empty SQL rejected");
    rejects(()->SqlText.single("x".repeat(SqlText.MAX_SQL+1)),"SQL size bounded");
    rejects(()->SqlText.forEngine("/* outer /* inner */ SELECT 1; */ SELECT 2;",DatabaseProfile.Engine.SQLITE),"SQLite non-nested comments cannot conceal extra statements");
    rejects(()->SqlText.forEngine("SELECT 'a\\'; DELETE FROM sample; --'",DatabaseProfile.Engine.MYSQL),"ambiguous MySQL escaped quotes cannot conceal extra statements");
    check(Arrays.stream(DatabaseProfile.class.getFields()).noneMatch(f->f.getName().toLowerCase(Locale.ROOT).contains("password")),"persistent profile has no password field");
    String lexText="SELECT 'a;''b', $$multiline\n;string$$; /* nested /* x */ y */ SELECT 2;";
    var lexer=new SqlLanguage.SqlLexer();lexer.start(lexText);List<String> tokens=new ArrayList<>();List<Integer> offsets=new ArrayList<>();
    while(lexer.getTokenType()!=null){tokens.add(lexer.getTokenType()+":"+lexText.substring(lexer.getTokenStart(),lexer.getTokenEnd()));offsets.add(lexer.getTokenStart());lexer.advance();}
    for(int i=0;i<offsets.size();i++){
      lexer.start(lexText,offsets.get(i),lexText.length(),0);List<String> tail=new ArrayList<>();while(lexer.getTokenType()!=null){tail.add(lexer.getTokenType()+":"+lexText.substring(lexer.getTokenStart(),lexer.getTokenEnd()));lexer.advance();}
      check(tail.equals(tokens.subList(i,tokens.size())),"native lexer incremental restart preserves tokens");
    }
    check(Files.deleteIfExists(Path.of(p.file)),"closed SQLite file removable");
    System.out.println("{\"status\":\"pass\",\"checks\":"+checks+",\"sqliteRealConnections\":true,\"queryCancelAndDeadline\":true,\"transactionsAndMetadata\":true,\"connectionsClosed\":true,\"networkServersTested\":false,\"nativeDesktopTested\":false}");
  }
}
