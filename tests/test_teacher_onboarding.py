"""Wave 0 teacher lifecycle cases; state-machine behavior is implemented in Plan 04."""

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
