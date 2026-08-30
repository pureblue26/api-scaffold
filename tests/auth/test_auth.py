"""auth 领域测试：注册/登录/认证依赖/角色校验。"""
from tests.conftest import make_admin


def register(client, username="alice", password="password123"):
    return client.post("/api/auth/register", json={"username": username, "password": password})


def login(client, username="alice", password="password123"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_register_success(client):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["username"] == "alice"
    assert body["role"] == "user"
    # 响应绝不含密码相关字段
    assert "password" not in body and "password_hash" not in body


def test_register_duplicate_username(client):
    register(client)
    r = register(client)
    assert r.status_code == 409
    assert r.json()["message"] == "用户名已存在"


def test_register_invalid_username(client):
    """pydantic pattern 校验：非法用户名 422。"""
    r = client.post("/api/auth/register", json={"username": "a b!", "password": "password123"})
    assert r.status_code == 422


def test_register_short_password(client):
    r = client.post("/api/auth/register", json={"username": "bob", "password": "short"})
    assert r.status_code == 422


def test_login_success(client):
    register(client)
    r = login(client)
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_login_wrong_password(client):
    register(client)
    r = login(client, password="wrong-password")
    assert r.status_code == 401


def test_login_unknown_user_same_error(client):
    """用户不存在和密码错误返回同样的 401（防用户枚举）。"""
    r = login(client, username="nobody", password="whatever123")
    assert r.status_code == 401
    assert r.json()["message"] == "用户名或密码错误"


def test_me_requires_token(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_with_token(client):
    register(client)
    token = login(client).json()["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "alice"


def test_list_users_forbidden_for_normal_user(client):
    register(client)
    token = login(client).json()["access_token"]
    r = client.get("/api/auth/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_list_users_as_admin(client):
    r = register(client)
    make_admin(client, r.json()["id"])
    token = login(client).json()["access_token"]
    r = client.get("/api/auth/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_change_username_success(client):
    register(client)
    token = login(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r = client.patch("/api/auth/me/username", json={"new_username": "alice2"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["username"] == "alice2"
    # 新用户名能登录
    assert login(client, username="alice2").status_code == 200


def test_change_username_duplicate(client):
    register(client, username="alice")
    register(client, username="bob")
    token = login(client, username="bob").json()["access_token"]
    r = client.patch(
        "/api/auth/me/username",
        json={"new_username": "alice"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409


def test_change_password_success(client):
    register(client)
    token = login(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r = client.patch(
        "/api/auth/me/password",
        json={"old_password": "password123", "new_password": "newpassword456"},
        headers=headers,
    )
    assert r.status_code == 200
    # 旧密码失效，新密码可登录
    assert login(client, password="password123").status_code == 401
    assert login(client, password="newpassword456").status_code == 200


def test_change_password_wrong_old(client):
    register(client)
    token = login(client).json()["access_token"]
    r = client.patch(
        "/api/auth/me/password",
        json={"old_password": "wrong-old", "new_password": "newpassword456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401
    assert r.json()["message"] == "旧密码不正确"


def test_update_requires_token(client):
    r = client.patch("/api/auth/me/username", json={"new_username": "alice2"})
    assert r.status_code == 401

