from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import prepare_frontend_candidate as candidate


class FrontendCandidateTests(unittest.TestCase):
    def setUp(self):
        parent=candidate.ROOT/'.tools'; parent.mkdir(exist_ok=True)
        self.directory=tempfile.TemporaryDirectory(prefix='frontend-candidate-unit-',dir=parent)
        self.addCleanup(self.directory.cleanup); self.root=Path(self.directory.name)
        self.plugin=self.root/'compiled'; (self.plugin/'lib').mkdir(parents=True)
        self.jar=self.plugin/'lib/frontend-m0.jar'; self.jar.write_bytes(b'owned candidate packaging control')
        self.digest=hashlib.sha256(self.jar.read_bytes()).hexdigest()
        self.report={'jarSha256':self.digest,'version':'0.1.0-dev.4-m0','payloadSha256':{'plugin':self.digest}}
        self.baseline={'scripts/package.py':'a'*64,'plugins/notebooks/src/Notebook.java':'b'*64}
        self.inputs={**self.baseline,'plugins/frontend/src/Frontend.java':'c'*64}
        self.protected={'README.md':'d'*64,'README.zh-CN.md':'e'*64}

    def test_default_overlay_keeps_baseline_and_does_not_invoke_runtime_checks(self):
        output=self.root/'candidate'
        with patch.object(candidate,'baseline_inputs',return_value=self.baseline), patch.object(candidate,'source_inputs',return_value=self.inputs), \
             patch.object(candidate,'protected_release_files',return_value=self.protected), \
             patch.object(candidate.frontend,'build',return_value=(self.plugin,self.report)) as build, \
             patch.object(candidate.frontend,'checks') as checks:
            report=candidate.prepare(Path('/authenticated/sdk'),output)
        checks.assert_not_called(); build.assert_called_once_with(Path('/authenticated/sdk'),force_rebuild=True)
        self.assertFalse(report['nodeExecuted']); self.assertFalse(report['runtimeToolsBundled'])
        self.assertEqual(report['baselineProductionInputs'],self.baseline)
        self.assertEqual(report['frontendSourceInputs'],{'plugins/frontend/src/Frontend.java':'c'*64})
        self.assertEqual(len(report['defaultProductPluginIds']),4)
        with zipfile.ZipFile(output/'frontend-candidate.zip') as archive:
            self.assertEqual(archive.namelist(),['frontend-m0/lib/frontend-m0.jar'])
            self.assertEqual(archive.read(archive.namelist()[0]),self.jar.read_bytes())
        self.assertEqual(json.loads((output/'candidate.json').read_text())['additionalCandidatePlugin']['toolsLockSha256'],
                         '5a7b20ce2ce915a4012b4ea5dfa35b77c709bdbb19de00be87700404a6f6fff2')

    def test_determinism_forces_two_compiles_and_rejects_changed_bytes(self):
        with patch.object(candidate,'baseline_inputs',return_value=self.baseline), patch.object(candidate,'source_inputs',return_value=self.inputs), \
             patch.object(candidate,'protected_release_files',return_value=self.protected), \
             patch.object(candidate.frontend,'build',side_effect=[(self.plugin,self.report),(self.plugin,{**self.report,'jarSha256':'0'*64})]) as build:
            with self.assertRaisesRegex(ValueError,'identical JAR'):
                candidate.prepare(Path('/sdk'),self.root/'must-not-promote',determinism=True)
        self.assertEqual(build.call_count,2);self.assertFalse((self.root/'must-not-promote').exists())
        self.assertTrue(all(call.kwargs=={'force_rebuild':True} for call in build.call_args_list))

    def test_changed_compiled_jar_is_rejected_before_candidate_promotion(self):
        self.jar.write_bytes(b'unreceipted bytes')
        with patch.object(candidate,'baseline_inputs',return_value=self.baseline), patch.object(candidate,'source_inputs',return_value=self.inputs), \
             patch.object(candidate,'protected_release_files',return_value=self.protected), \
             patch.object(candidate.frontend,'build',return_value=(self.plugin,self.report)):
            with self.assertRaisesRegex(ValueError,'authenticated build'):
                candidate.prepare(Path('/sdk'),self.root/'rejected-jar')
        self.assertFalse((self.root/'rejected-jar').exists())

    def test_published_readme_changes_are_rejected_before_compiling(self):
        with patch.object(candidate,'baseline_inputs',return_value=self.baseline), patch.object(candidate,'source_inputs',return_value=self.inputs), \
             patch.object(candidate,'protected_release_files',side_effect=ValueError('Keep the published dev.3 README unchanged')), \
             patch.object(candidate.frontend,'build') as build:
            with self.assertRaisesRegex(ValueError,'README unchanged'):
                candidate.prepare(Path('/sdk'),self.root/'rejected-readme')
            build.assert_not_called()

    def test_actual_readme_guard_uses_its_selected_baseline_and_rejects_changes(self):
        # Use a self-contained Git history; a shallow checkout need not contain
        # the historical dev.3 commit just to run these packaging unit controls.
        release = self.root / 'owned-release'; release.mkdir()
        original = {'README.md': b'owned English release README\n', 'README.zh-CN.md': b'owned Chinese release README\n'}
        for name, data in original.items(): (release / name).write_bytes(data)
        def git(*args):
            return subprocess.run(['git', *args], cwd=release, capture_output=True, check=True).stdout
        git('init'); git('add', 'README.md', 'README.zh-CN.md')
        git('-c', 'user.name=Owned Test', '-c', 'user.email=owned-test@example.invalid', 'commit', '-m', 'Owned baseline')
        baseline = git('rev-parse', 'HEAD').decode().strip()
        with patch.object(candidate, 'ROOT', release), patch.object(candidate, 'BASELINE', baseline):
            expected = {name: hashlib.sha256(data).hexdigest() for name, data in original.items()}
            self.assertEqual(candidate.protected_release_files(), expected)
            for name, data in original.items():
                (release / name).write_bytes(data + b'changed')
                with self.subTest(readme=name), self.assertRaisesRegex(ValueError, 'README unchanged'):
                    candidate.protected_release_files()
                (release / name).write_bytes(data)

    def test_changed_removed_or_unrelated_sources_fail_before_building(self):
        for current in ({**self.inputs,'scripts/package.py':'d'*64},
                        {k:v for k,v in self.inputs.items() if k!='scripts/package.py'},
                        {**self.inputs,'plugins/database/New.java':'e'*64}):
            with self.subTest(current=current), patch.object(candidate,'baseline_inputs',return_value=self.baseline), \
                 patch.object(candidate,'source_inputs',return_value=current),patch.object(candidate.frontend,'build') as build:
                with self.assertRaises(ValueError): candidate.prepare(Path('/sdk'),self.root/'rejected')
                build.assert_not_called()


if __name__=='__main__': unittest.main()
