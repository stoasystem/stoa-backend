from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from scripts.verify_phase474_python_evidence import (
    DEFAULT_MATRIX,
    DEFAULT_METADATA,
    EvidenceVerificationError,
    ROOT,
    verify_evidence,
)


Mutation = Callable[[dict[str, Any]], None]


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _verify_with(
    tmp_path: Path,
    *,
    metadata: dict[str, Any] | None = None,
    matrix: dict[str, Any] | None = None,
) -> None:
    metadata_path = tmp_path / "metadata.json"
    matrix_path = tmp_path / "matrix.json"
    _write(metadata_path, metadata if metadata is not None else _read(DEFAULT_METADATA))
    if matrix is None:
        matrix_path.write_bytes(DEFAULT_MATRIX.read_bytes())
    else:
        _write(matrix_path, matrix)
    verify_evidence(metadata_path=metadata_path, matrix_path=matrix_path, repo_root=ROOT)


def test_persisted_linux_python_evidence_passes() -> None:
    verify_evidence()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"status": "NOT RUN"}),
        lambda value: value.update({"unexpected": True}),
        lambda value: value["tested_source"].update({"tree": "0" * 40}),
        lambda value: value["runner"].update({"architecture": "x86_64"}),
        lambda value: value["production_operations"].update({"deploy": "PASS"}),
    ],
)
def test_metadata_tampering_fails_closed(tmp_path: Path, mutate: Mutation) -> None:
    metadata = copy.deepcopy(_read(DEFAULT_METADATA))
    mutate(metadata)
    with pytest.raises(EvidenceVerificationError):
        _verify_with(tmp_path, metadata=metadata)


def test_matrix_byte_tampering_fails_closed(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.json"
    matrix_path = tmp_path / "matrix.json"
    metadata_path.write_bytes(DEFAULT_METADATA.read_bytes())
    matrix_path.write_bytes(DEFAULT_MATRIX.read_bytes() + b" ")
    with pytest.raises(EvidenceVerificationError, match="byte length differs"):
        verify_evidence(metadata_path=metadata_path, matrix_path=matrix_path, repo_root=ROOT)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b'{"schema":"one","schema":"two"}', "duplicate JSON object key"),
        (b'{"status":NaN}', "non-finite JSON number"),
        (b'{"status":Infinity}', "non-finite JSON number"),
        (b'{"status":-Infinity}', "non-finite JSON number"),
    ],
)
def test_non_canonical_json_tampering_fails_closed(
    tmp_path: Path,
    raw: bytes,
    message: str,
) -> None:
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_bytes(raw)
    with pytest.raises(EvidenceVerificationError, match=message):
        verify_evidence(
            metadata_path=metadata_path,
            matrix_path=DEFAULT_MATRIX,
            repo_root=ROOT,
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: value["source"]["uv.lock"].update({"sha256": "0" * 64}),
            "source binding differs",
        ),
        (
            lambda value: value["runs"][1].update({"collection_sha256": "0" * 64}),
            "collection_sha256 differs",
        ),
        (
            lambda value: value["runs"][0]["counts"].update({"passed": 2138}),
            "counts differ",
        ),
        (
            lambda value: value["runs"].append(copy.deepcopy(value["runs"][1])),
            "exactly two runs",
        ),
    ],
)
def test_matrix_semantic_tampering_fails_closed(
    tmp_path: Path,
    mutate: Mutation,
    message: str,
) -> None:
    matrix = copy.deepcopy(_read(DEFAULT_MATRIX))
    mutate(matrix)
    with pytest.raises(EvidenceVerificationError, match=message):
        _verify_with(tmp_path, matrix=matrix)


def test_matrix_digest_is_the_recorded_exact_file() -> None:
    raw = DEFAULT_MATRIX.read_bytes()
    metadata = _read(DEFAULT_METADATA)
    assert len(raw) == metadata["matrix"]["bytes"] == 1739
    assert hashlib.sha256(raw).hexdigest() == metadata["matrix"]["sha256"]
