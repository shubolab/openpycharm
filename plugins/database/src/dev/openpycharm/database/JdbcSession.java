package dev.openpycharm.database;

import javax.swing.SwingUtilities;
import java.io.Reader;
import java.io.InputStream;
import java.sql.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.*;

/** One owned connection, used serially by a background worker; cancel has its own lane. */
public final class JdbcSession implements AutoCloseable {
  public static final int MAX_ROWS=500, MAX_COLUMNS=100, MAX_CELL=4096, MAX_RESULT_CHARS=2*1024*1024;
  private Connection connection;
  private DatabaseProfile.Engine engine;
  private volatile Statement active;
  private final AtomicBoolean cancelled = new AtomicBoolean();
  private final ScheduledExecutorService deadline=Executors.newSingleThreadScheduledExecutor(r->{Thread t=new Thread(r,"OpenPyCharm-JDBC-deadline");t.setDaemon(true);return t;});
  public record Result(List<String> columns,List<List<String>> rows,int updateCount,boolean truncated,long elapsedMillis) {}
  public record Table(String catalog,String schema,String name,String type) {
    @Override public String toString() { return (schema==null||schema.isBlank()?"":schema+".")+name+" ["+type+"]"; }
  }
  static void background() { if(SwingUtilities.isEventDispatchThread()) throw new IllegalStateException("JDBC work must run off the event dispatch thread"); }
  public void connect(DatabaseProfile p,char[] password) throws Exception {
    background(); p.validate(); close();
    Driver driver=(Driver)Class.forName(switch(p.kind()) {
      case SQLITE -> "org.sqlite.JDBC"; case POSTGRESQL -> "org.postgresql.Driver"; case MYSQL -> "org.mariadb.jdbc.Driver";
    }).getConstructor().newInstance();
    Properties properties=p.properties(password);
    try {
      connection=driver.connect(p.jdbcUrl(),properties);
      if(connection==null) throw new SQLException("The driver rejected this connection profile");
      connection.setAutoCommit(true);
      engine=p.kind();
    } catch(Exception e) {try{close();}catch(Exception close){e.addSuppressed(close);}throw e;}
    finally { properties.remove("password"); if(password!=null) Arrays.fill(password,'\0'); }
  }
  private Connection connected() throws SQLException {
    background(); if(connection==null || connection.isClosed()) throw new SQLException("Connect to a database first"); return connection;
  }
  public boolean autoCommit() throws SQLException { return connected().getAutoCommit(); }
  public void setAutoCommit(boolean value) throws SQLException { connected().setAutoCommit(value); }
  public void commit() throws SQLException { connected().commit(); }
  public void rollback() throws SQLException { connected().rollback(); }
  public Result execute(String sql) throws Exception {
    Connection c=connected(); sql=SqlText.forEngine(sql,engine); cancelled.set(false); long start=System.nanoTime();
    ScheduledFuture<?> alarm=null;
    try(Statement s=c.createStatement()) {
      active=s; s.setQueryTimeout(15); s.setMaxRows(MAX_ROWS+1);
      alarm=deadline.schedule(()->{try{s.cancel();}catch(SQLException ignored){}},15,TimeUnit.SECONDS);
      if(cancelled.get()) throw new SQLException("Query cancelled");
      if(s.execute(sql)) try(ResultSet rs=s.getResultSet()) { return read(rs,start); }
      return new Result(List.of(),List.of(),s.getUpdateCount(),false,(System.nanoTime()-start)/1_000_000);
    } finally { if(alarm!=null)alarm.cancel(false);active=null; }
  }
  public void cancel() throws SQLException { background(); cancelled.set(true); Statement s=active;if(s!=null) s.cancel(); }
  static Result read(ResultSet rs,long start) throws Exception {
    ResultSetMetaData md=rs.getMetaData(); int count=Math.min(md.getColumnCount(),MAX_COLUMNS), chars=0;
    boolean truncated=md.getColumnCount()>count; List<String> columns=new ArrayList<>(); List<List<String>> rows=new ArrayList<>();
    for(int i=1;i<=count;i++) columns.add(md.getColumnLabel(i));
    while(rs.next()) {
      if(rows.size()>=MAX_ROWS) {truncated=true;break;}
      List<String> row=new ArrayList<>();
      for(int i=1;i<=count;i++) {
        String value;
        int type=md.getColumnType(i);
        if(type==Types.BLOB || type==Types.BINARY || type==Types.VARBINARY || type==Types.LONGVARBINARY) {
          try(InputStream in=rs.getBinaryStream(i)) { value=in==null?null:HexFormat.of().formatHex(in.readNBytes(64));if(value!=null)value="0x"+value+" (binary preview)"; }
        } else {
          try(Reader in=rs.getCharacterStream(i)) {
            if(in==null) value=null;
            else { char[] data=new char[MAX_CELL+1];int n=0,k;while(n<data.length && (k=in.read(data,n,data.length-n))!=-1)n+=k;
              value=new String(data,0,Math.min(n,MAX_CELL))+(n>MAX_CELL?"…":"");if(n>MAX_CELL)truncated=true; }
          }
        }
        chars+=value==null?0:value.length(); row.add(value);
      }
      if(chars>MAX_RESULT_CHARS) { truncated=true;break; }
      rows.add(Collections.unmodifiableList(row));
    }
    return new Result(List.copyOf(columns),List.copyOf(rows),-1,truncated,(System.nanoTime()-start)/1_000_000);
  }
  public List<Table> tables() throws SQLException {
    DatabaseMetaData m=connected().getMetaData();List<Table> out=new ArrayList<>();
    try(ResultSet rs=m.getTables(connection.getCatalog(),null,"%",new String[]{"TABLE","VIEW"})) {
      while(out.size()<MAX_ROWS && rs.next()) out.add(new Table(rs.getString("TABLE_CAT"),rs.getString("TABLE_SCHEM"),rs.getString("TABLE_NAME"),rs.getString("TABLE_TYPE")));
    }
    return List.copyOf(out);
  }
  public Result columns(Table t) throws Exception {
    DatabaseMetaData m=connected().getMetaData();long start=System.nanoTime();
    try(ResultSet rs=m.getColumns(t.catalog,t.schema,t.name,"%")) {return read(rs,start);}
  }
  public String selectSql(Table t) throws SQLException {
    String q=connected().getMetaData().getIdentifierQuoteString().trim(); if(q.isEmpty()) q="\"";
    String table=quote(q,t.name);if(t.schema!=null&&!t.schema.isBlank())table=quote(q,t.schema)+"."+table;
    return "SELECT * FROM "+table+";";
  }
  private static String quote(String q,String value) {return q+value.replace(q,q+q)+q;}
  @Override public void close() throws SQLException {
    background();Connection c=connection;connection=null;
    if(c!=null) try {if(!c.isClosed()&&!c.getAutoCommit())c.rollback();} finally {c.close();}
  }
  public void dispose() throws SQLException {try{close();}finally{deadline.shutdownNow();}}
}
