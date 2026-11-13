# OpenPyCharm

[简体中文](README.zh-CN.md)

An independent native Python IDE built on the open-source PyCharm and IntelliJ
Platform. The reference is the locally installed PyCharm **2026.1.4**. The
workbench, editor and Python PSI come from the same upstream version; this
repository owns the product identity, distribution, integration changes and
verification.

**Development is in progress. Full 1:1 parity is not yet verified.** See the
[acceptance matrix](docs/acceptance.md) for pending native workflows and framework,
database, notebook, frontend and remote-development work.

First native preview: [v0.1.0-dev.1](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.1).

| System | Installer |
| --- | --- |
| macOS Apple silicon | [DMG](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.1/OpenPyCharm-0.1.0-dev.1-macos-arm64.dmg) |
| Windows x64 | [EXE](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.1/OpenPyCharm-0.1.0-dev.1-windows-x64-setup.exe) |

See [installation](docs/installation.md), [checksums](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.1/SHA256SUMS.txt)
and [release verification](docs/verification/2026-11-14-preview-release.md).
macOS Run/unittest/Debug passed in the installed app. Windows installation and
native startup passed; Python desktop workflows remain unverified there.
The Mac app is ad-hoc signed and not notarized; the Windows installer is unsigned.

![OpenPyCharm native workflow](docs/demo/openpycharm-native.gif)

Actual installed-app capture: **0.1.0-dev.1**, **macOS 27.2 arm64**,
Python 3.14.0. Run, unittest results, breakpoint evaluation and Step Over.
[Capture details](docs/demo/README.md). The demo is refreshed for each publishable version.

## Build

Python 3.10+ is required to assemble the product. The application includes its
Java runtime; select a local Python interpreter for your Python projects.
Keep at least 20 GiB free in addition to build space.

```sh
python3 -m pip install -r requirements-build.txt
python3 -m unittest discover -s tests -v
python3 scripts/provision_http_compiler.py
python3 scripts/build.py --target macos-arm64
python3 scripts/launch.py --profile .state/development fixtures/hello-python
python3 scripts/installers.py --target macos-arm64 --version 0.1.0-dev.2 --product build/product/OpenPyCharm.app
```

On Windows use `python` and `--target windows-x64`; the product directory is
`build/product/OpenPyCharm`. The installer builder obtains an authenticated Inno
Setup compiler when needed. See [installation](docs/installation.md).

The SDK is downloaded from the pinned [official open-source release](https://github.com/JetBrains/intellij-community/releases/tag/pycharm/2026.1.4),
verified by size and SHA-256, and reused only after a complete tree check.
Installed commercial IDEs and their user data are read-only references, never
product inputs. Git and development-service authentication remain available.

## Verify

Open [hello-python](fixtures/hello-python) for the Python editing, navigation,
refactoring, Run, unittest and Debug example. Its command-line tests are separate
from desktop acceptance. [Reference observations](docs/reference/installed-pycharm.md)
and [architecture](docs/architecture.md) record the evidence boundaries.

Source modifications are Apache-2.0. Upstream and third-party notices are retained.
OpenPyCharm is independently maintained and is not a JetBrains product.
