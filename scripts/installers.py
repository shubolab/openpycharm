#!/usr/bin/env python3
"""Build and verify native installers from an assembled OpenPyCharm product.

Verification checks installer contents, signatures where applicable, and byte
identity with the product. It does not claim Python desktop workflows passed.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import tempfile

from bootstrap import ROOT, check_space, sha256, tree_digest
from provenance import verify_source_inputs, verify_product_plugins

# Official release and its published digest, also used by opengoland.
INNO = {
    "version": "6.7.3",
    "url": "https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe",
    "size": 10592232,
    "sha256": "9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732",
    "publisher": "Pyrsys B.V.",
}


def run(command: list, log: Path, *, env: dict | None = None, timeout: int = 1800) -> None:
    with log.open("wb") as stream:
        subprocess.run([str(item) for item in command], check=True, stdin=subprocess.DEVNULL,
                       stdout=stream, stderr=subprocess.STDOUT, env=env, timeout=timeout)


def validate_product(product: Path, target: str, version: str) -> tuple[Path, dict]:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("Use a concrete release version")
    if product.is_symlink() or not product.is_dir():
        raise ValueError("Product must be a regular assembled directory")
    product = product.resolve()
    if not product.is_relative_to((ROOT / "build").resolve()):
        raise ValueError("Only products assembled under this repository's build directory may be packaged")
    contents = product / "Contents" if target == "macos-arm64" else product
    manifest_path = contents / "openpycharm-build.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verify_source_inputs(manifest)
    verify_product_plugins(manifest, contents)
    if any(manifest.get(key) != value for key, value in {
        "schema": 1, "name": "OpenPyCharm", "version": version, "target": target,
        "upstreamProduct": "PC",
    }.items()):
        raise ValueError("Product manifest does not match this installer target and version")
    info_path = contents / ("Resources/product-info.json" if target == "macos-arm64" else "product-info.json")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    if info.get("name") != "OpenPyCharm" or info.get("openpycharmVersion") != version:
        raise ValueError("Product metadata does not match OpenPyCharm")
    launcher = contents / ("MacOS/pycharm" if target == "macos-arm64" else "bin/pycharm64.exe")
    if not launcher.is_file():
        raise ValueError("The native product launcher is missing")
    if target == "windows-x64" and not (contents / "bin/openpycharm.bat").is_file():
        raise ValueError("The OpenPyCharm command-line entry point is missing")
    return product, manifest


def detach_created_image(image: Path, proof: Path) -> None:
    """Detach only a primary device owned by this newly created image."""
    result = subprocess.run(["hdiutil", "info", "-plist"], check=True, capture_output=True)
    (proof / "dmg-after-create.plist").write_bytes(result.stdout)
    records = [item for item in plistlib.loads(result.stdout).get("images", [])
               if item.get("image-path") and Path(item["image-path"]).resolve() == image.resolve()]
    if not records:
        return
    if len(records) != 1:
        raise ValueError("Ambiguous disk image attachment ownership")
    devices = {item["dev-entry"] for item in records[0].get("system-entities", [])
               if re.fullmatch(r"/dev/disk[0-9]+", item.get("dev-entry", ""))}
    if len(devices) != 1:
        raise ValueError("Cannot determine this image's primary device")
    run(["hdiutil", "detach", devices.pop()], proof / "dmg-after-create-detach.log")


def mac_installer(product: Path, image: Path, proof: Path, expected_tree: str) -> dict:
    if platform.system() != "Darwin" or platform.machine().lower() != "arm64":
        raise ValueError("The macOS arm64 installer must be built on Apple silicon macOS")
    if product.name != "OpenPyCharm.app":
        raise ValueError("The macOS product must be named OpenPyCharm.app")
    run(["codesign", "--verify", "--deep", "--strict", product], proof / "product-signature.log")
    with tempfile.TemporaryDirectory(prefix="dmg-stage-", dir=ROOT / "build") as name:
        stage = Path(name)
        run(["ditto", product, stage / product.name], proof / "dmg-stage-copy.log")
        (stage / "Applications").symlink_to("/Applications", target_is_directory=True)
        (stage / "Install.txt").write_text(
            "Drag OpenPyCharm.app to Applications and open it.\n"
            "Choose an installed Python interpreter or create a virtual environment.\n"
            "This preview is ad-hoc signed and is not notarized.\n"
            "Source and notices: https://github.com/shubolab/openpycharm\n", encoding="utf-8")
        run(["hdiutil", "create", "-volname", "OpenPyCharm", "-srcfolder", stage,
             "-format", "UDZO", "-imagekey", "zlib-level=9", image], proof / "dmg-create.log")
        detach_created_image(image, proof)
    run(["hdiutil", "verify", image], proof / "dmg-verify.log")
    with tempfile.TemporaryDirectory(prefix="dmg-mount-", dir=ROOT / "build") as name:
        mount = Path(name)
        result = subprocess.run(["hdiutil", "attach", "-readonly", "-nobrowse", "-noautoopen",
                                 "-mountpoint", str(mount), "-plist", str(image)], check=True, capture_output=True)
        (proof / "dmg-mount.plist").write_bytes(result.stdout)
        try:
            mounted = mount / product.name
            if not (mount / "Applications").is_symlink() or os.readlink(mount / "Applications") != "/Applications":
                raise ValueError("Mounted DMG lacks the drag-to-Applications target")
            if tree_digest(mounted) != expected_tree:
                raise ValueError("Mounted product differs from the assembled product")
            run(["codesign", "--verify", "--deep", "--strict", mounted], proof / "mounted-signature.log")
            with tempfile.TemporaryDirectory(prefix="installed-macos-", dir=ROOT / "build") as installed_name:
                installed = Path(installed_name) / product.name
                run(["ditto", mounted, installed], proof / "installer-copy.log")
                if tree_digest(installed) != expected_tree:
                    raise ValueError("Product copied from DMG differs from the assembled product")
                run(["codesign", "--verify", "--deep", "--strict", installed], proof / "installed-signature.log")
        finally:
            run(["hdiutil", "detach", mount], proof / "dmg-detach.log")
    return {"checks": ["hdiutil-verify", "mounted-product-tree", "Applications-symlink",
                       "copied-product-tree", "ad-hoc-signature"],
            "limitations": ["Not notarized", "Installer checks do not establish native Python Run/Test/Debug acceptance"]}


def inno_compiler(proof: Path) -> Path:
    download = ROOT / ".tools/downloads" / f"innosetup-{INNO['version']}.exe"
    download.parent.mkdir(parents=True, exist_ok=True)
    if not download.is_file() or download.stat().st_size != INNO["size"] or sha256(download) != INNO["sha256"]:
        if download.exists():
            raise ValueError("Cached Inno Setup download differs from its pin; move it aside before retrying")
        temporary = download.with_suffix(".exe.download")
        run(["curl.exe", "--fail", "--location", "--retry", "3", "--connect-timeout", "20",
             "--max-time", "600", "--output", temporary, INNO["url"]], proof / "inno-download.log")
        if temporary.stat().st_size != INNO["size"] or sha256(temporary) != INNO["sha256"]:
            raise ValueError("Official Inno Setup download failed size/SHA-256 authentication")
        temporary.replace(download)
    env = os.environ.copy()
    env["OPENPYCHARM_INNO_ASSET"] = str(download)
    run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         "$s = Get-AuthenticodeSignature -LiteralPath $env:OPENPYCHARM_INNO_ASSET; "
         "if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Pyrsys B\\.V\\.') "
         "{ throw 'Official Inno Setup publisher signature is invalid' }; $s | Format-List"],
        proof / "inno-authenticode.log", env=env)
    tool_root = ROOT / ".tools" / f"inno-setup-{INNO['version']}"
    receipt_path = tool_root.parent / f"inno-setup-{INNO['version']}.json"
    compiler = tool_root / "ISCC.exe"
    if tool_root.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("installerSha256") != INNO["sha256"] or receipt.get("treeSha256") != tree_digest(tool_root):
            raise ValueError("Cached Inno Setup compiler files differ from their receipt")
    else:
        run([download, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/CURRENTUSER",
             "/NOICONS", f"/DIR={tool_root}"], proof / "inno-setup.log")
        if not compiler.is_file():
            raise ValueError("The authenticated Inno Setup installation produced no compiler")
        receipt_path.write_text(json.dumps({"installerSha256": INNO["sha256"],
                                           "treeSha256": tree_digest(tool_root)}, indent=2) + "\n", encoding="utf-8")
    return compiler


def windows_installer(product: Path, image: Path, proof: Path, version: str, verify_install: bool) -> dict:
    if platform.system() != "Windows" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise ValueError("The Windows x64 installer must be built on Windows x64")
    compiler = inno_compiler(proof)
    run([compiler, f"/DAppSourceDir={product}", f"/DReleaseVersion={version}",
         f"/DReleaseOutputDir={image.parent}", ROOT / "product/windows/openpycharm.iss"], proof / "inno-compile.log")
    if not image.is_file():
        raise ValueError("Inno Setup did not create a Windows executable installer")
    with image.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("Inno Setup output has no Windows executable header")
    checks = ["pinned-Inno-Setup", "official-tool-Authenticode", "executable-installer"]
    startup = None
    if verify_install:
        # Intended for a fresh CI VM: installation registers this product for the
        # current Windows user. Never silently run it on an existing user install.
        with tempfile.TemporaryDirectory(prefix="Windows install verification ", dir=ROOT / "build") as name:
            installed = Path(name) / "OpenPyCharm"
            run([image, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/TASKS=",
                 f"/DIR={installed}", f"/LOG={proof / 'windows-install.log'}"], proof / "windows-install-process.log")
            try:
                for source in product.rglob("*"):
                    if source.is_file() and sha256(source) != sha256(installed / source.relative_to(product)):
                        raise ValueError("Installed product file differs: " + str(source.relative_to(product)))
                checks.append("silent-install-file-identity")
                from runtime_smoke import run_smoke
                startup_profile = proof / "installed-startup"
                observed = run_smoke(installed, startup_profile)
                startup = {"status": observed["status"], "receipt": "installed-startup/startup.json",
                           "productManifestSha256": observed["productManifestSha256"],
                           "projectTrustBypassed": observed["projectTrustBypassed"]}
                checks.append("installed-native-startup")
            finally:
                uninstaller = installed / "unins000.exe"
                if uninstaller.is_file():
                    run([uninstaller, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], proof / "windows-uninstall.log")
                # The owned startup process has stopped. Keep logs/config and
                # its receipt, rather than uploading disposable index caches.
                system_cache = proof / "installed-startup/system"
                if system_cache.is_dir() and not system_cache.is_symlink():
                    shutil.rmtree(system_cache)
    return {"tool": {**INNO, "compilerSha256": sha256(compiler)}, "checks": checks,
            "installedStartup": startup,
            "limitations": ["Installer is not code signed", "Windows native Python Run/Test/Debug and UI acceptance remain open"]}


def package(target: str, version: str, product: Path, output: Path, verify_install: bool = False) -> Path:
    product, manifest = validate_product(product, target, version)
    output = output.resolve()
    if not output.is_relative_to((ROOT / "build").resolve()):
        raise ValueError("Installer output must stay under this repository's build directory")
    check_space(output, 6 * 1024**3)
    output.mkdir(parents=True, exist_ok=True)
    extension = "macos-arm64.dmg" if target == "macos-arm64" else "windows-x64-setup.exe"
    image = output / f"OpenPyCharm-{version}-{extension}"
    proof = output / "provenance" / f"{version}-{target}"
    if image.exists() or proof.exists():
        raise ValueError("This installer or its evidence already exists; choose a new output directory")
    proof.mkdir(parents=True)
    expected_tree = tree_digest(product)
    (proof / "product-build.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    result = (mac_installer(product, image, proof, expected_tree) if target == "macos-arm64"
              else windows_installer(product, image, proof, version, verify_install))
    if tree_digest(product) != expected_tree:
        raise ValueError("Product changed during installer creation")
    verify_source_inputs(manifest)
    digest = sha256(image)
    receipt = {"schema": 1, "target": target, "version": version, "installer": image.name,
               "sha256": digest, "size": image.stat().st_size, "productTreeSha256": expected_tree, **result}
    (proof / "installer.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    (output / f"{image.name}.sha256").write_text(f"{digest}  {image.name}\n", encoding="utf-8")
    print(json.dumps({"installer": str(image), "sha256": digest, "evidence": str(proof)}))
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("macos-arm64", "windows-x64"), required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--product", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "build/installers")
    parser.add_argument("--verify-install", action="store_true", help="Windows only: silent install/uninstall on a fresh CI VM")
    args = parser.parse_args()
    try:
        package(args.target, args.version, args.product, args.output, args.verify_install)
    except (ValueError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"Installer build failed: {error}\n")


if __name__ == "__main__":
    main()
