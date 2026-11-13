package dev.openpycharm.notebooks;

import com.google.gson.*;
import java.util.*;
import java.util.concurrent.*;
/** Actual native JVM pipe/process checks; no IDE or Swing application is launched. */
public class NotebookKernelSessionTest {
 static final BlockingQueue<JsonObject> queue=new LinkedBlockingQueue<>();
 static final List<JsonObject> pending=new ArrayList<>();
 static JsonObject event(String id,String kind) throws Exception {
  for(int i=0;i<pending.size();i++) {JsonObject value=pending.get(i); if(kind.equals(NotebookKernelSession.string(value,"event")) && Objects.equals(id,NotebookKernelSession.string(value,"id"))) return pending.remove(i);}
  long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(45);
  while(System.nanoTime()<deadline) {
   JsonObject value=queue.poll(1,TimeUnit.SECONDS); if(value==null)continue;
   if("session_error".equals(NotebookKernelSession.string(value,"event")))throw new IllegalStateException(value.toString());
   if(kind.equals(NotebookKernelSession.string(value,"event")) && Objects.equals(id,NotebookKernelSession.string(value,"id")))return value;
   pending.add(value);
  }
  throw new IllegalStateException("No event "+id+"/"+kind+"; pending="+pending);
 }
 static void require(boolean pass,String message) {if(!pass)throw new AssertionError(message);}
 static boolean alive(long pid) {return ProcessHandle.of(pid).map(ProcessHandle::isAlive).orElse(false);}
 public static void main(String[] args) throws Exception {
  NotebookKernelSession session=new NotebookKernelSession(args[0],args[1],queue::add);
  Process sentinel=new ProcessBuilder(args[0],"-c","import time; time.sleep(90)").start();
  long pid=-1,restartedPid=-1;
  try {
   session.request("value","execute","value=40\nprint('java-protocol-output')\nvalue+2");
   JsonObject ready=event("","ready"); pid=ready.get("kernel_pid").getAsLong();
   require(args[0].equals(NotebookKernelSession.string(ready,"python")),"Kernel used a different Python interpreter");
   require("ok".equals(NotebookKernelSession.string(event("value","done"),"status")),"Initial execution failed");
   require(event("value","stream").getAsJsonObject("content").get("text").getAsString().contains("java-protocol-output"),"Stream missing");
   require(event("value","execute_result").getAsJsonObject("content").getAsJsonObject("data").get("text/plain").getAsString().equals("42"),"Result mismatch");
   session.request("long","execute","import time\nwhile True: time.sleep(.05)");event("long","execute_input");
   session.request("interrupt","interrupt",null);
   require("ok".equals(NotebookKernelSession.string(event("interrupt","done"),"status")),"Interrupt failed");
   require("error".equals(NotebookKernelSession.string(event("long","done"),"status")),"Execution not interrupted");
   session.request("again","execute","while True: time.sleep(.05)");event("again","execute_input");
   session.request("restart-control","restart",null);
   require("aborted".equals(NotebookKernelSession.string(event("again","done"),"status")),"Restart did not abort pending execution");
   JsonObject restarted=event("restart-control","done");require("ok".equals(NotebookKernelSession.string(restarted,"status")),"Restart failed");
   restartedPid=restarted.get("kernel_pid").getAsLong();require(pid!=restartedPid && !alive(pid),"Original kernel survived restart");
   session.request("state-reset","execute","value");
   require("error".equals(NotebookKernelSession.string(event("state-reset","done"),"status")),"Restart retained namespace");
   require("NameError".equals(event("state-reset","error").getAsJsonObject("content").get("ename").getAsString()),"Expected NameError missing");
   session.close();session.close();
   long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(15);while(alive(restartedPid)&&System.nanoTime()<deadline)Thread.sleep(50);
   require(!alive(restartedPid),"Restarted owned kernel survived session close");
   Thread.sleep(200);session.close();require(sentinel.isAlive(),"Unrelated owned test process was stopped");
   System.out.println("{\"status\":\"pass\",\"realJavaSession\":true,\"selectedPython\":true,\"streamAndResult\":true,\"interrupt\":true,\"restartWhileBusy\":true,\"stateReset\":true,\"doubleClose\":true,\"ownedKernelCleanup\":true,\"unrelatedProcessSurvived\":true,\"originalKernelPid\":"+pid+",\"restartedKernelPid\":"+restartedPid+"}");
  } finally {session.close();sentinel.destroy();if(!sentinel.waitFor(5,TimeUnit.SECONDS))sentinel.destroyForcibly();}
  System.exit(0);
 }
}
