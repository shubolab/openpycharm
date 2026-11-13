package dev.openpycharm.database;

import com.intellij.lang.Language;
import com.intellij.openapi.fileTypes.LanguageFileType;
import com.intellij.openapi.fileTypes.SyntaxHighlighterBase;
import com.intellij.openapi.fileTypes.SyntaxHighlighterFactory;
import com.intellij.openapi.fileTypes.SyntaxHighlighter;
import com.intellij.openapi.editor.DefaultLanguageHighlighterColors;
import com.intellij.openapi.editor.colors.TextAttributesKey;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.vfs.VirtualFile;
import com.intellij.lexer.Lexer;
import com.intellij.lexer.LexerBase;
import com.intellij.psi.TokenType;
import com.intellij.psi.tree.IElementType;
import com.intellij.icons.AllIcons;
import javax.swing.Icon;
import java.util.Locale;
import java.util.Set;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

public final class SqlLanguage extends Language {
  public static final SqlLanguage INSTANCE=new SqlLanguage();
  private SqlLanguage(){super("OpenPyCharmSQL");}
  public static final class FileType extends LanguageFileType {
    public static final FileType INSTANCE=new FileType();
    private FileType(){super(SqlLanguage.INSTANCE);}
    @Override public @NotNull String getName(){return "OpenPyCharm SQL";}
    @Override public @NotNull String getDescription(){return "SQL database console";}
    @Override public @NotNull String getDefaultExtension(){return "sql";}
    @Override public Icon getIcon(){return AllIcons.FileTypes.Any_type;}
  }
  public static final IElementType KEYWORD=new IElementType("SQL_KEYWORD",INSTANCE), STRING=new IElementType("SQL_STRING",INSTANCE),
    COMMENT=new IElementType("SQL_COMMENT",INSTANCE), NUMBER=new IElementType("SQL_NUMBER",INSTANCE), IDENTIFIER=new IElementType("SQL_IDENTIFIER",INSTANCE), SYMBOL=new IElementType("SQL_SYMBOL",INSTANCE);
  private static final Set<String> WORDS=Set.of("SELECT","FROM","WHERE","JOIN","LEFT","RIGHT","INNER","OUTER","ON","AS","INSERT","INTO","VALUES","UPDATE","SET","DELETE","CREATE","TABLE","VIEW","INDEX","DROP","ALTER","ADD","PRIMARY","KEY","FOREIGN","REFERENCES","NOT","NULL","DEFAULT","UNIQUE","CHECK","AND","OR","IN","IS","LIKE","BETWEEN","EXISTS","GROUP","BY","ORDER","HAVING","ASC","DESC","LIMIT","OFFSET","UNION","ALL","DISTINCT","WITH","RECURSIVE","CASE","WHEN","THEN","ELSE","END","BEGIN","COMMIT","ROLLBACK","EXPLAIN","PRAGMA","RETURNING");
  public static final class SqlLexer extends LexerBase {
    private CharSequence buffer="";private int end,start,next;private IElementType token;
    @Override public void start(@NotNull CharSequence b,int offset,int limit,int state){buffer=b;end=limit;start=offset;locate();}
    private boolean at(String s,int p){return p+s.length()<=end&&buffer.subSequence(p,p+s.length()).toString().equals(s);}
    private void locate(){
      if(start>=end){token=null;next=end;return;}char c=buffer.charAt(start);next=start+1;
      if(Character.isWhitespace(c)){token=TokenType.WHITE_SPACE;while(next<end&&Character.isWhitespace(buffer.charAt(next)))next++;}
      else if(at("--",start)){token=COMMENT;while(next<end&&buffer.charAt(next)!='\n')next++;}
      else if(at("/*",start)){token=COMMENT;next=start+2;int depth=1;while(next<end&&depth>0){if(at("/*",next)){depth++;next+=2;}else if(at("*/",next)){depth--;next+=2;}else next++;}}
      else if(c=='\''||c=='"'||c=='`'||c=='['){token=STRING;char close=c=='['?']':c;while(next<end){if(buffer.charAt(next++)==close){if(next<end&&buffer.charAt(next)==close)next++;else break;}}}
      else if(c=='$') {int p=next;while(p<end&&(Character.isLetterOrDigit(buffer.charAt(p))||buffer.charAt(p)=='_'))p++;if(p<end&&buffer.charAt(p)=='$'){String tag=buffer.subSequence(start,p+1).toString();next=p+1;while(next<end&&!at(tag,next))next++;if(next<end)next+=tag.length();token=STRING;}else token=SYMBOL;}
      else if(Character.isDigit(c)){token=NUMBER;while(next<end&&(Character.isLetterOrDigit(buffer.charAt(next))||buffer.charAt(next)=='.'))next++;}
      else if(Character.isJavaIdentifierStart(c)){while(next<end&&Character.isJavaIdentifierPart(buffer.charAt(next)))next++;token=WORDS.contains(buffer.subSequence(start,next).toString().toUpperCase(Locale.ROOT))?KEYWORD:IDENTIFIER;}
      else token=SYMBOL;
    }
    @Override public int getState(){return 0;}
    @Override public @Nullable IElementType getTokenType(){return token;}
    @Override public int getTokenStart(){return start;}
    @Override public int getTokenEnd(){return next;}
    @Override public void advance(){start=next;locate();}
    @Override public @NotNull CharSequence getBufferSequence(){return buffer;}
    @Override public int getBufferEnd(){return end;}
  }
  public static final class HighlighterFactory extends SyntaxHighlighterFactory {
    @Override public @NotNull SyntaxHighlighter getSyntaxHighlighter(@Nullable Project p,@Nullable VirtualFile f){return new SyntaxHighlighterBase(){
      @Override public @NotNull Lexer getHighlightingLexer(){return new SqlLexer();}
      @Override public TextAttributesKey @NotNull [] getTokenHighlights(IElementType t){
        TextAttributesKey k=t==KEYWORD?DefaultLanguageHighlighterColors.KEYWORD:t==STRING?DefaultLanguageHighlighterColors.STRING:t==COMMENT?DefaultLanguageHighlighterColors.BLOCK_COMMENT:t==NUMBER?DefaultLanguageHighlighterColors.NUMBER:null;
        return k==null?TextAttributesKey.EMPTY_ARRAY:new TextAttributesKey[]{k};
      }
    };}
  }
}
