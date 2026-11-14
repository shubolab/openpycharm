#!/usr/bin/env python3
"""Offline SDK boot/module/EP/service and candidate descriptor closure; no IDE startup."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
from bootstrap import sha256
from build_frontend_plugin import ID, sdk_layout, source_inputs
from provision_frontend_tools import ROOT, owned


def audit(sdk: Path, build_report: Path) -> dict:
    layout = sdk_layout(sdk)
    build = json.loads(build_report.read_text(encoding='utf-8'))['build']
    if build['identity']['sources'] != source_inputs():
        raise ValueError('Audit only the current compiled frontend candidate')
    jar = owned(Path(build['pluginDirectory']) / 'lib/frontend-m0.jar')
    if sha256(jar) != build['jarSha256']:
        raise ValueError('Candidate JAR changed after compilation')
    product = json.loads(layout.product_info.read_text(encoding='utf-8'))
    boot = {name for launch in product['launch'] for name in launch['bootClassPathJarNames']}
    names = ['intellij.platform.lsp.jar', 'intellij.platform.lsp.impl.jar', 'eclipse.lsp4j.jar', 'eclipse.lsp4j.jsonrpc.jar']
    if not set(names).issubset(boot):
        raise ValueError('Authenticated target does not place public LSP modules on its boot classpath')
    with zipfile.ZipFile(layout.lib / 'intellij.platform.lsp.impl.jar') as archive:
        xml = archive.read('intellij.platform.lsp.impl.xml')
    module = ET.fromstring(xml)
    alias = next((value.attrib for value in module.findall('module') if value.get('value') == 'com.intellij.modules.lsp'), None)
    ep = next((value.attrib for value in module.findall('extensionPoints/extensionPoint') if value.get('qualifiedName') == 'com.intellij.platform.lsp.integrationProvider'), None)
    service = next((value.attrib for value in module.findall('extensions/projectService') if value.get('serviceInterface') == 'com.intellij.platform.lsp.api.LspClientManager'), None)
    if alias is None or ep is None or service is None:
        raise ValueError('Actual SDK module/EP/project service registration is incomplete')
    with zipfile.ZipFile(jar) as archive:
        descriptor = ET.fromstring(archive.read('META-INF/plugin.xml'))
        dependencies = sorted(value.text for value in descriptor.findall('depends'))
        integration = descriptor.find('extensions/integrationProvider')
        if descriptor.findtext('id') != ID or dependencies != ['com.intellij.modules.lsp', 'com.intellij.modules.platform'] or integration is None:
            raise ValueError('Candidate normal dependency/EP declaration differs')
        implementation = integration.get('implementation')
        if implementation.replace('.', '/') + '.class' not in archive.namelist():
            raise ValueError('Candidate implementation class is absent')
    return {'schema': 1, 'status': 'static-registration-closure-pass', 'sdkReceiptSha256': build['identity']['sdkReceiptSha256'],
            'actualBootJars': {name: sha256(layout.lib / name) for name in names}, 'moduleAlias': alias,
            'extensionPoint': ep, 'projectService': service, 'candidateDependencies': dependencies,
            'candidateImplementation': implementation, 'candidateJarSha256': sha256(jar),
            'sourceInputsStillCurrent': True, 'nativeIdeStarted': False, 'nativeModuleEpServiceActivationObserved': False,
            'limitations': ['Static actual-SDK registration and classpath closure do not prove plugin classloader, service startup, native document/UI behavior, or Windows runtime']}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True); parser.add_argument('--build-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / '.tools/frontend-native-api-audit.json')
    args = parser.parse_args(); output = owned(args.output)
    report = audit(args.sdk, args.build_report); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8'); print(json.dumps(report))
    return 0

if __name__ == '__main__': raise SystemExit(main())
