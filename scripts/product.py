"""Independent product metadata for the authenticated OSS PyCharm distribution.

The resource-loading and ZIP-index handling follow the working opengoland
assembler. All transformations apply to an owned build copy, never an SDK.
"""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent.parent
IDENTITY = json.loads((ROOT / "product/product.json").read_text())


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rewrite_jar(path, replacements):
    """Preserve all ordinary ZIP entries; invalidate the offset-based index."""
    path = Path(path)
    temporary = path.with_suffix(".jar.openpycharm")
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(temporary, "w") as target:
        if len(source.namelist()) != len(set(source.namelist())):
            raise ValueError("Duplicate JAR entries")
        target.comment = b"" if len(source.comment) == 5 and source.comment[0] == 4 else source.comment
        unknown = set(replacements) - set(source.namelist())
        if unknown:
            raise ValueError(f"Missing JAR entries: {unknown}")
        for entry in source.infolist():
            target.writestr(entry, replacements.get(entry.filename, source.read(entry.filename)))
    temporary.replace(path)


def brand_application_info(raw):
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    xml = ET.fromstring(raw, parser=parser)
    namespace = xml.tag.partition("}")[0].removeprefix("{") if "}" in xml.tag else ""
    tag = lambda local: f"{{{namespace}}}{local}" if namespace else local
    names = xml.find(tag("names"))
    if names is None:
        raise ValueError("Missing application names")
    names.attrib.update(product=IDENTITY["name"], fullname=IDENTITY["name"], script=IDENTITY["script"],
                        motto="An open Python IDE")
    names.attrib.pop("edition", None)
    company = xml.find(tag("company"))
    if company is None:
        company = ET.SubElement(xml, tag("company"))
    company.attrib.update(name="OpenPyCharm contributors", shortName="OpenPyCharm", url=IDENTITY["repository"])
    # Retain build/API identity so Marketplace compatibility checks stay accurate.
    for local in ("documentation", "support", "feedback", "whatsnew"):
        element = xml.find(tag(local))
        if element is not None:
            for key in ("url", "web-url"):
                if key in element.attrib:
                    element.set(key, IDENTITY["repository"])
    if namespace:
        ET.register_namespace("", namespace)
    return ET.tostring(xml, encoding="utf-8", xml_declaration=True)


def brand_resources(contents):
    from icons import resources
    art = resources()
    changed = []
    for jar in (contents / "lib").glob("*.jar"):
        with zipfile.ZipFile(jar) as source:
            replacements = {name: brand_application_info(source.read(name))
                            for name in source.namelist()
                            if re.fullmatch(r"idea/[^/]*ApplicationInfo\.xml", name)}
            replacements.update({name: value for name, value in art.items() if name in source.namelist()})
        if replacements:
            before = sha(jar)
            rewrite_jar(jar, replacements)
            changed.append({"path": str(jar.relative_to(contents)), "entries": sorted(replacements),
                            "beforeSha256": before, "afterSha256": sha(jar)})
    if not changed:
        raise ValueError("No OSS application-info resource found")
    return changed


def brand_product_info(info, version):
    info = json.loads(json.dumps(info))
    if info["productCode"] != "PC":
        raise ValueError("Only the pinned open-source PyCharm product may be packaged")
    info.update(name=IDENTITY["name"], productVendor=IDENTITY["vendor"],
                dataDirectoryName=IDENTITY["selector"], envVarBaseName="OPENPYCHARM")
    info["openpycharmVersion"] = version
    overrides = {"idea.vendor.name": IDENTITY["vendor"], "idea.paths.selector": IDENTITY["selector"],
                 "intellij.platform.load.app.info.from.resources": "true",
                 "idea.no.platform.update": "true", "ide.no.platform.update": "true"}
    for launch in info["launch"]:
        # Thin-client launch modes are not shipped as a supported product feature.
        launch.pop("customCommands", None)
        args = launch.get("additionalJvmArguments", [])
        args = [a for a in args if not any(a.startswith(f"-D{k}=") for k in overrides)]
        launch["additionalJvmArguments"] = args + [f"-D{k}={v}" for k, v in overrides.items()]
    return info


def brand_plist(info, version):
    result = dict(info)
    result.update(CFBundleName=IDENTITY["name"], CFBundleDisplayName=IDENTITY["name"],
                  CFBundleIdentifier=IDENTITY["id"], CFBundleShortVersionString=version.split("-", 1)[0],
                  CFBundleGetInfoString=f"OpenPyCharm {version}; based on open-source PyCharm; notices retained")
    result["CFBundleURLTypes"] = [{"CFBundleTypeRole": "Editor", "CFBundleURLName": "OpenPyCharm",
                                   "CFBundleURLSchemes": ["openpycharm"]}]
    for key, value in list(result.items()):
        if key.endswith("UsageDescription") and isinstance(value, str):
            result[key] = value.replace("PyCharm", "OpenPyCharm")
    return result


def write_paths(contents, macos):
    if macos:
        paths = {"config": "${user.home}/Library/Application Support/OpenPyCharm/config",
                 "system": "${user.home}/Library/Caches/OpenPyCharm",
                 "plugins": "${user.home}/Library/Application Support/OpenPyCharm/plugins",
                 "log": "${user.home}/Library/Logs/OpenPyCharm"}
    else:
        paths = {name: "${user.home}/AppData/" + ("Local" if name in ("system", "log") else "Roaming")
                 + "/OpenPyCharm/" + name for name in ("config", "system", "plugins", "log")}
    properties = "\n".join(f"idea.{key}.path={value}" for key, value in paths.items()) + "\n"
    (contents / "bin/openpycharm.properties").write_text(properties, encoding="utf-8")
    default = contents / "bin/idea.properties"
    default.write_text(default.read_text(encoding="utf-8") + "\n# OpenPyCharm isolated paths\n" + properties,
                       encoding="utf-8")
    return paths
