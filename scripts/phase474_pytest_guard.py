#!/usr/bin/env python3
"""Strict, source-bound pytest accounting for Phase 474 formal verification."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
from typing import Any


SCHEMA_VERSION = "stoa.phase474.pytest-nodes.v1"
DEFAULT_SEED = 4740718
SUPPORTED_CLOCKS = frozenset(
    {
        "2026-07-01T12:00:00Z",
        "2035-01-15T12:00:00Z",
    }
)
NON_PASS_OUTCOMES = ("failed", "error", "skipped", "xfail", "xpass")
_PHASE_ORDER = {"setup": 0, "call": 1, "teardown": 2}


class StrictOutcomeError(ValueError):
    """The formal pytest observation is incomplete or contains a non-pass outcome."""


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def report_record(report: Any) -> dict[str, Any]:
    """Reduce a pytest report to closed, non-sensitive outcome facts."""
    when = getattr(report, "when", None)
    outcome = getattr(report, "outcome", None)
    if when not in _PHASE_ORDER or outcome not in {"passed", "failed", "skipped"}:
        raise StrictOutcomeError("pytest emitted an unknown report state")
    wasxfail = getattr(report, "wasxfail", None)
    longrepr = str(getattr(report, "longrepr", ""))
    return {
        "when": when,
        "outcome": outcome,
        "wasxfail": wasxfail is not None,
        "xpass_strict": bool(
            outcome == "failed"
            and (
                bool(getattr(report, "failed", False))
                and "XPASS(strict)" in longrepr
            )
        ),
    }


def classify_outcome(phases: Sequence[Mapping[str, Any]]) -> str:
    """Classify all setup/call/teardown reports into one closed node outcome."""
    if not phases:
        return "error"
    if any(bool(phase.get("xpass_strict")) for phase in phases):
        return "xpass"
    if any(phase.get("wasxfail") and phase.get("outcome") == "passed" for phase in phases):
        return "xpass"
    if any(phase.get("wasxfail") and phase.get("outcome") == "skipped" for phase in phases):
        return "xfail"
    if any(
        phase.get("when") in {"setup", "teardown"} and phase.get("outcome") == "failed"
        for phase in phases
    ):
        return "error"
    if any(phase.get("when") == "call" and phase.get("outcome") == "failed" for phase in phases):
        return "failed"
    if any(phase.get("outcome") == "skipped" for phase in phases):
        return "skipped"
    if all(phase.get("outcome") == "passed" for phase in phases):
        return "passed"
    return "error"


def build_manifest(
    *,
    nodes: Sequence[Mapping[str, Any]],
    clock: str,
    seed: int,
    runtime: str,
    lock_sha256: str,
) -> dict[str, Any]:
    """Build a deterministic manifest and reject empty or non-pass observations."""
    if not nodes:
        raise StrictOutcomeError("empty pytest collection is forbidden")
    ordered = sorted((dict(node) for node in nodes), key=lambda node: str(node.get("node_id")))
    node_ids = [node.get("node_id") for node in ordered]
    if any(not isinstance(node_id, str) or not node_id for node_id in node_ids):
        raise StrictOutcomeError("pytest collection contains a malformed node id")
    if len(set(node_ids)) != len(node_ids):
        raise StrictOutcomeError("pytest collection contains duplicate node ids")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise StrictOutcomeError("deterministic seed is malformed")
    if not isinstance(runtime, str) or not runtime.startswith("3.12."):
        raise StrictOutcomeError("formal Python runtime is not 3.12")
    if (
        not isinstance(lock_sha256, str)
        or len(lock_sha256) != 64
        or any(character not in "0123456789abcdef" for character in lock_sha256)
    ):
        raise StrictOutcomeError("lock digest is malformed")

    counts = {
        "total": len(ordered),
        "passed": 0,
        "failed": 0,
        "error": 0,
        "skipped": 0,
        "xfail": 0,
        "xpass": 0,
    }
    for node in ordered:
        outcome = node.get("outcome")
        if outcome not in counts or outcome == "total":
            raise StrictOutcomeError("pytest node has an unknown outcome")
        counts[outcome] += 1

    offenders = [name for name in NON_PASS_OUTCOMES if counts[name]]
    if offenders:
        raise StrictOutcomeError("non-pass pytest outcomes: " + ", ".join(offenders))

    collection = "".join(f"{node_id}\n" for node_id in node_ids).encode("utf-8")
    return {
        "schema_version": SCHEMA_VERSION,
        "clock": clock,
        "seed": seed,
        "runtime": runtime,
        "lock_sha256": lock_sha256,
        "collection_sha256": sha256(collection).hexdigest(),
        "nodes": ordered,
        "counts": counts,
    }


def hermetic_environment(
    source: Mapping[str, str], *, nonexistent_root: Path
) -> dict[str, str]:
    """Return an environment without ambient cloud credentials or proxy escape paths."""
    environment = dict(source)
    denied_exact = {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_SECURITY_TOKEN",
        "AWS_PROFILE",
        "AWS_DEFAULT_PROFILE",
        "AWS_ROLE_ARN",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "NO_PROXY",
        "no_proxy",
    }
    for name in denied_exact:
        environment.pop(name, None)
    environment["AWS_EC2_METADATA_DISABLED"] = "true"
    environment["AWS_SHARED_CREDENTIALS_FILE"] = str(nonexistent_root / "credentials")
    environment["AWS_CONFIG_FILE"] = str(nonexistent_root / "config")
    return environment


class _PytestGuardPlugin:
    def __init__(self, manifest_path: Path) -> None:
        self.manifest_path = manifest_path
        self.node_ids: list[str] = []
        self.reports: dict[str, list[dict[str, Any]]] = {}

    def pytest_collection_modifyitems(self, items: Sequence[Any]) -> None:
        self.node_ids = sorted(item.nodeid for item in items)

    def pytest_runtest_logreport(self, report: Any) -> None:
        self.reports.setdefault(report.nodeid, []).append(report_record(report))

    def pytest_sessionfinish(self, session: Any) -> None:
        nodes = []
        for node_id in self.node_ids:
            phases = sorted(
                self.reports.get(node_id, []),
                key=lambda phase: _PHASE_ORDER[str(phase["when"])],
            )
            nodes.append(
                {
                    "node_id": node_id,
                    "outcome": classify_outcome(phases),
                    "phases": phases,
                }
            )

        try:
            clock = os.environ["STOA_PHASE474_CLOCK"]
            seed = int(os.environ["STOA_PHASE474_SEED"])
            lock_path = Path(os.environ.get("STOA_PHASE474_LOCK", "uv.lock"))
            manifest = build_manifest(
                nodes=nodes,
                clock=clock,
                seed=seed,
                runtime=platform.python_version(),
                lock_sha256=_sha256_file(lock_path),
            )
        except (KeyError, OSError, ValueError, StrictOutcomeError) as exc:
            session.exitstatus = 1
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "status": "FAIL",
                "reason": type(exc).__name__,
            }

        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def pytest_configure(config: Any) -> None:
    """Register strict accounting only for an explicitly formal Phase 474 run."""
    manifest_path = os.environ.get("STOA_PHASE474_MANIFEST")
    if not manifest_path:
        return
    config.pluginmanager.register(
        _PytestGuardPlugin(Path(manifest_path)),
        "stoa-phase474-strict-accounting",
    )
