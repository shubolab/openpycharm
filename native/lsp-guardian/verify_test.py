#!/usr/bin/env python3
"""Small archive controls. No Go, IDE, Node or network execution."""
from __future__ import annotations

import io
import os
from pathlib import Path
import tarfile
import tempfile
import unittest

import verify


class ToolchainArchiveControls(unittest.TestCase):
    def test_exact_archive_rejects_extra_tools_links_and_changed_bytes(self):
        with tempfile.TemporaryDirectory(prefix="opc-guardian-archive-") as temporary:
            directory = Path(temporary).resolve()
            root = directory / "go"
            root.mkdir()
            archive = directory / "go.tar.gz"
            with tarfile.open(archive, "w:gz") as package:
                for number in range(1000):
                    name = f"input-{number}"
                    data = name.encode()
                    (root / name).write_bytes(data)
                    member = tarfile.TarInfo("go/" + name)
                    member.size = len(data)
                    package.addfile(member, io.BytesIO(data))
            digest = verify.sha(archive)
            self.assertEqual(verify.authenticate_go(root, archive, digest), 1000)
            extra = root / "test2json"
            extra.write_bytes(b"untrusted extra tool")
            with self.assertRaisesRegex(ValueError, "unexpected files"):
                verify.authenticate_go(root, archive, digest)
            extra.unlink()
            if os.name != "nt":  # Creating Windows links may require elevation.
                extra.symlink_to(root / "input-0")
                with self.assertRaisesRegex(ValueError, "symlink"):
                    verify.authenticate_go(root, archive, digest)
                extra.unlink()
            (root / "input-0").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "differs"):
                verify.authenticate_go(root, archive, digest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
