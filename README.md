# api-scaffold

FastAPI 工程脚手架：配置工程（pydantic-settings + fail-fast）、异常分类、健康检查、测试、CI 开箱即用。

## 技术栈

- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- FastAPI + SQLAlchemy(async) + asyncpg + Alembic
- pydantic-settings（类型化环境配置）
- PostgreSQL 16（docker-compose）
- pytest + ruff + GitHub Actions CI

## 快速开始

```bash
# 1. 安装依赖
uv sync

# 2. 启动数据库
docker compose up -d

# 3. 准备环境变量
cp .env.example .env.dev

# 4. 启动
uv run python -m app.main
# 或开发热重载：
uv run uvicorn app.main:app --reload
```

## 目录结构

```
app/
  main.py            # 入口：装配配置、异常、路由
  core/
    config.py        # 环境配置（环境变量 > .env.<ENV> > 默认值 + 生产 fail-fast）
    exceptions.py    # 业务异常分类（NotFound/Conflict/... 自动映射 HTTP 状态码）
  api/
    health.py        # /api/health 与 /api/health/db
    router.py        # 路由聚合：新增业务模块 include_router 进来
  database/
    base.py          # 引擎/会话工厂 + get_session 依赖
  models/            # ORM 模型（继承 models/base.py 的 BaseModel）
  services/          # 业务逻辑
  schemas/           # Pydantic 请求/响应模型
tests/               # pytest（NullPool 测试引擎）
alembic/             # 数据库迁移
.github/workflows/   # CI
```

## 环境配置机制

配置读取优先级：**环境变量 > .env.<ENVIRONMENT> 文件 > 代码默认值**。

- `ENVIRONMENT`（默认 `dev`）决定读取哪个 `.env.<环境>` 文件
- 生产环境启动即 fail-fast：SECRET_KEY 必须 32 位以上随机串、数据库密码不能是默认值、`DEBUG` 必须为 False
- 测试/生产不要携带 `.env` 文件，直接由 CI/CD 或密钥管理注入环境变量

```bash
# Windows PowerShell 切换环境
$env:ENVIRONMENT='test'; uv run python -m app.main
```

## 开发常用命令

```bash
uv run ruff check .          # 代码检查
uv run pytest                # 跑测试
uv run alembic revision --autogenerate -m "描述"   # 生成迁移
uv run alembic upgrade head  # 应用迁移
```
