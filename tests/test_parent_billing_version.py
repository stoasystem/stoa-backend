"""The allowance version arrives as a Decimal.

Every number DynamoDB hands back is a Decimal, so a check written as an exact
int comparison rejects a perfectly good version and the parent's billing page
reports itself unavailable. This is the third time this codebase has paid for
that, so it is pinned here.
"""

from decimal import Decimal

import pytest

from stoa.routers.parents import _required_positive_int


def test_a_version_stored_in_dynamodb_is_accepted():
    assert _required_positive_int(Decimal("1"), "allowance version") == 1
    assert _required_positive_int(Decimal("42"), "allowance version") == 42


def test_a_plain_integer_is_still_accepted():
    assert _required_positive_int(7, "allowance version") == 7


@pytest.mark.parametrize(
    "value",
    [
        Decimal("0"),
        Decimal("-1"),
        0,
        -3,
        Decimal("1.5"),
        Decimal("NaN"),
        "1",
        None,
        True,
    ],
)
def test_anything_that_is_not_a_whole_positive_number_is_refused(value):
    with pytest.raises(ValueError):
        _required_positive_int(value, "allowance version")
