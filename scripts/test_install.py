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
            codex_agent = home / ".codex" / "agents" / "delivery-backend.toml"
            claude_agent = home / ".claude" / "agents" / "delivery-backend.md"
            self.assertTrue(codex_agent.is_file())
            self.assertFalse(codex_agent.is_symlink())
            self.assertEqual(
                codex_agent.read_bytes(),
                (installer.DEFAULT_ROOT / "agents" / "codex" / codex_agent.name).read_bytes(),
            )
            self.assertTrue(claude_agent.is_symlink())
            self.assertTrue(installer.manifest_path(home).is_file())

    def test_matching_codex_symlink_is_migrated_to_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            source = (
                installer.DEFAULT_ROOT
                / "agents"
                / "codex"
                / "delivery-backend.toml"
            )
            target = home.resolve() / ".codex" / "agents" / source.name
            target.parent.mkdir(parents=True)
            target.symlink_to(source)

            before = installer.inspect_links(installer.DEFAULT_ROOT, home)
            backend = next(item for item in before if item.spec.target == target)
            self.assertEqual(backend.status, "migration-required")

            installer.install(installer.DEFAULT_ROOT, home)
            self.assertTrue(target.is_file())
            self.assertFalse(target.is_symlink())
            self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_managed_codex_copy_refreshes_but_manual_edit_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sandbox = Path(temporary)
            skill_root = sandbox / "skill"
            home = sandbox / "home"
            for name in installer.AGENTS:
                codex = skill_root / "agents" / "codex" / f"{name}.toml"
                claude = skill_root / "agents" / "claude" / f"{name}.md"
                codex.parent.mkdir(parents=True, exist_ok=True)
                claude.parent.mkdir(parents=True, exist_ok=True)
                codex.write_text(f'name = "{name}"\n', encoding="utf-8")
                claude.write_text(f"# {name}\n", encoding="utf-8")

            installer.install(skill_root, home)
            source = skill_root / "agents" / "codex" / "delivery-backend.toml"
            target = home.resolve() / ".codex" / "agents" / source.name
            source.write_text(
                'name = "delivery-backend"\ndescription = "updated"\n',
                encoding="utf-8",
            )

            refresh = next(
                item
                for item in installer.inspect_links(skill_root, home)
                if item.spec.target == target
            )
            self.assertEqual(refresh.status, "refresh-required")
            installer.install(skill_root, home)
            self.assertEqual(target.read_bytes(), source.read_bytes())

            target.write_text("manual edit\n", encoding="utf-8")
            with self.assertRaises(installer.InstallerError):
                installer.install(skill_root, home)

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
