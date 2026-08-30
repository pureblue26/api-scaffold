def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["app"] == "api-scaffold"
    assert body["environment"] == "test"


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_db_graceful(client):
    """数据库没启动也要返回 200 + 明确错误，而不是 500。"""
    r = client.get("/api/health/db")
    assert r.status_code == 200
    assert r.json()["status"] in ("ok", "error")


def test_health_redis(client):
    """Redis 连通性检查（认证/缓存的关键路径）。"""
    r = client.get("/api/health/redis")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
