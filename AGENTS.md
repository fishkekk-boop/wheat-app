# wheat-app（主项目）

FastAPI + Pydantic v2 + async SQLAlchemy 2.0（asyncpg）+ PostgreSQL 的 auth 服务。
结构：垂直切片 + 三层（`router` → `service` → `repository`）。

## 常用命令

```bash
uv sync                                   # 安装依赖
uv run alembic upgrade head               # 执行迁移
uv run wheat-app                          # 启动（开发）
uv run pytest -q                          # 全部测试（93 个）
uv run pytest -q --cov=src                # 覆盖率（当前 91%）
uvx ruff check src tests                  # 静态检查
uvx pyright --pythonpath .venv/bin/python  # 类型检查
```

提交前三件套：`pytest` 全绿 + `ruff` 无错 + `pyright` 0 error。

## 目录

```
src/wheat_app/
├── main.py            # create_app() + run() + GET / 健康检查
├── config.py          # pydantic-settings
├── core/              # 与业务无关：database / dependencies(get_db) / exceptions /
│                      # exception_handlers / security / logging / middleware / db_errors
├── features/auth/     # router / service / repository(Protocol) / repository_sql /
│                      # models(领域) / auth_orm(表) / schemas(传输) /
│                      # dependencies / exceptions / tokens
└── shared/            # constraints / schema(ORMModel)
migrations/            # Alembic（migrations/ 已被 ruff 排除，勿格式化）
tests/                 # conftest + 按主题拆分的测试文件
```

## 编码约定（改代码必须遵守）

- **分层**：`router` 只做参数绑定 + `response_model`；`service` 管业务规则与编排；`repository` 只管持久化。`service` **不得** import `schemas` 或 `sqlalchemy`。
- **事务**：会话生命周期 = 请求（`core/dependencies.get_db` 统一 commit/rollback）。repository 只 `add`/`flush`，**不 commit**；捕获 `IntegrityError` 后 rollback 再翻译成业务异常。
- **异常**：`core/exceptions.py` 放不含业务名词的语义骨架（4xx/5xx）；`features/auth/exceptions.py` 放业务异常，只继承 core 语义基类。新增异常前先问自己：前端会分支？状态码不同？日志要区分？都是否 → 复用。
- **枚举**：列上存 `StrEnum.value`（小写），统一用 `auth_orm.ENUM_KW`。
- **命名**：约束/索引由 `core/database.py` 的 `NAMING_CONVENTION` 生成（`uq_*`、`ix_*`、`*_fkey`）。
- **安全**：密码只存 argon2 哈希；登录失败统一 `InvalidCredentials`（防枚举）；敏感操作（解绑登录方式）需重新输入密码；公开资料响应不得含 email/phone。

## 测试约定

- 测试连独立库 `wheat_test`（`tests/conftest.py` 在 import 应用前设 `DATABASE_URL`），**不要**指向开发库 `wheat`。
- 每个用例前 `TRUNCATE` 清表（autouse fixture）；软删会改名 identifier，按 `user_id` 查而不是按账号名。
- `TestClient` 必须用 `with`（否则 lifespan 不执行，`app.state.db_session_factory` 不存在）。
- httpx 0.28 的 `client.delete()` 不接受 `json=`，带 body 用 `client.request("DELETE", url, json=...)`。

## 已知缺口（M5 待做，别当成 bug 修）

1. refresh token 未落库 → 不能撤销/轮换；旧 refresh 在有效期内仍可用。
2. 无登录失败限流/锁定。
3. `update_user` 是「读-改-写」，锁未配 `populate_existing`，并发下可能丢更新（将来改 patch 式更新）。
4. `AuthService._LOGIN_CAPABLE_PROVIDERS` 目前只有 `PASSWORD`；接入邮箱/手机号登录时必须同步加入，否则用户会被过度保护。

## 学习约束（重要）

- 数据结构、业务逻辑、SQL、重构**由用户手写**；AI 只审查、给示例、写测试骨架。
- 改源码前先征得同意；默认只做「读 + 审查 + 给方案」。
- 不要提交 `.env` / `.env.dev`（已在 `.gitignore`，且已从索引移除）。
- 提交信息：中文 + `feat/fix/test/refactor/chore/docs` 前缀。
