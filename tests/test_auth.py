import uuid
import pytest
from fastapi.testclient import TestClient
from app.api.main import app

client = TestClient(app)


def test_auth_signup_and_login_flow():
    unique_suffix = uuid.uuid4().hex[:8]
    email = f"testuser_{unique_suffix}@example.com"
    password = "SuperSecretPassword123!"

    # 1. Sign up
    signup_payload = {
        "email": email,
        "password": password,
        "full_name": "Test Engineer",
        "organization_name": "Test Engineering Corp",
    }
    res = client.post("/api/v1/auth/signup", json=signup_payload)
    assert res.status_code == 201, res.text
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == email
    assert data["user"]["full_name"] == "Test Engineer"
    assert data["organization"]["name"] == "Test Engineering Corp"
    assert data["organization"]["api_key"].startswith("sp_live_")

    token = data["access_token"]

    # 2. Duplicate signup should return 400
    dup_res = client.post("/api/v1/auth/signup", json=signup_payload)
    assert dup_res.status_code == 400

    # 3. Login with correct credentials
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "access_token" in login_data
    assert login_data["user"]["email"] == email

    # 4. Login with incorrect password should return 401
    bad_login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword999!"},
    )
    assert bad_login.status_code == 401

    # 5. Get current profile (/me) with valid token
    me_res = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["user"]["email"] == email
    assert me_data["organization"]["name"] == "Test Engineering Corp"

    # 6. /me without token should return 401
    unauth_res = client.get("/api/v1/auth/me")
    assert unauth_res.status_code == 401

    # 7. Rotate organization API key
    rotate_res = client.post(
        "/api/v1/auth/rotate-api-key",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rotate_res.status_code == 200
    rotated_org = rotate_res.json()
    assert rotated_org["api_key"].startswith("sp_live_")
    assert rotated_org["api_key"] != data["organization"]["api_key"]
