"""An upload's usable window and the table's TTL are two fields (#250).

The table deletes a row once its `expires_at` has passed. Upload rows used to
put their 30-minute usable window there, so the table removed them under the
cleanup, which then never knew what to delete from the bucket. Now the window is
`usable_until`, and `expires_at` is set only when the row has ended. A row
written before this keeps its window in `expires_at` and is read that way.

The sweep, scheduled with a fixed input, used to look at the first page of the
table only; it now pages through until it has a batch or the table ends.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from stoa.config import UPLOAD_INTENT_TTL_SECONDS, UPLOAD_ROW_RETENTION_SECONDS, Settings
from stoa.jobs import upload_cleanup
from stoa.services import uploads
from stoa.services.uploads import _store as upload_store
from fakes.dynamodb import FakeTable
from fakes.s3 import MultipartS3

from test_direct_part_upload import _Api, _intent, _png_near_the_limit, _sign
from test_direct_part_upload import table as table  # noqa: F401 - the fixture

BUCKET = "images-bucket-canary"


def _row(table: FakeTable, upload_id: str) -> dict[str, Any]:
    return table.rows[(f"UPLOAD#{upload_id}", "META")]


# ── Issuance ──────────────────────────────────────────────────────────────────


def test_an_issued_upload_has_a_usable_window_and_no_ttl(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table, MultipartS3(BUCKET))
    before = int(datetime.now(UTC).timestamp())

    intent = _intent(api, _png_near_the_limit())

    row = _row(table, intent["uploadId"])
    assert "expires_at" not in row
    assert before + UPLOAD_INTENT_TTL_SECONDS <= int(row["usable_until"]) <= before + UPLOAD_INTENT_TTL_SECONDS + 5


def test_a_part_row_outlives_its_upload_window_by_the_retention(monkeypatch, table) -> None:
    api = _Api(monkeypatch, table, MultipartS3(BUCKET))
    data = _png_near_the_limit()
    intent = _intent(api, data)
    part = data[: intent["chunkBytes"]]

    assert _sign(api, intent["uploadId"], 1, part).status_code == 200

    usable = int(_row(table, intent["uploadId"])["usable_until"])
    part_row = table.rows[(f"UPLOAD#{intent['uploadId']}", "PART#000001")]
    assert int(part_row["expires_at"]) == usable + UPLOAD_ROW_RETENTION_SECONDS


@pytest.mark.parametrize("field", ["usable_until", "expires_at"])
def test_an_upload_past_its_window_signs_no_more_parts(monkeypatch, table, field: str) -> None:
    """A row from before #250 carries its window in `expires_at`; it is read the same way."""
    api = _Api(monkeypatch, table, MultipartS3(BUCKET))
    data = _png_near_the_limit()
    intent = _intent(api, data)
    row = _row(table, intent["uploadId"])
    past = int(datetime.now(UTC).timestamp()) - 1
    if field == "expires_at":
        del row["usable_until"]
    row[field] = past

    signed = _sign(api, intent["uploadId"], 1, data[: intent["chunkBytes"]])

    assert signed.status_code >= 400


def test_usable_until_falls_back_to_the_ttl_field_of_an_old_row() -> None:
    assert upload_store.usable_until({"usable_until": 10, "expires_at": 99}) == 10
    assert upload_store.usable_until({"expires_at": 99}) == 99


# ── The sweep pages through the whole table ───────────────────────────────────


class _Pages:
    """A repository whose cleanup candidates are spread over pages, as a scan returns them."""

    def __init__(self, pages: list[list[dict[str, Any]]]) -> None:
        self.pages = pages
        self.reads: list[Any] = []

    def list_upload_cleanup_candidates(self, now_epoch, *, limit, exclusive_start_key=None):
        index = 0 if exclusive_start_key is None else int(exclusive_start_key["SK"])
        self.reads.append(exclusive_start_key)
        cursor = {"PK": "page", "SK": str(index + 1)} if index + 1 < len(self.pages) else None
        return self.pages[index], cursor


def _candidate(n: int) -> dict[str, Any]:
    return {"PK": f"UPLOAD#u{n}", "SK": "META", "upload_id": f"u{n}"}


@pytest.fixture
def cleaned(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def cleanup(candidate, **_kwargs: Any) -> str:
        seen.append(candidate["upload_id"])
        return "deleted"

    monkeypatch.setattr(uploads, "cleanup", cleanup)
    return seen


def _sweep(
    monkeypatch: pytest.MonkeyPatch, repository: _Pages, **kwargs: Any
) -> upload_cleanup.CleanupSummary:
    monkeypatch.setattr(
        upload_store, "list_upload_cleanup_candidates", repository.list_upload_cleanup_candidates
    )
    return upload_cleanup.cleanup_expired_uploads(
        s3=MultipartS3(BUCKET),
        settings_obj=Settings(s3_images_bucket=BUCKET),
        **kwargs,
    )


def test_candidates_past_the_first_page_are_cleaned(monkeypatch, cleaned) -> None:
    # Most of the table is not uploads: the first pages match nothing.
    repository = _Pages([[], [], [_candidate(1)], [], [_candidate(2)]])

    summary = _sweep(monkeypatch, repository)

    assert cleaned == ["u1", "u2"]
    assert summary.deleted == 2
    assert summary.continuation_token is None
    assert len(repository.reads) == 5


def test_one_run_cleans_at_most_one_batch(monkeypatch, cleaned) -> None:
    repository = _Pages([[_candidate(n) for n in range(30)], [_candidate(99)]])

    summary = _sweep(monkeypatch, repository)

    assert len(cleaned) == upload_cleanup.DEFAULT_BATCH_LIMIT == 25
    assert summary.continuation_token is not None
    # The batch was full after one page: the rest of the table waits for the next run.
    assert len(repository.reads) == 1


def test_a_run_short_of_time_stops_before_the_lambda_does(monkeypatch, cleaned) -> None:
    repository = _Pages([[_candidate(1)], [_candidate(2)], [_candidate(3)]])
    calls = 0

    def remaining() -> float:
        nonlocal calls
        calls += 1
        return 60.0 if calls == 1 else 5.0

    _sweep(monkeypatch, repository, remaining_seconds=remaining)

    # Stopped scanning after the second page, and cleaned nothing it had no time for.
    assert len(repository.reads) == 2
    assert cleaned == []


def test_the_page_budget_bounds_one_run(monkeypatch, cleaned) -> None:
    repository = _Pages([[] for _ in range(10)])

    summary = _sweep(monkeypatch, repository, max_pages=3)

    assert len(repository.reads) == 3
    assert cleaned == []
    assert summary.continuation_token is not None


def test_the_scheduled_event_runs_the_sweep(monkeypatch: pytest.MonkeyPatch, cleaned) -> None:
    repository = _Pages([[_candidate(1)]])
    monkeypatch.setattr(
        upload_store, "list_upload_cleanup_candidates", repository.list_upload_cleanup_candidates
    )
    monkeypatch.setattr(upload_cleanup.boto3, "client", lambda *_a, **_k: MultipartS3(BUCKET))

    class Context:
        def get_remaining_time_in_millis(self) -> int:
            return 60_000

    result = upload_cleanup.handler({"source": "stoa.scheduler", "job": "upload_cleanup"}, Context())

    assert result["deleted"] == 1
    assert cleaned == ["u1"]


def test_each_run_logs_its_counts_without_the_cursor(
    monkeypatch: pytest.MonkeyPatch, cleaned, caplog: pytest.LogCaptureFixture
) -> None:
    # The schedule invokes asynchronously, so the returned summary is seen by no one;
    # the log line is the only place a run's counts show up (#256).
    repository = _Pages([[_candidate(1), _candidate(2)], [_candidate(3)]])
    monkeypatch.setattr(
        upload_store, "list_upload_cleanup_candidates", repository.list_upload_cleanup_candidates
    )
    monkeypatch.setattr(upload_cleanup.boto3, "client", lambda *_a, **_k: MultipartS3(BUCKET))

    with caplog.at_level("INFO", logger=upload_cleanup.__name__):
        result = upload_cleanup.handler(
            {"source": "stoa.scheduler", "job": "upload_cleanup", "batchLimit": 1}, None
        )

    [line] = [r.getMessage() for r in caplog.records if r.name == upload_cleanup.__name__]
    assert line.startswith("upload_cleanup_run_completed ")
    assert "scanned=1 " in line and "deleted=1 " in line and "retryable=0 " in line
    assert line.endswith("more_to_do=true")
    assert result["continuation_token"] not in line


def test_the_sweep_handler_ships_in_the_lambda_package() -> None:
    import build_lambda_dist

    assert (
        build_lambda_dist.EXPECTED_HANDLERS["stoa.jobs.upload_cleanup.handler"]
        == "stoa/jobs/upload_cleanup.py"
    )


# ── An ended upload starts its TTL ────────────────────────────────────────────


def _cleanup_pending(table: FakeTable, **fields: Any) -> None:
    table.seed(
        {
            "PK": "UPLOAD#u-ended",
            "SK": "META",
            "upload_id": "u-ended",
            "status": "cleanup_pending",
            "version": 3,
            "usable_until": 1,
            **fields,
        }
    )


def _expires_in_a_week(row: dict[str, Any]) -> bool:
    now = datetime.now(UTC).timestamp()
    return abs(int(row["expires_at"]) - (now + UPLOAD_ROW_RETENTION_SECONDS)) < 120


def test_a_protected_upload_starts_its_ttl() -> None:
    table = FakeTable()
    _cleanup_pending(table)

    assert upload_store.block_upload_cleanup("u-ended", 3, table=table)

    row = _row(table, "u-ended")
    assert row["status"] == "cleanup_blocked"
    assert _expires_in_a_week(row)


def test_a_cleaned_upload_starts_its_ttl() -> None:
    table = FakeTable()
    _cleanup_pending(
        table,
        cleanup_multipart_aborted=True,
        cleanup_staging_deleted=True,
        cleanup_immutable_deleted=True,
        cleanup_parts_absent=True,
    )

    assert upload_store.complete_upload_cleanup(
        "u-ended", 3, datetime.now(UTC).isoformat(), table=table
    )

    row = _row(table, "u-ended")
    assert row["status"] == "cleanup_complete"
    assert _expires_in_a_week(row)


def test_the_account_deletion_function_runs_the_sweep_by_name(
    monkeypatch: pytest.MonkeyPatch, cleaned
) -> None:
    """stoa-infra schedules the sweep on the account-deletion function (#256)."""
    from stoa.jobs import account_deletion

    repository = _Pages([[_candidate(1)]])
    monkeypatch.setattr(
        upload_store, "list_upload_cleanup_candidates", repository.list_upload_cleanup_candidates
    )
    monkeypatch.setattr(upload_cleanup.boto3, "client", lambda *_a, **_k: MultipartS3(BUCKET))
    monkeypatch.setattr(
        account_deletion,
        "run_pending_deletions",
        lambda **_k: pytest.fail("the sweep is not an account deletion"),
    )

    result = account_deletion.handler({"source": "stoa.scheduler", "job": "upload_cleanup"}, None)

    assert result["deleted"] == 1
    assert cleaned == ["u1"]
