#!/usr/bin/env python3
"""Build independent native Database plugin offline from the authenticated OSS SDK."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from bootstrap import check_space, sha256
from build_framework_plugin import sdk_layout, execution_layout, compile_java, run_java, classpath
from platform_layout import cache_lock

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "plugins/database"
PLUGIN_ID = "dev.openpycharm.database"


def inputs() -> dict[str, str]:
    files = []
    for directory in (ROOT / "plugins", SOURCE):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("Database sources must be owned regular directories")
    for parent, directories, names in os.walk(SOURCE, followlinks=False):
        for name in sorted(directories + names):
            path = Path(parent) / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise ValueError("Database source symlinks and special files are not supported")
            if stat.S_ISREG(mode):
                files.append(path)
    files += [ROOT / "LICENSE", Path(__file__), ROOT / "scripts/build_framework_plugin.py", ROOT / "scripts/bootstrap.py", ROOT / "scripts/platform_layout.py"]
    return {path.relative_to(ROOT).as_posix(): sha256(path) for path in sorted(files)}


def driver_artifacts(caches: list[Path] | None = None) -> list[tuple[dict, Path]]:
    pin = json.loads((SOURCE / "drivers.lock.json").read_text())
    result = []
    for item in pin["artifacts"]:
        # Only lock-file names, exact SHA-256 and size; no implicit downloads.
        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.jar", item["name"]) or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]):
            raise ValueError("Invalid JDBC artifact pin")
        candidates = [(root / item["name"]) for root in (caches or [ROOT / ".tools/jdbc"])]
        candidates = [p for p in candidates if p.is_file() and not p.is_symlink() and p.stat().st_size == item["size"] and sha256(p) == item["sha256"]]
        if not candidates:
            raise ValueError(f"Missing authenticated cached JDBC artifact {item['name']}; run provision_database_drivers.py explicitly. The builder does not download dependencies.")
        result.append((item, candidates[0].resolve()))
    return result


def descriptor(data: bytes, version: str) -> bytes:
    data = data.replace(b"@VERSION@", version.encode())
    node = ET.fromstring(data)
    if node.tag != "idea-plugin" or node.findtext("id") != PLUGIN_ID or node.findtext("version") != version:
        raise ValueError("Database plugin identity/version mismatch")
    return data


def verify(layout, runtime, jar: Path, directory: Path) -> dict:
    args = ["--add-opens=java.base/sun.nio.ch=ALL-UNNAMED", "--add-opens=java.base/jdk.internal.ref=ALL-UNNAMED", "--class-path",
            os.pathsep.join(str(layout.lib / n) for n in ("platform-loader.jar", "annotations.jar")),
            str(SOURCE / "build-support/VerifyDatabaseArchive.java"), str(jar)]
    report = json.loads(run_java(runtime, args, directory, timeout=60).stdout)
    if report.get("status") != "pass" or report.get("closed") is not True or report.get("sha256") != sha256(jar):
        raise ValueError("Database plugin archive verification failed")
    return report


def build_plugin(sdk: Path, version: str | None = None, caches: list[Path] | None = None, host_sdk: Path | None = None) -> tuple[Path, dict]:
    version = version if version is not None else json.loads((ROOT / "product/product.json").read_text())["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("Use a concrete database plugin release version")
    layout = sdk_layout(sdk)
    runtime = execution_layout(layout, host_sdk)
    artifacts = driver_artifacts(caches)
    identity = {"pluginId": PLUGIN_ID, "version": version, "sources": inputs(),
                "sdkReceiptSha256": sha256(layout.sdk_root.parent / ".openpycharm-platform.json"),
                "executionSdkReceiptSha256": sha256(runtime.sdk_root.parent / ".openpycharm-platform.json"),
                "drivers": [item for item, path in artifacts]}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    work = ROOT / ".tools/database-plugin" / key
    check_space(work, 64 * 1024**2)
    work.mkdir(parents=True, exist_ok=True)
    plugin = work / "plugin"
    jar = plugin / "lib/database.jar"
    receipt = work / "build.json"
    expected = {"lib/database.jar": None}
    for item, path in artifacts:
        expected[("legal/" if item["role"] == "source" else "lib/") + item["name"]] = item["sha256"]
    with cache_lock(work / "build.lock"):
        if jar.is_file() and not jar.is_symlink() and receipt.is_file() and not receipt.is_symlink():
            saved = json.loads(receipt.read_text())
            expected["lib/database.jar"] = sha256(jar)
            if saved.get("identity") == identity and saved.get("jarSha256") == expected["lib/database.jar"] and saved.get("files") == expected and all((plugin / name).is_file() and not (plugin / name).is_symlink() and sha256(plugin / name) == digest for name, digest in expected.items()):
                return plugin, saved
        with tempfile.TemporaryDirectory(prefix="compile-", dir=work) as temp:
            temporary = Path(temp)
            classes = temporary / "classes"
            compilation = compile_java(layout, sorted((SOURCE / "src").rglob("*.java")), classes, temporary / "javac.args", runtime=runtime)
            payloads = {p.relative_to(classes).as_posix(): p.read_bytes() for p in classes.rglob("*.class")}
            for p in (SOURCE / "resources").rglob("*"):
                if p.is_file():
                    name = p.relative_to(SOURCE / "resources").as_posix()
                    payloads[name] = descriptor(p.read_bytes(), version) if name == "META-INF/plugin.xml" else p.read_bytes()
            for name, path in [("META-INF/LICENSE", ROOT / "LICENSE"), ("META-INF/NOTICE", SOURCE / "NOTICE"), ("META-INF/jdbc-drivers.lock.json", SOURCE / "drivers.lock.json")]:
                payloads[name] = path.read_bytes()
            for p in (SOURCE / "legal").rglob("*"):
                if p.is_file():
                    payloads["META-INF/legal/" + p.relative_to(SOURCE / "legal").as_posix()] = p.read_bytes()
            candidate = temporary / "database.jar"
            with zipfile.ZipFile(candidate, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, data in sorted(payloads.items()):
                    entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(entry, data)
            verified = verify(layout, runtime, candidate, temporary)
            if inputs() != identity["sources"]:
                raise ValueError("Database sources changed during compilation; build again")
            jar.parent.mkdir(parents=True, exist_ok=True)
            candidate.replace(jar)
            files = {"lib/database.jar": sha256(jar)}
            for item, path in artifacts:
                name = ("legal/" if item["role"] == "source" else "lib/") + item["name"]
                destination = plugin / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
                if sha256(destination) != item["sha256"]:
                    raise ValueError("JDBC artifact changed during packaging")
                files[name] = item["sha256"]
            saved = {"schema": 1, "identity": identity, "pluginDirectory": str(plugin), "jarSha256": sha256(jar), "files": files,
                     "compilation": compilation, "archiveVerification": verified, "targetPlatform": layout.platform,
                     "executionPlatform": runtime.platform, "nativeTargetRuntime": layout.platform == runtime.platform,
                     "limitations": ["Desktop acceptance is separate; PostgreSQL/MySQL server and Windows runtime checks are unverified"]}
            receipt.write_text(json.dumps(saved, indent=2) + "\n")
    return plugin, saved


def integration_tests(sdk: Path, plugin: Path, host_sdk: Path | None = None) -> dict:
    layout = sdk_layout(sdk)
    runtime = execution_layout(layout, host_sdk)
    work = ROOT / ".tools/database-tests"
    check_space(work, 8 * 1024**2)
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="owned-sqlite-", dir=work) as temp:
        directory = Path(temp)
        jars = sorted((plugin / "lib").glob("*.jar"))
        compile_java(layout, [ROOT / "tests/database/DatabaseIntegrationProbe.java", ROOT / "tests/database/DatabaseCompletionProbe.java"], directory / "classes", directory / "javac.args", jars, runtime)
        cp = os.pathsep.join(map(str, [directory / "classes", *jars, *classpath(layout)]))
        result = json.loads(run_java(runtime, ["-Djava.awt.headless=true", "-classpath", cp, "dev.openpycharm.database.DatabaseIntegrationProbe", str(directory)], directory, timeout=45).stdout)
        if result.get("status") != "pass" or result.get("connectionsClosed") is not True:
            raise ValueError("SQLite integration checks did not pass")
        completion = json.loads(run_java(runtime, ["-Djava.awt.headless=true", "-classpath", cp, "dev.openpycharm.database.DatabaseCompletionProbe", str(directory)], directory, timeout=45).stdout)
        if completion.get("status") != "pass" or completion.get("realSqliteMetadata") is not True:
            raise ValueError("SQLite metadata/completion checks did not pass")
        completion["testSourceSha256"] = sha256(ROOT / "tests/database/DatabaseCompletionProbe.java")
        result["completionTests"] = completion
        result.update(jarSha256=sha256(plugin / "lib/database.jar"), testSourceSha256=sha256(ROOT / "tests/database/DatabaseIntegrationProbe.java"), targetPlatform=layout.platform, executionPlatform=runtime.platform, nativeTargetRuntime=layout.platform == runtime.platform)
        (work / "latest.json").write_text(json.dumps(result, indent=2) + "\n")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--host-sdk", type=Path)
    parser.add_argument("--version")
    parser.add_argument("--driver-cache", type=Path, action="append")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    try:
        plugin, result = build_plugin(args.sdk, args.version, args.driver_cache, args.host_sdk)
        if args.test:
            result = {**result, "integrationTests": integration_tests(args.sdk, plugin, args.host_sdk)}
        print(json.dumps(result, indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
