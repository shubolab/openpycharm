#!/usr/bin/env python3
"""Prepare an explicit disposable HTTP project/profile, without launching an IDE."""
import argparse
import json
from pathlib import Path
import shutil
import sys

from build_http_plugin import ROOT, PLUGIN, sha
from platform_layout import detect_platform_layout


def prepare(app: Path, plugin: Path, output: Path) -> dict:
    app, plugin, output = app.resolve(), plugin.resolve(), output.resolve()
    layout = detect_platform_layout(app)
    if output.exists() or not any(output.is_relative_to((ROOT / name).resolve()) for name in (".state", "build")):
        raise ValueError("Choose a new owned acceptance directory below this worktree's .state or build")
    jar = plugin / "lib/openpycharm-http.jar"
    if not jar.is_file() or not (layout.contents / "openpycharm-build.json").is_file():
        raise ValueError("Build the HTTP plugin and select an independent OpenPyCharm app first")
    product = json.loads(layout.product_info.read_text(encoding="utf-8"))
    launch = product["launch"][0]
    if any(argument.startswith("-Dplugin.path=") for argument in launch.get("additionalJvmArguments", [])):
        raise ValueError("This app already fixes plugin.path in launcher metadata; use an integrated HTTP candidate instead")
    project, profile = output / "project", output / "profile"
    project.mkdir(parents=True)
    profile.mkdir()
    for name in ("demo.http", "stop.http", "server.py"):
        shutil.copyfile(PLUGIN / "examples" / name, project / name)
    properties = profile / "idea.properties"
    properties.write_text("\n".join(f"idea.{name}.path={(profile / name).as_posix()}" for name in ("config", "system", "plugins", "log")) +
                          "\nidea.initially.ask.config=never\nintellij.startup.wizard=false\n", encoding="utf-8")
    base = (layout.product_info.parent / launch["vmOptionsFilePath"]).resolve()
    options = output / "http.vmoptions"
    lines = [line for line in base.read_text(encoding="utf-8").splitlines() if not line.startswith("-Dplugin.path=")]
    options.write_text("\n".join(lines + ["-Dplugin.path=" + plugin.as_posix()]) + "\n", encoding="utf-8")
    executable = layout.contents / ("MacOS/pycharm" if layout.platform == "macos" else "bin/pycharm64.exe")
    result = {"schema": 1, "preparedOnly": True, "nativeApplicationLaunched": False,
              "projectTrustBypassed": False, "application": str(app), "pluginSha256": sha(jar),
              "project": str(project), "profile": str(profile),
              "serverCommand": [sys.executable, str(project / "server.py")],
              "nativeCommand": [str(executable), str(project)],
              "environment": {"OPENPYCHARM_PROPERTIES": str(properties), "OPENPYCHARM_VM_OPTIONS": str(options)},
              "checks": ["Normal Trust Project flow", "Open demo.http; native highlighting/toolbar/gutter", "Run current and Run All; inspect individual Services responses",
                         "Save binary response; verify bytes 00..0f", "Open stop.http and cancel its active streaming request", "Close project and confirm no owned HTTP exchange continues"]}
    (output / "acceptance.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--plugin", type=Path, default=ROOT / "build/http-client/plugin")
    parser.add_argument("--output", type=Path, default=ROOT / ".state/http-acceptance")
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.app, args.plugin, args.output), indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
