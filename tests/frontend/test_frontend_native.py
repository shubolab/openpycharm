from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import build_frontend_plugin as builder


class NativeHelperOwnershipTests(unittest.TestCase):
    def setUp(self):
        directory = builder.ROOT / '.tools'; directory.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='frontend-native-unit-', dir=directory)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / 'compile'; self.directory.mkdir()
        self.runtime = SimpleNamespace(java=Path('/selected/jbr/bin/java'))

    def test_helper_owns_a_new_posix_session_and_cleans_only_its_process(self):
        process = SimpleNamespace(pid=123456, returncode=0, communicate=lambda **kw: ('{"status":"pass"}', ''), poll=lambda: 0)
        with patch.object(builder.os, 'name', 'posix'), patch.object(builder.subprocess, 'Popen', return_value=process) as launch, \
             patch.object(builder, 'stop_owned', return_value={'mode': 'owned-posix-session'}) as cleanup:
            report = builder.native_process_check(self.runtime, ['NativeProcessCheck'], self.directory)
        self.assertTrue(launch.call_args.kwargs['start_new_session'])
        self.assertEqual(launch.call_args.kwargs['stdin'], subprocess.DEVNULL)
        cleanup.assert_called_once_with(process, None)
        self.assertEqual(report['externalWatchdogCleanup']['mode'], 'owned-posix-session')

    def test_timeout_keeps_partial_evidence_and_still_cleans_exact_owned_helper(self):
        class Process:
            pid = 234567
            returncode = None
            def communicate(self, **kwargs):
                raise subprocess.TimeoutExpired(['owned-helper'], 60, output=b'owned partial stdout', stderr=b'owned timeout stack')
            def poll(self): return None
        process = Process()
        with patch.object(builder.os, 'name', 'posix'), patch.object(builder.subprocess, 'Popen', return_value=process), \
             patch.object(builder, 'stop_owned', return_value={'mode': 'owned-posix-session', 'pid': process.pid}) as cleanup:
            with self.assertRaisesRegex(ValueError, '60-second deadline'):
                builder.native_process_check(self.runtime, ['NativeProcessCheck'], self.directory)
        cleanup.assert_called_once_with(process, None)
        evidence = json.loads((self.directory.parent / 'native-process-last-failure.json').read_text(encoding='utf-8'))
        self.assertEqual(evidence['stdout'], 'owned partial stdout')
        self.assertEqual(evidence['stderr'], 'owned timeout stack')
        self.assertEqual(evidence['externalWatchdogCleanup']['pid'], process.pid)


if __name__ == '__main__': unittest.main()
