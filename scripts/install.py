#!/usr/bin/env python3
"""Install Delivery Engineering discovery links without overwriting files."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parent.parent
AGENTS = ("delivery-backend", "delivery-frontend", "delivery-tester")


class InstallerError(RuntimeError):
    """Unsafe or incomplete installation state."""


@dataclass(frozen=True)
class LinkSpec:
    source: Path
    target: Path


@dataclass(frozen=True)
class LinkState:
    spec: LinkSpec
    status: str
    detail: str


def link_specs(skill_root: Path, user_home: Path) -> list[LinkSpec]:
    root = skill_root.expanduser().resolve()
    home = user_home.expanduser().resolve()
    specs = [
        LinkSpec(root, home / ".agents" / "skills" / "delivery-engineering"),
        LinkSpec(root, home / ".claude" / "skills" / "delivery-engineering"),
    ]
    for name in AGENTS:
        specs.append(LinkSpec(root / "agents" / "codex" / f"{name}.toml", home / ".codex" / "agents" / f"{name}.toml"))
        specs.append(LinkSpec(root / "agents" / "claude" / f"{name}.md", home / ".claude" / "agents" / f"{name}.md"))
    return specs


def inspect_links(skill_root: Path, user_home: Path) -> list[LinkState]:
    states: list[LinkState] = []
    for spec in link_specs(skill_root, user_home):
        source = spec.source.resolve()
        if not source.exists():
            states.append(LinkState(spec, "source-missing", str(source)))
        elif spec.target.is_symlink():
            if spec.target.resolve(strict=False) == source:
                states.append(LinkState(spec, "installed", str(source)))
            else:
                states.append(LinkState(spec, "conflict", f"points to {spec.target.resolve(strict=False)}"))
        elif spec.target.exists():
            states.append(LinkState(spec, "conflict", "target exists and is not a symlink"))
        else:
            states.append(LinkState(spec, "missing", str(source)))
    return states


def install(skill_root: Path, user_home: Path, *, dry_run: bool = False) -> list[LinkState]:
    states = inspect_links(skill_root, user_home)
    blockers = [state for state in states if state.status in {"source-missing", "conflict"}]
    if blockers:
        detail = "\n".join(f"- {item.status}: {item.spec.target} ({item.detail})" for item in blockers)
        raise InstallerError(f"Preflight failed; no links changed:\n{detail}")
    if dry_run:
        return states
    for state in states:
        if state.status != "missing":
            continue
        state.spec.target.parent.mkdir(parents=True, exist_ok=True)
        state.spec.target.symlink_to(state.spec.source.resolve(), target_is_directory=state.spec.source.is_dir())
    verified = inspect_links(skill_root, user_home)
    incomplete = [state for state in verified if state.status != "installed"]
    if incomplete:
        detail = "\n".join(f"- {item.status}: {item.spec.target} ({item.detail})" for item in incomplete)
        raise InstallerError(f"Post-install verification failed:\n{detail}")
    return verified


def print_states(states: list[LinkState]) -> None:
    for state in states:
        print(f"{state.status}\t{state.spec.target}\t{state.detail}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--skill-root", type=Path, default=DEFAULT_ROOT)
    root.add_argument("--home", type=Path, default=Path.home())
    root.add_argument("--check", action="store_true")
    root.add_argument("--dry-run", action="store_true")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.check:
            states = inspect_links(args.skill_root, args.home)
            print_states(states)
            if any(item.status in {"source-missing", "conflict"} for item in states):
                return 2
            return 1 if any(item.status == "missing" for item in states) else 0
        states = install(args.skill_root, args.home, dry_run=args.dry_run)
        print_states(states)
        return 0
    except (OSError, InstallerError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

