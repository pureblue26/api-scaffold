# 领域层（app/domains/）

按"业务领域"组织，一个领域一个自包含文件夹（参考 [fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices) 的 Netflix Dispatch 结构）。

## 规则

- **新增领域 = 新建文件夹；删除领域 = 删文件夹**
- 文件**按需创建**，不要空文件仪式：
  - `router.py` —— 该领域的接口（必须有）
  - `schemas.py` —— 该领域的 Pydantic 请求/响应模型
  - `models.py` —— 该领域的 ORM 模型（继承 `app/models/base.py` 的 BaseModel）
  - `service.py` —— 该领域的业务逻辑（规则住在这里，router 只做编排）
  - `dependencies.py` —— 该领域的依赖：资源存在性校验等（FastAPI 请求内缓存结果）
  - `exceptions.py` —— 该领域的异常（继承 `app/core/exceptions.py` 的 AppError，自动注册）
  - `constants.py` —— 该领域的常量 / 错误文案
- **跨领域引用必须显式**：`from app.domains.auth import constants as auth_constants`
- 只有**真正全局**的才放 `app/core/`、`app/database/`、`app/models/base.py`

## 接入流程（第一个业务领域）

1. `app/domains/<名称>/models.py` 定义 ORM 模型（继承 BaseModel）
2. `uv run alembic revision --autogenerate -m "<描述>"` && `uv run alembic upgrade head`
3. `app/domains/<名称>/schemas.py` 定义请求/响应模型
4. `app/domains/<名称>/service.py` 写业务逻辑（含并发正确性：约束/锁/不变式）
5. `app/domains/<名称>/router.py` 写接口
6. `app/main.py` 里 `include_router`
7. `tests/<名称>/` 写测试（含并发测试）
