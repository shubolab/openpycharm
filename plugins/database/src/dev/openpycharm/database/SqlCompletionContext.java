package dev.openpycharm.database;

import java.util.*;

/** Bounded lexical SQL context; no PSI resolution, services, filesystem or JDBC calls. */
public final class SqlCompletionContext {
  public static final int MAX_TEXT=128*1024,MAX_TOKENS=12000;
  public static final int MAX_IDENTIFIER=1024,MAX_RAW_PREFIX=2*MAX_IDENTIFIER+2;
  public enum Mode { NONE, RELATION, COLUMN }
  public record Identifier(String name,boolean quoted) {}
  public record Binding(Identifier schema,Identifier table,Identifier alias) {}
  public record Context(Mode mode,String prefix,String rawPrefix,int replaceStart,int replaceEnd,boolean followedByDot,List<Identifier> qualifier,List<Binding> bindings) {
    public Context {qualifier=List.copyOf(qualifier);bindings=List.copyOf(bindings);}
  }
  private enum Kind { WORD, IDENTIFIER, STRING, COMMENT, DOT, COMMA, SEMICOLON, LEFT, RIGHT, OTHER }
  private record Token(Kind kind,String text,int start,int end,boolean closed) {
    boolean identifier(){return kind==Kind.WORD||kind==Kind.IDENTIFIER;}
    Identifier id(){return new Identifier(text,kind==Kind.IDENTIFIER);}
    String word(){return kind==Kind.WORD?text.toUpperCase(Locale.ROOT):"";}
  }
  private static final Set<String> RELATIONS=Set.of("FROM","JOIN","UPDATE","INTO","TABLE");
  private static final Set<String> CLAUSES=Set.of("SELECT","FROM","JOIN","UPDATE","INTO","TABLE","WHERE","ON","GROUP","ORDER","HAVING","RETURNING","SET","VALUES","LIMIT","OFFSET","UNION");
  private static final Set<String> RESERVED=Set.of("SELECT","FROM","JOIN","UPDATE","INTO","TABLE","WHERE","ON","GROUP","ORDER","HAVING","RETURNING","SET","VALUES","LIMIT","OFFSET","UNION","AS","LEFT","RIGHT","INNER","OUTER","CROSS","FULL","NATURAL","USING","BY","AND","OR","ASC","DESC","DISTINCT","ALL","WHEN","THEN","ELSE","END");
  private static final Set<String> BIND_RELATIONS=Set.of("FROM","JOIN","UPDATE","INTO"),END_FROM=Set.of("WHERE","ON","GROUP","ORDER","HAVING","SET","VALUES","RETURNING","LIMIT","UNION");
  private static Context none(int caret){return new Context(Mode.NONE,"","",caret,caret,false,List.of(),List.of());}
  public static Context analyze(String sql,int caret){
    if(sql.length()>MAX_TEXT||caret<0||caret>sql.length())return none(Math.max(0,caret));
    List<Token> all=lex(sql);if(all==null)return none(caret);
    int statementStart=0,statementEnd=sql.length();
    for(Token t:all)if(t.kind==Kind.SEMICOLON){if(t.end<=caret)statementStart=t.end;else if(t.start>=caret){statementEnd=t.start;break;}}
    Token current=null;
    for(Token t:all){
      if(t.start<caret&&caret<=t.end){
        if(t.kind==Kind.STRING||t.kind==Kind.COMMENT)return none(caret);
        if(t.identifier())current=t;
      }
    }
    List<Token> tokens=new ArrayList<>();
    for(Token t:all)if(t.start>=statementStart&&t.end<=statementEnd&&t.kind!=Kind.COMMENT)tokens.add(t);
    // Avoid aliases crossing unsupported CTE, compound-arm or nested scopes.
    for(Token t:tokens)if(Set.of("WITH","UNION","INTERSECT","EXCEPT").contains(t.word()))return none(caret);
    for(int i=0;i+1<tokens.size();i++)if(tokens.get(i).kind==Kind.LEFT&&Set.of("SELECT","WITH").contains(tokens.get(i+1).word()))return none(caret);
    int start=current==null?caret:current.start,end=current==null?caret:current.end;
    if(end-start>MAX_RAW_PREFIX)return none(caret);
    String rawPrefix=sql.substring(start,caret),prefix=decodedIdentifierPrefix(rawPrefix);
    if(prefix==null)return none(caret);
    List<Token> before=new ArrayList<>();for(Token t:tokens)if(t.end<=start)before.add(t);
    List<Identifier> qualifier=new ArrayList<>();int at=before.size()-1;
    if(at>=0&&before.get(at).kind==Kind.DOT){
      while(at>=1&&before.get(at).kind==Kind.DOT&&before.get(at-1).identifier()){
        qualifier.addFirst(before.get(at-1).id());at-=2;
        if(qualifier.size()>3)return none(caret);
      }
      if(qualifier.isEmpty())return none(caret);
    }
    String previous=at>=0?before.get(at).word():"";
    Mode mode;
    if(RELATIONS.contains(previous))mode=Mode.RELATION;
    else {
      String clause="";for(int i=at;i>=0;i--)if(CLAUSES.contains(before.get(i).word())){clause=before.get(i).word();break;}
      if(at>=0&&before.get(at).kind==Kind.COMMA&&(clause.equals("FROM")||clause.equals("JOIN")))mode=Mode.RELATION;
      else if((clause.equals("FROM")||clause.equals("JOIN")||clause.equals("TABLE"))&&qualifier.isEmpty())mode=Mode.NONE;
      else if(Set.of("SELECT","WHERE","ON","GROUP","ORDER","HAVING","SET","RETURNING","UPDATE","INTO").contains(clause)||!qualifier.isEmpty())mode=Mode.COLUMN;
      else mode=Mode.NONE;
    }
    boolean followedByDot=false;for(Token t:tokens)if(t.start>=end){followedByDot=t.kind==Kind.DOT;break;}
    return new Context(mode,prefix,rawPrefix,start,end,followedByDot,qualifier,bindings(tokens));
  }
  /** Raw UTF-16 length belongs to native replacement; decoded text belongs to name matching. */
  static String decodedIdentifierPrefix(String raw){
    if(raw.length()>MAX_RAW_PREFIX)return null;
    if(raw.isEmpty())return "";
    char open=raw.charAt(0),close=open=='['?']':open;
    boolean quoted=open=='"'||open=='`'||open=='[';
    StringBuilder decoded=new StringBuilder();
    for(int i=quoted?1:0;i<raw.length();){
      int cp=raw.codePointAt(i),width=Character.charCount(cp);
      if(cp>=Character.MIN_SURROGATE&&cp<=Character.MAX_SURROGATE)return null;
      if(quoted&&cp==close){
        if(i+1<raw.length()&&raw.charAt(i+1)==close){decoded.append(close);i+=2;}
        else if(i+1==raw.length())break;
        else return null;
      }else {
        if(!quoted&&!(i==0?Character.isJavaIdentifierStart(cp):Character.isJavaIdentifierPart(cp)))return null;
        decoded.appendCodePoint(cp);i+=width;
      }
      if(decoded.length()>MAX_IDENTIFIER)return null;
    }
    return decoded.toString();
  }
  private static List<Binding> bindings(List<Token> tokens){
    List<Binding> out=new ArrayList<>();boolean fromList=false;int depth=0;
    for(int i=0;i<tokens.size();i++){
      Token t=tokens.get(i);if(t.kind==Kind.LEFT){depth++;continue;}if(t.kind==Kind.RIGHT){depth--;continue;}
      if(depth!=0)continue;
      String word=t.word();boolean relation=BIND_RELATIONS.contains(word)||(fromList&&t.kind==Kind.COMMA);
      if(END_FROM.contains(word))fromList=false;
      if(!relation)continue;
      if(word.equals("FROM")||word.equals("JOIN"))fromList=true;
      int p=i+1;if(p>=tokens.size()||!tokens.get(p).identifier()||RESERVED.contains(tokens.get(p).word()))continue;
      Identifier first=tokens.get(p++).id(),schema=null,table=first;
      if(p+1<tokens.size()&&tokens.get(p).kind==Kind.DOT&&tokens.get(p+1).identifier()){schema=first;table=tokens.get(p+1).id();p+=2;}
      Identifier alias=null;
      if(p<tokens.size()&&tokens.get(p).word().equals("AS"))p++;
      if(p<tokens.size()&&tokens.get(p).identifier()&&!RESERVED.contains(tokens.get(p).word()))alias=tokens.get(p).id();
      out.add(new Binding(schema,table,alias));
      if(out.size()>=64)break;
    }
    return out;
  }
  private static List<Token> lex(String text){
    List<Token> out=new ArrayList<>();int i=0,n=text.length();
    while(i<n){
      char c=text.charAt(i);if(Character.isWhitespace(c)){i++;continue;}
      int start=i;Kind kind;String value;boolean closed=true;
      if(text.startsWith("--",i)){kind=Kind.COMMENT;int end=text.indexOf('\n',i+2);i=end<0?n:end;value="";}
      else if(text.startsWith("/*",i)){kind=Kind.COMMENT;i+=2;int depth=1;while(i<n&&depth>0){if(text.startsWith("/*",i)){depth++;i+=2;}else if(text.startsWith("*/",i)){depth--;i+=2;}else i++;}closed=depth==0;value="";}
      else if(c=='\''||c=='"'||c=='`'||c=='['){
        kind=c=='\''?Kind.STRING:Kind.IDENTIFIER;char close=c=='['?']':c;i++;StringBuilder decoded=new StringBuilder();closed=false;
        while(i<n){char next=text.charAt(i++);if(c=='\''&&next=='\\'&&i<n){decoded.append(next).append(text.charAt(i++));continue;}if(next==close){if(i<n&&text.charAt(i)==close){decoded.append(close);i++;}else{closed=true;break;}}else decoded.append(next);}
        value=decoded.toString();
      }
      else if(c=='$'&&dollarTag(text,i)!=null){String tag=dollarTag(text,i);kind=Kind.STRING;int end=text.indexOf(tag,i+tag.length());closed=end>=0;i=closed?end+tag.length():n;value="";}
      else if(Character.isJavaIdentifierStart(text.codePointAt(i))){kind=Kind.WORD;i+=Character.charCount(text.codePointAt(i));while(i<n&&Character.isJavaIdentifierPart(text.codePointAt(i)))i+=Character.charCount(text.codePointAt(i));value=text.substring(start,i);}
      else {kind=switch(c){case '.'->Kind.DOT;case ','->Kind.COMMA;case ';'->Kind.SEMICOLON;case '('->Kind.LEFT;case ')'->Kind.RIGHT;default->Kind.OTHER;};value=Character.toString(c);i++;}
      out.add(new Token(kind,value,start,i,closed));if(out.size()>MAX_TOKENS)return null;
    }
    return out;
  }
  private static String dollarTag(String text,int offset){int end=text.indexOf('$',offset+1);if(end<0)return null;String body=text.substring(offset+1,end);return body.matches("(?:[A-Za-z_][A-Za-z_0-9]*)?")?text.substring(offset,end+1):null;}
}
