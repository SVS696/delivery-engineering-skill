from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


CONTEXT_MODULE_PATH = Path(__file__).with_name("delivery_context.py")
CONTEXT_SPEC = importlib.util.spec_from_file_location("delivery_context", CONTEXT_MODULE_PATH)
assert CONTEXT_SPEC and CONTEXT_SPEC.loader
context = importlib.util.module_from_spec(CONTEXT_SPEC)
sys.modules["delivery_context"] = context
CONTEXT_SPEC.loader.exec_module(context)


MODULE_PATH = Path(__file__).with_name("delivery_case.py")
SPEC = importlib.util.spec_from_file_location("delivery_case", MODULE_PATH)
assert SPEC and SPEC.loader
case = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(case)


def prepare_context(root: Path, assignments: dict[str, list[str]]) -> None:
    payload, contents = context.build_engineering_context(assignments)
    context.write_engineering_context(root, payload, contents)


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
            prepare_context(root, {"test": ["test-design"]})
            case.init_case(root, "D-3", "accept", "demo", ["test"])
            with self.assertRaises(case.CaseError):
                case.transition(root, "test", "blocked", "")

    def test_gate_detects_changed_subject(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            prepare_context(root, {"test": ["test-design"]})
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
            prepare_context(root, {"test": ["test-design"]})
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

    def test_new_case_requires_engineering_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(case.CaseError) as raised:
                case.init_case(Path(temporary) / "case", "D-6", "accept", "demo", ["test"])
            self.assertIn("requires engineering-context", str(raised.exception))

    def test_init_binds_context_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            prepare_context(
                root,
                {"backend": ["backend-http"], "test": ["test-design"]},
            )
            data = case.init_case(root, "D-7", "implement", "demo", ["backend", "test"])
            payload, _ = case.load_engineering_context(root)
            self.assertEqual(
                data["engineering_context"]["fingerprint"], payload["fingerprint"]
            )

    def test_init_rejects_context_lane_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            prepare_context(root, {"test": ["test-design"]})
            with self.assertRaises(case.CaseError):
                case.init_case(root, "D-8", "implement", "demo", ["backend", "test"])

    def test_validation_detects_tampered_lane_basis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            prepare_context(root, {"test": ["test-design"]})
            case.init_case(root, "D-9", "accept", "demo", ["test"])
            with (root / "basis" / "test.md").open("a", encoding="utf-8") as stream:
                stream.write("tampered\n")
            with self.assertRaises(case.CaseError) as raised:
                case.validate_case(root, False)
            self.assertIn("content hash mismatch", str(raised.exception))

    def test_context_bundle_contains_only_lane_basis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            prepare_context(
                root,
                {"backend": ["backend-http"], "test": ["test-design"]},
            )
            case.init_case(root, "D-10", "implement", "demo", ["backend", "test"])
            bundle = case.context_bundle(root, "backend")
            self.assertIn("basis/backend.md", bundle["allowed_inputs"])
            self.assertNotIn("basis/test.md", bundle["allowed_inputs"])
            self.assertEqual(bundle["basis_routes"], ["backend-http"])


if __name__ == "__main__":
    unittest.main()
