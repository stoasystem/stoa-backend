from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import tomllib
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = ROOT / "scripts" / "phase474_pytest_guard.py"


def _load_guard() -> Any:
    assert GUARD_PATH.is_file(), "the Phase 474 strict pytest guard must exist"
    spec = importlib.util.spec_from_file_location("phase474_pytest_guard", GUARD_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(
    *,
    when: str = "call",
    outcome: str = "passed",
    wasxfail: str | None = None,
    longrepr: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        when=when,
        outcome=outcome,
        wasxfail=wasxfail,
        failed=outcome == "failed",
        longrepr=longrepr,
    )


def test_approved_verification_toolchain_is_exactly_pinned() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev = set(project["project"]["optional-dependencies"]["dev"])

    assert {
        "pytest==9.0.3",
        "pytest-asyncio==1.4.0",
        "moto[dynamodb,s3,sqs,ses,rekognition]==5.2.1",
        "ruff==0.15.14",
        "mypy==2.1.0",
        "pip-audit==2.10.1",
        "time-machine==3.2.0",
        "pytest-socket==0.8.0",
        "boto3-stubs==1.43.16",
        "types-python-jose==3.5.0.20260408",
    }.issubset(dev)


@pytest.mark.parametrize(
    ("phases", "expected"),
    [
        ([_report()], "passed"),
        ([_report(outcome="failed")], "failed"),
        ([_report(when="setup", outcome="failed")], "error"),
        ([_report(outcome="skipped")], "skipped"),
        ([_report(outcome="skipped", wasxfail="expected")], "xfail"),
        ([_report(outcome="passed", wasxfail="expected")], "xpass"),
        ([_report(outcome="failed", longrepr="[XPASS(strict)]")], "xpass"),
    ],
)
def test_guard_classifies_every_closed_pytest_outcome(
    phases: list[SimpleNamespace], expected: str
) -> None:
    guard = _load_guard()
    encoded = [guard.report_record(report) for report in phases]
    assert guard.classify_outcome(encoded) == expected


def test_manifest_binds_runtime_lock_seed_clock_and_collection() -> None:
    guard = _load_guard()
    nodes = [
        {
            "node_id": "tests/test_alpha.py::test_one",
            "outcome": "passed",
            "phases": [guard.report_record(_report())],
        },
        {
            "node_id": "tests/test_beta.py::test_two",
            "outcome": "passed",
            "phases": [guard.report_record(_report())],
        },
    ]
    manifest = guard.build_manifest(
        nodes=nodes,
        clock="2026-07-01T12:00:00Z",
        seed=4740718,
        runtime="3.12.13",
        lock_sha256="a" * 64,
    )

    expected_collection = sha256(
        b"tests/test_alpha.py::test_one\ntests/test_beta.py::test_two\n"
    ).hexdigest()
    assert manifest == {
        "schema_version": "stoa.phase474.pytest-nodes.v1",
        "clock": "2026-07-01T12:00:00Z",
        "seed": 4740718,
        "runtime": "3.12.13",
        "lock_sha256": "a" * 64,
        "collection_sha256": expected_collection,
        "nodes": nodes,
        "counts": {
            "total": 2,
            "passed": 2,
            "failed": 0,
            "error": 0,
            "skipped": 0,
            "xfail": 0,
            "xpass": 0,
        },
    }
    assert json.loads(json.dumps(manifest, sort_keys=True)) == manifest


@pytest.mark.parametrize(
    "outcome", ["failed", "error", "skipped", "xfail", "xpass"]
)
def test_guard_rejects_every_non_pass_outcome(outcome: str) -> None:
    guard = _load_guard()
    nodes = [{"node_id": "tests/test_bad.py::test_bad", "outcome": outcome, "phases": []}]
    with pytest.raises(guard.StrictOutcomeError, match=outcome):
        guard.build_manifest(
            nodes=nodes,
            clock="2035-01-15T12:00:00Z",
            seed=4740718,
            runtime="3.12.13",
            lock_sha256="b" * 64,
        )


def test_guard_rejects_empty_collection() -> None:
    guard = _load_guard()
    with pytest.raises(guard.StrictOutcomeError, match="empty"):
        guard.build_manifest(
            nodes=[],
            clock="2026-07-01T12:00:00Z",
            seed=4740718,
            runtime="3.12.13",
            lock_sha256="c" * 64,
        )


def test_hermetic_environment_removes_ambient_aws_and_proxy_paths() -> None:
    guard = _load_guard()
    environment = guard.hermetic_environment(
        {
            "AWS_ACCESS_KEY_ID": "secret",
            "AWS_SECRET_ACCESS_KEY": "secret",
            "AWS_SESSION_TOKEN": "secret",
            "AWS_PROFILE": "production",
            "HTTP_PROXY": "http://proxy.invalid",
            "HTTPS_PROXY": "http://proxy.invalid",
            "ALL_PROXY": "socks5://proxy.invalid",
            "PATH": "/usr/bin",
        },
        nonexistent_root=Path("/definitely/not/stoa/credentials"),
    )

    for name in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
    ):
        assert name not in environment
    assert environment["AWS_EC2_METADATA_DISABLED"] == "true"
    assert environment["AWS_SHARED_CREDENTIALS_FILE"].endswith("credentials")
    assert environment["AWS_CONFIG_FILE"].endswith("config")
    assert environment["PATH"] == "/usr/bin"

