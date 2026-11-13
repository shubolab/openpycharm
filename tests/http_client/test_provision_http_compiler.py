import hashlib
import importlib.util
import io
import json
from email.message import Message
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
import urllib.response
from unittest.mock import patch, Mock

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


class RedirectTransport(provision.urllib.request.BaseHandler):
    """Exercise urllib's real redirect machinery without external networking."""
    handler_order = 400

    def __init__(self, destination, data=b"compiler", repeat=False):
        self.destination, self.data, self.repeat, self.opened = destination, data, repeat, []
        self.responses = []

    def https_open(self, request):
        self.opened.append(request.full_url)
        headers = Message()
        if len(self.opened) == 1 or self.repeat:
            headers["Location"] = self.destination
            code, data, message = 302, b"", "Found"
        else:
            headers["Content-Length"] = str(len(self.data))
            code, data, message = 200, self.data, "OK"
        response = urllib.response.addinfourl(io.BytesIO(data), headers, request.full_url, code)
        response.msg = message
        self.responses.append(response)
        return response

    http_open = https_open


class RouteTransport(RedirectTransport):
    def __init__(self, exchanges):
        self.exchanges, self.opened, self.responses = exchanges, [], []

    def https_open(self, request):
        index = len(self.opened)
        if index >= len(self.exchanges):
            raise AssertionError("An unapproved extra network hop was opened")
        expected, code, destination, data = self.exchanges[index]
        if request.full_url != expected:
            raise AssertionError(f"Unexpected network endpoint {request.full_url}")
        self.opened.append(request.full_url)
        headers = Message()
        if destination is not None:
            headers["Location"] = destination
        else:
            headers["Content-Length"] = str(len(data))
        response = urllib.response.addinfourl(io.BytesIO(data), headers, request.full_url, code)
        response.msg = "Found" if destination is not None else "OK"
        self.responses.append(response)
        return response

    http_open = https_open


class CompilerProvisionControls(unittest.TestCase):
    def response_opener(self, response):
        return patch.object(provision.urllib.request, "build_opener", return_value=Mock(open=Mock(return_value=response)))

    def item(self, data=b"compiler"):
        return {"group": "org.jetbrains.kotlin", "artifact": "compiler", "version": "1.0",
                "name": "compiler-1.0.jar", "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "url": provision.CENTRAL + "org/jetbrains/kotlin/compiler/1.0/compiler-1.0.jar"}

    def compiler_item(self, data=b"compiler"):
        item = json.loads(provision.PIN.read_text())["artifacts"][0]
        item["size"], item["sha256"] = len(data), hashlib.sha256(data).hexdigest()
        item["releaseRedirect"].update(assetSize=item["size"], assetSha256=item["sha256"])
        return item

    def route_opener(self, transport):
        build_opener = provision.urllib.request.build_opener
        return patch.object(provision.urllib.request, "build_opener", side_effect=lambda handler: build_opener(handler, transport))

    def test_authenticated_bytes_promote_and_bad_or_excess_bytes_leave_no_artifact(self):
        item = self.item()
        for data, expected in ((b"compiler", None), (b"tampered", "SHA-256"), (b"compiler extra", "exceeds")):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / item["name"]
                with self.response_opener(Response(data, item["url"])):
                    if expected:
                        with self.assertRaisesRegex(ValueError, expected):
                            provision.download(item, destination)
                        self.assertEqual(list(destination.parent.iterdir()), [])
                    else:
                        provision.download(item, destination)
                        self.assertEqual(destination.read_bytes(), data)

    def test_download_rejects_an_unexpected_final_origin_or_length(self):
        item = self.item()
        for url, length in (("https://unexpected.invalid/compiler.jar", None), (item["url"], item["size"] + 1)):
            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / item["name"]
                with self.response_opener(Response(b"compiler", url, length)):
                    with self.assertRaises(ValueError):
                        provision.download(item, destination)
                self.assertEqual(list(destination.parent.iterdir()), [])

    def test_primary_https_default_port_redirect_is_checked_and_byte_authenticated(self):
        item = self.item()
        target = item["url"].replace("repo.maven.apache.org", "REPO.MAVEN.APACHE.ORG:443")
        for data in (b"compiler", b"tampered"):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                transport = RedirectTransport(target, data)
                build_opener = provision.urllib.request.build_opener
                destination = Path(directory) / item["name"]
                with patch.object(provision.urllib.request, "build_opener", side_effect=lambda handler: build_opener(handler, transport)):
                    if data == b"compiler":
                        result = provision.download(item, destination)
                        self.assertEqual(result["finalUrl"], target)
                        self.assertEqual(result["redirects"], [{"status": 302, "source": item["url"], "destination": target}])
                        self.assertEqual(destination.read_bytes(), data)
                    else:
                        with self.assertRaisesRegex(ValueError, "SHA-256"):
                            provision.download(item, destination)
                        self.assertEqual(list(destination.parent.iterdir()), [])
                self.assertEqual(transport.opened, [item["url"], target])

    def test_redirect_policy_rejects_unapproved_hops_before_contacting_destination(self):
        item = self.item()
        targets = (item["url"].replace("repo.maven.apache.org", "unexpected.invalid"),
                   item["url"].replace("https:", "http:"), item["url"] + "?download=1", item["url"] + "#fragment",
                   item["url"].replace("compiler-1.0.jar", "different.jar"),
                   item["url"].replace("repo.maven.apache.org", "user:password@repo.maven.apache.org"),
                   item["url"].replace("repo.maven.apache.org", "repo.maven.apache.org:8443"))
        for target in targets:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                transport = RedirectTransport(target)
                build_opener = provision.urllib.request.build_opener
                destination = Path(directory) / item["name"]
                with patch.object(provision.urllib.request, "build_opener", side_effect=lambda handler: build_opener(handler, transport)):
                    with self.assertRaisesRegex(ValueError, "before following HTTP 302") as caught:
                        provision.download(item, destination)
                self.assertIn(provision.urllib.parse.urlsplit(target).hostname, str(caught.exception))
                self.assertEqual(transport.opened, [item["url"]])
                self.assertTrue(transport.responses[0].closed)
                self.assertEqual(list(destination.parent.iterdir()), [])

    def test_even_an_authorized_redirect_loop_is_bounded_without_cache_promotion(self):
        item = self.item()
        transport = RedirectTransport(item["url"], repeat=True)
        build_opener = provision.urllib.request.build_opener
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / item["name"]
            with patch.object(provision.urllib.request, "build_opener", side_effect=lambda handler: build_opener(handler, transport)):
                with self.assertRaises(urllib.error.HTTPError):
                    provision.download(item, destination)
            self.assertLessEqual(len(transport.opened), 4)
            self.assertEqual(list(destination.parent.iterdir()), [])

    def test_verified_release_chain_authenticates_bytes_and_omits_temporary_signature_from_receipt(self):
        item = self.compiler_item()
        route = item["releaseRedirect"]
        cdn = route["assetCdnUrl"] + "?sp=r&spr=https&sr=b&sig=test-signature"
        for data in (b"compiler", b"tampered"):
            exchanges = [(item["url"], 301, route["url"], b""), (route["url"], 302, cdn, b""), (cdn, 200, None, data)]
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                transport = RouteTransport(exchanges)
                destination = Path(directory) / item["name"]
                with self.route_opener(transport):
                    if data == b"compiler":
                        receipt = provision.download(item, destination)
                        self.assertEqual(destination.read_bytes(), data)
                        self.assertEqual(receipt["finalUrl"], route["assetCdnUrl"])
                        self.assertTrue(receipt["signedQueryOmitted"])
                        self.assertEqual(len(receipt["redirects"]), 2)
                        self.assertNotIn("test-signature", json.dumps(receipt))
                    else:
                        with self.assertRaisesRegex(ValueError, "SHA-256"):
                            provision.download(item, destination)
                        self.assertEqual(list(destination.parent.iterdir()), [])
                self.assertEqual(transport.opened, [item["url"], route["url"], cdn])

    def test_release_route_cannot_skip_the_primary_release_or_open_another_asset(self):
        item = self.compiler_item()
        route = item["releaseRedirect"]
        cdn = route["assetCdnUrl"] + "?sp=r&spr=https&sr=b&sig=test-signature"
        bad_cdn = (cdn.replace("8c5a5b7a", "aaaaaaaa"), cdn.replace("3432266", "1234567"),
                   cdn.replace("release-assets.githubusercontent.com", "unexpected.invalid"), cdn.replace("https:", "http:"),
                   cdn.replace("spr=https", "spr=http"), cdn.replace("sp=r", "sp=w"),
                   cdn.replace("sig=test-signature", "sig="), cdn + "&unknown=redirect", cdn + "&sp=r")
        cases = [[(item["url"], 301, cdn, b"")],
                 [(item["url"], 301, route["url"].replace("JetBrains/kotlin", "untrusted/kotlin"), b"")],
                 *[[(item["url"], 301, route["url"], b""), (route["url"], 302, target, b"")] for target in bad_cdn]]
        for exchanges in cases:
            with self.subTest(target=exchanges[-1][2]), tempfile.TemporaryDirectory() as directory:
                transport = RouteTransport(exchanges)
                destination = Path(directory) / item["name"]
                with self.route_opener(transport), self.assertRaisesRegex(ValueError, "before following HTTP"):
                    provision.download(item, destination)
                self.assertEqual(len(transport.opened), len(exchanges))
                self.assertTrue(transport.responses[-1].closed)
                self.assertEqual(list(destination.parent.iterdir()), [])

    def test_an_unrelated_artifact_or_changed_asset_pin_cannot_inherit_the_release_route(self):
        item = self.compiler_item()
        unrelated = json.loads(provision.PIN.read_text())["artifacts"][1]
        unrelated["releaseRedirect"] = item["releaseRedirect"]
        with self.assertRaisesRegex(ValueError, "Only the verified"):
            provision.artifact_url(unrelated)
        for key, value in (("assetId", 1), ("assetSize", 0), ("assetSha256", "0" * 64),
                           ("assetCdnUrl", item["releaseRedirect"]["assetCdnUrl"] + "/another")):
            candidate = {**item, "releaseRedirect": {**item["releaseRedirect"], key: value}}
            with self.subTest(changed=key), self.assertRaisesRegex(ValueError, "verified asset identity"):
                provision.artifact_url(candidate)

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
