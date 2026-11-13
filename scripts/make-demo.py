#!/usr/bin/env python3
"""Build the README GIF from real captures and their reviewed metadata."""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
from PIL import Image

def make_demo(directory):
    manifest_path = directory / "capture.json"
    metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in ("productVersion", "upstreamVersion", "upstreamBuild", "system", "python", "captureDate"):
        if not isinstance(metadata.get(key), str) or not metadata[key].strip():
            raise ValueError(f"Record the actual capture {key} in {manifest_path} first")
    date.fromisoformat(metadata["captureDate"])
    names = ["run.png", "tests.png", "debug.png", "step.png"]
    frames, records, dimensions = [], [], None
    for name in names:
        path = directory / name
        frame = Image.open(path).convert("RGB")
        if dimensions is None:
            dimensions = frame.size
        if frame.size != dimensions:
            raise ValueError("Capture dimensions differ; record one consistent native window before assembling")
        width, height = dimensions
        frames.append(frame.resize((1280, round(1280 * height / width)), Image.Resampling.LANCZOS))
        records.append({"file": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    output = directory / "openpycharm-native.gif"
    frames[0].save(output, save_all=True, append_images=frames[1:],
                   duration=[2800, 3400, 3800, 2800], loop=0, optimize=True)
    metadata.update(captures=records, captureSize=list(dimensions),
                    method="Real native OpenPyCharm app screenshots assembled into an animated sequence",
                    gifSha256=hashlib.sha256(output.read_bytes()).hexdigest())
    manifest_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parents[1] / "docs/demo")
    args = parser.parse_args()
    print(make_demo(args.directory))
