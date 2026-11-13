import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_notebook_plugin as builder


class NotebookBuilderBoundaryTests(unittest.TestCase):
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
        descriptor = b'<idea-plugin><id>dev.openpycharm.notebooks</id><version>@VERSION@</version></idea-plugin>'
        rendered = builder.render_descriptor(descriptor, '0.1.0-dev.2')
        self.assertIn(b'<version>0.1.0-dev.2</version>', rendered)
        self.assertNotIn(b'@VERSION@', rendered)
        for invalid in (descriptor.replace(b'dev.openpycharm.notebooks', b'Pythonid'),
                        descriptor.replace(b'@VERSION@', b'0.1.0-dev.1')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                builder.render_descriptor(invalid, '0.1.0-dev.2')

    def test_source_symlinks_cannot_import_reference_files_or_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'owned'
            source = root / 'plugins/notebooks'
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
            (reference / 'notebooks').mkdir()
            (linked_root / 'plugins').symlink_to(reference, target_is_directory=True)
            with patch.object(builder, 'ROOT', linked_root), patch.object(builder, 'SOURCE', linked_root / 'plugins/notebooks'):
                with self.assertRaisesRegex(ValueError, 'symlinks'):
                    builder.source_inputs()


if __name__ == '__main__':
    unittest.main()
