#!/usr/bin/env python3
"""Read what the five production aliases serve and check it is the expected build.

Both production pipelines call this: the backend after it moves the aliases, and
infra before it deploys (the live release must already be the backend commit it
is about to rebuild). It only reads and reports. It never moves an alias back.

The result is one bounded observation. The aliases are read, their packages are
downloaded and checked, and the aliases are read again; a change in between
fails the check. Nothing here stops another pipeline from moving an alias after
the second read.

release.json and release.json.sha256 are written on every outcome, including a
failure part-way through, so the evidence of a failed check is kept too.
"""

from __future__ import annotations

import argparse
import base64
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
from typing import Any
import urllib.request
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_lambda_dist import MANIFEST_NAME, DistVerificationError, sha256_dist_tree  # noqa: E402


FUNCTIONS = (
    "stoa-api",
    "stoa-weekly-report",
    "stoa-dispatch-reconciler",
    "stoa-account-deletion",
    "stoa-conversation-generation",
)
ALIAS = "production"
REGION = "eu-central-2"
RECORD_NAME = "release.json"
DIGEST_NAME = "release.json.sha256"
PHASES = ("pre-deploy", "post-deploy")
# Lambda caps an unzipped package at 250 MB; anything past this is not ours.
MAX_UNZIPPED_BYTES = 300 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 120

Runner = Callable[[Sequence[str]], str]
Fetcher = Callable[[str], bytes]


class ReleaseCheckError(RuntimeError):
    """Raised when the live release cannot be read or does not match."""


def _aws_cli(args: Sequence[str]) -> str:
    try:
        return subprocess.run(
            list(args), check=True, capture_output=True, text=True
        ).stdout
    except subprocess.CalledProcessError as exc:
        # stderr names the failing call and error code; it never carries the
        # function environment, which every query below leaves out.
        raise ReleaseCheckError(f"{' '.join(args[:3])} failed: {exc.stderr.strip()}") from exc


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:  # noqa: S310
        return response.read()


def _read_json(run: Runner, args: Sequence[str]) -> dict[str, Any]:
    raw = run(args)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReleaseCheckError(f"{args[2]} returned malformed JSON") from exc
    if not isinstance(parsed, dict):
        raise ReleaseCheckError(f"{args[2]} returned {type(parsed).__name__}, not an object")
    return parsed


def _require_str(payload: dict[str, Any], key: str, what: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ReleaseCheckError(f"{what}: missing {key}")
    return value


def read_alias(run: Runner, function: str, region: str) -> tuple[str, str, dict[str, Any]]:
    """Return the alias's (version, revision id, additional version weights).

    An alias can send part of its traffic to other versions. The weights come
    back empty when it does not; this check does not support a weighted alias.
    """
    payload = _read_json(
        run,
        [
            "aws", "lambda", "get-alias",
            "--function-name", function,
            "--name", ALIAS,
            "--region", region,
            "--query",
            "{version: FunctionVersion, revision: RevisionId,"
            " weights: RoutingConfig.AdditionalVersionWeights}",
            "--output", "json",
        ],
    )
    what = f"{function}:{ALIAS}"
    if "weights" not in payload:
        raise ReleaseCheckError(f"{what}: missing weights")
    weights = payload["weights"]
    if weights is None:
        weights = {}
    if not isinstance(weights, dict):
        raise ReleaseCheckError(f"{what}: malformed weights")
    return _require_str(payload, "version", what), _require_str(payload, "revision", what), weights


def read_code(run: Runner, function: str, region: str) -> tuple[str, str, str]:
    """Return (version, CodeSha256, download URL) read through the alias qualifier.

    The query leaves the function environment out on purpose: it holds keys.
    The URL is presigned and is never printed or recorded.
    """
    payload = _read_json(
        run,
        [
            "aws", "lambda", "get-function",
            "--function-name", function,
            "--qualifier", ALIAS,
            "--region", region,
            "--query",
            "{version: Configuration.Version, code_sha256: Configuration.CodeSha256,"
            " location: Code.Location}",
            "--output", "json",
        ],
    )
    what = f"{function}:{ALIAS}"
    return (
        _require_str(payload, "version", what),
        _require_str(payload, "code_sha256", what),
        _require_str(payload, "location", what),
    )


def code_sha256(package: bytes) -> str:
    """Lambda's CodeSha256: the base64 of the package's SHA-256 digest."""
    return base64.b64encode(hashlib.sha256(package).digest()).decode("ascii")


def extract_package(package: bytes, target: Path) -> None:
    """Unpack a Lambda zip, refusing links, escaping paths and oversize content."""
    archive_path = target.parent / f"{target.name}.zip"
    archive_path.write_bytes(package)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            total = 0
            for info in archive.infolist():
                name = PurePosixPath(info.filename)
                if name.is_absolute() or ".." in name.parts:
                    raise ReleaseCheckError(f"package entry escapes the archive: {info.filename}")
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ReleaseCheckError(f"package entry is a symlink: {info.filename}")
                if info.is_dir():
                    continue
                total += info.file_size
                if total > MAX_UNZIPPED_BYTES:
                    raise ReleaseCheckError("package unzips past the Lambda size limit")
                destination = target.joinpath(*name.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, destination.open("wb") as sink:
                    while chunk := source.read(1024 * 1024):
                        sink.write(chunk)
    except zipfile.BadZipFile as exc:
        raise ReleaseCheckError("package is not a readable zip") from exc
    finally:
        archive_path.unlink(missing_ok=True)


def inspect_package(package: bytes, workdir: Path) -> dict[str, Any]:
    """Return the package's manifest identity, recomputing its distribution hash."""
    target = workdir / hashlib.sha256(package).hexdigest()
    target.mkdir()
    extract_package(package, target)
    manifest_path = target / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ReleaseCheckError(f"package has no {MANIFEST_NAME}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseCheckError(f"package {MANIFEST_NAME} is malformed") from exc
    if not isinstance(manifest, dict):
        raise ReleaseCheckError(f"package {MANIFEST_NAME} is malformed")
    try:
        recomputed = sha256_dist_tree(target)
    except DistVerificationError as exc:
        raise ReleaseCheckError(str(exc)) from exc
    return {
        "source_git_sha": manifest.get("source_git_sha"),
        "source_git_dirty": manifest.get("source_git_dirty"),
        "distribution_tree_hash": manifest.get("distribution_tree_hash"),
        "recomputed_distribution_tree_hash": recomputed,
    }


def local_build_identity(local_dist: Path) -> dict[str, Any]:
    manifest_path = local_dist / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseCheckError(f"local build {MANIFEST_NAME} is unreadable") from exc
    if not isinstance(manifest, dict):
        raise ReleaseCheckError(f"local build {MANIFEST_NAME} is malformed")
    try:
        recomputed = sha256_dist_tree(local_dist)
    except DistVerificationError as exc:
        raise ReleaseCheckError(str(exc)) from exc
    return {
        "source_git_sha": manifest.get("source_git_sha"),
        "distribution_tree_hash": manifest.get("distribution_tree_hash"),
        "recomputed_distribution_tree_hash": recomputed,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def verify_live_release(
    *,
    expected_sha: str,
    phase: str,
    local_dist: Path | None,
    region: str = REGION,
    run: Runner = _aws_cli,
    fetch: Fetcher = _fetch,
    now: Callable[[], str] = _now,
    functions: Sequence[str] = FUNCTIONS,
) -> dict[str, Any]:
    """Observe the live release and return the record; ``errors`` empty means verified."""
    record: dict[str, Any] = {
        "schema_version": 1,
        "phase": phase,
        "result": "failed",
        "errors": [],
        "expected_source_git_sha": expected_sha,
        "local_build": None,
        "run": {
            "repository": os.environ.get("GITHUB_REPOSITORY"),
            "workflow": os.environ.get("GITHUB_WORKFLOW"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        },
        "region": region,
        "alias": ALIAS,
        "observed_from": now(),
        "observed_until": None,
        "functions": [],
    }
    errors: list[str] = record["errors"]

    def fail(message: str) -> None:
        errors.append(message)

    try:
        if phase not in PHASES:
            raise ReleaseCheckError(f"unknown phase {phase!r}")
        if phase == "post-deploy" and local_dist is None:
            raise ReleaseCheckError("post-deploy needs the local build to compare against")

        if local_dist is not None:
            local = local_build_identity(local_dist)
            record["local_build"] = local
            if local["source_git_sha"] != expected_sha:
                fail(f"local build is {local['source_git_sha']}, not {expected_sha}")
            if local["recomputed_distribution_tree_hash"] != local["distribution_tree_hash"]:
                fail("local build files do not match its own manifest")

        packages: dict[str, dict[str, Any]] = {}
        with tempfile.TemporaryDirectory(prefix="stoa-live-release-") as scratch:
            workdir = Path(scratch)
            for function in functions:
                entry: dict[str, Any] = {"function": function}
                record["functions"].append(entry)
                version, revision, weights = read_alias(run, function, region)
                entry.update(
                    version=version, alias_revision_id=revision, additional_version_weights=weights
                )
                if weights:
                    fail(f"{function}: alias also routes traffic to {sorted(weights)}")
                code_version, sha, location = read_code(run, function, region)
                entry["code_sha256"] = sha
                if code_version != version:
                    fail(f"{function}: alias read {version}, code read {code_version}")
                if sha not in packages:
                    package = fetch(location)
                    actual = code_sha256(package)
                    if actual != sha:
                        fail(f"{function}: downloaded package is {actual}, AWS says {sha}")
                    packages[sha] = inspect_package(package, workdir)
                identity = packages[sha]
                entry.update(
                    source_git_sha=identity["source_git_sha"],
                    distribution_tree_hash=identity["distribution_tree_hash"],
                )
                if identity["recomputed_distribution_tree_hash"] != identity["distribution_tree_hash"]:
                    fail(f"{function}: package files do not match its manifest")
                if identity["source_git_sha"] != expected_sha:
                    fail(f"{function}: serves {identity['source_git_sha']}, not {expected_sha}")
                if identity["source_git_dirty"] is not False:
                    fail(f"{function}: package was built from a dirty tree")
                if (
                    record["local_build"] is not None
                    and identity["distribution_tree_hash"]
                    != record["local_build"]["recomputed_distribution_tree_hash"]
                ):
                    fail(f"{function}: package is not this run's local build")

            if len(packages) > 1:
                fail(f"the five aliases serve {len(packages)} different packages")

            for entry in record["functions"]:
                version, revision, weights = read_alias(run, entry["function"], region)
                entry.update(
                    reread_version=version,
                    reread_alias_revision_id=revision,
                    reread_additional_version_weights=weights,
                )
                if (version, revision, weights) != (
                    entry["version"],
                    entry["alias_revision_id"],
                    entry["additional_version_weights"],
                ):
                    fail(f"{entry['function']}: alias moved while it was being checked")
    except (ReleaseCheckError, OSError) as exc:
        fail(str(exc))
    except Exception as exc:  # noqa: BLE001 - any surprise still fails closed with a record
        fail(f"unexpected {type(exc).__name__}: {exc}")
    finally:
        record["observed_until"] = now()

    if not errors:
        record["result"] = "verified"
    return record


def write_record(record: dict[str, Any], output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    body = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
    (output_dir / RECORD_NAME).write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    # sha256sum format, so `sha256sum -c release.json.sha256` checks it.
    (output_dir / DIGEST_NAME).write_text(f"{digest}  {RECORD_NAME}\n", encoding="ascii")
    return digest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--phase", required=True, choices=PHASES)
    parser.add_argument("--local-dist", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--region", default=REGION)
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    run: Runner = _aws_cli,
    fetch: Fetcher = _fetch,
) -> int:
    args = parse_args(argv)
    record = verify_live_release(
        expected_sha=args.expected_sha,
        phase=args.phase,
        local_dist=args.local_dist,
        region=args.region,
        run=run,
        fetch=fetch,
    )
    digest = write_record(record, args.output_dir)
    for entry in record["functions"]:
        print(
            f"{entry['function']}:{ALIAS} v{entry.get('version')} "
            f"code={entry.get('code_sha256')} sha={entry.get('source_git_sha')}"
        )
    for error in record["errors"]:
        print(f"::error::{error}", file=sys.stderr)
    print(f"Live release {record['result']}: {RECORD_NAME} sha256={digest}")
    return 0 if record["result"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
