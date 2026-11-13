package dev.openpycharm.database;

import com.intellij.extapi.psi.ASTWrapperPsiElement;
import com.intellij.extapi.psi.PsiFileBase;
import com.intellij.lang.*;
import com.intellij.lexer.Lexer;
import com.intellij.openapi.fileTypes.FileType;
import com.intellij.openapi.project.Project;
import com.intellij.psi.*;
import com.intellij.psi.tree.*;
import org.jetbrains.annotations.NotNull;

/** Native PSI/token structure, without a dialect-specific semantic SQL engine. */
public final class SqlParserDefinition implements ParserDefinition {
  private static final IFileElementType FILE=new IFileElementType(SqlLanguage.INSTANCE);
  @Override public @NotNull Lexer createLexer(Project project){return new SqlLanguage.SqlLexer();}
  @Override public @NotNull PsiParser createParser(Project project){return (root,builder)->{var mark=builder.mark();while(!builder.eof())builder.advanceLexer();mark.done(root);return builder.getTreeBuilt();};}
  @Override public @NotNull IFileElementType getFileNodeType(){return FILE;}
  @Override public @NotNull TokenSet getWhitespaceTokens(){return TokenSet.create(TokenType.WHITE_SPACE);}
  @Override public @NotNull TokenSet getCommentTokens(){return TokenSet.create(SqlLanguage.COMMENT);}
  @Override public @NotNull TokenSet getStringLiteralElements(){return TokenSet.create(SqlLanguage.STRING);}
  @Override public @NotNull PsiElement createElement(ASTNode node){return new ASTWrapperPsiElement(node);}
  @Override public @NotNull PsiFile createFile(@NotNull FileViewProvider viewProvider){return new PsiFileBase(viewProvider,SqlLanguage.INSTANCE){@Override public @NotNull FileType getFileType(){return SqlLanguage.FileType.INSTANCE;}};}
  @Override public @NotNull SpaceRequirements spaceExistenceTypeBetweenTokens(ASTNode left,ASTNode right){return SpaceRequirements.MAY;}
}
