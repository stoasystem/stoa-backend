"""Business account numbers: role prefix, two-digit year, four-digit sequence."""

from __future__ import annotations

from datetime import UTC, datetime
import re

from stoa.db.repositories import account_number_repo


ROLE_NUMBER_PREFIXES = {
    "student": "S",
    "teacher": "T",
    "parent": "P",
    "admin": "A",
}

NUMBER_PREFIX_ROLES = {prefix: role for role, prefix in ROLE_NUMBER_PREFIXES.items()}

ACCOUNT_NUMBER_PATTERN = re.compile(r"^([STPA])(\d{2})-(\d{4})$")

MIN_SEQUENCE = 1
MAX_SEQUENCE = 9999
MAX_CLAIM_ATTEMPTS = 2000


class UnknownAccountRole(ValueError):
    """The role has no numbering prefix."""


class AccountNumberExhausted(RuntimeError):
    """Every sequence for this role and year is already assigned."""


class AccountNumberAllocationFailed(RuntimeError):
    """Contention outlasted the bounded retry budget."""


def number_prefix(role: str) -> str:
    """Prefix letter for one role."""
    prefix = ROLE_NUMBER_PREFIXES.get(role)
    if prefix is None:
        raise UnknownAccountRole(f"role without account numbering: {role}")
    return prefix


def format_account_number(*, role: str, year: int, sequence: int) -> str:
    """Render one account number without reserving it."""
    if not MIN_SEQUENCE <= sequence <= MAX_SEQUENCE:
        raise ValueError("sequence out of range")
    return f"{number_prefix(role)}{year % 100:02d}-{sequence:04d}"


def role_for_account_number(account_number: str) -> str:
    """Role encoded in one account number."""
    match = ACCOUNT_NUMBER_PATTERN.match(account_number)
    if match is None:
        raise ValueError(f"malformed account number: {account_number}")
    return NUMBER_PREFIX_ROLES[match.group(1)]


def resolve_account_id(account_number: str, *, table: object | None = None) -> str | None:
    """Which account holds this number, or None when it was never assigned.

    The claim row is the only place the pairing is recorded, so a number that
    was never issued and one whose row is gone are the same answer here.
    """
    claim = account_number_repo.get_account_number_claim(account_number, table=table)
    if claim is None:
        return None
    account_id = claim.get("account_id")
    return account_id if isinstance(account_id, str) and account_id else None


def allocate_account_number(
    *,
    role: str,
    account_id: str,
    created_at: datetime | None = None,
    table: object | None = None,
) -> str:
    """Reserve the next free number for one role and creation year.

    Uniqueness rests on the conditional claim write alone. The cursor only picks
    a starting point, so a stale or lost cursor costs retries, never a duplicate.
    """
    prefix = number_prefix(role)
    if not account_id:
        raise ValueError("account_id is required")
    moment = created_at or datetime.now(UTC)
    year = moment.year
    stamp = moment.isoformat()

    sequence = account_number_repo.read_allocation_hint(
        role=role, year=year, table=table
    ) + 1
    for _attempt in range(MAX_CLAIM_ATTEMPTS):
        if sequence > MAX_SEQUENCE:
            raise AccountNumberExhausted(f"{prefix}{year % 100:02d} sequence exhausted")
        account_number = format_account_number(role=role, year=year, sequence=sequence)
        claimed = account_number_repo.claim_account_number(
            account_number=account_number,
            role=role,
            year=year,
            sequence=sequence,
            account_id=account_id,
            created_at=stamp,
            table=table,
        )
        if claimed:
            account_number_repo.advance_allocation_hint(
                role=role, year=year, sequence=sequence, table=table
            )
            return account_number
        hint = account_number_repo.read_allocation_hint(role=role, year=year, table=table)
        sequence = max(sequence + 1, hint + 1)
    raise AccountNumberAllocationFailed("account number contention exceeded retry budget")
