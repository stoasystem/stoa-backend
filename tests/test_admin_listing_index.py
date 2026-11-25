"""`/admin/stats` and the curriculum worklist read GSI-Listing, not the table (card 133).

In production the stats took 4.6 s and the worklist 15.4 s: each read every page
of `stoa-main` to find a few thousand rows. The legacy questions, the help
requests and the lesson versions and pointers now carry `listing` and
`listed_at`, and both pages query those lists.

Each test answers the same fixture twice - through the scan the page used to
read and through the index - and requires the same body, with no scan on the
second. The backfill puts the rows written before in place.
"""

from __future__ import annotations

from itertools import islice
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from fakes.dynamodb import DEFAULT_INDEXES, FakeTable, IndexSchema
from scripts import backfill_listing_index_admin as backfill
from stoa.db import table as db_table
from stoa.db.repositories import curriculum_ops_repo, question_repo, user_repo
from stoa.routers import admin
from stoa.services import curriculum_ops_service, help_requests

ASKED = "2026-10-01T08:00:00Z"
PROFILES = [{"role": "student"}, {"role": "teacher"}]


# ── The reads as they were before card 133 ───────────────────────────────────


def _scanned_question_census(*, page_budget: int, table: object | None = None):
    target = table or db_table.table()
    rows: list[dict[str, Any]] = []
    for page in islice(
        db_table.pages(
            "scan",
            table=target,
            FilterExpression="SK = :meta",
            ExpressionAttributeValues={":meta": "META"},
        ),
        page_budget,
    ):
        rows.extend(page.items)
        if page.last_key is None:
            return rows, True
    return rows, False


def _scanned_worklist(**_ignored: Any) -> curriculum_ops_repo.WorklistRows:
    versions: list[dict[str, Any]] = []
    published: dict[str, str] = {}
    for item in db_table.rows("scan", table=db_table.table()):
        if item.get("entity_type") == curriculum_ops_repo.POINTER_ENTITY:
            if isinstance(item.get("published_version_id"), str):
                published[str(item["public_id"])] = item["published_version_id"]
        elif item.get("entity_type") == curriculum_ops_repo.VERSION_ENTITY:
            versions.append(item)
    newest = sorted(versions, key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return curriculum_ops_repo.WorklistRows(newest, published)


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _filler(table: FakeTable, rows: int = 30) -> None:
    for index in range(rows):
        table.seed({"PK": f"AAA#filler-{index:02d}", "SK": "ROW", "entity_type": "filler"})


def _stats_table() -> FakeTable:
    """Rows as the releases before card 133 left them: no `listing` on any."""
    table = FakeTable(page_item_cap=4)
    _filler(table)
    questions = [
        ("q-1", "ai_answered", {}),
        ("q-2", "resolved", {"sla_request_to_first_reply_seconds": 600,
                             "teacher_first_reply_sla_bucket": "within_target"}),
        ("q-3", "escalated", {}),
        ("q-4", "teacher_active", {"source": "conversation_escalation"}),
    ]
    for question_id, status, extra in questions:
        table.seed({
            "PK": f"QUESTION#{question_id}", "SK": "META", "entity_type": "question",
            "status": status, "created_at": ASKED, **extra,
        })
    # A META row that is not a question and has no question status.
    table.seed({"PK": "NOTIFICATION#n-1", "SK": "META", "status": "sent"})
    records = [
        ("c-1", {"escalation_status": "pending"}),
        ("c-2", {"escalation_status": "resolved", "teacher_id": "t-1",
                 "accepted_at": ASKED, "resolved_at": "2026-10-01T08:20:00Z",
                 "first_teacher_reply_at": "2026-10-01T08:05:00Z"}),
        ("c-3", {"escalation_status": "withdrawn"}),
    ]
    for conversation_id, extra in records:
        record = {
            **help_requests.key(conversation_id),
            "entity_type": help_requests.ENTITY_TYPE,
            "conversation_id": conversation_id,
            "student_id": "s-1",
            "version": 1,
            "created_at": ASKED,
            "escalated_at": ASKED,
            **extra,
        }
        table.seed({**record, **help_requests.index_fields(record)})
    return table


def _admin() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(app, {"sub": "admin-1", "role": "admin"})
    return TestClient(app)


@pytest.fixture
def profiles(monkeypatch: pytest.MonkeyPatch) -> None:
    # The profile census is card 133-B1's; held still so only these reads are compared.
    monkeypatch.setattr(user_repo, "profile_role_census", lambda **_kwargs: (PROFILES, True))


def _stats_through_the_scan(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    with monkeypatch.context() as patch:
        patch.setattr(question_repo, "question_meta_census", _scanned_question_census)
        patch.setattr(help_requests, "list_listed", help_requests.list_all)
        response = _admin().get("/admin/stats")
    assert response.status_code == 200, response.text
    return response.json()


def _backfill(table: FakeTable) -> None:
    assert backfill.run(table, apply_writes=True, verify_index=False) == 0


# ── /admin/stats ─────────────────────────────────────────────────────────────


def test_stats_answer_what_the_scan_answered_without_scanning(monkeypatch, profiles) -> None:
    table = _stats_table()
    db_table.install(table)
    before = _stats_through_the_scan(monkeypatch)
    _backfill(table)
    table.calls.clear()

    response = _admin().get("/admin/stats")

    assert response.status_code == 200, response.text
    assert table.calls["scan"] == 0
    assert table.calls["query"] > 0
    assert response.json() == before
    assert before["total_questions"] == 4
    assert before["teacher_resolved"] == 2
    assert response.json()["counts_complete"] is True


def test_stats_miss_what_is_not_yet_in_the_index(monkeypatch, profiles) -> None:
    """Negative control: before the backfill the index is empty, and the counts show it."""
    table = _stats_table()
    db_table.install(table)

    body = _admin().get("/admin/stats").json()

    assert body["total_questions"] == 0
    assert body["teacher_resolved"] == 0
    assert table.calls["scan"] == 0


def test_a_census_cut_short_says_so(profiles) -> None:
    table = _stats_table()
    _backfill(table)
    table.page_item_cap = 2

    rows, complete = question_repo.question_meta_census(page_budget=1, table=table)

    assert complete is False
    assert len(rows) < 4


def test_a_request_is_listed_by_when_it_was_asked() -> None:
    record = {"created_at": "2026-10-01T08:00:00.123456+00:00"}

    assert help_requests.listing_fields(record) == {
        "listing": help_requests.LISTING_NAME,
        "listed_at": "2026-10-01T08:00:00Z",
    }


def test_the_lists_are_ones_the_table_carries() -> None:
    schema = IndexSchema("listing", "listed_at")
    assert DEFAULT_INDEXES[question_repo.LISTING_INDEX] == schema
    assert DEFAULT_INDEXES[help_requests.LISTING_INDEX] == schema
    assert DEFAULT_INDEXES[curriculum_ops_repo.LISTING_INDEX] == schema
    assert len(set(backfill.LISTINGS)) == 4


# ── The curriculum worklist ──────────────────────────────────────────────────


def _version(public_id: str, version_id: str, state: str, minute: int) -> dict[str, Any]:
    return {
        "public_id": public_id,
        "version_id": version_id,
        "content_type": "lesson_bundle",
        "state": state,
        "lesson": {"title": public_id},
        "exercises": [],
        "created_at": f"2026-10-01T08:{59 - minute:02d}:00Z",
        "updated_at": f"2026-10-01T09:{minute:02d}:00Z",
    }


def _curriculum(table: FakeTable) -> None:
    """Three lessons through the writers: drafts, a publish, and one replaced."""
    _filler(table)
    table.page_item_cap = 4
    minute = 0
    for lesson in ("l-1", "l-2", "l-3"):
        for number, state in enumerate(("published", "published", "draft", "in_review")):
            minute += 1
            curriculum_ops_repo.put_version(_version(lesson, f"{lesson}-v{number}", state, minute))
        curriculum_ops_repo.put_pointer({
            "public_id": lesson, "draft_version_id": f"{lesson}-v2",
            "updated_at": f"2026-10-01T10:{minute:02d}:00Z",
        })
    for lesson, live in (("l-1", "l-1-v1"), ("l-2", "l-2-v0")):
        curriculum_ops_repo.set_published_pointer(
            public_id=lesson, version_id=live, manifest_id=f"m-{lesson}",
            expected_published_version_id=None, actor_id="admin-1",
            updated_at="2026-10-01T11:00:00Z",
        )


QUERIES = [
    {},
    {"limit": 2},
    {"status": "draft"},
    {"status": "published"},
    {"status": "superseded", "limit": 1},
    {"status": "in_review", "limit": 2},
    {"status": "archived"},
]


@pytest.mark.parametrize("query", QUERIES, ids=[str(query) for query in QUERIES])
def test_the_worklist_answers_what_the_scan_answered_without_scanning(
    fake_table: FakeTable, monkeypatch: pytest.MonkeyPatch, query: dict[str, Any]
) -> None:
    _curriculum(fake_table)
    with monkeypatch.context() as patch:
        patch.setattr(curriculum_ops_repo, "list_worklist", _scanned_worklist)
        before = curriculum_ops_service.list_worklist(**query)
    fake_table.calls.clear()

    after = curriculum_ops_service.list_worklist(**query)

    assert fake_table.calls["scan"] == 0
    assert after == before


def test_a_short_worklist_reads_only_the_newest_versions(fake_table: FakeTable) -> None:
    _curriculum(fake_table)

    rows = curriculum_ops_repo.list_worklist(want=2)

    assert [row["version_id"] for row in rows.versions] == ["l-3-v3", "l-3-v2"]
    assert rows.published_version_ids == {"l-1": "l-1-v1", "l-2": "l-2-v0"}


def test_every_writer_of_a_version_or_pointer_sets_its_list(fake_table: FakeTable) -> None:
    _curriculum(fake_table)

    version = fake_table.rows[("CURRICULUM_VERSION#l-1", "VERSION#l-1-v0")]
    assert (version["listing"], version["listed_at"]) == ("curriculum_version", version["updated_at"])
    published = fake_table.rows[("CURRICULUM_POINTER#l-1", "META")]
    assert (published["listing"], published["listed_at"]) == ("curriculum_pointer", "2026-10-01T11:00:00Z")
    drafted = fake_table.rows[("CURRICULUM_POINTER#l-3", "META")]
    assert drafted["listing"] == "curriculum_pointer"
    assert drafted["listed_at"].startswith("2026-10-01T10:")


# ── The backfill ─────────────────────────────────────────────────────────────


def _unlisted(table: FakeTable) -> None:
    for row in table.rows.values():
        row.pop("listing", None)
        row.pop("listed_at", None)


def test_the_backfill_dry_run_counts_and_writes_nothing(fake_table: FakeTable, capsys) -> None:
    _curriculum(fake_table)
    stats = _stats_table()
    for row in stats.rows.values():
        fake_table.seed(row)
    _unlisted(fake_table)
    before = {key: dict(row) for key, row in fake_table.rows.items()}
    fake_table.calls.clear()

    assert backfill.run(fake_table, apply_writes=False, verify_index=False) == 0

    out = capsys.readouterr().out
    assert "question_meta: 4 | help_request: 3 | curriculum_version: 12 | curriculum_pointer: 3" in out
    assert "to write: 22" in out
    assert "[DRY RUN]" in out
    assert fake_table.rows == before
    assert fake_table.calls["update_item"] == 0


def test_the_backfill_writes_each_row_once_and_verifies(fake_table: FakeTable, capsys) -> None:
    _curriculum(fake_table)
    worklist = curriculum_ops_service.list_worklist()
    _unlisted(fake_table)
    assert curriculum_ops_service.list_worklist()["items"] == []
    assert backfill.run(fake_table, apply_writes=False, verify_index=True) == 1

    assert backfill.run(fake_table, apply_writes=True, verify_index=False) == 0
    assert "written: 15" in capsys.readouterr().out
    assert backfill.run(fake_table, apply_writes=True, verify_index=False) == 0
    assert "Nothing to write." in capsys.readouterr().out

    assert backfill.run(fake_table, apply_writes=False, verify_index=True) == 0
    assert curriculum_ops_service.list_worklist() == worklist


def test_the_backfill_leaves_a_row_written_meanwhile_as_its_writer_left_it(
    fake_table: FakeTable,
) -> None:
    curriculum_ops_repo.put_version(_version("l-1", "v-1", "draft", 1))
    written = dict(fake_table.rows[("CURRICULUM_VERSION#l-1", "VERSION#v-1")])
    # As the scan read it, before the writer that sets the keys got there.
    stale = {key: value for key, value in written.items() if key not in {"listing", "listed_at"}}

    outcome = backfill.apply(fake_table, [stale])

    assert outcome == {"listed or gone meanwhile, skipped": 1}
    assert fake_table.rows[("CURRICULUM_VERSION#l-1", "VERSION#v-1")] == written


def test_a_tombstone_and_an_unrelated_meta_row_are_in_no_list() -> None:
    assert backfill.listing_fields(
        {"PK": "CONV#c-1", "SK": "HELP", "entity_type": "help_request", "conversation_id": "c-1",
         "status": "deleted", "owner_deletion_generation": 1}
    ) == {}
    assert backfill.listing_fields({"PK": "NOTIFICATION#n-1", "SK": "META", "status": "pending"}) == {}
    counts = backfill.count([{"PK": "NOTIFICATION#n-1", "SK": "META", "status": "pending"}])
    assert counts["not a question, no longer counted"] == 1
