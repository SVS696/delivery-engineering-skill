#!/usr/bin/env python3
"""Deterministic literature router for Delivery Engineering."""

from __future__ import annotations

import argparse
import hashlib
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
ENGINEERING_CONTEXT_JSON = "engineering-context.json"
BASIS_DIRECTORY = "basis"
ENGINEERING_CONTEXT_SCHEMA = 1
LANE_ORDER = ("backend", "frontend", "test")
ROUTE_LIMITS = {"backend": 2, "frontend": 2, "test": 3}
MAX_BASIS_CHARS = 60_000


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


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def payload_fingerprint(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "fingerprint"}
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return text_sha256(encoded)


def normalize_assignments(assignments: dict[str, list[str]]) -> dict[str, list[str]]:
    unknown_lanes = set(assignments) - set(LANE_ORDER)
    if unknown_lanes:
        raise ContextError(f"unknown lanes: {', '.join(sorted(unknown_lanes))}")
    normalized: dict[str, list[str]] = {}
    available = route_index(fenced_json(MAP_PATH, MAP_MARKER))
    for lane in LANE_ORDER:
        if lane not in assignments:
            continue
        route_ids = assignments[lane]
        if not route_ids:
            raise ContextError(f"{lane}: at least one route is required")
        if len(route_ids) != len(set(route_ids)):
            raise ContextError(f"{lane}: route ids must be unique")
        if len(route_ids) > ROUTE_LIMITS[lane]:
            raise ContextError(f"{lane}: at most {ROUTE_LIMITS[lane]} routes are allowed")
        unknown_routes = set(route_ids) - set(available)
        if unknown_routes:
            raise ContextError(
                f"{lane}: unknown routes: {', '.join(sorted(unknown_routes))}"
            )
        incompatible = [
            route_id
            for route_id in route_ids
            if lane not in available[route_id].get("lanes", [])
        ]
        if incompatible:
            raise ContextError(
                f"{lane}: incompatible routes: {', '.join(incompatible)}"
            )
        normalized[lane] = list(route_ids)
    if not normalized:
        raise ContextError("at least one lane assignment is required")
    return normalized


def build_engineering_context(
    assignments: dict[str, list[str]],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Build deterministic, lane-isolated literature snapshots."""

    normalized = normalize_assignments(assignments)
    routes = route_index(fenced_json(MAP_PATH, MAP_MARKER))
    payload_assignments: dict[str, Any] = {}
    contents: dict[str, str] = {}
    for lane, route_ids in normalized.items():
        chunks = [
            f"# Engineering basis: {lane}",
            (
                "Эта выжимка — проверочная линза для назначенной lane. Она не "
                "создаёт scope и не перекрывает требования, проектные инструкции, "
                "конфиги и устойчивые соглашения кодовой базы."
            ),
        ]
        section_meta: list[dict[str, Any]] = []
        for route_id in route_ids:
            route = routes[route_id]
            chunks.append(f"## Route: {route_id}\n\n**Когда:** {route.get('when', '')}")
            for target in route.get("distilled", []):
                if not isinstance(target, dict):
                    raise ContextError(f"{route_id}: target must be an object")
                relative = target.get("file", "")
                title = target.get("heading")
                if not isinstance(title, str):
                    raise ContextError(f"{route_id}: target heading must be a string")
                section = extract_heading(safe_file(relative), title)
                chunks.append(section)
                section_meta.append(
                    {
                        "route_id": route_id,
                        "file": relative,
                        "heading": title,
                        "sha256": text_sha256(section),
                        "characters": len(section),
                    }
                )
        content = "\n\n".join(chunks).strip() + "\n"
        if len(content) > MAX_BASIS_CHARS:
            raise ContextError(
                f"{lane}: materialized basis exceeds {MAX_BASIS_CHARS} characters"
            )
        content_path = f"{BASIS_DIRECTORY}/{lane}.md"
        contents[lane] = content
        payload_assignments[lane] = {
            "route_ids": route_ids,
            "content_path": content_path,
            "content_sha256": text_sha256(content),
            "characters": len(content),
            "sections": section_meta,
        }
    payload: dict[str, Any] = {
        "schema": ENGINEERING_CONTEXT_SCHEMA,
        "assignments": payload_assignments,
    }
    payload["fingerprint"] = payload_fingerprint(payload)
    return payload, contents


def validate_engineering_context(
    payload: dict[str, Any],
    contents: dict[str, str],
    *,
    expected_lanes: set[str] | None = None,
    verify_sources: bool = False,
) -> None:
    if payload.get("schema") != ENGINEERING_CONTEXT_SCHEMA:
        raise ContextError("unsupported engineering context schema")
    assignments = payload.get("assignments")
    if not isinstance(assignments, dict) or not assignments:
        raise ContextError("engineering context assignments must be a non-empty object")
    actual_lanes = set(assignments)
    if expected_lanes is not None and actual_lanes != expected_lanes:
        raise ContextError(
            "engineering context lanes do not match case lanes: "
            f"expected {sorted(expected_lanes)}, got {sorted(actual_lanes)}"
        )
    if set(contents) != actual_lanes:
        raise ContextError("engineering context content set does not match assignments")
    normalized: dict[str, list[str]] = {}
    for lane, item in assignments.items():
        if lane not in LANE_ORDER or not isinstance(item, dict):
            raise ContextError(f"invalid engineering context lane: {lane}")
        route_ids = item.get("route_ids")
        if not isinstance(route_ids, list) or not all(
            isinstance(route_id, str) for route_id in route_ids
        ):
            raise ContextError(f"{lane}: route_ids must be a string array")
        normalized[lane] = route_ids
        expected_path = f"{BASIS_DIRECTORY}/{lane}.md"
        if item.get("content_path") != expected_path:
            raise ContextError(f"{lane}: invalid content path")
        content = contents[lane]
        if item.get("content_sha256") != text_sha256(content):
            raise ContextError(f"{lane}: content hash mismatch")
        if item.get("characters") != len(content):
            raise ContextError(f"{lane}: character count mismatch")
    if payload.get("fingerprint") != payload_fingerprint(payload):
        raise ContextError("engineering context fingerprint mismatch")
    normalize_assignments(normalized)
    if verify_sources:
        rebuilt_payload, rebuilt_contents = build_engineering_context(normalized)
        if payload != rebuilt_payload or contents != rebuilt_contents:
            raise ContextError("engineering context differs from current routed sources")


def write_engineering_context(
    root: Path, payload: dict[str, Any], contents: dict[str, str]
) -> None:
    case_root = root.expanduser().resolve()
    metadata_path = case_root / ENGINEERING_CONTEXT_JSON
    basis_root = case_root / BASIS_DIRECTORY
    targets = [metadata_path, *(basis_root / f"{lane}.md" for lane in contents)]
    if any(path.exists() for path in targets) or (basis_root.exists() and any(basis_root.iterdir())):
        raise ContextError("refusing to overwrite existing engineering context")
    case_root.mkdir(parents=True, exist_ok=True)
    basis_root.mkdir(exist_ok=True)
    for lane, content in contents.items():
        (basis_root / f"{lane}.md").write_text(content, encoding="utf-8")
    metadata_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def parse_assignment(value: str) -> tuple[str, str]:
    lane, separator, route_id = value.partition("=")
    if not separator or not lane or not route_id:
        raise ContextError("assignment must have form lane=route-id")
    return lane, route_id


def validate() -> dict[str, int]:
    errors: list[str] = []
    try:
        data = fenced_json(MAP_PATH, MAP_MARKER)
        index = route_index(data)
        if data.get("default_route") not in index:
            errors.append("default_route does not resolve")
        target_count = 0
        for route_id, route in index.items():
            lanes = route.get("lanes")
            if (
                not isinstance(lanes, list)
                or not lanes
                or not all(isinstance(lane, str) and lane in LANE_ORDER for lane in lanes)
                or len(lanes) != len(set(lanes))
            ):
                errors.append(f"{route_id}: lanes must be a non-empty unique known-lane array")
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
    materialize = commands.add_parser("materialize")
    materialize.add_argument(
        "--assign",
        action="append",
        required=True,
        metavar="LANE=ROUTE",
        help="Repeat up to twice for BE/FE and three times for test",
    )
    materialize.add_argument("--write", type=Path, required=True, metavar="CASE_ROOT")
    commands.add_parser("validate")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "route":
            print(json.dumps(choose(args.task), ensure_ascii=False, indent=2))
        elif args.command == "extract":
            print(extract(args.route), end="")
        elif args.command == "materialize":
            assignments: dict[str, list[str]] = {}
            for value in args.assign:
                lane, route_id = parse_assignment(value)
                assignments.setdefault(lane, []).append(route_id)
            payload, contents = build_engineering_context(assignments)
            validate_engineering_context(payload, contents, verify_sources=True)
            write_engineering_context(args.write, payload, contents)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(validate(), ensure_ascii=False))
        return 0
    except (OSError, ContextError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
