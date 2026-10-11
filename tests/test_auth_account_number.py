"""An account can read its own number (#124 follow-up).

A parent whose child is not linked yet has to be found by whoever links them,
and the number existed only on administrator routes: the person it belongs to
could not read it off their own screen. The projection is the same one the
administrator sees, so the two cannot drift.
"""

from stoa.routers import auth


def test_the_projection_carries_the_account_number_it_was_given() -> None:
    out = auth._build_user_out(
        {
            "user_id": "u-1",
            "email": "parent@example.ch",
            "name": "A Parent",
            "role": "parent",
            "account_number": "P-2026-000042",
        }
    )

    assert out.accountNumber == "P-2026-000042"


def test_an_account_opened_before_numbers_reads_back_empty_not_missing() -> None:
    """The negative control: an absent number is "", never None and never the id."""
    out = auth._build_user_out(
        {"user_id": "u-2", "email": "old@example.ch", "name": "Old", "role": "student"}
    )

    assert out.accountNumber == ""
    assert out.accountNumber != out.id
