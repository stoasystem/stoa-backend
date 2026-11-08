"""The console is told which version of a lesson is live (#111).

Publishing names the live version as `expectedPublishedVersionId`, and nothing
returned it: the console took the newest `published` row of the worklist. An older
version kept `state: published` after a newer one replaced it, so after a rollback,
or for a lesson whose live version was past the worklist's hundred rows, the guess
was wrong and the publish was refused as stale.

The worklist and preview now carry the lesson's pointer as `publishedVersionId`, and
read each version's state against it: `published` is the live version only, and a
version a later publish replaced is `superseded`. Stored rows are not rewritten.

Everything runs the real workflow against the shared table double.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from fakes.dynamodb import FakeTable
from stoa.db.repositories import curriculum_ops_repo
from stoa.routers import admin
from stoa.services import curriculum_ops_service
from test_curriculum_publish_projection import (
    LESSON_ID,
    OPERATOR,
    _approved,
    _exercise,
    _payload,
    _publish,
    install_seeded_table,
)


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> FakeTable:
    return install_seeded_table(monkeypatch)


def _states(**query: Any) -> dict[str, str]:
    items = curriculum_ops_service.list_worklist(**query)["items"]
    return {item["versionId"]: item["state"] for item in items if item["publicLessonId"] == LESSON_ID}


def _pointers(**query: Any) -> set[str | None]:
    items = curriculum_ops_service.list_worklist(**query)["items"]
    return {item["publishedVersionId"] for item in items if item["publicLessonId"] == LESSON_ID}


def test_a_replaced_version_is_superseded_and_every_row_names_the_live_one(table: FakeTable) -> None:
    first = _publish(_payload(_exercise(1)))
    second = _publish(_payload(_exercise(1), _exercise(2)), expected=first)

    assert _states() == {first: "superseded", second: "published"}
    assert _pointers() == {second}

    preview = curriculum_ops_service.preview_lesson(LESSON_ID, first)
    assert preview["state"] == "superseded"
    assert preview["publishedVersionId"] == second
    assert preview["lesson"]["lesson_id"] == LESSON_ID

    # Read, not migrated: the stored row still says what it was last written as.
    assert curriculum_ops_repo.get_version(LESSON_ID, first)["state"] == "published"


def test_after_a_rollback_the_pointer_and_states_follow_the_live_version(table: FakeTable) -> None:
    first = _publish(_payload(_exercise(1)))
    second = _publish(_payload(_exercise(1), _exercise(2)), expected=first)
    curriculum_ops_service.rollback(
        LESSON_ID, first, OPERATOR, expected_published_version_id=second, reason="v2 was wrong"
    )

    # The newest published row is `second`; guessing from it was the stale publish.
    assert _states() == {first: "published", second: "superseded"}
    assert _pointers() == {first}

    third = _approved(_payload(_exercise(3)))
    pointer = curriculum_ops_service.preview_lesson(LESSON_ID, third)["publishedVersionId"]
    published = curriculum_ops_service.publish(
        LESSON_ID, third, OPERATOR, expected_published_version_id=pointer
    )

    assert published["pointer"]["publishedVersionId"] == third
    assert _states() == {first: "superseded", second: "superseded", third: "published"}


def test_the_pointer_is_right_when_the_live_version_is_past_the_cut(table: FakeTable) -> None:
    live = _publish(_payload(_exercise(1)))
    newest = _approved(_payload(_exercise(2)))
    stored = curriculum_ops_repo.get_version(LESSON_ID, newest)
    content = {key: value for key, value in stored.items() if key not in {"PK", "SK"}}
    # A hundred and more versions touched after the live one push it off the list.
    for index in range(120):
        curriculum_ops_repo.put_version(
            {
                **content,
                "version_id": f"later-{index:03d}",
                "state": "draft",
                "updated_at": f"2999-01-01T00:{index // 60:02d}:{index % 60:02d}Z",
            }
        )

    items = curriculum_ops_service.list_worklist(limit=100)["items"]
    assert len(items) == 100
    assert live not in {item["versionId"] for item in items}
    assert {item["publishedVersionId"] for item in items} == {live}

    published = curriculum_ops_service.publish(
        LESSON_ID, newest, OPERATOR, expected_published_version_id=items[0]["publishedVersionId"]
    )
    assert published["pointer"]["publishedVersionId"] == newest


def test_the_status_filter_reads_the_state_the_console_is_shown(table: FakeTable) -> None:
    first = _publish(_payload(_exercise(1)))
    second = _publish(_payload(_exercise(1), _exercise(2)), expected=first)
    draft = curriculum_ops_service.create_lesson_draft(_payload(_exercise(3)), OPERATOR)["versionId"]

    assert _states(status="published") == {second: "published"}
    assert _states(status="superseded") == {first: "superseded"}
    assert _states(status="draft") == {draft: "draft"}


def test_a_lesson_never_published_has_no_pointer_and_keeps_its_states(table: FakeTable) -> None:
    draft = curriculum_ops_service.create_lesson_draft(_payload(_exercise(1)), OPERATOR)["versionId"]
    approved = _approved(_payload(_exercise(2)))

    # A draft writes the pointer row too, with no live version on it.
    assert curriculum_ops_repo.get_pointer(LESSON_ID) is not None
    assert _states() == {draft: "draft", approved: "approved"}
    assert _pointers() == {None}
    assert curriculum_ops_service.preview_lesson(LESSON_ID, draft)["publishedVersionId"] is None


def test_a_published_row_with_no_pointer_is_left_as_stored(table: FakeTable) -> None:
    # Nothing writes one, but there is no live version to call it replaced by.
    version = _approved(_payload(_exercise(1)))
    stored = curriculum_ops_repo.get_version(LESSON_ID, version)
    curriculum_ops_repo.put_version({**stored, "state": "published"})
    table.rows.pop((f"CURRICULUM_POINTER#{LESSON_ID}", "META"), None)

    assert _states() == {version: "published"}
    assert _pointers() == {None}


def test_the_routes_return_the_pointer(table: FakeTable) -> None:
    first = _publish(_payload(_exercise(1)))
    second = _publish(_payload(_exercise(1), _exercise(2)), expected=first)
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(app, OPERATOR)
    client = TestClient(app)

    worklist = client.get("/admin/curriculum/worklist")
    preview = client.get(
        f"/admin/curriculum/lessons/{LESSON_ID}/preview", params={"versionId": first}
    )

    assert worklist.status_code == 200
    rows = {item["versionId"]: item for item in worklist.json()["items"]}
    assert rows[first]["state"] == "superseded"
    assert rows[second]["state"] == "published"
    assert {rows[first]["publishedVersionId"], rows[second]["publishedVersionId"]} == {second}
    assert preview.status_code == 200
    assert preview.json()["state"] == "superseded"
    assert preview.json()["publishedVersionId"] == second
