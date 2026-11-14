#!/usr/bin/env python3
"""Prepare a separate default-off frontend ZIP/overlay candidate, never an IDE build/release.

Keeps the dev.3 baseline sources and four-plugin assembler unchanged. No Node,
provisioning, download, installation, native application or installer is run.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

import build_frontend_plugin as frontend
from bootstrap import sha256
from provenance import source_inputs
from provision_frontend_tools import ROOT, PIN, owned

BASELINE = '913e59b4b41704ca5a25baa6cc1134013b6b5e35'
BASELINE_INPUT_COUNT = 145
NEW_SCRIPTS = {'scripts/build_frontend_plugin.py', 'scripts/frontend_native_api_audit.py',
               'scripts/frontend_protocol_probe.py', 'scripts/provision_frontend_tools.py',
               'scripts/prepare_frontend_candidate.py'}


def baseline_inputs(root: Path = ROOT) -> dict[str, str]:
    result = subprocess.run(['git', 'ls-tree', '-r', '-z', BASELINE, '--', 'scripts', 'product', 'plugins',
                             'requirements-build.txt', 'LICENSE', 'NOTICE'], cwd=root,
                            capture_output=True, check=True)
    values = {}
    for entry in result.stdout.split(b'\0'):
        if not entry: continue
        metadata, name = entry.split(b'\t', 1); mode, kind, oid = metadata.split(b' '); path = name.decode('utf-8')
        if mode not in {b'100644', b'100755'} or kind != b'blob':
            raise ValueError('Baseline source contains a nonregular Git entry')
        content = subprocess.run(['git', 'cat-file', 'blob', oid.decode('ascii')], cwd=root,
                                 capture_output=True, check=True).stdout
        values[path] = hashlib.sha256(content).hexdigest()
    if len(values) != BASELINE_INPUT_COUNT:
        raise ValueError(f'Expected the exact {BASELINE_INPUT_COUNT}-input dev.3 baseline, got {len(values)}')
    return dict(sorted(values.items()))


def compare_sources(baseline: dict[str, str], current: dict[str, str]) -> dict[str, str]:
    removed = sorted(baseline.keys() - current.keys())
    changed = sorted(path for path in baseline.keys() & current.keys() if baseline[path] != current[path])
    if removed or changed:
        raise ValueError('Existing dev.3 production inputs changed: ' + ', '.join(removed + changed))
    added = {path: current[path] for path in sorted(current.keys() - baseline.keys())}
    unexpected = [path for path in added if not path.startswith('plugins/frontend/') and path not in NEW_SCRIPTS]
    if unexpected: raise ValueError('New sources are not frontend-only: ' + ', '.join(unexpected))
    return added


def protected_release_files() -> dict[str, str]:
    result = {}
    for name in ('README.md', 'README.zh-CN.md'):
        expected = subprocess.run(['git', 'show', BASELINE + ':' + name], cwd=ROOT, capture_output=True, check=True).stdout
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != expected:
            raise ValueError('Keep the published dev.3 README unchanged: ' + name)
        result[name] = hashlib.sha256(expected).hexdigest()
    return result


def prepare(sdk: Path, output: Path, *, determinism: bool = False, tests: bool = False) -> dict:
    output = owned(output)
    if output.exists(): raise ValueError('Choose a new owned frontend candidate output')
    baseline = baseline_inputs(); all_inputs = source_inputs(); extra = compare_sources(baseline, all_inputs)
    protected = protected_release_files()
    directory, build = frontend.build(sdk, force_rebuild=True)
    first_digest = build['jarSha256']; first_payloads = build['payloadSha256']
    if determinism:
        directory, build = frontend.build(sdk, force_rebuild=True)
        if build['jarSha256'] != first_digest or build['payloadSha256'] != first_payloads:
            raise ValueError('Forced frontend compilation did not produce identical JAR/payload bytes')
    checks = frontend.checks(sdk, directory) if tests else None
    if source_inputs() != all_inputs: raise ValueError('Sources changed during candidate preparation')
    source = owned(directory / 'lib/frontend-m0.jar')
    if source.is_symlink() or not source.is_file() or sha256(source) != build['jarSha256']:
        raise ValueError('Compiled frontend bytes differ from the authenticated build')
    with source.open('rb') as stream: payload = stream.read(128 * 1024**2 + 1)
    if len(payload) > 128 * 1024**2 or hashlib.sha256(payload).hexdigest() != build['jarSha256']:
        raise ValueError('Frontend payload changed before candidate capture')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.frontend-candidate-', dir=output.parent) as temporary:
        stage = Path(temporary); plugin = stage / 'frontend-m0/lib'; plugin.mkdir(parents=True)
        (plugin / 'frontend-m0.jar').write_bytes(payload)
        if sha256(plugin / 'frontend-m0.jar') != build['jarSha256']:
            raise ValueError('Copied frontend payload digest differs')
        archive = stage / 'frontend-candidate.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            entry = zipfile.ZipInfo('frontend-m0/lib/frontend-m0.jar', (1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED; entry.external_attr = 0o100644 << 16
            zip_file.writestr(entry, payload)
        report = {'schema': 1, 'scope': 'Next-only frontend plugin overlay candidate; no assembled IDE/installer/release',
                  'baseCommit': BASELINE, 'baselineProductionInputCount': len(baseline),
                  'baselineProductionInputs': baseline, 'baselineInputsUnchanged': True,
                  'protectedReleaseReadmes': protected,
                  'frontendSourceInputs': extra, 'allSourceInputs': all_inputs,
                  'defaultProductPluginIds': ['dev.openpycharm.http', 'dev.openpycharm.frameworks', 'dev.openpycharm.notebooks', 'dev.openpycharm.database'],
                  'additionalCandidatePlugin': {'id': frontend.ID, 'version': build['version'],
                      'path': 'frontend-m0', 'jar': 'frontend-m0/lib/frontend-m0.jar', 'jarSha256': build['jarSha256'],
                      'toolsLockSha256': sha256(PIN), 'build': build},
                  'candidateZipSha256': sha256(archive), 'deterministicForcedCompiles': 2 if determinism else 1,
                  'deterministicJarAndPayloads': True if determinism else None, 'checks': checks,
                  'runtimeToolsBundled': False, 'runtimeToolsProvisioned': False, 'nodeExecuted': False,
                  'automaticDownloadOrInstall': False, 'activationEnabledByDefault': False,
                  'nativeIdeStarted': False, 'nativeServiceDocumentUiOrWindowsAccepted': False,
                  'productVersionOrRootReadmesChanged': False,
                  'limitations': ['Owned-fixture/cache boundaries remain compiled into the plugin; this is a local acceptance candidate',
                                 'Root must explicitly prepare authenticated tools and normal trusted native acceptance later',
                                 'Unexpected parent-crash reparenting and Windows native lifecycle remain unverified']}
        (stage / 'candidate.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        if source_inputs() != all_inputs or protected_release_files() != protected:
            raise ValueError('Sources/release READMEs changed before candidate promotion')
        if output.exists(): raise ValueError('Candidate output appeared before promotion')
        stage.rename(output)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify-determinism', action='store_true'); parser.add_argument('--test', action='store_true')
    args = parser.parse_args(); report = prepare(args.sdk, args.output, determinism=args.verify_determinism, tests=args.test)
    print(json.dumps({'candidate': str(owned(args.output)), 'jarSha256': report['additionalCandidatePlugin']['jarSha256'],
                      'zipSha256': report['candidateZipSha256'], 'baselineCount': report['baselineProductionInputCount'],
                      'frontendCount': len(report['frontendSourceInputs']), 'nodeExecuted': False}))
    return 0

if __name__ == '__main__': raise SystemExit(main())
