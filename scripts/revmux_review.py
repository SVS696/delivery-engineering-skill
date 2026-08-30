#!/usr/bin/env python3
"""Prepare revmux review inputs, validate rounds, and emit adoption evidence.

The script is deliberately not a review loop. It turns one finished revmux
round into immutable evidence and combines exactly one initial/final pair into
bounded adoption metrics. Source changes remain the coordinator's responsibility.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


GATING_SEVERITIES = {"critical", "major"}
ACTIONABLE_VERDICTS = {"confirmed", "refined"}
VALID_VERDICTS = ACTIONABLE_VERDICTS | {"unverified"}
PHASES = {"initial", "final"}
SHA256_RE_LENGTH = 64
REVMUX_COMPAT_REVISION = "33ede7aaf632cebbde08f2dd53ffa06c4722d81b"


class EvidenceError(RuntimeError):
    """The supplied revmux evidence is incomplete or inconsistent."""


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"JSON root must be an object: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise EvidenceError(f"{field} must be a string array")
    return value


def findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    value = report.get("findings")
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise EvidenceError("findings must be an object array")
    return value


def finding_area(item: dict[str, Any]) -> str:
    file_name = str(item.get("file") or "<document>")
    lenses = item.get("lenses")
    if not isinstance(lenses, list) or not lenses:
        return f"unclassified::{file_name}"
    return ",".join(sorted(str(lens) for lens in lenses)) + f"::{file_name}"


def resolve_bounded_file(root: Path, relative: str, field: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise EvidenceError(f"{field} escapes its root: {relative}") from exc
    if not path.is_file():
        raise EvidenceError(f"{field} is not a readable file: {path}")
    return path


def git_output(worktree: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(worktree), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise EvidenceError(f"cannot execute git: {exc}") from exc
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise EvidenceError(f"git {' '.join(args)} failed: {message}")
    return result.stdout


def detect_revmux(binary: str) -> dict[str, str]:
    resolved = shutil.which(binary)
    if resolved is None:
        raise EvidenceError(f"required revmux binary is not on PATH: {binary}")
    try:
        result = subprocess.run(
            [resolved, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise EvidenceError(f"cannot execute revmux binary {resolved}: {exc}") from exc
    version = result.stdout.decode("utf-8", errors="replace").strip()
    if result.returncode != 0 or not version:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise EvidenceError(f"revmux --version failed: {detail or result.returncode}")
    if REVMUX_COMPAT_REVISION[:7] not in version:
        raise EvidenceError(
            "unsupported revmux build; expected compatible revision "
            f"{REVMUX_COMPAT_REVISION}, got {version!r}"
        )
    return {
        "binary": str(Path(resolved).resolve()),
        "version": version,
        "compatible_revision": REVMUX_COMPAT_REVISION,
    }


def resolve_commit(worktree: Path, ref: str) -> str:
    value = git_output(
        worktree,
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{ref}^{{commit}}",
    ).decode("ascii", errors="strict").strip()
    if len(value) != 40:
        raise EvidenceError(f"git ref did not resolve to one commit: {ref}")
    return value


def prepare_round(args: argparse.Namespace) -> int:
    assignment = read_json(args.assignment)
    if assignment.get("role") != "delivery-tester" or assignment.get("lane") != "test":
        raise EvidenceError("revmux round preparation requires the delivery test lane")
    if assignment.get("role_mode") != "conformance":
        raise EvidenceError("revmux round preparation requires role_mode=conformance")
    if assignment.get("review_backend") != "revmux":
        raise EvidenceError("assignment must select review_backend=revmux")
    phase = assignment.get("review_phase")
    if phase not in PHASES:
        raise EvidenceError("assignment requires review_phase=initial|final")
    expected_profile = "comprehensive" if phase == "initial" else "final"
    if assignment.get("revmux_profile") != expected_profile:
        raise EvidenceError(f"assignment profile must be {expected_profile}")
    covered = string_list(assignment.get("covered_gates"), "covered_gates")
    if covered != ["project_conformance"]:
        raise EvidenceError("Delivery revmux assignment must cover project_conformance exactly")
    revmux_dependency = detect_revmux(args.revmux_bin)

    case_root = args.case_root.resolve()
    skill_root = args.skill_root.resolve()
    worktree = args.worktree.resolve()
    if not case_root.is_dir() or not skill_root.is_dir() or not worktree.is_dir():
        raise EvidenceError("case root, skill root and worktree must be existing directories")
    git_output(worktree, "rev-parse", "--is-inside-work-tree")
    base_sha = resolve_commit(worktree, args.base_ref)
    head_sha = resolve_commit(worktree, args.head_ref)
    range_spec = f"{base_sha}..{head_sha}"
    diff_bytes = git_output(worktree, "diff", "--binary", "--no-ext-diff", range_spec, "--")
    if not diff_bytes:
        raise EvidenceError("Delivery revmux subject diff is empty")
    diff_sha256 = hashlib.sha256(diff_bytes).hexdigest()
    changed_files = [
        line
        for line in git_output(
            worktree, "diff", "--name-only", "--no-ext-diff", range_spec, "--"
        ).decode("utf-8").splitlines()
        if line
    ]
    shortstat = git_output(
        worktree, "diff", "--shortstat", "--no-ext-diff", range_spec, "--"
    ).decode("utf-8").strip()

    allowed_inputs = string_list(assignment.get("allowed_inputs"), "allowed_inputs")
    contract_inputs = string_list(assignment.get("contract_inputs"), "contract_inputs")
    case_files = [
        resolve_bounded_file(case_root, relative, "allowed input")
        for relative in allowed_inputs
    ]
    contract_files = [
        resolve_bounded_file(skill_root, relative, "contract input")
        for relative in contract_inputs
    ]
    profile_source = args.profile_source.resolve()
    if not profile_source.is_file():
        raise EvidenceError(f"project profile is not a readable file: {profile_source}")
    instruction_files = []
    for item in args.repository_instruction:
        path = item.resolve()
        try:
            path.relative_to(worktree)
        except ValueError as exc:
            raise EvidenceError(f"repository instruction is outside worktree: {path}") from exc
        if not path.is_file():
            raise EvidenceError(f"repository instruction is not a readable file: {path}")
        instruction_files.append(path)

    materials = [
        {
            "kind": "case-baseline",
            "path": str(path),
            "relative": relative,
            "sha256": sha256(path),
        }
        for relative, path in zip(allowed_inputs, case_files, strict=True)
    ] + [
        {
            "kind": "review-contract",
            "path": str(path),
            "relative": relative,
            "sha256": sha256(path),
        }
        for relative, path in zip(contract_inputs, contract_files, strict=True)
    ]
    materials.extend(
        {
            "kind": "repository-instruction",
            "path": str(path),
            "relative": str(path.relative_to(worktree)),
            "sha256": sha256(path),
        }
        for path in instruction_files
    )
    materials.append(
        {
            "kind": "project-profile",
            "path": str(profile_source),
            "relative": profile_source.name,
            "sha256": sha256(profile_source),
        }
    )
    fingerprint_payload = {
        "diff_sha256": diff_sha256,
        "covered_gates": covered,
        "materials": materials,
    }
    material_fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    subject_sha256 = hashlib.sha256(
        f"{diff_sha256}\n{material_fingerprint}\n".encode("ascii")
    ).hexdigest()

    outputs = [args.scope_output, args.goal_output, args.profile_output]
    if any(path.exists() for path in outputs):
        raise EvidenceError("revmux new output files must not already exist")
    if args.context_dir.exists():
        if not args.context_dir.is_dir() or any(args.context_dir.iterdir()):
            raise EvidenceError("revmux context directory must be absent or empty")
    args.context_dir.mkdir(parents=True, exist_ok=True)
    diff_path = args.context_dir / "delivery.diff"
    context_path = args.context_dir / "delivery-assignment.json"
    diff_path.write_bytes(diff_bytes)
    context_payload = {
        "schema": 1,
        "case_id": assignment.get("case_id"),
        "role": "delivery-tester",
        "role_mode": "conformance",
        "review_backend": "revmux",
        "review_phase": phase,
        "revmux_profile": expected_profile,
        "covered_gates": covered,
        "subject_sha256": subject_sha256,
        "material_fingerprint": material_fingerprint,
        "diff": {
            "worktree": str(worktree),
            "base_ref": args.base_ref,
            "base_sha": base_sha,
            "head_ref": args.head_ref,
            "head_sha": head_sha,
            "range": range_spec,
            "sha256": diff_sha256,
            "archive": str(diff_path),
            "shortstat": shortstat,
            "changed_files": changed_files,
        },
        "comparison": {
            "target": "the archived exact diff and changed files at head_sha",
            "baselines": materials,
            "question": (
                "Does this exact diff satisfy the approved scope and acceptance basis, follow the "
                "frozen project/repository rules, preserve the authoritative implementation path, "
                "and avoid material regressions or scope creep?"
            ),
        },
        "revmux_dependency": revmux_dependency,
        "excluded": assignment.get("excluded", []),
    }
    context_path.write_text(
        json.dumps(context_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    excluded = assignment.get("excluded")
    excluded_text = ", ".join(str(item) for item in excluded) if isinstance(excluded, list) else "none"
    scope_text = (
        "# Scope\n\n"
        f"- Delivery case: `{assignment.get('case_id')}`; phase: `{phase}`; profile: `{expected_profile}`\n"
        f"- Review exact diff `{base_sha}..{head_sha}` ({shortstat or 'non-empty diff'}).\n"
        f"- Archived diff: `{diff_path}`; SHA-256: `{diff_sha256}`\n"
        f"- Changed files and hashed comparison baselines: `{context_path}`\n"
        "- Inspect with:\n\n"
        "```text\n"
        f"git diff {base_sha}..{head_sha}\n"
        "```\n\n"
        f"- Subject SHA-256: `{subject_sha256}`\n"
        f"- Exclude: {excluded_text}\n"
        "- Do not inspect unrelated repository paths or substitute test execution for review.\n"
    )
    goal_text = (
        "# Goal\n\n"
        f"{context_payload['comparison']['question']}\n\n"
        "This review is correct only if every finding is caused by the exact archived diff and is "
        "judged against the frozen acceptance/conformance inputs and repository instructions.\n\n"
        "Confirmed critical/major findings gate conformance. Minor findings never request a "
        "correction round; in final phase they are not reported. Tests, CI and live verification "
        "remain separate evidence and must not be rerun by this panel.\n"
    )
    args.scope_output.write_text(scope_text, encoding="utf-8")
    args.goal_output.write_text(goal_text, encoding="utf-8")
    args.profile_output.write_bytes(profile_source.read_bytes())
    result = {
        "schema": 1,
        "scope": str(args.scope_output.resolve()),
        "goal": str(args.goal_output.resolve()),
        "profile": str(args.profile_output.resolve()),
        "context": str(context_path.resolve()),
        "diff": str(diff_path.resolve()),
        "base_sha": base_sha,
        "head_sha": head_sha,
        "diff_sha256": diff_sha256,
        "subject_sha256": subject_sha256,
        "material_fingerprint": material_fingerprint,
        "covered_gates": covered,
        "revmux_dependency": revmux_dependency,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def gating_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in findings(report)
        if item.get("severity") in GATING_SEVERITIES
        and item.get("verdict") in ACTIONABLE_VERDICTS
    ]


def validate_round(
    report_path: Path,
    manifest_path: Path,
    expected_profile: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    report = read_json(report_path)
    manifest = read_json(manifest_path)
    scope = report.get("scope")
    sources = report.get("sources")
    stats = report.get("stats")
    if not isinstance(scope, dict) or not isinstance(sources, dict) or not isinstance(stats, dict):
        raise EvidenceError("report requires scope, sources and stats objects")
    for field in ("task", "run", "scope_path"):
        if not isinstance(scope.get(field), str) or not scope[field]:
            raise EvidenceError(f"scope.{field} must be a non-empty string")
    for field in ("task", "run", "scope_path"):
        if manifest.get(field) != scope.get(field):
            raise EvidenceError(f"manifest {field} does not match report scope")
    if manifest.get("profile") != expected_profile:
        raise EvidenceError(
            f"expected revmux profile {expected_profile!r}, got {manifest.get('profile')!r}"
        )
    expected = sources.get("expected")
    reported = sources.get("reported")
    degraded = string_list(sources.get("degraded"), "sources.degraded")
    agents = sources.get("agents")
    if not isinstance(expected, int) or expected < 1:
        raise EvidenceError("sources.expected must be a positive integer")
    if not isinstance(reported, int) or reported != expected:
        raise EvidenceError(f"incomplete revmux sources: {reported}/{expected}")
    if degraded:
        raise EvidenceError("degraded revmux sources: " + ", ".join(degraded))
    if not isinstance(agents, list) or len(agents) != expected:
        raise EvidenceError("sources.agents must contain every expected source")
    degraded_agents = [
        str(agent.get("name", "<unnamed>"))
        for agent in agents
        if isinstance(agent, dict) and agent.get("degraded") is True
    ]
    if degraded_agents:
        raise EvidenceError("degraded revmux agents: " + ", ".join(degraded_agents))
    for item in findings(report):
        severity = item.get("severity")
        verdict = item.get("verdict")
        if severity not in {"critical", "major", "minor"}:
            raise EvidenceError(f"finding has invalid severity: {severity!r}")
        if verdict not in VALID_VERDICTS:
            raise EvidenceError(f"finding has invalid actionable verdict: {verdict!r}")
        if severity in GATING_SEVERITIES and verdict == "unverified":
            raise EvidenceError("critical/major finding is unverified")
    duration_ms = stats.get("duration_ms")
    tokens = stats.get("tokens")
    if not isinstance(duration_ms, int) or duration_ms < 0:
        raise EvidenceError("stats.duration_ms must be a non-negative integer")
    if not isinstance(tokens, int) or tokens < 0:
        raise EvidenceError("stats.tokens must be a non-negative integer")
    if manifest.get("duration_ms") != duration_ms or manifest.get("tokens") != tokens:
        raise EvidenceError("manifest timing/token totals do not match report")

    stages = stats.get("stages")
    if not isinstance(stages, list) or not all(isinstance(item, dict) for item in stages):
        raise EvidenceError("stats.stages must be an object array")
    stage_names = {str(item.get("name")) for item in stages}
    if not {"synthesis", "verify"}.issubset(stage_names):
        raise EvidenceError("review evidence requires both synthesis and verify stages")

    round_dir = manifest_path.resolve().parent
    stage_prompts = list((round_dir / "prompts" / "stages").glob("*.md"))
    if len(stage_prompts) < 2:
        raise EvidenceError("round archive is missing synthesis/verify prompt evidence")
    retry_calls = list((round_dir / "agents").glob("*.retry.*"))
    revmux_model_calls = len(agents) + len(stage_prompts) + len(retry_calls)
    model_calls = revmux_model_calls + 1  # the fresh reviewer-driver assignment
    gating = gating_findings(report)
    metrics = {
        "schema": 1,
        "task": scope["task"],
        "run": scope["run"],
        "profile": expected_profile,
        "report": str(report_path.resolve()),
        "report_sha256": sha256(report_path),
        "manifest": str(manifest_path.resolve()),
        "manifest_sha256": sha256(manifest_path),
        "revmux_duration_ms": duration_ms,
        "model_calls": model_calls,
        "revmux_model_calls": revmux_model_calls,
        "driver_model_calls": 1,
        "revmux_tokens": tokens,
        "confirmed_critical": sum(item.get("severity") == "critical" for item in gating),
        "confirmed_major": sum(item.get("severity") == "major" for item in gating),
        "confirmed_gating_total": len(gating),
        "minor": sum(item.get("severity") == "minor" for item in findings(report)),
        "gating_areas": sorted({finding_area(item) for item in gating}),
        "source_count": expected,
        "degraded": False,
    }
    return report, manifest, metrics


def write_round(args: argparse.Namespace) -> int:
    report, _, metrics = validate_round(args.report, args.manifest, args.expected_profile)
    if args.phase not in PHASES:
        raise EvidenceError(f"invalid phase: {args.phase}")
    if len(args.subject_sha256) != SHA256_RE_LENGTH:
        raise EvidenceError("subject SHA-256 must contain 64 characters")
    gating = gating_findings(report)
    decision = "pass" if not gating else "revise"
    if args.phase == "final" and gating:
        decision = "fail"
    covered = list(dict.fromkeys(args.covered_gate))
    if not covered:
        raise EvidenceError("round evidence requires at least one covered gate")
    gate_recommendation = (
        "pass"
        if not gating
        else ("user-decision" if args.phase == "final" else "revise")
    )
    evidence_lines = [
        "# revmux review evidence",
        "",
        f"- backend: `revmux`",
        f"- phase: `{args.phase}`",
        f"- profile: `{metrics['profile']}`",
        f"- task: `{metrics['task']}`",
        f"- run: `{metrics['run']}`",
        f"- subject_sha256: `{args.subject_sha256}`",
        f"- report_sha256: `{metrics['report_sha256']}`",
        f"- manifest_sha256: `{metrics['manifest_sha256']}`",
        f"- covered_gates: [{', '.join(covered)}]",
        f"- confirmed_critical: `{metrics['confirmed_critical']}`",
        f"- confirmed_major: `{metrics['confirmed_major']}`",
        f"- minor: `{metrics['minor']}`",
        f"- reported_blocker: `{metrics['confirmed_critical']}`",
        f"- reported_major: `{metrics['confirmed_major']}`",
        f"- reported_minor: `{metrics['minor']}`",
        f"- gate_recommendation: `{gate_recommendation}`",
        f"- revmux_duration_ms: `{metrics['revmux_duration_ms']}`",
        f"- model_calls: `{metrics['model_calls']}`",
        f"- revmux_tokens: `{metrics['revmux_tokens']}`",
        f"- decision: `{decision}`",
        "",
        "The reviewer used revmux as the sole semantic review engine for this gate and did not add an independent model pass.",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(evidence_lines) + "\n", encoding="utf-8")
    metrics.update(
        phase=args.phase,
        subject_sha256=args.subject_sha256,
        covered_gates=covered,
        decision=decision,
        gate_recommendation=gate_recommendation,
        evidence=str(args.output.resolve()),
        evidence_sha256=sha256(args.output),
    )
    args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
    args.metrics_output.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 1 if args.phase == "final" and gating else 0


def write_case(args: argparse.Namespace) -> int:
    initial = read_json(args.initial_metrics)
    final = read_json(args.final_metrics)
    if initial.get("phase") != "initial" or final.get("phase") != "final":
        raise EvidenceError("case metrics require one initial and one final receipt")
    if initial.get("task") != final.get("task"):
        raise EvidenceError("initial/final task mismatch")
    if args.correction_rounds not in {0, 1}:
        raise EvidenceError("review cycle permits zero or one correction round")
    if args.active_time_seconds < 0:
        raise EvidenceError("active time must be non-negative")
    if args.driver_tokens < 0:
        raise EvidenceError("driver tokens must be non-negative")
    initial_gating = int(initial.get("confirmed_critical", 0)) + int(
        initial.get("confirmed_major", 0)
    )
    final_gating = int(final.get("confirmed_critical", 0)) + int(
        final.get("confirmed_major", 0)
    )
    if args.correction_rounds != int(initial_gating > 0):
        raise EvidenceError("correction round count must match initial gating findings")
    if final.get("decision") == "pass" and final_gating:
        raise EvidenceError("final pass cannot contain confirmed critical/major findings")
    initial_areas = set(string_list(initial.get("gating_areas"), "initial.gating_areas"))
    final_areas = set(string_list(final.get("gating_areas"), "final.gating_areas"))
    receipt = {
        "schema": 1,
        "case_kind": args.case_kind,
        "task": initial["task"],
        "initial_subject_sha256": initial["subject_sha256"],
        "final_subject_sha256": final["subject_sha256"],
        "active_time_seconds": args.active_time_seconds,
        "revmux_duration_ms": int(initial["revmux_duration_ms"]) + int(final["revmux_duration_ms"]),
        "model_calls": int(initial["model_calls"]) + int(final["model_calls"]),
        "revmux_tokens": int(initial["revmux_tokens"]) + int(final["revmux_tokens"]),
        "driver_tokens": args.driver_tokens,
        "tokens": int(initial["revmux_tokens"]) + int(final["revmux_tokens"]) + args.driver_tokens,
        "confirmed_critical": int(initial["confirmed_critical"]),
        "confirmed_major": int(initial["confirmed_major"]),
        "correction_rounds": args.correction_rounds,
        "reopened_reviewed_areas": sorted(final_areas - initial_areas),
        "repeated_gating_areas": sorted(final_areas & initial_areas),
        "final_decision": final.get("decision"),
        "initial_metrics_sha256": sha256(args.initial_metrics),
        "final_metrics_sha256": sha256(args.final_metrics),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["final_decision"] == "pass" else 1


def aggregate(args: argparse.Namespace) -> int:
    receipts = [read_json(path) for path in args.receipt]
    count = len(receipts)
    if count > 5:
        raise EvidenceError("adoption decision must be taken no later than five cases")
    identities = [
        (str(item.get("task")), str(item.get("initial_subject_sha256")))
        for item in receipts
    ]
    if len(set(identities)) != count:
        raise EvidenceError("adoption aggregate requires distinct case subjects")
    case_kinds = {str(item.get("case_kind")) for item in receipts}
    coverage_ready = {"vigers", "delivery"}.issubset(case_kinds)
    decision_ready = 3 <= count <= 5 and coverage_ready
    result = {
        "schema": 1,
        "case_count": count,
        "case_kinds": sorted(case_kinds),
        "decision_ready": decision_ready,
        "permanent_enablement": (
            "human-decision-required"
            if decision_ready
            else ("missing-vigers-or-delivery-coverage" if count >= 3 else "not-enough-cases")
        ),
        "totals": {
            field: sum(int(item.get(field, 0)) for item in receipts)
            for field in (
                "active_time_seconds",
                "revmux_duration_ms",
                "model_calls",
                "revmux_tokens",
                "driver_tokens",
                "tokens",
                "confirmed_critical",
                "confirmed_major",
                "correction_rounds",
            )
        },
        "reopened_reviewed_areas": sum(
            len(item.get("reopened_reviewed_areas", [])) for item in receipts
        ),
        "repeated_gating_areas": sum(
            len(item.get("repeated_gating_areas", [])) for item in receipts
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    prepare_cmd = commands.add_parser("prepare")
    prepare_cmd.add_argument("--assignment", type=Path, required=True)
    prepare_cmd.add_argument("--case-root", type=Path, required=True)
    prepare_cmd.add_argument(
        "--skill-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    prepare_cmd.add_argument("--profile-source", type=Path, required=True)
    prepare_cmd.add_argument("--revmux-bin", default="revmux")
    prepare_cmd.add_argument("--worktree", type=Path, required=True)
    prepare_cmd.add_argument("--base-ref", required=True)
    prepare_cmd.add_argument("--head-ref", default="HEAD")
    prepare_cmd.add_argument(
        "--repository-instruction",
        type=Path,
        action="append",
        default=[],
    )
    prepare_cmd.add_argument("--scope-output", type=Path, required=True)
    prepare_cmd.add_argument("--goal-output", type=Path, required=True)
    prepare_cmd.add_argument("--profile-output", type=Path, required=True)
    prepare_cmd.add_argument("--context-dir", type=Path, required=True)
    round_cmd = commands.add_parser("round")
    round_cmd.add_argument("--report", type=Path, required=True)
    round_cmd.add_argument("--manifest", type=Path, required=True)
    round_cmd.add_argument("--phase", choices=sorted(PHASES), required=True)
    round_cmd.add_argument("--expected-profile", required=True)
    round_cmd.add_argument("--subject-sha256", required=True)
    round_cmd.add_argument("--covered-gate", action="append", default=[])
    round_cmd.add_argument("--output", type=Path, required=True)
    round_cmd.add_argument("--metrics-output", type=Path, required=True)
    case_cmd = commands.add_parser("case")
    case_cmd.add_argument("--initial-metrics", type=Path, required=True)
    case_cmd.add_argument("--final-metrics", type=Path, required=True)
    case_cmd.add_argument("--case-kind", choices=("vigers", "delivery"), required=True)
    case_cmd.add_argument("--active-time-seconds", type=int, required=True)
    case_cmd.add_argument("--driver-tokens", type=int, required=True)
    case_cmd.add_argument("--correction-rounds", type=int, required=True)
    case_cmd.add_argument("--output", type=Path, required=True)
    aggregate_cmd = commands.add_parser("aggregate")
    aggregate_cmd.add_argument("--receipt", type=Path, action="append", required=True)
    aggregate_cmd.add_argument("--output", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "prepare":
            return prepare_round(args)
        if args.command == "round":
            return write_round(args)
        if args.command == "case":
            return write_case(args)
        return aggregate(args)
    except EvidenceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
