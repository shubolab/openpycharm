import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_framework_plugin as builder


class FrameworkBuilderBoundaryTests(unittest.TestCase):
    def test_cross_platform_checks_require_an_authenticated_native_execution_sdk(self):
        windows = SimpleNamespace(platform='windows')
        mac = SimpleNamespace(platform='macos')
        with patch.object(builder.platform, 'system', return_value='Darwin'):
            with self.assertRaisesRegex(ValueError, 'native --host-sdk'):
                builder.execution_layout(windows)
            with patch.object(builder, 'sdk_layout', return_value=mac) as authenticated:
                self.assertIs(builder.execution_layout(windows, Path('/selected/host-sdk')), mac)
                authenticated.assert_called_once_with(Path('/selected/host-sdk'))

    def test_emitted_descriptor_has_the_requested_version_and_independent_identity(self):
        descriptor = b'<idea-plugin><id>dev.openpycharm.frameworks</id><version>@VERSION@</version></idea-plugin>'
        rendered = builder.render_descriptor(descriptor, '0.1.0-dev.2')
        self.assertIn(b'<version>0.1.0-dev.2</version>', rendered)
        self.assertNotIn(b'@VERSION@', rendered)
        for invalid in (descriptor.replace(b'dev.openpycharm.frameworks', b'Pythonid'),
                        descriptor.replace(b'@VERSION@', b'0.1.0-dev.1')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                builder.render_descriptor(invalid, '0.1.0-dev.2')

    def test_source_symlinks_cannot_import_reference_files_or_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'owned'
            source = root / 'plugins/frameworks'
            source.mkdir(parents=True)
            reference = Path(directory) / 'reference'
            reference.mkdir()
            secret = reference / 'reference.java'
            secret.write_bytes(b'read-only reference bytes')
            with patch.object(builder, 'ROOT', root), patch.object(builder, 'SOURCE', source):
                for link in (source / 'file.java', source / 'directory'):
                    link.symlink_to(secret if link.suffix else reference, target_is_directory=not link.suffix)
                    with self.subTest(link=link.name), self.assertRaisesRegex(ValueError, 'symlinks'):
                        builder.source_inputs()
                    link.unlink()
            self.assertEqual(secret.read_bytes(), b'read-only reference bytes')
            self.assertEqual(sorted(path.name for path in reference.iterdir()), ['reference.java'])

            linked_root = Path(directory) / 'linked-source'
            linked_root.mkdir()
            (reference / 'frameworks').mkdir()
            (linked_root / 'plugins').symlink_to(reference, target_is_directory=True)
            with patch.object(builder, 'ROOT', linked_root), patch.object(builder, 'SOURCE', linked_root / 'plugins/frameworks'):
                with self.assertRaisesRegex(ValueError, 'symlinks'):
                    builder.source_inputs()

    def test_checks_and_test_probe_never_write_under_a_supplied_product_plugin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'owned-repository'
            sources = root / 'tests/frameworks/native'
            sources.mkdir(parents=True)
            (sources / 'FrameworkProbe.java').write_text('test-only source')
            (sources / 'plugin.xml').write_text('<idea-plugin/>')
            script = root / 'scripts/build_framework_plugin.py'
            script.parent.mkdir()
            script.write_text('builder-identity')
            product = Path(directory) / 'signed-product/Contents/third-party-plugins/frameworks'
            jar = product / 'lib/frameworks.jar'
            jar.parent.mkdir(parents=True)
            jar.write_bytes(b'immutable packaged plugin')
            sdk = Path(directory) / 'authenticated-sdk/PyCharm.app'
            sdk.mkdir(parents=True)
            (sdk.parent / '.openpycharm-platform.json').write_text('authenticated-receipt')
            layout = SimpleNamespace(platform='macos', sdk_root=sdk)
            before = {str(path.relative_to(product)): path.read_bytes() for path in product.rglob('*') if path.is_file()}
            destinations = []

            def compile_owned(_layout, _sources, destination, _argument_file, *args, **kwargs):
                self.assertTrue(destination.is_relative_to(root / '.tools'))
                self.assertFalse(destination.is_relative_to(product))
                destinations.append(destination)
                destination.mkdir()
                (destination / 'FrameworkProbe.class').write_bytes(b'test class')
                return {'stdout': '', 'stderr': ''}

            with patch.object(builder, 'ROOT', root), patch.object(builder, '__file__', str(script)), \
                    patch.object(builder, 'sdk_layout', return_value=layout), \
                    patch.object(builder, 'execution_layout', return_value=layout), \
                    patch.object(builder, 'classpath', return_value=[]), \
                    patch.object(builder, 'check_space'), \
                    patch.object(builder, 'compile_java', side_effect=compile_owned), \
                    patch.object(builder, 'run_java', return_value=SimpleNamespace(stdout=json.dumps({'status': 'pass'}))):
                checks = builder.run_command_tests(sdk, product)
                probe = builder.build_native_probe(sdk, product)
            self.assertEqual(checks['status'], 'pass')
            self.assertTrue(probe.is_relative_to(root / '.tools'))
            self.assertTrue((probe / 'lib/framework-probe.jar').is_file())
            self.assertEqual(len(destinations), 2)
            after = {str(path.relative_to(product)): path.read_bytes() for path in product.rglob('*') if path.is_file()}
            self.assertEqual(after, before)
            self.assertEqual(sorted(path.relative_to(product).as_posix() for path in product.rglob('*')), ['lib', 'lib/frameworks.jar'])


if __name__ == '__main__':
    unittest.main()
