import re

from fastapi.testclient import TestClient

from app.services import mailer


def _link_token(to: str) -> str:
    msg = [m for m in mailer.outbox if m["To"] == to][-1]
    return re.search(r"#token=([A-Za-z0-9_\-]+)", msg.get_content()).group(1)


def test_create_user(client: TestClient):
    response = client.post(
        "/api/v1/register",
        json={"email": "test@example.com", "password": "password123", "full_name": "Test User"},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["verification_required"] is True
    assert "access_token" not in data and "id" not in data


def test_login_user(client: TestClient):
    # Not before the e-mail is confirmed...
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "EMAIL_NOT_VERIFIED"

    # ...and normally afterwards.
    v = client.post("/api/v1/auth/verify-email",
                    json={"token": _link_token("test@example.com"), "password": "password123"})
    assert v.status_code == 200, v.text
    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
