"""Opt-in pytest guard for strict, machine-readable Phase 473 outcomes."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Any

from pytest import ExitCode


SCHEMA_VERSION = "phase-473-pytest-nodes.v1"
_reports: dict[str, list[dict[str, Any]]] = defaultdict(list)


def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup("phase473-evidence")
    group.addoption(
        "--phase473-node-manifest",
        action="store",
        dest="phase473_node_manifest",
        metavar="PATH",
        help="write deterministic strict Phase 473 node outcomes to PATH",
    )


def pytest_configure(config: Any) -> None:
    _reports.clear()


def pytest_runtest_logreport(report: Any) -> None:
    wasxfail = getattr(report, "wasxfail", None)
    _reports[report.nodeid].append(
        {
            "when": report.when,
            "outcome": report.outcome,
            "wasxfail": str(wasxfail) if wasxfail is not None else None,
            "strict_xpass": report.failed and str(report.longrepr).startswith("[XPASS"),
        }
    )


def _outcome(phases: list[dict[str, Any]]) -> str:
    if any(phase["strict_xpass"] for phase in phases):
        return "xpass"
    if any(phase["wasxfail"] is not None and phase["outcome"] == "passed" for phase in phases):
        return "xpass"
    if any(
        phase["wasxfail"] is not None and phase["outcome"] == "skipped"
        for phase in phases
    ):
        return "xfail"
    if any(phase["outcome"] == "skipped" for phase in phases):
        return "skipped"
    if any(
        phase["outcome"] == "failed" and phase["when"] in {"setup", "teardown"}
        for phase in phases
    ):
        return "error"
    if any(phase["outcome"] == "failed" for phase in phases):
        return "failed"
    if any(phase["when"] == "call" and phase["outcome"] == "passed" for phase in phases):
        return "passed"
    return "error"


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    destination = session.config.getoption("phase473_node_manifest")
    if not destination:
        return
    nodes = [
        {"node_id": node_id, "outcome": _outcome(phases), "phases": phases}
        for node_id, phases in sorted(_reports.items())
    ]
    counts = {
        "total": len(nodes),
        "passed": sum(node["outcome"] == "passed" for node in nodes),
        "failed": sum(node["outcome"] == "failed" for node in nodes),
        "error": sum(node["outcome"] == "error" for node in nodes),
        "skipped": sum(node["outcome"] == "skipped" for node in nodes),
        "xfail": sum(node["outcome"] == "xfail" for node in nodes),
        "xpass": sum(node["outcome"] == "xpass" for node in nodes),
    }
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"schema_version": SCHEMA_VERSION, "nodes": nodes, "counts": counts},
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if any(counts[key] for key in ("failed", "error", "skipped", "xfail", "xpass")):
        session.exitstatus = ExitCode.TESTS_FAILED
