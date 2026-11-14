#!/usr/bin/env python3
"""Compile/run only standalone JVM+Go owned fixtures; no IDE, Node or network."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, os, subprocess, sys, time

ROOT=Path(__file__).resolve().parents[3]
SOURCE=Path(__file__).resolve().parent

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(65536),b''):h.update(b)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk',type=Path,required=True)
    parser.add_argument('--go-proof',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); proof=args.go_proof.resolve(); previous=json.loads((proof/'receipt.json').read_text())
    guardian,child=proof/'guardian',proof/'tiny-child'
    for file in (guardian,child):
        if sha(file)!=previous['binaries'][file.name]:raise ValueError('Go fixture binary differs from authenticated receipt')
    sys.path.insert(0,str(ROOT/'scripts'))
    from build_framework_plugin import sdk_layout
    sdk=sdk_layout(args.sdk.resolve()); jdk=sdk.contents/'jbr/Contents/Home/bin'
    output=args.output.resolve(); output.mkdir(parents=True,exist_ok=False); classes=output/'classes';classes.mkdir()
    commands=[]
    def run(command,name,timeout=30):
        p=subprocess.run(list(map(str,command)),capture_output=True,timeout=timeout)
        (output/(name+'.stdout')).write_bytes(p.stdout);(output/(name+'.stderr')).write_bytes(p.stderr)
        commands.append({'name':name,'exit':p.returncode,'stdoutSha256':sha(output/(name+'.stdout')),'stderrSha256':sha(output/(name+'.stderr'))})
        if p.returncode:raise AssertionError(name+' failed: '+p.stderr.decode(errors='replace'))
        return p.stdout
    sources=sorted(SOURCE.glob('*.java'))
    run([jdk/'javac','--release','21','-encoding','UTF-8','-d',classes,*sources],'compile')
    java=[str(jdk/'java'),'-Djava.awt.headless=true','-cp',str(classes),'dev.openpycharm.guardian.prototype.GuardianLeaseCheck']
    controls=json.loads(run(java+['controls'],'worker-handshake-controls'))
    assert controls=={'status':'pass','controls':5}
    os.environ['OPC_GUARDIAN_BINARY']=str(guardian);os.environ['OPC_GUARDIAN_CHILD']=str(child)
    spec=importlib.util.spec_from_file_location('owned_guardian_fixture',SOURCE.parent/'integration_test.py'); fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    results=[]
    for case,mode in [('normal-close','tree'),('jvm-abrupt-exit','tree'),('stdout-undrained','blocked-output')]:
        directory=output/case;directory.mkdir()
        sentinel=subprocess.Popen([str(child),str(directory),'sentinel'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        sentinel_id=fixture.wait_json(directory/'sentinel.json')
        process=subprocess.Popen(java+['hold',str(guardian),str(child),str(directory),mode],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            lease=fixture.wait_json(directory/'jvm-ready.json');root=fixture.wait_json(directory/'root.json'); identities=[root]
            if mode=='tree':
                fixture.wait_json(directory/'ready.json')
                identities.extend(fixture.wait_json(directory/(name+'.json')) for name in ('child','grandchild'))
            time.sleep(.2)
            assert process.poll() is None and fixture.alive(root)
            if case=='jvm-abrupt-exit':process.kill()
            else:(directory/'close-lease').touch()
            process.wait(timeout=8)
            # Keep the pipe undrained through JVM exit and complete owned cleanup.
            deadline=time.monotonic()+3
            while any(fixture.alive(i) for i in identities) and time.monotonic()<deadline:time.sleep(.01)
            assert not any(fixture.alive(i) for i in identities),'owned targets survived lease EOF'
            stdout,stderr=process.communicate(timeout=3)
            (directory/'stdout.bin').write_bytes(stdout);(directory/'stderr.txt').write_bytes(stderr)
            assert process.returncode==(-9 if case=='jvm-abrupt-exit' else 0),(case,process.returncode,stderr)
            deadline=time.monotonic()+3
            while any(fixture.alive(i) for i in identities) and time.monotonic()<deadline:time.sleep(.01)
            assert not any(fixture.alive(i) for i in identities),'owned targets survived lease EOF'
            deadline=time.monotonic()+3
            while fixture.alive({'pid':lease['guardianPid']}) and time.monotonic()<deadline:time.sleep(.01)
            assert not fixture.alive({'pid':lease['guardianPid']}),'Go guardian remained after JVM lease EOF'
            assert sentinel.poll() is None and fixture.alive(sentinel_id),'unrelated owned sentinel was affected'
            if case=='stdout-undrained':assert len(stdout)>0,'fixture produced no actual stdout'
            results.append({'case':case,'status':'pass','ownedTargetCount':len(identities),'unrelatedOwnedSentinelSurvived':True,'jvmKilled':case=='jvm-abrupt-exit','stdoutNotDrainedUntilJvmExitAndOwnedCleanup':case=='stdout-undrained','capturedStdoutBytes':len(stdout),'exit':process.returncode,'stderrSha256':sha(directory/'stderr.txt')})
        finally:
            if process.poll() is None:process.kill()
            try:process.communicate(timeout=8)
            finally:
                for stream in (process.stdin,process.stdout,process.stderr):
                    if stream and not stream.closed:stream.close()
                if sentinel.poll() is None:sentinel.kill()
                sentinel.wait(timeout=3)
    report={'schema':1,'prototypeOnly':True,'status':'bounded-macos-jvm-lease-pass','sources':{p.name:sha(p) for p in [*sources,Path(__file__)]},'jbr':{'javaSha256':sha(jdk/'java'),'javacSha256':sha(jdk/'javac'),'sdkReceiptSha256':sha(sdk.sdk_root.parent/'.openpycharm-platform.json'),'javaVersion':subprocess.check_output([str(jdk/'java'),'-version'],stderr=subprocess.STDOUT,text=True).strip()},'goProofReceiptSha256':sha(proof/'receipt.json'),'goBinaries':{p.name:sha(p) for p in (guardian,child)},'boundaryControls':controls['controls'],'commands':commands,'ownedJvmCases':results,'ideStarted':False,'nodeStarted':False,'network':'IPv4 loopback only','unknown':['Actual IntelliJ Disposable/ProcessHandler/LSP lifecycle adapter is not implemented.','Windows/Linux JVM bridge runtime, malicious peers with a stolen nonce, process-group escape and exhaustive scheduler races are unverified.','The stdout fixture was left undrained; kernel blocked-write duration was not measured.','close() must be called from a worker; asynchronous EDT disposal integration remains future work.']}
    (output/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
