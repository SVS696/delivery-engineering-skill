#!/usr/bin/env python3
"""Static audit of role contracts and thin runtime adapters."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections import Counter
from pathlib import Path


CONTRACT_RE = re.compile(r"agents/contracts/([a-z0-9-]+)\.md")
VAGUE_PATTERNS = ("проанализируй всё", "исследуй всё", "сделай качественно", "не останавливайся никогда")


class PromptAuditError(RuntimeError):
    """Prompt package violates a structural prompt rule."""


def frontmatter_name(text: str, source: Path) -> str:
    if not text.startswith("---\n"):
        raise PromptAuditError(f"{source}: missing frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise PromptAuditError(f"{source}: unclosed frontmatter")
    match = re.search(r"^name:\s*([^\n]+)$", parts[1], re.MULTILINE)
    if not match:
        raise PromptAuditError(f"{source}: missing name")
    return match.group(1).strip().strip("\"'")


def audit(skill_root: Path) -> dict[str, int]:
    root = skill_root.expanduser().resolve()
    errors: list[str] = []
    contract_dir = root / "agents" / "contracts"
    codex_dir = root / "agents" / "codex"
    claude_dir = root / "agents" / "claude"
    contracts = sorted(contract_dir.glob("*.md"))
    codex_adapters = sorted(codex_dir.glob("*.toml"))
    claude_adapters = sorted(claude_dir.glob("*.md"))
    lane_basis = {
        "backend": "basis/backend.md",
        "frontend": "basis/frontend.md",
        "tester": "basis/test.md",
    }
    delivery_package = (root / "references" / "engineering-basis.md").is_file()
    if not contracts:
        errors.append("no role contracts")

    contract_names = {path.stem for path in contracts}
    for path in contracts:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(root)
        if "## Назначение" not in text or "## Выход" not in text:
            errors.append(f"{relative}: missing purpose or output section")
        if "## Вход" not in text and "## Общие границы" not in text:
            errors.append(f"{relative}: missing explicit input/boundary section")
        if "Не " not in text and "Запрещено" not in text:
            errors.append(f"{relative}: missing negative authority boundary")
        if len(text.splitlines()) > 120:
            errors.append(f"{relative}: contract exceeds 120 lines")
        lowered = text.casefold()
        for pattern in VAGUE_PATTERNS:
            if pattern in lowered:
                errors.append(f"{relative}: vague unbounded instruction {pattern!r}")
        if delivery_package and path.stem in lane_basis:
            for required in ("engineering-context.json", lane_basis[path.stem]):
                if required not in text:
                    errors.append(f"{relative}: missing pinned lane basis {required}")

    references: Counter[str] = Counter()
    for path in codex_adapters:
        relative = path.relative_to(root)
        try:
            parsed = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            errors.append(f"{relative}: invalid TOML: {exc}")
            continue
        name = parsed.get("name")
        instructions = parsed.get("developer_instructions")
        if name != path.stem:
            errors.append(f"{relative}: name must match filename")
        if not isinstance(instructions, str):
            errors.append(f"{relative}: missing developer_instructions")
            continue
        matches = CONTRACT_RE.findall(instructions)
        if len(matches) != 1:
            errors.append(f"{relative}: adapter must reference exactly one contract")
            continue
        contract = matches[0]
        references[f"codex:{contract}"] += 1
        if contract not in contract_names:
            errors.append(f"{relative}: unknown contract {contract}")
        if "полностью прочитай" not in instructions:
            errors.append(f"{relative}: must require complete contract read")
        if not any(token in instructions for token in ("только передан", "Работай только", "Используй только")):
            errors.append(f"{relative}: missing bounded input context")
        if "Верни" not in instructions and "верни" not in instructions:
            errors.append(f"{relative}: missing explicit return instruction")
        contract_text = (contract_dir / f"{contract}.md").read_text(encoding="utf-8") if contract in contract_names else ""
        if ("## Режим" in contract_text or "## Режимы" in contract_text) and "режим" not in instructions.casefold():
            errors.append(f"{relative}: multi-mode contract without explicit mode")
        if len(instructions) > 1400:
            errors.append(f"{relative}: adapter exceeds 1400 characters")
        if delivery_package and contract in lane_basis:
            for required in ("engineering-context.json", lane_basis[contract]):
                if required not in instructions:
                    errors.append(f"{relative}: missing pinned lane basis {required}")

    for path in claude_adapters:
        relative = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        compact = " ".join(text.split())
        try:
            name = frontmatter_name(text, path)
        except PromptAuditError as exc:
            errors.append(str(exc))
            continue
        if name != path.stem:
            errors.append(f"{relative}: name must match filename")
        matches = CONTRACT_RE.findall(text)
        if len(matches) != 1:
            errors.append(f"{relative}: adapter must reference exactly one contract")
            continue
        contract = matches[0]
        references[f"claude:{contract}"] += 1
        if contract not in contract_names:
            errors.append(f"{relative}: unknown contract {contract}")
        if "полностью прочитай" not in compact:
            errors.append(f"{relative}: must require complete contract read")
        if not any(token in compact for token in ("только передан", "Работай только", "Используй только")):
            errors.append(f"{relative}: missing bounded input context")
        if "Верни" not in compact and "верни" not in compact:
            errors.append(f"{relative}: missing explicit return instruction")
        contract_text = (contract_dir / f"{contract}.md").read_text(encoding="utf-8") if contract in contract_names else ""
        if ("## Режим" in contract_text or "## Режимы" in contract_text) and "режим" not in compact.casefold():
            errors.append(f"{relative}: multi-mode contract without explicit mode")
        if len(text) > 1600:
            errors.append(f"{relative}: adapter exceeds 1600 characters")
        if delivery_package and contract in lane_basis:
            for required in ("engineering-context.json", lane_basis[contract]):
                if required not in text:
                    errors.append(f"{relative}: missing pinned lane basis {required}")

    for contract in sorted(contract_names):
        if references[f"codex:{contract}"] != 1:
            errors.append(f"contract {contract}: expected one Codex adapter")
        if references[f"claude:{contract}"] != 1:
            errors.append(f"contract {contract}: expected one Claude adapter")

    if errors:
        raise PromptAuditError("\n".join(f"- {error}" for error in errors))
    return {
        "contracts": len(contracts),
        "codex_adapters": len(codex_adapters),
        "claude_adapters": len(claude_adapters),
        "checks": 10,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--skill-root", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        print(json.dumps(audit(args.skill_root), ensure_ascii=False))
        return 0
    except (OSError, PromptAuditError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
