#!/usr/bin/env python3
"""Fail closed when the historical teacher-role term becomes an active contract."""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


LEGACY_PATTERN = re.compile(r"\btu" r"tor(?:s|ing)?\b", re.IGNORECASE)
SCANNED_ROOTS = ("src", "tests", "scripts", "mobile")
SCANNED_SUFFIXES = {".py", ".json", ".md", ".js", ".jsx", ".ts", ".tsx", ".yaml", ".yml"}
ALLOWED_PURPOSES = {"negative_input", "historical_reconciliation"}


@dataclass(frozen=True, order=True)
class Occurrence:
    file: str
    symbol: str
    literal: str


def _node_start(node: ast.AST) -> int:
    starts = [getattr(node, "lineno", 1)]
    starts.extend(getattr(item, "lineno", starts[0]) for item in getattr(node, "decorator_list", ()))
    return min(starts)


def _python_symbol(path: Path, line: int) -> str:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return "<module>"
    candidates: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        start = _node_start(node)
        end = getattr(node, "end_lineno", start)
        if start <= line <= end:
            candidates.append((end - start, node.name))
    return min(candidates)[1] if candidates else "<module>"


def collect_occurrences(root: Path) -> Counter[Occurrence]:
    found: Counter[Occurrence] = Counter()
    for base_name in SCANNED_ROOTS:
        base = root / base_name
        if not base.exists():
            continue
        for path in sorted(candidate for candidate in base.rglob("*") if candidate.is_file()):
            relative = path.relative_to(root).as_posix()
            if path.suffix.lower() not in SCANNED_SUFFIXES:
                continue
            for part in Path(relative).parts:
                for match in LEGACY_PATTERN.finditer(part):
                    found[Occurrence(relative, "<filename>", match.group(0))] += 1
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(lines, start=1):
                for match in LEGACY_PATTERN.finditer(line):
                    symbol = _python_symbol(path, line_number) if path.suffix == ".py" else f"line:{line_number}"
                    found[Occurrence(relative, symbol, match.group(0))] += 1
    return found


def load_allowlist(path: Path) -> Counter[Occurrence]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("entries"), list):
        raise ValueError("allowlist must contain version=1 and an entries array")
    allowed: Counter[Occurrence] = Counter()
    for entry in payload["entries"]:
        file = entry.get("file")
        symbol = entry.get("symbol")
        purpose = entry.get("purpose")
        literal = entry.get("literal")
        count = entry.get("count")
        if not all(isinstance(value, str) and value for value in (file, symbol, purpose, literal)):
            raise ValueError("every allowlist entry requires exact file, symbol, purpose, and literal")
        if purpose not in ALLOWED_PURPOSES:
            raise ValueError(f"invalid allowlist purpose: {purpose}")
        if any(marker in file for marker in ("*", "?", "[", "]")) or not file.startswith("tests/"):
            raise ValueError(f"broad or production-source exemption is forbidden: {file}")
        if symbol in {"*", "<module>", "<filename>"}:
            raise ValueError(f"allowlist entry must name a narrow test symbol: {file}")
        if not LEGACY_PATTERN.fullmatch(literal) or not isinstance(count, int) or count < 1:
            raise ValueError(f"invalid expected literal/count for {file}:{symbol}")
        occurrence = Occurrence(file, symbol, literal)
        if occurrence in allowed:
            raise ValueError(f"duplicate allowlist entry: {file}:{symbol}:{literal}")
        allowed[occurrence] = count
    return allowed


def check(root: Path, allowlist_path: Path) -> tuple[bool, str]:
    actual = collect_occurrences(root)
    allowed = load_allowlist(allowlist_path)
    unexpected = actual - allowed
    stale = allowed - actual
    lines = ["Teacher terminology semantic gate", f"allowlist entries used: {sum((actual & allowed).values())}"]
    for occurrence, count in sorted((actual & allowed).items()):
        lines.append(
            f"USED {occurrence.file}::{occurrence.symbol} literal={occurrence.literal!r} count={count}"
        )
    for occurrence, count in sorted(unexpected.items()):
        lines.append(
            f"ACTIVE {occurrence.file}::{occurrence.symbol} literal={occurrence.literal!r} count={count}"
        )
    for occurrence, count in sorted(stale.items()):
        lines.append(
            f"STALE {occurrence.file}::{occurrence.symbol} literal={occurrence.literal!r} count={count}"
        )
    passed = not unexpected and not stale
    lines.append("PASS" if passed else "FAIL")
    return passed, "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--allowlist", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    allowlist = args.allowlist if args.allowlist.is_absolute() else root / args.allowlist
    try:
        passed, report = check(root, allowlist)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Teacher terminology semantic gate\nINVALID {exc}\nFAIL")
        return 2
    print(report)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
