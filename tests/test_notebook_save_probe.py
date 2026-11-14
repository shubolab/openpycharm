import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import notebook_save_probe as probe


class NotebookNativeSaveProbeTests(unittest.TestCase):
    def test_default_preparation_does_not_launch(self):
        prepared = {'workspace': '/owned/prepared', 'probeBuild': {'pluginSha256': 'probe'}, 'productionJarSha256': 'production'}
        with patch.object(sys, 'argv', ['probe', '--sdk', '/sdk', '--workspace', '/owned/prepared']), \
             patch.object(probe, 'prepare', return_value=prepared), patch.object(probe, 'run') as run, \
             patch('builtins.print'):
            self.assertEqual(probe.main(), 0)
        run.assert_not_called()
        with patch.object(sys, 'argv', ['probe', '--sdk', '/sdk', '--workspace', '/owned/prepared', '--run']), \
             patch.object(probe, 'prepare') as prepare, patch('sys.stderr'):
            with self.assertRaises(SystemExit):
                probe.main()
        prepare.assert_not_called()

    def test_workspace_rejects_existing_or_unowned_paths_before_sdk_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repo'; owned = root / '.tools/existing'; owned.mkdir(parents=True)
            with patch.object(probe, 'ROOT', root), patch.object(probe.builder, 'sdk_layout') as sdk:
                for path in (owned, root / 'project', root / '.tools/../escape'):
                    with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'new owned workspace'):
                        probe.prepare(Path('/sdk'), path)
            sdk.assert_not_called()

    def test_prepare_keeps_unicode_fixture_and_never_runs_a_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'repo'; workspace = root / '.tools/中文 save gate'
            sdk = Path(directory) / 'sdk'; sdk.mkdir()
            production = Path(directory) / 'built'; (production / 'lib').mkdir(parents=True)
            jar = production / 'lib/notebooks.jar'; jar.write_bytes(b'owned test jar')
            with patch.object(probe, 'ROOT', root), patch.object(probe.builder, 'sdk_layout', return_value=SimpleNamespace(sdk_root=sdk)), \
                 patch.object(probe.builder, 'build_plugin', return_value=(production, {})), \
                 patch.object(probe, 'build_probe', return_value=(Path(directory) / 'probe', {'pluginSha256': 'fixture'})), \
                 patch.object(probe.subprocess, 'Popen') as launch:
                result = probe.prepare(sdk, workspace)
            launch.assert_not_called()
            fixture = json.loads(Path(result['fixture']).read_text(encoding='utf-8'))
            self.assertEqual(fixture['metadata']['large'], 9007199254740993)
            self.assertIn('原始保存夹具', fixture['cells'][0]['source'][0])
            self.assertFalse(result['nativeApplicationLaunched'])
            self.assertFalse(result['kernelCodeExecuted'])
            self.assertFalse(result['projectTrustBypassed'])
            self.assertIn('not runtime Python execution evidence', ' '.join(result['limitations']))

    def test_timeout_and_cleanup_failure_retain_owned_pid_report_and_dump(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory); contents = workspace / 'app'; (contents / 'bin').mkdir(parents=True)
            (contents / 'bin/pycharm.vmoptions').write_text('-Xmx1g\n', encoding='utf-8')
            layout = SimpleNamespace(contents=contents, platform='macos', jcmd=contents / 'jcmd')
            process = SimpleNamespace(pid=123456, poll=lambda: 0, returncode=1)
            prepared = {'workspace': str(workspace), 'profile': str(workspace / 'profile'), 'properties': str(workspace / 'owned.properties'),
                        'project': str(workspace / 'project'), 'fixture': str(workspace / 'project/owned.ipynb'),
                        'pluginDirectory': str(workspace / 'probe'), 'productionJarSha256': 'owned-jar'}
            with patch.object(probe, 'app_layout', return_value=layout), patch.object(probe.subprocess, 'Popen', return_value=process), \
                 patch.object(probe.subprocess, 'run', return_value=SimpleNamespace(stdout='owned timeout stack', stderr='')), \
                 patch.object(probe, 'stop_owned', side_effect=TimeoutError('owned cleanup timeout')) as stop:
                result = probe.run(contents, prepared, 30)
            stop.assert_called_once_with(process, None)
            self.assertEqual(result['assessment']['status'], 'fail')
            saved = json.loads((workspace / 'result.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['cleanup']['ownedPid'], process.pid)
            self.assertEqual((workspace / 'external-timeout-threads.txt').read_text(encoding='utf-8'), 'owned timeout stack')
            self.assertEqual(saved['ownedPid'], process.pid)


if __name__ == '__main__':
    unittest.main()
