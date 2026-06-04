async def test_subscription_page_for_new_user_shows_empty_state(client):
    await client.post(
        "/register",
        data={"email": "web-new@example.com", "password": "password123", "next": "/subscription"},
    )
    login = await client.post(
        "/login",
        data={"email": "web-new@example.com", "password": "password123", "next": "/subscription"},
        follow_redirects=True,
    )

    assert login.status_code == 200
    assert "Choose your first plan" in login.text
    assert "No subscription yet" in login.text
    assert '{"detail":"No subscription found"}' not in login.text


async def test_register_duplicate_email_shows_html_error(client):
    await client.post(
        "/register",
        data={"email": "duplicate@example.com", "password": "password123", "next": "/plans"},
    )

    response = await client.post(
        "/register",
        data={"email": "duplicate@example.com", "password": "password123", "next": "/plans"},
    )

    assert response.status_code == 409
    assert "Email is already registered" in response.text
    assert response.headers["content-type"].startswith("text/html")


async def test_login_invalid_credentials_shows_html_error(client):
    response = await client.post(
        "/login",
        data={"email": "missing@example.com", "password": "wrong-password", "next": "/plans"},
    )

    assert response.status_code == 401
    assert "Invalid email or password" in response.text
    assert response.headers["content-type"].startswith("text/html")
