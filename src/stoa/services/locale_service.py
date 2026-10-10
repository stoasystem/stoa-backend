"""Locale normalization and fallback helpers for user preferences.

A request carries the language the client is rendering right now in
`Accept-Language`; the profile carries the durable preference. The request wins
when both are present, so switching language in the UI does not have to wait
for the preference write to land before content comes back translated.
"""

from __future__ import annotations

import logging
import re
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_LOCALES = frozenset({"de", "en", "fr", "it"})
DEFAULT_LOCALE = "de"

_LOCALE_RE = re.compile(r"^[a-zA-Z]{2,3}(?:[-_][a-zA-Z0-9]{2,8})*$")

_REQUEST_LOCALE: ContextVar[str | None] = ContextVar("stoa_request_locale", default=None)


def normalize_locale(value: str | None) -> str:
    """Return the supported base locale or raise ValueError."""
    raw = str(value or "").strip()
    if not raw or not _LOCALE_RE.match(raw):
        raise ValueError("Invalid locale")
    base = raw.replace("_", "-").split("-", 1)[0].lower()
    if base not in SUPPORTED_LOCALES:
        raise ValueError("Unsupported locale")
    return base


def effective_locale(profile: dict[str, Any] | None) -> str:
    """Resolve a user's effective locale from durable profile fields."""
    profile = profile or {}
    for key in ("preferred_locale", "preferredLocale", "language", "preferredLanguage"):
        value = profile.get(key)
        if not value:
            continue
        try:
            return normalize_locale(str(value))
        except ValueError:
            continue
    return DEFAULT_LOCALE


def locale_from_accept_language(header: str | None) -> str | None:
    """Return the most preferred supported locale in an Accept-Language header.

    Entries are ranked by `q` (1 when absent), ties keeping header order. An
    entry with q=0 is a refusal and never chosen; one whose q is not a number
    from 0 to 1 is skipped rather than guessed at.
    """
    if not header:
        return None
    ranked: list[tuple[float, str]] = []
    for entry in header.split(","):
        tag, *params = (part.strip() for part in entry.split(";"))
        if not tag or tag == "*":
            continue
        weight = _quality(params)
        if weight is None or weight <= 0:
            continue
        ranked.append((weight, tag))
    # sorted() is stable, so equal weights keep the order the client sent.
    for _, tag in sorted(ranked, key=lambda item: -item[0]):
        try:
            return normalize_locale(tag)
        except ValueError:
            continue
    return None


def _quality(params: list[str]) -> float | None:
    """The entry's q value, 1.0 when absent, None when it is not a usable weight."""
    for param in params:
        name, _, value = param.partition("=")
        if name.strip().lower() != "q":
            continue
        try:
            weight = float(value.strip())
        except ValueError:
            return None
        if not 0 <= weight <= 1:  # also false for NaN
            return None
        return weight
    return 1.0


def set_request_locale(locale: str | None) -> None:
    """Bind the locale this request asked for, for the duration of the request."""
    _REQUEST_LOCALE.set(locale)


def request_locale() -> str | None:
    return _REQUEST_LOCALE.get()


def resolve_locale(profile: dict[str, Any] | None) -> str:
    """The language to answer this request in: what was asked, else what was stored."""
    return request_locale() or effective_locale(profile)


def _stored_profile(user_id: str | None) -> dict[str, Any] | None:
    """One user's durable profile, or nothing when it cannot be read.

    Imported here rather than at module scope: `user_repo` opens a table on
    import in some entry points, and this module is pulled in by code that has
    no table at all.
    """
    if not user_id:
        return None
    from stoa.db.repositories import user_repo

    try:
        return user_repo.get_user(str(user_id))
    except Exception:  # noqa: BLE001 - a language is never worth a failed request
        logger.warning("locale_profile_unavailable", exc_info=True)
        return None


def reader_locale(user_id: str | None) -> str:
    """The language to answer **this request** in, for the person making it.

    What the client is rendering right now wins over the stored preference, so
    switching language in the UI does not wait for the preference write.
    """
    return resolve_locale(_stored_profile(user_id))


def stored_locale(user_id: str | None) -> str:
    """The language one person stored, ignoring whose request is running.

    For anything written **for** somebody rather than **to** the caller - a
    notification, a message left in another person's thread - the request's
    language names the wrong actor entirely (#124).
    """
    return effective_locale(_stored_profile(user_id))

