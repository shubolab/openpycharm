"""Product descriptor and optional actual-SDK controls; no Node or IDE execution.

OPENPYCHARM_FRONTEND_PRODUCT_SDK selects an already authenticated PC261 SDK.
OPENPYCHARM_FRONTEND_PRODUCT_BUNDLE optionally selects an already built plugin
directory. Tools are authenticated/read only, never launched or installed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'plugins/frontend'
NAMES = ('FrontendProductLspProvider', 'FrontendBundledRuntime', 'FrontendProductScope',
         'FrontendProjectSettings', 'FrontendSettingsLifecycle', 'FrontendProjectConfigurable',
         'FrontendNativeProcess', 'FrontendBoundedOutput', 'FrontendProcessLifetime')


class FrontendProductDescriptorTests(unittest.TestCase):
    def test_product_and_m0_have_separate_id_provider_and_resources(self):
        product = ET.parse(SOURCE / 'product-resources/META-INF/plugin.xml').getroot()
        m0 = ET.parse(SOURCE / 'resources/META-INF/plugin.xml').getroot()
        self.assertEqual(product.findtext('id'), 'dev.openpycharm.frontend')
        self.assertEqual(product.findtext('version'), '0.1.0-dev.4')
        self.assertNotEqual(product.findtext('id'), m0.findtext('id'))
        self.assertEqual({item.text for item in product.findall('depends')},
                         {'com.intellij.modules.platform', 'com.intellij.modules.lsp'})
        providers = product.findall("extensions[@defaultExtensionNs='com.intellij.platform.lsp']/integrationProvider")
        self.assertEqual([x.attrib['implementation'] for x in providers],
                         ['dev.openpycharm.frontend.FrontendProductLspProvider'])
        settings = product.find("extensions[@defaultExtensionNs='com.intellij']/projectConfigurable")
        self.assertEqual(settings.attrib['instance'], 'dev.openpycharm.frontend.FrontendProjectConfigurable')
        self.assertEqual(settings.attrib['id'], 'dev.openpycharm.frontend.settings')
        self.assertTrue((SOURCE / 'product-resources/META-INF/NOTICE').is_file())


@unittest.skipUnless(os.environ.get('OPENPYCHARM_FRONTEND_PRODUCT_SDK'), 'select an authenticated PC261 SDK for actual Java controls')
class FrontendProductSdkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import build_frontend_plugin as builder
        cls.builder = builder
        cls.layout = builder.sdk_layout(Path(os.environ['OPENPYCHARM_FRONTEND_PRODUCT_SDK']))
        cls.runtime = builder.execution_layout(cls.layout, None)
        (ROOT / '.tools').mkdir(exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix='frontend-product-unit-', dir=ROOT / '.tools')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        cls.classes = cls.directory / 'classes'
        builder.compile_java(cls.layout, cls.runtime,
                             [SOURCE / 'src/dev/openpycharm/frontend' / (name + '.java') for name in NAMES],
                             cls.classes, cls.directory / 'javac.args')
        cls.helpers = cls.directory / 'helpers'
        builder.compile_java(cls.layout, cls.runtime,
                             [ROOT / 'tests/frontend/FrontendProductCoreTest.java', ROOT / 'tests/frontend/FrontendProductBundleCheck.java'],
                             cls.helpers, cls.directory / 'helpers.args', [cls.classes])

    def helper(self, name, *args, jar=None):
        classpath = [self.helpers, jar or self.classes, *sorted(self.layout.lib.glob('*.jar'))]
        result = subprocess.run([str(self.runtime.java), '-Djava.awt.headless=true', '--class-path',
                                 os.pathsep.join(map(str, classpath)), 'dev.openpycharm.frontend.' + name,
                                 *map(str, args)], capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['status'], 'pass')
        self.assertFalse(report.get('nodeStarted', True))
        return report

    def test_actual_worker_settings_lifecycle_and_filesystem_controls(self):
        report = self.helper('FrontendProductCoreTest', self.directory / 'owned-core')
        self.assertGreaterEqual(report['checks'], 68)

    @unittest.skipUnless(os.environ.get('OPENPYCHARM_FRONTEND_PRODUCT_BUNDLE'), 'select an already built product bundle for real191 authentication')
    def test_full_bundle_authentication_without_execution(self):
        plugin = Path(os.environ['OPENPYCHARM_FRONTEND_PRODUCT_BUNDLE']).absolute()
        system = self.directory / 'owned-system'; system.mkdir()
        project = self.directory / 'owned-project'; project.mkdir()
        target = 'windows-x64' if sys.platform == 'win32' else 'macos-arm64'
        report = self.helper('FrontendProductBundleCheck', plugin, system, project, target, jar=plugin / 'lib/frontend.jar')
        self.assertTrue(report['fullPinned191PayloadAuthenticated'])


if __name__ == '__main__': unittest.main()
