# OpenPyCharm

[简体中文](README.zh-CN.md)

An independent native Python IDE built on the open-source PyCharm and IntelliJ
Platform. The reference is the locally installed PyCharm **2026.1.4**. The
workbench, editor and Python PSI come from the same upstream version; this
repository owns the product identity, distribution, integration changes and
verification.

**Development is in progress. Full 1:1 parity is not yet verified.**

The **0.1.0-dev.2 candidate** adds native HTTP requests and independent
Django, Flask and FastAPI project generators and Run/Debug configurations:

- Open `.http` files, run the current request or a batch, inspect responses in
  Services, save the original response bytes, and cancel running requests.
- Create a small framework project with the native interpreter/venv selector.
  Dependency installation is optional and off by default. Run and debug with the
  selected Python SDK, working directory and environment.
- Fix cold-start Markdown preview initialization while retaining normal rendering,
  proxy configuration and service authentication.

Framework templates and launch/debug support do not provide complete framework
semantics: template/ORM intelligence, framework navigation and broader framework
behavior remain pending. Notebook and database tools are **not included in dev.2**.
See the [acceptance matrix](docs/acceptance.md) and
[dev.2 release notes](docs/releases/v0.1.0-dev.2.md).

**dev.2 is not published yet.** The final macOS installation passed Python Run
and unittest, fresh FastAPI creation and Debug, HTTP requests, and restored README
preview. Its product tree stayed unchanged and strict signature verification
passed afterwards; the bounded session log has 0 errors and 20 retained warnings. Windows
desktop workflows remain unverified. Track the exact source and installer hashes
in the [dev.2 verification](docs/verification/2026-11-14-dev2-release.md).

The currently published native preview is
[v0.1.0-dev.1](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.1):

| System | Installer |
| --- | --- |
| macOS Apple silicon | [DMG](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.1/OpenPyCharm-0.1.0-dev.1-macos-arm64.dmg) |
| Windows x64 | [EXE](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.1/OpenPyCharm-0.1.0-dev.1-windows-x64-setup.exe) |

See [installation](docs/installation.md), [dev.1 checksums](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.1/SHA256SUMS.txt)
and [dev.1 verification](docs/verification/2026-11-14-preview-release.md).
For dev.1, macOS Run/unittest/Debug passed in the installed app. Windows
installation and native startup passed; Python desktop workflows remain unverified.
The Mac app is ad-hoc signed and not notarized; the Windows installer is unsigned.

![OpenPyCharm 0.1.0-dev.2 installed native workflows](docs/demo/v0.1.0-dev.2/openpycharm-native.gif)

Actual installed **0.1.0-dev.2**, **macOS 27.2 arm64**, Python **3.14.0**:
Run, unittest results, FastAPI breakpoint evaluation and HTTP batch/Unicode
response. This animation assembles real native app screenshots.
[Capture manifest](docs/demo/v0.1.0-dev.2/capture.json).
Each publishable release gets fresh installed-version captures and a manifest.

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

Run the Python example's tests from its own directory:

```sh
cd fixtures/hello-python
python3 main.py
python3 -m unittest discover -s tests -v
```

On Windows use `python` and `--target windows-x64`; the product directory is
`build/product/OpenPyCharm`. The installer builder obtains an authenticated Inno
Setup compiler when needed. See [installation](docs/installation.md).

The SDK is downloaded from the pinned [official open-source release](https://github.com/JetBrains/intellij-community/releases/tag/pycharm/2026.1.4),
verified by size and SHA-256, and reused only after a complete tree check.
Installed commercial IDEs and their user data are read-only references, never
product inputs. Local IDE use has no IDE account, billing, subscription, trial
or upgrade-promotion flow. Git, GitHub, private-repository and user-selected
development-service authentication remain available.

## Verify

Open [hello-python](fixtures/hello-python) for the Python editing, navigation,
refactoring, Run, unittest and Debug example. Its command-line tests are separate
from desktop acceptance. [Reference observations](docs/reference/installed-pycharm.md)
and [architecture](docs/architecture.md) record the evidence boundaries.

Source modifications are Apache-2.0. Upstream and third-party notices are retained.
OpenPyCharm is independently maintained and is not a JetBrains product.
