def test_register_creates_user_and_returns_token(client):
    resp = client.post("/auth/register", json={"email": "a@example.com", "password": "s3cret!"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_register_rejects_duplicate_email(client):
    client.post("/auth/register", json={"email": "a@example.com", "password": "s3cret!"})

    resp = client.post("/auth/register", json={"email": "a@example.com", "password": "different"})

    assert resp.status_code == 400


def test_login_succeeds_with_correct_credentials(client):
    client.post("/auth/register", json={"email": "a@example.com", "password": "s3cret!"})

    resp = client.post("/auth/login", json={"email": "a@example.com", "password": "s3cret!"})

    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_login_rejects_wrong_password(client):
    client.post("/auth/register", json={"email": "a@example.com", "password": "s3cret!"})

    resp = client.post("/auth/login", json={"email": "a@example.com", "password": "wrong"})

    assert resp.status_code == 401


def test_login_rejects_nonexistent_email(client):
    resp = client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever"})

    assert resp.status_code == 401
