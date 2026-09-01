#!/usr/bin/env python3
"""Profile discovery and package validation for Delivery Engineering."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GENERIC_PROFILE = ROOT / "profiles" / "generic.md"
PROFILE_TEMPLATE = ROOT / "profiles" / "project-profile-template.md"
PROFILE_RELATIVE = Path(".delivery-engineering") / "profile.md"
PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
CAPABILITIES = {"backend", "frontend", "test"}
REQUIRED_HEADINGS = (
    "## Область",
    "## Источники истины",
    "## Capabilities",
    "## Codebase conformance",
    "## Engineering gates",
    "## Тестирование и приёмка",
    "## Внешний жизненный цикл",
)
ROLES = ("backend", "frontend", "tester")
PUBLIC_FORBIDDEN_MARKERS = tuple(
    "".join(parts) for parts in (("R", "TL"), ("H", "ÆZE"), ("HA", "EZE"))
)
HOME_MARKERS = tuple("".join(parts) for parts in (("/", "Users/"),))
RUNTIME_DIRECTORIES = {".git", ".omc", ".revmux", ".serena", "__pycache__"}


class PipelineError(RuntimeError):
    """Profile discovery or package validation failed."""


def is_public_package_path(path: Path) -> bool:
    """Exclude repository and review-tool runtime state from public scans."""
    try:
        relative = path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return False
    return not any(part in RUNTIME_DIRECTORIES for part in relative.parts)


@dataclass(frozen=True)
class Profile:
    profile_id: str
    capabilities: tuple[str, ...]
    path: Path
    project_root: Path | None
    source: str


def safe_file(relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise PipelineError("File path must be a non-empty relative string")
    candidate = (ROOT / relative).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise PipelineError(f"Path escapes skill root: {relative}") from exc
    if not candidate.is_file():
        raise PipelineError(f"File does not exist: {relative}")
    return candidate


def parse_frontmatter(text: str, source: Path) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise PipelineError(f"{source}: missing YAML frontmatter")
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise PipelineError(f"{source}: unclosed YAML frontmatter") from exc
    result: dict[str, str] = {}
    for line in lines[1:end]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise PipelineError(f"{source}: invalid frontmatter line: {stripped}")
        key, value = stripped.split(":", 1)
        result[key.strip()] = value.strip().strip("\"'")
    return result


def validate_profile_text(text: str, source: Path, *, allow_generic: bool) -> tuple[str, ...]:
    metadata = parse_frontmatter(text, source)
    if metadata.get("delivery_engineering_profile") != "1":
        raise PipelineError(f"{source}: delivery_engineering_profile must be 1")
    profile_id = metadata.get("profile_id", "")
    if not PROFILE_ID_RE.fullmatch(profile_id):
        raise PipelineError(f"{source}: invalid profile_id: {profile_id!r}")
    if profile_id == "generic" and not allow_generic:
        raise PipelineError(f"{source}: project profile cannot shadow generic")
    raw_capabilities = metadata.get("capabilities", "")
    capabilities = tuple(item.strip() for item in raw_capabilities.split(",") if item.strip())
    if not capabilities or len(set(capabilities)) != len(capabilities):
        raise PipelineError(f"{source}: capabilities must be a non-empty unique list")
    unknown = sorted(set(capabilities) - CAPABILITIES)
    if unknown:
        raise PipelineError(f"{source}: unknown capabilities: {', '.join(unknown)}")
    if "test" not in capabilities:
        raise PipelineError(f"{source}: test capability is mandatory")
    missing = [heading for heading in REQUIRED_HEADINGS if heading not in text]
    if missing:
        raise PipelineError(f"{source}: missing headings: {', '.join(missing)}")
    return capabilities


def read_profile(path: Path, project_root: Path | None, source: str) -> Profile:
    text = path.read_text(encoding="utf-8")
    capabilities = validate_profile_text(text, path, allow_generic=source == "generic")
    metadata = parse_frontmatter(text, path)
    return Profile(metadata["profile_id"], capabilities, path.resolve(), project_root, source)


def read_project_profile(root: Path) -> Profile | None:
    candidate = root / PROFILE_RELATIVE
    if not candidate.exists() and not candidate.is_symlink():
        return None
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise PipelineError(f"{candidate}: profile symlink escapes project root") from exc
    if not resolved.is_file():
        raise PipelineError(f"{candidate}: profile is not a readable file")
    return read_profile(resolved, root.resolve(), "project")


def ancestors(cwd: Path) -> list[Path]:
    current = cwd.expanduser().resolve()
    if current.is_file():
        current = current.parent
    return [current, *current.parents]


def detect_profile(cwd: Path) -> Profile:
    for root in ancestors(cwd):
        profile = read_project_profile(root)
        if profile is not None:
            return profile
    return read_profile(GENERIC_PROFILE, None, "generic")


def select_profile(requested: str, cwd: Path) -> Profile:
    if requested == "generic":
        return read_profile(GENERIC_PROFILE, None, "generic")
    detected = detect_profile(cwd)
    if requested == "auto" or requested == detected.profile_id:
        return detected
    raise PipelineError(
        f"Requested profile {requested!r}, but cwd resolves to {detected.profile_id!r}"
    )


def validate(project_roots: list[Path] | None = None) -> dict[str, int]:
    errors: list[str] = []
    for path, allow_generic in ((GENERIC_PROFILE, True), (PROFILE_TEMPLATE, False)):
        try:
            validate_profile_text(path.read_text(encoding="utf-8"), path, allow_generic=allow_generic)
        except (OSError, PipelineError) as exc:
            errors.append(str(exc))

    project_count = 0
    for root in project_roots or []:
        try:
            profile = read_project_profile(root.expanduser().resolve())
            if profile is None:
                raise PipelineError(f"{root}: missing {PROFILE_RELATIVE}")
            project_count += 1
        except (OSError, PipelineError) as exc:
            errors.append(str(exc))

    for role in ROLES:
        contract = f"agents/contracts/{role}.md"
        codex = f"agents/codex/delivery-{role}.toml"
        claude = f"agents/claude/delivery-{role}.md"
        try:
            body = safe_file(contract).read_text(encoding="utf-8")
            for heading in ("## Назначение", "## Вход", "## Запрещено", "## Выход"):
                if heading not in body:
                    errors.append(f"{contract}: missing heading {heading}")
        except PipelineError as exc:
            errors.append(str(exc))
        try:
            parsed = tomllib.loads(safe_file(codex).read_text(encoding="utf-8"))
            for field in ("name", "description", "developer_instructions"):
                if not isinstance(parsed.get(field), str) or not parsed[field].strip():
                    errors.append(f"{codex}: missing string field {field}")
            if role == "tester":
                instructions = parsed.get("developer_instructions", "")
                for marker in (
                    "установленный Codex skill `revmux`",
                    "dependency blocker",
                ):
                    if marker not in instructions:
                        errors.append(f"{codex}: missing revmux caller marker {marker}")
        except (PipelineError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"{codex}: {exc}")
        try:
            body = safe_file(claude).read_text(encoding="utf-8")
            if not body.startswith("---\n"):
                errors.append(f"{claude}: missing YAML frontmatter")
            for field in ("name:", "description:", "tools:"):
                if field not in body:
                    errors.append(f"{claude}: missing frontmatter field {field}")
            if role == "tester":
                for marker in (
                    "tools: Read, Grep, Glob, Edit, Write, Bash, Skill",
                    "skills:\n  - revmux:revmux",
                    "через `Skill`",
                    "dependency blocker",
                ):
                    if marker not in body:
                        errors.append(f"{claude}: missing revmux caller marker {marker}")
        except PipelineError as exc:
            errors.append(str(exc))

    required = (
        "SKILL.md",
        "agents/openai.yaml",
        "workflows/delivery-pipeline.md",
        "references/delivery-handoff.md",
        "references/case-state.md",
        "references/engineering-basis.md",
        "references/knowledge-map.md",
        "references/source-registry.md",
        "references/prompt-standard.md",
        "references/process-audit-integration.md",
        "references/revmux-review-backend.md",
        "revmux/prompts/profiles/comprehensive.md",
        "revmux/prompts/profiles/final.md",
        "scripts/delivery_case.py",
        "scripts/delivery_context.py",
        "scripts/prompt_audit.py",
        "scripts/revmux_review.py",
        "scripts/install.py",
    )
    for relative in required:
        try:
            safe_file(relative)
        except PipelineError as exc:
            errors.append(str(exc))

    try:
        workflow = safe_file("workflows/delivery-pipeline.md").read_text(encoding="utf-8")
        for phase in range(1, 11):
            if f"## Фаза {phase}." not in workflow:
                errors.append(f"delivery-pipeline.md: missing phase {phase}")
        for invariant in ("### Process YAGNI", "лестницу реализации", "protected floor", "root_owner"):
            if invariant not in workflow:
                errors.append(f"delivery-pipeline.md: missing simplicity invariant {invariant}")
    except PipelineError as exc:
        errors.append(str(exc))

    try:
        skill = safe_file("SKILL.md").read_text(encoding="utf-8")
        if len(skill.splitlines()) > 500:
            errors.append("SKILL.md exceeds 500 lines")
        for link in (
            "{baseDir}/workflows/delivery-pipeline.md",
            "{baseDir}/references/delivery-handoff.md",
            "{baseDir}/references/case-state.md",
            "{baseDir}/references/process-audit-integration.md",
            "{baseDir}/references/revmux-review-backend.md",
            "{baseDir}/references/knowledge-map.md",
            "{baseDir}/scripts/delivery_pipeline.py",
            "{baseDir}/scripts/delivery_context.py",
            "{baseDir}/scripts/delivery_case.py",
            "{baseDir}/scripts/prompt_audit.py",
            "{baseDir}/scripts/revmux_review.py",
        ):
            if link not in skill:
                errors.append(f"SKILL.md missing link: {link}")
        for invariant in ("engineering-context.json", "basis/<lane>.md", "materialize"):
            if invariant not in skill:
                errors.append(f"SKILL.md missing engineering-context invariant: {invariant}")
    except PipelineError as exc:
        errors.append(str(exc))

    public_suffixes = {".md", ".json", ".py", ".toml", ".yaml", ".yml"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in public_suffixes:
            continue
        if not is_public_package_path(path):
            continue
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        if any(marker in text for marker in HOME_MARKERS):
            errors.append(f"{relative} contains a hardcoded home path")
        for marker in PUBLIC_FORBIDDEN_MARKERS:
            if marker in text:
                errors.append(f"{relative} contains private project marker {marker!r}")

    if errors:
        raise PipelineError("\n".join(f"- {error}" for error in errors))
    return {
        "builtin_profiles": 1,
        "project_profiles": project_count,
        "contracts": len(ROLES),
        "runtime_adapters": len(ROLES) * 2,
        "workflows": 1,
    }


def payload(profile: Profile) -> dict[str, object]:
    shown_path = str(profile.path.relative_to(ROOT)) if profile.source == "generic" else str(PROFILE_RELATIVE)
    return {
        "profile_id": profile.profile_id,
        "capabilities": list(profile.capabilities),
        "source": profile.source,
        "profile_path": shown_path,
        "project_root": str(profile.project_root) if profile.project_root else None,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    detect = commands.add_parser("detect")
    detect.add_argument("--cwd", type=Path, default=Path.cwd())
    show = commands.add_parser("show-profile")
    show.add_argument("profile_id")
    show.add_argument("--cwd", type=Path, default=Path.cwd())
    validate_cmd = commands.add_parser("validate")
    validate_cmd.add_argument("--project-root", type=Path, action="append", default=[])
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "detect":
            print(json.dumps(payload(detect_profile(args.cwd)), ensure_ascii=False, indent=2))
        elif args.command == "show-profile":
            profile = select_profile(args.profile_id, args.cwd)
            print(json.dumps(payload(profile), ensure_ascii=False, indent=2))
            print("---")
            print(profile.path.read_text(encoding="utf-8"), end="")
        else:
            print(json.dumps(validate(args.project_root), ensure_ascii=False))
        return 0
    except (OSError, PipelineError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
