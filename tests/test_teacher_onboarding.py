"""Wave 0 teacher lifecycle cases; state-machine behavior is implemented in Plan 04."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
import pytest

from stoa.services import teacher_application_service


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
        applications[key] = dict(item)
        return dict(item)

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
    }

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
    assert "invitationToken" in approved
    assert approved["invitationToken"] not in repr(invitation)
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
    approved = teacher_application_service.review_application(
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
        token=approved["invitationToken"],
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
            token=approved["invitationToken"],
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
    approved = teacher_application_service.review_application(
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
                token=approved["invitationToken"],
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
    approved = teacher_application_service.review_application(
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
        token=approved["invitationToken"],
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
