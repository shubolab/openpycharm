# OpenPyCharm

[简体中文](README.zh-CN.md)

An independent native Python IDE built on the open-source PyCharm and IntelliJ
Platform. The reference is the locally installed PyCharm **2026.1.4**. The
workbench, editor and Python PSI come from the same upstream version; this
repository owns the product identity, distribution, integration changes and
verification.

**Development is in progress. Full 1:1 parity is not yet verified.**

The **0.1.0-dev.4 candidate** adds native JavaScript and TypeScript language
services to the existing Python, Notebook, Database, HTTP and framework tools:

- Open a trusted local project and edit JavaScript or TypeScript with native
  completion, diagnostics and definition navigation. The service is enabled by
  default; **Settings → Languages & Frameworks → JavaScript and TypeScript**
  provides a project-level opt-out.
- Node.js **24.22.3**, TypeScript **6.0.3** and typescript-language-server
  **6.1.0** are bundled and authenticated before startup. Opening an editor does
  not download a runtime or install dependencies. Analysis state stays in the
  isolated OpenPyCharm system directory.
- Retain native `.ipynb` cells and local-kernel execution, SQL profiles/console
  and cached metadata completion, `.http` requests/Services responses, and
  Django/Flask/FastAPI generators and Run/Debug configurations.

The local installed dev.4 DMG candidate passed Python editing, Run, unittest
(9 methods/20 items), breakpoint/step/evaluate/resume, native completion and
cross-file Rename/Undo. JavaScript/TypeScript checks covered member completion,
a type diagnostic, definition navigation and unsaved text containing Chinese
and emoji. Closing the project removed its three owned Node processes. The
installed app tree stayed unchanged and strict signature verification passed.

[CI 43608150941](https://github.com/shubolab/openpycharm/actions/runs/43608150941)
is building source `63921a4`. Its frontend JVM/full-runtime and startup gates passed on
both platforms. Windows completed the installer checks; macOS is finishing the
DMG gate. The full CI result, final artifact receipt and public dev.4 release
have **not yet been confirmed**. See the [dev.4 candidate notes](docs/releases/v0.1.0-dev.4.md).

HTML/CSS, dedicated JavaScript/TypeScript syntax PSI and refactorings, frontend
framework intelligence and full PyCharm parity remain incomplete. Framework
template/ORM support, network database acceptance, Windows physical desktop
workflows and cleanup after an unexpected process-owner crash remain open.
Notebook remote kernels, widgets and debugging and editable/exportable database
results are not implemented. See [installation](docs/installation.md) and the
[acceptance matrix](docs/acceptance.md).

## Published preview

The current published installers are [v0.1.0-dev.3](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.3),
from source `9a243e6` and [CI 43565932969](https://github.com/shubolab/openpycharm/actions/runs/43565932969).

| System | Installer |
| --- | --- |
| macOS Apple silicon | [DMG](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.3/OpenPyCharm-0.1.0-dev.3-macos-arm64.dmg) |
| Windows x64 | [EXE](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.3/OpenPyCharm-0.1.0-dev.3-windows-x64-setup.exe) |

See [installation](docs/installation.md), [checksums](https://github.com/shubolab/openpycharm/releases/download/v0.1.0-dev.3/SHA256SUMS.txt)
and [dev.3 verification](docs/verification/2026-11-14-dev3-release.md). The Mac app
is ad-hoc signed and not notarized; the Windows installer is unsigned.
[Previous preview: dev.2](https://github.com/shubolab/openpycharm/releases/tag/v0.1.0-dev.2).

![OpenPyCharm 0.1.0-dev.4 installed native workflows](docs/demo/v0.1.0-dev.4/openpycharm-native.gif)

Actual installed **0.1.0-dev.4**, **macOS 27.2 arm64**, Python **3.14.0**:
Python Run, unittest, breakpoint/evaluation, cross-file Rename/tests, TypeScript
completion/diagnostics and JavaScript unsaved completion. These six frames are
real native app screenshots from the **local DMG candidate**, source `88387c3`,
DMG SHA-256 `8b849bc6db67e929c8dff25ed32f79b0bb1d420c89487b6d85c0e34c8545dd64`.
This capture is distinct from the CI installer verification.
[Capture manifest](docs/demo/v0.1.0-dev.4/capture.json).
Each publishable release gets fresh installed-version captures and a manifest.
[Historical dev.3 demo](docs/demo/v0.1.0-dev.3/openpycharm-native.gif).

## Build the dev.4 candidate

Python 3.10+ is required. The application includes Java; select a separate local
Python interpreter for Python projects. Keep at least 20 GiB free in addition
to build space. The ordinary build CLI still defaults to dev.3; use the explicit
version and frontend receipt below to assemble the five-plugin candidate.

```sh
python3 -m pip install -r requirements-build.txt
python3 -m unittest discover -s tests -v
python3 scripts/bootstrap.py --target macos-arm64
python3 scripts/provision_http_compiler.py
python3 scripts/provision_database_drivers.py
python3 scripts/provision_frontend_tools.py --target macos-arm64
python3 scripts/package.py --target macos-arm64 --version 0.1.0-dev.4 --output build/dev4/OpenPyCharm.app --frontend-runtime-receipt /absolute/path/from-provision/frontend-tools.json
python3 scripts/launch.py --app build/dev4/OpenPyCharm.app --profile .state/development fixtures/hello-python
python3 scripts/installers.py --target macos-arm64 --version 0.1.0-dev.4 --product build/dev4/OpenPyCharm.app
```

Replace the receipt placeholder with the provision command's `receipt` path.
Provisioning is an explicit build-time network action; normal editor opening
uses the bundled tools. Choose a new output path for each assembly.
On Windows use `python`, `--target windows-x64` and `build/dev4/OpenPyCharm`.
The installer builder obtains an authenticated Inno Setup compiler when needed.

The SDK comes from the pinned [official open-source release](https://github.com/JetBrains/intellij-community/releases/tag/pycharm/2026.1.4),
verified by size and SHA-256 and reused only after a complete tree check.
Installed commercial IDEs and their user data are read-only references.
Local IDE use has no IDE account, billing, subscription, trial or upgrade flow.
Git, GitHub, private-repository and user-selected service authentication remain
available. Source modifications are Apache-2.0; upstream and third-party notices
are retained. OpenPyCharm is independently maintained and is not a JetBrains product.

## Verify

Open [hello-python](fixtures/hello-python) for Python editing, navigation,
refactoring, Run, unittest and Debug. Run its command-line tests separately:

```sh
cd fixtures/hello-python
python3 main.py
python3 -m unittest discover -s tests -v
```

Command-line and native API checks are separate from installed desktop acceptance.
[Reference observations](docs/reference/installed-pycharm.md) and
[architecture](docs/architecture.md) record the evidence boundaries.
