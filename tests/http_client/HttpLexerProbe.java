package dev.openpycharm.http;

import com.intellij.lexer.LexerPosition;
import com.intellij.psi.tree.IElementType;
import dev.openpycharm.http.lang.HttpRequestLexer;
import dev.openpycharm.http.lang.HttpRequestTokens;
import java.util.ArrayList;
import java.util.List;

/** Check IntelliJ's token-start-state/restart/restore contract against the emitted plugin. */
public final class HttpLexerProbe {
  private record Token(int start, int end, int state, IElementType type) { }

  public static void main(String[] arguments) {
    List<String> inputs = new ArrayList<>(List.of(
      "GET http://localhost/a HTTP/1.1\r\nX-Probe: value\r\n\r\n### Next\nPOST {{base}}/b\nContent-Type: application/json\n\n{\"hello\":\"你好😀\",\"n\":1}",
      "@base = http://localhost\n# comment\n// comment\n  PATCH\t{{base}}/path\n\n[true, null, 1.25]\n### End\nHEAD https://example.invalid/",
      "GET", "GET \t", "GET http://localhost/path", "\n\t\r\n"
    ));
    int physicalLineCases = 0;
    for (String newline : List.of("\n", "\r\n")) {
      for (String fragment : List.of("don't change this", "\"unterminated", "'unterminated",
                                    "\"unterminated\\", "'unterminated\\", "{{unfinished", "prefix {{unfinished",
                                    "{{complete}}", "\"valid \\\"quote\\\" and don't\"")) {
        String text = "POST http://localhost/a" + newline + "Content-Type: text/plain" + newline + newline + fragment + newline
          + "### Next" + newline + "GET http://localhost/b" + newline;
        assertNextRequestVisible(text);
        inputs.add(text);
        physicalLineCases++;
      }
      String headerVariable = "GET http://localhost/a" + newline + "X-Probe: {{unfinished" + newline
        + newline + "### Next" + newline + "GET http://localhost/b" + newline;
      assertNextRequestVisible(headerVariable);
      inputs.add(headerVariable);
      physicalLineCases++;
    }
    int restartChecks = 0;
    int restoreChecks = 0;
    for (String text : inputs) {
      List<Token> baseline = scan(text);
      for (int index = 0; index < baseline.size(); index++) {
        Token token = baseline.get(index);
        HttpRequestLexer restarted = new HttpRequestLexer();
        restarted.start(text, token.start(), text.length(), token.state());
        for (int suffix = index; suffix < baseline.size(); suffix++) {
          equal(baseline.get(suffix), current(restarted), "restart at " + token.start());
          restarted.advance();
          restartChecks++;
        }
        if (restarted.getTokenType() != null) throw new AssertionError("Restart did not reach EOF");
      }
      HttpRequestLexer restoring = new HttpRequestLexer();
      restoring.start(text, 0, text.length(), 0);
      for (Token expected : baseline) {
        LexerPosition position = restoring.getCurrentPosition();
        restoring.advance();
        if (restoring.getTokenType() != null) restoring.advance();
        restoring.restore(position);
        equal(expected, current(restoring), "restore at " + position.getOffset());
        restoring.advance();
        restoreChecks++;
      }
      LexerPosition eof = restoring.getCurrentPosition();
      restoring.restore(eof);
      if (restoring.getTokenType() != null || restoring.getTokenStart() != text.length()) {
        throw new AssertionError("Restoring EOF changed its position");
      }
    }
    HttpRequestLexer first = new HttpRequestLexer();
    first.start("GET http://localhost/", 0, 21, 0);
    if (first.getTokenType() != HttpRequestTokens.INSTANCE.getMETHOD()) throw new AssertionError("GET is not a method");
    System.out.println("{\"status\":\"pass\",\"documents\":" + inputs.size() + ",\"physicalLineCases\":" + physicalLineCases + ",\"restartSuffixTokenChecks\":" + restartChecks + ",\"restoreChecks\":" + restoreChecks + "}");
  }

  private static void assertNextRequestVisible(String text) {
    List<Token> tokens = scan(text);
    List<String> methods = tokens.stream().filter(token -> token.type() == HttpRequestTokens.INSTANCE.getMETHOD())
      .map(token -> text.substring(token.start(), token.end())).toList();
    if (methods.size() != 2 || tokens.stream().filter(token -> token.type() == HttpRequestTokens.INSTANCE.getSEPARATOR()).count() != 1) {
      throw new AssertionError("A quote or unfinished variable swallowed the next ###/GET request: " + text.replace("\r", "\\r").replace("\n", "\\n"));
    }
    if (tokens.stream().noneMatch(token -> token.type() == HttpRequestTokens.INSTANCE.getURL()
        && text.substring(token.start(), token.end()).equals("http://localhost/b"))) {
      throw new AssertionError("The next request target is not a URL token");
    }
    for (Token token : tokens) {
      if (token.type() == HttpRequestTokens.INSTANCE.getSTRING() || token.type() == HttpRequestTokens.INSTANCE.getVARIABLE()) {
        String value = text.substring(token.start(), token.end());
        if (value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0) throw new AssertionError("String/variable token crossed a physical line");
      }
    }
    if (text.contains("{{complete}}") && tokens.stream().noneMatch(token -> token.type() == HttpRequestTokens.INSTANCE.getVARIABLE()
        && text.substring(token.start(), token.end()).equals("{{complete}}"))) {
      throw new AssertionError("A complete same-line variable was damaged");
    }
  }

  private static List<Token> scan(String text) {
    HttpRequestLexer lexer = new HttpRequestLexer();
    lexer.start(text, 0, text.length(), 0);
    List<Token> tokens = new ArrayList<>();
    while (lexer.getTokenType() != null) {
      if (lexer.getTokenEnd() <= lexer.getTokenStart()) throw new AssertionError("Lexer made no progress");
      tokens.add(current(lexer));
      lexer.advance();
    }
    return tokens;
  }

  private static Token current(HttpRequestLexer lexer) {
    return new Token(lexer.getTokenStart(), lexer.getTokenEnd(), lexer.getState(), lexer.getTokenType());
  }

  private static void equal(Token expected, Token actual, String context) {
    if (!expected.equals(actual)) throw new AssertionError(context + ": expected " + expected + ", actual " + actual);
  }
}
