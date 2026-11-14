#!/usr/bin/env python3
"""Explicit real owned SIGSTOP/full-pipe cancellation regression; never an IDE.

Not a unit-discovery test: requires already authenticated native Node/TLS tools.
Preserves the original review control while expecting bounded independent cleanup.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from frontend_protocol_probe import Client, prepare_fixture
from provision_frontend_tools import authenticate_runtime, owned


def run(receipt: Path, output: Path) -> dict:
    if os.name == "nt": raise ValueError("SIGSTOP/full POSIX pipe control is not a Windows runtime claim")
    tools=authenticate_runtime(receipt);fixture,nonce=prepare_fixture(tools);client=Client(tools,fixture);worker=None
    result={"schema":1,"test":"real owned SIGSTOP plus full stdin close","nativeIdeStarted":False,
            "ownedPid":client.process.pid,"fixture":str(fixture),"nonce":nonce,"watchdogForcedKill":False}
    try:
        client.call('initialize',{'processId':os.getpid(),'rootUri':fixture.as_uri(),'capabilities':{},
                    'initializationOptions':{'disableAutomaticTypingAcquisition':True,'tsserver':{'path':str(Path(tools['runtimeRoot'])/tools['entries']['typescriptServer'])}}})
        client.notify('initialized',{})
        os.killpg(client.process.pid,signal.SIGSTOP)
        fd=client.process.stdin.fileno();os.set_blocking(fd,False);filled=0
        try:
            while filled <= 4_000_000: filled+=os.write(fd,b'x'*4096)
            raise AssertionError('Pipe did not reach bounded backpressure')
        except BlockingIOError: pass
        finally: os.set_blocking(fd,True)
        result['pipeBytesWrittenBeforeEagain']=filled;outcome={}
        def close():
            try:outcome['cleanup']=client.close()
            except BaseException as error:outcome['failure']=type(error).__name__+': '+str(error)
        worker=threading.Thread(target=close,name='frontend-backpressure-close',daemon=True)
        started=time.monotonic();worker.start();worker.join(12)
        result['closeSeconds']=round(time.monotonic()-started,3);result['closeStillBlocked']=worker.is_alive()
        if worker.is_alive():
            result['stackWhileBlocked']=traceback.format_stack(sys._current_frames()[worker.ident])
            os.killpg(client.process.pid,signal.SIGKILL);result['watchdogForcedKill']=True;worker.join(3)
        result['closeOutcome']=outcome;result['remainingOwnedGroupPids']=client.group_members()
        cleanup=outcome.get('cleanup',{})
        result['status']='pass' if (not result['closeStillBlocked'] and result['closeSeconds'] < 10 and not result['watchdogForcedKill']
             and cleanup.get('cleanupComplete') is True and not result['remainingOwnedGroupPids']
             and all(cleanup.get('streamCleanup',{}).get(name,{}).get('closed') is True for name in ('stdin','stdout','stderr'))
             and not any(cleanup.get('cleanupThreadsAlive',{'unknown':True}).values())) else 'fail'
    finally:
        try:os.killpg(client.process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        if worker:worker.join(3)
        client.process.wait(timeout=3)
        if not client.closed:client.close()
    output=owned(output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--receipt',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'.tools/frontend-review/backpressure-fixed.json')
    args=parser.parse_args();result=run(args.receipt,args.output);print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['status']=='pass' else 1)
