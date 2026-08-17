"""Wave 0 teacher lifecycle cases; state-machine behavior is implemented in Plan 04."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
import pytest

from stoa.services import teacher_application_service, teacher_identity_provider


def _reviewer():
    return {
        "user_id": "reviewer-1",
        "role": "admin",
        "account_status": "active",
        "current_grants": [
            {
                "capability": "teacher_identity_reviewer",
                "scope": "global",
                "status": "active",
                "version": 1,
            }
        ],
    }


def _install_teacher_repositories(monkeypatch):
    applications = {}
    reviews = {}
    invitations = {}
    commands = {}
    profiles = {}
    bindings = {}
    audits = []
    repo = teacher_application_service.teacher_application_repo

    monkeypatch.setattr(
        repo,
        "list_application_versions",
        lambda application_id: [
            dict(item)
            for (item_application_id, _), item in applications.items()
            if item_application_id == application_id
        ],
    )

    def create_application(item):
        key = (item["application_id"], item["version"])
        if key in applications:
            raise repo.TeacherApplicationConflict("exists")
        # The real repository seeds the review-state index attribute on write, so the
        # double has to as well or the reviewer queue looks empty here but not in AWS.
        applications[key] = {"review_state": repo.PENDING_REVIEW_STATE, **item}
        return dict(applications[key])

    monkeypatch.setattr(repo, "create_application_version", create_application)
    monkeypatch.setattr(
        repo,
        "get_application_version",
        lambda application_id, version: dict(applications[(application_id, version)])
        if (application_id, version) in applications
        else None,
    )

    def create_review(item):
        key = (item["application_id"], item["version"])
        if key in reviews:
            raise repo.TeacherApplicationConflict("exists")
        reviews[key] = dict(item)
        return dict(item)

    monkeypatch.setattr(repo, "create_review", create_review)
    monkeypatch.setattr(
        repo,
        "get_review",
        lambda application_id, version: dict(reviews[(application_id, version)])
        if (application_id, version) in reviews
        else None,
    )

    def set_review_state(application_id, version, *, review_state, decided_at):
        key = (application_id, version)
        if key not in applications:
            raise repo.TeacherApplicationConflict("application version missing")
        applications[key].update(review_state=review_state, decided_at=decided_at)

    monkeypatch.setattr(repo, "set_application_review_state", set_review_state)
    monkeypatch.setattr(
        repo,
        "list_applications_by_review_state",
        lambda review_state, *, limit=50: [
            dict(item)
            for item in sorted(applications.values(), key=lambda row: row["created_at"])
            if item.get("review_state") == review_state
        ][:limit],
    )

    def send_invitation_email(recipient, *, activation_token, expires_at, full_name=""):
        delivered_invitations.append(
            {
                "recipient": recipient,
                "token": activation_token,
                "expires_at": expires_at,
                "full_name": full_name,
            }
        )

    delivered_invitations: list[dict] = []
    monkeypatch.setattr(
        teacher_application_service.notify_service,
        "send_teacher_invitation_email",
        send_invitation_email,
    )

    def create_invitation(item):
        invitations[item["token_digest"]] = dict(item)
        return dict(item)

    monkeypatch.setattr(repo, "create_invitation", create_invitation)
    monkeypatch.setattr(
        repo,
        "get_invitation",
        lambda digest: dict(invitations[digest]) if digest in invitations else None,
    )

    def claim_invitation(digest, *, command_id, consumed_at):
        item = invitations[digest]
        if item["status"] != "issued":
            return False
        item.update(status="consumed", command_id=command_id, consumed_at=consumed_at, version=2)
        return True

    monkeypatch.setattr(repo, "claim_invitation", claim_invitation)

    def create_command(item):
        commands.setdefault(item["command_id"], dict(item))
        return dict(commands[item["command_id"]])

    monkeypatch.setattr(repo, "create_activation_command", create_command)
    monkeypatch.setattr(
        repo,
        "get_activation_command",
        lambda command_id: dict(commands[command_id]) if command_id in commands else None,
    )

    def update_command(command_id, *, expected_version, status, updated_at, evidence_reference):
        item = commands[command_id]
        if item["version"] != expected_version:
            raise repo.TeacherApplicationConflict("stale")
        item.update(
            status=status,
            updated_at=updated_at,
            evidence_reference=evidence_reference,
            version=expected_version + 1,
        )
        return dict(item)

    monkeypatch.setattr(repo, "update_activation_command", update_command)
    monkeypatch.setattr(
        teacher_application_service.user_repo,
        "put_user",
        lambda item: profiles.__setitem__(item["user_id"], dict(item)),
    )

    def create_binding(**kwargs):
        key = (kwargs["issuer"], kwargs["subject"])
        bindings.setdefault(key, dict(kwargs))
        return dict(bindings[key])

    monkeypatch.setattr(
        teacher_application_service.identity_repo, "create_identity_binding", create_binding
    )
    monkeypatch.setattr(
        teacher_application_service.security_audit_repo,
        "append_event",
        lambda stream_id, event: audits.append((stream_id, dict(event))),
    )
    return {
        "applications": applications,
        "reviews": reviews,
        "invitations": invitations,
        "commands": commands,
        "profiles": profiles,
        "bindings": bindings,
        "audits": audits,
        # Email is the only place the plaintext token appears, so tests read it here for
        # the same reason a candidate does rather than from the reviewer's response.
        "delivered": delivered_invitations,
    }


def _delivered_token(state):
    assert state["delivered"], "an approved application must deliver one invitation email"
    return state["delivered"][-1]["token"]


def test_t472_04_frozen_clock_supports_invitation_expiry(frozen_clock):
    issued_at = frozen_clock.now()
    frozen_clock.advance(seconds=901)
    assert (frozen_clock.now() - issued_at).total_seconds() == 901


def test_t472_04_provider_mutations_are_observable(fake_cognito):
    fake_cognito.admin_add_user_to_group(Username="teacher-1", GroupName="teacher")
    assert fake_cognito.calls == [
        ("admin_add_user_to_group", {"Username": "teacher-1", "GroupName": "teacher"})
    ]


def test_public_application_and_approval_create_no_privilege(monkeypatch):
    state = _install_teacher_repositories(monkeypatch)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    application = teacher_application_service.submit_application(
        {
            "email": "candidate@example.test",
            "email_verified": True,
            "full_name": "Candidate Teacher",
            "subjects": ["mathematics"],
            "statement": "I teach mathematics offline.",
        },
        now=lambda: now,
    )
    approved = teacher_application_service.review_application(
        actor=_reviewer(),
        application_id=application["applicationId"],
        version=application["version"],
        decision="approved",
        reason="offline qualifications reviewed",
        now=lambda: now,
    )

    assert state["profiles"] == {}
    assert state["bindings"] == {}
    assert len(state["invitations"]) == 1
    invitation = next(iter(state["invitations"].values()))
    # The reviewer's response must never carry a usable credential: the token reaches the
    # bound address only, and what is stored is a digest.
    assert "invitationToken" not in approved
    assert approved["invitationDelivered"] is True
    assert state["delivered"][-1]["recipient"] == "candidate@example.test"
    assert _delivered_token(state) not in repr(invitation)
    assert invitation["application_version"] == application["version"]
    assert "document" not in repr(state["applications"])


def test_activation_is_same_email_single_use_and_fail_closed(monkeypatch):
    state = _install_teacher_repositories(monkeypatch)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    application = teacher_application_service.submit_application(
        {
            "email": "candidate@example.test",
            "email_verified": True,
            "full_name": "Candidate Teacher",
            "subjects": ["mathematics"],
            "statement": "I teach mathematics offline.",
        },
        now=lambda: now,
    )
    teacher_application_service.review_application(
        actor=_reviewer(),
        application_id=application["applicationId"],
        version=1,
        decision="approved",
        reason="offline qualifications reviewed",
        now=lambda: now,
    )

    class Provider:
        def __init__(self):
            self.calls = []

        def ensure_teacher_identity(self, **kwargs):
            self.calls.append(kwargs)

    provider = Provider()
    activated = teacher_application_service.activate_from_invitation(
        token=_delivered_token(state),
        verified_email="candidate@example.test",
        issuer="https://identity.test/primary",
        subject="subject-teacher-1",
        provider=provider,
        now=lambda: now + timedelta(seconds=1),
    )
    assert activated["status"] == "active"
    assert state["profiles"][activated["userId"]]["account_status"] == "active"
    assert len(provider.calls) == 1
    assert len(state["bindings"]) == 1

    with pytest.raises(HTTPException) as replay:
        teacher_application_service.activate_from_invitation(
            token=_delivered_token(state),
            verified_email="candidate@example.test",
            issuer="https://identity.test/primary",
            subject="subject-teacher-1",
            provider=provider,
            now=lambda: now + timedelta(seconds=2),
        )
    assert replay.value.detail["code"] == "invitation_already_used"
    assert len(provider.calls) == 1


def test_invitation_wrong_email_and_expiry_never_create_profile(monkeypatch):
    state = _install_teacher_repositories(monkeypatch)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    application = teacher_application_service.submit_application(
        {
            "email": "candidate@example.test",
            "email_verified": True,
            "full_name": "Candidate Teacher",
            "subjects": ["mathematics"],
            "statement": "I teach mathematics offline.",
        },
        now=lambda: now,
    )
    teacher_application_service.review_application(
        actor=_reviewer(),
        application_id=application["applicationId"],
        version=1,
        decision="approved",
        reason="offline qualifications reviewed",
        invitation_expiry_seconds=60,
        now=lambda: now,
    )
    for email, instant, code in [
        ("other@example.test", now + timedelta(seconds=1), "invitation_email_mismatch"),
        ("candidate@example.test", now + timedelta(seconds=61), "invitation_expired"),
    ]:
        with pytest.raises(HTTPException) as denied:
            teacher_application_service.activate_from_invitation(
                token=_delivered_token(state),
                verified_email=email,
                issuer="https://identity.test/primary",
                subject="subject-teacher-1",
                provider=object(),
                now=lambda instant=instant: instant,
            )
        assert denied.value.detail["code"] == code
    assert state["profiles"] == {}


def test_provider_failure_keeps_local_teacher_non_active_and_retry_resumes(monkeypatch):
    state = _install_teacher_repositories(monkeypatch)
    now = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    application = teacher_application_service.submit_application(
        {
            "email": "candidate@example.test",
            "email_verified": True,
            "full_name": "Candidate Teacher",
            "subjects": ["mathematics"],
            "statement": "I teach mathematics offline.",
        },
        now=lambda: now,
    )
    teacher_application_service.review_application(
        actor=_reviewer(),
        application_id=application["applicationId"],
        version=1,
        decision="approved",
        reason="offline qualifications reviewed",
        now=lambda: now,
    )

    class Provider:
        def __init__(self):
            self.fail = True
            self.calls = 0

        def ensure_teacher_identity(self, **_kwargs):
            self.calls += 1
            if self.fail:
                raise TimeoutError("provider-canary-must-not-be-audited")

    provider = Provider()
    activation = dict(
        token=_delivered_token(state),
        verified_email="candidate@example.test",
        issuer="https://identity.test/primary",
        subject="subject-teacher-1",
        provider=provider,
    )
    with pytest.raises(HTTPException) as deferred:
        teacher_application_service.activate_from_invitation(
            **activation, now=lambda: now + timedelta(seconds=1)
        )
    assert deferred.value.status_code == 503
    profile = next(iter(state["profiles"].values()))
    assert profile["account_status"] == "pending_review"
    assert "provider-canary" not in repr(state["audits"])

    provider.fail = False
    result = teacher_application_service.activate_from_invitation(
        **activation, now=lambda: now + timedelta(seconds=2)
    )
    assert result["status"] == "active"
    assert state["profiles"][result["userId"]]["account_status"] == "active"
    assert provider.calls == 2


@pytest.mark.parametrize(
    "case",
    [
        "approve-exact-version",
        "invitation-same-email",
        "invitation-expired",
        "invitation-replay",
        "concurrent-consumption",
        "provider-partial-failure",
        "immediate-revocation",
    ],
    ids=lambda value: f"T-472-04-onboarding-{value}",
)
def test_t472_04_teacher_onboarding_state_machine_cases(case):
    from stoa.security.teacher_onboarding import exercise_onboarding_case

    result = exercise_onboarding_case(case)
    assert result.safe is True
    assert result.privilege_count <= 1


_CANDIDATE = {
    "email": "candidate@example.test",
    "email_verified": True,
    "full_name": "Candidate Teacher",
    "subjects": ["mathematics"],
    "statement": "I teach mathematics offline.",
}
_ISSUER = "https://identity.test/primary"
_PASSWORD = "correct-horse-battery"


def _non_reviewer():
    actor = _reviewer()
    actor["current_grants"] = []
    return actor


def _submit(monkeypatch, *, now):
    state = _install_teacher_repositories(monkeypatch)
    application = teacher_application_service.submit_application(dict(_CANDIDATE), now=lambda: now)
    return state, application


def _submit_and_approve(monkeypatch, *, now, invitation_expiry_seconds=259200):
    state, application = _submit(monkeypatch, now=now)
    approved = teacher_application_service.review_application(
        actor=_reviewer(),
        application_id=application["applicationId"],
        version=application["version"],
        decision="approved",
        reason="offline qualifications reviewed",
        invitation_expiry_seconds=invitation_expiry_seconds,
        now=lambda: now,
    )
    return state, application, approved


class _AccountProvider:
    """Stands in for Cognito, including its refusal to create a duplicate address."""

    def __init__(self, subject="subject-claimed-1"):
        self._subject = subject
        self.created = []
        self.groups = []

    def create_teacher_account(self, *, email, password):
        if any(entry["email"] == email for entry in self.created):
            raise teacher_identity_provider.TeacherAccountExists(email)
        self.created.append({"email": email, "password": password})
        return self._subject

    def ensure_teacher_identity(self, **kwargs):
        self.groups.append(kwargs)


def test_claim_creates_an_account_only_for_the_invited_address(monkeypatch):
    now = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    state, _, _ = _submit_and_approve(monkeypatch, now=now)
    provider = _AccountProvider()

    activated = teacher_application_service.claim_and_activate(
        token=_delivered_token(state),
        password=_PASSWORD,
        issuer=_ISSUER,
        provider=provider,
        now=lambda: now + timedelta(seconds=1),
    )

    assert activated["status"] == "active"
    # The address comes from the invitation, never from the caller, so a stolen token
    # cannot be redirected to an identity the reviewer did not approve.
    assert [entry["email"] for entry in provider.created] == ["candidate@example.test"]
    assert len(provider.groups) == 1
    assert state["profiles"][activated["userId"]]["account_status"] == "active"
    assert len(state["bindings"]) == 1


def test_claim_is_single_use_and_never_creates_a_second_account(monkeypatch):
    now = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    state, _, _ = _submit_and_approve(monkeypatch, now=now)
    provider = _AccountProvider()
    token = _delivered_token(state)
    teacher_application_service.claim_and_activate(
        token=token,
        password=_PASSWORD,
        issuer=_ISSUER,
        provider=provider,
        now=lambda: now + timedelta(seconds=1),
    )

    with pytest.raises(HTTPException) as replay:
        teacher_application_service.claim_and_activate(
            token=token,
            password=_PASSWORD,
            issuer=_ISSUER,
            provider=provider,
            now=lambda: now + timedelta(seconds=2),
        )

    assert replay.value.detail["code"] == "invitation_already_used"
    assert len(provider.created) == 1
    assert len(state["profiles"]) == 1


def test_claim_fails_closed_on_expired_and_unknown_tokens(monkeypatch):
    now = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    state, _, _ = _submit_and_approve(monkeypatch, now=now, invitation_expiry_seconds=60)
    provider = _AccountProvider()

    for token, instant, code in [
        (_delivered_token(state), now + timedelta(seconds=61), "invitation_expired"),
        ("unknown-token-value-that-was-never-issued", now + timedelta(seconds=1), "invitation_invalid"),
    ]:
        with pytest.raises(HTTPException) as denied:
            teacher_application_service.claim_and_activate(
                token=token,
                password=_PASSWORD,
                issuer=_ISSUER,
                provider=provider,
                now=lambda instant=instant: instant,
            )
        assert denied.value.detail["code"] == code

    assert provider.created == []
    assert state["profiles"] == {}
    assert state["bindings"] == {}


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (teacher_identity_provider.TeacherAccountExists("taken"), 409, "account_exists"),
        (
            teacher_identity_provider.TeacherAccountPasswordRejected("weak"),
            422,
            "password_rejected",
        ),
        (
            teacher_identity_provider.TeacherAccountUnavailable("down"),
            503,
            "activation_temporarily_unavailable",
        ),
    ],
    ids=["account-exists", "password-rejected", "provider-unavailable"],
)
def test_claim_maps_provider_refusals_and_grants_nothing(monkeypatch, error, status_code, code):
    now = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    state, _, _ = _submit_and_approve(monkeypatch, now=now)

    class Refusing:
        def create_teacher_account(self, **_kwargs):
            raise error

        def ensure_teacher_identity(self, **_kwargs):
            raise AssertionError("identity must not be granted when account creation failed")

    with pytest.raises(HTTPException) as denied:
        teacher_application_service.claim_and_activate(
            token=_delivered_token(state),
            password=_PASSWORD,
            issuer=_ISSUER,
            provider=Refusing(),
            now=lambda: now + timedelta(seconds=1),
        )

    assert denied.value.status_code == status_code
    assert denied.value.detail["code"] == code
    assert state["profiles"] == {}
    assert state["bindings"] == {}


def test_public_status_reports_progress_without_submitted_content(monkeypatch):
    now = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    state, application = _submit(monkeypatch, now=now)
    application_id = application["applicationId"]

    pending = teacher_application_service.application_status(application_id)
    assert pending["reviewState"] == "pending_review"
    # An enumerated id must reveal how far the application moved and nothing else.
    assert set(pending) == {"applicationId", "version", "reviewState", "createdAt", "decidedAt"}

    teacher_application_service.review_application(
        actor=_reviewer(),
        application_id=application_id,
        version=application["version"],
        decision="rejected",
        reason="internal reviewer note that must stay private",
        now=lambda: now,
    )
    decided = teacher_application_service.application_status(application_id)
    assert decided["reviewState"] == "rejected"
    body = repr(decided)
    for secret in [
        "internal reviewer note that must stay private",
        _CANDIDATE["statement"],
        _CANDIDATE["email"],
        _CANDIDATE["full_name"],
    ]:
        assert secret not in body
    assert state["delivered"] == []

    with pytest.raises(HTTPException) as missing:
        teacher_application_service.application_status("application_does_not_exist")
    assert missing.value.status_code == 404


def test_reviewer_listing_requires_capability_and_withholds_statements(monkeypatch):
    now = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    _submit(monkeypatch, now=now)

    listed = teacher_application_service.applications_for_reviewer(_reviewer())
    assert listed["count"] == 1
    assert listed["items"][0]["verifiedEmail"] == _CANDIDATE["email"]
    # Reviewers open a single version to read the statement; the queue must not carry it.
    assert "statement" not in listed["items"][0]
    assert _CANDIDATE["statement"] not in repr(listed)

    with pytest.raises(HTTPException) as denied:
        teacher_application_service.applications_for_reviewer(_non_reviewer())
    assert denied.value.status_code == 403

    with pytest.raises(HTTPException) as invalid:
        teacher_application_service.applications_for_reviewer(_reviewer(), review_state="all")
    assert invalid.value.detail["code"] == "invalid_review_state"


def test_reissue_delivers_a_fresh_token_without_returning_it(monkeypatch):
    now = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    state, application, _ = _submit_and_approve(monkeypatch, now=now)
    first_token = _delivered_token(state)

    reissued = teacher_application_service.reissue_invitation(
        actor=_reviewer(),
        application_id=application["applicationId"],
        version=application["version"],
        now=lambda: now + timedelta(seconds=5),
    )

    second_token = _delivered_token(state)
    assert second_token != first_token
    assert "invitationToken" not in reissued
    assert reissued["invitationDelivered"] is True
    assert state["delivered"][-1]["recipient"] == _CANDIDATE["email"]

    provider = _AccountProvider()
    activated = teacher_application_service.claim_and_activate(
        token=second_token,
        password=_PASSWORD,
        issuer=_ISSUER,
        provider=provider,
        now=lambda: now + timedelta(seconds=6),
    )
    assert activated["status"] == "active"

    # Reissue does not revoke the superseded invitation, so the provider's refusal to
    # create a duplicate address is what keeps a stale token from yielding a second
    # account. Tightening this to an explicit revoke is tracked separately.
    with pytest.raises(HTTPException) as stale:
        teacher_application_service.claim_and_activate(
            token=first_token,
            password=_PASSWORD,
            issuer=_ISSUER,
            provider=provider,
            now=lambda: now + timedelta(seconds=7),
        )
    assert stale.value.detail["code"] == "account_exists"
    assert len(provider.created) == 1
    assert len(state["profiles"]) == 1


def test_reissue_is_denied_without_capability_or_an_approval(monkeypatch):
    now = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    state, application = _submit(monkeypatch, now=now)

    with pytest.raises(HTTPException) as unapproved:
        teacher_application_service.reissue_invitation(
            actor=_reviewer(),
            application_id=application["applicationId"],
            version=application["version"],
            now=lambda: now,
        )
    assert unapproved.value.detail["code"] == "application_not_approved"

    with pytest.raises(HTTPException) as denied:
        teacher_application_service.reissue_invitation(
            actor=_non_reviewer(),
            application_id=application["applicationId"],
            version=application["version"],
            now=lambda: now,
        )
    assert denied.value.status_code == 403

    assert state["delivered"] == []
    assert state["invitations"] == {}
