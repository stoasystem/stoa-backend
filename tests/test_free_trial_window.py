from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock

import pytest

from stoa.config import Settings
from stoa.db.repositories import account_deletion_repo
from stoa.services import entitlement_service, free_trial_service


START = datetime(2026, 7, 24, 9, 15, 30, 123456, tzinfo=UTC)
EXPIRY = START + timedelta(days=14)


class _ProfileStore:
    def __init__(self, profile: dict[str, object]) -> None:
        self.profile = deepcopy(profile)
        self.lock = Lock()
        self.writes = 0

    def get(self, user_id: str) -> dict[str, object] | None:
        assert user_id == self.profile["user_id"]
        with self.lock:
            return deepcopy(self.profile)

    def require_active_fence(
        self, user_id: str, *, table: object | None = None
    ) -> dict[str, object]:
        del table
        assert user_id == self.profile["user_id"]
        return {"status": "active", "generation": 7}

    def transact(
        self,
        operations: list[dict[str, object]],
        *,
        table: object | None = None,
    ) -> None:
        del table
        update = operations[-1]["Update"]
        assert isinstance(update, dict)
        values = update["ExpressionAttributeValues"]
        assert isinstance(values, dict)
        with self.lock:
            if (
                self.profile.get("version") != values[":expected_profile_version"]
                or "first_student_activation_at" in self.profile
                or "free_trial_expires_at" in self.profile
            ):
                raise account_deletion_repo.AccountDeletionConflict(
                    "conditional profile write lost"
                )
            self.profile.update(
                {
                    "version": values[":next_profile_version"],
                    "first_student_activation_at": values[":trial_start"],
                    "free_trial_expires_at": values[":trial_expiry"],
                    "free_trial_schema_version": values[":trial_schema_version"],
                }
            )
            self.writes += 1


def _active_student(**overrides: object) -> dict[str, object]:
    profile: dict[str, object] = {
        "PK": "USER#student-1",
        "SK": "PROFILE",
        "user_id": "student-1",
        "role": "student",
        "account_status": "active",
        "subscription_tier": "free_trial",
        "email_verified_at": START.isoformat(),
        "version": 1,
    }
    profile.update(overrides)
    return profile


def _install_store(monkeypatch: pytest.MonkeyPatch, store: _ProfileStore) -> None:
    monkeypatch.setattr(free_trial_service.user_repo, "get_user", store.get)
    monkeypatch.setattr(
        free_trial_service.account_deletion_repo,
        "require_active_account_fence",
        store.require_active_fence,
    )
    monkeypatch.setattr(
        free_trial_service.account_deletion_repo,
        "transact",
        store.transact,
    )


def test_concurrent_first_activation_writes_one_immutable_trial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _ProfileStore(_active_student())
    _install_store(monkeypatch, store)

    with ThreadPoolExecutor(max_workers=2) as pool:
        states = tuple(pool.map(free_trial_service.activate_student_free_trial, ["student-1"] * 2))

    assert store.writes == 1
    assert {state.first_student_activation_at for state in states} == {START}
    assert {state.free_trial_expires_at for state in states} == {EXPIRY}
    assert {state.status for state in states} == {"active"}


def test_retries_and_unrelated_profile_changes_never_reset_trial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _ProfileStore(_active_student())
    _install_store(monkeypatch, store)
    first = free_trial_service.activate_student_free_trial("student-1")
    original_bytes = (
        store.profile["first_student_activation_at"],
        store.profile["free_trial_expires_at"],
        store.profile["free_trial_schema_version"],
    )

    store.profile.update(
        {
            "preferred_locale": "de-CH",
            "parent_binding_status": "active",
            "subscription_tier": "student",
            "version": int(store.profile["version"]) + 3,
            "email_verified_at": (START + timedelta(days=90)).isoformat(),
        }
    )
    replay = free_trial_service.activate_student_free_trial("student-1")

    assert store.writes == 1
    assert replay.first_student_activation_at == first.first_student_activation_at
    assert replay.free_trial_expires_at == first.free_trial_expires_at
    assert (
        store.profile["first_student_activation_at"],
        store.profile["free_trial_expires_at"],
        store.profile["free_trial_schema_version"],
    ) == original_bytes


def test_trial_admission_changes_at_the_exact_aware_expiry_instant() -> None:
    profile = _active_student(
        first_student_activation_at=START.isoformat(),
        free_trial_expires_at=EXPIRY.isoformat(),
        free_trial_schema_version="free-trial.v1",
    )

    before = free_trial_service.get_free_trial_state(
        profile, observed_at=EXPIRY - timedelta(microseconds=1)
    )
    at_expiry = free_trial_service.get_free_trial_state(profile, observed_at=EXPIRY)

    assert before.status == "active"
    assert free_trial_service.free_trial_allows_new_usage(before) is True
    assert at_expiry.status == "expired"
    assert free_trial_service.free_trial_allows_new_usage(at_expiry) is False
    assert at_expiry.action == "choose_paid_plan"


@pytest.mark.parametrize(
    "profile",
    [
        _active_student(email_verified_at=None),
        _active_student(first_student_activation_at="not-a-timestamp"),
        _active_student(
            first_student_activation_at=START.isoformat(),
            free_trial_expires_at=(EXPIRY + timedelta(seconds=1)).isoformat(),
            free_trial_schema_version="free-trial.v1",
        ),
        _active_student(migration_review_required=True),
    ],
)
def test_missing_or_malformed_historical_evidence_denies_without_default_now(
    monkeypatch: pytest.MonkeyPatch,
    profile: dict[str, object],
) -> None:
    store = _ProfileStore(profile)
    _install_store(monkeypatch, store)

    state = free_trial_service.get_free_trial_state(profile, observed_at=EXPIRY)

    assert state.status == "migration_review_required"
    assert state.first_student_activation_at is None
    assert state.free_trial_expires_at is None
    assert state.action == "choose_paid_plan"
    assert free_trial_service.free_trial_allows_new_usage(state) is False
    assert store.writes == 0


def test_effective_entitlement_projects_trial_without_removing_read_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _active_student(
        first_student_activation_at=START.isoformat(),
        free_trial_expires_at=EXPIRY.isoformat(),
        free_trial_schema_version="free-trial.v1",
    )
    monkeypatch.setattr(entitlement_service.user_repo, "get_user", lambda user_id: profile)
    monkeypatch.setattr(entitlement_service, "_get_payment_rollout_item", lambda: None)
    monkeypatch.setattr(
        entitlement_service.free_trial_service,
        "utc_now",
        lambda: EXPIRY,
    )

    entitlement = entitlement_service.resolve_student_entitlement(
        "student-1",
        settings=Settings(),
        student_profile=profile,
    )

    assert entitlement["effectivePlan"] == "free_trial"
    assert entitlement["freeTrial"] == {
        "status": "expired",
        "firstStudentActivationAt": START.isoformat(),
        "expiresAt": EXPIRY.isoformat(),
        "allowsNewUsage": False,
        "action": "choose_paid_plan",
    }
    assert entitlement["readAccess"] == {
        "account": True,
        "learningHistory": True,
        "parentView": True,
    }


def test_expired_admission_denial_precedes_ai_or_teacher_support_mutation() -> None:
    profile = _active_student(
        first_student_activation_at=START.isoformat(),
        free_trial_expires_at=EXPIRY.isoformat(),
        free_trial_schema_version="free-trial.v1",
    )
    state = free_trial_service.get_free_trial_state(profile, observed_at=EXPIRY)
    mutations: list[str] = []

    for mutation in ("ai", "teacher_support"):
        if free_trial_service.free_trial_allows_new_usage(state):
            mutations.append(mutation)

    assert mutations == []
    assert state.action == "choose_paid_plan"


def test_auth_confirmation_has_exact_trial_activation_key_link() -> None:
    root = Path(__file__).resolve().parents[1]
    auth_source = (root / "src/stoa/routers/auth.py").read_text(encoding="utf-8")
    entitlement_source = (
        root / "src/stoa/services/entitlement_service.py"
    ).read_text(encoding="utf-8")

    confirm_start = auth_source.index("async def confirm_email_verification(")
    confirm_end = auth_source.index('@router.post("/login-code/request"', confirm_start)
    confirmation = auth_source[confirm_start:confirm_end]

    assert "free_trial_service.activate_student_free_trial" in confirmation
    assert confirmation.count("activate_student_free_trial") == 2
    assert (
        confirmation.index("confirm_and_reconcile_public_identity")
        < confirmation.rindex("activate_student_free_trial")
    )
    assert "free_trial_service.get_free_trial_state" in entitlement_source
    assert "activate_student_free_trial" not in entitlement_source
