"""Wave 0 teacher lifecycle cases; state-machine behavior is implemented in Plan 04."""

import pytest

pytest_plugins = ("security.conftest",)


def test_t472_04_frozen_clock_supports_invitation_expiry(frozen_clock):
    issued_at = frozen_clock.now()
    frozen_clock.advance(seconds=901)
    assert (frozen_clock.now() - issued_at).total_seconds() == 901


def test_t472_04_provider_mutations_are_observable(fake_cognito):
    fake_cognito.admin_add_user_to_group(Username="teacher-1", GroupName="teacher")
    assert fake_cognito.calls == [
        ("admin_add_user_to_group", {"Username": "teacher-1", "GroupName": "teacher"})
    ]


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
