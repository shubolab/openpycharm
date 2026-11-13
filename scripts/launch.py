#!/usr/bin/env python3
"""Launch our assembled native IDE with an optional isolated test profile."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
from product import ROOT

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--app", type=Path)
parser.add_argument("--profile", type=Path, help="Use a test profile instead of the normal OpenPyCharm configuration")
parser.add_argument("project", type=Path, nargs="?")
args = parser.parse_args()
macos = platform.system() == "Darwin"
app = (args.app or ROOT / "build/product" / ("OpenPyCharm.app" if macos else "OpenPyCharm")).resolve()
contents = app / "Contents" if macos else app
if not (contents / "openpycharm-build.json").is_file():
    raise SystemExit("Build OpenPyCharm first")
env = dict(os.environ)
if args.profile:
    profile = args.profile.resolve()
    profile.mkdir(parents=True, exist_ok=True)
    properties = profile / "idea.properties"
    properties.write_text("\n".join(f"idea.{name}.path={str(profile / name).replace(chr(92), '/')}"
                                    for name in ("config", "system", "plugins", "log")) +
                          "\nidea.initially.ask.config=never\nintellij.startup.wizard=false\n", encoding="utf-8")
    env["OPENPYCHARM_PROPERTIES"] = str(properties)
executable = contents / ("MacOS/pycharm" if macos else "bin/pycharm64.exe")
command = [str(executable)] + ([str(args.project.resolve())] if args.project else [])
process = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           start_new_session=macos)
print(json.dumps({"pid": process.pid, "application": str(app), "profile": str(args.profile) if args.profile else "OpenPyCharm default"}))
