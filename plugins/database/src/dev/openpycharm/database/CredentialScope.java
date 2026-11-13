package dev.openpycharm.database;

import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

/** PasswordSafe isolation includes canonical project and the entire generated endpoint. */
public final class CredentialScope {
  public static String key(String projectPath,DatabaseProfile profile) {
    JdbcSession.background();String root;
    try {root=Path.of(projectPath).toRealPath().toString();}
    catch(java.io.IOException e){root=Path.of(projectPath).toAbsolutePath().normalize().toString();}
    String scope=root+"\0"+profile.jdbcUrl()+"\0"+profile.user+"\0"+profile.id+"\0verifyTls="+profile.verifyTls;
    try{return "OpenPyCharm Database:"+HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(scope.getBytes(StandardCharsets.UTF_8)));}
    catch(java.security.NoSuchAlgorithmException e){throw new IllegalStateException(e);}
  }
}
