// SPDX-License-Identifier: Apache-2.0
package dev.openpycharm.guardian.prototype;

import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.swing.SwingUtilities;

public final class GuardianLeaseCheck {
  public static void main(String[] args) throws Exception {
    if(args[0].equals("controls")) {
      var rejected=new AtomicBoolean();
      SwingUtilities.invokeAndWait(()->{try {GuardianLease.open();} catch(IllegalStateException expected){rejected.set(true);}catch(Exception e){throw new RuntimeException(e);}});
      if(!rejected.get())throw new AssertionError("EDT open accepted");
      try(var lease=GuardianLease.open()) {
        rejected.set(false);
        SwingUtilities.invokeAndWait(()->{try{lease.close();}catch(IllegalStateException expected){rejected.set(true);}catch(Exception e){throw new RuntimeException(e);}});
        if(!rejected.get())throw new AssertionError("EDT close accepted");
        String[] address=lease.address().split(":");
        try(var peer=new Socket(address[0],Integer.parseInt(address[1]))) {
          peer.getOutputStream().write(("OPC-LSP-LEASE/1 "+(lease.nonce().charAt(0)=='0'?"1":"0")+lease.nonce().substring(1)+"\n").getBytes(java.nio.charset.StandardCharsets.US_ASCII));
          boolean bad=false;try{lease.accept(Duration.ofSeconds(1));}catch(java.io.IOException expected){bad=true;}
          int ack;try{ack=peer.getInputStream().read();}catch(java.net.SocketException rejectedPeer){ack=-1;}
          if(!bad || ack!=-1)throw new AssertionError("Invalid nonce accepted");
        }
      }
      var lease=GuardianLease.open();var cancelled=new AtomicBoolean();
      Thread accepting=new Thread(()->{try{lease.accept(Duration.ofSeconds(3));}catch(java.io.IOException expected){cancelled.set(true);}});
      accepting.start();Thread.sleep(60);lease.close();accepting.join(1000);
      if(accepting.isAlive() || !cancelled.get())throw new AssertionError("close did not wake accept");
      try(var idle=GuardianLease.open()) {
        boolean timed=false;try{idle.accept(Duration.ofMillis(40));}catch(java.net.SocketTimeoutException expected){timed=true;}
        if(!timed)throw new AssertionError("Missing timeout");
      }
      System.out.println("{\"status\":\"pass\",\"controls\":5}");return;
    }
    Path dir=Path.of(args[3]);
    try(var lease=GuardianLease.open()) {
      var cmd=lease.command(Path.of(args[1]),List.of(args[2],dir.toString(),args[4]));
      Process child=new ProcessBuilder(cmd).inheritIO().start();
      try {
        lease.accept(Duration.ofSeconds(2));
        Files.writeString(dir.resolve("jvm-ready.json"),"{\"jvmPid\":"+ProcessHandle.current().pid()+",\"guardianPid\":"+child.pid()+"}");
        while(!Files.exists(dir.resolve("close-lease")))Thread.sleep(10);
        lease.close();
        if(!child.waitFor(6,TimeUnit.SECONDS))throw new AssertionError("guardian did not end on lease EOF");
      } finally {
        lease.close();
        if(child.isAlive()){child.destroyForcibly();child.waitFor(6,TimeUnit.SECONDS);}
      }
    }
  }
}
