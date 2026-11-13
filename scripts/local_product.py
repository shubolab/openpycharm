"""Remove account/cloud/promotion registrations from our pinned OSS product.

The v2 bundled-plugin cache framing and public runtime-repository workflow are
adapted from shubolab/opengoland's product_metadata.py/local_ide_metadata.py.
The upstream format authority is IntelliJ commit
456919a9624bae72ac12efafc35d2b916cb0c5c5 (Apache-2.0). Untouched XML bytes and
plugin records are preserved, including CDATA. No license checks are changed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from xml.parsers import expat
from xml.sax.saxutils import escape
import zipfile

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "product/local-policy.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def owned_file(contents: Path, path: Path) -> Path:
    """Reject descendant symlinks before opening any output for writing."""
    try:
        relative = path.relative_to(contents)
    except ValueError as error:
        raise ValueError("Product file escapes its owned root") from error
    current = contents
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symbolic link in mutable product path: " + str(relative))
    if not path.is_file() or not path.resolve().is_relative_to(contents.resolve()):
        raise ValueError("Expected an owned regular product file: " + str(relative))
    return path


class Reader:
    def __init__(self, data: bytes):
        self.data, self.at = data, 0

    def take(self, size: int) -> bytes:
        if size < 0 or self.at + size > len(self.data):
            raise ValueError("Truncated bundled-plugin classpath")
        result = self.data[self.at:self.at + size]
        self.at += size
        return result

    def number(self, form: str) -> int:
        return struct.unpack(form, self.take(struct.calcsize(form)))[0]

    def utf(self) -> str:
        value = self.take(self.number(">H"))
        if not value or not value.isascii() or b"\0" in value:
            raise ValueError("Unexpected path encoding in pinned bundled-plugin cache")
        return value.decode("ascii")


def cache_records(data: bytes):
    """Parse the public jar-only v2 writer; retain raw slices for every record."""
    r = Reader(data)
    if r.take(2) != b"\x02\x01":
        raise ValueError("Unsupported bundled-plugin classpath format")
    core = r.take(r.number(">i"))
    count = r.number(">H")
    records = []
    for _ in range(count):
        begin = r.at
        file_count = r.number(">H")
        if not file_count:
            raise ValueError("Empty bundled-plugin file list")
        directory = r.utf()
        xml_length_at = r.at
        descriptor = r.take(r.number(">i"))
        xml_end = r.at
        for _ in range(file_count):
            r.utf()
        identity = ET.fromstring(descriptor).findtext("id")
        records.append({"directory": directory, "id": identity, "descriptor": descriptor,
                        "head": data[begin:xml_length_at], "tail": data[xml_end:r.at],
                        "raw": data[begin:r.at]})
    if r.at != len(data):
        raise ValueError("Trailing bundled-plugin classpath bytes")
    return core, records


def xml_filter(data: bytes, excluded: set[str]) -> tuple[bytes, list[dict]]:
    """Select registered features by exact identity; preserve other raw bytes."""
    parser = expat.ParserCreate()
    stack, elements = [], []

    def reject(*unused):
        raise ValueError("Descriptor DTD/entity declarations are unsupported")

    def start(tag, attrs):
        at, quote = parser.CurrentByteIndex, None
        while at < len(data):
            value = data[at]
            if quote is not None:
                if value == quote:
                    quote = None
            elif value in (34, 39):
                quote = value
            elif value == 62:
                break
            at += 1
        if at == len(data):
            raise ValueError("Unclosed descriptor tag")
        stack.append([tag, attrs, stack[-1][0] if stack else None,
                      parser.CurrentByteIndex, data[parser.CurrentByteIndex:at].rstrip().endswith(b"/"), [], at + 1])

    def end(tag):
        name, attrs, parent, begin, empty, text, body_start = stack.pop()
        if name != tag:
            raise ValueError("Invalid descriptor nesting")
        finish = close_start = parser.CurrentByteIndex
        if not empty:
            if data[finish:finish + 2] != b"</":
                raise ValueError("Invalid descriptor closing tag")
            finish = data.index(b">", finish) + 1
        elements.append((name, attrs, parent, begin, finish, "".join(text), body_start, close_start))

    def chars(value):
        if stack:
            stack[-1][5].append(value)

    parser.StartElementHandler, parser.EndElementHandler = start, end
    parser.CharacterDataHandler = chars
    parser.StartDoctypeDeclHandler = parser.EntityDeclHandler = parser.ExternalEntityRefHandler = reject
    parser.Parse(data, True)
    advertiser = "com.intellij.openapi.updateSettings.impl.pluginsAdvertisement."
    targets = []
    for tag, attrs, parent, begin, finish, text, body_start, close_start in elements:
        selected = (
            (tag == "module" and parent == "content" and attrs.get("name") in excluded)
            or (tag == "pluginSuggestionProvider" and attrs.get("implementation") == "com.jetbrains.python.suggestions.PycharmProSuggestionProvider")
            or (tag == "openAnotherToolHandler" and attrs.get("implementation") == "com.intellij.openapi.updateSettings.impl.upgradeToUltimate.installation.install.TryUltimateActionHandler")
            or (tag == "editorNotificationProvider" and attrs.get("implementation") == advertiser + "PluginAdvertiserEditorNotificationProvider")
            or (tag == "backgroundPostStartupActivity" and attrs.get("implementation") == advertiser + "PluginsAdvertiserStartupActivity")
            or (tag == "action" and attrs.get("id") == "CheckSuggestedPlugins" and attrs.get("class") == advertiser + "CheckSuggestedPluginsAction")
            or (tag == "applicationConfigurable" and attrs.get("instance") == "com.intellij.ide.gdpr.ConsentConfigurable" and attrs.get("id") == "consents")
            or (tag == "depends" and attrs.get("optional") == "true" and text.strip() == "tanvd.grazi")
        )
        if selected:
            targets.append((begin, finish, {"tag": tag, "attributes": attrs, "sha256": sha(data[begin:finish])}, b""))
        elif tag == "module" and parent == "content" and text.lstrip().startswith("<idea-plugin"):
            # The 2026 fast-loader stores content descriptors as escaped XML
            # text (or CDATA). Editing their source JAR alone is insufficient.
            nested, nested_changes = xml_filter(text.encode("utf-8"), excluded)
            if nested_changes:
                raw_body = data[body_start:close_start]
                encoded_body = None
                for entities in ({'"': '&quot;', "'": '&apos;'}, {'"': '&quot;'}, {}):
                    if escape(text, entities).encode("utf-8") == raw_body:
                        encoded_body = escape(nested.decode("utf-8"), entities).encode("utf-8")
                        break
                if encoded_body is None and raw_body == b"<![CDATA[" + text.encode("utf-8") + b"]]>":
                    if b"]]>" in nested:
                        raise ValueError("Unsupported CDATA terminator in embedded descriptor")
                    encoded_body = b"<![CDATA[" + nested + b"]]>"
                if encoded_body is None:
                    raise ValueError("Embedded module descriptor escaping does not roundtrip")
                replacement = data[begin:body_start] + encoded_body + data[close_start:finish]
                targets.append((begin, finish, {"embeddedModule": attrs.get("name"), "nestedRemovals": nested_changes}, replacement))
    targets.sort()
    chunks, cursor, report = [], 0, []
    for begin, finish, record, replacement in targets:
        if begin < cursor:
            continue  # a selected parent already removes this nested declaration
        chunks.extend((data[cursor:begin], replacement))
        cursor = finish
        report.append(record)
    chunks.append(data[cursor:])
    result = b"".join(chunks)
    if report:
        ET.fromstring(result)
    return result, report


def rewrite_jar(path: Path, replacements: dict[str, bytes], removals: set[str] = frozenset()):
    """Keep all unselected entry bytes; clear only stale optimized ZIP offsets."""
    output = path.with_name(path.name + ".openpycharm-tmp")
    try:
        with zipfile.ZipFile(path) as before, zipfile.ZipFile(output, "w") as after:
            names = before.namelist()
            if len(names) != len(set(names)):
                raise ValueError("Duplicate entries in product JAR: " + str(path))
            # IntelliJ ImmutableZipFile's five-byte v4 trailer contains offsets
            # that cannot survive rewriting. Empty selects its central directory.
            after.comment = b"" if len(before.comment) == 5 and before.comment[0] == 4 else before.comment
            for item in before.infolist():
                if item.filename not in removals:
                    after.writestr(item, replacements.get(item.filename, before.read(item.filename)))
        output.chmod(path.stat().st_mode & 0o777)
        output.replace(path)
    finally:
        output.unlink(missing_ok=True)


def _module_repository(contents: Path, excluded: set[str], policy: dict, sdk_contents: Path | None = None) -> dict:
    source_dat = contents / "modules/module-descriptors.dat"
    source_jar = contents / "modules/module-descriptors.jar"
    if not source_dat.is_file() or not source_jar.is_file():
        raise ValueError("Pinned runtime-module repository is missing")
    replacements, dropped, edges = {}, set(), []
    with zipfile.ZipFile(source_jar) as archive:
        modules = {name[:-4] for name in archive.namelist() if name.endswith(".xml")}
        excluded.intersection_update(modules)
        for entry in archive.infolist():
            if not entry.filename.endswith(".xml"):
                continue
            owner = entry.filename[:-4]
            if owner in excluded:
                dropped.add(entry.filename)
                continue
            data = archive.read(entry)
            xml = ET.fromstring(data)
            changes = []
            for dependency in xml.findall("dependencies/module"):
                name = dependency.get("name")
                if name in excluded:
                    if owner not in policy["optionalDependencyOwners"]:
                        raise ValueError(f"Undeclared incoming dependency on excluded module: {owner} -> {name}")
                    changes.append((owner, name))
            if changes:
                modified = data
                for _, dependency in changes:
                    # Public serializer writes one exact standalone module line.
                    line = f'    <module name="{dependency}"/>\n'.encode()
                    if modified.count(line) != 1:
                        raise ValueError("Unknown runtime descriptor XML framing")
                    modified = modified.replace(line, b"", 1)
                replacements[entry.filename] = modified
                edges.extend(changes)
    before = {"dat": sha(source_dat.read_bytes()), "jar": sha(source_jar.read_bytes())}
    # Keep compiler outputs outside a macOS .app. Besides preserving its bundle
    # shape, this avoids macOS bundle-protection writes after a launch attempt.
    staging_parent = contents.parent.parent if contents.parent.suffix == ".app" else contents.parent
    with tempfile.TemporaryDirectory(prefix="local-modules-", dir=staging_parent) as temporary:
        stage = Path(temporary)
        filtered_jar = stage / "module-descriptors.jar"
        shutil.copyfile(source_jar, filtered_jar)
        rewrite_jar(filtered_jar, replacements, dropped)
        removed_ids, removed_edges = stage / "ids.txt", stage / "edges.txt"
        removed_ids.write_text("".join(name + "\n" for name in sorted(excluded)), encoding="utf-8")
        removed_edges.write_text("".join(owner + "\t" + dependency + "\n" for owner, dependency in sorted(edges)), encoding="utf-8")
        sdk = Path(sdk_contents).resolve() if sdk_contents is not None else contents
        bundled_java = sdk / ("jbr/Contents/Home/bin/java" if (sdk / "jbr/Contents/Home").is_dir() else "jbr/bin/java.exe")
        java = Path(os.environ.get("OPENPYCHARM_JAVA", str(bundled_java)))
        classpath = os.pathsep.join(str(sdk / "lib" / name) for name in ("platform-loader.jar", "annotations.jar"))
        result = subprocess.run([str(java), "--class-path", classpath,
                                 str(ROOT / "product/LocalModuleRepository.java"),
                                 str(source_dat), str(filtered_jar), str(stage / "module-descriptors.dat"),
                                 str(removed_ids), str(removed_edges)],
                                text=True, capture_output=True, timeout=90)
        if result.returncode:
            raise ValueError("Runtime-module repository validation failed: " + result.stdout + result.stderr)
        checked = json.loads(result.stdout)
        shutil.copyfile(filtered_jar, source_jar)
        shutil.copyfile(stage / "module-descriptors.dat", source_dat)
    return {**checked, "removedModules": sorted(excluded), "removedOptionalEdges": sorted(edges),
            "before": before, "after": {"dat": sha(source_dat.read_bytes()), "jar": sha(source_jar.read_bytes())}}


def apply(contents: Path, sdk_contents: Path | None = None) -> dict:
    """Transform only an owned assembled product; reference SDKs are immutable."""
    contents = Path(contents).resolve()
    if not any(contents.is_relative_to(ROOT / name) for name in ("build", ".tools")) or contents.is_relative_to(ROOT / ".tools/platform"):
        raise ValueError("Local product policy requires an owned build copy outside the SDK")
    policy_bytes = POLICY.read_bytes()
    policy = json.loads(policy_bytes)
    if policy["schema"] != 1:
        raise ValueError("Unknown local product policy")
    module_jar = contents / "modules/module-descriptors.jar"
    info_path = contents / ("Resources/product-info.json" if (contents / "Resources/product-info.json").is_file() else "product-info.json")
    cache = contents / "plugins/plugin-classpath.txt"
    for path in (module_jar, contents / "modules/module-descriptors.dat", cache, info_path):
        owned_file(contents, path)
    with zipfile.ZipFile(module_jar) as archive:
        names = {name[:-4] for name in archive.namelist() if name.endswith(".xml")}
    excluded = {name for name in names if name in policy["excludeModuleIds"] or any(name.startswith(prefix) for prefix in policy["excludeModulePrefixes"])}
    raw_cache = cache.read_bytes()
    core, records = cache_records(raw_cache)
    core, core_changes = xml_filter(core, excluded)
    kept, removed_plugins, changed_records = [], [], []
    for record in records:
        if record["id"] in policy["dropPluginIds"]:
            removed_plugins.append({"id": record["id"], "directory": record["directory"], "sha256": sha(record["raw"])})
            continue
        descriptor, changes = xml_filter(record["descriptor"], excluded)
        if changes:
            raw = record["head"] + struct.pack(">i", len(descriptor)) + descriptor + record["tail"]
            changed_records.append({"id": record["id"], "directory": record["directory"], "changes": changes})
        else:
            raw = record["raw"]
        kept.append(raw)
    filtered_cache = b"\x02\x01" + struct.pack(">i", len(core)) + core + struct.pack(">H", len(kept)) + b"".join(kept)
    check_core, check_records = cache_records(filtered_cache)
    if check_core != core or len(check_records) != len(kept):
        raise ValueError("Filtered plugin classpath roundtrip failed")
    jars = []
    tokens = [b"settingsSync", b"ultimatePromo", b"grazie", b".promotion", b"PycharmProSuggestionProvider", b"pluginsAdvertisement", b"TryUltimateActionHandler", b"ConsentConfigurable"]
    for path in sorted(contents.rglob("*.jar")):
        if path == module_jar:
            continue
        owned_file(contents, path)
        replacements, changes = {}, []
        with zipfile.ZipFile(path) as archive:
            for entry in archive.infolist():
                if not entry.filename.endswith(".xml") or entry.file_size > 4_000_000:
                    continue
                data = archive.read(entry)
                if not any(token in data for token in tokens):
                    continue
                # Registration descriptors and action sets only, not templates.
                try:
                    root = ET.fromstring(data)
                except ET.ParseError:
                    continue
                if root.tag not in {"idea-plugin", "actions"}:
                    continue
                filtered, selected = xml_filter(data, excluded)
                if selected:
                    replacements[entry.filename] = filtered
                    changes.append({"entry": entry.filename, "beforeSha256": sha(data), "afterSha256": sha(filtered), "removals": selected})
        if replacements:
            before = sha(path.read_bytes())
            rewrite_jar(path, replacements)
            jars.append({"path": path.relative_to(contents).as_posix(), "beforeSha256": before, "afterSha256": sha(path.read_bytes()), "changes": changes})
    module_report = _module_repository(contents, excluded, policy, sdk_contents)
    cache.write_bytes(filtered_cache)
    info = json.loads(info_path.read_text(encoding="utf-8"))
    dropped_ids = excluded | set(policy["dropPluginIds"])
    for key in ("bundledPlugins", "modules"):
        info[key] = [name for name in info.get(key, []) if name not in dropped_ids]
    info["layout"] = [entry for entry in info.get("layout", []) if entry["name"] not in dropped_ids]
    info_path.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    return {"policy": "product/local-policy.json", "policySha256": sha(policy_bytes),
            "coreChanges": core_changes, "changedPluginRecords": changed_records, "removedPlugins": removed_plugins,
            "pluginCache": {"beforeSha256": sha(raw_cache), "afterSha256": sha(filtered_cache), "beforeCount": len(records), "afterCount": len(kept)},
            "jars": jars, "moduleRepository": module_report,
            "implementationCodeChanged": False, "retainedGitAuthentication": True,
            "limitations": ["Native UI absence and credentials flows require runtime verification.", "Inactive upstream classes and shared libraries remain preserved; feature registrations are excluded."]}
