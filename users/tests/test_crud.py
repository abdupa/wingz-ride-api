import pytest

from users.models import User

USER_PAYLOAD = {
    "role": "driver",
    "first_name": "Howard",
    "last_name": "Yamamoto",
    "email": "howard.yamamoto@example.com",
    "phone_number": "+639170000010",
    "password": "a-strong-test-password-1",
}


@pytest.mark.django_db
def test_create(api):
    response = api.post("/api/users/", USER_PAYLOAD, format="json")
    assert response.status_code == 201
    assert "password" not in response.data
    user = User.objects.get(email="howard.yamamoto@example.com")
    assert user.check_password("a-strong-test-password-1")


@pytest.mark.django_db
def test_list_and_retrieve(api, rider):
    assert api.get("/api/users/").status_code == 200
    response = api.get(f"/api/users/{rider.id_user}/")
    assert response.status_code == 200
    assert response.data["email"] == rider.email


@pytest.mark.django_db
def test_update(api, rider):
    response = api.patch(
        f"/api/users/{rider.id_user}/", {"phone_number": "+639179999999"}, format="json"
    )
    assert response.status_code == 200
    rider.refresh_from_db()
    assert rider.phone_number == "+639179999999"


@pytest.mark.django_db
def test_delete(api, rider):
    assert api.delete(f"/api/users/{rider.id_user}/").status_code == 204
    assert not User.objects.filter(pk=rider.pk).exists()


@pytest.mark.django_db
def test_fields_are_in_the_order_the_spec_lists_them(api, rider):
    response = api.get(f"/api/users/{rider.id_user}/")
    assert list(response.data.keys()) == [
        "id_user",
        "role",
        "first_name",
        "last_name",
        "email",
        "phone_number",
    ]


@pytest.mark.django_db
def test_password_is_never_returned(api, rider):
    response = api.get(f"/api/users/{rider.id_user}/")
    assert "password" not in response.data
    assert "last_login" not in response.data
