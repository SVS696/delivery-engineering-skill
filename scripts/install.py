#!/usr/bin/env python3
"""Install Delivery Engineering discovery links without overwriting files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parent.parent
AGENTS = ("delivery-backend", "delivery-frontend", "delivery-tester")
MANIFEST_NAME = ".delivery-engineering-agent-copies.json"
LINK = "link"
COPY = "copy"


class InstallerError(RuntimeError):
    """Unsafe or incomplete installation state."""


@dataclass(frozen=True)
class LinkSpec:
    source: Path
    target: Path
    mode: str = LINK


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
        specs.append(
            LinkSpec(
                root / "agents" / "codex" / f"{name}.toml",
                home / ".codex" / "agents" / f"{name}.toml",
                COPY,
            )
        )
        specs.append(LinkSpec(root / "agents" / "claude" / f"{name}.md", home / ".claude" / "agents" / f"{name}.md"))
    return specs


def manifest_path(user_home: Path) -> Path:
    """Return the ownership manifest for managed Codex agent copies."""
    return user_home.expanduser().resolve() / ".codex" / "agents" / MANIFEST_NAME


def digest(path: Path) -> str:
    """Return a stable content digest for a regular file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(user_home: Path) -> dict[str, str]:
    """Load managed-copy hashes and reject ambiguous manifest state."""
    path = manifest_path(user_home)
    if not path.exists() and not path.is_symlink():
        return {}
    if path.is_symlink() or not path.is_file():
        raise InstallerError(f"Managed-copy manifest is not a regular file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallerError(f"Cannot read managed-copy manifest {path}: {exc}") from exc
    if payload.get("schema") != 1 or not isinstance(payload.get("files"), dict):
        raise InstallerError(f"Unsupported managed-copy manifest: {path}")
    files = payload["files"]
    if not all(isinstance(name, str) and isinstance(value, str) for name, value in files.items()):
        raise InstallerError(f"Invalid managed-copy manifest entries: {path}")
    return files


def atomic_copy(source: Path, target: Path) -> None:
    """Replace a target with a regular-file copy without exposing partial content."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent,
            prefix=f".{target.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(source.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(source.stat().st_mode & 0o777)
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def write_manifest(user_home: Path, files: dict[str, str]) -> None:
    """Atomically record the exact Codex agent copies managed by this installer."""
    path = manifest_path(user_home)
    payload = json.dumps({"schema": 1, "files": files}, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def inspect_links(skill_root: Path, user_home: Path) -> list[LinkState]:
    managed = load_manifest(user_home)
    states: list[LinkState] = []
    for spec in link_specs(skill_root, user_home):
        source = spec.source.resolve()
        if not source.exists():
            states.append(LinkState(spec, "source-missing", str(source)))
        elif spec.target.is_symlink():
            if spec.target.resolve(strict=False) == source:
                status = "installed" if spec.mode == LINK else "migration-required"
                states.append(LinkState(spec, status, str(source)))
            else:
                states.append(LinkState(spec, "conflict", f"points to {spec.target.resolve(strict=False)}"))
        elif spec.target.exists() and spec.mode == COPY:
            if not spec.target.is_file():
                states.append(LinkState(spec, "conflict", "copy target is not a regular file"))
                continue
            source_digest = digest(source)
            target_digest = digest(spec.target)
            managed_digest = managed.get(spec.target.name)
            if target_digest == source_digest and managed_digest == target_digest:
                states.append(LinkState(spec, "installed", source_digest))
            elif target_digest == source_digest:
                states.append(LinkState(spec, "adoption-required", source_digest))
            elif managed_digest == target_digest:
                states.append(
                    LinkState(
                        spec,
                        "refresh-required",
                        f"{target_digest} -> {source_digest}",
                    )
                )
            else:
                states.append(
                    LinkState(
                        spec,
                        "conflict",
                        "regular file differs from source and is not an unchanged managed copy",
                    )
                )
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
        if state.status == "installed":
            continue
        if state.spec.mode == COPY:
            atomic_copy(state.spec.source.resolve(), state.spec.target)
        elif state.status == "missing":
            state.spec.target.parent.mkdir(parents=True, exist_ok=True)
            state.spec.target.symlink_to(
                state.spec.source.resolve(),
                target_is_directory=state.spec.source.is_dir(),
            )

    copies = {
        spec.target.name: digest(spec.target)
        for spec in link_specs(skill_root, user_home)
        if spec.mode == COPY
    }
    write_manifest(user_home, copies)
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
            return 1 if any(item.status != "installed" for item in states) else 0
        states = install(args.skill_root, args.home, dry_run=args.dry_run)
        print_states(states)
        return 0
    except (OSError, InstallerError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
