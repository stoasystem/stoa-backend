"""Locale normalization and fallback helpers for user preferences.

A request carries the language the client is rendering right now in
`Accept-Language`; the profile carries the durable preference. The request wins
when both are present, so switching language in the UI does not have to wait
for the preference write to land before content comes back translated.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from typing import Any

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
    """Return the first supported locale in an Accept-Language header."""
    if not header:
        return None
    for entry in header.split(","):
        tag = entry.split(";", 1)[0].strip()
        if not tag or tag == "*":
            continue
        try:
            return normalize_locale(tag)
        except ValueError:
            continue
    return None


def set_request_locale(locale: str | None) -> None:
    """Bind the locale this request asked for, for the duration of the request."""
    _REQUEST_LOCALE.set(locale)


def request_locale() -> str | None:
    return _REQUEST_LOCALE.get()


def resolve_locale(profile: dict[str, Any] | None) -> str:
    """The language to answer this request in: what was asked, else what was stored."""
    return request_locale() or effective_locale(profile)
