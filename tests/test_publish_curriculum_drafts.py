"""Many drafts reach students in one run, each through the ordinary workflow calls.

`scripts/publish_curriculum_drafts.py` is a client of the admin API. Here it talks
to the real admin router over a test client, with the real workflow behind it and
one seeded table double, so every step passes the same capability checks and the
same validation as a call by hand.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from actor_helpers import install_actor_overrides
from scripts import publish_curriculum_drafts as bulk
from stoa.db.repositories import curriculum_ops_repo, practice_repo
from stoa.routers import admin
from stoa.services import curriculum_ops_service
from test_curriculum_publish_projection import install_seeded_table


EVERY_CAPABILITY = (
    curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY,
    curriculum_ops_service.AUTHOR_CAPABILITY,
    curriculum_ops_service.REVIEWER_CAPABILITY,
    curriculum_ops_service.PUBLISHER_CAPABILITY,
)


def _operator(*capabilities: str) -> dict[str, Any]:
    return {
        "sub": "operator-1",
        "role": "admin",
        "capabilities": {capability: "granted" for capability in capabilities},
    }


OPERATOR = _operator(*EVERY_CAPABILITY)


class ClientApi:
    """The script's view of the API, over a test client of the admin router."""

    def __init__(self, user: dict[str, Any], *, fail: str | None = None) -> None:
        app = FastAPI()
        app.include_router(admin.router, prefix="/admin")
        install_actor_overrides(app, user)
        self.client = TestClient(app)
        self._fail = fail

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        if self._fail and path.endswith(self._fail):
            return 503, {"detail": "service_unavailable"}
        response = self.client.request(method, path, params=params, json=body)
        return response.status_code, response.json() if response.content else None


@pytest.fixture(autouse=True)
def table(monkeypatch: pytest.MonkeyPatch) -> Any:
    return install_seeded_table(monkeypatch)


def _lesson(public_id: str, *, prompt: str = "Berechne 1/4 + 3/4.", **exercise: Any) -> dict[str, Any]:
    return {
        "publicLessonId": public_id,
        "title": "Brüche addieren",
        "objective": "Gleichnamige Brüche addieren.",
        "subjectId": "math",
        "topicId": "brueche",
        "unitId": "brueche-u2",
        "gradeLevel": "grade_6_primary",
        "language": "de",
        "difficulty": "practice",
        "exercises": [
            {
                "exerciseId": f"{public_id}-q01",
                "type": "text_input",
                "prompt": prompt,
                "answerKey": "1",
                "explanation": "1/4 + 3/4 = 4/4 = 1.",
                "difficulty": "practice",
                "skills": ["brueche-addieren"],
                **exercise,
            }
        ],
    }


def _manifest(*lessons: dict[str, Any]) -> dict[str, Any]:
    return {"source": {"sourceId": "kb", "sourceVersion": "test"}, "lessons": list(lessons)}


def _import(*lessons: dict[str, Any]) -> str:
    """Dry run and apply one manifest over the API; every lesson becomes a draft."""
    api = ClientApi(OPERATOR)
    manifest = _manifest(*lessons)
    status, preview = api.request("POST", "/admin/curriculum/migrations/dry-run", body=manifest)
    assert status == 200 and preview["publishReady"], preview
    status, applied = api.request(
        "POST",
        f"/admin/curriculum/migrations/{preview['migrationId']}/apply",
        body={"manifest": manifest, "confirmationToken": preview["confirmationToken"]},
    )
    assert status == 200, applied
    return preview["migrationId"]


def _rows(migration_id: str, api: ClientApi | None = None) -> list[bulk.PlanRow]:
    api = api or ClientApi(OPERATOR)
    return bulk.plan(api, bulk.select(api, [migration_id]))


def _run(migration_id: str, confirm: str | None, api: ClientApi | None = None, **kwargs: Any) -> int:
    return bulk.run(
        api or ClientApi(OPERATOR),
        [migration_id],
        only=kwargs.get("only"),
        exclude=kwargs.get("exclude", set()),
        confirm=confirm,
        report=kwargs.get("report"),
        out=kwargs.get("out", io.StringIO()),
    )


def _state(public_id: str, version_id: str) -> str:
    version = curriculum_ops_repo.get_version(public_id, version_id)
    assert version is not None
    return str(version["state"])


def test_the_dry_run_lists_what_would_move_and_why_the_rest_stays_and_moves_nothing(
    tmp_path: Path,
) -> None:
    migration = _import(
        _lesson("kb-ready"),
        _lesson("kb-unexplained", explanation=""),
        _lesson("kb-returned"),
    )
    returned = next(row for row in _rows(migration) if row.candidate.public_id == "kb-returned")
    version_id = returned.candidate.version_id
    curriculum_ops_service.submit_review("kb-returned", version_id, OPERATOR)
    curriculum_ops_service.request_changes("kb-returned", version_id, OPERATOR, "Prompt unklar")

    out = io.StringIO()
    assert _run(migration, None, out=out, report=tmp_path / "plan.json") == 0

    lines = out.getvalue().splitlines()
    assert lines[0] == "kb-ready (draft): submit-review -> approve -> publish"
    assert lines[1].startswith("kb-unexplained (draft): skip: validation issues: ")
    assert "exercises[0].explanation" in lines[1]
    assert lines[2] == "kb-returned (changes_requested): skip: a reviewer asked for changes"
    assert lines[3].startswith("1 to publish, 2 skipped; confirmation confirm_")
    assert practice_repo.get_challenge("kb-ready-q01") is None
    assert "kb-ready" in (tmp_path / "plan.json").read_text(encoding="utf-8")


def test_apply_moves_nothing_without_the_code_of_the_dry_run() -> None:
    migration = _import(_lesson("kb-ready"))

    assert _run(migration, "confirm_0000000000000000") == 2

    [row] = _rows(migration)
    assert row.state == "draft"
    assert practice_repo.get_challenge("kb-ready-q01") is None


def test_apply_publishes_every_ready_draft_and_a_second_run_finds_nothing_to_move() -> None:
    migration = _import(_lesson("kb-one"), _lesson("kb-two"), _lesson("kb-unexplained", explanation=""))
    code = bulk.confirmation_code(_rows(migration))

    out = io.StringIO()
    assert _run(migration, code, out=out) == 0

    assert out.getvalue().splitlines() == [
        "[1/2] kb-one published",
        "[2/2] kb-two published",
        "2 published, 1 skipped",
    ]
    assert practice_repo.get_challenge("kb-one-q01") is not None
    assert practice_repo.get_challenge("kb-two-q01") is not None
    assert practice_repo.get_challenge("kb-unexplained-q01") is None
    again = _rows(migration)
    assert [(row.state, row.skip_reason) for row in again] == [
        ("published", "already published"),
        ("published", "already published"),
        ("draft", "validation issues: exercises[0].explanation"),
    ]
    assert not any(row.moves for row in again)


def test_only_and_exclude_narrow_the_drafts_of_a_migration() -> None:
    migration = _import(_lesson("kb-one"), _lesson("kb-two"), _lesson("kb-three"))
    api = ClientApi(OPERATOR)

    only = bulk.select(api, [migration], only={"kb-one", "kb-three"}, exclude={"kb-three"})

    assert [candidate.public_id for candidate in only] == ["kb-one"]


def test_a_directory_of_manifests_names_their_migrations(tmp_path: Path) -> None:
    first = _import(_lesson("kb-one"))
    second = _import(_lesson("kb-two"))
    for name, lesson in (("manifest-001.json", "kb-one"), ("manifest-002.json", "kb-two")):
        (tmp_path / name).write_text(json.dumps(_manifest(_lesson(lesson))), encoding="utf-8")
    (tmp_path / "report.json").write_text("{}", encoding="utf-8")

    assert bulk.migration_ids_of_manifests(ClientApi(OPERATOR), [tmp_path]) == [first, second]


def test_a_run_that_stops_says_where_and_the_next_dry_run_goes_on_from_there(
    capsys: pytest.CaptureFixture[str],
) -> None:
    migration = _import(_lesson("kb-one"), _lesson("kb-two"))
    rows = _rows(migration)
    flaky = ClientApi(OPERATOR, fail=f"/kb-two/drafts/{rows[1].candidate.version_id}/approve")

    assert _run(migration, bulk.confirmation_code(rows), api=flaky) == 1

    error = capsys.readouterr().err
    assert "stopped at kb-two (approve)" in error and "503" in error
    assert "1 of 2 published" in error
    resumed = _rows(migration)
    assert [(row.state, row.steps) for row in resumed] == [
        ("published", ()),
        ("in_review", ("approve", "publish")),
    ]

    assert _run(migration, bulk.confirmation_code(resumed)) == 0
    assert practice_repo.get_challenge("kb-two-q01") is not None


def test_each_step_keeps_its_own_capability() -> None:
    migration = _import(_lesson("kb-one"))
    rows = _rows(migration)
    without_author = ClientApi(
        _operator(
            curriculum_ops_service.MIGRATION_OPERATOR_CAPABILITY,
            curriculum_ops_service.REVIEWER_CAPABILITY,
            curriculum_ops_service.PUBLISHER_CAPABILITY,
        )
    )

    with pytest.raises(bulk.Refused) as refused:
        bulk.apply(without_author, rows, out=io.StringIO())

    assert refused.value.status == 403
    assert rows[0].done == []
    assert _state("kb-one", rows[0].candidate.version_id) == "draft"


def test_a_replacement_is_published_against_the_version_live_when_it_was_imported() -> None:
    first = _import(_lesson("kb-one"))
    assert _run(first, bulk.confirmation_code(_rows(first))) == 0
    [live] = _rows(first)
    second = _import(_lesson("kb-one", prompt="Berechne 2/4 + 2/4."))
    [replacement] = _rows(second)
    assert replacement.candidate.expected_published_version_id == live.candidate.version_id

    assert _run(second, bulk.confirmation_code([replacement])) == 0

    pointer = curriculum_ops_repo.get_pointer("kb-one") or {}
    assert pointer["published_version_id"] == replacement.candidate.version_id
    challenge = practice_repo.get_challenge("kb-one-q01")
    assert challenge is not None and challenge["prompt"] == "Berechne 2/4 + 2/4."


def test_a_replacement_is_refused_when_another_version_went_live_since_the_import(
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = _import(_lesson("kb-one"))
    assert _run(first, bulk.confirmation_code(_rows(first))) == 0
    [live] = _rows(first)
    second = _import(_lesson("kb-one", prompt="Berechne 2/4 + 2/4."))
    by_hand = curriculum_ops_service.create_lesson_draft(
        _lesson("kb-one", prompt="Berechne 3/4 + 1/4."), OPERATOR
    )["versionId"]
    curriculum_ops_service.submit_review("kb-one", by_hand, OPERATOR)
    curriculum_ops_service.approve("kb-one", by_hand, OPERATOR)
    curriculum_ops_service.publish(
        "kb-one", by_hand, OPERATOR, expected_published_version_id=live.candidate.version_id
    )

    assert _run(second, bulk.confirmation_code(_rows(second))) == 1

    assert "stale_pointer" in capsys.readouterr().err
    assert (curriculum_ops_repo.get_pointer("kb-one") or {})["published_version_id"] == by_hand
    challenge = practice_repo.get_challenge("kb-one-q01")
    assert challenge is not None and challenge["prompt"] == "Berechne 3/4 + 1/4."
