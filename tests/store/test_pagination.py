"""分页测试：页大小/偏移/总数/边界校验。"""
from tests.conftest import make_admin
from tests.store.test_store import _create_product, _register


def _make_products(client, count=5):
    admin_id, admin_headers = _register(client, "admin")
    make_admin(client, admin_id)
    for i in range(count):
        _create_product(client, admin_headers, name=f"商品{i}", price=100 + i, stock=100)
    return admin_headers


def test_pagination_pages_and_total(client):
    _make_products(client, 5)

    r = client.get("/api/products?limit=2&offset=0")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert body["has_more"] is True

    # 最后一页：剩 1 条，没有下一页
    r = client.get("/api/products?limit=2&offset=4")
    body = r.json()
    assert len(body["items"]) == 1
    assert body["has_more"] is False


def test_pagination_defaults(client):
    _make_products(client, 3)
    # 不带参数：limit 默认 20，返回全部 3 条
    r = client.get("/api/products")
    body = r.json()
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert len(body["items"]) == 3
    assert body["has_more"] is False


def test_pagination_validation(client):
    assert client.get("/api/products?limit=0").status_code == 422   # 小于 1
    assert client.get("/api/products?limit=101").status_code == 422  # 超过 100
    assert client.get("/api/products?offset=-1").status_code == 422  # 负数
