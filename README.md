# api-scaffold

[![CI](https://github.com/pureblue26/api-scaffold/actions/workflows/ci.yml/badge.svg)](https://github.com/pureblue26/api-scaffold/actions/workflows/ci.yml)

FastAPI + PostgreSQL + Redis 电商后端脚手架：**配置工程、领域分层、并发安全、缓存策略、幂等、超时任务、可观测性、CI** 开箱即用。

## 功能特性

- **认证**：JWT + bcrypt、登出黑名单、改密全量失效（token 版本号）、登录限流、seed 初始化管理员
- **商品**：创建/修改/详情/分页列表，Redis 缓存（Cache Aside + 穿透/击穿/雪崩防护 + 版本号失效）
- **订单**：下单（原子扣库存）、支付（幂等）、取消/退款（回补库存）、发货/完成、**超时自动取消**、完整状态机
- **并发安全**：所有写路径由数据库约束兜底（原子 UPDATE / 唯一索引 / 条件状态迁移），并发测试守护
- **可观测性**：request-id 全链路（响应头 + 错误响应 + 日志关联）、DB/Redis 健康检查
- **工程化**：pydantic-settings 配置链 + 生产 fail-fast、Alembic 迁移、63 个测试、ruff、GitHub Actions CI、locust 压测

## 技术栈

- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- FastAPI + SQLAlchemy(async) + asyncpg + Alembic
- pydantic-settings（类型化环境配置，生产 fail-fast）
- PostgreSQL 16 + Redis 7（docker-compose）
- pytest（63 个测试）+ ruff + GitHub Actions CI + locust

## 快速开始

```bash
# 1. 安装依赖
uv sync

# 2. 启动数据库与 Redis
docker compose up -d

# 3. 准备环境变量
cp .env.example .env.dev

# 4. 首次部署：应用数据库迁移
uv run alembic upgrade head

# 5. 初始化管理员（幂等：已存在则跳过）
uv run python -m app.seed --password <你的密码>

# 6. 启动
uv run python -m app.main
# 或开发热重载：
uv run uvicorn app.main:app --reload
```

## 目录结构

```
app/
  main.py               # 入口：装配全局 + 各领域路由 + lifespan（Redis/超时任务）
  seed.py               # 初始化管理员脚本（幂等）
  core/                 # 全局横切
    config.py           # 配置：环境变量 > .env.<ENV> > 默认值 + 生产 fail-fast
    exceptions.py       # 异常分类 AppError（自动注册）+ 兜底 500（带 request_id）
    redis.py            # Redis 客户端（按事件循环自动重建）
    ratelimit.py        # 限流依赖工厂（INCR + EXPIRE）
    request_id.py       # 请求 ID 中间件（X-Request-ID）
    paths.py
  database/
    base.py             # 引擎/会话工厂 + get_session 依赖
  models/
    base.py             # ORM 基类 BaseModel
  domains/              # ★ 领域层：一个业务领域一个自包含文件夹
    auth/               # 认证：JWT/bcrypt/黑名单/版本号/限流
      router.py  schemas.py  models.py  service.py  data.py
      dependencies.py  security.py  config.py  exceptions.py
    store/              # 商品/订单：状态机/超时/幂等/缓存
      router.py  schemas.py  models.py  service.py  data.py
      cache.py  tasks.py  exceptions.py
    health/             # 健康检查（存活/DB/Redis）
      router.py
    README.md           # 领域层规则与接入流程
tests/                  # 测试按领域镜像组织（63 个）
  auth/  store/  health/  core/
  conftest.py           # NullPool 测试引擎 + Redis 自动接入
alembic/                # 数据库迁移
docker/initdb/          # 首次建卷时创建测试库
locustfile.py           # 压测脚本
.github/workflows/      # CI（Postgres + Redis service）
```

## 环境配置机制

配置读取优先级：**环境变量 > .env.<ENVIRONMENT> 文件 > 代码默认值**。

- `ENVIRONMENT`（默认 `dev`）决定读取哪个 `.env.<环境>` 文件
- **生产环境启动即 fail-fast**：SECRET_KEY/JWT_SECRET 必须 32 位以上、数据库密码不能是默认值、`DEBUG` 必须 False、REDIS_URL 不能是本机默认值——任一不满足直接拒绝启动
- 测试/生产不要携带 `.env` 文件，由 CI/CD 或密钥管理注入环境变量

### 主要配置项

| 配置 | 默认 | 说明 |
|---|---|---|
| `ENVIRONMENT` | dev | dev / test / prod |
| `DEBUG` | False | 调试开关（生产 fail-fast 拒绝 True） |
| `SECRET_KEY` / `JWT_SECRET` | 开发占位 | 生产必须注入 32+ 位随机串 |
| `DATABASE_*` | postgres/postgres/scaffold_dev | 数据库连接（URL 自动拼装） |
| `REDIS_URL` | redis://127.0.0.1:6380/0 | Redis 连接 |
| `CACHE_ENABLED` | True | 缓存总开关（压测 A/B、故障演练） |
| `ORDER_TIMEOUT_MINUTES` | 30 | 待支付订单超时自动取消时限 |
| `LOGIN_RATE_LIMIT` / `LOGIN_RATE_WINDOW` | 5 / 60 | 登录限流（次/秒窗口/IP） |

```bash
# Windows PowerShell 切换环境
$env:ENVIRONMENT='test'; uv run python -m app.main
```

## 业务领域

### 认证（auth）

JWT + bcrypt（PyJWT/bcrypt，不用停维护的 python-jose/passlib）。Redis 支撑两套失效机制：

- **登出黑名单**：jti 入黑名单，TTL = token 剩余有效期（过期自动清理）
- **token 版本号**：改密后版本 +1，所有旧 token 立即失效

### 订单状态机（store）

```text
PENDING ──支付──▶ PAID ──发货──▶ SHIPPED ──完成──▶ COMPLETED
   │                │
   └─取消─▶ CANCELLED   └─退款─▶ REFUNDED
   （回补库存）          （回补库存）
```

- **图上没有的迁移一律 409**（条件 UPDATE 兜底并发）
- **超时**：PENDING 超过 `ORDER_TIMEOUT_MINUTES` 自动取消——支付防线（过期不能支付）+ 后台清扫任务（每 60s）
- **支付幂等**：已 PAID 重复支付返回当前状态（200）；可带 `payment_id` 流水号，Redis SETNX 去重防重放

### 缓存策略（"改了什么"决定"失效什么"）

| 缓存 | 失效方式 | 为什么 |
|---|---|---|
| 商品列表 | 版本号 +1（建/改商品时）；TTL 60-90s | 名称/价格变了必须及时可见 |
| 商品详情 | 写路径直接删（下单/取消/退款/改商品） | 决策页必须精确 |
| 订单列表 | **不缓存** | 私有 + 频繁变动 + 正确性敏感 |

## 接口一览

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | /api/auth/register | 注册用户 | 公开 |
| POST | /api/auth/login | 登录换 JWT（限流） | 公开 |
| POST | /api/auth/logout | 登出（token 立即失效） | 需 Bearer Token |
| GET | /api/auth/me | 当前用户信息 | 需 Bearer Token |
| PATCH | /api/auth/me/username | 修改用户名 | 需 Bearer Token |
| PATCH | /api/auth/me/password | 修改密码（旧 token 全失效） | 需 Bearer Token |
| GET | /api/auth/users | 用户列表 | 仅管理员 |
| GET | /api/products?limit&offset | 商品列表（缓存 + 分页） | 公开 |
| GET | /api/products/{id} | 商品详情（缓存） | 公开 |
| POST | /api/products | 创建商品 | 仅管理员 |
| PATCH | /api/products/{id} | 修改商品 | 仅管理员 |
| POST | /api/orders | 下单（原子扣库存） | 需 Bearer Token |
| GET | /api/orders?limit&offset | 我的订单（分页，不缓存） | 需 Bearer Token |
| GET | /api/orders/{id} | 订单详情 | 本人/管理员 |
| POST | /api/orders/{id}/pay | 支付（幂等，可带 payment_id） | 本人 |
| POST | /api/orders/{id}/cancel | 取消（回补库存） | 本人 |
| POST | /api/orders/{id}/ship | 发货 | 仅管理员 |
| POST | /api/orders/{id}/complete | 完成 | 仅管理员 |
| POST | /api/orders/{id}/refund | 退款（回补库存） | 仅管理员 |
| GET | /api/health | 存活检查 | 公开 |
| GET | /api/health/db | 数据库连通性 | 公开 |
| GET | /api/health/redis | Redis 连通性 | 公开 |

## 压测（locust）

```bash
# 1. 启动服务（限流调大，避免压测被登录限流干扰）
$env:LOGIN_RATE_LIMIT='10000'; uv run python -m app.main
# 2. 跑压测（45 秒，20 用户）
$env:PYTHONUTF8='1'; uv run locust -f locustfile.py --headless -u 20 -r 5 -t 45s --only-summary --host http://127.0.0.1:8000
# 3. A/B 对比缓存收益：CACHE_ENABLED=false 重启服务再压一遍
```

> `PYTHONUTF8=1` 是必须的：locust 解析 pyproject.toml 时 Windows GBK 编解码中文注释会崩。

## 可观测性

- 每个响应都带 `X-Request-ID` 头（客户端自带则透传，否则自动生成）
- 所有错误响应（含 500）都返回 `request_id`，客户端可拿它反馈排查
- 未处理异常会在服务端日志记录 request_id + 路径 + 堆栈

## 开发常用命令

```bash
uv run ruff check .          # 代码检查
uv run pytest                # 跑测试（63 个）
uv run alembic revision --autogenerate -m "描述"   # 生成迁移
uv run alembic upgrade head  # 应用迁移
uv run python -m app.seed --password <密码>   # 初始化管理员（幂等）
```
