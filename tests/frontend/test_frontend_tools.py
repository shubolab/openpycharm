from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import queue
import stat
import sys
import tarfile
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import provision_frontend_tools as tools
from frontend_protocol_probe import Client, DeadlineWriter, child_environment, position


class FixtureCase(unittest.TestCase):
    def setUp(self):
        (tools.ROOT / ".tools").mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="frontend-unit-", dir=tools.ROOT / ".tools")
        self.root = Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)

    def item(self, data: bytes) -> dict:
        return {"id": "typescript", "version": "6.0.3", "url": "https://registry.npmjs.org/typescript/-/typescript-6.0.3.tgz",
                "size": len(data), "sha256": tools.digest(data),
                "integrity": "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode(),
                "extract": {"prefix": "package", "destination": "typescript", "allRegularFiles": True}, "format": "tar.gz"}


class ArtifactAuthenticationTests(FixtureCase):
    def test_sha_size_sri_and_symlink_are_independent_guards(self):
        content = b"authenticated artifact"; item = self.item(content); path = self.root / "archive.tgz"; path.write_bytes(content)
        self.assertEqual(tools.authenticate(path, item), content)
        for field, value in (("size", len(content) + 1), ("sha256", "0" * 64), ("integrity", "sha512-wrong")):
            broken = {**item, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError): tools.authenticate(path, broken)
        linked = self.root / "linked.tgz"
        try: linked.symlink_to(path)
        except OSError: self.skipTest("Host disallows symlinks")
        with self.assertRaises(ValueError): tools.authenticate(linked, item)

    def test_non_official_downgrade_query_userinfo_and_version_routes_fail_before_network(self):
        item = self.item(b"content")
        for url in ("http://registry.npmjs.org/typescript/-/typescript-6.0.3.tgz", "https://example.com/typescript/-/typescript-6.0.3.tgz",
                    item["url"] + "?token=secret", "https://user:password@registry.npmjs.org/typescript/-/typescript-6.0.3.tgz",
                    "https://registry.npmjs.org/typescript/-/typescript-6.0.4.tgz"):
            with self.subTest(url=url), mock.patch.object(tools.urllib.request, "build_opener") as opened:
                with self.assertRaises(ValueError): tools.download({**item, "url": url}, self.root / "out")
                opened.assert_not_called()

    def test_redirect_closes_response_without_making_followup_request(self):
        response = mock.Mock()
        with self.assertRaisesRegex(ValueError, "redirected"):
            tools.NoRedirect().redirect_request(None, response, 302, "Found", {}, "https://example.com/secret")
        response.close.assert_called_once()

    def test_bad_download_never_promotes_and_removes_partial_file(self):
        item = self.item(b"good"); destination = self.root / "good.tgz"
        response = mock.MagicMock(); response.__enter__.return_value = response
        response.status = 200; response.geturl.return_value = item["url"]; response.headers = {"Content-Length": "4"}
        response.read.side_effect = [b"evil", b""]
        with mock.patch.object(tools.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = response
            with self.assertRaisesRegex(ValueError, "SHA-256"): tools.download(item, destination)
        self.assertFalse(destination.exists()); self.assertEqual(list(self.root.iterdir()), [])

    def test_owned_cache_rejects_escape_and_symlink_ancestor(self):
        with self.assertRaises(ValueError): tools.owned(Path(tempfile.gettempdir()) / "external-frontend-cache")
        real = self.root / "real"; real.mkdir(); linked = self.root / "linked"
        try: linked.symlink_to(real, target_is_directory=True)
        except OSError: self.skipTest("Host disallows symlinks")
        with self.assertRaises(ValueError): tools.owned(linked / "cache")

    def test_download_cannot_write_outside_owned_tools_even_with_a_valid_official_pin(self):
        with mock.patch.object(tools.urllib.request, 'build_opener') as opened:
            with self.assertRaises(ValueError): tools.download(self.item(b'content'),Path(tempfile.gettempdir())/'forbidden-frontend-payload')
            opened.assert_not_called()


class ExtractionTests(FixtureCase):
    def archive(self, entries):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:gz") as tar:
            for name, content, link in entries:
                entry = tarfile.TarInfo(name)
                if link: entry.type = tarfile.SYMTYPE; entry.linkname = link; tar.addfile(entry)
                else: entry.size = len(content); tar.addfile(entry, io.BytesIO(content))
        return data.getvalue()

    def test_traversal_duplicate_and_link_members_never_publish_outside_stage(self):
        for entries in ([('package/../escape',b'x',None)], [('package/file',b'a',None),('package/file',b'b',None)],
                        [('package/file',b'', '/etc/passwd')]):
            data = self.archive(entries); stage = self.root / str(len(list(self.root.iterdir()))); stage.mkdir()
            with self.subTest(entries=entries), self.assertRaises(ValueError): tools.extract(data,self.item(data),stage)
        self.assertFalse((self.root / "escape").exists())

    def test_exact_payload_manifest_and_package_identity_are_enforced(self):
        content = json.dumps({"name":"typescript","version":"6.0.3","scripts":{"install":"must not execute"}}).encode()
        data = self.archive([('package/package.json',content,None),('package/LICENSE',b'legal text',None)])
        item = self.item(data); item['expectedPackage']={'name':'typescript','version':'6.0.3','noRuntimeDependencies':True}
        stage=self.root/'stage';stage.mkdir(); records=tools.extract(data,item,stage)
        self.assertEqual((stage/'typescript/LICENSE').read_bytes(), b'legal text')
        self.assertFalse((stage/'must-not-execute').exists())
        item['payload']={**records,'typescript/extra':{'size':1,'sha256':'0'*64}}
        another=self.root/'another';another.mkdir()
        with self.assertRaisesRegex(ValueError,'manifest'):tools.extract(data,item,another)
        broken=self.item(data);broken['expectedPackage']={'name':'wrong','version':'6.0.3'}
        identity=self.root/'identity';identity.mkdir()
        with self.assertRaisesRegex(ValueError,'identity'):tools.extract(data,broken,identity)

    def test_zip_special_mode_is_rejected(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            entry=zipfile.ZipInfo('package/file');entry.external_attr=(stat.S_IFCHR|0o600)<<16;archive.writestr(entry,b'x')
        data=stream.getvalue();item=self.item(data);item['format']='zip'
        with self.assertRaisesRegex(ValueError,'special'):tools.extract(data,item,self.root)

    def test_bundled_notice_omission_cannot_pass_source_map_closure(self):
        source_map={'sources':['../node_modules/.pnpm/one@1.0.0/node_modules/one/index.js',
                               '../node_modules/.pnpm/two@2.0.0/node_modules/two/index.js']}
        path=self.root/'cli.map';path.write_text(json.dumps(source_map))
        pin={'bundledClosure':{'sourceMapPath':'cli.map','sourceMapSha256':tools.digest(path.read_bytes()),'sourceCount':2,
                              'packages':{'one':'1.0.0','two':'2.0.0'}},
             'artifacts':[{'package':'one','version':'1.0.0','purpose':'bundled-cli-corresponding-notices-only'}]}
        with self.assertRaisesRegex(ValueError,'closure is incomplete'):tools.verify_closure(self.root,pin)
        pin['artifacts'].append({'package':'two','version':'2.0.0','purpose':'bundled-cli-corresponding-notices-only'})
        tools.verify_closure(self.root,pin)


class RuntimeReceiptTests(FixtureCase):
    def setUp(self):
        super().setUp();self.runtime=self.root/'runtime';self.runtime.mkdir();self.pin=self.root/'pin.json';self.pin.write_text('{}')
        self.files={'node/bin/node':{'size':4,'sha256':tools.digest(b'node')}}
        path=self.runtime/'node/bin/node';path.parent.mkdir(parents=True);path.write_bytes(b'node')
        self.item={'id':'node-macos-arm64','sha256':'a'*64,'size':4,'payload':self.files,'nodeExecutable':'node/bin/node'}
        self.lock={'artifacts':[self.item],'bundledClosure':{'packages':{}},'runtimeEntries':{'typescriptLanguageServer':'node/bin/node','typescriptServer':'node/bin/node'}}
        self.report={'schema':1,'owner':tools.OWNER,'target':'macos-arm64','lockSha256':tools.digest(self.pin.read_bytes()),
                     'runtimeRoot':str(self.runtime),'files':copy.deepcopy(self.files),'entries':{'node':'node/bin/node',**self.lock['runtimeEntries']},
                     'installationScriptsExecuted':False,'productionPackaged':False,'bundledPackageNotices':0,
                     'artifacts':[{k:self.item[k] for k in ('id','sha256','size')}]}
        self.receipt=self.runtime/'frontend-tools.json';self.receipt.write_text(json.dumps(self.report))
        self.pin_patch=mock.patch.object(tools,'PIN',self.pin);self.pin_patch.start();self.addCleanup(self.pin_patch.stop)
        self.loader=mock.patch.object(tools,'load_pin',return_value=self.lock);self.loader.start();self.addCleanup(self.loader.stop)

    def test_payload_tamper_cannot_be_reauthorized_by_forging_receipt_hashes(self):
        tools.authenticate_runtime(self.receipt)
        path=self.runtime/'node/bin/node';path.write_bytes(b'evil')
        self.report['files']['node/bin/node']['sha256']=tools.digest(b'evil');self.receipt.write_text(json.dumps(self.report))
        with self.assertRaisesRegex(ValueError,'pinned payload'):tools.authenticate_runtime(self.receipt)

    def test_extra_file_and_changed_entry_are_rejected(self):
        extra=self.runtime/'extra';extra.write_bytes(b'unexpected')
        with self.assertRaisesRegex(ValueError,'payload set'):tools.authenticate_runtime(self.receipt)
        extra.unlink();self.report['entries']['node']='node/bin/other';self.receipt.write_text(json.dumps(self.report))
        with self.assertRaisesRegex(ValueError,'closure'):tools.authenticate_runtime(self.receipt)


class ProtocolHarnessTests(unittest.TestCase):
    def test_utf16_columns_surrogate_pair_crlf_and_bounds(self):
        text='a😀中文\r\nx'
        self.assertEqual(position(text,4),{'line':0,'character':5})
        self.assertEqual(position(text,len(text)),{'line':1,'character':1})
        for value in (-1,len(text)+1):
            with self.assertRaises(ValueError):position(text,value)

    def test_reader_rejects_duplicate_frame_and_short_body(self):
        for data in (b'Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}',b'Content-Length: 10\r\n\r\n{}'):
            client=Client.__new__(Client);client.process=SimpleNamespace(stdout=io.BytesIO(data));client.messages=queue.Queue();client.read_error=None
            client._read();self.assertIsNone(client.messages.get_nowait());self.assertIsNotNone(client.read_error)

    def test_child_environment_excludes_inherited_auth_and_node_injection(self):
        with mock.patch.dict('os.environ',{'NPM_TOKEN':'secret','GITHUB_TOKEN':'secret','NODE_OPTIONS':'--require user-code'}):
            env=child_environment(Path('/owned/state'),Path('/owned/tools/bin/node'))
        self.assertNotIn('NPM_TOKEN',env);self.assertNotIn('GITHUB_TOKEN',env);self.assertEqual(env['NODE_OPTIONS'],'')
        self.assertEqual(env['HOME'],'/owned/state/home')


class DeadlineWriterTests(unittest.TestCase):
    class Blocked:
        def __init__(self): self.release=threading.Event();self.entered=threading.Event();self.closed=False
        def write(self, data): self.entered.set();self.release.wait();return len(data)
        def flush(self): pass
        def close(self): self.closed=True

    def test_rpc_budget_covers_a_blocked_pipe_write_before_response_wait(self):
        stream=self.Blocked();closed=[];writer=DeadlineWriter(stream,lambda name,value:(value.close(),closed.append(name)))
        client=Client.__new__(Client);client.writer=writer;client.closed=False;client.counter=0;client.responses={}
        client._receive=mock.Mock(side_effect=AssertionError('Response wait must not begin after write timeout'))
        try:
            started=time.monotonic()
            with self.assertRaisesRegex(TimeoutError,'write deadline'):client.call('shutdown',timeout=0.1)
            self.assertLess(time.monotonic()-started,0.8);self.assertTrue(stream.entered.is_set());client._receive.assert_not_called()
            started=time.monotonic();writer.stop();self.assertLess(time.monotonic()-started,0.1)
        finally:
            stream.release.set();writer.stop();writer.thread.join(2)
        self.assertFalse(writer.thread.is_alive());self.assertTrue(stream.closed);self.assertEqual(closed,['stdin'])

    def test_server_request_reply_uses_the_original_absolute_deadline(self):
        stream=self.Blocked();writer=DeadlineWriter(stream,lambda name,value:value.close())
        client=Client.__new__(Client);client.writer=writer;client.closed=False;client.events=[];client.responses={};client.messages=queue.Queue()
        client.messages.put({'id':7,'method':'workspace/configuration','params':{'items':[{'section':'formattingOptions'}]}})
        try:
            started=time.monotonic()
            with self.assertRaisesRegex(TimeoutError,'write deadline'):client._receive(started+0.1)
            self.assertLess(time.monotonic()-started,0.8)
        finally:
            stream.release.set();writer.stop();writer.thread.join(2)
        self.assertFalse(writer.thread.is_alive())

    def test_stdin_close_error_does_not_skip_other_streams_or_joins(self):
        class BrokenClose(io.BytesIO):
            def close(self):
                super().close();raise BrokenPipeError('controlled stdin close failure')
        stdin=BrokenClose();stdout=io.BytesIO();stderr=io.BytesIO()
        client=Client.__new__(Client);client.closed=False;client.cleanup_report=None;client.stream_cleanup={};client.job=None
        client.process=SimpleNamespace(pid=123456,stdin=stdin,stdout=stdout,returncode=0,poll=lambda:0,wait=lambda timeout:0)
        client.group_members=mock.Mock(return_value=[]);client.stderr=stderr
        client.writer=DeadlineWriter(stdin,client._close_stream)
        client.reader=threading.Thread(target=client._close_stream,args=('stdout',stdout),name='controlled-reader');client.reader.start()
        report=client.close(timeout=1)
        self.assertTrue(report['cleanupComplete']);self.assertIn('BrokenPipeError',report['streamCleanup']['stdin']['error'])
        self.assertTrue(all(report['streamCleanup'][name]['closed'] for name in ('stdin','stdout','stderr')))
        self.assertFalse(any(report['cleanupThreadsAlive'].values()));self.assertIs(client.close(),report)


if __name__ == '__main__':unittest.main()
