// SPDX-License-Identifier: Apache-2.0
package dev.openpycharm.guardian.prototype;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import javax.swing.SwingUtilities;

/** Standalone worker-only lease. No IntelliJ registration or LSP stream forwarding. */
public final class GuardianLease implements AutoCloseable {
  private final ServerSocket listener;
  private final String nonce;
  private final AtomicBoolean closed = new AtomicBoolean();
  private final AtomicBoolean accepting = new AtomicBoolean();
  private final AtomicReference<Socket> connection = new AtomicReference<>();

  private GuardianLease(ServerSocket listener, String nonce) { this.listener=listener; this.nonce=nonce; }
  private static void worker() {
    if (SwingUtilities.isEventDispatchThread()) throw new IllegalStateException("Guardian lease I/O requires a worker");
  }
  public static GuardianLease open() throws IOException {
    worker(); byte[] bytes=new byte[32]; new SecureRandom().nextBytes(bytes);
    ServerSocket listener=new ServerSocket();
    try {
      listener.bind(new InetSocketAddress(InetAddress.getByAddress(new byte[]{127,0,0,1}),0),1);
      return new GuardianLease(listener,HexFormat.of().formatHex(bytes));
    } catch (IOException | RuntimeException error) { listener.close(); throw error; }
  }
  public String address() { return "127.0.0.1:"+listener.getLocalPort(); }
  public String nonce() { return nonce; }
  public List<String> command(Path guardian, List<String> target) {
    if (closed.get() || !guardian.isAbsolute() || target.isEmpty() || !Path.of(target.get(0)).isAbsolute())
      throw new IllegalArgumentException("Open lease and absolute guardian/target required");
    var args=new ArrayList<String>(); args.add(guardian.toString()); args.add("--lease"); args.add(address());
    args.add("--nonce");args.add(nonce);args.add("--");args.addAll(target);
    if (args.stream().anyMatch(x->x.indexOf('\0')>=0)) throw new IllegalArgumentException("NUL argument");
    return List.copyOf(args);
  }
  /** One peer, one bounded greeting, one total deadline. Failure permanently closes this lease. */
  public void accept(Duration timeout) throws IOException {
    worker(); long millis=timeout.toMillis();
    if (millis<1 || millis>5000) throw new IllegalArgumentException("Handshake timeout must be 1..5000 ms");
    if (closed.get() || !accepting.compareAndSet(false,true)) throw new IOException("Lease is closed or already accepted");
    long deadline=System.nanoTime()+millis*1_000_000;
    try {
      listener.setSoTimeout((int)millis); Socket peer=listener.accept(); connection.set(peer); listener.close();
      if (closed.get()) throw new IOException("Lease closed during accept");
      byte[] expected=("OPC-LSP-LEASE/1 "+nonce+"\n").getBytes(StandardCharsets.US_ASCII);
      var input=peer.getInputStream();
      for (byte value:expected) {
        long remaining=deadline-System.nanoTime();
        if (remaining<=0) throw new java.net.SocketTimeoutException("Lease greeting deadline");
        peer.setSoTimeout((int)Math.max(1,(remaining+999999)/1_000_000));
        if (input.read()!=Byte.toUnsignedInt(value)) throw new IOException("Lease greeting rejected");
      }
      if (closed.get()) throw new IOException("Lease closed before acknowledgement");
      peer.getOutputStream().write(new byte[]{'O','K','\n'});peer.getOutputStream().flush();peer.setSoTimeout(0);
    } catch (IOException | RuntimeException error) {
      try { close(); } catch (IOException closing) { error.addSuppressed(closing); }
      throw error;
    }
  }
  @Override public void close() throws IOException {
    worker();closed.set(true);IOException failure=null;
    Socket peer=connection.getAndSet(null);
    if (peer!=null) try { peer.close(); } catch (IOException error) { failure=error; }
    try { listener.close(); } catch (IOException error) { if(failure==null)failure=error;else failure.addSuppressed(error); }
    if(failure!=null)throw failure;
  }
}
