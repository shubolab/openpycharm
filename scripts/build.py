#!/usr/bin/env python3
"""Bootstrap the pinned OSS platform and assemble the independent IDE."""
import argparse
from pathlib import Path
import platform
from bootstrap import bootstrap, ROOT
from package import assemble
from product import IDENTITY

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--target", choices=["macos-arm64", "windows-x64"],
                    default="windows-x64" if platform.system() == "Windows" else "macos-arm64")
parser.add_argument("--version", default=IDENTITY["version"])
parser.add_argument("--output", type=Path)
args = parser.parse_args()
sdk = bootstrap(args.target, ROOT / ".tools")
output = args.output or ROOT / "build/product" / ("OpenPyCharm.app" if args.target == "macos-arm64" else "OpenPyCharm")
assemble(sdk, args.target, args.version, output)
