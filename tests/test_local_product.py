"""Descriptor registration controls protect development-service credentials."""
import struct
import tempfile
import unittest
from pathlib import Path
from xml.sax.saxutils import escape

from scripts.local_product import apply, cache_records, owned_file, xml_filter


class LocalProductDescriptorTests(unittest.TestCase):
    def test_sync_and_promo_removed_without_touching_git_authentication(self):
        data = b'''<idea-plugin>
  <content><module name="intellij.settingsSync.core"/><module name="Git4Idea"/></content>
  <extensions defaultExtensionNs="com.intellij">
    <pluginSuggestionProvider order="first" implementation="com.jetbrains.python.suggestions.PycharmProSuggestionProvider"/>
    <applicationService serviceImplementation="org.jetbrains.plugins.github.authentication.GHAccountsRepository"/>
    <applicationService serviceImplementation="git4idea.credentials.GitCredentialManager"/>
  </extensions>
</idea-plugin>'''
        filtered, removed = xml_filter(data, {"intellij.settingsSync.core"})
        self.assertEqual(2, len(removed))
        expected = data.replace(b'<module name="intellij.settingsSync.core"/>', b'').replace(
            b'<pluginSuggestionProvider order="first" implementation="com.jetbrains.python.suggestions.PycharmProSuggestionProvider"/>', b'')
        self.assertEqual(expected, filtered)

    def test_cdata_and_comments_cannot_forge_registration_nodes(self):
        data = b'''<idea-plugin>
<description><![CDATA[<module name="intellij.settingsSync.core"/>]]></description>
<!-- <pluginSuggestionProvider implementation="com.jetbrains.python.suggestions.PycharmProSuggestionProvider"/> -->
<content><module name="ordinary.feature"/></content>
</idea-plugin>'''
        self.assertEqual((data, []), xml_filter(data, {"intellij.settingsSync.core"}))

    def test_namesake_attribute_in_other_descriptor_context_is_preserved(self):
        data = b'<idea-plugin><dependencies><module name="intellij.settingsSync.core"/></dependencies></idea-plugin>'
        # Runtime dependency edges have their own checked graph policy. A broad
        # textual removal here would hide an otherwise unresolved dependency.
        self.assertEqual((data, []), xml_filter(data, {"intellij.settingsSync.core"}))

    def test_entity_declarations_are_rejected(self):
        data = b'<!DOCTYPE idea-plugin [<!ENTITY x "anything">]><idea-plugin/>'
        with self.assertRaisesRegex(ValueError, "DTD/entity"):
            xml_filter(data, set())

    def test_embedded_module_descriptor_is_filtered_in_fast_loader_cache(self):
        nested = '<idea-plugin><extensions><pluginSuggestionProvider implementation="com.jetbrains.python.suggestions.PycharmProSuggestionProvider"/><ordinaryFeature implementation="PythonDebugger"/></extensions></idea-plugin>'
        removed = '<pluginSuggestionProvider implementation="com.jetbrains.python.suggestions.PycharmProSuggestionProvider"/>'
        encode = lambda text: escape(text, {'"': '&quot;'}).encode()
        prefix = b'<idea-plugin><content><module name="intellij.python.community.impl" loading="required">'
        suffix = b'</module></content></idea-plugin>'
        for before, after in ((encode(nested), encode(nested.replace(removed, ''))),
                              (b'<![CDATA[' + nested.encode() + b']]>', b'<![CDATA[' + nested.replace(removed, '').encode() + b']]>')):
            with self.subTest(encoding=before[:10]):
                filtered, report = xml_filter(prefix + before + suffix, set())
                self.assertEqual(prefix + after + suffix, filtered)
                self.assertEqual('intellij.python.community.impl', report[0]['embeddedModule'])

    def test_cache_preserves_non_xml_record_bytes_and_rejects_truncation(self):
        core = b'<idea-plugin><id>core</id></idea-plugin>'
        descriptor = b'<idea-plugin><id>Git4Idea</id></idea-plugin>'
        utf = lambda value: struct.pack('>H', len(value)) + value
        record = struct.pack('>H', 1) + utf(b'vcs-git') + struct.pack('>i', len(descriptor)) + descriptor + utf(b'lib/git4idea.jar')
        data = b'\x02\x01' + struct.pack('>i', len(core)) + core + struct.pack('>H', 1) + record
        parsed_core, records = cache_records(data)
        self.assertEqual(core, parsed_core)
        self.assertEqual('Git4Idea', records[0]['id'])
        self.assertEqual(record, records[0]['raw'])
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            cache_records(data[:-1])
        with self.assertRaisesRegex(ValueError, 'Trailing'):
            cache_records(data + b'\0')

    def test_source_sdk_is_rejected_before_any_write(self):
        sdk = Path(__file__).resolve().parents[1] / '.tools/platform/immutable-sdk/Contents'
        with self.assertRaisesRegex(ValueError, 'outside the SDK'):
            apply(sdk)

    def test_descendant_symlink_cannot_redirect_a_write_to_source_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source-sdk.dat'
            source.write_bytes(b'immutable upstream bytes')
            product = root / 'product'
            product.mkdir()
            redirected = product / 'module-descriptors.dat'
            redirected.symlink_to(source)
            with self.assertRaisesRegex(ValueError, 'Symbolic link'):
                owned_file(product, redirected)
            self.assertEqual(b'immutable upstream bytes', source.read_bytes())


if __name__ == '__main__':
    unittest.main()
