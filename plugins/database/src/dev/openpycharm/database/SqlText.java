package dev.openpycharm.database;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.Locale;

/** Statement boundaries preserve quoted SQL, comments and PostgreSQL dollar strings. */
public final class SqlText {
  public static final int MAX_SQL = 1024 * 1024;
  public record Span(int start, int end) {}
  public static List<Span> statements(String text) {
    return statements(text,true,false);
  }
  private static List<Span> statements(String text,boolean nestedComments,boolean backslashEscapes) {
    if (text.length()>MAX_SQL) throw new IllegalArgumentException("SQL exceeds the 1 MiB console limit");
    List<Span> out = new ArrayList<>();
    int start=0, i=0; boolean content=false;
    while (i<text.length()) {
      char c=text.charAt(i);
      if (Character.isWhitespace(c)) { i++; continue; }
      if (text.startsWith("--",i)) { int n=text.indexOf('\n',i+2); i=n<0?text.length():n+1; continue; }
      if (text.startsWith("/*",i)) {
        int depth=1; i+=2;
        while (i<text.length() && depth>0) {
          if (nestedComments && text.startsWith("/*",i)) { depth++; i+=2; }
          else if (text.startsWith("*/",i)) { depth--; i+=2; } else i++;
        }
        if (depth!=0) throw new IllegalArgumentException("Unclosed SQL comment");
        continue;
      }
      if (c==';') { if (content) out.add(new Span(start,i)); start=++i; content=false; continue; }
      content=true;
      if (c=='\'' || c=='"' || c=='`' || c=='[') {
        char end=c=='['?']':c; i++; boolean closed=false;
        while (i<text.length()) {
          if(backslashEscapes && (c=='\'' || c=='"') && text.charAt(i)=='\\' && i+1<text.length()) {i+=2;continue;}
          if (text.charAt(i++)==end) { if(i<text.length() && text.charAt(i)==end) i++; else { closed=true; break; } }
        }
        if(!closed) throw new IllegalArgumentException("Unclosed SQL quoted value");
        continue;
      }
      if (c=='$' && (i==0 || !Character.isJavaIdentifierPart(text.charAt(i-1)))) {
        int n=text.indexOf('$',i+1);
        if(n>=0 && text.substring(i+1,n).matches("(?:[A-Za-z_][A-Za-z_0-9]*)?")) {
          String tag=text.substring(i,n+1); int close=text.indexOf(tag,n+1);
          if(close<0) throw new IllegalArgumentException("Unclosed SQL dollar string");
          i=close+tag.length(); continue;
        }
      }
      i++;
    }
    if(content) out.add(new Span(start,text.length()));
    return out;
  }
  public static String single(String text) {
    return single(text,true,false);
  }
  private static String single(String text,boolean nested,boolean escapes) {
    List<Span> parts=statements(text,nested,escapes);
    if(parts.size()!=1) throw new IllegalArgumentException("Run one SQL statement at a time; select the statement to execute");
    Span p=parts.getFirst(); return text.substring(p.start,p.end).trim();
  }
  public static String forEngine(String text,DatabaseProfile.Engine engine) {
    String standard=single(text,engine==DatabaseProfile.Engine.POSTGRESQL,false);
    if(engine!=DatabaseProfile.Engine.SQLITE) {
      // Server SQL modes can change backslash escaping. Execute only an
      // unambiguous single statement under either interpretation.
      String escaped=single(text,engine==DatabaseProfile.Engine.POSTGRESQL,true);
      if(!standard.equals(escaped))throw new IllegalArgumentException("Ambiguous backslash-escaped SQL; use standard doubled quotes");
    }
    String first=leadingKeyword(standard,engine==DatabaseProfile.Engine.POSTGRESQL);
    if(Set.of("ABORT","BEGIN","START","COMMIT","END","ROLLBACK","SAVEPOINT","RELEASE","SET","PREPARE","DISCARD","LOCK","UNLOCK").contains(first))
      throw new IllegalArgumentException("Use Begin transaction, Commit and Rollback buttons; direct transaction/session-control SQL is not supported in this console");
    return standard;
  }
  private static String leadingKeyword(String text,boolean nested) {
    int i=0;
    while(i<text.length()) {
      if(Character.isWhitespace(text.charAt(i))){i++;continue;}
      if(text.startsWith("--",i)){int n=text.indexOf('\n',i+2);i=n<0?text.length():n+1;continue;}
      if(text.startsWith("/*",i)){
        int depth=1;i+=2;
        while(i<text.length()&&depth>0){if(nested&&text.startsWith("/*",i)){depth++;i+=2;}else if(text.startsWith("*/",i)){depth--;i+=2;}else i++;}
        continue;
      }
      int start=i;while(i<text.length()&&Character.isJavaIdentifierPart(text.charAt(i)))i++;
      return text.substring(start,i).toUpperCase(Locale.ROOT);
    }
    return "";
  }
  public static String atCaret(String text,int caret) {
    List<Span> parts=statements(text);
    for(Span p:parts) if(caret>=p.start && caret<=p.end+1) return text.substring(p.start,p.end).trim();
    if(parts.size()==1) { Span p=parts.getFirst();return text.substring(p.start,p.end).trim(); }
    throw new IllegalArgumentException("Place the caret inside a SQL statement");
  }
}
