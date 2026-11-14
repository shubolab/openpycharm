package dev.openpycharm.notebooks.saveprobe;

import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

/** Filesystem boundaries only; never initializes an application, creates a Project or grants trust. */
public final class NotebookSaveOwnedProjectTest {
  private static int checks;private static boolean symlinksSupported=true;
  private static void check(boolean value,String message){checks++;if(!value)throw new AssertionError(message);}
  private interface Checked {void run()throws Exception;}
  private static void reject(Checked task)throws Exception{try{task.run();throw new AssertionError("Unsafe owned-project input was accepted");}catch(IllegalStateException expected){checks++;}}
  public static void main(String[] args)throws Exception{
    Path parent=Path.of(args[0]),root=Files.createTempDirectory(parent,"owned-project-boundary-"),app=Files.createTempDirectory(parent,"owned-product-boundary-");
    try {
      Path project=Files.createDirectory(root.resolve("project")),profile=Files.createDirectory(root.resolve("profile")),fixture=project.resolve("native-save.ipynb"),report=root.resolve("native-report.json");
      Files.writeString(fixture,"{\"generated\":\"中文\"}\n");String hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(fixture)));
      var owned=NotebookSaveOwnedProject.validate(root,project,fixture,profile,app,report,hash);check(owned.fixture().equals(fixture)&&owned.hash().equals(hash),"Valid generated fixture boundary");
      reject(()->NotebookSaveOwnedProject.validate(root,project,fixture,profile,app,report,"0".repeat(64)));
      reject(()->NotebookSaveOwnedProject.validate(root,project,fixture,profile,app,root.resolve("other-report.json"),hash));
      reject(()->NotebookSaveOwnedProject.validate(root,project,fixture,profile,root,report,hash));
      Path other=Files.createDirectory(root.resolve("other-profile"));reject(()->NotebookSaveOwnedProject.validate(root,project,fixture,other,app,report,hash));
      Path metadata=Files.createDirectory(project.resolve(".idea"));reject(()->NotebookSaveOwnedProject.validate(root,project,fixture,profile,app,report,hash));Files.delete(metadata);
      Path module=project.resolve("foreign.iml");Files.writeString(module,"<module/>");reject(()->NotebookSaveOwnedProject.validate(root,project,fixture,profile,app,report,hash));Files.delete(module);
      Path escaped=root.resolve("outside.ipynb");Files.copy(fixture,escaped);reject(()->NotebookSaveOwnedProject.validate(root,project,escaped,profile,app,report,hash));
      try {
        Files.delete(fixture);Files.createSymbolicLink(fixture,escaped);reject(()->NotebookSaveOwnedProject.validate(root,project,fixture,profile,app,report,hash));Files.delete(fixture);Files.copy(escaped,fixture);
        Path link=root.resolve("linked-profile");Files.createSymbolicLink(link,profile);reject(()->NotebookSaveOwnedProject.validate(root,project,fixture,link,app,report,hash));Files.delete(link);
      }catch(UnsupportedOperationException|FileSystemException unavailable){symlinksSupported=false;if(Files.isSymbolicLink(fixture))Files.delete(fixture);if(!Files.exists(fixture))Files.copy(escaped,fixture);}
      Files.writeString(fixture,"x".repeat(256*1024+1));reject(()->NotebookSaveOwnedProject.validate(root,project,fixture,profile,app,report,hash));
      System.out.println("{\"status\":\"pass\",\"checks\":"+checks+",\"symlinkControlsSupported\":"+symlinksSupported+",\"nativeApplicationLaunched\":false,\"projectTrustGranted\":false}");
    } finally {
      for(Path directory:List.of(root,app))try(var paths=Files.walk(directory)){for(Path path:paths.sorted(Comparator.reverseOrder()).toList())Files.deleteIfExists(path);}
    }
  }
}
