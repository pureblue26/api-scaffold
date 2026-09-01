"""商品上下架（你的第一个手写功能）——核心逻辑都在这个文件里。

【开始前，先做三个设计决策】——这是本练习最有价值的部分，答案没有唯一解，
但你要说出理由（写完代码后我会问你为什么这样选）：

1. 下架的商品，商品列表还显示吗？
   提示：下架的语义是"不再售卖"。列表是浏览入口，建议不显示。

2. 下架的商品，商品详情还能访问吗？
   提示：已下单用户的历史订单里引用着这个商品。如果详情不能访问，
   用户的"我的订单"里就会显示"商品不存在"。

3. 上下架操作后，哪些缓存要失效？
   提示：列表缓存【必须】失效（下架的商品要立刻从列表消失，不能等 TTL）。
   详情缓存要不要失效，取决于你对第 2 题的答案。

【你的任务】实现下面两个函数（签名已定，实现是你写）：
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.store.models import Product


async def set_product_active(
    session: AsyncSession, product_id: int, is_active: bool
) -> Product | None:
    """上下架商品：修改 is_active 字段 + 失效相关缓存。

    返回更新后的商品；商品不存在返回 None。

    可用的工具（都在项目里，你只管调用）：
    - 查商品:        await data.get_product_by_id(session, product_id)
    - 提交:          await data.save(session, product)
    - 失效列表缓存:  await cache.invalidate_products()
    - 失效详情缓存:  await cache.invalidate_product(product_id)
    """
    # TODO: 你的实现


async def list_active_products(
    session: AsyncSession, limit: int, offset: int
) -> tuple[list[Product], int]:
    """商品列表：只显示上架商品（is_active=True），分页。

    返回 (当前页商品, 总条数)。
    参考 data.py 里 list_products 的写法：
    - 总数:  select(func.count()).select_from(Product).where(...)
    - 当前页: select(Product).where(...).order_by(Product.id).limit(limit).offset(offset)
    """
    # TODO: 你的实现
