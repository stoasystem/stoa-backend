"""Sign-in hands over the refresh token Cognito issued (`/auth/refresh`).

`/auth/refresh` has existed the whole time, and Cognito has returned a
`RefreshToken` on every sign-in. The login route read `AccessToken` off the
result and dropped the rest, so nothing could ever call that route: a reader
was signed out the moment their access token expired, which is an hour.
"""

from __future__ import annotations

import inspect

from stoa.routers import auth


def test_the_response_model_carries_a_refresh_token() -> None:
    assert "refreshToken" in auth.AuthResponse.model_fields


def test_a_pool_that_issues_none_leaves_the_field_empty_rather_than_blank() -> None:
    """`.get` and not `[...]`: an absent token must not become `""`, which a
    reader would send back and have refused."""
    source = inspect.getsource(auth)

    assert 'resp["AuthenticationResult"].get("RefreshToken")' in source
    assert 'resp["AuthenticationResult"]["RefreshToken"]' not in source
    assert auth.AuthResponse.model_fields["refreshToken"].default is None


def test_sign_in_passes_it_to_the_response() -> None:
    source = inspect.getsource(auth)

    assert source.count("refresh_token=refresh_token,") == 2, (
        "both sign-in paths hand it over; one that does not signs that reader "
        "out in an hour"
    )


def test_refreshing_keeps_the_token_the_caller_sent() -> None:
    """REFRESH_TOKEN_AUTH does not reissue one. Returning nothing there would
    make the second refresh impossible."""
    source = inspect.getsource(auth)

    assert 'result.get("RefreshToken") or body.refresh_token' in source


def test_the_builder_defaults_to_no_token_rather_than_requiring_one() -> None:
    signature = inspect.signature(auth._auth_response_for_profile)

    assert signature.parameters["refresh_token"].default is None
