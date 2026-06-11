"""Locale normalization and fallback helpers for user preferences."""

from __future__ import annotations

import re
from typing import Any

SUPPORTED_LOCALES = frozenset({"de", "en"})
DEFAULT_LOCALE = "de"

_LOCALE_RE = re.compile(r"^[a-zA-Z]{2,3}(?:[-_][a-zA-Z0-9]{2,8})*$")


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
