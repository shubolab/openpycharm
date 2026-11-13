# Installed reference

Observed on 2026-11-13, macOS Apple silicon. The installed reference is
`~/Applications/PyCharm.app`, version **2026.1.4**, build **PY-261.26222.68**.
It is the unified commercial distribution, not the input to this product.

REA `inspect_plist` evidence:
`ev_3a2794bd04161298dbe071a3ea6edb0e4df6b30a3aee9fbccdcfbb506d1b8bab`.
The Info.plist SHA-256 is
`40efccabf6681f20d008025d998403b43d0e56dd3ab90479cd372ce1f4e3e260`.
This establishes bundle identity only, not feature correctness.

Computer-use observation showed the native dark workbench, project and Git
branch controls, editor tabs, left tool-window stripe, bottom Git panel, Python
Console and Packages entries, interpreter status, standard Code/Refactor/Run
menus, Chinese localization, and a Pro trial advertisement. The user's existing
project was not edited and its screenshot is not committed to this public repo.

The product uses the separate [open-source release](https://github.com/JetBrains/intellij-community/releases/tag/pycharm/2026.1.4)
at source commit `456919a9624bae72ac12efafc35d2b916cb0c5c5`, authenticated by
the archive size and SHA-256 in `product/platform.lock.json`. Its product code
must be **PC**, contain **PythonCore**, and omit the proprietary **Pythonid**.

Inference: matching the platform source/version provides a strong basis for the
same native editing and desktop interactions. Unknown: complete behavioral
parity, framework integrations, notebooks, databases and all operating-system
workflows until the acceptance matrix is exercised.

## Reuse from opengoland

The sibling project's native resource-loading switch, isolated configuration
paths, cached plugin-descriptor handling, module-repository serialization and
installer verification guide this implementation. Product code is specialized
for the OSS Python distribution; Go language integrations are not bundled.
