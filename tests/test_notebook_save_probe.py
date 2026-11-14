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
            self.assertEqual(result['projectCreationMode'], 'normal-ide-new-owned-project')
            self.assertEqual(list(Path(result['project']).iterdir()), [Path(result['fixture'])])
            self.assertIn('not runtime Python execution evidence', ' '.join(result['limitations']))

    def test_timeout_and_cleanup_failure_retain_owned_pid_report_and_dump(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory); contents = workspace / 'app'; (contents / 'bin').mkdir(parents=True)
            (contents / 'bin/pycharm.vmoptions').write_text('-Xmx1g\n', encoding='utf-8')
            layout = SimpleNamespace(contents=contents, platform='macos', jcmd=contents / 'jcmd')
            process = SimpleNamespace(pid=123456, poll=lambda: 0, returncode=1)
            prepared = {'workspace': str(workspace), 'profile': str(workspace / 'profile'), 'properties': str(workspace / 'owned.properties'),
                        'project': str(workspace / 'project'), 'fixture': str(workspace / 'project/owned.ipynb'),
                        'pluginDirectory': str(workspace / 'probe'), 'productionJarSha256': 'owned-jar', 'initialFixtureSha256': 'a' * 64}
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

    def test_owned_creation_launch_has_no_cli_project_and_rejects_incomplete_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory); contents = workspace / 'app'; (contents / 'bin').mkdir(parents=True)
            (contents / 'bin/pycharm.vmoptions').write_text('-Xmx1g\n', encoding='utf-8')
            layout = SimpleNamespace(contents=contents, platform='macos', jcmd=contents / 'jcmd')
            prepared = {'workspace': str(workspace), 'profile': str(workspace / 'profile'), 'properties': str(workspace / 'owned.properties'),
                        'project': str(workspace / 'project'), 'fixture': str(workspace / 'project/native-save.ipynb'),
                        'pluginDirectory': str(workspace / 'probe'), 'productionJarSha256': 'owned-jar', 'initialFixtureSha256': 'a' * 64}
            required = ['nativeUndoRestored', 'pendingCellAndTextMerge', 'nativeSavePersisted', 'postSaveExternalDirtyMerge',
                        'metadataAndExistingOutputsPreserved', 'closeReopenSourcePreserved', 'platformSaveAllPersisted',
                        'successfulReloadStatusRestored', 'successfulReloadStateClean', 'postSaveAllCanEdit']
            native = {**dict.fromkeys(required, True), 'status': 'pass', 'heartbeatTicksAfterSave': 3, 'invocationId': 'owned',
                      'plugin': {'jarSha256': 'owned-jar'}, 'normalIdeNewProjectCreation': True, 'normalIdeProjectOpen': True,
                      'expectedInitialFixtureHash': 'a' * 64, 'projectTrustBypassed': False, 'projectTrusted': True,
                      'globalTrustChecksDisabled': False, 'manualTrustClicked': False, 'projectCreationMode': 'normal-ide-new-owned-project',
                      'trustedProjectRoot': prepared['project'],
                      'parentTrustedBefore': False, 'parentTrustedAfter': False}
            process = SimpleNamespace(pid=123456, poll=lambda: 0, returncode=0)
            with patch.object(probe, 'app_layout', return_value=layout), patch.object(probe.uuid, 'uuid4', return_value=SimpleNamespace(hex='owned')), \
                 patch.object(probe.subprocess, 'Popen', return_value=process) as launch, patch.object(probe, 'stop_owned', return_value={'status': 'pass'}):
                for change in ({}, {'normalIdeNewProjectCreation': False}, {'normalIdeProjectOpen': False},
                               {'expectedInitialFixtureHash': 'b' * 64}, {'projectTrustBypassed': True}, {'parentTrustedAfter': True}):
                    (workspace / 'native-report.json').write_text(json.dumps({**native, **change}), encoding='utf-8')
                    result = probe.run(contents, prepared, 30)
                    self.assertEqual(result['assessment']['status'], 'fail' if change else 'pass')
                native.update(status='fail', stage='normal-owned-project-bootstrap', failure='Owned constructor failed')
                (workspace / 'native-report.json').write_text(json.dumps(native), encoding='utf-8')
                result = probe.run(contents, prepared, 30)
                self.assertEqual(result['assessment']['status'], 'fail')
                self.assertEqual(result['native']['failure'], 'Owned constructor failed')
                self.assertEqual(launch.call_args.args[0], [str(contents / 'MacOS/pycharm')])
            options = (workspace / 'probe.vmoptions').read_text(encoding='utf-8')
            self.assertIn('-Dopenpycharm.notebook.save.mode=normal-ide-new-owned-project', options)
            self.assertIn('-Dopenpycharm.notebook.save.initial.sha256=' + 'a' * 64, options)
            self.assertNotIn('idea.trust.all.projects', options)


if __name__ == '__main__':
    unittest.main()
