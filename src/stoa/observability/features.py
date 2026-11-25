"""The product features a request or a page belongs to (card 134).

The one source of the feature keys: the request metrics, the frontend error
metrics and the usage pages all count under these. A backend route is matched
by its template (`/conversations/{conv_id}`), never by the path that was asked
for; a frontend route by its first segment.
"""

from __future__ import annotations

from typing import NamedTuple


class Feature(NamedTuple):
    key: str
    name_zh: str
    name_en: str


FEATURES: tuple[Feature, ...] = (
    Feature("auth", "登录与账号", "Sign-in and account"),
    Feature("practice", "星图与练习", "Star map and practice"),
    Feature("ask_ai", "AI 提问", "Ask AI"),
    Feature("teacher_help", "老师兜底", "Teacher help"),
    Feature("voice", "语音提问", "Voice questions"),
    Feature("notifications", "通知", "Notifications"),
    Feature("parent_reports", "家长报告", "Parent reports"),
    Feature("admin", "管理后台", "Admin console"),
    Feature("other", "其他", "Other"),
)
FEATURE_KEYS = frozenset(feature.key for feature in FEATURES)
OTHER = "other"

# Routes that belong to no feature on purpose.
OTHER_ROUTES = frozenset(
    {
        ("GET", "/health"),
        ("POST", "/analytics/events"),
        ("POST", "/monitoring/frontend-errors"),
        ("POST", "/billing/webhooks/stripe"),
    }
)


class _Rule(NamedTuple):
    method: str | None
    prefix: str
    feature: str
    exact: bool = False


# First match wins, so a narrower prefix comes before the one it falls under.
_ROUTE_RULES: tuple[_Rule, ...] = (
    _Rule(None, "/students/me/voice-questions", "voice"),
    _Rule(None, "/parents/me/children/{child_id}/voice-questions", "voice"),
    _Rule(None, "/auth", "auth"),
    _Rule(None, "/teacher-applications/activation", "auth"),
    _Rule("POST", "/teacher-applications", "auth", exact=True),
    _Rule(None, "/teacher-applications", "admin"),
    _Rule(None, "/students/me/profile", "auth"),
    _Rule(None, "/students/me/parent-requests", "auth"),
    _Rule(None, "/parents/me/children/requests", "auth"),
    _Rule(None, "/teacher-help", "teacher_help"),
    _Rule(None, "/teachers", "teacher_help"),
    _Rule(None, "/conversations/{conv_id}/classroom", "teacher_help"),
    _Rule(None, "/conversations", "ask_ai"),
    _Rule(None, "/files", "ask_ai"),
    _Rule(None, "/upload-codes", "ask_ai"),
    _Rule(None, "/questions", "ask_ai"),
    _Rule(None, "/adaptive/parents", "parent_reports"),
    _Rule(None, "/practice", "practice"),
    _Rule(None, "/adaptive", "practice"),
    _Rule(None, "/students", "practice"),
    _Rule(None, "/parents", "parent_reports"),
    _Rule(None, "/notifications", "notifications"),
    _Rule(None, "/admin", "admin"),
)


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def feature_for_route(method: str, route_template: str) -> str:
    """The feature of one backend route, by its method and template."""
    method = (method or "").upper()
    if (method, route_template) in OTHER_ROUTES:
        return OTHER
    for rule in _ROUTE_RULES:
        if rule.method is not None and rule.method != method:
            continue
        if rule.exact:
            if route_template == rule.prefix:
                return rule.feature
        elif _under(route_template, rule.prefix):
            return rule.feature
    return OTHER


# The web client's routes, by their leading segments. "/" is the star map.
FRONTEND_ROUTE_FEATURES: tuple[tuple[str, str], ...] = (
    ("/login", "auth"),
    ("/register", "auth"),
    ("/activate", "auth"),
    ("/teacher-activate", "auth"),
    ("/forgot-password", "auth"),
    ("/reset-password", "auth"),
    ("/onboarding", "auth"),
    ("/me", "auth"),
    ("/ask", "ask_ai"),
    ("/classroom", "teacher_help"),
    ("/teacher", "teacher_help"),
    ("/map", "practice"),
    ("/chapter", "practice"),
    ("/review", "practice"),
    ("/star-quiz", "practice"),
    ("/assignments", "practice"),
    ("/students", "practice"),
    ("/parent", "parent_reports"),
    ("/admin", "admin"),
    ("/organization", "admin"),
    ("/unsubscribe", "notifications"),
)

_MAX_SEGMENT = 32


def frontend_route_template(path: str) -> str:
    """A browser path with every id-like segment replaced by `:id`.

    The client sends `window.location.pathname`, which carries conversation,
    child and request ids; only the shape is kept.
    """
    path = (path or "").split("?", 1)[0].split("#", 1)[0]
    segments = []
    for segment in path.split("/"):
        if not segment:
            continue
        if (
            len(segment) > _MAX_SEGMENT
            or any(char.isdigit() for char in segment)
            or not all(char.isalpha() or char in "-_:" for char in segment)
        ):
            segments.append(":id")
        else:
            segments.append(segment.lower())
    return "/" + "/".join(segments[:6])


def feature_for_frontend_route(route: str) -> str:
    """The feature of one web client route, a path or a template."""
    template = frontend_route_template(route)
    if template == "/":
        return "practice"
    for prefix, feature in FRONTEND_ROUTE_FEATURES:
        if _under(template, prefix):
            return feature
    return OTHER
