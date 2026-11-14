package dev.openpycharm.database;

import java.util.*;
import static dev.openpycharm.database.SqlCompletionContext.*;
import static dev.openpycharm.database.DatabaseMetadataCache.*;

/** Pure candidates from an immutable snapshot and bounded lexical context. */
public final class SqlCompletionCandidates {
  public static final int MAX_CANDIDATES=200;
  public record Candidate(String name,String insertion,String kind,String detail) {}
  private record Resolved(Binding binding,Table table) {}
  public static List<Candidate> suggest(Snapshot snapshot,Context context){
    if(snapshot==null||context.mode()==Mode.NONE)return List.of();
    Map<String,Candidate> result=new LinkedHashMap<>();
    if(context.mode()==Mode.RELATION){
      if(context.qualifier().isEmpty()){
        for(Table table:snapshot.tables()){
          if(table.schema()!=null&&!table.schema().isBlank())add(result,context,new Candidate(table.schema(),snapshot.quoted(table.schema())+(context.followedByDot()?"":"."),"schema",""));
          add(result,context,new Candidate(table.name(),snapshot.qualified(table),"table/view",table.schema()==null?"":table.schema()));
        }
      }else if(context.qualifier().size()==1){
        Identifier schema=context.qualifier().getFirst();
        for(Table table:snapshot.tables())if(matches(schema,table.schema()))add(result,context,new Candidate(table.name(),snapshot.quoted(table.name()),"table/view",table.schema()));
      }
    } else {
      List<Resolved> sources=resolveBindings(snapshot,context.bindings());
      if(!context.qualifier().isEmpty()){
        List<Table> tables=qualifiedTables(snapshot,context.qualifier(),sources);
        for(Table table:tables)for(Column column:table.columns())add(result,context,new Candidate(column.name(),snapshot.quoted(column.name()),"column",snapshot.qualified(table)+" · "+column.type()));
      }else {
        Map<String,Integer> counts=new HashMap<>();for(Resolved source:sources)for(Column c:source.table.columns())counts.merge(c.name().toLowerCase(Locale.ROOT),1,Integer::sum);
        for(Resolved source:sources){
          if(source.binding.alias()!=null){Identifier alias=source.binding.alias();add(result,context,new Candidate(alias.name(),snapshot.quoted(alias.name())+(context.followedByDot()?"":"."),"alias",snapshot.qualified(source.table)));}
          for(Column column:source.table.columns()){
            String insertion=snapshot.quoted(column.name());
            if(counts.get(column.name().toLowerCase(Locale.ROOT))>1){String qualifier=source.binding.alias()==null?snapshot.qualified(source.table):snapshot.quoted(source.binding.alias().name());insertion=qualifier+"."+insertion;}
            add(result,context,new Candidate(column.name(),insertion,"column",snapshot.qualified(source.table)+" · "+column.type()));
          }
        }
      }
    }
    return result.values().stream().sorted(Comparator.comparing(Candidate::name,String.CASE_INSENSITIVE_ORDER).thenComparing(Candidate::insertion)).limit(MAX_CANDIDATES).toList();
  }
  private static void add(Map<String,Candidate> out,Context context,Candidate candidate){
    if(candidate.name().regionMatches(true,0,context.prefix(),0,context.prefix().length()))out.putIfAbsent(candidate.insertion(),candidate);
  }
  private static List<Resolved> resolveBindings(Snapshot snapshot,List<Binding> bindings){
    List<Resolved> out=new ArrayList<>();
    for(Binding b:bindings){List<Table> matches=snapshot.tables().stream().filter(t->matches(b.table(),t.name())&&(b.schema()==null||matches(b.schema(),t.schema()))).toList();if(matches.size()==1)out.add(new Resolved(b,matches.getFirst()));}
    return out;
  }
  private static List<Table> qualifiedTables(Snapshot snapshot,List<Identifier> q,List<Resolved> sources){
    if(q.size()==1){
      Identifier name=q.getFirst();List<Table> aliases=sources.stream().filter(r->r.binding.alias()!=null&&matches(name,r.binding.alias().name())).map(Resolved::table).toList();
      if(!aliases.isEmpty())return aliases.size()==1?aliases:List.of();
      // A table with an explicit alias must be addressed through that alias.
      if(sources.stream().anyMatch(r->r.binding.alias()!=null&&matches(name,r.table.name())))return List.of();
      List<Table> tables=snapshot.tables().stream().filter(t->matches(name,t.name())).toList();return tables.size()==1?tables:List.of();
    }
    if(q.size()==2)return snapshot.tables().stream().filter(t->matches(q.getFirst(),t.schema())&&matches(q.get(1),t.name())).toList();
    if(q.size()==3)return snapshot.tables().stream().filter(t->matches(q.getFirst(),t.catalog())&&matches(q.get(1),t.schema())&&matches(q.get(2),t.name())).toList();
    return List.of();
  }
  private static boolean matches(Identifier reference,String name){return name!=null&&(reference.quoted()?reference.name().equals(name):reference.name().equalsIgnoreCase(name));}
}
