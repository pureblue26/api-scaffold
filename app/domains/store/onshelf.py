"""商品上下架——你写的第一个功能，现在是真实实现。

【分层修正说明】你写的 list_active_products（只显示上架商品的分页查询）
逻辑已移入 data.list_products——查询属于数据层；onshelf.py 只留业务逻辑。
查询放 data、规则放 service，这是项目一贯的分层。
"""
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.store import cache, data
from app.domains.store.models import Product


async def set_product_active(
    session: AsyncSession, product_id: int, is_active: bool
) -> Product | None:
    """上下架商品：修改 is_active + 维护缓存状态。

    缓存策略（设计决策的落地）：
    - 下架：列表失效 + 详情写"已下架"标记（下次详情零数据库访问返回 410）
    - 上架：列表失效 + 详情删标记（恢复正常）
    shelved_at 只在"下架→上架"转换时更新（重复上架不刷新时间）。
    """
    product = await data.get_product_by_id(session, product_id)
    if product is None:
        return None
    if is_active and not product.is_active:
        product.shelved_at = datetime.now(UTC)  # 只在真正的下架→上架时记时间
    product.is_active = is_active
    await data.save(session, product)
    await cache.invalidate_products()  # 列表必须失效（立刻从列表出现/消失）
    if is_active:
        await cache.invalidate_product(product_id)  # 上架：删掉"已下架"标记
    else:
        await cache.mark_product_delisted(product_id)  # 下架：写标记（不查库）
    return product
