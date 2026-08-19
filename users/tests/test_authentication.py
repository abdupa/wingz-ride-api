"""
Requirement 2: only users with role 'admin' may call the endpoints.

Authentication (who are you) and authorisation (are you allowed) are tested
separately, because they fail with different status codes and for different
reasons.
"""

import pytest
from rest_framework.authtoken.models import Token

from config.urls import router


def registered_list_urls():
    return [f"/api/{prefix}/" for prefix, _viewset, _basename in router.registry]


@pytest.mark.django_db
@pytest.mark.parametrize("url", registered_list_urls())
def test_every_registered_route_rejects_anonymous(anonymous_api, url):
    """
    Walks the router rather than naming endpoints one by one, so a ViewSet
    added later cannot be left unprotected without this test going red.
    """
    assert anonymous_api.get(url).status_code == 401
    assert anonymous_api.post(url, {}, format="json").status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize("url", registered_list_urls())
def test_authenticated_non_admin_is_forbidden(anonymous_api, rider, url):
    anonymous_api.force_authenticate(user=rider)
    assert anonymous_api.get(url).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("url", registered_list_urls())
def test_admin_is_allowed(api, url):
    assert api.get(url).status_code == 200


@pytest.mark.django_db
def test_anonymous_gets_401_not_403(anonymous_api):
    """
    DRF picks 401 vs 403 from the first authentication class. Token auth sends
    a WWW-Authenticate header and yields 401; session auth sends none and
    yields 403. This pins the ordering in settings.
    """
    response = anonymous_api.get("/api/rides/")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Token")


@pytest.mark.django_db
def test_a_bad_token_is_rejected(anonymous_api):
    anonymous_api.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
    assert anonymous_api.get("/api/rides/").status_code == 401


@pytest.mark.django_db
def test_token_endpoint_is_reachable_without_a_token(anonymous_api, admin):
    """
    The permission is global, so without an explicit exemption you would need
    an admin token to obtain an admin token.
    """
    response = anonymous_api.post(
        "/api/auth/token/",
        {"email": "ada.admin@example.com", "password": "test-pass-123"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["token"] == Token.objects.get(user=admin).key


@pytest.mark.django_db
def test_a_real_token_opens_the_api(anonymous_api, admin):
    token = Token.objects.create(user=admin)
    anonymous_api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    assert anonymous_api.get("/api/rides/").status_code == 200


@pytest.mark.django_db
def test_wrong_password_is_rejected(anonymous_api, admin):
    response = anonymous_api.post(
        "/api/auth/token/",
        {"email": "ada.admin@example.com", "password": "wrong"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_login_is_case_insensitive_on_email(anonymous_api, admin):
    """Emails are lowercased on save, so the stored value is canonical."""
    response = anonymous_api.post(
        "/api/auth/token/",
        {"email": "ADA.ADMIN@EXAMPLE.COM", "password": "test-pass-123"},
        format="json",
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_a_non_admin_can_authenticate_but_gets_nowhere(anonymous_api, rider):
    """
    Proving who you are and being allowed in are separate questions. A rider
    gets a perfectly valid token that opens no doors.
    """
    response = anonymous_api.post(
        "/api/auth/token/",
        {"email": rider.email, "password": "test-pass-123"},
        format="json",
    )
    assert response.status_code == 200

    anonymous_api.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")
    assert anonymous_api.get("/api/rides/").status_code == 403
