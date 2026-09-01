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


def prepare_verified_accept_case(root: Path, case_id: str) -> list[Path]:
    prepare_context(root, {"test": ["test-design"]})
    case.init_case(root, case_id, "accept", "demo", ["test"])
    case.transition(root, "test", "ready", "")
    case.transition(root, "test", "verifying", "")
    subject = root / "acceptance.md"
    assignment = case.begin_verification(
        root,
        subjects=[subject],
        note="Initial verification",
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
        input_bytes=10,
        input_tokens=2,
        output_tokens=2,
        reported_blocker=0,
        reported_major=0,
        reported_minor=0,
        status="completed",
        degraded_reasons=[],
        lenses=["acceptance@1"],
        prompt_artifact="acceptance.md",
        output_artifact="reports/verification.md",
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
    case.transition(root, "test", "verified", "")
    case.set_gate(
        root,
        "project_checks",
        "pass",
        "project checks pass",
        "",
        [subject],
    )
    return [root / "scope.md", subject, root / "conformance.md", report]


def record_conformance_run(
    root: Path,
    *,
    report_name: str,
    body: str,
    major: int,
) -> tuple[str, str]:
    _, data = case.load(root)
    state = data["conformance"]
    relative = f"reports/{report_name}"
    report = root / relative
    report.write_text(body, encoding="utf-8")
    run_id = case.agent_ledger.record_run(
        root,
        role="delivery-tester",
        role_mode="conformance",
        model="test-model",
        subject_sha256=state["current_subject_sha256"],
        duration_seconds=1,
        retries=0,
        input_bytes=10,
        input_tokens=2,
        output_tokens=2,
        reported_blocker=0,
        reported_major=major,
        reported_minor=0,
        status="completed",
        degraded_reasons=[],
        lenses=["project-conformance@1"],
        prompt_artifact="conformance.md",
        output_artifact=relative,
    )
    return run_id, relative


def pass_plain_final_gates(root: Path, subjects: list[Path]) -> None:
    for gate in (
        "authorization",
        "scope",
        "codebase_conformance",
        "lane_reports",
        "traceability",
    ):
        case.set_gate(root, gate, "pass", f"{gate} pass", "", subjects)


def refresh_verification(root: Path, subject: Path, report_name: str) -> None:
    case.transition(root, "test", "verifying", "")
    assignment = case.begin_verification(
        root,
        subjects=[subject],
        note="User-approved affected verification",
    )
    relative = f"reports/{report_name}"
    report = root / relative
    report.write_text("# Verification\n\nPASS\n", encoding="utf-8")
    run_id = case.agent_ledger.record_run(
        root,
        role="delivery-tester",
        role_mode="verification",
        model="test-model",
        subject_sha256=assignment["subject_sha256"],
        duration_seconds=1,
        retries=0,
        input_bytes=10,
        input_tokens=2,
        output_tokens=2,
        reported_blocker=0,
        reported_major=0,
        reported_minor=0,
        status="completed",
        degraded_reasons=[],
        lenses=["acceptance@1"],
        prompt_artifact="acceptance.md",
        output_artifact=relative,
    )
    case.set_gate(
        root,
        "independent_verification",
        "pass",
        relative,
        "",
        [subject],
        run_id,
    )
    case.transition(root, "test", "verified", "")
    case.set_gate(
        root,
        "project_checks",
        "pass",
        "affected project checks pass",
        "",
        [subject],
    )


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
            subjects = prepare_verified_accept_case(root, "D-10R")
            case.begin_conformance(
                root,
                backend="revmux",
                subjects=subjects,
                note="Initial conformance",
            )
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
            self.assertEqual(bundle["convergence"]["review_scope"], "full-stage")
            with self.assertRaises(case.CaseError):
                case.context_bundle(
                    root, "backend", "revmux", "initial", "conformance"
                )

    def test_conformance_clean_initial_is_terminal_and_cannot_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            subjects = prepare_verified_accept_case(root, "D-CF-1")
            first = case.begin_conformance(
                root,
                backend="native",
                subjects=subjects,
                note="One initial conformance assignment",
            )
            repeated = case.begin_conformance(
                root,
                backend="native",
                subjects=subjects,
                note="Runner retry reads the same assignment",
            )
            self.assertEqual(first["assignment_id"], repeated["assignment_id"])
            with self.assertRaisesRegex(case.CaseError, "review_phase=initial"):
                case.context_bundle(
                    root, "test", "native", "final", "conformance"
                )
            run_id, evidence = record_conformance_run(
                root,
                report_name="conformance-initial.md",
                body="# Conformance\n\nPASS\n",
                major=0,
            )
            result = case.record_conformance_review(
                root,
                run_id=run_id,
                decision="pass",
                evidence=evidence,
                findings=[],
                affected_paths=[],
                note="",
            )
            self.assertEqual(result["phase"], "terminal")
            case.set_gate(
                root,
                "project_conformance",
                "pass",
                evidence,
                "",
                subjects,
                run_id,
            )
            pass_plain_final_gates(root, subjects)
            self.assertEqual(case.validate_case(root, True)["status"], "PASS")
            with self.assertRaisesRegex(case.CaseError, "Cannot start conformance"):
                case.begin_conformance(
                    root,
                    backend="native",
                    subjects=subjects,
                    note="Forbidden second initial",
                )

    def test_final_validation_rejects_missing_conformance_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            prepare_verified_accept_case(root, "D-CF-NO-TERMINAL")
            with self.assertRaises(case.CaseError) as raised:
                case.validate_case(root, True)
            self.assertIn("conformance is not terminal PASS", str(raised.exception))

    def test_conformance_rejects_verdict_for_changed_subject(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            subjects = prepare_verified_accept_case(root, "D-CF-STALE")
            case.begin_conformance(
                root,
                backend="native",
                subjects=subjects,
                note="Bind the initial subject",
            )
            run_id, evidence = record_conformance_run(
                root,
                report_name="conformance-stale.md",
                body="# Conformance\n\nPASS for the assigned subject.\n",
                major=0,
            )
            (root / "scope.md").write_text(
                "# Scope\n\nChanged after assignment.\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(case.CaseError, "changed after assignment"):
                case.record_conformance_review(
                    root,
                    run_id=run_id,
                    decision="pass",
                    evidence=evidence,
                    findings=[],
                    affected_paths=[],
                    note="",
                )
            data, _ = case.reconcile_subjects(root)
            self.assertEqual(data["conformance"]["phase"], "user-decision")
            with self.assertRaisesRegex(case.CaseError, "finish the current episode"):
                case.begin_conformance(
                    root,
                    backend="native",
                    subjects=subjects,
                    note="No silent replacement episode",
                )
            decision = root / "reports" / "subject-change-decision.md"
            decision.write_text(
                "# Decision\n\nAccept the changed subject as a distinct baseline.\n",
                encoding="utf-8",
            )
            case.resume_conformance(
                root,
                evidence="reports/subject-change-decision.md",
                impact="baseline",
                note="Explicitly accept the new baseline",
            )
            refresh_verification(
                root, root / "acceptance.md", "verification-new-baseline.md"
            )
            restarted = case.begin_conformance(
                root,
                backend="native",
                subjects=subjects,
                note="Distinct episode after user decision",
            )
            self.assertEqual(restarted["episode"], 2)

    def test_conformance_correction_is_targeted_and_final_stops(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            subjects = prepare_verified_accept_case(root, "D-CF-2")
            case.begin_conformance(
                root,
                backend="revmux",
                subjects=subjects,
                note="Initial conformance",
            )
            run_id, evidence = record_conformance_run(
                root,
                report_name="conformance-initial.md",
                body="# Conformance\n\nCF-001 major\n",
                major=1,
            )
            result = case.record_conformance_review(
                root,
                run_id=run_id,
                decision="revise",
                evidence=evidence,
                findings=["CF-001=major"],
                affected_paths=["src/app.py", "tests/test_app.py"],
                note="Fix one accepted finding",
            )
            self.assertEqual(result["phase"], "remediation")
            with self.assertRaisesRegex(case.CaseError, "not legal from remediation"):
                case.context_bundle(
                    root, "test", "revmux", "final", "conformance"
                )

            case.transition(root, "test", "verifying", "")
            verification = case.begin_verification(
                root,
                subjects=[root / "acceptance.md"],
                note="Affected verification only",
                direct_regressions=["tests/test_app.py"],
            )
            self.assertEqual(
                verification["verification_scope"]["finding_ids"], ["CF-001"]
            )
            correction_report = root / "reports" / "verification-correction.md"
            correction_report.write_text("# Targeted verification\n\nPASS\n", encoding="utf-8")
            verification_run = case.agent_ledger.record_run(
                root,
                role="delivery-tester",
                role_mode="verification",
                model="test-model",
                subject_sha256=verification["subject_sha256"],
                duration_seconds=1,
                retries=0,
                input_bytes=10,
                input_tokens=2,
                output_tokens=2,
                reported_blocker=0,
                reported_major=0,
                reported_minor=0,
                status="completed",
                degraded_reasons=[],
                lenses=["acceptance@1"],
                prompt_artifact="acceptance.md",
                output_artifact="reports/verification-correction.md",
            )
            case.set_gate(
                root,
                "independent_verification",
                "pass",
                "reports/verification-correction.md",
                "",
                [root / "acceptance.md"],
                verification_run,
            )
            case.transition(root, "test", "verified", "")
            case.set_gate(
                root,
                "project_checks",
                "pass",
                "affected project checks pass",
                "",
                [root / "acceptance.md"],
            )
            remediation = root / "reports" / "remediation.md"
            remediation.write_text("# Remediation\n\nCF-001 fixed\n", encoding="utf-8")
            corrected_subjects = [*subjects, correction_report, remediation]
            completed = case.complete_conformance_remediation(
                root,
                evidence="reports/remediation.md",
                subjects=corrected_subjects,
                changed_paths=["src/app.py", "tests/test_app.py"],
                direct_regressions=["tests/test_app.py"],
                note="Bounded correction",
            )
            self.assertEqual(completed["phase"], "final-ready")
            final = case.context_bundle(
                root, "test", "revmux", "final", "conformance"
            )
            self.assertEqual(final["convergence"]["review_scope"], "targeted-remediation")
            self.assertEqual(final["convergence"]["finding_ids"], ["CF-001"])
            final_run, final_evidence = record_conformance_run(
                root,
                report_name="conformance-final.md",
                body="# Final\n\nCF-002 major\n",
                major=1,
            )
            stopped = case.record_conformance_review(
                root,
                run_id=final_run,
                decision="revise",
                evidence=final_evidence,
                findings=["CF-002=major"],
                affected_paths=["src/app.py"],
                note="New gating finding requires user decision",
            )
            self.assertEqual(stopped["phase"], "user-decision")
            with self.assertRaisesRegex(case.CaseError, "current episode"):
                case.begin_conformance(
                    root,
                    backend="revmux",
                    subjects=corrected_subjects,
                    note="Forbidden automatic restart",
                )
            decision = root / "reports" / "user-decision.md"
            decision.write_text(
                "# User decision\n\nScope changed for a distinct episode.\n",
                encoding="utf-8",
            )
            resumed = case.resume_conformance(
                root,
                evidence="reports/user-decision.md",
                impact="scope",
                note="Approved distinct scope episode",
            )
            self.assertEqual(resumed["phase"], "idle")
            refresh_verification(
                root, root / "acceptance.md", "verification-new-scope.md"
            )
            new_episode = case.begin_conformance(
                root,
                backend="revmux",
                subjects=corrected_subjects,
                note="Explicit second episode",
            )
            self.assertEqual(new_episode["episode"], 2)

    def test_failed_conformance_targeted_recheck_stops_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            subjects = prepare_verified_accept_case(root, "D-CF-FAIL")
            case.begin_conformance(
                root, backend="native", subjects=subjects, note="Initial review"
            )
            run_id, evidence = record_conformance_run(
                root,
                report_name="conformance-finding.md",
                body="# Conformance\n\nCF-FAIL major\n",
                major=1,
            )
            case.record_conformance_review(
                root,
                run_id=run_id,
                decision="revise",
                evidence=evidence,
                findings=["CF-FAIL=major"],
                affected_paths=["src/app.py"],
                note="One correction batch",
            )
            case.begin_verification(
                root,
                subjects=[root / "acceptance.md"],
                note="Targeted recheck",
            )
            case.set_gate(
                root,
                "independent_verification",
                "fail",
                "",
                "CF-FAIL remains",
                [],
            )
            _, data = case.load(root)
            self.assertEqual(data["verification"]["status"], "user-decision")
            self.assertEqual(data["conformance"]["phase"], "user-decision")
            with self.assertRaisesRegex(case.CaseError, "awaiting a user decision"):
                case.begin_verification(
                    root,
                    subjects=[root / "acceptance.md"],
                    note="Forbidden retry",
                )

    def test_scope_expansion_has_explicit_user_decision_transition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            subjects = prepare_verified_accept_case(root, "D-CF-SCOPE")
            case.begin_conformance(
                root, backend="native", subjects=subjects, note="Initial review"
            )
            run_id, evidence = record_conformance_run(
                root,
                report_name="conformance-scope.md",
                body="# Conformance\n\nCF-SCOPE major\n",
                major=1,
            )
            case.record_conformance_review(
                root,
                run_id=run_id,
                decision="revise",
                evidence=evidence,
                findings=["CF-SCOPE=major"],
                affected_paths=["src/app.py"],
                note="Initial affected boundary",
            )
            request = root / "reports" / "scope-expansion.md"
            request.write_text(
                "# Scope expansion\n\nThe correction also requires src/helper.py.\n",
                encoding="utf-8",
            )
            result = case.request_conformance_decision(
                root,
                evidence="reports/scope-expansion.md",
                reason="scope-expansion",
                affected_paths=["src/helper.py"],
                note="Correction cannot remain inside the accepted boundary",
            )
            self.assertEqual(result["phase"], "user-decision")
            self.assertEqual(result["decision_reason"]["kind"], "scope-expansion")

    def test_terminal_subject_change_requires_user_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            subjects = prepare_verified_accept_case(root, "D-CF-TERMINAL-STALE")
            case.begin_conformance(
                root, backend="native", subjects=subjects, note="Initial review"
            )
            run_id, evidence = record_conformance_run(
                root,
                report_name="conformance-terminal.md",
                body="# Conformance\n\nPASS\n",
                major=0,
            )
            case.record_conformance_review(
                root,
                run_id=run_id,
                decision="pass",
                evidence=evidence,
                findings=[],
                affected_paths=[],
                note="",
            )
            (root / "conformance.md").write_text(
                "# Codebase conformance\n\nChanged after PASS.\n", encoding="utf-8"
            )
            data, _ = case.reconcile_subjects(root)
            self.assertEqual(data["conformance"]["phase"], "user-decision")
            self.assertEqual(
                data["conformance"]["decision_reason"]["from_phase"], "terminal"
            )

    def test_begin_conformance_rejects_schema_one_or_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            subjects = prepare_verified_accept_case(root, "D-CF-LEGACY")
            manifest = root / "manifest.json"
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["schema_version"] = 2
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(case.CaseError, r"schema-3\+"):
                case.begin_conformance(
                    root,
                    backend="native",
                    subjects=subjects,
                    note="Legacy case must migrate explicitly",
                )

    def test_corrected_final_pass_is_terminal_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            subjects = prepare_verified_accept_case(root, "D-CF-FINAL-PASS")
            case.begin_conformance(
                root, backend="native", subjects=subjects, note="Initial review"
            )
            run_id, evidence = record_conformance_run(
                root,
                report_name="conformance-before-fix.md",
                body="# Conformance\n\nCF-PASS major\n",
                major=1,
            )
            case.record_conformance_review(
                root,
                run_id=run_id,
                decision="revise",
                evidence=evidence,
                findings=["CF-PASS=major"],
                affected_paths=["src/app.py"],
                note="One bounded correction",
            )
            refresh_verification(
                root, root / "acceptance.md", "verification-corrected-pass.md"
            )
            remediation = root / "reports" / "remediation-final-pass.md"
            remediation.write_text(
                "# Remediation\n\nCF-PASS fixed.\n", encoding="utf-8"
            )
            corrected_subjects = [
                *subjects,
                root / "reports" / "verification-corrected-pass.md",
                remediation,
            ]
            case.complete_conformance_remediation(
                root,
                evidence="reports/remediation-final-pass.md",
                subjects=corrected_subjects,
                changed_paths=["src/app.py"],
                direct_regressions=[],
                note="Exact correction delta",
            )
            case.context_bundle(root, "test", "native", "final", "conformance")
            final_run, final_evidence = record_conformance_run(
                root,
                report_name="conformance-after-fix.md",
                body="# Final conformance\n\nPASS\n",
                major=0,
            )
            result = case.record_conformance_review(
                root,
                run_id=final_run,
                decision="pass",
                evidence=final_evidence,
                findings=[],
                affected_paths=[],
                note="",
            )
            self.assertEqual(result["phase"], "terminal")
            case.set_gate(
                root,
                "project_conformance",
                "pass",
                final_evidence,
                "",
                corrected_subjects,
                final_run,
            )
            pass_plain_final_gates(root, corrected_subjects)
            self.assertEqual(case.validate_case(root, True)["status"], "PASS")

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

    def test_verification_rejects_another_full_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "case"
            prepare_context(root, {"test": ["test-design"]})
            case.init_case(root, "D-14", "accept", "demo", ["test"])
            case.begin_verification(
                root,
                subjects=[root / "acceptance.md"],
                note="Initial verification",
            )
            case.set_gate(
                root,
                "independent_verification",
                "fail",
                "",
                "Initial finding",
                [],
            )
            with self.assertRaisesRegex(case.CaseError, "exact findings"):
                case.begin_verification(
                    root,
                    subjects=[root / "acceptance.md"],
                    note="Forbidden full repeat",
                )
            targeted = case.begin_verification(
                root,
                subjects=[root / "acceptance.md"],
                note="One targeted correction verification",
                findings=["VF-001=major"],
                affected_paths=["src/app.py"],
                direct_regressions=["tests/test_app.py"],
            )
            self.assertEqual(
                targeted["verification_scope"]["review_scope"],
                "targeted-remediation",
            )
            case.set_gate(
                root,
                "independent_verification",
                "fail",
                "",
                "Finding remains",
                [],
            )
            with self.assertRaisesRegex(case.CaseError, "user decision|budget exhausted"):
                case.begin_verification(
                    root,
                    subjects=[root / "acceptance.md"],
                    note="Forbidden third verification",
                    findings=["VF-001=major"],
                    affected_paths=["src/app.py"],
                )
            _, data = case.load(root)
            self.assertEqual(data["verification"]["status"], "user-decision")
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
