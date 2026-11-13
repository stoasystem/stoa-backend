"""The curriculum operations an agent may run: read, import, publish, roll back (#426).

Each mirrors the console's curriculum desk by calling the same services -
`curriculum_migration_service` for manifests and `curriculum_ops_service` for a
lesson's versions - under the same rules: validation, the review states, the
conditional publish against the version that was live, the publish analytics.
The one difference is who: every version, manifest and lifecycle event they
write names `operator:agent_mcp`, and the operator call's own audit row - which
carries the fingerprint of the caller's SSO session - names the migration or
lesson, so the two join.

Two things the console leaves to the person's eye are made explicit here,
because a manifest from October nearly replaced five live lessons without
anyone noticing (#423):

- an `update` row (a new version of a lesson that is live now) is listed on its
  own by the dry run, and an import is refused unless `confirmUpdates` names
  exactly those lessons;
- a publish that would replace a live version is listed under `replacements`,
  and refused unless `confirmReplacements` names exactly those lessons.

A publish runs lesson after lesson and stops at the first refusal - another
version having gone live in between, say - and answers with how far it got.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import logging
import time
from typing import Any

from stoa.db.repositories import curriculum_ops_repo
from stoa.operator_calls import catalog
from stoa.operator_calls.catalog import (
    ApplyCurriculumMigrationArguments,
    DryRunCurriculumMigrationArguments,
    GetLessonStateArguments,
    GetMigrationArguments,
    PublishCurriculumDraftsArguments,
    RollbackLessonArguments,
)
from stoa.operator_calls.outcome import OperatorCallRefused, Outcome
from stoa.rule_violation import RuleViolation
from stoa.services import curriculum_migration_service, curriculum_ops_service


logger = logging.getLogger(__name__)

# The curriculum services check capabilities on a user map; an operator call has
# been verified as a production SSO administrator, so it holds all four.
OPERATOR_USER: dict[str, Any] = {
    "sub": catalog.OPERATOR_ACTOR_ID,
    "role": "operator",
    "capabilities": {
        capability: "granted" for capability in sorted(curriculum_ops_service.CURRICULUM_CAPABILITIES)
    },
}

#: How long a publish keeps starting new lessons. The function is cut off at 29
#: seconds, and the run's audit row is written after the last lesson, so it pauses
#: well before: the lessons done stay done and a new dry run goes on from there.
PUBLISH_TIME_BUDGET_SECONDS = 18.0
_clock = time.monotonic

#: What each state still needs to be live, in order (`scripts/publish_curriculum_drafts.py`).
REMAINING_STEPS: dict[str, tuple[str, ...]] = {
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


def _title(lesson: object) -> str | None:
    if isinstance(lesson, Mapping):
        title = lesson.get("title")
        return str(title) if title else None
    return None


def _published_version_id(public_id: str) -> str | None:
    pointer = curriculum_ops_repo.get_pointer(public_id) or {}
    value = pointer.get("published_version_id")
    return value if isinstance(value, str) else None


def _evidence(text: str) -> str:
    return text[:400]


def _id_list(values: Iterable[str], limit: int = 12) -> str:
    values = list(values)
    shown = ", ".join(values[:limit])
    return shown + (f" and {len(values) - limit} more" if len(values) > limit else "")


# -- reads ------------------------------------------------------------------------------


def get_lesson_state(arguments: GetLessonStateArguments) -> Outcome:
    public_id = arguments.publicLessonId.strip()
    pointer = curriculum_ops_repo.get_pointer(public_id) or {}
    versions = curriculum_ops_repo.list_versions(public_id)
    if not pointer and not versions:
        raise OperatorCallRefused(
            "lesson_not_found",
            f"No curriculum lesson {public_id}.",
            target_type="curriculum_lesson",
            target_id=public_id,
        )
    live = pointer.get("published_version_id")
    live = live if isinstance(live, str) else None
    previous = None
    manifest_id = pointer.get("manifest_id")
    if live and isinstance(manifest_id, str):
        manifest = curriculum_ops_repo.get_manifest(public_id, manifest_id) or {}
        value = manifest.get("previous_published_version_id")
        previous = value if isinstance(value, str) else None
    rows = sorted(versions, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    events: list[dict[str, Any]] = []
    if arguments.auditLimit:
        # Event keys are random, so the newest are found by time, not by key order.
        stored = curriculum_ops_repo.list_audit_events(public_id, limit=100)
        stored.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        events = [
            {
                "createdAt": event.get("created_at"),
                "operation": event.get("operation"),
                "versionId": event.get("version_id"),
                "fromState": event.get("from_state"),
                "toState": event.get("to_state"),
                "reason": event.get("reason"),
                "actorId": event.get("actor_id"),
            }
            for event in stored[: arguments.auditLimit]
        ]
    return Outcome(
        {
            "publicLessonId": public_id,
            "publishedVersionId": live,
            "previousPublishedVersionId": previous,
            "draftVersionId": pointer.get("draft_version_id"),
            "pointerUpdatedAt": pointer.get("updated_at"),
            "pointerUpdatedBy": pointer.get("updated_by"),
            "versions": [
                {
                    "versionId": version.get("version_id"),
                    "state": curriculum_ops_service._effective_state(version, live),  # noqa: SLF001
                    "reviewState": version.get("review_state"),
                    "title": _title(version.get("lesson")),
                    "exerciseCount": len(version.get("exercises") or []),
                    "migrationId": version.get("migration_id"),
                    "createdAt": version.get("created_at"),
                    "updatedAt": version.get("updated_at"),
                    "updatedBy": version.get("updated_by"),
                }
                for version in rows
            ],
            "events": events,
        },
        "curriculum_lesson",
        public_id,
        f"versions:{len(rows)}",
    )


def _slim_evidence_row(row: Mapping[str, Any]) -> dict[str, Any]:
    rollback = row.get("rollback") if isinstance(row.get("rollback"), Mapping) else {}
    return {
        "rowIndex": row.get("rowIndex"),
        "publicLessonId": row.get("publicLessonId"),
        "action": row.get("action"),
        "status": row.get("status"),
        "versionId": row.get("versionId"),
        "previousPublishedVersionId": rollback.get("previousPublishedVersionId"),
    }


def _migration_answer(evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "migrationId": evidence.get("migrationId"),
        "status": evidence.get("status"),
        "source": evidence.get("source") or {},
        "operatorNote": evidence.get("operatorNote"),
        "appliedBy": evidence.get("appliedBy"),
        "appliedAt": evidence.get("appliedAt"),
        "summary": evidence.get("summary") or {},
        "rows": [_slim_evidence_row(row) for row in evidence.get("rows") or []],
    }


def get_migration(arguments: GetMigrationArguments) -> Outcome:
    migration_id = arguments.migrationId.strip()
    evidence = curriculum_migration_service.get_migration(migration_id, OPERATOR_USER)
    return Outcome(
        _migration_answer(evidence),
        "curriculum_migration",
        migration_id,
        f"rows:{len(evidence.get('rows') or [])}",
    )


# -- dry run and apply ------------------------------------------------------------------


def _check_size(manifest: Mapping[str, Any]) -> None:
    size = len(json.dumps(manifest, separators=(",", ":"), default=str).encode("utf-8"))
    if size > catalog.MAX_MANIFEST_BYTES:
        raise OperatorCallRefused(
            "manifest_too_large",
            f"The manifest is {size} bytes as JSON; one call takes at most "
            f"{catalog.MAX_MANIFEST_BYTES}. Split it into smaller manifests.",
        )


@dataclass(frozen=True, slots=True)
class _Preview:
    answer: dict[str, Any]
    updates: tuple[str, ...]
    publish_rows: tuple[str, ...]


def _preview(manifest: dict[str, Any]) -> _Preview:
    _check_size(manifest)
    preview = curriculum_migration_service.dry_run(manifest, OPERATOR_USER)
    migration_id = preview["migrationId"]
    existing = curriculum_ops_repo.get_migration_evidence(migration_id) or {}
    rows = preview.get("rows") or []
    updates = [
        {
            "publicLessonId": row["publicLessonId"],
            "title": _title(row.get("lesson")),
            "currentPublishedVersionId": row.get("currentPublishedVersionId"),
        }
        for row in rows
        if row.get("action") == "update"
    ]
    publish_rows = [row["publicLessonId"] for row in rows if row.get("publishIntent")]
    answer = {
        "migrationId": migration_id,
        "confirmationCode": preview["confirmationToken"],
        "source": preview.get("source") or {},
        "operatorNote": preview.get("operatorNote"),
        "summary": preview.get("summary") or {},
        "publishReady": bool(preview.get("publishReady")),
        "alreadyApplied": existing.get("status") == "applied",
        "updates": updates,
        "publishMarkedRows": publish_rows,
        "rows": [
            {
                "rowIndex": row.get("rowIndex"),
                "publicLessonId": row.get("publicLessonId"),
                "title": _title(row.get("lesson")),
                "action": row.get("action"),
                "exerciseCount": len(row.get("exercises") or []),
                "currentPublishedVersionId": row.get("currentPublishedVersionId"),
                "expectedPublishedVersionId": row.get("expectedPublishedVersionId"),
                "validationIssues": row.get("validationIssues") or [],
                "conflicts": row.get("conflicts") or [],
            }
            for row in rows
        ],
    }
    return _Preview(
        answer,
        tuple(update["publicLessonId"] for update in updates),
        tuple(publish_rows),
    )


def _summary_evidence(migration_id: str, summary: Mapping[str, Any]) -> str:
    return (
        f"{migration_id} creates:{summary.get('creates', 0)} updates:{summary.get('updates', 0)} "
        f"skips:{summary.get('skips', 0)} conflicts:{summary.get('conflicts', 0)} "
        f"errors:{summary.get('errors', 0)}"
    )


def dry_run_curriculum_migration(arguments: DryRunCurriculumMigrationArguments) -> Outcome:
    preview = _preview(arguments.manifest)
    answer = preview.answer
    return Outcome(
        answer,
        "curriculum_migration",
        answer["migrationId"],
        _evidence(_summary_evidence(answer["migrationId"], answer["summary"])),
    )


def _apply_refusal(
    preview: _Preview, arguments: ApplyCurriculumMigrationArguments
) -> OperatorCallRefused | None:
    answer = preview.answer
    migration_id = answer["migrationId"]

    def refused(code: str, message: str) -> OperatorCallRefused:
        return OperatorCallRefused(
            code,
            message,
            target_type="curriculum_migration",
            target_id=migration_id,
            evidence=_evidence(_summary_evidence(migration_id, answer["summary"])),
        )

    if (
        arguments.migrationId.strip() != migration_id
        or arguments.confirmationCode.strip() != answer["confirmationCode"]
    ):
        return refused(
            "confirmation_mismatch",
            "migrationId and confirmationCode are not the ones this manifest gives; "
            "run the dry run on this manifest again.",
        )
    if preview.publish_rows:
        return refused(
            "publish_rows_not_allowed",
            f"{len(preview.publish_rows)} rows are marked publish ("
            + _id_list(preview.publish_rows)
            + "). Import drafts only: set publish to false and publish them with "
            "publish_curriculum_drafts.",
        )
    if not answer["publishReady"]:
        summary = answer["summary"]
        return refused(
            "migration_not_ready",
            f"The manifest has {summary.get('errors', 0)} rows with errors and "
            f"{summary.get('conflicts', 0)} conflicts; nothing was imported.",
        )
    confirmed = set(arguments.confirmUpdates)
    expected = set(preview.updates)
    if confirmed != expected:
        missing = sorted(expected - confirmed)
        extra = sorted(confirmed - expected)
        parts = []
        if missing:
            parts.append(
                f"{len(missing)} update rows not confirmed ({_id_list(missing)}): each "
                "writes a new version of a lesson that is live now"
            )
        if extra:
            parts.append(f"{len(extra)} confirmed lessons are not update rows ({_id_list(extra)})")
        return refused(
            "updates_not_confirmed",
            "; ".join(parts) + ". confirmUpdates must name exactly the dry run's updates.",
        )
    return None


def apply_curriculum_migration(arguments: ApplyCurriculumMigrationArguments) -> Outcome:
    preview = _preview(arguments.manifest)
    answer = preview.answer
    migration_id = answer["migrationId"]
    refusal = _apply_refusal(preview, arguments)
    summary_evidence = _summary_evidence(migration_id, answer["summary"])
    if arguments.dryRun:
        rehearsal = dict(answer)
        rehearsal["wouldBeRefused"] = (
            {"code": refusal.code, "message": refusal.message} if refusal else None
        )
        return Outcome(rehearsal, "curriculum_migration", migration_id, _evidence(summary_evidence))
    if refusal is not None:
        raise refusal
    evidence = curriculum_migration_service.apply_migration(
        migration_id,
        arguments.manifest,
        answer["confirmationCode"],
        OPERATOR_USER,
    )
    result = _migration_answer(evidence)
    result["idempotent"] = bool(evidence.get("idempotent"))
    result["confirmedUpdates"] = sorted(preview.updates)
    updates_note = f" updates confirmed: {_id_list(sorted(preview.updates), 8)}" if preview.updates else ""
    return Outcome(
        result,
        "curriculum_migration",
        migration_id,
        _evidence(summary_evidence + (" idempotent" if result["idempotent"] else "") + updates_note),
    )


# -- publish ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Candidate:
    public_id: str
    version_id: str
    # The version that was live when the migration was applied, None for a new lesson.
    expected_published_version_id: str | None


@dataclass(slots=True)
class _PlanRow:
    candidate: _Candidate
    state: str | None
    title: str | None = None
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
            "title": self.title,
            "state": self.state,
            "replacesVersionId": self.candidate.expected_published_version_id,
            "steps": list(self.steps),
            "skipReason": self.skip_reason,
            "done": list(self.done),
        }


def _candidates(
    evidence: Mapping[str, Any], *, only: Sequence[str] | None, exclude: Sequence[str]
) -> list[_Candidate]:
    rows = [row for row in evidence.get("rows") or [] if isinstance(row, Mapping)]
    known = {str(row.get("publicLessonId")) for row in rows}
    unknown = sorted({*(only or ()), *exclude} - known)
    if unknown:
        raise OperatorCallRefused(
            "unknown_lessons",
            f"{len(unknown)} named lessons are not in this migration: {_id_list(unknown)}.",
            target_type="curriculum_migration",
            target_id=str(evidence.get("migrationId") or ""),
        )
    chosen: list[_Candidate] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        public_id, version_id = str(row.get("publicLessonId")), row.get("versionId")
        if row.get("status") != "applied" or not isinstance(version_id, str):
            continue  # content unchanged: the migration wrote no version for it
        if (only is not None and public_id not in only) or public_id in exclude:
            continue
        if (public_id, version_id) in seen:
            continue
        seen.add((public_id, version_id))
        rollback = row.get("rollback") if isinstance(row.get("rollback"), Mapping) else {}
        previous = rollback.get("previousPublishedVersionId")
        chosen.append(
            _Candidate(public_id, version_id, previous if isinstance(previous, str) else None)
        )
    return chosen


def _plan(candidates: Iterable[_Candidate]) -> list[_PlanRow]:
    """What each version still needs, or why it stays where it is. Reads only."""
    rows: list[_PlanRow] = []
    moving = 0
    for candidate in candidates:
        version = curriculum_ops_repo.get_version(candidate.public_id, candidate.version_id)
        if not version:
            rows.append(_PlanRow(candidate, None, skip_reason="version not found"))
            continue
        live = _published_version_id(candidate.public_id)
        state = curriculum_ops_service._effective_state(version, live)  # noqa: SLF001
        title = _title(version.get("lesson"))
        if state not in REMAINING_STEPS:
            reason = SKIPPED_STATES.get(str(state), f"state {state}")
            rows.append(_PlanRow(candidate, state, title, skip_reason=reason))
            continue
        if live != candidate.expected_published_version_id:
            rows.append(
                _PlanRow(
                    candidate,
                    state,
                    title,
                    skip_reason=(
                        f"the live version is now {live or 'none'}, not "
                        f"{candidate.expected_published_version_id or 'none'} as when the "
                        "migration was applied; a person has to decide"
                    ),
                )
            )
            continue
        validation = curriculum_ops_service.validation_preview(
            candidate.public_id, candidate.version_id, OPERATOR_USER
        )
        if not validation.get("publishReady"):
            fields = sorted({str(issue.get("field")) for issue in validation.get("issues") or []})
            rows.append(
                _PlanRow(
                    candidate, state, title, skip_reason="validation issues: " + ", ".join(fields)
                )
            )
            continue
        if moving >= catalog.MAX_PUBLISH_LESSONS:
            rows.append(
                _PlanRow(
                    candidate,
                    state,
                    title,
                    skip_reason=(
                        f"beyond the {catalog.MAX_PUBLISH_LESSONS} lessons of one call; "
                        "dry-run again after this run"
                    ),
                )
            )
            continue
        moving += 1
        rows.append(_PlanRow(candidate, state, title, steps=REMAINING_STEPS[str(state)]))
    return rows


def confirmation_code(rows: Iterable[_PlanRow]) -> str:
    """Names exactly the versions that would move and the steps each would take.

    The same digest as `scripts/publish_curriculum_drafts.py`, so the two agree."""
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


def _replacements(rows: Iterable[_PlanRow]) -> list[dict[str, Any]]:
    return [
        {
            "publicLessonId": row.candidate.public_id,
            "title": row.title,
            "versionId": row.candidate.version_id,
            "replacesVersionId": row.candidate.expected_published_version_id,
        }
        for row in rows
        if row.moves and row.candidate.expected_published_version_id is not None
    ]


def _step(row: _PlanRow, step: str, migration_id: str) -> None:
    candidate = row.candidate
    if step == "submit-review":
        curriculum_ops_service.submit_review(candidate.public_id, candidate.version_id, OPERATOR_USER)
    elif step == "approve":
        curriculum_ops_service.approve(candidate.public_id, candidate.version_id, OPERATOR_USER)
    else:
        curriculum_ops_service.publish(
            candidate.public_id,
            candidate.version_id,
            OPERATOR_USER,
            expected_published_version_id=candidate.expected_published_version_id,
            reason=f"bulk publish of {migration_id} by agent",
        )


def publish_curriculum_drafts(arguments: PublishCurriculumDraftsArguments) -> Outcome:
    migration_id = arguments.migrationId.strip()
    evidence = curriculum_migration_service.get_migration(migration_id, OPERATOR_USER)
    if evidence.get("status") != "applied":
        raise OperatorCallRefused(
            "migration_not_applied",
            f"{migration_id} is {evidence.get('status')!r}, not applied.",
            target_type="curriculum_migration",
            target_id=migration_id,
        )
    rows = _plan(
        _candidates(evidence, only=arguments.onlyLessonIds, exclude=arguments.excludeLessonIds)
    )
    code = confirmation_code(rows)
    moving = [row for row in rows if row.moves]
    replacements = _replacements(rows)
    plan_evidence = (
        f"{migration_id} to_publish:{len(moving)} skipped:{len(rows) - len(moving)} "
        f"replacements:{len(replacements)}"
    )
    if arguments.dryRun:
        return Outcome(
            {
                "migrationId": migration_id,
                "confirmationCode": code,
                "toPublish": len(moving),
                "skipped": len(rows) - len(moving),
                "replacements": replacements,
                "rows": [row.report() for row in rows],
            },
            "curriculum_migration",
            migration_id,
            _evidence(plan_evidence),
        )

    def refused(code_: str, message: str) -> OperatorCallRefused:
        return OperatorCallRefused(
            code_,
            message,
            target_type="curriculum_migration",
            target_id=migration_id,
            evidence=_evidence(plan_evidence),
        )

    if not arguments.confirmationCode:
        raise refused(
            "confirmation_required", "Run with dryRun=true first and pass its confirmationCode."
        )
    if arguments.confirmationCode.strip() != code:
        raise refused(
            "plan_changed",
            "The plan is not the one confirmed; nothing was published. Run the dry run "
            "again and show the person the new plan.",
        )
    expected = {item["publicLessonId"] for item in replacements}
    confirmed = set(arguments.confirmReplacements)
    if confirmed != expected:
        missing, extra = sorted(expected - confirmed), sorted(confirmed - expected)
        parts = []
        if missing:
            parts.append(
                f"{len(missing)} replacements not confirmed ({_id_list(missing)}): each "
                "replaces the version students see now"
            )
        if extra:
            parts.append(f"{len(extra)} confirmed lessons are not replacements ({_id_list(extra)})")
        raise refused(
            "replacements_not_confirmed",
            "; ".join(parts) + ". confirmReplacements must name exactly the dry run's replacements.",
        )

    stopped: _PlanRow | None = None
    stop_code = ""
    started = _clock()
    for row in moving:
        if _clock() - started > PUBLISH_TIME_BUDGET_SECONDS:
            stopped, stop_code = row, "time_budget"
            break
        try:
            for step in row.steps:
                _step(row, step, migration_id)
                row.done.append(step)
        except RuleViolation as violation:
            stopped, stop_code = row, str(violation.code.value)
        except Exception:  # noqa: BLE001 - lessons already published stay published
            logger.exception("curriculum publish of %s stopped at %s", migration_id, row.candidate.public_id)
            stopped, stop_code = row, "failed"
        if stopped is not None:
            break
    published = [row.candidate.public_id for row in moving if row.done == list(row.steps)]
    result: dict[str, Any] = {
        "migrationId": migration_id,
        "status": (
            "completed" if stopped is None else "paused" if stop_code == "time_budget" else "stopped"
        ),
        "published": published,
        "publishedCount": len(published),
        "plannedCount": len(moving),
        "skipped": len(rows) - len(moving),
        "rows": [row.report() for row in rows],
        "stoppedAt": None,
    }
    if stopped is not None:
        result["stoppedAt"] = {
            "publicLessonId": stopped.candidate.public_id,
            "step": stopped.steps[len(stopped.done)],
            "code": stop_code,
            "message": (
                "Paused before this lesson to stay within the function's time limit; "
                "run the dry run again and confirm its new plan to go on."
                if stop_code == "time_budget"
                else "Stopped here; lessons after it were not touched. Look at the lesson "
                "with get_lesson_state, then run the dry run again to go on."
            ),
        }
    stop_note = (
        f" stopped:{stopped.candidate.public_id}:{stop_code}" if stopped is not None else ""
    )
    return Outcome(
        result,
        "curriculum_migration",
        migration_id,
        _evidence(
            f"{migration_id} published:{len(published)}/{len(moving)}{stop_note} "
            f"lessons:{_id_list(published, 10)}"
        ),
    )


# -- rollback ---------------------------------------------------------------------------


def rollback_lesson(arguments: RollbackLessonArguments) -> Outcome:
    public_id = arguments.publicLessonId.strip()
    reason = arguments.reason.strip()
    pointer = curriculum_ops_repo.get_pointer(public_id) or {}
    live = pointer.get("published_version_id")
    if not isinstance(live, str):
        raise OperatorCallRefused(
            "not_published",
            f"{public_id} has no live version to roll back.",
            target_type="curriculum_lesson",
            target_id=public_id,
        )
    target = arguments.versionId
    if target is None:
        manifest_id = pointer.get("manifest_id")
        manifest = (
            curriculum_ops_repo.get_manifest(public_id, manifest_id)
            if isinstance(manifest_id, str)
            else None
        ) or {}
        previous = manifest.get("previous_published_version_id")
        target = previous if isinstance(previous, str) else None
        if target is None:
            raise OperatorCallRefused(
                "no_previous_version",
                f"{public_id} had no live version before {live}; name versionId.",
                target_type="curriculum_lesson",
                target_id=public_id,
            )
    if target == live:
        raise OperatorCallRefused(
            "already_live",
            f"{target} is already the live version of {public_id}.",
            target_type="curriculum_lesson",
            target_id=public_id,
        )
    version = curriculum_ops_repo.get_version(public_id, target)
    if not version:
        raise OperatorCallRefused(
            "version_not_found",
            f"{public_id} has no version {target}.",
            target_type="curriculum_lesson",
            target_id=public_id,
        )
    evidence = _evidence(f"{public_id} {live} -> {target}; reason: {reason}")
    answer: dict[str, Any] = {
        "publicLessonId": public_id,
        "liveVersionId": live,
        "rollbackToVersionId": target,
        "rollbackToState": curriculum_ops_service._effective_state(version, live),  # noqa: SLF001
        "rollbackToTitle": _title(version.get("lesson")),
        "rollbackToCreatedAt": version.get("created_at"),
    }
    if arguments.dryRun:
        allowed = version.get("state") in curriculum_ops_service.ROLLBACK_STATES
        answer["wouldBeRefused"] = (
            None
            if allowed
            else {
                "code": "rollback_target_not_publishable",
                "message": f"{target} is {version.get('state')}; it was never approved.",
            }
        )
        return Outcome(answer, "curriculum_lesson", public_id, evidence)
    if arguments.expectedPublishedVersionId is None:
        raise OperatorCallRefused(
            "expected_version_required",
            "Pass the live version the dry run showed as expectedPublishedVersionId.",
            target_type="curriculum_lesson",
            target_id=public_id,
            evidence=evidence,
        )
    if arguments.expectedPublishedVersionId != live:
        raise OperatorCallRefused(
            "stale_pointer",
            f"The live version of {public_id} is now {live}, not the one the dry run "
            "showed; nothing was changed. Run the dry run again.",
            target_type="curriculum_lesson",
            target_id=public_id,
            evidence=evidence,
        )
    outcome = curriculum_ops_service.rollback(
        public_id,
        target,
        OPERATOR_USER,
        expected_published_version_id=live,
        reason=f"{reason} (agent)",
    )
    pointer_after = outcome.get("pointer") or {}
    answer["status"] = outcome.get("status")
    answer["publishedVersionId"] = pointer_after.get("publishedVersionId")
    answer["manifestId"] = pointer_after.get("manifestId")
    return Outcome(answer, "curriculum_lesson", public_id, evidence)
