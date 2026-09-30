"""Local logic of the live-release check, against stand-ins for AWS and S3.

These prove the decisions the script makes from what it reads. They cannot prove
what Lambda or S3 actually return; that is only shown by a real pipeline run.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
from typing import Any
import zipfile

import pytest

from build_lambda_dist import MANIFEST_NAME, sha256_dist_tree
import verify_live_release as live


SHA = "a" * 40
OTHER_SHA = "b" * 40
FILES = {"stoa/main.py": b"def handler(event, context):\n    return {}\n", "vendor/x.py": b"x = 1\n"}


def _dist(root: Path, *, sha: str = SHA, files: dict[str, bytes] = FILES, dirty: bool = False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    manifest = {
        "source_git_sha": sha,
        "source_git_dirty": dirty,
        "distribution_tree_hash": sha256_dist_tree(root),
    }
    (root / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _zip(dist: Path, *, compresslevel: int = 9, comment: bytes = b"") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.comment = comment
        for path in sorted(p for p in dist.rglob("*") if p.is_file()):
            archive.write(path, path.relative_to(dist).as_posix(), compresslevel=compresslevel)
    return buffer.getvalue()


class FakeLambda:
    """Answers the two CLI reads the script makes, per function."""

    def __init__(self, packages: dict[str, bytes]) -> None:
        self.packages = packages
        self.aliases = {name: ("7", f"rev-{name}") for name in live.FUNCTIONS}
        self.code_versions: dict[str, str] = {}
        self.reported_sha: dict[str, str] = {}
        self.alias_reads: dict[str, int] = {}
        self.moves_on_reread: dict[str, tuple[str, str]] = {}
        self.weights: dict[str, Any] = {}
        self.weights_on_reread: dict[str, Any] = {}
        self.fail_on: set[tuple[str, str]] = set()
        self.calls: list[list[str]] = []

    def location(self, function: str) -> str:
        return f"https://example.invalid/{function}"

    def run(self, args: list[str]) -> str:
        self.calls.append(list(args))
        command = args[2]
        function = args[args.index("--function-name") + 1]
        if (command, function) in self.fail_on:
            raise live.ReleaseCheckError(f"aws lambda {command} failed: AccessDeniedException")
        if command == "get-alias":
            count = self.alias_reads.get(function, 0) + 1
            self.alias_reads[function] = count
            version, revision = self.aliases[function]
            if count > 1 and function in self.moves_on_reread:
                version, revision = self.moves_on_reread[function]
            weights = self.weights.get(function)
            if count > 1 and function in self.weights_on_reread:
                weights = self.weights_on_reread[function]
            payload = {"version": version, "revision": revision, "weights": weights}
            if weights == "absent":
                del payload["weights"]
            return json.dumps(payload)
        if command == "get-function":
            package = self.packages[function]
            return json.dumps(
                {
                    "version": self.code_versions.get(function, self.aliases[function][0]),
                    "code_sha256": self.reported_sha.get(function, live.code_sha256(package)),
                    "location": self.location(function),
                }
            )
        raise AssertionError(f"unexpected call {args}")

    def fetch(self, url: str) -> bytes:
        return self.packages[url.rsplit("/", 1)[1]]


@pytest.fixture
def build(tmp_path: Path) -> tuple[Path, bytes]:
    dist = _dist(tmp_path / "dist")
    return dist, _zip(dist)


def _check(fake: FakeLambda, *, local_dist: Path | None, phase: str = "post-deploy") -> dict[str, Any]:
    return live.verify_live_release(
        expected_sha=SHA,
        phase=phase,
        local_dist=local_dist,
        run=fake.run,
        fetch=fake.fetch,
        now=lambda: "2026-09-30T00:00:00+00:00",
    )


def _all(package: bytes) -> dict[str, bytes]:
    return {name: package for name in live.FUNCTIONS}


def test_a_consistent_release_of_this_build_is_verified(build: tuple[Path, bytes]) -> None:
    dist, package = build
    fake = FakeLambda(_all(package))
    record = _check(fake, local_dist=dist)
    assert record["errors"] == []
    assert record["result"] == "verified"
    assert [entry["function"] for entry in record["functions"]] == list(live.FUNCTIONS)
    for entry in record["functions"]:
        assert entry["version"] == entry["reread_version"] == "7"
        assert entry["alias_revision_id"] == entry["reread_alias_revision_id"]
        assert entry["code_sha256"] == live.code_sha256(package)
        assert entry["source_git_sha"] == SHA


def test_each_distinct_package_is_downloaded_once(build: tuple[Path, bytes]) -> None:
    dist, package = build
    fake = FakeLambda(_all(package))
    fetched: list[str] = []

    def fetch(url: str) -> bytes:
        fetched.append(url)
        return fake.fetch(url)

    live.verify_live_release(
        expected_sha=SHA, phase="post-deploy", local_dist=dist, run=fake.run, fetch=fetch
    )
    assert len(fetched) == 1


def test_reads_go_through_the_alias_and_leave_the_environment_out(
    build: tuple[Path, bytes],
) -> None:
    dist, package = build
    fake = FakeLambda(_all(package))
    _check(fake, local_dist=dist)
    for call in fake.calls:
        if call[2] == "get-function":
            assert call[call.index("--qualifier") + 1] == "production"
        if call[2] == "get-alias":
            assert call[call.index("--name") + 1] == "production"
        query = call[call.index("--query") + 1]
        assert "Environment" not in query


def test_a_download_that_is_not_what_aws_reports_fails(build: tuple[Path, bytes]) -> None:
    dist, package = build
    fake = FakeLambda(_all(package))
    fake.reported_sha = {name: "bm90LXRoZS1wYWNrYWdl" for name in live.FUNCTIONS}
    record = _check(fake, local_dist=dist)
    assert record["result"] == "failed"
    assert any("downloaded package is" in error for error in record["errors"])


def test_a_package_whose_files_disagree_with_its_manifest_fails(
    tmp_path: Path, build: tuple[Path, bytes]
) -> None:
    dist, _ = build
    tampered = _dist(tmp_path / "tampered")
    (tampered / "vendor" / "x.py").write_bytes(b"x = 2\n")
    fake = FakeLambda(_all(_zip(tampered)))
    record = _check(fake, local_dist=dist)
    assert any("do not match its manifest" in error for error in record["errors"])


def test_a_different_build_of_the_same_commit_fails(
    tmp_path: Path, build: tuple[Path, bytes]
) -> None:
    dist, _ = build
    other = _dist(tmp_path / "other", files={**FILES, "vendor/y.py": b"y = 1\n"})
    fake = FakeLambda(_all(_zip(other)))
    record = _check(fake, local_dist=dist)
    assert any("not this run's local build" in error for error in record["errors"])


def test_the_same_build_zipped_differently_still_matches_the_local_build(
    build: tuple[Path, bytes],
) -> None:
    # Backend and CDK zip the same dist differently; the distribution hash is
    # what identifies the build, the zip digest only identifies the upload.
    dist, _ = build
    fake = FakeLambda(_all(_zip(dist, compresslevel=1, comment=b"cdk")))
    assert _check(fake, local_dist=dist)["errors"] == []


def test_a_package_of_another_commit_fails(tmp_path: Path, build: tuple[Path, bytes]) -> None:
    dist, _ = build
    older = _dist(tmp_path / "older", sha=OTHER_SHA)
    fake = FakeLambda(_all(_zip(older)))
    record = _check(fake, local_dist=dist)
    assert any(f"serves {OTHER_SHA}" in error for error in record["errors"])


def test_a_package_built_from_a_dirty_tree_fails(tmp_path: Path) -> None:
    dirty = _dist(tmp_path / "dirty", dirty=True)
    fake = FakeLambda(_all(_zip(dirty)))
    record = _check(fake, local_dist=None, phase="pre-deploy")
    assert any("dirty tree" in error for error in record["errors"])


def test_aliases_serving_different_packages_fail(tmp_path: Path, build: tuple[Path, bytes]) -> None:
    dist, package = build
    fake = FakeLambda(
        {**_all(package), "stoa-account-deletion": _zip(dist, comment=b"cdk")}
    )
    record = _check(fake, local_dist=dist)
    assert any("2 different packages" in error for error in record["errors"])


def test_an_alias_that_moves_during_the_check_fails(build: tuple[Path, bytes]) -> None:
    dist, package = build
    fake = FakeLambda(_all(package))
    fake.moves_on_reread = {"stoa-weekly-report": ("8", "rev-new")}
    record = _check(fake, local_dist=dist)
    assert record["errors"] == ["stoa-weekly-report: alias moved while it was being checked"]
    entry = next(e for e in record["functions"] if e["function"] == "stoa-weekly-report")
    assert entry["reread_version"] == "8"


def test_a_revision_change_alone_counts_as_a_move(build: tuple[Path, bytes]) -> None:
    dist, package = build
    fake = FakeLambda(_all(package))
    fake.moves_on_reread = {"stoa-api": ("7", "rev-new")}
    assert _check(fake, local_dist=dist)["result"] == "failed"


def test_an_alias_that_splits_traffic_to_another_version_fails(
    build: tuple[Path, bytes],
) -> None:
    # The primary version is right, but a fifth of the traffic still goes to 6.
    dist, package = build
    fake = FakeLambda(_all(package))
    fake.weights = {"stoa-api": {"6": 0.2}}
    record = _check(fake, local_dist=dist)
    assert record["result"] == "failed"
    assert record["errors"] == ["stoa-api: alias also routes traffic to ['6']"]
    entry = next(e for e in record["functions"] if e["function"] == "stoa-api")
    assert entry["additional_version_weights"] == {"6": 0.2}


def test_empty_routing_is_not_a_split(build: tuple[Path, bytes]) -> None:
    dist, package = build
    fake = FakeLambda(_all(package))
    fake.weights = {"stoa-api": {}, "stoa-weekly-report": None}
    assert _check(fake, local_dist=dist)["errors"] == []


def test_routing_that_appears_during_the_check_counts_as_a_move(
    build: tuple[Path, bytes],
) -> None:
    dist, package = build
    fake = FakeLambda(_all(package))
    fake.weights_on_reread = {"stoa-account-deletion": {"6": 0.5}}
    record = _check(fake, local_dist=dist)
    assert record["errors"] == ["stoa-account-deletion: alias moved while it was being checked"]


@pytest.mark.parametrize(("weights", "reason"), [("absent", "missing weights"), ([], "malformed")])
def test_unreadable_routing_fails_closed(
    build: tuple[Path, bytes], weights: object, reason: str
) -> None:
    dist, package = build
    fake = FakeLambda(_all(package))
    fake.weights = {"stoa-api": weights}
    record = _check(fake, local_dist=dist)
    assert any(reason in error for error in record["errors"])


def test_an_alias_and_code_read_that_disagree_fail(build: tuple[Path, bytes]) -> None:
    dist, package = build
    fake = FakeLambda(_all(package))
    fake.code_versions = {"stoa-api": "8"}
    record = _check(fake, local_dist=dist)
    assert any("alias read 7, code read 8" in error for error in record["errors"])


@pytest.mark.parametrize("command", ["get-alias", "get-function"])
def test_a_denied_or_missing_read_fails_and_keeps_what_was_read(
    build: tuple[Path, bytes], command: str
) -> None:
    dist, package = build
    fake = FakeLambda(_all(package))
    fake.fail_on = {(command, "stoa-dispatch-reconciler")}
    record = _check(fake, local_dist=dist)
    assert record["result"] == "failed"
    assert any("AccessDeniedException" in error for error in record["errors"])
    assert [e["function"] for e in record["functions"]][:2] == ["stoa-api", "stoa-weekly-report"]


def test_a_failed_download_fails(build: tuple[Path, bytes]) -> None:
    dist, package = build
    fake = FakeLambda(_all(package))

    def fetch(url: str) -> bytes:
        raise OSError("connection reset")

    record = live.verify_live_release(
        expected_sha=SHA, phase="post-deploy", local_dist=dist, run=fake.run, fetch=fetch
    )
    assert record["errors"] == ["connection reset"]


def test_malformed_aws_output_fails_closed(build: tuple[Path, bytes]) -> None:
    dist, _ = build
    record = live.verify_live_release(
        expected_sha=SHA,
        phase="post-deploy",
        local_dist=dist,
        run=lambda args: "not json",
        fetch=lambda url: b"",
    )
    assert record["result"] == "failed"
    assert record["errors"] == ["get-alias returned malformed JSON"]


def test_an_unexpected_error_still_fails_with_a_reason(build: tuple[Path, bytes]) -> None:
    dist, _ = build
    record = live.verify_live_release(
        expected_sha=SHA,
        phase="post-deploy",
        local_dist=dist,
        run=lambda args: json.dumps({"version": 7, "revision": None}),
        fetch=lambda url: b"",
    )
    assert record["result"] == "failed"
    assert record["errors"]


def test_a_local_build_of_another_commit_fails(tmp_path: Path) -> None:
    dist = _dist(tmp_path / "dist", sha=OTHER_SHA)
    fake = FakeLambda(_all(_zip(dist)))
    record = _check(fake, local_dist=dist)
    assert any(f"local build is {OTHER_SHA}" in error for error in record["errors"])


def test_post_deploy_requires_the_local_build(build: tuple[Path, bytes]) -> None:
    _, package = build
    record = _check(FakeLambda(_all(package)), local_dist=None)
    assert record["errors"] == ["post-deploy needs the local build to compare against"]


def test_pre_deploy_checks_the_live_commit_without_a_local_build(
    build: tuple[Path, bytes],
) -> None:
    _, package = build
    record = _check(FakeLambda(_all(package)), local_dist=None, phase="pre-deploy")
    assert record["errors"] == []
    assert record["local_build"] is None


@pytest.mark.parametrize(
    ("name", "mode", "reason"),
    [
        ("../escape.py", 0o644, "escapes the archive"),
        ("/abs.py", 0o644, "escapes the archive"),
        ("link.py", stat.S_IFLNK | 0o777, "symlink"),
    ],
)
def test_hostile_package_entries_are_refused(
    tmp_path: Path, name: str, mode: int, reason: str
) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo(name)
        info.external_attr = mode << 16
        archive.writestr(info, b"x")
    target = tmp_path / "unpacked"
    target.mkdir()
    with pytest.raises(live.ReleaseCheckError, match=reason):
        live.extract_package(buffer.getvalue(), target)


def test_record_and_digest_are_written_separately_and_agree(tmp_path: Path) -> None:
    record = {"result": "failed", "errors": ["x"]}
    digest = live.write_record(record, tmp_path / "out")
    body = (tmp_path / "out" / live.RECORD_NAME).read_bytes()
    assert hashlib.sha256(body).hexdigest() == digest
    assert json.loads(body) == record
    line = (tmp_path / "out" / live.DIGEST_NAME).read_text(encoding="ascii")
    assert line == f"{digest}  {live.RECORD_NAME}\n"
    checked = subprocess.run(
        ["shasum", "-a", "256", "-c", live.DIGEST_NAME],
        cwd=tmp_path / "out",
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 0, checked.stderr


def test_the_record_carries_the_run_identity(
    build: tuple[Path, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    dist, package = build
    monkeypatch.setenv("GITHUB_REPOSITORY", "stoasystem/stoa-backend")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    record = _check(FakeLambda(_all(package)), local_dist=dist)
    assert record["run"]["run_id"] == "123"
    assert record["run"]["run_attempt"] == "2"
    assert record["observed_from"] and record["observed_until"]


def test_main_writes_the_record_even_when_the_check_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def denied(args: list[str]) -> str:
        raise live.ReleaseCheckError("aws lambda get-alias failed: AccessDeniedException")

    out = tmp_path / "out"
    status = live.main(
        ["--expected-sha", SHA, "--phase", "pre-deploy", "--output-dir", str(out)],
        run=denied,
        fetch=lambda url: b"",
    )
    assert status == 1
    record = json.loads((out / live.RECORD_NAME).read_text(encoding="utf-8"))
    assert record["result"] == "failed"
    assert (out / live.DIGEST_NAME).is_file()
    assert "::error::" in capsys.readouterr().err
