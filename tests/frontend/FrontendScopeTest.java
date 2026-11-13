package dev.openpycharm.frontend;

public final class FrontendScopeTest {
  private static int checks;
  public static void main(String[] args) {
    for (String base : new String[]{"/owned/测试 space", "C:/owned/测试 space"}) {
      String parent = base + "/.tools/frontend-m0-fixtures", cache = base + "/.tools/frontend-m0-tools";
      String nonce = "0123456789abcdef0123456789abcdef", root = parent + "/fixture-" + nonce;
      String receipt = cache + "/runtime/macos-arm64/hash/frontend-tools.json", hash = "a".repeat(64);
      for (String suffix : new String[]{"main.ts", "main.js", "组件.tsx", "视图.jsx"})
        require(FrontendFixtureScope.evaluate(true,parent,cache,root,root+"/"+suffix,root,nonce,receipt,hash).isPresent(), "Owned fixture rejected");
      require(FrontendFixtureScope.evaluate(false,parent,cache,root,root+"/main.ts",root,nonce,receipt,hash).isEmpty(), "M0 not default off");
      require(FrontendFixtureScope.evaluate(true,parent,cache,base+"/user-project",root+"/main.ts",root,nonce,receipt,hash).isEmpty(), "Non-fixture project accepted");
      require(FrontendFixtureScope.evaluate(true,parent,cache,root,base+"/user.ts",root,nonce,receipt,hash).isEmpty(), "Non-fixture file accepted");
      require(FrontendFixtureScope.evaluate(true,parent,cache,root,root+"-other/main.ts",root,nonce,receipt,hash).isEmpty(), "Sibling prefix accepted");
      require(FrontendFixtureScope.evaluate(true,parent,cache,root,root+"/main.py",root,nonce,receipt,hash).isEmpty(), "Python file intercepted");
      require(FrontendFixtureScope.evaluate(true,parent,cache,root,root+"/main.ts",root,nonce,base+"/user/frontend-tools.json",hash).isEmpty(), "User cache accepted");
      for (String invalid : new String[]{null,"", "../file", "file:///path", root+"/../main.ts", root+"/./main.ts", root+"/x\n.ts", root+"/x\\main.ts"})
        require(FrontendFixtureScope.evaluate(true,parent,cache,root,invalid,root,nonce,receipt,hash).isEmpty(), "Unsafe file accepted");
      require(FrontendFixtureScope.evaluate(true,parent,cache,root,root+"/main.ts",root,"wrong",receipt,hash).isEmpty(), "Wrong nonce accepted");
      require(FrontendFixtureScope.evaluate(true,parent,cache,root,root+"/main.ts",root,nonce,receipt,"bad").isEmpty(), "Wrong hash accepted");
    }
    require("javascript".equals(FrontendFixtureScope.languageId("a.js")), "JS language ID");
    require("typescriptreact".equals(FrontendFixtureScope.languageId("a.tsx")), "TSX language ID");
    System.out.println("{\"status\":\"pass\",\"pureScopeChecks\":"+checks+",\"nativeIdeStarted\":false}");
  }
  private static void require(boolean condition, String message) { checks++; if (!condition) throw new AssertionError(message); }
}
