#!/usr/bin/env python3
"""Persistent case-state manager for Delivery Engineering."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import agent_ledger
from delivery_context import (
    BASIS_DIRECTORY,
    ENGINEERING_CONTEXT_JSON,
    ContextError,
    validate_engineering_context,
)


SCHEMA_VERSION = 3
SUPPORTED_SCHEMAS = {1, 2, SCHEMA_VERSION}
DELIVERY_HANDOFF = "delivery-handoff.json"
DELIVERY_HANDOFF_SCHEMA = 1
MAX_VERIFICATION_ATTEMPTS = 3
CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
INTENTS = {"implement", "accept", "test-design"}
LANES = {"backend", "frontend", "test"}
TEST_ROLE_MODES = {"test-design", "test-automation", "verification", "conformance"}
DEV_LANES = {"backend", "frontend"}
GATES = (
    "authorization",
    "scope",
    "codebase_conformance",
    "lane_reports",
    "project_checks",
    "independent_verification",
    "project_conformance",
    "traceability",
)
GATE_STATUSES = {"pending", "pass", "fail", "not_required", "stale"}
AGENT_BOUND_GATES = {
    "independent_verification": "verification",
    "project_conformance": "project-conformance",
}
DEV_TRANSITIONS = {
    "planned": {"ready", "blocked"},
    "ready": {"in_progress", "blocked"},
    "in_progress": {"implemented", "blocked", "failed"},
    "blocked": {"ready", "in_progress"},
    "failed": {"in_progress"},
    "implemented": {"stale"},
    "stale": {"in_progress"},
}
TEST_TRANSITIONS = {
    "planned": {"designing", "ready", "blocked"},
    "designing": {"designed", "blocked", "failed"},
    "designed": {"ready", "stale"},
    "ready": {"verifying", "blocked"},
    "verifying": {"verified", "failed", "blocked"},
    "verified": {"stale"},
    "blocked": {"designing", "ready", "verifying"},
    "failed": {"designing", "verifying"},
    "stale": {"designing", "ready", "verifying"},
}


class CaseError(RuntimeError):
    """Invalid case operation or invariant."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def manifest_path(root: Path) -> Path:
    return root.expanduser().resolve() / "manifest.json"


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load(root: Path) -> tuple[Path, dict[str, Any]]:
    case_root = root.expanduser().resolve()
    path = manifest_path(case_root)
    if not path.is_file():
        raise CaseError(f"Missing case manifest: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CaseError(f"Invalid case manifest: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") not in SUPPORTED_SCHEMAS:
        raise CaseError("Unsupported case manifest schema")
    return case_root, data


def load_engineering_context(case_root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    metadata_path = case_root / ENGINEERING_CONTEXT_JSON
    if not metadata_path.is_file():
        raise CaseError(f"Missing engineering context: {metadata_path}")
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CaseError(f"Invalid engineering context JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CaseError("Engineering context root must be an object")
    assignments = payload.get("assignments")
    if not isinstance(assignments, dict):
        raise CaseError("Engineering context assignments must be an object")
    contents: dict[str, str] = {}
    for lane in assignments:
        if lane not in LANES:
            raise CaseError(f"Invalid engineering context lane: {lane}")
        path = case_root / BASIS_DIRECTORY / f"{lane}.md"
        if not path.is_file():
            raise CaseError(f"Missing engineering basis: {path}")
        contents[lane] = path.read_text(encoding="utf-8")
    return payload, contents


def engineering_binding(payload: dict[str, Any]) -> dict[str, Any]:
    assignments = payload["assignments"]
    return {
        "metadata_path": ENGINEERING_CONTEXT_JSON,
        "fingerprint": payload["fingerprint"],
        "assignments": {
            lane: {
                "route_ids": item["route_ids"],
                "content_path": item["content_path"],
                "content_sha256": item["content_sha256"],
            }
            for lane, item in assignments.items()
        },
    }


def subject_entry(case_root: Path, path: Path) -> str:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise CaseError(f"Subject is not a file: {resolved}")
    try:
        return f"case:{resolved.relative_to(case_root).as_posix()}"
    except ValueError:
        return f"absolute:{resolved}"


def resolve_subject(case_root: Path, entry: str) -> Path:
    if entry.startswith("case:"):
        candidate = (case_root / entry.removeprefix("case:")).resolve()
        try:
            candidate.relative_to(case_root)
        except ValueError as exc:
            raise CaseError(f"Case subject escapes root: {entry}") from exc
        return candidate
    if entry.startswith("absolute:"):
        return Path(entry.removeprefix("absolute:")).resolve()
    raise CaseError(f"Invalid subject entry: {entry}")


def fingerprint(case_root: Path, entries: list[str]) -> str:
    digest = hashlib.sha256()
    for entry in sorted(entries):
        path = resolve_subject(case_root, entry)
        if not path.is_file():
            raise CaseError(f"Gate subject missing: {path}")
        digest.update(entry.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_delivery_handoff(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaseError(f"Invalid delivery handoff: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != DELIVERY_HANDOFF_SCHEMA:
        raise CaseError("Delivery handoff must be a schema-1 object")
    if not isinstance(payload.get("case_id"), str) or not payload["case_id"].strip():
        raise CaseError("Delivery handoff requires case_id")
    revision = payload.get("spec_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise CaseError("Delivery handoff requires positive spec_revision")
    for field in ("spec_fingerprint", "acceptance_fingerprint"):
        value = payload.get(field)
        if not isinstance(value, str) or not agent_ledger.SHA256_RE.fullmatch(value):
            raise CaseError(f"Delivery handoff has invalid {field}")
    transition = payload.get("implementation_transition")
    if not isinstance(transition, dict) or transition.get("mode") not in {
        "evolve-in-place",
        "replace-and-remove",
        "staged-migration",
    }:
        raise CaseError("Delivery handoff requires implementation_transition")
    return payload


def source_revision(data: dict[str, Any]) -> str:
    binding = data.get("source_handoff")
    if isinstance(binding, dict):
        return f"vigers:{binding.get('case_id')}@{binding.get('spec_revision')}"
    return "standalone:1"


def agent_run(case_root: Path, run_id: str) -> dict[str, Any]:
    try:
        _, payload = agent_ledger.load(case_root)
    except agent_ledger.LedgerError as exc:
        raise CaseError(str(exc)) from exc
    matches = [
        item
        for item in payload.get("runs", [])
        if isinstance(item, dict) and item.get("run_id") == run_id
    ]
    if len(matches) != 1:
        raise CaseError(f"Agent run not found: {run_id}")
    return matches[0]


def validate_agent_gate_binding(
    case_root: Path,
    gate: str,
    run_id: str,
    subject_sha256: str,
    evidence: str,
) -> dict[str, str]:
    run = agent_run(case_root, run_id)
    if run.get("role") != "delivery-tester":
        raise CaseError(f"{gate} requires a delivery-tester run")
    if run.get("role_mode") != AGENT_BOUND_GATES[gate]:
        raise CaseError(
            f"{gate} requires role_mode={AGENT_BOUND_GATES[gate]}, "
            f"got {run.get('role_mode')}"
        )
    if run.get("status") != "completed":
        raise CaseError(f"{gate} requires a completed agent run")
    if run.get("subject_sha256") != subject_sha256:
        raise CaseError(f"{gate} agent run is bound to another subject")
    output = (run.get("artifacts") or {}).get("output")
    if not isinstance(output, dict) or output.get("ref") != evidence:
        raise CaseError(f"{gate} evidence must be the exact agent output artifact")
    output_path = case_root / evidence
    if not output_path.is_file() or file_sha256(output_path) != output.get("sha256"):
        raise CaseError(f"{gate} agent output artifact is missing or changed")
    return {"run_id": run_id, "output_sha256": str(output["sha256"])}


def status_text(data: dict[str, Any]) -> str:
    lines = [
        f"# Delivery case {data['case_id']}",
        "",
        f"- intent: `{data['intent']}`",
        f"- profile: `{data['profile_id']}`",
        f"- revision: `{data['revision']}`",
        f"- source revision: `{source_revision(data)}`",
        "- verification attempts: "
        f"`{data.get('verification', {}).get('attempts', 0)}/"
        f"{data.get('verification', {}).get('max_attempts', MAX_VERIFICATION_ATTEMPTS)}`",
        "- engineering context: `recorded`"
        if data.get("engineering_context")
        else "- engineering context: `legacy-unrecorded`",
        "",
        "## Lanes",
        "",
    ]
    for lane, item in data["lanes"].items():
        lines.append(f"- `{lane}`: `{item['state']}`")
    lines.extend(["", "## Gates", ""])
    for gate, item in data["gates"].items():
        lines.append(f"- `{gate}`: `{item['status']}`")
    return "\n".join(lines) + "\n"


def save(case_root: Path, data: dict[str, Any], event: dict[str, Any]) -> None:
    data["revision"] += 1
    data["updated_at"] = now()
    event = {"at": data["updated_at"], **event}
    data.setdefault("history", []).append(event)
    atomic_json(case_root / "manifest.json", data)
    (case_root / "status.md").write_text(status_text(data), encoding="utf-8")


def init_case(
    root: Path,
    case_id: str,
    intent: str,
    profile_id: str,
    lanes: list[str],
    allow_unrecorded_engineering_context: bool = False,
) -> dict[str, Any]:
    if not CASE_ID_RE.fullmatch(case_id):
        raise CaseError(f"Invalid case id: {case_id!r}")
    if intent not in INTENTS:
        raise CaseError(f"Unknown intent: {intent}")
    unique_lanes = list(dict.fromkeys(lanes))
    if len(unique_lanes) != len(lanes) or not unique_lanes:
        raise CaseError("Lanes must be a non-empty unique list")
    unknown = set(unique_lanes) - LANES
    if unknown:
        raise CaseError(f"Unknown lanes: {', '.join(sorted(unknown))}")
    if "test" not in unique_lanes:
        raise CaseError("test lane is mandatory")
    if intent == "implement" and not set(unique_lanes) & DEV_LANES:
        raise CaseError("implement requires backend and/or frontend lane")
    if intent != "implement" and set(unique_lanes) & DEV_LANES:
        raise CaseError(f"{intent} cannot contain developer lanes")

    case_root = root.expanduser().resolve()
    case_root.mkdir(parents=True, exist_ok=True)
    expected_basis = {Path(BASIS_DIRECTORY) / f"{lane}.md" for lane in unique_lanes}
    existing_files = {
        path.relative_to(case_root)
        for path in case_root.rglob("*")
        if path.is_file()
    }
    allowed_files = {
        Path(ENGINEERING_CONTEXT_JSON),
        Path(DELIVERY_HANDOFF),
        *expected_basis,
    }
    unexpected = existing_files - allowed_files
    if unexpected:
        raise CaseError(
            "Case root contains unexpected files before init: "
            + ", ".join(sorted(path.as_posix() for path in unexpected))
        )
    context_present = (case_root / ENGINEERING_CONTEXT_JSON).is_file()
    basis_present = {path for path in expected_basis if (case_root / path).is_file()}
    if context_present or basis_present:
        if not context_present or basis_present != expected_basis:
            raise CaseError("Engineering context is partial or does not cover every active lane")
        try:
            context_payload, context_contents = load_engineering_context(case_root)
            validate_engineering_context(
                context_payload,
                context_contents,
                expected_lanes=set(unique_lanes),
                verify_sources=True,
            )
        except ContextError as exc:
            raise CaseError(f"Invalid engineering context: {exc}") from exc
        context_binding: dict[str, Any] | None = engineering_binding(context_payload)
    elif allow_unrecorded_engineering_context:
        context_binding = None
    else:
        raise CaseError(
            "New case requires engineering-context.json and basis/<lane>.md; "
            "run delivery_context.py materialize first"
        )
    handoff_path = case_root / DELIVERY_HANDOFF
    if handoff_path.is_file():
        handoff = load_delivery_handoff(handoff_path)
        source_handoff: dict[str, Any] | None = {
            "path": DELIVERY_HANDOFF,
            "sha256": file_sha256(handoff_path),
            "case_id": handoff["case_id"],
            "spec_revision": handoff["spec_revision"],
            "spec_fingerprint": handoff["spec_fingerprint"],
            "acceptance_fingerprint": handoff["acceptance_fingerprint"],
        }
    else:
        source_handoff = None
    (case_root / "lanes").mkdir()
    (case_root / "reports").mkdir()
    agent_ledger.create(case_root, case_id)

    created = now()
    gates = {
        gate: {"status": "pending", "evidence": "", "note": "", "subjects": [], "fingerprint": ""}
        for gate in GATES
    }
    if intent == "test-design":
        for gate in ("project_checks", "independent_verification", "project_conformance"):
            gates[gate].update(status="not_required", note="intent test-design")
    data: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "intent": intent,
        "profile_id": profile_id,
        "engineering_context": context_binding,
        "source_handoff": source_handoff,
        "legacy_unrecorded_engineering_context": context_binding is None,
        "revision": 1,
        "created_at": created,
        "updated_at": created,
        "lanes": {lane: {"state": "planned", "note": "", "updated_at": created} for lane in unique_lanes},
        "gates": gates,
        "verification": {
            "source_revision": (
                f"vigers:{source_handoff['case_id']}@{source_handoff['spec_revision']}"
                if source_handoff
                else "standalone:1"
            ),
            "attempts": 0,
            "max_attempts": MAX_VERIFICATION_ATTEMPTS,
            "status": "pending",
            "current_subject_sha256": None,
            "feedback_batch": None,
        },
        "history": [
            {
                "at": created,
                "type": "init",
                "intent": intent,
                "lanes": unique_lanes,
                "engineering_context_fingerprint": (
                    context_binding["fingerprint"] if context_binding else None
                ),
                "source_revision": (
                    f"vigers:{source_handoff['case_id']}@{source_handoff['spec_revision']}"
                    if source_handoff
                    else "standalone:1"
                ),
            }
        ],
    }
    for filename, title in (
        ("scope.md", "Scope"),
        ("acceptance.md", "Acceptance basis"),
        ("conformance.md", "Codebase conformance"),
        ("evidence.md", "Evidence"),
        ("decisions.md", "Decisions"),
    ):
        (case_root / filename).write_text(f"# {title}\n\n<!-- fill and keep source revisions -->\n", encoding="utf-8")
    for lane in unique_lanes:
        (case_root / "lanes" / f"{lane}.md").write_text(
            f"# Lane: {lane}\n\n- assigned IDs:\n- target/baseline:\n- file boundary:\n- dependencies:\n- required checks:\n- forbidden actions:\n",
            encoding="utf-8",
        )
    atomic_json(case_root / "manifest.json", data)
    (case_root / "status.md").write_text(status_text(data), encoding="utf-8")
    return data


def transition(root: Path, lane: str, target: str, note: str) -> dict[str, Any]:
    case_root, data = load(root)
    if lane not in data["lanes"]:
        raise CaseError(f"Lane is not active: {lane}")
    current = data["lanes"][lane]["state"]
    allowed = TEST_TRANSITIONS if lane == "test" else DEV_TRANSITIONS
    if target not in allowed.get(current, set()):
        raise CaseError(f"Invalid {lane} transition: {current} -> {target}")
    if target in {"blocked", "failed", "stale"} and not note.strip():
        raise CaseError(f"Transition to {target} requires --note")
    data["lanes"][lane] = {"state": target, "note": note.strip(), "updated_at": now()}
    save(case_root, data, {"type": "lane-transition", "lane": lane, "from": current, "to": target, "note": note.strip()})
    return data


def reconcile_subjects(root: Path) -> tuple[dict[str, Any], list[str]]:
    """Persist effective stale state before status, context, or validation."""
    case_root, data = load(root)
    stale: list[str] = []
    for gate, item in data.get("gates", {}).items():
        if not isinstance(item, dict) or item.get("status") != "pass":
            continue
        try:
            current = fingerprint(case_root, item.get("subjects", []))
        except CaseError:
            current = "missing"
        if not item.get("fingerprint") or current != item.get("fingerprint"):
            item["status"] = "stale"
            item["note"] = "subject changed after PASS"
            item["current_fingerprint"] = current
            stale.append(gate)
    if stale:
        test_lane = data.get("lanes", {}).get("test")
        if isinstance(test_lane, dict) and test_lane.get("state") == "verified":
            test_lane.update(
                state="stale",
                note="verification subject changed",
                updated_at=now(),
            )
        verification = data.get("verification")
        if isinstance(verification, dict):
            verification["status"] = "stale"
        save(
            case_root,
            data,
            {"type": "subject-reconciled", "stale_gates": sorted(stale)},
        )
    return data, stale


def begin_verification(
    root: Path,
    *,
    subjects: list[Path],
    note: str,
) -> dict[str, Any]:
    """Open one bounded verification assignment for the exact current subject."""
    case_root, data = load(root)
    if data.get("schema_version") != SCHEMA_VERSION:
        raise CaseError("Bounded verification requires a schema-3 delivery case")
    verification = data.get("verification")
    if not isinstance(verification, dict):
        raise CaseError("Verification state is missing")
    if verification.get("source_revision") != source_revision(data):
        raise CaseError("Verification source revision is stale")
    if verification.get("status") == "running":
        raise CaseError("Current verification assignment is still running")
    attempts = verification.get("attempts")
    maximum = verification.get("max_attempts", MAX_VERIFICATION_ATTEMPTS)
    if not isinstance(attempts, int) or not isinstance(maximum, int):
        raise CaseError("Verification attempt counters are invalid")
    if attempts >= maximum:
        verification["status"] = "feedback_required"
        data["lanes"]["test"].update(
            state="blocked",
            note="verification budget exhausted; aggregate one spec-feedback batch",
            updated_at=now(),
        )
        save(
            case_root,
            data,
            {"type": "verification-budget-exhausted", "attempts": attempts},
        )
        raise CaseError(
            "Verification budget exhausted after three assignments; aggregate one "
            "spec-feedback batch or record a user decision instead of another full pass"
        )
    if not subjects:
        raise CaseError("Verification requires at least one subject")
    entries = [subject_entry(case_root, path) for path in subjects]
    subject_sha256 = fingerprint(case_root, entries)
    verification.update(
        attempts=attempts + 1,
        status="running",
        current_subject_sha256=subject_sha256,
        current_subjects=entries,
        note=note.strip(),
    )
    save(
        case_root,
        data,
        {
            "type": "verification-started",
            "attempt": attempts + 1,
            "source_revision": verification["source_revision"],
            "subject_sha256": subject_sha256,
        },
    )
    return {
        "attempt": attempts + 1,
        "max_attempts": maximum,
        "source_revision": verification["source_revision"],
        "subject_sha256": subject_sha256,
    }


def record_feedback_batch(
    root: Path,
    *,
    gaps: list[str],
    evidence: list[Path],
    note: str,
) -> dict[str, Any]:
    """Freeze all accepted spec gaps for one immutable Vigers source revision."""
    case_root, data = load(root)
    source = data.get("source_handoff")
    verification = data.get("verification")
    if not isinstance(source, dict):
        raise CaseError("Spec feedback requires a bound Vigers delivery handoff")
    if not isinstance(verification, dict) or verification.get("attempts", 0) < 1:
        raise CaseError("Spec feedback requires at least one verification assignment")
    if verification.get("feedback_batch") is not None:
        raise CaseError("This source revision already has a feedback batch")
    normalized_gaps = [item.strip() for item in gaps if item.strip()]
    if not normalized_gaps or len(normalized_gaps) != len(set(normalized_gaps)):
        raise CaseError("Feedback gaps must be a non-empty unique list")
    evidence_entries = [subject_entry(case_root, path) for path in evidence]
    if not evidence_entries:
        raise CaseError("Feedback batch requires evidence")
    feedback_dir = case_root / "feedback-batches"
    feedback_dir.mkdir(exist_ok=True)
    batch_id = f"FB-{source['spec_revision']:03d}-001"
    relative = f"feedback-batches/{batch_id}.json"
    path = case_root / relative
    if path.exists():
        raise CaseError(f"Feedback batch already exists: {batch_id}")
    payload = {
        "schema": 1,
        "batch_id": batch_id,
        "batch_complete": True,
        "delivery_case_id": data["case_id"],
        "target_vigers_case_id": source["case_id"],
        "target_spec_revision": source["spec_revision"],
        "target_spec_fingerprint": source["spec_fingerprint"],
        "verification_attempts": verification["attempts"],
        "verification_subject_sha256": verification.get("current_subject_sha256"),
        "accepted_spec_gaps": normalized_gaps,
        "evidence": [
            {"entry": entry, "sha256": file_sha256(resolve_subject(case_root, entry))}
            for entry in evidence_entries
        ],
        "note": note.strip(),
        "created_at": now(),
    }
    atomic_json(path, payload)
    binding = {"ref": relative, "sha256": file_sha256(path), "batch_id": batch_id}
    verification.update(status="feedback_required", feedback_batch=binding)
    data["lanes"]["test"].update(
        state="blocked",
        note="one complete spec-feedback batch awaits a new source revision",
        updated_at=now(),
    )
    save(
        case_root,
        data,
        {
            "type": "spec-feedback-recorded",
            "batch_id": batch_id,
            "target_spec_revision": source["spec_revision"],
        },
    )
    return payload


def migrate_source_handoff(root: Path, *, handoff: Path, note: str) -> dict[str, Any]:
    """Advance a blocked Delivery case to one newer immutable Vigers revision."""
    case_root, data = load(root)
    current = data.get("source_handoff")
    verification = data.get("verification")
    if not isinstance(current, dict):
        raise CaseError("Source migration requires an existing Vigers handoff")
    if not isinstance(verification, dict) or verification.get("feedback_batch") is None:
        raise CaseError("Source migration requires one recorded feedback batch")
    source_path = handoff.expanduser().resolve()
    target_path = case_root / DELIVERY_HANDOFF
    if source_path == target_path:
        raise CaseError("New handoff must be supplied as a separate immutable file")
    payload = load_delivery_handoff(source_path)
    if payload["case_id"] != current.get("case_id"):
        raise CaseError("New handoff belongs to another Vigers case")
    if payload["spec_revision"] <= current.get("spec_revision", 0):
        raise CaseError("New handoff revision must increase")
    if not note.strip():
        raise CaseError("Source migration requires a note")
    if not target_path.is_file() or file_sha256(target_path) != current.get("sha256"):
        raise CaseError("Current delivery handoff changed after binding")
    feedback_binding = verification["feedback_batch"]
    feedback_path = case_root / str(feedback_binding.get("ref", ""))
    if (
        not feedback_path.is_file()
        or file_sha256(feedback_path) != feedback_binding.get("sha256")
    ):
        raise CaseError("Recorded feedback batch changed after binding")
    archive_dir = case_root / "source-handoffs"
    archive_dir.mkdir(exist_ok=True)
    archive = archive_dir / f"{current['case_id']}-r{current['spec_revision']}.json"
    if archive.exists():
        raise CaseError(f"Source handoff archive already exists: {archive.name}")
    shutil.copyfile(target_path, archive)
    shutil.copyfile(source_path, target_path)
    data["source_handoff"] = {
        "path": DELIVERY_HANDOFF,
        "sha256": file_sha256(target_path),
        "case_id": payload["case_id"],
        "spec_revision": payload["spec_revision"],
        "spec_fingerprint": payload["spec_fingerprint"],
        "acceptance_fingerprint": payload["acceptance_fingerprint"],
    }
    data["verification"] = {
        "source_revision": source_revision(data),
        "attempts": 0,
        "max_attempts": MAX_VERIFICATION_ATTEMPTS,
        "status": "pending",
        "current_subject_sha256": None,
        "feedback_batch": None,
    }
    for gate, item in data.get("gates", {}).items():
        if gate != "authorization" and item.get("status") == "pass":
            item.update(status="stale", note="Vigers source revision advanced")
    for lane, item in data.get("lanes", {}).items():
        if lane in DEV_LANES and item.get("state") == "implemented":
            item.update(state="stale", note="Vigers source revision advanced", updated_at=now())
        elif lane == "test" and item.get("state") not in {"planned", "stale"}:
            item.update(state="stale", note="Vigers source revision advanced", updated_at=now())
    save(
        case_root,
        data,
        {
            "type": "source-handoff-migrated",
            "from_revision": current["spec_revision"],
            "to_revision": payload["spec_revision"],
            "archive": archive.relative_to(case_root).as_posix(),
            "note": note.strip(),
        },
    )
    return {
        "case_id": data["case_id"],
        "source_revision": source_revision(data),
        "archived": archive.relative_to(case_root).as_posix(),
    }


def set_gate(
    root: Path,
    gate: str,
    status: str,
    evidence: str,
    note: str,
    subjects: list[Path],
    agent_run_id: str | None = None,
) -> dict[str, Any]:
    case_root, data = load(root)
    if gate not in GATES:
        raise CaseError(f"Unknown gate: {gate}")
    if status not in GATE_STATUSES - {"pending", "stale"}:
        raise CaseError("Gate can be explicitly set only to pass, fail or not_required")
    if status == "pass" and (not evidence.strip() or not subjects):
        raise CaseError("pass requires --evidence and at least one --subject")
    if status == "not_required" and not note.strip():
        raise CaseError("not_required requires --note")
    entries = [subject_entry(case_root, path) for path in subjects]
    subject_sha256 = fingerprint(case_root, entries) if entries else ""
    run_binding: dict[str, str] | None = None
    if (
        status == "pass"
        and gate in AGENT_BOUND_GATES
        and data.get("schema_version") == SCHEMA_VERSION
    ):
        if not isinstance(agent_run_id, str) or not agent_run_id.strip():
            raise CaseError(f"{gate} PASS requires --agent-run")
        verification = data.get("verification")
        if gate == "independent_verification" and (
            not isinstance(verification, dict)
            or verification.get("status") != "running"
            or verification.get("current_subject_sha256") != subject_sha256
        ):
            raise CaseError(
                "independent_verification PASS requires a current begin-verification assignment"
            )
        run_binding = validate_agent_gate_binding(
            case_root,
            gate,
            agent_run_id.strip(),
            subject_sha256,
            evidence.strip(),
        )
    data["gates"][gate] = {
        "status": status,
        "evidence": evidence.strip(),
        "note": note.strip(),
        "subjects": entries,
        "fingerprint": subject_sha256,
        **({"agent_run": run_binding} if run_binding is not None else {}),
    }
    if status == "pass" and gate == "independent_verification" and run_binding:
        data["verification"]["status"] = "passed"
    elif status == "fail" and gate == "independent_verification":
        data["verification"]["status"] = "failed"
    save(case_root, data, {"type": "gate", "gate": gate, "status": status, "note": note.strip()})
    return data


def validate_case(root: Path, final: bool) -> dict[str, Any]:
    data, reconciled_stale = reconcile_subjects(root)
    case_root = root.expanduser().resolve()
    errors: list[str] = []
    active = set(data.get("lanes", {}))
    if "test" not in active:
        errors.append("test lane is missing")
    if data.get("intent") == "implement" and not active & DEV_LANES:
        errors.append("implement requires a developer lane")
    if data.get("intent") != "implement" and active & DEV_LANES:
        errors.append(f"{data.get('intent')} contains a developer lane")
    binding = data.get("engineering_context")
    if binding is None:
        if data.get("schema_version") == SCHEMA_VERSION and not data.get(
            "legacy_unrecorded_engineering_context"
        ):
            errors.append("engineering context is missing")
    elif not isinstance(binding, dict):
        errors.append("engineering context binding must be an object")
    else:
        try:
            payload, contents = load_engineering_context(case_root)
            validate_engineering_context(
                payload, contents, expected_lanes=active, verify_sources=False
            )
            expected_binding = engineering_binding(payload)
            if binding != expected_binding:
                errors.append("engineering context does not match manifest binding")
        except (CaseError, ContextError) as exc:
            errors.append(f"engineering context: {exc}")
    source = data.get("source_handoff")
    if isinstance(source, dict):
        handoff_path = case_root / str(source.get("path", ""))
        try:
            handoff = load_delivery_handoff(handoff_path)
            if file_sha256(handoff_path) != source.get("sha256"):
                errors.append("delivery handoff changed after binding")
            if handoff.get("spec_revision") != source.get("spec_revision"):
                errors.append("delivery handoff revision differs from manifest")
        except CaseError as exc:
            errors.append(str(exc))
    verification = data.get("verification")
    if isinstance(verification, dict) and isinstance(
        verification.get("feedback_batch"), dict
    ):
        feedback_binding = verification["feedback_batch"]
        feedback_path = case_root / str(feedback_binding.get("ref", ""))
        if (
            not feedback_path.is_file()
            or file_sha256(feedback_path) != feedback_binding.get("sha256")
        ):
            errors.append("recorded feedback batch changed after binding")
    for lane in active:
        if lane not in LANES:
            errors.append(f"unknown lane in manifest: {lane}")
        if not (case_root / "lanes" / f"{lane}.md").is_file():
            errors.append(f"missing lane card: {lane}")
    stale: list[str] = list(reconciled_stale)
    for gate, item in data.get("gates", {}).items():
        if gate not in GATES:
            errors.append(f"unknown gate in manifest: {gate}")
            continue
        if item.get("status") == "pass":
            try:
                current = fingerprint(case_root, item.get("subjects", []))
                if not item.get("fingerprint") or current != item["fingerprint"]:
                    stale.append(gate)
            except CaseError as exc:
                errors.append(f"{gate}: {exc}")
        if (
            item.get("status") == "pass"
            and gate in AGENT_BOUND_GATES
            and data.get("schema_version") == SCHEMA_VERSION
        ):
            binding = item.get("agent_run")
            if not isinstance(binding, dict) or not isinstance(binding.get("run_id"), str):
                errors.append(f"{gate}: PASS has no agent-run binding")
            else:
                try:
                    expected = validate_agent_gate_binding(
                        case_root,
                        gate,
                        binding["run_id"],
                        str(item.get("fingerprint", "")),
                        str(item.get("evidence", "")),
                    )
                    if expected != binding:
                        errors.append(f"{gate}: agent-run binding differs from ledger")
                except CaseError as exc:
                    errors.append(f"{gate}: {exc}")
    if data.get("schema_version") == SCHEMA_VERSION:
        try:
            _, ledger = agent_ledger.load(case_root)
            errors.extend(
                f"agent ledger: {item}"
                for item in agent_ledger.validate(
                    ledger,
                    case_id=str(data.get("case_id")),
                    root=case_root,
                )
            )
        except agent_ledger.LedgerError as exc:
            errors.append(f"agent ledger: {exc}")
    if stale:
        errors.append(f"stale gate subjects: {', '.join(stale)}")
    if final:
        intent = data.get("intent")
        for lane, item in data["lanes"].items():
            expected = "designed" if intent == "test-design" and lane == "test" else (
                "verified" if lane == "test" else "implemented"
            )
            if item.get("state") != expected:
                errors.append(f"lane {lane} must be {expected}, got {item.get('state')}")
        for gate in GATES:
            status = data.get("gates", {}).get(gate, {}).get("status")
            if status not in {"pass", "not_required"}:
                errors.append(f"gate {gate} is {status}")
            if status == "not_required" and intent != "test-design":
                errors.append(f"gate {gate} cannot be not_required for {intent}")
    if errors:
        raise CaseError("\n".join(f"- {error}" for error in errors))
    return {
        "case_id": data["case_id"],
        "intent": data["intent"],
        "revision": data["revision"],
        "lanes": {lane: item["state"] for lane, item in data["lanes"].items()},
        "final": final,
        "status": "PASS",
    }


def context_bundle(
    root: Path,
    lane: str,
    review_backend: str = "native",
    review_phase: str | None = None,
    role_mode: str | None = None,
) -> dict[str, Any]:
    validate_case(root, False)
    case_root, data = load(root)
    if lane not in data["lanes"]:
        raise CaseError(f"Lane is not active: {lane}")
    if review_backend not in {"native", "revmux"}:
        raise CaseError(f"Unknown review backend: {review_backend}")
    if review_backend == "revmux":
        if lane != "test":
            raise CaseError("revmux review backend is available only to the test lane")
        if role_mode != "conformance":
            raise CaseError("revmux review backend requires role_mode=conformance")
        if review_phase not in {"initial", "final"}:
            raise CaseError("revmux backend requires review_phase=initial|final")
    elif review_phase is not None:
        raise CaseError("review_phase is valid only with review_backend=revmux")
    if role_mode is not None:
        if lane != "test" or role_mode not in TEST_ROLE_MODES:
            raise CaseError("role_mode is valid only for a supported test-lane mode")
    binding = data.get("engineering_context")
    if not isinstance(binding, dict):
        raise CaseError("Lane context requires recorded engineering context")
    lane_binding = binding.get("assignments", {}).get(lane)
    if not isinstance(lane_binding, dict):
        raise CaseError(f"Engineering context is missing lane: {lane}")
    allowed = [
        "manifest.json",
        "scope.md",
        "acceptance.md",
        "conformance.md",
        "evidence.md",
        "decisions.md",
        f"lanes/{lane}.md",
        ENGINEERING_CONTEXT_JSON,
        lane_binding["content_path"],
    ]
    if lane == "test":
        allowed.extend(
            f"reports/{developer}.md"
            for developer in ("backend", "frontend")
            if (case_root / "reports" / f"{developer}.md").is_file()
        )
    elif (case_root / "reports" / "test-design.md").is_file():
        allowed.append("reports/test-design.md")
    role = "delivery-tester" if lane == "test" else f"delivery-{lane}"
    return {
        "case_id": data["case_id"],
        "intent": data["intent"],
        "lane": lane,
        "role": role,
        "role_mode": role_mode,
        "review_backend": review_backend,
        "review_phase": review_phase,
        "revmux_profile": (
            "comprehensive"
            if review_backend == "revmux" and review_phase == "initial"
            else (
                "final"
                if review_backend == "revmux" and review_phase == "final"
                else None
            )
        ),
        "covered_gates": ["project_conformance"] if role_mode == "conformance" else [],
        "contract_inputs": [
            "agents/contracts/tester.md" if lane == "test" else f"agents/contracts/{lane}.md",
            *(
                ["references/revmux-review-backend.md"]
                if review_backend == "revmux"
                else []
            ),
        ],
        "basis_routes": lane_binding["route_ids"],
        "allowed_inputs": allowed,
        "external_inputs": [
            "resolved project profile and nearest repository instructions",
            "target repository/worktree at the recorded baseline",
        ],
        "excluded": [
            "parent-chat reasoning",
            "basis files of other lanes",
            "unrelated reports and repository files",
            "external write authority not present in the lane card",
        ],
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--case-root", type=Path, required=True)
    init.add_argument("--case-id", required=True)
    init.add_argument("--intent", choices=sorted(INTENTS), required=True)
    init.add_argument("--profile-id", required=True)
    init.add_argument("--lane", action="append", choices=sorted(LANES), required=True)
    init.add_argument("--allow-unrecorded-engineering-context", action="store_true")
    show = commands.add_parser("show")
    show.add_argument("--case-root", type=Path, required=True)
    context = commands.add_parser("context")
    context.add_argument("--case-root", type=Path, required=True)
    context.add_argument("--lane", choices=sorted(LANES), required=True)
    context.add_argument(
        "--review-backend",
        choices=("native", "revmux"),
        default="native",
    )
    context.add_argument("--review-phase", choices=("initial", "final"))
    context.add_argument("--role-mode", choices=sorted(TEST_ROLE_MODES))
    move = commands.add_parser("transition")
    move.add_argument("--case-root", type=Path, required=True)
    move.add_argument("--lane", choices=sorted(LANES), required=True)
    move.add_argument("--to", required=True)
    move.add_argument("--note", default="")
    gate = commands.add_parser("set-gate")
    gate.add_argument("--case-root", type=Path, required=True)
    gate.add_argument("--gate", choices=GATES, required=True)
    gate.add_argument("--status", choices=("pass", "fail", "not_required"), required=True)
    gate.add_argument("--evidence", default="")
    gate.add_argument("--note", default="")
    gate.add_argument("--subject", type=Path, action="append", default=[])
    gate.add_argument("--agent-run")
    verify = commands.add_parser("begin-verification")
    verify.add_argument("--case-root", type=Path, required=True)
    verify.add_argument("--subject", type=Path, action="append", required=True)
    verify.add_argument("--note", default="")
    feedback = commands.add_parser("record-feedback")
    feedback.add_argument("--case-root", type=Path, required=True)
    feedback.add_argument("--gap", action="append", required=True)
    feedback.add_argument("--evidence", type=Path, action="append", required=True)
    feedback.add_argument("--note", default="")
    migrate = commands.add_parser("migrate-source-handoff")
    migrate.add_argument("--case-root", type=Path, required=True)
    migrate.add_argument("--handoff", type=Path, required=True)
    migrate.add_argument("--note", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--case-root", type=Path, required=True)
    validate.add_argument("--final", action="store_true")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "init":
            result = init_case(
                args.case_root,
                args.case_id,
                args.intent,
                args.profile_id,
                args.lane,
                args.allow_unrecorded_engineering_context,
            )
        elif args.command == "show":
            result, _ = reconcile_subjects(args.case_root)
        elif args.command == "context":
            result = context_bundle(
                args.case_root,
                args.lane,
                args.review_backend,
                args.review_phase,
                args.role_mode,
            )
        elif args.command == "transition":
            result = transition(args.case_root, args.lane, args.to, args.note)
        elif args.command == "set-gate":
            result = set_gate(
                args.case_root,
                args.gate,
                args.status,
                args.evidence,
                args.note,
                args.subject,
                args.agent_run,
            )
        elif args.command == "begin-verification":
            result = begin_verification(
                args.case_root,
                subjects=args.subject,
                note=args.note,
            )
        elif args.command == "record-feedback":
            result = record_feedback_batch(
                args.case_root,
                gaps=args.gap,
                evidence=args.evidence,
                note=args.note,
            )
        elif args.command == "migrate-source-handoff":
            result = migrate_source_handoff(
                args.case_root,
                handoff=args.handoff,
                note=args.note,
            )
        else:
            result = validate_case(args.case_root, args.final)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, CaseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
