"""#426: an agent imports, publishes and rolls back curriculum through operator calls.

Everything runs the real migration and curriculum services against one table
double seeded with the real practice seed, as `test_curriculum_publish_projection`
does, so a lesson an operator call publishes is one students could read.
"""

from __future__ import annotations

from functools import partial
from typing import Any

import pytest

from test_curriculum_publish_projection import install_seeded_table
from test_operator_calls import (
    AUDIT_KEY,
    FUNCTION_ARN,
    SIGNED,
    _audit_rows,
    _business_rows_added,
    _call,
    _rows,
    _sts_xml,
)

from stoa.db.repositories import curriculum_ops_repo
from stoa.operator_calls import caller_identity, catalog, curriculum, entry
from stoa.services import curriculum_analytics_service, curriculum_ops_service


CONSOLE = {
    "sub": "console-admin-1",
    "role": "admin",
    "capabilities": {
        curriculum_ops_service.AUTHOR_CAPABILITY: "granted",
        curriculum_ops_service.REVIEWER_CAPABILITY: "granted",
        curriculum_ops_service.PUBLISHER_CAPABILITY: "granted",
    },
}
NEW_1 = "zap1-op-test-001"
LIVE = "zap1-op-test-002"
NEW_2 = "zap1-op-test-003"


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch):
    return install_seeded_table(monkeypatch)


@pytest.fixture
def publish_events(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    monkeypatch.setattr(
        curriculum_analytics_service,
        "record_publish_event",
        lambda version, *, operation: events.append((str(version["public_id"]), operation)),
    )
    return events


def _exercise(public_id: str, number: int = 1, answer: str = "1") -> dict[str, Any]:
    return {
        "exerciseId": f"{public_id}-q{number:02d}",
        "type": "text_input",
        "prompt": f"Berechne {number}/4 + {4 - number}/4.",
        "answerKey": answer,
        "explanation": f"{number}/4 + {4 - number}/4 = 4/4 = 1.",
        "difficulty": "practice",
        "skills": ["brueche-addieren"],
    }


def _lesson(public_id: str, *, title: str = "Brüche addieren", answer: str = "1", **extra: Any):
    return {
        "publicLessonId": public_id,
        "title": title,
        "objective": "Gleichnamige Brüche addieren.",
        "subjectId": "math",
        "topicId": "brueche",
        "unitId": "brueche-u2",
        "gradeLevel": "grade_6_primary",
        "language": "de",
        "difficulty": "practice",
        "publish": False,
        "exercises": [_exercise(public_id, answer=answer)],
        **extra,
    }


def _manifest(*lessons: dict[str, Any], note: str = "ZAP1 test batch") -> dict[str, Any]:
    return {
        "source": {"sourceId": "zap1", "sourceVersion": "2026-11", "sourceType": "manifest"},
        "operatorNote": note,
        "lessons": list(lessons),
    }


def _console_publish(public_id: str, *, answer: str = "1", expected: str | None = None) -> str:
    """A lesson put live by hand in the console, as batch 1 was."""
    payload = _lesson(public_id, answer=answer)
    payload.pop("publish")
    version_id = curriculum_ops_service.create_lesson_draft(payload, CONSOLE)["versionId"]
    curriculum_ops_service.submit_review(public_id, version_id, CONSOLE)
    curriculum_ops_service.approve(public_id, version_id, CONSOLE)
    curriculum_ops_service.publish(
        public_id, version_id, CONSOLE, expected_published_version_id=expected
    )
    return version_id


def _live(public_id: str) -> str | None:
    return (curriculum_ops_repo.get_pointer(public_id) or {}).get("published_version_id")


def _ok(answer: dict) -> dict:
    assert answer["ok"] is True, answer
    return answer["result"]


def _refused(answer: dict, code: str) -> str:
    assert answer["ok"] is False, answer
    assert answer["error"]["code"] == code, answer
    return answer["error"]["message"]


def _batch() -> tuple[dict[str, Any], str]:
    """NEW_1, then LIVE (live now, so an update), then NEW_2."""
    live_version = _console_publish(LIVE)
    manifest = _manifest(
        _lesson(NEW_1), _lesson(LIVE, title="Brüche addieren (neu)", answer="4/4"), _lesson(NEW_2)
    )
    return manifest, live_version


def _apply(manifest: dict[str, Any], **fields: Any) -> dict:
    check = _ok(_call("dry_run_curriculum_migration", {"manifest": manifest}))
    arguments = {
        "migrationId": check["migrationId"],
        "confirmationCode": check["confirmationCode"],
        "manifest": manifest,
        "confirmUpdates": [row["publicLessonId"] for row in check["updates"]],
        "dryRun": False,
    }
    arguments.update(fields)
    return _call("apply_curriculum_migration", arguments)


def _publish(migration_id: str, *, dry: bool, **fields: Any) -> dict:
    return _call(
        "publish_curriculum_drafts", {"migrationId": migration_id, "dryRun": dry, **fields}
    )


def _confirmed_publish(migration_id: str, **fields: Any) -> dict:
    plan = _ok(_publish(migration_id, dry=True))
    return _publish(
        migration_id,
        dry=False,
        confirmationCode=plan["confirmationCode"],
        confirmReplacements=[row["publicLessonId"] for row in plan["replacements"]],
        **fields,
    )


# -- the catalog ----------------------------------------------------------------------


def test_the_curriculum_operations_are_listed_with_their_rehearsal() -> None:
    for name in ("apply_curriculum_migration", "publish_curriculum_drafts", "rollback_lesson"):
        spec = catalog.OPERATIONS_BY_NAME[name]
        assert spec.effect is catalog.Effect.WRITE
        assert "dryRun=true" in spec.description and "confirm with the person" in spec.description
        assert "dryRun" in spec.input_schema()["required"]
    assert "confirmUpdates" in catalog.OPERATIONS_BY_NAME["apply_curriculum_migration"].description
    assert (
        "confirmReplacements"
        in catalog.OPERATIONS_BY_NAME["publish_curriculum_drafts"].description
    )
    for name in ("get_lesson_state", "get_migration", "dry_run_curriculum_migration"):
        assert catalog.OPERATIONS_BY_NAME[name].effect is catalog.Effect.READ


# -- who may call ---------------------------------------------------------------------


@pytest.mark.parametrize("operation", ["apply_curriculum_migration", "publish_curriculum_drafts"])
def test_an_unverified_caller_imports_and_publishes_nothing(table, operation) -> None:
    manifest, _ = _batch()
    before = _rows(table)

    def refuse(*_args: object, **_kwargs: object) -> str:
        raise caller_identity.CallerNotVerified(
            "This is the wrong account; run 'aws sso login --sso-session stoa'."
        )

    answer = entry.handle(
        {
            "operation": operation,
            "arguments": {
                "migrationId": "migration_x",
                "confirmationCode": "confirm_x",
                "manifest": manifest,
                "dryRun": False,
            },
            "callerIdentity": SIGNED,
        },
        invoked_function_arn=FUNCTION_ARN,
        region="eu-central-2",
        verify=refuse,
        audit_key=lambda: AUDIT_KEY,
    )

    _refused(answer, "caller_not_verified")
    assert _rows(table) == before


def test_a_call_from_another_account_is_refused_before_anything_runs(table) -> None:
    manifest, _ = _batch()
    before = _rows(table)

    answer = entry.handle(
        {
            "operation": "dry_run_curriculum_migration",
            "arguments": {"manifest": manifest},
            "callerIdentity": SIGNED,
        },
        invoked_function_arn=FUNCTION_ARN,
        region="eu-central-2",
        # STS says the signer belongs to another AWS account than the production function.
        verify=partial(
            caller_identity.verify,
            post=lambda *_: caller_identity.StsAnswer(200, _sts_xml(account="111122223333")),
        ),
        audit_key=lambda: AUDIT_KEY,
    )

    _refused(answer, "caller_not_verified")
    assert _rows(table) == before


# -- dry run and import ---------------------------------------------------------------


def test_the_dry_run_lists_updates_of_live_lessons_on_their_own_and_writes_nothing(table) -> None:
    manifest, live_version = _batch()
    before = _rows(table)

    result = _ok(_call("dry_run_curriculum_migration", {"manifest": manifest}))

    assert result["summary"]["creates"] == 2 and result["summary"]["updates"] == 1
    assert result["updates"] == [
        {
            "publicLessonId": LIVE,
            "title": "Brüche addieren (neu)",
            "currentPublishedVersionId": live_version,
        }
    ]
    assert result["publishReady"] is True and result["alreadyApplied"] is False
    assert [row["action"] for row in result["rows"]] == ["create", "update", "create"]
    assert "exercises" not in result["rows"][0]  # counts, not content
    assert _business_rows_added(table, before) == set()
    (row,) = _audit_rows(table)
    assert row["action"] == "dry_run_curriculum_migration"
    assert row["target_id"] == result["migrationId"]
    assert "updates:1" in row["evidence_reference"]


def test_an_import_with_unconfirmed_updates_is_refused_and_writes_nothing(table) -> None:
    manifest, live_version = _batch()
    before = _rows(table)

    message = _refused(_apply(manifest, confirmUpdates=[]), "updates_not_confirmed")

    assert LIVE in message
    assert _business_rows_added(table, before) == set()
    assert _live(LIVE) == live_version
    assert _audit_rows(table)[-1]["result_code"] == "updates_not_confirmed"


def test_confirming_a_lesson_that_is_not_an_update_is_refused_too(table) -> None:
    manifest, _ = _batch()

    _refused(_apply(manifest, confirmUpdates=[LIVE, NEW_1]), "updates_not_confirmed")


def test_an_import_with_the_wrong_confirmation_code_is_refused(table) -> None:
    manifest, _ = _batch()
    before = _rows(table)

    _refused(_apply(manifest, confirmationCode="confirm_0000000000000000"), "confirmation_mismatch")

    # The code belongs to the manifest: a changed manifest needs a new dry run.
    check = _ok(_call("dry_run_curriculum_migration", {"manifest": manifest}))
    changed = _manifest(*manifest["lessons"], note="edited after the dry run")
    answer = _call(
        "apply_curriculum_migration",
        {
            "migrationId": check["migrationId"],
            "confirmationCode": check["confirmationCode"],
            "manifest": changed,
            "confirmUpdates": [LIVE],
            "dryRun": False,
        },
    )
    _refused(answer, "confirmation_mismatch")
    assert _business_rows_added(table, before) == set()


def test_rows_marked_publish_are_refused_so_nothing_goes_live_on_import(table) -> None:
    manifest = _manifest(_lesson(NEW_1, publish=True))

    message = _refused(_apply(manifest), "publish_rows_not_allowed")

    assert NEW_1 in message
    assert _live(NEW_1) is None


def test_a_rehearsed_import_says_whether_it_would_be_refused(table) -> None:
    manifest, _ = _batch()
    check = _ok(_call("dry_run_curriculum_migration", {"manifest": manifest}))
    before = _rows(table)

    result = _ok(
        _call(
            "apply_curriculum_migration",
            {
                "migrationId": check["migrationId"],
                "confirmationCode": check["confirmationCode"],
                "manifest": manifest,
                "dryRun": True,
            },
        )
    )

    assert result["wouldBeRefused"]["code"] == "updates_not_confirmed"
    assert _business_rows_added(table, before) == set()
    assert _audit_rows(table)[-1]["dry_run"] is True


def test_a_confirmed_import_writes_drafts_as_the_operator_and_nothing_goes_live(table) -> None:
    manifest, live_version = _batch()

    result = _ok(_apply(manifest))

    assert result["status"] == "applied" and result["idempotent"] is False
    assert result["confirmedUpdates"] == [LIVE]
    assert {row["publicLessonId"]: row["previousPublishedVersionId"] for row in result["rows"]} == {
        NEW_1: None,
        LIVE: live_version,
        NEW_2: None,
    }
    for row in result["rows"]:
        version = curriculum_ops_repo.get_version(row["publicLessonId"], row["versionId"])
        assert version is not None
        assert version["state"] == "draft"
        assert version["created_by"] == catalog.OPERATOR_ACTOR_ID
    assert _live(LIVE) == live_version and _live(NEW_1) is None
    row = _audit_rows(table)[-1]
    assert row["action"] == "apply_curriculum_migration" and row["dry_run"] is False
    assert row["target_id"] == result["migrationId"]
    assert f"updates confirmed: {LIVE}" in row["evidence_reference"]

    # The same manifest again changes nothing.
    assert _ok(_apply(manifest))["idempotent"] is True


def test_get_migration_reads_the_import_back(table) -> None:
    manifest, _ = _batch()
    applied = _ok(_apply(manifest))

    result = _ok(_call("get_migration", {"migrationId": applied["migrationId"]}))

    assert result["status"] == "applied"
    assert result["appliedBy"] == catalog.OPERATOR_ACTOR_ID
    assert [row["publicLessonId"] for row in result["rows"]] == [NEW_1, LIVE, NEW_2]
    _refused(_call("get_migration", {"migrationId": "migration_missing"}), "migration_not_found")


def test_a_manifest_over_the_limit_is_refused(table, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catalog, "MAX_MANIFEST_BYTES", 100)

    _refused(
        _call("dry_run_curriculum_migration", {"manifest": _manifest(_lesson(NEW_1))}),
        "manifest_too_large",
    )


# -- publish --------------------------------------------------------------------------


def test_the_publish_dry_run_lists_replacements_and_moves_nothing(table) -> None:
    manifest, live_version = _batch()
    migration_id = _ok(_apply(manifest))["migrationId"]
    before = _rows(table)

    plan = _ok(_publish(migration_id, dry=True))

    assert plan["toPublish"] == 3 and plan["skipped"] == 0
    assert [(row["publicLessonId"], row["replacesVersionId"]) for row in plan["replacements"]] == [
        (LIVE, live_version)
    ]
    assert plan["rows"][0]["steps"] == ["submit-review", "approve", "publish"]
    assert _business_rows_added(table, before) == set()


def test_a_publish_needs_the_dry_runs_code_and_its_replacements_confirmed(table) -> None:
    manifest, live_version = _batch()
    migration_id = _ok(_apply(manifest))["migrationId"]
    plan = _ok(_publish(migration_id, dry=True))
    before = _rows(table)

    _refused(_publish(migration_id, dry=False), "confirmation_required")
    _refused(
        _publish(migration_id, dry=False, confirmationCode="confirm_0000000000000000"),
        "plan_changed",
    )
    message = _refused(
        _publish(migration_id, dry=False, confirmationCode=plan["confirmationCode"]),
        "replacements_not_confirmed",
    )

    assert LIVE in message
    assert _business_rows_added(table, before) == set()
    assert _live(LIVE) == live_version


def test_a_confirmed_publish_puts_every_lesson_live_as_the_operator(table, publish_events) -> None:
    manifest, live_version = _batch()
    migration_id = _ok(_apply(manifest))["migrationId"]
    publish_events.clear()

    result = _ok(_confirmed_publish(migration_id))

    assert result["status"] == "completed"
    assert result["published"] == [NEW_1, LIVE, NEW_2]
    assert sorted(publish_events) == sorted(
        [(NEW_1, "publish"), (LIVE, "publish"), (NEW_2, "publish")]
    )
    state = _ok(_call("get_lesson_state", {"publicLessonId": LIVE}))
    assert state["previousPublishedVersionId"] == live_version
    assert state["pointerUpdatedBy"] == catalog.OPERATOR_ACTOR_ID
    states = {version["versionId"]: version["state"] for version in state["versions"]}
    assert states[live_version] == "superseded"
    assert states[state["publishedVersionId"]] == "published"
    assert state["events"][0]["operation"] == "publish"
    assert state["events"][0]["actorId"] == catalog.OPERATOR_ACTOR_ID
    row = [r for r in _audit_rows(table) if r["action"] == "publish_curriculum_drafts"][-1]
    assert row["dry_run"] is False and row["target_id"] == migration_id
    assert "published:3/3" in row["evidence_reference"]

    # Run again: everything is already published, so nothing moves.
    again = _ok(_publish(migration_id, dry=True))
    assert again["toPublish"] == 0
    assert {row["skipReason"] for row in again["rows"]} == {"already published"}


def test_only_and_exclude_narrow_the_publish(table) -> None:
    manifest, _ = _batch()
    migration_id = _ok(_apply(manifest))["migrationId"]

    plan = _ok(_publish(migration_id, dry=True, onlyLessonIds=[NEW_1, NEW_2], excludeLessonIds=[NEW_2]))

    assert [row["publicLessonId"] for row in plan["rows"]] == [NEW_1]
    _refused(_publish(migration_id, dry=True, onlyLessonIds=["not-in-it"]), "unknown_lessons")


def test_a_publish_stops_where_another_version_went_live_meanwhile(
    table, publish_events, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, live_version = _batch()
    migration_id = _ok(_apply(manifest))["migrationId"]
    plan = _ok(_publish(migration_id, dry=True))
    real_publish = curriculum_ops_service.publish
    console_version: list[str] = []

    def publish_then_someone_else_does(public_id: str, *args: Any, **kwargs: Any):
        answer = real_publish(public_id, *args, **kwargs)
        if public_id == NEW_1:
            # While the run goes on, someone puts another version of LIVE live by hand.
            console_version.append(_console_publish(LIVE, answer="2/2", expected=live_version))
        return answer

    monkeypatch.setattr(curriculum_ops_service, "publish", publish_then_someone_else_does)

    result = _ok(
        _publish(
            migration_id,
            dry=False,
            confirmationCode=plan["confirmationCode"],
            confirmReplacements=[LIVE],
        )
    )

    assert result["status"] == "stopped"
    assert result["published"] == [NEW_1]
    assert result["stoppedAt"]["publicLessonId"] == LIVE
    assert result["stoppedAt"]["step"] == "publish"
    assert result["stoppedAt"]["code"] == "stale_pointer"
    # The version put live by hand stays live; the lesson after it was not touched.
    assert _live(LIVE) == console_version[0]
    assert _live(NEW_2) is None
    new_2 = next(row for row in result["rows"] if row["publicLessonId"] == NEW_2)
    assert new_2["done"] == []
    row = _audit_rows(table)[-1]
    assert f"stopped:{LIVE}:stale_pointer" in row["evidence_reference"]

    # A new dry run no longer offers to replace what is live now.
    again = _ok(_publish(migration_id, dry=True))
    live_row = next(row for row in again["rows"] if row["publicLessonId"] == LIVE)
    assert live_row["steps"] == [] and "a person has to decide" in live_row["skipReason"]
    assert again["replacements"] == []


def test_a_long_publish_pauses_within_the_time_limit(table, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, _ = _batch()
    migration_id = _ok(_apply(manifest))["migrationId"]
    ticks = iter([0.0, 0.0, curriculum.PUBLISH_TIME_BUDGET_SECONDS + 1] + [99.0] * 10)
    monkeypatch.setattr(curriculum, "_clock", lambda: next(ticks))

    result = _ok(_confirmed_publish(migration_id))

    assert result["status"] == "paused"
    assert result["published"] == [NEW_1]
    assert result["stoppedAt"]["code"] == "time_budget"
    assert _live(LIVE) != _live(NEW_1)


# -- rollback -------------------------------------------------------------------------


def test_a_rollback_puts_the_previous_version_back_after_a_dry_run(table, publish_events) -> None:
    first = _console_publish(LIVE)
    second = _console_publish(LIVE, answer="4/4", expected=first)
    publish_events.clear()

    plan = _ok(
        _call("rollback_lesson", {"publicLessonId": LIVE, "reason": "Wrong key.", "dryRun": True})
    )
    assert plan["liveVersionId"] == second and plan["rollbackToVersionId"] == first
    assert plan["wouldBeRefused"] is None
    assert _live(LIVE) == second

    _refused(
        _call("rollback_lesson", {"publicLessonId": LIVE, "reason": "Wrong key.", "dryRun": False}),
        "expected_version_required",
    )
    _refused(
        _call(
            "rollback_lesson",
            {
                "publicLessonId": LIVE,
                "reason": "Wrong key.",
                "expectedPublishedVersionId": first,
                "dryRun": False,
            },
        ),
        "stale_pointer",
    )
    result = _ok(
        _call(
            "rollback_lesson",
            {
                "publicLessonId": LIVE,
                "reason": "Wrong key.",
                "expectedPublishedVersionId": second,
                "dryRun": False,
            },
        )
    )

    assert result["status"] == "rolled_back"
    assert _live(LIVE) == first
    assert publish_events == [(LIVE, "publish")]
    row = _audit_rows(table)[-1]
    assert row["action"] == "rollback_lesson" and row["target_id"] == LIVE
    assert "Wrong key." in row["evidence_reference"]


def test_a_lesson_never_published_has_nothing_to_roll_back(table) -> None:
    _refused(
        _call("rollback_lesson", {"publicLessonId": NEW_1, "reason": "x", "dryRun": True}),
        "not_published",
    )
    first = _console_publish(LIVE)
    _refused(
        _call("rollback_lesson", {"publicLessonId": LIVE, "reason": "x", "dryRun": True}),
        "no_previous_version",
    )
    _refused(
        _call(
            "rollback_lesson",
            {"publicLessonId": LIVE, "versionId": first, "reason": "x", "dryRun": True},
        ),
        "already_live",
    )


def test_an_unknown_lesson_is_not_found(table) -> None:
    _refused(_call("get_lesson_state", {"publicLessonId": "no-such-lesson"}), "lesson_not_found")
