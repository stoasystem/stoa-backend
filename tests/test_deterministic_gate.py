from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = ROOT / "scripts" / "phase474_pytest_guard.py"
RELEASE_GATE_PATH = ROOT / "scripts" / "release_gate.py"


def _load_guard() -> Any:
    assert GUARD_PATH.is_file(), "the Phase 474 strict pytest guard must exist"
    spec = importlib.util.spec_from_file_location("phase474_pytest_guard", GUARD_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_release_gate() -> Any:
    spec = importlib.util.spec_from_file_location("phase474_release_gate", RELEASE_GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
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


def _matrix_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    for name, content in (
        ("pyproject.toml", "[project]\nname = 'matrix'\nversion = '1'\n"),
        ("uv.lock", "version = 1\n"),
        ("requirements.txt", "example==1\n"),
    ):
        (project / name).write_text(content, encoding="utf-8")
    return project


def _matrix_operations(gate: Any, project: Path, *, mismatch: bool = False) -> tuple[Any, list[Any]]:
    calls: list[Any] = []

    def run_process(
        argv: tuple[str, ...], environment: dict[str, str], cwd: Path, timeout_seconds: int
    ) -> Any:
        calls.append((argv, dict(environment), cwd, timeout_seconds))
        assert cwd == project
        if argv[:2] == ("uv", "sync"):
            environment_path = Path(environment["UV_PROJECT_ENVIRONMENT"])
            python = environment_path / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")
            return gate.ProcessResult(0, b"sync", b"")

        manifest_path = Path(environment["STOA_PHASE474_MANIFEST"])
        clock = environment["STOA_PHASE474_CLOCK"]
        collection = "b" * 64 if mismatch and clock.startswith("2035") else "a" * 64
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "stoa.phase474.pytest-nodes.v1",
                    "clock": clock,
                    "seed": 4740718,
                    "runtime": "3.12.13",
                    "lock_sha256": sha256((project / "uv.lock").read_bytes()).hexdigest(),
                    "collection_sha256": collection,
                    "nodes": [{"node_id": "tests/test_ok.py::test_ok", "outcome": "passed", "phases": []}],
                    "counts": {
                        "total": 1,
                        "passed": 1,
                        "failed": 0,
                        "error": 0,
                        "skipped": 0,
                        "xfail": 0,
                        "xpass": 0,
                    },
                }
            ),
            encoding="utf-8",
        )
        return gate.ProcessResult(0, b"pytest", b"")

    return (
        gate.PythonMatrixOperations(
            run_process=run_process,
            network_boundary=lambda: ("network-none", "--"),
        ),
        calls,
    )


def test_python_matrix_returns_exact_not_run_without_an_os_boundary(tmp_path: Path) -> None:
    gate = _load_release_gate()
    project = _matrix_project(tmp_path)
    operations = gate.PythonMatrixOperations(
        run_process=lambda *args: pytest.fail("no process may run without the required boundary"),
        network_boundary=lambda: None,
    )

    result = gate.run_python_matrix(
        root=project,
        environment_paths=(tmp_path / "env-one", tmp_path / "env-two"),
        operations=operations,
        source_environment={"PATH": "/usr/bin"},
    )

    assert result["status"] == "NOT RUN"
    assert result["reason_code"] == "OS_NETWORK_BOUNDARY_UNAVAILABLE"
    assert result["runs"] == []
    assert gate.python_matrix_exit_code(result) == 2


def test_python_matrix_uses_two_fresh_envs_and_identical_suite_argv(tmp_path: Path) -> None:
    gate = _load_release_gate()
    project = _matrix_project(tmp_path)
    operations, calls = _matrix_operations(gate, project)
    environment_paths = (tmp_path / "env-one", tmp_path / "env-two")

    result = gate.run_python_matrix(
        root=project,
        environment_paths=environment_paths,
        operations=operations,
        source_environment={
            "PATH": "/usr/bin",
            "AWS_ACCESS_KEY_ID": "ambient",
            "HTTPS_PROXY": "http://ambient.invalid",
        },
    )

    assert result["status"] == "PASS"
    assert gate.python_matrix_exit_code(result) == 0
    assert [run["clock"] for run in result["runs"]] == list(gate.PYTHON_MATRIX_CLOCKS)
    assert result["runs"][0]["collection_sha256"] == result["runs"][1]["collection_sha256"]
    sync_calls = [call for call in calls if call[0][:2] == ("uv", "sync")]
    test_calls = [call for call in calls if call[0][:2] != ("uv", "sync")]
    assert len(sync_calls) == len(test_calls) == 2
    assert sync_calls[0][1]["UV_PROJECT_ENVIRONMENT"] != sync_calls[1][1]["UV_PROJECT_ENVIRONMENT"]
    assert [call[0][2:] for call in test_calls] == [gate.PYTHON_SUITE_ARGV] * 2
    for _, environment, _, _ in test_calls:
        assert "AWS_ACCESS_KEY_ID" not in environment
        assert "HTTPS_PROXY" not in environment
        assert environment["AWS_EC2_METADATA_DISABLED"] == "true"
        assert environment["STOA_PHASE474_HERMETIC"] == "1"


def test_python_matrix_rejects_a_warm_environment(tmp_path: Path) -> None:
    gate = _load_release_gate()
    project = _matrix_project(tmp_path)
    operations, _ = _matrix_operations(gate, project)
    warm = tmp_path / "warm"
    warm.mkdir()

    with pytest.raises(gate.GatePolicyError, match="fresh"):
        gate.run_python_matrix(
            root=project,
            environment_paths=(warm, tmp_path / "fresh"),
            operations=operations,
            source_environment=os.environ,
        )


def test_python_matrix_rejects_collection_drift(tmp_path: Path) -> None:
    gate = _load_release_gate()
    project = _matrix_project(tmp_path)
    operations, _ = _matrix_operations(gate, project, mismatch=True)

    with pytest.raises(gate.GatePolicyError, match="collection"):
        gate.run_python_matrix(
            root=project,
            environment_paths=(tmp_path / "env-one", tmp_path / "env-two"),
            operations=operations,
            source_environment=os.environ,
        )


def test_backend_python_matrix_is_a_checked_in_registered_gate() -> None:
    gate = _load_release_gate()
    spec = gate.default_registry().require("backend-python-hermetic")
    assert spec.argv == (sys.executable, "scripts/release_gate.py", "python-hermetic")
    assert spec.artifact_paths == ("pyproject.toml", "uv.lock", "requirements.txt")
    assert spec.timeout_seconds >= 3600


def test_formal_runtime_uses_the_declared_frozen_clock() -> None:
    if os.environ.get("STOA_PHASE474_HERMETIC") != "1":
        return
    from datetime import datetime, timezone

    observed = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    assert observed == os.environ["STOA_PHASE474_CLOCK"]


def test_formal_runtime_denies_direct_and_subprocess_network() -> None:
    if os.environ.get("STOA_PHASE474_HERMETIC") != "1":
        return
    import socket

    from pytest_socket import SocketBlockedError

    with pytest.raises(SocketBlockedError):
        socket.create_connection(("1.1.1.1", 443), timeout=1)

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import socket; socket.create_connection(('1.1.1.1', 443), timeout=2)",
        ],
        check=False,
        capture_output=True,
        timeout=5,
    )
    assert completed.returncode != 0


def test_formal_runtime_denies_ambient_aws_discovery() -> None:
    if os.environ.get("STOA_PHASE474_HERMETIC") != "1":
        return
    import boto3

    for name in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
        "AWS_ROLE_ARN",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    ):
        assert name not in os.environ
    assert os.environ["AWS_EC2_METADATA_DISABLED"] == "true"
    assert boto3.Session().get_credentials() is None
