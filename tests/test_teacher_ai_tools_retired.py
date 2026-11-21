"""#518: the teacher summary draft, assistance summary and exercise-draft routes are gone.

No client called them any more (stoa-frontend dropped the last callers before
the teacher help-request page of stoa-frontend#725). Drafts already stored are
still delivered through `POST /adaptive/assignments` (`tests/test_exercise_draft_delivery.py`).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from stoa.main import app

RETIRED = [
    ("GET", "/teachers/questions/question-1/assistance-summary"),
    ("POST", "/teachers/questions/question-1/ai-tools/summary-draft"),
    ("POST", "/teachers/ai-tools/exercise-drafts"),
    ("GET", "/teachers/ai-tools/drafts"),
    ("GET", "/teachers/ai-tools/drafts/aitool-1"),
    ("POST", "/teachers/ai-tools/drafts/aitool-1/regenerate"),
    ("POST", "/teachers/ai-tools/drafts/aitool-1/accept"),
    ("POST", "/teachers/ai-tools/drafts/aitool-1/reject"),
    ("POST", "/teachers/ai-tools/drafts/aitool-1/archive"),
]


def test_no_route_of_the_app_is_a_retired_one():
    paths = {getattr(route, "path", "") for route in app.routes}
    assert not {path for path in paths if "/ai-tools" in path or "assistance-summary" in path}


@pytest.mark.parametrize("method,path", RETIRED)
def test_a_retired_route_answers_not_found(method, path):
    saved = dict(app.dependency_overrides)
    install_actor_overrides(app, {"sub": "teacher-1", "role": "teacher"})
    try:
        response = TestClient(app).request(method, path, json={})
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)

    assert response.status_code in {404, 405}, response.text
