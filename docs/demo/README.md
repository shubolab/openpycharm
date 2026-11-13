# Native workflow demo

![OpenPyCharm native Run, unittest and Debug](openpycharm-native.gif)

Recorded **OpenPyCharm 0.1.0-dev.1**, based on **PC-261.26222.68 (2026.1.4)**,
on **macOS 27.2 arm64**, using **Python 3.14.0**, on 2026-11-13.

The GIF combines real native app captures: successful Run, unittest results
(20 items including subtests, 9 test methods), breakpoint/stack/locals/expression
evaluation, and Step Over. It is an animated sequence of captured states, not a
mock interface. PNG originals and hashes are retained alongside it.

This is a development candidate capture. Every publishable version must update
the README demo from that version's actual installed app and refresh the version,
system and capture manifest. Source changes that materially alter the demonstrated
workflow require new captures.

Rebuild the GIF from the reviewed native captures with `python3 scripts/make-demo.py`.
