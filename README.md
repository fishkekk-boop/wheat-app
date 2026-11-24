# Wheat-APP（麦田-目标规划助手）

FastAPI + SQLAlchemy（async）+ PostgreSQL 的 auth 服务，采用**垂直切片 + 三层**结构：
`router`（薄，只做绑定）→ `service`（业务编排）→ `repository`（持久化）。

## 技术栈

- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- FastAPI、Pydantic v2、pydantic-settings
- SQLAlchemy 2.0（async + asyncpg）+ Alembic
- structlog（结构化日志）
- pwdlib[argon2] + PyJWT（密码哈希 / JWT）
- pytest + pytest-asyncio + pytest-cov

## 目录结构

```
src/wheat_app/
├── main.py               # 应用工厂 create_app() + 启动入口 run()
├── config.py             # Pydantic Settings（环境变量）
├── core/                 # 与业务无关的共享基础设施
│   ├── database.py       # engine / 会话工厂 / Base / 命名约定
│   ├── dependencies.py   # 全局依赖（get_db：请求级事务）
│   ├── exceptions.py     # 异常骨架（AppError / DomainError / InfrastructureError ...）
│   ├── exception_handlers.py  # 全局异常 → {error_code, message}
│   ├── security.py       # 密码哈希 / JWT 读取
│   ├── logging.py        # structlog 配置
│   ├── middleware.py     # request_id 中间件
│   └── db_errors.py      # 从 IntegrityError 提取约束名
├── features/auth/        # 业务域（垂直切片）
│   ├── router.py         # HTTP 层：参数绑定 + response_model
│   ├── service.py        # 用例编排：业务规则
│   ├── repository.py     # 存储端口（Protocol）
│   ├── repository_sql.py # SQLAlchemy 实现（适配器）
│   ├── models.py         # 领域模型（纯 Pydantic）
│   ├── auth_orm.py       # SQLAlchemy 表结构
│   ├── schemas.py        # HTTP 请求/响应模型
│   ├── dependencies.py   # get_auth_repo / get_auth_service / get_current_user
│   ├── exceptions.py     # auth 领域异常
│   └── tokens.py         # JWT 签发/校验
└── shared/               # 跨 feature 复用
    ├── constraints.py    # 字段格式约束（StrippedStr / PhoneNumber / UuidPk）
    └── schema.py         # ORMModel（from_attributes）
```

## 快速开始

```bash
# 1. 安装依赖
uv sync

# 2. 准备环境变量（复制并填写）
cp .env.example .env

# 3. 准备数据库（Postgres）
createdb wheat
psql -d postgres -c "CREATE ROLE wheat LOGIN PASSWORD 'wheat_dev_pwd';"
psql -d postgres -c "CREATE DATABASE wheat OWNER wheat;"

# 4. 执行迁移
uv run alembic upgrade head

# 5. 启动
uv run wheat-app          # 或 uv run uvicorn wheat_app.main:create_app --factory --reload

# 6. 测试
uv run pytest -q --cov=src
```

## 环境变量

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `APP_NAME` | 应用名 | `Wheat-APP` |
| `DATABASE_URL` | 数据库连接串 | `sqlite:///./wheat.db` |
| `SECRET_KEY` | JWT 签名密钥（必填，生产 ≥32 位） | — |
| `ALGORITHM` | JWT 算法（必填） | — |
| `ENV` / `APP_ENV` | 运行环境（dev/test/prod） | `dev` |
| `DEBUG` | 是否开启调试/重载 | `false` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | access token 有效期 | `15` |
| `REFRESH_TOKEN_EXPIRE_MINUTES` | refresh token 有效期 | `10080`（7 天） |

## API 端点

| 方法 | 路径 | 说明 | 鉴权 |
| --- | --- | --- | --- |
| GET | `/` | 健康检查 | 无 |
| POST | `/auth/register/password` | 注册（用户名+密码） | 无 |
| POST | `/auth/login/password` | 登录 | 无 |
| POST | `/auth/login/password/form` | OAuth2 表单登录（供 Swagger） | 无 |
| POST | `/auth/token/refresh` | 刷新 token | 无 |
| GET | `/auth/users/me` | 当前用户资料 | access token |
| PATCH | `/auth/users/me` | 更新资料（nickname/bio/avatar_url） | access token |
| GET | `/auth/users/me/identities` | 当前用户所有登录方式 | access token |
| DELETE | `/auth/users/me/identities/{provider}` | 解绑登录方式（需当前密码） | access token |
| GET | `/auth/users/{user_id}` | 用户公开资料 | 无 |
| DELETE | `/auth/users/{user_id}` | 软删除用户 | admin |

## 编码约定

### 分层职责

| 层 | 该做什么 | 不该做什么 |
| --- | --- | --- |
| `router` | 绑定参数、`response_model`、状态码 | 业务逻辑 |
| `service` | 业务规则、用例编排、日志 | 直接接触 SQL/ORM |
| `repository` | `add`/`flush`、约束错误翻译 | commit（交给 `get_db`）|

### 异常

- `core/exceptions.py`：无业务名词的语义骨架（`DomainError`→4xx、`InfrastructureError`→5xx）。
- `features/auth/exceptions.py`：auth 领域异常，只继承 core 的语义基类。
- 判断是否新建异常：**前端会不会据此分支？状态码是否不同？日志是否要区分？** 三个都是「否」就复用。

### 事务

- 会话生命周期 = 请求（`core/dependencies.get_db` 统一 commit/rollback）。
- repository 只 `flush()`：把唯一约束/外键错误提前到本层，才能翻译成 409/404。
- 捕获 `IntegrityError` 后 repository 会 `rollback()`，故当前每个用例都是单步写。

### 其他

- 枚举列存 `StrEnum.value`（小写），避免数据库里出现 `ACTIVE` 与 API 的 `active` 不一致。
- 索引/约束命名由 `core/database.py` 的 `NAMING_CONVENTION` 统一。
- 提交前跑：`uv run pytest -q`、`uvx ruff check src tests`、`uvx pyright --pythonpath .venv/bin/python`。
