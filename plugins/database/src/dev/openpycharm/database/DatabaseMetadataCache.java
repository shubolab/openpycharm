package dev.openpycharm.database;

import java.util.List;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.LongSupplier;

/** Immutable in-memory metadata only. Reads never connect, schedule work or perform I/O. */
public final class DatabaseMetadataCache {
  public static final long MAX_AGE_NANOS=java.util.concurrent.TimeUnit.MINUTES.toNanos(5);
  public record Column(String name,String type) {}
  public record Table(String catalog,String schema,String name,List<Column> columns) {
    public Table {columns=List.copyOf(columns);}
  }
  public record Snapshot(String quote,List<Table> tables,boolean truncated,long capturedAtNanos) {
    public Snapshot {tables=List.copyOf(tables);}
    public String quoted(String name) {
      String open=quote==null||quote.isBlank()?"\"":quote;
      String close=open.equals("[")?"]":open;
      return open+name.replace(close,close+close)+close;
    }
    public String qualified(Table table) {return table.schema==null||table.schema.isBlank()?quoted(table.name):quoted(table.schema)+"."+quoted(table.name);}
  }
  public record Token(long value) {}
  private record State(Token token,Snapshot snapshot) {}
  private final AtomicLong sequence=new AtomicLong();
  private final AtomicReference<State> state=new AtomicReference<>(new State(null,null));
  private final LongSupplier clock;
  public DatabaseMetadataCache(){this(System::nanoTime);}
  DatabaseMetadataCache(LongSupplier clock){this.clock=clock;}
  public void connected(){state.set(new State(new Token(sequence.incrementAndGet()),null));}
  public void disconnected(){state.set(new State(null,null));}
  public Token beginRefresh(){
    for(;;){State old=state.get();if(old.token==null)return null;Token token=new Token(sequence.incrementAndGet());if(state.compareAndSet(old,new State(token,null)))return token;}
  }
  public void invalidate(){beginRefresh();}
  public boolean publish(Token token,String quote,List<Table> tables,boolean truncated){
    if(token==null)return false;
    for(;;){State old=state.get();if(old.token!=token)return false;Snapshot snapshot=new Snapshot(quote,tables,truncated,clock.getAsLong());if(state.compareAndSet(old,new State(token,snapshot)))return true;}
  }
  public Snapshot current(){State current=state.get();Snapshot s=current.snapshot;if(current.token==null||s==null)return null;long age=clock.getAsLong()-s.capturedAtNanos;return age>=0&&age<=MAX_AGE_NANOS?s:null;}
}
