import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("http_compiler_provision", ROOT / "scripts/provision_http_compiler.py")
provision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provision)


class Response(io.BytesIO):
    def __init__(self, data, url, length=None):
        super().__init__(data)
        self.url = url
        self.headers = {} if length is None else {"Content-Length": str(length)}

    def geturl(self):
        return self.url


class CompilerProvisionControls(unittest.TestCase):
    def item(self, data=b"compiler"):
        return {"group": "org.jetbrains.kotlin", "artifact": "compiler", "version": "1.0",
                "name": "compiler-1.0.jar", "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "url": provision.CENTRAL + "org/jetbrains/kotlin/compiler/1.0/compiler-1.0.jar"}

    def test_authenticated_bytes_promote_and_bad_or_excess_bytes_leave_no_artifact(self):
        item = self.item()
        for data, expected in ((b"compiler", None), (b"tampered", "SHA-256"), (b"compiler extra", "exceeds")):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / item["name"]
                with patch.object(provision.urllib.request, "urlopen", return_value=Response(data, item["url"])):
                    if expected:
                        with self.assertRaisesRegex(ValueError, expected):
                            provision.download(item, destination)
                        self.assertEqual(list(destination.parent.iterdir()), [])
                    else:
                        provision.download(item, destination)
                        self.assertEqual(destination.read_bytes(), data)

    def test_download_cannot_follow_a_different_origin_or_length(self):
        item = self.item()
        for url, length in (("https://unexpected.invalid/compiler.jar", None), (item["url"], item["size"] + 1)):
            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / item["name"]
                with patch.object(provision.urllib.request, "urlopen", return_value=Response(b"compiler", url, length)):
                    with self.assertRaises(ValueError):
                        provision.download(item, destination)
                self.assertEqual(list(destination.parent.iterdir()), [])

    def test_coordinate_and_remote_origin_are_fixed_by_the_lock(self):
        for change in ({"group": "../../outside"}, {"url": "https://unexpected.invalid/compiler.jar"},
                       {"name": "../compiler.jar"}, {"size": 1024**3}, {"sha256": "unknown"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                provision.artifact_url({**self.item(), **change})

    def test_shared_cache_is_rejected_before_any_download_or_write(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "unowned-cache"
            with patch.object(provision.urllib.request, "urlopen", side_effect=AssertionError("No request allowed")):
                with self.assertRaisesRegex(ValueError, "owned"):
                    provision.provision(target)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
