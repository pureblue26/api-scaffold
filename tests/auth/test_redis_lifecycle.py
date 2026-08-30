"""auth Redis 测试：登出黑名单 / 改密全量失效 / 登录限流。"""


def _register_and_login(client, username="alice", password="password123"):
    client.post("/api/auth/register", json={"username": username, "password": password})
    token = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_logout_revokes_token_immediately(client):
    headers = _register_and_login(client)
    r = client.post("/api/auth/logout", headers=headers)
    assert r.status_code == 200

    # 旧 token 立即失效
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 401
    assert r.json()["message"] == "令牌已失效"


def test_password_change_revokes_all_tokens(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "password123"})
    old_token = client.post(
        "/api/auth/login", json={"username": "alice", "password": "password123"}
    ).json()["access_token"]
    old_headers = {"Authorization": f"Bearer {old_token}"}

    r = client.patch(
        "/api/auth/me/password",
        json={"old_password": "password123", "new_password": "newpassword456"},
        headers=old_headers,
    )
    assert r.status_code == 200

    # 改密后：旧 token 立即失效（版本号 +1）
    assert client.get("/api/auth/me", headers=old_headers).status_code == 401

    # 新密码登录拿到的新 token 正常
    new_token = client.post(
        "/api/auth/login", json={"username": "alice", "password": "newpassword456"}
    ).json()["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
    assert r.status_code == 200


def test_login_rate_limited(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "password123"})
    body = {"username": "alice", "password": "password123"}

    for _ in range(5):  # 前 5 次正常
        assert client.post("/api/auth/login", json=body).status_code == 200

    r = client.post("/api/auth/login", json=body)  # 第 6 次：限流
    assert r.status_code == 429
