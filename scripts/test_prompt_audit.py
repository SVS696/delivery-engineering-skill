from __future__ import annotations

import importlib.util
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

    def test_vigers_prompts_pass(self) -> None:
        root = Path(__file__).resolve().parents[2] / "vigers"
        if not root.is_dir():
            self.skipTest("sibling Vigers installation is not part of this package")
        result = audit.audit(root)
        self.assertEqual(result["contracts"], 4)


if __name__ == "__main__":
    unittest.main()
