"""压测脚本：模拟用户浏览商品 + 下单。

读接口（商品列表/详情）公开，是压测主体；下单需要 token，共享一个。
商品从列表动态挑选（有货才下单），避免硬编码 id 撞上库存为 0 的商品。
"""
import random
import uuid

from locust import HttpUser, between, task


class StoreUser(HttpUser):
    wait_time = between(0.2, 1.0)

    token: str | None = None  # 共享 token（类属性）

    def on_start(self):
        if StoreUser.token is None:
            # 防御：登录可能被限流（429），重试拿不到 token 就不挂任务
            for _ in range(3):
                username = f"load_{uuid.uuid4().hex[:8]}"
                self.client.post(
                    "/api/auth/register",
                    json={"username": username, "password": "password123"},
                )
                r = self.client.post(
                    "/api/auth/login", json={"username": username, "password": "password123"}
                )
                if r.status_code == 200:
                    StoreUser.token = r.json()["access_token"]
                    break
        if StoreUser.token:
            self.headers = {"Authorization": f"Bearer {StoreUser.token}"}

    def _products(self):
        """取商品列表（走 Redis 缓存）。"""
        r = self.client.get("/api/products")
        return r.json() if r.status_code == 200 else []

    @task(6)
    def browse_products(self):
        """商品列表（走 Redis 缓存）——压测主体。"""
        self._products()

    @task(3)
    def product_detail(self):
        """商品详情（走 Redis 缓存）。"""
        products = self._products()
        if products:
            self.client.get(f"/api/products/{products[0]['id']}")

    @task(1)
    def create_order(self):
        """下单（写路径：扣库存 + 失效缓存）。只挑有货的商品。"""
        products = self._products()
        in_stock = [p for p in products if p["stock"] > 0]
        if not in_stock:
            return
        product = random.choice(in_stock)
        with self.client.post(
            "/api/orders",
            json={"items": [{"product_id": product["id"], "quantity": 1}]},
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code != 201:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:150]}")
