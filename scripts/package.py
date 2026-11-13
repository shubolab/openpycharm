#!/usr/bin/env python3
"""Assemble OpenPyCharm from a verified OSS distribution."""
import argparse
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import stat
import subprocess
import tempfile

from product import IDENTITY, ROOT, brand_plist, brand_product_info, brand_resources, seal_python_helper_directories, sha, write_paths
from bootstrap import PIN_PATH, validate_cached
from provenance import source_inputs, verify_source_inputs, verify_product_plugins


def copy_plugin_payloads(source, destination, jar_name, build):
    """Copy only receipt-bound regular files, including replaceable JDBC/source JARs."""
    files = build.get("files", {"lib/" + jar_name: build["jarSha256"]})
    if not isinstance(files, dict) or not 1 <= len(files) <= 32 or files.get("lib/" + jar_name) != build["jarSha256"]:
        raise ValueError("Plugin payload receipt must include its primary JAR")
    source = Path(source).absolute()
    if not source.is_relative_to(ROOT):
        raise ValueError("Plugin payload source must stay in this checkout")
    for name, digest in files.items():
        if not isinstance(name, str):
            raise ValueError("Plugin payload path must be a string")
        relative = Path(name)
        if (not isinstance(name, str) or not name or relative.is_absolute() or relative.as_posix() != name
                or any(c in name for c in "\\:\0") or any(p in {".", ".."} for p in relative.parts)
                or relative.parts[0] not in {"lib", "legal"} or not isinstance(digest, str)
                or re.fullmatch(r"[a-f0-9]{64}", digest) is None):
            raise ValueError("Plugin payload paths/digests must be bounded relative lib/legal files")
        original = source / relative
        for parent in [original, *original.parents]:
            if parent == ROOT:
                break
            if parent.is_symlink():
                raise ValueError("Plugin payload source ancestors cannot be symlinks")
        if not original.is_file() or not stat.S_ISREG(original.stat().st_mode) or original.stat().st_size > 128 * 1024**2 or sha(original) != digest:
            raise ValueError("Plugin payload differs from its authenticated build")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        if sha(target) != digest:
            raise ValueError("Packaged plugin payload digest differs from its authenticated build")
    return files


def assemble(sdk, target, version, output):
    sdk = sdk.resolve()
    macos = target == "macos-arm64"
    receipt_path = sdk.parent / ".openpycharm-platform.json"
    if not receipt_path.is_file():
        raise ValueError("Run scripts/bootstrap.py first; the verified OSS SDK receipt is required")
    receipt = json.loads(receipt_path.read_text())
    authenticated_sdk = validate_cached(sdk.parent, json.loads(PIN_PATH.read_text()), target)
    if authenticated_sdk != sdk:
        raise ValueError("SDK does not match its authenticated receipt")
    source_contents = sdk / "Contents" if macos else sdk
    source_info = source_contents / ("Resources/product-info.json" if macos else "product-info.json")
    original_info = json.loads(source_info.read_text())
    if original_info.get("productCode") != "PC" or original_info["version"] != "2026.1.4":
        raise ValueError("Expected the pinned OSS PyCharm 2026.1.4 distribution")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("Invalid release version")
    output = output.resolve()
    if not output.is_relative_to((ROOT / "build").resolve()) or output.exists():
        raise ValueError("Choose a new output below this repository's build directory")
    if shutil.disk_usage(ROOT).free < 24 * 1024**3:
        raise ValueError("The build needs 20 GiB reserve plus assembly space")
    inputs = source_inputs()
    from build_http_plugin import build as build_http_plugin
    http = build_http_plugin(sdk, ROOT / f"build/http-client-{target}", version, [ROOT / ".tools/kotlin"])
    from build_framework_plugin import build_plugin as build_framework_plugin
    framework_directory, frameworks = build_framework_plugin(sdk, version=version)
    from build_database_plugin import build_plugin as build_database_plugin
    database_directory, database = build_database_plugin(sdk, version=version)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="assemble-", dir=output.parent) as staging_name:
        staging = Path(staging_name) / output.name
        if macos:
            subprocess.run(["ditto", str(sdk), str(staging)], check=True)
            subprocess.run(["codesign", "--remove-signature", str(staging)], check=True)
        else:
            shutil.copytree(sdk, staging, symlinks=True)
        contents = staging / "Contents" if macos else staging
        metadata = contents / ("Resources/product-info.json" if macos else "product-info.json")
        metadata.write_text(json.dumps(brand_product_info(original_info, version), indent=2) + "\n")
        paths = write_paths(contents, macos)
        from repairs import apply as apply_repairs
        repairs = apply_repairs(contents, sdk)
        branding = brand_resources(contents)
        from local_product import apply
        local_policy = apply(contents, source_contents)
        plugins = []
        for plugin_id, name, directory_name, source_directory, jar_name, build in (
            ("dev.openpycharm.http", "OpenPyCharm HTTP Client", "openpycharm-http", Path(http["pluginDirectory"]), "openpycharm-http.jar", http),
            ("dev.openpycharm.frameworks", "OpenPyCharm Python Frameworks", "openpycharm-frameworks", framework_directory, "frameworks.jar", frameworks),
            ("dev.openpycharm.database", "OpenPyCharm Database", "openpycharm-database", database_directory, "database.jar", database),
        ):
            directory = contents / "third-party-plugins" / directory_name
            jar = directory / "lib" / jar_name
            files = copy_plugin_payloads(source_directory, directory, jar_name, build)
            plugins.append({"id": plugin_id, "name": name, "version": version,
                            "path": directory.relative_to(contents).as_posix(), "jar": jar.relative_to(contents).as_posix(),
                            "jarSha256": build["jarSha256"], "files": files, "build": build})
        if macos:
            from icons import mac_icon
            mac_icon(contents)
            info_path = contents / "Info.plist"
            plist = brand_plist(plistlib.loads(info_path.read_bytes()), version)
            plist["CFBundleIconFile"] = "openpycharm.icns"
            for item in plist.get("CFBundleDocumentTypes", []):
                item["CFBundleTypeIconFile"] = "openpycharm.icns"
            info_path.write_bytes(plistlib.dumps(plist))
            launcher = contents / "bin/openpycharm"
            launcher.write_text('#!/bin/sh\nset -eu\ncontents="$(cd "$(dirname "$0")/.." && pwd)"\nexec "$contents/MacOS/pycharm" "$@"\n')
            launcher.chmod(0o755)
        else:
            (contents / "bin/openpycharm.bat").write_bytes(b'@echo off\r\n"%~dp0pycharm64.exe" %*\r\n')
        report = {"schema": 1, "name": IDENTITY["name"], "version": version, "target": target,
                  "upstreamBuild": original_info["buildNumber"], "upstreamProduct": "PC",
                  "platformReceipt": receipt, "branding": branding, "paths": paths,
                  "localProduct": local_policy, "platformRepairs": repairs,
                  "plugins": plugins,
                  "limitations": ["Full 1:1 acceptance remains open"]}
        import PIL
        report["buildDependencies"] = {"Pillow": PIL.__version__}
        report["sourceInputs"] = inputs
        try:
            report["sourceCommit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        except subprocess.CalledProcessError:
            report["sourceCommit"] = None
        shutil.copyfile(ROOT / "NOTICE", contents / "license/OPENPYCHARM-NOTICE.txt")
        (contents / "openpycharm-build.json").write_text(json.dumps(report, indent=2) + "\n")
        if macos:
            report["pythonHelperResources"] = seal_python_helper_directories(contents)
            (contents / "openpycharm-build.json").write_text(json.dumps(report, indent=2) + "\n")
            subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(staging)], check=True)
            subprocess.run(["codesign", "--verify", "--deep", "--strict", str(staging)], check=True)
        verify_product_plugins(report, contents)
        verify_source_inputs(report)
        staging.rename(output)
    print(json.dumps({"output": str(output), "version": version, "target": target}))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["macos-arm64", "windows-x64"], default="macos-arm64")
    parser.add_argument("--sdk", type=Path)
    parser.add_argument("--version", default=IDENTITY["version"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    macos = args.target == "macos-arm64"
    sdk = args.sdk or ROOT / f".tools/platform/pycharm-2026.1.4-{args.target}" / ("PyCharm.app" if macos else "pycharm")
    output = args.output or ROOT / "build/product" / ("OpenPyCharm.app" if macos else "OpenPyCharm")
    assemble(sdk, args.target, args.version, output)


if __name__ == "__main__":
    main()
