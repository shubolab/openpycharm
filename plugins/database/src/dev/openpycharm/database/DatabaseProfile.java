package dev.openpycharm.database;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Properties;
import java.util.Map;
import java.util.UUID;

/** Non-secret project state. No arbitrary JDBC URL or connection properties. */
public final class DatabaseProfile {
  public enum Engine { SQLITE, POSTGRESQL, MYSQL }
  public String id = UUID.randomUUID().toString();
  public String name = "Local SQLite";
  public String engine = Engine.SQLITE.name();
  public Map<String,String> metadata = new java.util.LinkedHashMap<>();
  public Engine kind() {
    try {return Engine.valueOf(engine);} catch(RuntimeException e) {throw new IllegalArgumentException("Unsupported database engine: "+engine);}
  }
  public String file = "";
  public String host = "127.0.0.1";
  public int port = 5432;
  public String database = "";
  public String user = "";
  public boolean verifyTls = true;

  public DatabaseProfile copy() {
    DatabaseProfile p = new DatabaseProfile();
    p.id=id; p.name=name; p.engine=engine; p.file=file; p.host=host; p.port=port;
    p.database=database; p.user=user; p.verifyTls=verifyTls; p.metadata=metadata==null?new java.util.LinkedHashMap<>():new java.util.LinkedHashMap<>(metadata);
    return p;
  }

  public void validate() {
    if (id == null || !id.matches("[a-fA-F0-9-]{36}")) throw new IllegalArgumentException("Invalid connection identity");
    if (name == null || name.isBlank() || name.length()>120) throw new IllegalArgumentException("Enter a connection name (up to 120 characters)");
    kind();
    if (kind() == Engine.SQLITE) {
      if (file == null || file.isBlank() || file.length()>4096 || file.indexOf('\0')>=0 || file.indexOf('?')>=0 || file.indexOf('#')>=0 || !Path.of(file).isAbsolute())
        throw new IllegalArgumentException("SQLite requires an absolute local file path without ? or #");
    } else {
      if (host == null || !host.matches("[A-Za-z0-9._:-]{1,253}") || host.contains(":::") || host.startsWith("-") || host.contains(".."))
        throw new IllegalArgumentException("Enter a hostname or IPv4/IPv6 address");
      if (port<1 || port>65535) throw new IllegalArgumentException("Port must be between 1 and 65535");
      if (database==null || database.isBlank() || database.length()>256 || database.chars().anyMatch(c -> c<32))
        throw new IllegalArgumentException("Enter a database name");
      if (user==null || user.length()>256 || user.chars().anyMatch(c -> c<32)) throw new IllegalArgumentException("Invalid user name");
    }
  }

  public String jdbcUrl() {
    validate();
    if (kind() == Engine.SQLITE) return "jdbc:sqlite:" + Path.of(file).normalize();
    String hostname = host.contains(":") ? "["+host+"]" : host;
    String db = URLEncoder.encode(database, StandardCharsets.UTF_8).replace("+", "%20");
    return (kind() == Engine.POSTGRESQL ? "jdbc:postgresql://" : "jdbc:mariadb://") + hostname + ":" + port + "/" + db;
  }

  public Properties properties(char[] password) {
    Properties p = new Properties();
    if (kind() == Engine.SQLITE) {
      p.setProperty("busy_timeout", "5000");
      p.setProperty("enable_load_extension", "false");
    } else {
      p.setProperty("user", user);
      if (password!=null) p.setProperty("password", new String(password));
      if (kind() == Engine.POSTGRESQL) {
        p.setProperty("connectTimeout", "5"); p.setProperty("socketTimeout", "20");
        p.setProperty("cancelSignalTimeout", "5"); p.setProperty("sslmode", verifyTls?"verify-full":"disable");
        p.setProperty("ApplicationName", "OpenPyCharm Database");
      } else {
        p.setProperty("connectTimeout", "5000"); p.setProperty("socketTimeout", "20000");
        p.setProperty("sslMode", verifyTls?"verify-full":"disable");
        p.setProperty("allowMultiQueries", "false"); p.setProperty("allowLocalInfile", "false");
      }
    }
    return p;
  }

  @Override public String toString() { return name + " ("+engine+")"; }
}
