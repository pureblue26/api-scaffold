# api-scaffold

[![CI](https://github.com/pureblue26/api-scaffold/actions/workflows/ci.yml/badge.svg)](https://github.com/pureblue26/api-scaffold/actions/workflows/ci.yml)

FastAPI 工程脚手架：配置工程（pydantic-settings + fail-fast）、异常分类、健康检查、测试、CI 开箱即用。

## 技术栈

- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- FastAPI + SQLAlchemy(async) + asyncpg + Alembic
- pydantic-settings（类型化环境配置）
- PostgreSQL 16 + Redis 7（docker-compose）
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
  main.py               # 入口：装配全局 + 各领域路由
  core/
    config.py           # 全局配置（环境变量 > .env.<ENV> > 默认值 + 生产 fail-fast）
    exceptions.py       # 全局异常基类 AppError（领域异常继承它，自动注册）
    paths.py
  database/
    base.py             # 引擎/会话工厂 + get_session 依赖
  models/
    base.py             # ORM 基类 BaseModel（领域模型继承它）
  domains/              # ★ 领域层：一个业务领域一个自包含文件夹
    auth/               # 认证领域（JWT + bcrypt）
      router.py  schemas.py  models.py  service.py
      dependencies.py  security.py  config.py  exceptions.py
    health/             # 健康检查领域
      router.py
    README.md           # 领域层规则与接入流程
tests/
  conftest.py           # pytest 共享（NullPool 测试引擎）
  health/
    test_health.py      # 测试按领域镜像组织
alembic/                # 数据库迁移
.github/workflows/      # CI
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

## 接口一览

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | /api/auth/register | 注册用户 | 公开 |
| POST | /api/auth/login | 登录换 JWT（限流 5 次/分/IP） | 公开 |
| POST | /api/auth/logout | 登出（token 立即失效） | 需 Bearer Token |
| GET | /api/auth/me | 当前用户信息 | 需 Bearer Token |
| PATCH | /api/auth/me/username | 修改用户名 | 需 Bearer Token |
| PATCH | /api/auth/me/password | 修改密码（验旧密码，旧 token 全失效） | 需 Bearer Token |
| GET | /api/auth/users | 用户列表 | 仅管理员 |
| GET | /api/products | 商品列表（Redis 缓存） | 公开 |
| GET | /api/products/{id} | 商品详情（Redis 缓存） | 公开 |
| POST | /api/products | 创建商品 | 仅管理员 |
| POST | /api/orders | 下单（原子扣库存） | 需 Bearer Token |
| GET | /api/orders | 我的订单 | 需 Bearer Token |
| GET | /api/orders/{id} | 订单详情 | 本人/管理员 |
| POST | /api/orders/{id}/pay | 支付 | 本人 |
| POST | /api/orders/{id}/cancel | 取消（回补库存） | 本人 |
| GET | /api/health | 存活检查 | 公开 |
| GET | /api/health/db | 数据库连通性 | 公开 |

## 压测（locust）

```bash
# 1. 启动服务（限流调大，避免压测被登录限流干扰）
$env:LOGIN_RATE_LIMIT='10000'; uv run python -m app.main
# 2. 跑压测（45 秒，20 用户）
$env:PYTHONUTF8='1'; uv run locust -f locustfile.py --headless -u 20 -r 5 -t 45s --only-summary --host http://127.0.0.1:8000
# 3. A/B 对比缓存收益：CACHE_ENABLED=false 重启服务再压一遍
```

> PYTHONUTF8=1 是必须的：locust 解析 pyproject.toml 时 Windows GBK 编解码中文注释会崩。

## 开发常用命令

```bash
uv run ruff check .          # 代码检查
uv run pytest                # 跑测试
uv run alembic revision --autogenerate -m "描述"   # 生成迁移
uv run alembic upgrade head  # 应用迁移
uv run python -m app.seed --password <密码>   # 初始化管理员（幂等）
```
