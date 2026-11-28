"""The admin account list, at the repository that owns it (#290, card 133).

`user_repo.list_accounts` queries the profiles' partition of GSI-Listing, filters
them and hands out its own cursor; `account_invitation_repo.issued_invitation_ids`
finds the invitation an invited account can be reissued from, for a whole page at
once. The route only projects what comes back, so the paging, filtering and
invitation rules are pinned here.
"""

from __future__ import annotations

import base64
import json

import pytest
from boto3.dynamodb.conditions import ConditionExpressionBuilder

from fakes.dynamodb import FakeTable

from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, account_invitation_repo, user_repo


def _profile(
    user_id: str,
    *,
    role: str = "student",
    status: str = "active",
    name: str | None = None,
    email: str | None = None,
    account_number: str = "",
    created_at: str = "2026-01-01T00:00:00+00:00",
) -> dict[str, object]:
    row: dict[str, object] = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "user_id": user_id,
        "role": role,
        "account_status": status,
        "name": name or user_id,
        "email": email or f"{user_id}@stoa.test",
        "account_number": account_number,
        "created_at": created_at,
    }
    return {**row, **account_deletion_repo.account_listing_fields(row)}


def _noise(table: FakeTable, rows: int) -> None:
    """Rows that sort ahead of every profile in the table, the way lessons and attempts do."""
    for index in range(rows):
        table.seed({"PK": "PRACTICE", "SK": f"CHALLENGE#lesson-{index:05d}", "entity_type": "challenge"})


def _ids(page: user_repo.AccountPage) -> list[str]:
    return [str(profile["user_id"]) for profile in page.profiles]


# -- paging ------------------------------------------------------------------------


def test_pages_neither_repeat_nor_skip_a_profile_newest_first() -> None:
    table = FakeTable()
    for index in range(10):
        table.seed(_profile(f"student-{index:02d}", created_at=f"2026-01-{index + 1:02d}"))

    seen: list[str] = []
    sizes: list[int] = []
    cursor: str | None = None
    while True:
        page = user_repo.list_accounts(limit=3, cursor=cursor, table=table)
        seen.extend(_ids(page))
        sizes.append(len(page.profiles))
        cursor = page.next_cursor
        assert len(sizes) <= 10, sizes
        if not cursor:
            break

    assert seen == [f"student-{index:02d}" for index in reversed(range(10))]
    assert sizes == [3, 3, 3, 1]


def test_a_page_comes_back_without_its_table_or_index_keys() -> None:
    table = FakeTable()
    table.seed(_profile("student-1"))

    (profile,) = user_repo.list_accounts(limit=5, table=table).profiles

    assert not {"PK", "SK", "listing", "listed_at"} & set(profile)
    assert profile["user_id"] == "student-1"


def test_rows_outside_the_index_cost_nothing() -> None:
    """The scan this replaced walked every lesson and attempt to reach the profiles;
    the index holds the profiles alone, so the table's other rows are never read."""
    table = FakeTable()
    _noise(table, 500)
    for index in range(4):
        table.seed(_profile(f"student-{index}", created_at=f"2026-01-0{index + 1}"))

    page = user_repo.list_accounts(limit=50, table=table)

    assert _ids(page) == [f"student-{index}" for index in reversed(range(4))]
    assert page.next_cursor is None
    assert dict(table.calls) == {"query": 1}
    ((operation, request),) = table.requests
    assert request["IndexName"] == "GSI-Listing"
    assert request["ScanIndexForward"] is False


def test_a_profile_without_the_index_keys_is_not_listed() -> None:
    """Why the backfill exists: a profile written before card 133 is invisible here."""
    table = FakeTable()
    legacy = _profile("student-old")
    del legacy["listing"], legacy["listed_at"]
    table.seed(legacy, _profile("student-new"))

    assert _ids(user_repo.list_accounts(limit=10, table=table)) == ["student-new"]


def test_a_walk_that_runs_out_of_budget_says_there_is_more(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bounded, and a bounded walk says so: "stopped looking" is not "no more"."""
    monkeypatch.setattr(user_repo, "ACCOUNT_LIST_SCAN_PAGE_SIZE", 2)
    monkeypatch.setattr(user_repo, "ACCOUNT_LIST_SCAN_MAX_PAGES", 3)
    table = FakeTable()
    for index in range(7):
        table.seed(_profile(f"teacher-{index}", role="teacher", created_at=f"2026-02-0{index + 1}"))
    table.seed(_profile("student-late", created_at="2026-01-01"))

    stopped = user_repo.list_accounts(limit=50, role="student", table=table)

    assert stopped.profiles == []
    assert stopped.next_cursor is not None
    assert table.calls["query"] == 3

    resumed = user_repo.list_accounts(
        limit=50, role="student", cursor=stopped.next_cursor, table=table
    )

    assert _ids(resumed) == ["student-late"]
    assert resumed.next_cursor is None


@pytest.mark.parametrize(
    "cursor",
    [
        "not base64 at all!",
        base64.urlsafe_b64encode(b"\xff\xfe").decode("ascii"),
        base64.urlsafe_b64encode(json.dumps(["PK", "SK"]).encode()).decode("ascii"),
        # A cursor the table scan handed out before card 133: the base key alone.
        db_table.page_token(user_repo.ACCOUNT_LIST_SCOPE, {"PK": "USER#a", "SK": "PROFILE"}),
        # Another index partition.
        db_table.page_token(
            user_repo.ACCOUNT_LIST_SCOPE,
            {"PK": "USER#a", "SK": "PROFILE", "listing": "notification", "listed_at": "2026"},
        ),
    ],
)
def test_a_cursor_it_did_not_hand_out_is_refused(cursor: str) -> None:
    table = FakeTable()
    with pytest.raises(user_repo.InvalidAccountCursor):
        user_repo.list_accounts(limit=5, cursor=cursor, table=table)
    assert dict(table.calls) == {}


def test_a_cursor_outside_the_range_asked_for_is_refused_not_sent(mixed: FakeTable) -> None:
    """The table refuses a start key outside the key condition as a malformed request."""
    first = user_repo.list_accounts(limit=1, table=mixed)
    mixed.calls.clear()

    with pytest.raises(user_repo.InvalidAccountCursor):
        user_repo.list_accounts(
            limit=5, cursor=first.next_cursor, created_to="2026-02-15", table=mixed
        )
    assert dict(mixed.calls) == {}


# -- filters -----------------------------------------------------------------------


@pytest.fixture
def mixed() -> FakeTable:
    table = FakeTable()
    table.seed(
        _profile("parent-1", role="parent", name="Maria Keller", created_at="2026-02-01T00:00:00+00:00"),
        _profile("student-1", name="Lea Keller", account_number="S26-0001", created_at="2026-03-01T00:00:00+00:00"),
        _profile("student-2", status="invited", email="new@stoa.test", created_at="2026-04-01T00:00:00+00:00"),
        _profile("teacher-1", role="teacher", status="suspended", created_at="2026-05-01T00:00:00+00:00"),
    )
    return table


def test_role_filter(mixed: FakeTable) -> None:
    assert _ids(user_repo.list_accounts(limit=10, role="student", table=mixed)) == [
        "student-2",
        "student-1",
    ]


def test_status_filter(mixed: FakeTable) -> None:
    assert _ids(user_repo.list_accounts(limit=10, status="suspended", table=mixed)) == ["teacher-1"]


@pytest.mark.parametrize(
    ("keyword", "expected"),
    [
        ("keller", ["student-1", "parent-1"]),
        ("  KELLER ", ["student-1", "parent-1"]),
        ("s26-0001", ["student-1"]),
        ("new@stoa", ["student-2"]),
        ("teacher-1", ["teacher-1"]),
        ("   ", ["teacher-1", "student-2", "student-1", "parent-1"]),
        ("nobody", []),
    ],
)
def test_keyword_matches_name_email_account_number_and_id(
    mixed: FakeTable, keyword: str, expected: list[str]
) -> None:
    assert _ids(user_repo.list_accounts(limit=10, keyword=keyword, table=mixed)) == expected


def test_created_range_is_inclusive_on_both_ends(mixed: FakeTable) -> None:
    page = user_repo.list_accounts(
        limit=10,
        created_from="2026-03-01T00:00:00+00:00",
        created_to="2026-04-01T00:00:00+00:00",
        table=mixed,
    )
    assert _ids(page) == ["student-2", "student-1"]


@pytest.mark.parametrize(
    ("created_from", "created_to", "expected"),
    [
        ("2026-04-01T00:00:00+00:00", None, ["teacher-1", "student-2"]),
        (None, "2026-02-01T00:00:00+00:00", ["parent-1"]),
    ],
)
def test_one_ended_created_range(
    mixed: FakeTable, created_from: str | None, created_to: str | None, expected: list[str]
) -> None:
    page = user_repo.list_accounts(
        limit=10, created_from=created_from, created_to=created_to, table=mixed
    )
    assert _ids(page) == expected


def test_the_created_range_is_read_from_the_index_not_filtered_after(mixed: FakeTable) -> None:
    user_repo.list_accounts(limit=10, created_from="2026-04-01", table=mixed)

    ((_, request),) = mixed.requests
    built = ConditionExpressionBuilder().build_expression(
        request["KeyConditionExpression"], is_key_condition=True
    )
    assert sorted(built.attribute_name_placeholders.values()) == ["listed_at", "listing"]
    assert ">=" in built.condition_expression


def test_a_range_that_runs_backwards_is_empty_without_a_read(mixed: FakeTable) -> None:
    page = user_repo.list_accounts(
        limit=10, created_from="2026-05-01", created_to="2026-01-01", table=mixed
    )

    assert page == user_repo.AccountPage([], None)
    assert dict(mixed.calls) == {}


def test_filters_combine_and_the_limit_counts_matches_not_rows_read(mixed: FakeTable) -> None:
    page = user_repo.list_accounts(limit=1, role="student", keyword="keller", table=mixed)

    assert _ids(page) == ["student-1"]
    rest = user_repo.list_accounts(
        limit=1, role="student", keyword="keller", cursor=page.next_cursor, table=mixed
    )
    assert _ids(rest) == []
    assert rest.next_cursor is None


# -- the index keys ----------------------------------------------------------------


def test_a_profile_is_listed_from_the_moment_it_is_written(fake_table: FakeTable) -> None:
    table = fake_table
    user_repo.put_user(
        {"user_id": "student-9", "role": "student", "created_at": "2026-06-01T00:00:00+00:00"}
    )

    stored = table.rows[("USER#student-9", "PROFILE")]
    assert stored["listing"] == "account_profile"
    assert stored["listed_at"] == "2026-06-01T00:00:00+00:00"
    assert _ids(user_repo.list_accounts(limit=5, table=table)) == ["student-9"]


@pytest.mark.parametrize("created_at", [None, "", 7])
def test_a_profile_without_a_creation_time_is_listed_among_the_oldest(created_at: object) -> None:
    row: dict[str, object] = {"user_id": "u"}
    if created_at is not None:
        row["created_at"] = created_at

    assert account_deletion_repo.account_listing_fields(row) == {
        "listing": "account_profile",
        "listed_at": account_deletion_repo.ACCOUNT_LISTED_AT_UNKNOWN,
    }


def test_the_deletion_tombstone_keeps_no_index_key() -> None:
    """A profile is replaced by a tombstone built from an allowlist; the listing keys
    are not on it, so a closed account leaves GSI-Listing with its profile."""
    assert not set(account_deletion_repo.ACCOUNT_LISTING_FIELDS) & (
        account_deletion_repo._profile_tombstone_keeps()
    )


# -- invitation ids ----------------------------------------------------------------


def _invitation(
    digest: str,
    *,
    account_id: str,
    email: str,
    invitation_id: str,
    issued_at: str,
    status: str = account_invitation_repo.ISSUED_STATUS,
) -> dict[str, object]:
    return {
        **account_invitation_repo.invitation_key(digest),
        "entity_type": "account_invitation",
        "invitation_id": invitation_id,
        "token_digest": digest,
        "account_id": account_id,
        "email": email,
        "status": status,
        "issued_at": issued_at,
    }


def test_each_invited_account_gets_its_latest_issued_invitation() -> None:
    table = FakeTable()
    table.seed(
        _invitation("d1", account_id="acct-1", email="a@stoa.test", invitation_id="inv-old", issued_at="2026-01-01"),
        _invitation("d2", account_id="acct-1", email="a@stoa.test", invitation_id="inv-new", issued_at="2026-02-01"),
        _invitation(
            "d3", account_id="acct-1", email="a@stoa.test", invitation_id="inv-revoked",
            issued_at="2026-03-01", status=account_invitation_repo.REVOKED_STATUS,
        ),
        _invitation("d4", account_id="acct-2", email="b@stoa.test", invitation_id="inv-b", issued_at="2026-01-01"),
    )

    found = account_invitation_repo.issued_invitation_ids(
        [
            {"user_id": "acct-1", "email": "a@stoa.test"},
            {"user_id": "acct-2", "email": "b@stoa.test"},
            {"user_id": "acct-3", "email": "c@stoa.test"},
        ],
        table=table,
    )

    assert found == {"acct-1": "inv-new", "acct-2": "inv-b"}


def test_an_invitation_on_the_same_address_for_another_account_is_not_credited() -> None:
    """One person holds accounts in two roles on one address; each has its own invitation."""
    table = FakeTable()
    table.seed(
        _invitation("d1", account_id="acct-other", email="a@stoa.test", invitation_id="inv-other", issued_at="2026-01-01"),
    )

    found = account_invitation_repo.issued_invitation_ids(
        [{"user_id": "acct-1", "email": "a@stoa.test"}], table=table
    )

    assert found == {}


def test_a_page_asks_once_per_address_not_once_per_account() -> None:
    table = FakeTable()
    table.seed(
        _invitation("d1", account_id="acct-1", email="a@stoa.test", invitation_id="inv-1", issued_at="2026-01-01"),
        _invitation("d2", account_id="acct-2", email="a@stoa.test", invitation_id="inv-2", issued_at="2026-01-01"),
    )

    found = account_invitation_repo.issued_invitation_ids(
        [
            {"user_id": "acct-1", "email": "a@stoa.test"},
            {"user_id": "acct-2", "email": "a@stoa.test"},
            {"user_id": "acct-3", "email": ""},
        ],
        table=table,
    )

    assert found == {"acct-1": "inv-1", "acct-2": "inv-2"}
    assert dict(table.calls) == {"query": 1}


def test_no_invited_accounts_costs_nothing() -> None:
    table = FakeTable()

    assert account_invitation_repo.issued_invitation_ids([], table=table) == {}
    assert dict(table.calls) == {}
