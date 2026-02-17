def test_register(client):
    res = client.post("/api/auth/register", json={
        "email": "new@shop.com",
        "password": "pass1234",
        "full_name": "Jane Doe",
        "shop_name": "Jane's Boutique",
        "pos_system": "square",
    })
    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_register_duplicate(client):
    payload = {
        "email": "dup@shop.com",
        "password": "pass1234",
        "full_name": "Jane",
        "shop_name": "Shop",
        "pos_system": "square",
    }
    client.post("/api/auth/register", json=payload)
    res = client.post("/api/auth/register", json=payload)
    assert res.status_code == 409


def test_login_success(client):
    client.post("/api/auth/register", json={
        "email": "login@shop.com",
        "password": "pass1234",
        "full_name": "Jane",
        "shop_name": "Shop",
        "pos_system": "square",
    })
    res = client.post("/api/auth/login", json={
        "email": "login@shop.com",
        "password": "pass1234",
    })
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_wrong_password(client):
    client.post("/api/auth/register", json={
        "email": "wrong@shop.com",
        "password": "pass1234",
        "full_name": "Jane",
        "shop_name": "Shop",
        "pos_system": "square",
    })
    res = client.post("/api/auth/login", json={
        "email": "wrong@shop.com",
        "password": "badpassword",
    })
    assert res.status_code == 401


def test_me_authenticated(client, auth_headers):
    res = client.get("/api/auth/me", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "test@shop.com"
    assert data["full_name"] == "Test Owner"


def test_me_unauthenticated(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401


def test_logout(client, auth_headers):
    res = client.post("/api/auth/logout")
    assert res.status_code == 200
