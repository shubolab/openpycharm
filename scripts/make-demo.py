#!/usr/bin/env python3
"""Assemble a GIF from the recorded native app states, without invented UI."""
import hashlib
import json
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parents[1]
directory = root / "docs/demo"
names = ["run.png", "tests.png", "debug.png", "step.png"]
frames = []
records = []
for name in names:
    path = directory / name
    frame = Image.open(path).convert("RGB")
    if frame.size != (2800, 1750):
        raise ValueError("Native capture dimensions changed; review and update the demo recipe")
    frame = frame.resize((1280, 800), Image.Resampling.LANCZOS)
    frames.append(frame)
    records.append({"file": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
output = directory / "openpycharm-native.gif"
frames[0].save(output, save_all=True, append_images=frames[1:], duration=[2800,3400,3800,2800],
               loop=0, optimize=True)
(directory / "capture.json").write_text(json.dumps({
    "productVersion": "0.1.0-dev.1", "upstreamVersion": "2026.1.4", "upstreamBuild": "PC-261.26222.68",
    "system": "macOS 27.2 arm64", "python": "3.14.0", "captureDate": "2026-11-13",
    "method": "Real native OpenPyCharm app screenshots assembled into an animated sequence",
    "states": ["Python Run exited 0", "Native unittest tree: 20 items passed / 9 methods",
               "Breakpoint, stack, locals and Decimal expression evaluation", "Step over to next line"],
    "captures": records, "gifSha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    "releaseStatus": "development candidate; refresh captures for the published release"
}, indent=2) + "\n")
print(output)
