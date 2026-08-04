#!/usr/bin/env python3
"""Persistent case-state manager for Delivery Engineering."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from delivery_context import (
    BASIS_DIRECTORY,
    ENGINEERING_CONTEXT_JSON,
    ContextError,
    validate_engineering_context,
)


SCHEMA_VERSION = 2
SUPPORTED_SCHEMAS = {1, SCHEMA_VERSION}
CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
INTENTS = {"implement", "accept", "test-design"}
LANES = {"backend", "frontend", "test"}
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


def status_text(data: dict[str, Any]) -> str:
    lines = [
        f"# Delivery case {data['case_id']}",
        "",
        f"- intent: `{data['intent']}`",
        f"- profile: `{data['profile_id']}`",
        f"- revision: `{data['revision']}`",
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
    allowed_files = {Path(ENGINEERING_CONTEXT_JSON), *expected_basis}
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
    (case_root / "lanes").mkdir()
    (case_root / "reports").mkdir()

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
        "legacy_unrecorded_engineering_context": context_binding is None,
        "revision": 1,
        "created_at": created,
        "updated_at": created,
        "lanes": {lane: {"state": "planned", "note": "", "updated_at": created} for lane in unique_lanes},
        "gates": gates,
        "history": [
            {
                "at": created,
                "type": "init",
                "intent": intent,
                "lanes": unique_lanes,
                "engineering_context_fingerprint": (
                    context_binding["fingerprint"] if context_binding else None
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


def set_gate(
    root: Path,
    gate: str,
    status: str,
    evidence: str,
    note: str,
    subjects: list[Path],
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
    data["gates"][gate] = {
        "status": status,
        "evidence": evidence.strip(),
        "note": note.strip(),
        "subjects": entries,
        "fingerprint": fingerprint(case_root, entries) if entries else "",
    }
    save(case_root, data, {"type": "gate", "gate": gate, "status": status, "note": note.strip()})
    return data


def validate_case(root: Path, final: bool) -> dict[str, Any]:
    case_root, data = load(root)
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
    for lane in active:
        if lane not in LANES:
            errors.append(f"unknown lane in manifest: {lane}")
        if not (case_root / "lanes" / f"{lane}.md").is_file():
            errors.append(f"missing lane card: {lane}")
    stale: list[str] = []
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


def context_bundle(root: Path, lane: str) -> dict[str, Any]:
    validate_case(root, False)
    case_root, data = load(root)
    if lane not in data["lanes"]:
        raise CaseError(f"Lane is not active: {lane}")
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
            _, result = load(args.case_root)
        elif args.command == "context":
            result = context_bundle(args.case_root, args.lane)
        elif args.command == "transition":
            result = transition(args.case_root, args.lane, args.to, args.note)
        elif args.command == "set-gate":
            result = set_gate(args.case_root, args.gate, args.status, args.evidence, args.note, args.subject)
        else:
            result = validate_case(args.case_root, args.final)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, CaseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
