import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.core.security import create_access_token
from app.models import User, UserCreate, UserRole
from tests.utils.item import create_random_item
from tests.utils.user import create_random_user, user_authentication_headers
from tests.utils.utils import random_email, random_lower_string


def create_role_user(
    client: TestClient, db: Session, role: UserRole
) -> tuple[User, dict[str, str]]:
    password = random_lower_string()
    user = crud.create_user(
        session=db,
        user_create=UserCreate(email=random_email(), password=password, role=role),
    )
    headers = user_authentication_headers(
        client=client, email=user.email, password=password
    )
    return user, headers


@pytest.mark.parametrize("role", list(UserRole))
def test_role_read_permissions(client: TestClient, db: Session, role: UserRole) -> None:
    _, headers = create_role_user(client, db, role)
    other_user = create_random_user(db)
    other_item = create_random_item(db)
    expected = 403 if role == UserRole.member else 200

    for path in ("/users/", f"/users/{other_user.id}", "/metrics/"):
        response = client.get(f"{settings.API_V1_STR}{path}", headers=headers)
        assert response.status_code == expected
        if path == "/metrics/" and expected == 200:
            assert response.json()["total_users"] >= 2
            assert response.json()["total_items"] >= 1

    response = client.get(
        f"{settings.API_V1_STR}/items/{other_item.id}", headers=headers
    )
    assert response.status_code == (200 if role == UserRole.admin else 403)


@pytest.mark.parametrize("role", list(UserRole))
def test_only_admin_can_manage_users(
    client: TestClient, db: Session, role: UserRole
) -> None:
    _, headers = create_role_user(client, db, role)
    other_user = create_random_user(db)
    expected = 200 if role == UserRole.admin else 403
    email = random_email()

    response = client.post(
        f"{settings.API_V1_STR}/users/",
        headers=headers,
        json={"email": email, "password": random_lower_string(), "role": "manager"},
    )
    assert response.status_code == expected
    created_user = crud.get_user_by_email(session=db, email=email)
    if role == UserRole.admin:
        assert created_user is not None
        assert created_user.role == UserRole.manager
    else:
        assert created_user is None

    response = client.patch(
        f"{settings.API_V1_STR}/users/{other_user.id}",
        headers=headers,
        json={"role": "admin"},
    )
    assert response.status_code == expected
    db.refresh(other_user)
    assert other_user.role == (
        UserRole.admin if role == UserRole.admin else UserRole.member
    )

    if role == UserRole.admin:
        for invalid_role in (None, "owner"):
            response = client.patch(
                f"{settings.API_V1_STR}/users/{other_user.id}",
                headers=headers,
                json={"role": invalid_role},
            )
            assert response.status_code == 422

    response = client.delete(
        f"{settings.API_V1_STR}/users/{other_user.id}", headers=headers
    )
    assert response.status_code == expected


@pytest.mark.parametrize("role", list(UserRole))
def test_self_profile_and_signup_cannot_assign_privileges(
    client: TestClient, db: Session, role: UserRole
) -> None:
    user, headers = create_role_user(client, db, role)
    response = client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["role"] == role

    response = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"full_name": "Updated profile"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated profile"

    for privileges in (
        {"role": "admin"},
        {"is_superuser": True},
        {"is_active": True},
        {"id": str(uuid.uuid4())},
        {"hashed_password": "forged-hash"},
    ):
        response = client.patch(
            f"{settings.API_V1_STR}/users/me", headers=headers, json=privileges
        )
        assert response.status_code == 422
        db.refresh(user)
        assert user.role == role

        email = random_email()
        response = client.post(
            f"{settings.API_V1_STR}/users/signup",
            json={"email": email, "password": random_lower_string(), **privileges},
        )
        assert response.status_code == 422
        assert crud.get_user_by_email(session=db, email=email) is None

    response = client.post(
        f"{settings.API_V1_STR}/users/signup",
        json={"email": random_email(), "password": random_lower_string()},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "member"


def test_role_changes_apply_to_existing_access_token(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    user, headers = create_role_user(client, db, UserRole.manager)
    response = client.get(f"{settings.API_V1_STR}/metrics/", headers=headers)
    assert response.status_code == 200

    response = client.patch(
        f"{settings.API_V1_STR}/users/{user.id}",
        headers=superuser_token_headers,
        json={"role": "member"},
    )
    assert response.status_code == 200
    response = client.get(f"{settings.API_V1_STR}/metrics/", headers=headers)
    assert response.status_code == 403
    response = client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["role"] == "member"


@pytest.mark.parametrize("credential", ["missing", "invalid", "expired", "deleted"])
def test_protected_routes_reject_invalid_authentication(
    client: TestClient, credential: str
) -> None:
    headers = {}
    if credential == "invalid":
        headers = {"Authorization": "Bearer invalid-token"}
    elif credential in {"expired", "deleted"}:
        token = create_access_token(
            uuid.uuid4(),
            expires_delta=timedelta(minutes=-1 if credential == "expired" else 5),
        )
        headers = {"Authorization": f"Bearer {token}"}

    for path in ("/users/", "/users/me", "/metrics/"):
        response = client.get(f"{settings.API_V1_STR}{path}", headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("role", list(UserRole))
def test_deactivation_revokes_existing_token(
    client: TestClient, db: Session, role: UserRole
) -> None:
    user, headers = create_role_user(client, db, role)
    user.is_active = False
    db.add(user)
    db.commit()

    for path in ("/users/me", "/users/", "/metrics/", "/items/"):
        response = client.get(f"{settings.API_V1_STR}{path}", headers=headers)
        assert response.status_code == 403
        assert response.json()["detail"] == "Inactive user"


@pytest.mark.parametrize("field", ["email", "is_active", "password"])
def test_user_updates_reject_null_required_values(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str], field: str
) -> None:
    user, headers = create_role_user(client, db, UserRole.manager)
    original_email = user.email
    response = client.patch(
        f"{settings.API_V1_STR}/users/{user.id}",
        headers=superuser_token_headers,
        json={field: None},
    )
    assert response.status_code == 422
    if field == "email":
        response = client.patch(
            f"{settings.API_V1_STR}/users/me", headers=headers, json={field: None}
        )
        assert response.status_code == 422
    db.refresh(user)
    assert user.email == original_email
    assert user.is_active
    assert user.role == UserRole.manager


def test_partial_admin_update_preserves_role(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    user, _ = create_role_user(client, db, UserRole.manager)
    response = client.patch(
        f"{settings.API_V1_STR}/users/{user.id}",
        headers=superuser_token_headers,
        json={"full_name": None},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "manager"
    assert response.json()["full_name"] is None


@pytest.mark.parametrize("role", list(UserRole))
def test_item_mutations_respect_ownership(
    client: TestClient, db: Session, role: UserRole
) -> None:
    user, headers = create_role_user(client, db, role)
    other_item = create_random_item(db)
    response = client.post(
        f"{settings.API_V1_STR}/items/",
        headers=headers,
        json={"title": "Own item", "owner_id": str(other_item.owner_id)},
    )
    assert response.status_code == 200
    own_item_id = response.json()["id"]
    assert response.json()["owner_id"] == str(user.id)
    response = client.get(f"{settings.API_V1_STR}/items/", headers=headers)
    listed_ids = {item["id"] for item in response.json()["data"]}
    assert own_item_id in listed_ids
    assert (str(other_item.id) in listed_ids) == (role == UserRole.admin)

    for item_id, expected in (
        (own_item_id, 200),
        (str(other_item.id), 200 if role == UserRole.admin else 403),
    ):
        response = client.put(
            f"{settings.API_V1_STR}/items/{item_id}",
            headers=headers,
            json={"title": "Updated"},
        )
        assert response.status_code == expected
        response = client.delete(
            f"{settings.API_V1_STR}/items/{item_id}", headers=headers
        )
        assert response.status_code == expected


@pytest.mark.parametrize("role", list(UserRole))
def test_admin_utilities_require_admin(
    client: TestClient, db: Session, role: UserRole
) -> None:
    user, headers = create_role_user(client, db, role)
    expected = 200 if role == UserRole.admin else 403
    response = client.post(
        f"{settings.API_V1_STR}/password-recovery-html-content/{user.email}",
        headers=headers,
    )
    assert response.status_code == expected
    if role == UserRole.admin:
        assert response.headers["subject"]
        assert "text/html" in response.headers["content-type"]

    with patch("app.api.routes.utils.send_email") as send_email:
        response = client.post(
            f"{settings.API_V1_STR}/utils/test-email/",
            headers=headers,
            params={"email_to": user.email},
        )
        assert response.status_code == (201 if role == UserRole.admin else 403)
        assert send_email.called == (role == UserRole.admin)
