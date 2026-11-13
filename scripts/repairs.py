"""Replay bounded open-source platform repairs into an owned product copy.

The Unicode and PSI fixes are reused from tracked opengoland source. JDOMUtil preserves valid
supplementary Unicode in persisted XML; PsiChangeHandler initializes its Alarm
before publishing listeners. JBCefApp constructs its singleton on demand outside
class initialization. Every original JAR, source and patch is pinned;
all non-replaced JAR entry bytes are checked after compilation and installation.
"""

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import SimpleNamespace

from bootstrap import PIN_PATH, validate_cached
from platform_layout import cache_lock, detect_platform_layout

ROOT = Path(__file__).resolve().parent.parent
_SPEC = spec_from_file_location("openpycharm_platform_repair", ROOT / "scripts/patch-platform-unicode.py")
_REPAIR = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_REPAIR)


def apply(contents: Path, sdk: Path) -> dict:
    """Compile authenticated public source and install only below ROOT/build.

    Call before branding or local-product metadata edits: the copied input JARs
    must still match their authenticated upstream digests. Repeated application
    is allowed only if the already installed repair verifies completely.
    """
    contents = Path(contents).resolve()
    layout = detect_platform_layout(Path(sdk))
    target = "macos-arm64" if layout.platform == "macos" else "windows-x64"
    if layout.platform not in {"macos", "windows"}:
        raise ValueError("Platform repairs currently support macOS and Windows only")
    authenticated = validate_cached(layout.sdk_root.parent, json.loads(PIN_PATH.read_text(encoding="utf-8")), target)
    if authenticated != layout.sdk_root:
        raise ValueError("Repairs require the authenticated OSS PyCharm SDK")
    build = (ROOT / "build").resolve()
    if not contents.is_relative_to(build) or contents.is_relative_to(layout.sdk_root):
        raise ValueError("Repairs may modify only an owned copy below this repository's build directory")
    if not contents.is_dir():
        raise ValueError("Product contents directory does not exist")
    target_app = contents.parent if layout.platform == "macos" else contents
    fixes = []
    for name in ("unicode", "psi-listener", "jcef-startup"):
        suffix = "-windows" if layout.platform == "windows" else ""
        pin_path = ROOT / f"product/patches/platform-{name}{suffix}-2026.1.4.json"
        cache_name = f"platform-{name}-{target}"
        cache = ROOT / ".tools" / cache_name
        cache.mkdir(parents=True, exist_ok=True)
        args = SimpleNamespace(
            sdk=layout.sdk_root, pin=pin_path,
            marker=f"META-INF/openpycharm-platform-{name}.json",
            cache_name=cache_name, jar_output=None, metadata_output=None,
            target_app=target_app,
        )
        with cache_lock(cache / "build.lock"):
            result = _REPAIR.build(args)
        startup_controls = None
        if name == "jcef-startup":
            from check_jcef_startup import verify
            startup_controls = verify(layout.sdk_root, result, pin_path)
        # Keep reviewable provenance without retaining a staging-directory path
        # that becomes obsolete when the assembled application is renamed.
        fix = {
            "name": name,
            "jar": result["upstreamJarRelativePath"].removeprefix("Contents/"),
            "pin": str(pin_path.relative_to(ROOT)),
            "upstreamJarSha256": result["upstreamJarSha256"],
            "patchedJarSha256": result["patchedJarSha256"],
            "upstreamCommit": result["upstreamCommit"],
            "patchSha256": result["patchSha256"],
            "sources": result["sources"],
            "compiler": result["compiler"],
            "classSha256": result["classSha256"],
            "marker": result["marker"],
            "unchangedEntriesVerified": True,
        }
        if startup_controls is not None:
            fix["startupControls"] = startup_controls
        fixes.append(fix)
    return {
        "schema": 1, "sourceSdk": str(layout.sdk_root), "target": target,
        "fixes": fixes, "sourceSdkModified": False,
        "limitations": ["Source replay and entry verification do not replace native behavior acceptance"],
    }
