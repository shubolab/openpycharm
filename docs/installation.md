# Installation and local profiles

Development targets are macOS Apple silicon and Windows x64. A source build is
not a published release or proof of all native workflows. The current acceptance
status is in [acceptance.md](acceptance.md).

## macOS

Build `OpenPyCharm-VERSION-macos-arm64.dmg` with `scripts/installers.py`, mount it,
and drag **OpenPyCharm.app** to **Applications** or `~/Applications`. Open the
installed app. Local builds use an ad-hoc signature and are not notarized.
Check the installer SHA-256 against its generated `.sha256` file before use.

The app uses its own bundle ID `dev.openpycharm.ide`. Configuration and plugins
live under `~/Library/Application Support/OpenPyCharm`; caches and logs are in
`~/Library/Caches/OpenPyCharm` and `~/Library/Logs/OpenPyCharm`. Uninstalling the
application does not delete projects or these settings.

## Windows

Build the Windows x64 product on Windows, then use `scripts/installers.py` to
create the `.exe` installer. It installs per user, offers optional `.py` file
association, and does not require an administrator. The first release candidates
are unsigned. The silent installation check is a separate build option; native
Run/Test/Debug acceptance is required as well.

Configuration/plugins are under `%USERPROFILE%\AppData\Roaming\OpenPyCharm`;
caches/logs are under `%USERPROFILE%\AppData\Local\OpenPyCharm`.

## Interpreter and test profiles

Choose an installed Python interpreter or create a virtual environment through
the native project/interpreter settings. OpenPyCharm's Java runtime is included;
the project Python interpreter is separate.

For development use `python3 scripts/launch.py --profile .state/development
fixtures/hello-python`. This test profile has its own config, cache, plugins and
logs. It does not import the installed PyCharm configuration.

Upstream licenses and third-party notices remain in the application's `license`
directory. The installed reference PyCharm is never modified.
