#!/usr/bin/env python3
"""Move many curriculum drafts through review, approval and publication in one run.

A knowledge-base import applies some two thousand practice sets as drafts, and
each one takes three admin calls to reach students: submit-review, approve,
publish. This script makes those calls for every draft of the migrations it is
given, one practice set after the other, under the operator's own admin session.
It is a client of the admin API and nothing else: every step passes the same
role, capability and target checks and the same validation as a call by hand,
and the audit names the operator.

    uv run python scripts/publish_curriculum_drafts.py dry-run \\
        --base-url https://api.stoaedu.ch --manifest manifests/
    uv run python scripts/publish_curriculum_drafts.py apply \\
        --base-url https://api.stoaedu.ch --manifest manifests/ --confirm confirm_...

The admin access token is read from STOA_ADMIN_TOKEN, never from the command
line. Drafts are chosen by migration (`--migration ID`, or `--manifest FILE|DIR`,
whose migration the dry-run endpoint names), narrowed by `--only FILE` and
`--exclude FILE` (one publicLessonId per line).

The dry run reads every chosen version and its validation preview and lists what
would move and what is skipped and why: already published, changes requested,
blocking validation issues. It prints a confirmation code for exactly that list;
`apply` plans again, refuses when the list is no longer the same, and otherwise
moves each set through the steps it still lacks. A set an earlier run left in
review or approved goes on from there, a published one is skipped, so a run that
stopped is resumed by a new dry run and apply. The first refusal or failure stops
the run where it is and reports how far it got.

A set replacing one that was live when it was imported is published against that
version (`expectedPublishedVersionId`); if another version was published since,
the publish is refused as stale and the run stops for a person to decide.
"""

from __future__ import annotations

import argparse
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Protocol
import urllib.error
import urllib.parse
import urllib.request


TOKEN_ENV = "STOA_ADMIN_TOKEN"
ADMIN = "/admin/curriculum"
#: What each state still needs to be live, in order.
REMAINING_STEPS = {
    "draft": ("submit-review", "approve", "publish"),
    "in_review": ("approve", "publish"),
    "approved": ("publish",),
}
SKIPPED_STATES = {
    "published": "already published",
    "changes_requested": "a reviewer asked for changes",
    "archived": "archived",
    "superseded": "superseded",
}


class Api(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]: ...


class Refused(RuntimeError):
    """An admin call answered with anything but success."""

    def __init__(self, method: str, path: str, status: int, detail: Any) -> None:
        super().__init__(f"{method} {path} returned {status}: {json.dumps(detail)[:300]}")
        self.status = status
        self.detail = detail


class HttpApi:
    def __init__(self, base_url: str, token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        url = self._base_url + urllib.parse.quote(path)
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                status, payload = response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            status, payload = exc.code, exc.read().decode("utf-8")
        try:
            return status, json.loads(payload) if payload else None
        except json.JSONDecodeError:
            return status, payload


def _call(
    api: Api,
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    status, payload = api.request(method, path, params=params, body=body)
    if not 200 <= status < 300:
        detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
        raise Refused(method, path, status, detail)
    return payload


@dataclass(frozen=True)
class Candidate:
    public_id: str
    version_id: str
    migration_id: str
    #: The version that was live when the migration was applied, None for a new set.
    expected_published_version_id: str | None


@dataclass
class PlanRow:
    candidate: Candidate
    state: str | None
    steps: tuple[str, ...] = ()
    skip_reason: str | None = None
    done: list[str] = field(default_factory=list)

    @property
    def moves(self) -> bool:
        return bool(self.steps)

    def report(self) -> dict[str, Any]:
        return {
            "publicLessonId": self.candidate.public_id,
            "versionId": self.candidate.version_id,
            "migrationId": self.candidate.migration_id,
            "expectedPublishedVersionId": self.candidate.expected_published_version_id,
            "state": self.state,
            "steps": list(self.steps),
            "skipReason": self.skip_reason,
            "done": list(self.done),
        }


def migration_ids_of_manifests(api: Api, paths: Iterable[Path]) -> list[str]:
    """The migration each manifest became, named by the (read-only) dry-run endpoint."""
    ids = []
    for path in _manifest_files(paths):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        ids.append(_call(api, "POST", f"{ADMIN}/migrations/dry-run", body=manifest)["migrationId"])
    return ids


def _manifest_files(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        files.extend(sorted(path.glob("manifest-*.json")) if path.is_dir() else [path])
    return files


def select(
    api: Api,
    migration_ids: Sequence[str],
    *,
    only: Collection[str] | None = None,
    exclude: Collection[str] = (),
) -> list[Candidate]:
    """Every version the migrations applied, in their order, narrowed by the lists."""
    chosen: list[Candidate] = []
    seen: set[tuple[str, str]] = set()
    for migration_id in migration_ids:
        evidence = _call(api, "GET", f"{ADMIN}/migrations/{migration_id}")
        if evidence.get("status") != "applied":
            raise RuntimeError(f"{migration_id} is {evidence.get('status')!r}, not applied")
        for row in evidence.get("rows") or []:
            public_id, version_id = row.get("publicLessonId"), row.get("versionId")
            if row.get("status") != "applied" or not version_id:
                continue  # content unchanged: the migration wrote no version for it
            if (only is not None and public_id not in only) or public_id in exclude:
                continue
            if (public_id, version_id) in seen:
                continue
            seen.add((public_id, version_id))
            rollback = row.get("rollback") or {}
            chosen.append(
                Candidate(
                    public_id=public_id,
                    version_id=version_id,
                    migration_id=migration_id,
                    expected_published_version_id=rollback.get("previousPublishedVersionId"),
                )
            )
    return chosen


def plan(api: Api, candidates: Iterable[Candidate]) -> list[PlanRow]:
    """What each version still needs, or why it stays where it is. Reads only."""
    rows = []
    for candidate in candidates:
        lesson = f"{ADMIN}/lessons/{candidate.public_id}"
        try:
            version = _call(
                api, "GET", f"{lesson}/preview", params={"versionId": candidate.version_id}
            )
        except Refused as refused:
            if refused.status != 404:
                raise
            rows.append(PlanRow(candidate, None, skip_reason="version not found"))
            continue
        state = version.get("state")
        if state not in REMAINING_STEPS:
            reason = SKIPPED_STATES.get(state, f"state {state}")
            rows.append(PlanRow(candidate, state, skip_reason=reason))
            continue
        # A POST, but it only reads: it validates the version as publish would.
        validation = _call(
            api, "POST", f"{lesson}/drafts/{candidate.version_id}/validation-preview"
        )
        if not validation.get("publishReady"):
            fields = sorted({issue.get("field") for issue in validation.get("issues") or []})
            rows.append(
                PlanRow(candidate, state, skip_reason="validation issues: " + ", ".join(fields))
            )
            continue
        rows.append(PlanRow(candidate, state, steps=REMAINING_STEPS[state]))
    return rows


def confirmation_code(rows: Iterable[PlanRow]) -> str:
    """Names exactly the versions that would move and the steps each would take."""
    moving = [
        [
            row.candidate.public_id,
            row.candidate.version_id,
            row.candidate.expected_published_version_id,
            list(row.steps),
        ]
        for row in rows
        if row.moves
    ]
    digest = hashlib.sha256(json.dumps(moving, sort_keys=True).encode("utf-8")).hexdigest()
    return f"confirm_{digest[:16]}"


def apply(api: Api, rows: Sequence[PlanRow], *, out: Any = sys.stdout) -> None:
    """Move every row through its steps, recording each step done; the first refusal raises."""
    moving = [row for row in rows if row.moves]
    for number, row in enumerate(moving, start=1):
        candidate = row.candidate
        draft = f"{ADMIN}/lessons/{candidate.public_id}/drafts/{candidate.version_id}"
        for step in row.steps:
            if step == "publish":
                _call(
                    api,
                    "POST",
                    f"{ADMIN}/lessons/{candidate.public_id}/publish",
                    body={
                        "versionId": candidate.version_id,
                        "expectedPublishedVersionId": candidate.expected_published_version_id,
                        "reason": f"bulk publish of {candidate.migration_id}",
                    },
                )
            else:
                _call(api, "POST", f"{draft}/{step}")
            row.done.append(step)
        print(f"[{number}/{len(moving)}] {candidate.public_id} published", file=out, flush=True)


def run(
    api: Api,
    migration_ids: Sequence[str],
    *,
    only: set[str] | None,
    exclude: set[str],
    confirm: str | None,
    report: Path | None,
    out: Any = sys.stdout,
) -> int:
    """The dry run without `confirm`, the apply with it. Returns the exit code."""
    rows = plan(api, select(api, migration_ids, only=only, exclude=exclude))
    code = confirmation_code(rows)
    moving = [row for row in rows if row.moves]
    skipped = [row for row in rows if not row.moves]
    if confirm is None:
        for row in rows:
            what = " -> ".join(row.steps) if row.moves else f"skip: {row.skip_reason}"
            print(f"{row.candidate.public_id} ({row.state}): {what}", file=out)
        print(f"{len(moving)} to publish, {len(skipped)} skipped; confirmation {code}", file=out)
        _write_report(report, rows, stopped=None)
        return 0
    if confirm != code:
        print(
            f"the plan is not the one confirmed ({confirm}); it is now {code} - "
            "run the dry run again and check it",
            file=sys.stderr,
        )
        return 2
    stopped: PlanRow | None = None
    failure: Exception | None = None
    try:
        apply(api, rows, out=out)
    except (Refused, OSError) as exc:
        failure = exc
        stopped = next(row for row in moving if row.done != list(row.steps))
    _write_report(report, rows, stopped=stopped)
    published = sum(1 for row in moving if row.done == list(row.steps))
    if stopped is not None:
        step = stopped.steps[len(stopped.done)]
        print(
            f"stopped at {stopped.candidate.public_id} ({step}): {failure}\n"
            f"{published} of {len(moving)} published; run the dry run again to go on",
            file=sys.stderr,
        )
        return 1
    print(f"{published} published, {len(skipped)} skipped", file=out)
    return 0


def _write_report(path: Path | None, rows: Sequence[PlanRow], *, stopped: PlanRow | None) -> None:
    if path is None:
        return
    document = {
        "rows": [row.report() for row in rows],
        "stoppedAt": stopped.candidate.public_id if stopped else None,
    }
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _id_list(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("command", choices=("dry-run", "apply"))
    parser.add_argument("--base-url", required=True, help="e.g. https://api.stoaedu.ch")
    parser.add_argument("--migration", action="append", default=[], metavar="ID")
    parser.add_argument(
        "--manifest", action="append", default=[], type=Path, metavar="FILE|DIR",
        help="a manifest file, or a directory of manifest-*.json",
    )
    parser.add_argument("--only", type=Path, help="publish only these publicLessonIds")
    parser.add_argument("--exclude", type=Path, help="leave these publicLessonIds out")
    parser.add_argument("--confirm", help="the confirmation code the dry run printed")
    parser.add_argument("--report", type=Path, help="write every row and its outcome here")
    args = parser.parse_args(argv)
    if args.command == "apply" and not args.confirm:
        parser.error("apply needs --confirm with the code of the dry run")
    if not args.migration and not args.manifest:
        parser.error("name at least one --migration or --manifest")
    token = os.environ.get(TOKEN_ENV)
    if not token:
        parser.error(f"set {TOKEN_ENV} to an admin access token")

    api = HttpApi(args.base_url, token)
    try:
        migration_ids = [*args.migration, *migration_ids_of_manifests(api, args.manifest)]
        return run(
            api,
            migration_ids,
            only=_id_list(args.only),
            exclude=_id_list(args.exclude) or set(),
            confirm=args.confirm if args.command == "apply" else None,
            report=args.report,
        )
    except (RuntimeError, OSError, ValueError) as error:
        print(f"nothing moved: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
