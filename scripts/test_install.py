from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("install.py")
SPEC = importlib.util.spec_from_file_location("delivery_install", MODULE_PATH)
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = installer
SPEC.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def test_install_and_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            states = installer.install(installer.DEFAULT_ROOT, home)
            self.assertTrue(states)
            self.assertTrue(all(item.status == "installed" for item in states))
            checked = installer.inspect_links(installer.DEFAULT_ROOT, home)
            self.assertTrue(all(item.status == "installed" for item in checked))

    def test_conflict_prevents_all_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            conflict = home / ".agents" / "skills" / "delivery-engineering"
            conflict.mkdir(parents=True)
            with self.assertRaises(installer.InstallerError):
                installer.install(installer.DEFAULT_ROOT, home)
            self.assertFalse((home / ".codex" / "agents" / "delivery-backend.toml").exists())


if __name__ == "__main__":
    unittest.main()
