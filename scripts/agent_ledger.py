#!/usr/bin/env python3
"""Additive model-run observability for Delivery Engineering cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FILENAME = "agent-ledger.json"
SCHEMA = 1
RUN_ID_RE = re.compile(r"^AR-[0-9]{4,}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LENS_RE = re.compile(r"^[a-z][a-z0-9._-]{0,63}@[1-9][0-9]*$")
STATUSES = {"completed", "degraded", "failed", "timed_out"}


class LedgerError(RuntimeError):
    """Invalid observability record or unsafe artifact binding."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def case_file(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise LedgerError(f"Case path escapes root: {relative}") from exc
    return candidate


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create(root: Path, case_id: str) -> None:
    path = root.resolve() / FILENAME
    if path.exists():
        raise LedgerError(f"Agent ledger already exists: {path}")
    atomic_json(path, {"schema": SCHEMA, "case_id": case_id, "runs": []})


def load(root: Path) -> tuple[Path, dict[str, Any]]:
    path = root.resolve() / FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LedgerError(f"Cannot read agent ledger: {exc}") from exc
    if not isinstance(payload, dict):
        raise LedgerError("Agent ledger must be an object")
    return path, payload


def artifact_binding(root: Path, relative: str) -> dict[str, str]:
    path = case_file(root, relative)
    if not path.is_file():
        raise LedgerError(f"Agent artifact is missing: {relative}")
    return {"ref": relative, "sha256": digest(path)}


def next_run_id(runs: list[Any]) -> str:
    maximum = 0
    for run in runs:
        if not isinstance(run, dict):
            continue
        run_id = run.get("run_id")
        if isinstance(run_id, str) and RUN_ID_RE.fullmatch(run_id):
            maximum = max(maximum, int(run_id.removeprefix("AR-")))
    return f"AR-{maximum + 1:04d}"


def validate(payload: Any, *, case_id: str, root: Path | None = None) -> list[str]:
    if not isinstance(payload, dict):
        return ["agent-ledger.json must be an object"]
    if payload.get("schema") != SCHEMA or payload.get("case_id") != case_id:
        return ["agent-ledger.json identity is invalid"]
    runs = payload.get("runs")
    if not isinstance(runs, list):
        return ["agent-ledger.json runs must be an array"]
    errors: list[str] = []
    seen: set[str] = set()
    for index, run in enumerate(runs, start=1):
        label = f"agent-ledger run {index}"
        if not isinstance(run, dict):
            errors.append(f"{label} must be an object")
            continue
        run_id = run.get("run_id")
        if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
            errors.append(f"{label} has invalid run_id")
        elif run_id in seen:
            errors.append(f"{label} duplicates run_id {run_id}")
        else:
            seen.add(run_id)
        for field in ("at", "role", "role_mode", "model", "subject_sha256"):
            if not isinstance(run.get(field), str) or not run[field].strip():
                errors.append(f"{label} requires {field}")
        if isinstance(run.get("subject_sha256"), str) and not SHA256_RE.fullmatch(
            run["subject_sha256"]
        ):
            errors.append(f"{label} has invalid subject_sha256")
        if run.get("status", "completed") not in STATUSES:
            errors.append(f"{label} has invalid status")
        reasons = run.get("degraded_reasons", [])
        if not isinstance(reasons, list) or any(
            not isinstance(item, str) or not item.strip() for item in reasons
        ):
            errors.append(f"{label} degraded_reasons must contain non-empty strings")
        if reasons and run.get("status", "completed") == "completed":
            errors.append(f"{label} completed status cannot have degraded_reasons")
        lenses = run.get("lenses", [])
        if not isinstance(lenses, list) or len(lenses) != len(set(lenses)) or any(
            not isinstance(item, str) or not LENS_RE.fullmatch(item) for item in lenses
        ):
            errors.append(f"{label} lenses must be unique stable id@version values")
        for field in (
            "input_bytes",
            "input_tokens",
            "output_tokens",
            "retries",
            "tool_calls",
            "poll_calls",
        ):
            value = run.get(field)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                errors.append(f"{label} {field} must be non-negative or null")
        duration = run.get("duration_seconds")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration < 0:
            errors.append(f"{label} has invalid duration_seconds")
        wait_seconds = run.get("wait_seconds")
        if wait_seconds is not None and (
            not isinstance(wait_seconds, (int, float))
            or isinstance(wait_seconds, bool)
            or wait_seconds < 0
        ):
            errors.append(f"{label} wait_seconds must be non-negative or null")
        findings = run.get("findings")
        if not isinstance(findings, dict):
            errors.append(f"{label} findings must be an object")
        else:
            for severity in ("blocker", "major", "minor"):
                value = findings.get(severity)
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    errors.append(f"{label} findings.{severity} is invalid")
        bindings: list[tuple[str, Any]] = list((run.get("artifacts") or {}).items())
        verification = run.get("verification")
        if isinstance(verification, dict):
            if not isinstance(verification.get("at"), str) or not verification["at"].strip():
                errors.append(f"{label} verification requires at")
            bindings.append(
                (
                    "verification",
                    {
                        "ref": verification.get("evidence_ref"),
                        "sha256": verification.get("evidence_sha256"),
                    },
                )
            )
            dispositions = verification.get("dispositions")
            if not isinstance(dispositions, dict):
                errors.append(f"{label} verification dispositions must be an object")
            else:
                for disposition in ("accepted", "rejected", "duplicate", "verified"):
                    value = dispositions.get(disposition)
                    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                        errors.append(f"{label} verification {disposition} is invalid")
                if isinstance(dispositions.get("verified"), int) and isinstance(
                    dispositions.get("accepted"), int
                ) and dispositions["verified"] > dispositions["accepted"]:
                    errors.append(f"{label} verification verified exceeds accepted")
        artifacts = run.get("artifacts")
        if artifacts is not None and (not isinstance(artifacts, dict) or not artifacts):
            errors.append(f"{label} artifacts must be a non-empty object")
        for kind, binding in bindings:
            if kind not in {"prompt", "output", "verification"} or not isinstance(binding, dict):
                errors.append(f"{label} has invalid {kind} artifact")
                continue
            relative = binding.get("ref")
            expected = binding.get("sha256")
            if not isinstance(relative, str) or not relative.strip():
                errors.append(f"{label} {kind} artifact requires ref")
                continue
            if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
                errors.append(f"{label} {kind} artifact has invalid sha256")
                continue
            if root is not None:
                try:
                    path = case_file(root, relative)
                except LedgerError as exc:
                    errors.append(f"{label} {kind}: {exc}")
                    continue
                if not path.is_file():
                    errors.append(f"{label} {kind} artifact is missing")
                elif digest(path) != expected:
                    errors.append(f"{label} {kind} artifact changed after binding")
    return errors


def record_run(
    root: Path,
    *,
    role: str,
    role_mode: str,
    model: str,
    subject_sha256: str,
    duration_seconds: float,
    retries: int,
    input_bytes: int | None,
    input_tokens: int | None,
    output_tokens: int | None,
    reported_blocker: int,
    reported_major: int,
    reported_minor: int,
    status: str,
    degraded_reasons: list[str],
    lenses: list[str],
    prompt_artifact: str | None,
    output_artifact: str | None,
    tool_calls: int | None = None,
    poll_calls: int | None = None,
    wait_seconds: float | None = None,
) -> str:
    path, payload = load(root)
    errors = validate(payload, case_id=str(payload.get("case_id")), root=root)
    if errors:
        raise LedgerError("; ".join(errors))
    normalized_reasons = [item.strip() for item in degraded_reasons]
    normalized_lenses = [item.strip() for item in lenses]
    if status not in STATUSES:
        raise LedgerError("Agent run status is invalid")
    if normalized_reasons and status == "completed":
        raise LedgerError("Completed agent run cannot have degraded reasons")
    if len(normalized_lenses) != len(set(normalized_lenses)) or any(
        not LENS_RE.fullmatch(item) for item in normalized_lenses
    ):
        raise LedgerError("Agent lenses must be unique stable id@version values")
    counters = [
        input_bytes,
        input_tokens,
        output_tokens,
        retries,
        reported_blocker,
        reported_major,
        reported_minor,
        tool_calls,
        poll_calls,
    ]
    if any(
        value is not None
        and (not isinstance(value, int) or isinstance(value, bool) or value < 0)
        for value in counters
    ) or duration_seconds < 0:
        raise LedgerError("Agent counters and duration must be non-negative")
    if wait_seconds is not None and (
        not isinstance(wait_seconds, (int, float))
        or isinstance(wait_seconds, bool)
        or wait_seconds < 0
    ):
        raise LedgerError("Agent wait_seconds must be non-negative or null")
    if not SHA256_RE.fullmatch(subject_sha256):
        raise LedgerError("Agent subject hash must be lowercase SHA-256")
    run: dict[str, Any] = {
        "run_id": next_run_id(payload["runs"]),
        "at": now(),
        "role": role.strip(),
        "role_mode": role_mode.strip(),
        "model": model.strip(),
        "subject_sha256": subject_sha256,
        "input_bytes": input_bytes,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_seconds": duration_seconds,
        "retries": retries,
        "tool_calls": tool_calls,
        "poll_calls": poll_calls,
        "wait_seconds": wait_seconds,
        "findings": {
            "blocker": reported_blocker,
            "major": reported_major,
            "minor": reported_minor,
        },
        "status": status,
        "degraded_reasons": normalized_reasons,
        "lenses": normalized_lenses,
    }
    if not run["role"] or not run["role_mode"] or not run["model"]:
        raise LedgerError("Agent role, role mode and model are required")
    artifacts: dict[str, dict[str, str]] = {}
    if prompt_artifact:
        artifacts["prompt"] = artifact_binding(root, prompt_artifact)
    if output_artifact:
        artifacts["output"] = artifact_binding(root, output_artifact)
    if artifacts:
        run["artifacts"] = artifacts
    payload["runs"].append(run)
    atomic_json(path, payload)
    return str(run["run_id"])


def record_verification(
    root: Path,
    *,
    run_id: str,
    accepted: int,
    rejected: int,
    duplicate: int,
    verified: int,
    evidence_ref: str,
) -> None:
    path, payload = load(root)
    errors = validate(payload, case_id=str(payload.get("case_id")), root=root)
    if errors:
        raise LedgerError("; ".join(errors))
    if any(value < 0 for value in (accepted, rejected, duplicate, verified)):
        raise LedgerError("Agent verification counts must be non-negative")
    if verified > accepted:
        raise LedgerError("Verified findings cannot exceed accepted findings")
    matches = [
        run
        for run in payload.get("runs", [])
        if isinstance(run, dict) and run.get("run_id") == run_id
    ]
    if len(matches) != 1:
        raise LedgerError(f"Agent run not found: {run_id}")
    run = matches[0]
    if "verification" in run:
        raise LedgerError(f"Agent run already has verification: {run_id}")
    reported_total = sum(run["findings"].values())
    if accepted + rejected + duplicate != reported_total:
        raise LedgerError("Agent verification must classify every reported finding exactly once")
    evidence = artifact_binding(root, evidence_ref)
    run["verification"] = {
        "at": now(),
        "evidence_ref": evidence["ref"],
        "evidence_sha256": evidence["sha256"],
        "dispositions": {
            "accepted": accepted,
            "rejected": rejected,
            "duplicate": duplicate,
            "verified": verified,
        },
    }
    atomic_json(path, payload)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record-run")
    record.add_argument("--case-root", type=Path, required=True)
    record.add_argument("--role", required=True)
    record.add_argument("--role-mode", required=True)
    record.add_argument("--model", required=True)
    record.add_argument("--subject-sha256", required=True)
    record.add_argument("--duration-seconds", type=float, required=True)
    record.add_argument("--retries", type=int, default=0)
    record.add_argument("--input-bytes", type=int)
    record.add_argument("--input-tokens", type=int)
    record.add_argument("--output-tokens", type=int)
    record.add_argument("--tool-calls", type=int)
    record.add_argument("--poll-calls", type=int)
    record.add_argument("--wait-seconds", type=float)
    record.add_argument("--reported-blocker", type=int, default=0)
    record.add_argument("--reported-major", type=int, default=0)
    record.add_argument("--reported-minor", type=int, default=0)
    record.add_argument("--status", choices=sorted(STATUSES), default="completed")
    record.add_argument("--degraded-reason", action="append", default=[])
    record.add_argument("--lens", action="append", default=[])
    record.add_argument("--prompt-artifact")
    record.add_argument("--output-artifact")
    verify = commands.add_parser("record-verification")
    verify.add_argument("--case-root", type=Path, required=True)
    verify.add_argument("--run-id", required=True)
    verify.add_argument("--accepted", type=int, required=True)
    verify.add_argument("--rejected", type=int, required=True)
    verify.add_argument("--duplicate", type=int, required=True)
    verify.add_argument("--verified", type=int, required=True)
    verify.add_argument("--evidence-ref", required=True)
    check = commands.add_parser("validate")
    check.add_argument("--case-root", type=Path, required=True)
    check.add_argument("--case-id", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "record-run":
            run_id = record_run(
                args.case_root,
                role=args.role,
                role_mode=args.role_mode,
                model=args.model,
                subject_sha256=args.subject_sha256,
                duration_seconds=args.duration_seconds,
                retries=args.retries,
                input_bytes=args.input_bytes,
                input_tokens=args.input_tokens,
                output_tokens=args.output_tokens,
                reported_blocker=args.reported_blocker,
                reported_major=args.reported_major,
                reported_minor=args.reported_minor,
                status=args.status,
                degraded_reasons=args.degraded_reason,
                lenses=args.lens,
                prompt_artifact=args.prompt_artifact,
                output_artifact=args.output_artifact,
                tool_calls=args.tool_calls,
                poll_calls=args.poll_calls,
                wait_seconds=args.wait_seconds,
            )
            result = {"status": "PASS", "run_id": run_id}
        elif args.command == "record-verification":
            record_verification(
                args.case_root,
                run_id=args.run_id,
                accepted=args.accepted,
                rejected=args.rejected,
                duplicate=args.duplicate,
                verified=args.verified,
                evidence_ref=args.evidence_ref,
            )
            result = {"status": "PASS", "run_id": args.run_id}
        else:
            _, payload = load(args.case_root)
            errors = validate(payload, case_id=args.case_id, root=args.case_root)
            if errors:
                raise LedgerError("; ".join(errors))
            result = {"status": "PASS", "runs": len(payload["runs"])}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, LedgerError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
