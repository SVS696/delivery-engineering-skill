from __future__ import annotations

import importlib.util
import json
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
            _, data = case.load(root)
            self.assertEqual(data["gates"]["scope"]["status"], "stale")
            self.assertIn("`scope`: `stale`", (root / "status.md").read_text())

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
            self.assertNotIn("agent-ledger.json", bundle["allowed_inputs"])
            self.assertEqual(bundle["basis_routes"], ["backend-http"])

    def test_revmux_context_is_explicit_and_test_lane_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            prepare_context(
                root,
                {"backend": ["backend-http"], "test": ["test-design"]},
            )
            case.init_case(root, "D-10R", "implement", "demo", ["backend", "test"])
            bundle = case.context_bundle(
                root, "test", "revmux", "initial", "conformance"
            )
            self.assertEqual(bundle["review_backend"], "revmux")
            self.assertEqual(bundle["revmux_profile"], "comprehensive")
            self.assertEqual(bundle["covered_gates"], ["project_conformance"])
            self.assertIn(
                "references/revmux-review-backend.md",
                bundle["contract_inputs"],
            )
            with self.assertRaises(case.CaseError):
                case.context_bundle(
                    root, "backend", "revmux", "initial", "conformance"
                )

    def test_agent_observability_is_additive_and_auditable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            prepare_context(root, {"test": ["test-design"]})
            case.init_case(root, "D-11", "accept", "demo", ["test"])
            run_id = case.agent_ledger.record_run(
                root,
                role="delivery-tester",
                role_mode="verification",
                model="test-model",
                subject_sha256="a" * 64,
                duration_seconds=3,
                retries=0,
                input_bytes=100,
                input_tokens=20,
                output_tokens=5,
                tool_calls=7,
                poll_calls=1,
                wait_seconds=30,
                reported_blocker=0,
                reported_major=1,
                reported_minor=1,
                status="completed",
                degraded_reasons=[],
                lenses=["acceptance@1"],
                prompt_artifact="acceptance.md",
                output_artifact="evidence.md",
            )
            case.agent_ledger.record_verification(
                root,
                run_id=run_id,
                accepted=1,
                rejected=0,
                duplicate=1,
                verified=1,
                evidence_ref="evidence.md",
            )
            _, payload = case.agent_ledger.load(root)
            self.assertEqual(payload["runs"][0]["run_id"], "AR-0001")
            self.assertEqual(payload["runs"][0]["tool_calls"], 7)
            self.assertEqual(payload["runs"][0]["poll_calls"], 1)
            self.assertEqual(payload["runs"][0]["wait_seconds"], 30)
            self.assertEqual(
                payload["runs"][0]["verification"]["dispositions"]["duplicate"],
                1,
            )
            self.assertEqual(case.validate_case(root, False)["status"], "PASS")
            payload["runs"][0]["poll_calls"] = -1
            self.assertTrue(
                any(
                    "poll_calls" in error
                    for error in case.agent_ledger.validate(
                        payload,
                        case_id="D-11",
                        root=root,
                    )
                )
            )

    def test_schema_three_rejects_broken_agent_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            prepare_context(root, {"test": ["test-design"]})
            case.init_case(root, "D-12", "accept", "demo", ["test"])
            ledger_path = root / case.agent_ledger.FILENAME
            payload = json.loads(ledger_path.read_text(encoding="utf-8"))
            payload["runs"] = "broken"
            ledger_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(case.CaseError) as raised:
                case.validate_case(root, False)
            self.assertIn("agent ledger", str(raised.exception))
            _, broken = case.agent_ledger.load(root)
            self.assertTrue(
                case.agent_ledger.validate(broken, case_id="D-12", root=root)
            )

    def test_independent_pass_requires_exact_fresh_tester_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            prepare_context(root, {"test": ["test-design"]})
            case.init_case(root, "D-13", "accept", "demo", ["test"])
            subject = root / "acceptance.md"
            assignment = case.begin_verification(
                root,
                subjects=[subject],
                note="Initial acceptance verification",
            )
            report = root / "reports" / "verification.md"
            report.write_text("# Verification\n\nPASS\n", encoding="utf-8")
            run_id = case.agent_ledger.record_run(
                root,
                role="delivery-tester",
                role_mode="verification",
                model="test-model",
                subject_sha256=assignment["subject_sha256"],
                duration_seconds=1,
                retries=0,
                input_bytes=None,
                input_tokens=None,
                output_tokens=None,
                reported_blocker=0,
                reported_major=0,
                reported_minor=0,
                status="completed",
                degraded_reasons=[],
                lenses=["acceptance@1"],
                prompt_artifact=None,
                output_artifact="reports/verification.md",
            )
            with self.assertRaisesRegex(case.CaseError, "requires --agent-run"):
                case.set_gate(
                    root,
                    "independent_verification",
                    "pass",
                    "reports/verification.md",
                    "",
                    [subject],
                )
            case.set_gate(
                root,
                "independent_verification",
                "pass",
                "reports/verification.md",
                "",
                [subject],
                run_id,
            )
            _, data = case.load(root)
            self.assertEqual(
                data["gates"]["independent_verification"]["agent_run"]["run_id"],
                run_id,
            )
            self.assertEqual(case.validate_case(root, False)["status"], "PASS")

    def test_verification_budget_stops_fourth_full_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            prepare_context(root, {"test": ["test-design"]})
            case.init_case(root, "D-14", "accept", "demo", ["test"])
            for attempt in range(3):
                case.begin_verification(
                    root,
                    subjects=[root / "acceptance.md"],
                    note=f"Attempt {attempt + 1}",
                )
                case.set_gate(
                    root,
                    "independent_verification",
                    "fail",
                    "",
                    f"Attempt {attempt + 1} found accepted gaps",
                    [],
                )
            with self.assertRaisesRegex(case.CaseError, "budget exhausted"):
                case.begin_verification(
                    root,
                    subjects=[root / "acceptance.md"],
                    note="Forbidden fourth pass",
                )
            _, data = case.load(root)
            self.assertEqual(data["verification"]["status"], "feedback_required")
            self.assertEqual(data["lanes"]["test"]["state"], "blocked")

    def test_init_binds_vigers_delivery_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            prepare_context(root, {"test": ["test-design"]})
            (root / case.DELIVERY_HANDOFF).write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "case_id": "V-1",
                        "spec_revision": 7,
                        "spec_fingerprint": "a" * 64,
                        "acceptance_fingerprint": "b" * 64,
                        "implementation_transition": {"mode": "evolve-in-place"},
                    }
                ),
                encoding="utf-8",
            )
            data = case.init_case(root, "D-15", "accept", "demo", ["test"])
            self.assertEqual(data["verification"]["source_revision"], "vigers:V-1@7")

    def test_feedback_is_one_complete_batch_per_source_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            prepare_context(root, {"test": ["test-design"]})
            (root / case.DELIVERY_HANDOFF).write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "case_id": "V-2",
                        "spec_revision": 4,
                        "spec_fingerprint": "c" * 64,
                        "acceptance_fingerprint": "d" * 64,
                        "implementation_transition": {"mode": "evolve-in-place"},
                    }
                ),
                encoding="utf-8",
            )
            case.init_case(root, "D-16", "accept", "demo", ["test"])
            case.begin_verification(
                root,
                subjects=[root / "acceptance.md"],
                note="Find all spec gaps",
            )
            evidence = root / "reports" / "verification.md"
            evidence.write_text("# Findings\n\nTwo accepted gaps.\n", encoding="utf-8")
            payload = case.record_feedback_batch(
                root,
                gaps=["GAP-001 missing timeout", "GAP-002 missing rollback condition"],
                evidence=[evidence],
                note="Complete accepted batch",
            )
            self.assertTrue(payload["batch_complete"])
            self.assertEqual(payload["target_spec_revision"], 4)
            with self.assertRaisesRegex(case.CaseError, "already has a feedback batch"):
                case.record_feedback_batch(
                    root,
                    gaps=["GAP-003 late finding"],
                    evidence=[evidence],
                    note="Must not fragment feedback",
                )
            next_handoff = Path(temporary) / "delivery-handoff-r5.json"
            next_handoff.write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "case_id": "V-2",
                        "spec_revision": 5,
                        "spec_fingerprint": "e" * 64,
                        "acceptance_fingerprint": "f" * 64,
                        "implementation_transition": {"mode": "evolve-in-place"},
                    }
                ),
                encoding="utf-8",
            )
            migrated = case.migrate_source_handoff(
                root,
                handoff=next_handoff,
                note="Vigers resolved the complete feedback batch",
            )
            self.assertEqual(migrated["source_revision"], "vigers:V-2@5")
            _, data = case.load(root)
            self.assertEqual(data["verification"]["attempts"], 0)
            self.assertIsNone(data["verification"]["feedback_batch"])


if __name__ == "__main__":
    unittest.main()
