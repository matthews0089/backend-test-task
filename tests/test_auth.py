from app.core.security import hash_password, verify_password


async def test_registration_and_login(client):
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "password123"},
    )
    assert register.status_code == 201
    assert register.json()["user"]["email"] == "new@example.com"

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "new@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    assert "access_token" in login.cookies


async def test_password_hashing():
    hashed = hash_password("password123")
    assert hashed != "password123"
    assert verify_password("password123", hashed)
    assert not verify_password("wrong-password", hashed)


async def test_protected_endpoint_requires_auth(client):
    response = await client.get("/api/v1/plans")
    assert response.status_code == 401


async def test_protected_endpoint_allows_authenticated_user(authenticated_client):
    response = await authenticated_client.get("/api/v1/plans")
    assert response.status_code == 200
    assert len(response.json()) == 3
