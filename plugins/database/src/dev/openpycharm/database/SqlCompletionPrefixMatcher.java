package dev.openpycharm.database;

import com.intellij.codeInsight.completion.PrefixMatcher;
import org.jetbrains.annotations.NotNull;

/** Native lookup must replace raw quoted text, while candidates match decoded identifiers. */
final class SqlCompletionPrefixMatcher extends PrefixMatcher {
  private final String decoded;
  SqlCompletionPrefixMatcher(String rawPrefix){super(rawPrefix);decoded=SqlCompletionContext.decodedIdentifierPrefix(rawPrefix);}
  @Override public boolean prefixMatches(@NotNull String name){
    return decoded!=null&&name.regionMatches(true,0,decoded,0,decoded.length());
  }
  @Override public @NotNull PrefixMatcher cloneWithPrefix(@NotNull String prefix){return new SqlCompletionPrefixMatcher(prefix);}
}
