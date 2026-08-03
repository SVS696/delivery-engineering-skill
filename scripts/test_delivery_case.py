from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("delivery_case.py")
SPEC = importlib.util.spec_from_file_location("delivery_case", MODULE_PATH)
assert SPEC and SPEC.loader
case = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(case)


class DeliveryCaseTests(unittest.TestCase):
    def test_implement_requires_developer_and_test(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(case.CaseError):
                case.init_case(Path(temporary) / "case", "D-1", "implement", "demo", ["test"])

    def test_accept_rejects_developer_lane(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(case.CaseError):
                case.init_case(Path(temporary) / "case", "D-2", "accept", "demo", ["backend", "test"])

    def test_transition_requires_note_for_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            case.init_case(root, "D-3", "accept", "demo", ["test"])
            with self.assertRaises(case.CaseError):
                case.transition(root, "test", "blocked", "")

    def test_gate_detects_changed_subject(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            case.init_case(root, "D-4", "accept", "demo", ["test"])
            subject = root / "scope.md"
            case.set_gate(root, "scope", "pass", "reviewed", "", [subject])
            subject.write_text("# Scope\nchanged\n", encoding="utf-8")
            with self.assertRaises(case.CaseError) as raised:
                case.validate_case(root, False)
            self.assertIn("stale gate subjects", str(raised.exception))

    def test_test_design_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            case.init_case(root, "D-5", "test-design", "demo", ["test"])
            case.transition(root, "test", "designing", "")
            report = root / "reports" / "test-design.md"
            report.write_text("# Test design\n\nAC-1 -> condition -> check\n", encoding="utf-8")
            case.transition(root, "test", "designed", "")
            subjects = [root / "scope.md", root / "acceptance.md", root / "conformance.md", report]
            for gate in ("authorization", "scope", "codebase_conformance", "lane_reports", "traceability"):
                case.set_gate(root, gate, "pass", f"evidence for {gate}", "", subjects)
            result = case.validate_case(root, True)
            self.assertEqual(result["status"], "PASS")


if __name__ == "__main__":
    unittest.main()

