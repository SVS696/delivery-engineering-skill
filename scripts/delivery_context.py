#!/usr/bin/env python3
"""Deterministic literature router for Delivery Engineering."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT / "references" / "knowledge-map.md"
SOURCE_PATH = ROOT / "references" / "source-registry.md"
MAP_MARKER = "<!-- delivery-engineering:routes -->"
SOURCE_MARKER = "<!-- delivery-engineering:sources -->"
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
WORD_RE = re.compile(r"[0-9a-zа-яё]+", re.IGNORECASE)


class ContextError(RuntimeError):
    """Knowledge routing or extraction failed."""


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().replace("ё", "е").split())


def terms(value: str) -> set[str]:
    result: set[str] = set()
    for token in WORD_RE.findall(normalize(value)):
        if len(token) <= 3:
            result.add(token)
        elif re.fullmatch(r"[а-я]+", token):
            result.add(token[:5])
        else:
            result.add(token)
    return result


def fenced_json(path: Path, marker: str) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    offset = text.find(marker)
    if offset < 0:
        raise ContextError(f"{path}: missing marker {marker}")
    match = re.search(r"```json\s*(\{.*?\})\s*```", text[offset:], re.DOTALL)
    if not match:
        raise ContextError(f"{path}: missing fenced JSON after marker")
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ContextError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ContextError(f"{path}: JSON root must be an object")
    return data


def safe_file(relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ContextError("Target file must be a non-empty relative path")
    path = (ROOT / relative).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ContextError(f"Target escapes skill root: {relative}") from exc
    if not path.is_file():
        raise ContextError(f"Target file does not exist: {relative}")
    return path


def headings(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    found: list[dict[str, Any]] = []
    fence: str | None = None
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        token = re.match(r"(```+|~~~+)", stripped)
        if token:
            if fence is None:
                fence = token.group(1)[0]
            elif token.group(1)[0] == fence:
                fence = None
            continue
        if fence:
            continue
        match = HEADING_RE.match(line)
        if match:
            found.append({"title": match.group(2).strip(), "level": len(match.group(1)), "start": index})
    for position, heading in enumerate(found):
        heading["end"] = len(lines)
        for following in found[position + 1 :]:
            if following["level"] <= heading["level"]:
                heading["end"] = following["start"]
                break
    return found


def extract_heading(path: Path, title: str) -> str:
    text = path.read_text(encoding="utf-8")
    matches = [item for item in headings(text) if normalize(item["title"]) == normalize(title)]
    if len(matches) != 1:
        raise ContextError(
            f"{path.relative_to(ROOT)} heading {title!r} resolved {len(matches)} times"
        )
    item = matches[0]
    return "\n".join(text.splitlines()[item["start"] : item["end"]]).strip()


def route_index(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = data.get("routes")
    if not isinstance(raw, list):
        raise ContextError("routes must be an array")
    result: dict[str, dict[str, Any]] = {}
    for route in raw:
        if not isinstance(route, dict) or not isinstance(route.get("id"), str):
            raise ContextError("every route must have a string id")
        if route["id"] in result:
            raise ContextError(f"duplicate route id: {route['id']}")
        result[route["id"]] = route
    return result


def choose(task: str) -> list[dict[str, Any]]:
    data = fenced_json(MAP_PATH, MAP_MARKER)
    index = route_index(data)
    task_terms = terms(task)
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for order, route in enumerate(index.values()):
        score = 0
        matches: list[str] = []
        for signal in route.get("signals", []):
            signal_terms = terms(signal)
            if signal_terms and signal_terms <= task_terms:
                score += max(1, len(signal_terms))
                matches.append(signal)
        if score:
            selected = dict(route)
            selected["score"] = score
            selected["matched_signals"] = matches
            ranked.append((score, -order, selected))
    ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
    if ranked:
        return [item[2] for item in ranked]
    default = data.get("default_route")
    if default not in index:
        raise ContextError("default_route does not resolve")
    selected = dict(index[default])
    selected["score"] = 0
    selected["matched_signals"] = []
    return [selected]


def extract(route_id: str) -> str:
    index = route_index(fenced_json(MAP_PATH, MAP_MARKER))
    route = index.get(route_id)
    if route is None:
        raise ContextError(f"unknown route: {route_id}")
    chunks = [f"# Route: {route_id}"]
    for target in route.get("distilled", []):
        if not isinstance(target, dict):
            raise ContextError(f"{route_id}: target must be an object")
        path = safe_file(target.get("file", ""))
        title = target.get("heading")
        if not isinstance(title, str):
            raise ContextError(f"{route_id}: target heading must be a string")
        chunks.append(extract_heading(path, title))
    return "\n\n".join(chunks) + "\n"


def validate() -> dict[str, int]:
    errors: list[str] = []
    try:
        data = fenced_json(MAP_PATH, MAP_MARKER)
        index = route_index(data)
        if data.get("default_route") not in index:
            errors.append("default_route does not resolve")
        target_count = 0
        for route_id, route in index.items():
            signals = route.get("signals")
            if not isinstance(signals, list) or not all(isinstance(item, str) for item in signals):
                errors.append(f"{route_id}: signals must be a string array")
            distilled = route.get("distilled")
            if not isinstance(distilled, list) or not distilled:
                errors.append(f"{route_id}: distilled must be non-empty")
                continue
            for target in distilled:
                target_count += 1
                try:
                    path = safe_file(target.get("file", ""))
                    title = target.get("heading")
                    if not isinstance(title, str):
                        raise ContextError("heading must be a string")
                    extract_heading(path, title)
                except (AttributeError, ContextError) as exc:
                    errors.append(f"{route_id}: {exc}")
        source_data = fenced_json(SOURCE_PATH, SOURCE_MARKER)
        sources = source_data.get("sources")
        if not isinstance(sources, list) or not sources:
            errors.append("source registry must contain sources")
            source_count = 0
        else:
            ids = [item.get("id") for item in sources if isinstance(item, dict)]
            source_count = len(ids)
            if len(ids) != len(sources) or any(not isinstance(item, str) for item in ids):
                errors.append("every source must have a string id")
            if len(set(ids)) != len(ids):
                errors.append("source ids must be unique")
            for item in sources:
                if not isinstance(item, dict):
                    continue
                for field in ("title", "version", "url", "access", "used"):
                    if field not in item:
                        errors.append(f"source {item.get('id')}: missing {field}")
        for path in (ROOT / "references").glob("native-*.md"):
            if len(path.read_text(encoding="utf-8").splitlines()) > 400:
                errors.append(f"{path.relative_to(ROOT)} exceeds 400 lines")
    except (OSError, ContextError) as exc:
        errors.append(str(exc))
        index = {}
        target_count = 0
        source_count = 0
    if errors:
        raise ContextError("\n".join(f"- {error}" for error in errors))
    return {"routes": len(index), "targets": target_count, "sources": source_count}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    route = commands.add_parser("route")
    route.add_argument("--task", required=True)
    extract_cmd = commands.add_parser("extract")
    extract_cmd.add_argument("--route", required=True)
    commands.add_parser("validate")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "route":
            print(json.dumps(choose(args.task), ensure_ascii=False, indent=2))
        elif args.command == "extract":
            print(extract(args.route), end="")
        else:
            print(json.dumps(validate(), ensure_ascii=False))
        return 0
    except (OSError, ContextError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

