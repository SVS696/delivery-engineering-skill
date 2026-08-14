from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("prompt_audit.py")
SPEC = importlib.util.spec_from_file_location("prompt_audit", MODULE_PATH)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class PromptAuditTests(unittest.TestCase):
    def test_delivery_prompts_pass(self) -> None:
        result = audit.audit(Path(__file__).resolve().parent.parent)
        self.assertEqual(result["contracts"], 3)
        self.assertEqual(result["checks"], 15)

    def test_missing_protected_floor_is_rejected(self) -> None:
        source = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "skill"
            shutil.copytree(source, root, ignore=shutil.ignore_patterns("__pycache__"))
            contract = root / "agents" / "contracts" / "backend.md"
            contract.write_text(
                contract.read_text(encoding="utf-8").replace("`protected_floor`", "protected state"),
                encoding="utf-8",
            )
            with self.assertRaises(audit.PromptAuditError):
                audit.audit(root)

    def test_vigers_prompts_pass(self) -> None:
        root = Path(__file__).resolve().parents[2] / "vigers"
        if not root.is_dir():
            self.skipTest("sibling Vigers installation is not part of this package")
        result = audit.audit(root)
        self.assertGreaterEqual(result["contracts"], 4)
        self.assertEqual(result["codex_adapters"], result["contracts"])
        self.assertEqual(result["claude_adapters"], result["contracts"])


if __name__ == "__main__":
    unittest.main()
