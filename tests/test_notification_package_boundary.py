"""Notifications are one package with two doors, and the realtime connections know nothing of it (#686).

- Nothing in `src/stoa` outside `services/notifications/` imports the
  notification store (`notification_repo`) or a module of the package other
  than the package itself: callers tell `notifications.happened` what happened
  and read through the reader door.
- `websocket_service` only keeps connections. It imports nothing of the
  notification package or its store, so the old cycle (the connection module
  lazily calling back into the notification service to deliver) cannot return.
- Every kind of happening the package exports is one the entry knows.
"""

from __future__ import annotations

import ast
from pathlib import Path

from stoa.services import notifications
from stoa.services.notifications import _tell

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "stoa"
PACKAGE = SRC / "services" / "notifications"
STORE = "stoa.db.repositories.notification_repo"
PACKAGE_NAME = "stoa.services.notifications"


def _imported(tree: ast.AST) -> set[str]:
    """Every module a file imports, by its full dotted name (`from a import b` gives `a.b` too)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _outside_the_package() -> dict[str, set[str]]:
    return {
        path.relative_to(ROOT).as_posix(): _imported(ast.parse(path.read_text(encoding="utf-8")))
        for path in SRC.rglob("*.py")
        if PACKAGE not in path.parents
    }


def test_nothing_outside_the_package_imports_the_notification_store() -> None:
    offenders = sorted(
        relative
        for relative, names in _outside_the_package().items()
        if relative != "src/stoa/db/repositories/notification_repo.py"
        and any(name == STORE or name.startswith(f"{STORE}.") for name in names)
    )
    assert offenders == []


def test_nothing_outside_the_package_imports_its_inner_modules() -> None:
    offenders = sorted(
        f"{relative}: {name}"
        for relative, names in _outside_the_package().items()
        for name in names
        if name.startswith(f"{PACKAGE_NAME}.")
    )
    assert offenders == []


def test_the_old_notification_service_is_gone() -> None:
    assert not (SRC / "services" / "notification_service.py").exists()
    for relative, names in _outside_the_package().items():
        assert "stoa.services.notification_service" not in names, relative


def test_the_connection_module_imports_nothing_of_notifications() -> None:
    names = _imported(
        ast.parse((SRC / "services" / "websocket_service.py").read_text(encoding="utf-8"))
    )
    assert not any(
        name == PACKAGE_NAME
        or name.startswith(f"{PACKAGE_NAME}.")
        or name == STORE
        or name == "stoa.services.notification_service"
        for name in names
    ), sorted(names)


def test_every_exported_happening_has_a_handler() -> None:
    exported = set(notifications.Happening.__args__)
    assert exported == set(_tell._HANDLERS)
    assert all(getattr(notifications, kind.__name__) is kind for kind in exported)
