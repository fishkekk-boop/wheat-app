基于**垂直切片范式**的项目结构，后续开发按以下项目结构进行组织开发

```text
project-root/
├── alembic.ini                # Alembic 迁移配置
├── pyproject.toml             # 依赖与项目元数据（推荐使用 uv / poetry）
├── .env.example
├── README.md
├── src/
│   └── app/
│       ├── main.py            # 应用工厂 create_app()，挂载路由与中间件
│       ├── config.py          # Pydantic Settings，环境变量入口
│       │
│       ├── features/          # 垂直切片：每个业务域一个目录
│       │   ├── auth/
│       │   │   ├── router.py           # 薄路由，只做校验与转发
│       │   │   ├── service.py          # 业务编排与领域逻辑
│       │   │   ├── repository.py       # 数据访问（SQLAlchemy 查询）
│       │   │   ├── models.py           # SQLAlchemy ORM 模型
│       │   │   ├── schemas.py          # Pydantic 请求/响应模型
│       │   │   ├── dependencies.py     # 该功能专用的依赖（如 get_current_user）
│       │   │   ├── exceptions.py       # 功能特有的领域异常
│       │   │   └── constants.py        # 功能特有的常量
│       │   ├── users/
│       │   │   └── ...                 # 同上结构
│       │   └── orders/
│       │       └── ...                 # 同上结构
│       │
│       ├── core/              # 共享基础设施（跨功能，与业务无关）
│       │   ├── database.py            # Engine、Session 工厂、Base
│       │   ├── security.py            # 密码哈希、JWT 签发/验证
│       │   ├── dependencies.py        # 全局依赖：get_db、分页、当前用户
│       │   ├── exceptions.py          # 基础异常类与全局异常处理器
│       │   ├── middleware.py          # CORS、请求 ID、日志等
│       │   └── pagination.py          # 共享分页工具
│       │
│       ├── lib/               # 外部服务客户端（无业务逻辑）
│       │   ├── email.py
│       │   ├── storage.py
│       │   └── payment.py
│       │
│       └── contracts/         # 跨功能的共享类型/事件（可选，按需启用）
│           └── events.py
│
├── migrations/                # Alembic 迁移脚本
│   ├── versions/
│   └── env.py
│
└── tests/                     # 按功能组织的测试
    ├── conftest.py            # Fixtures：测试 DB、客户端、认证
    └── features/
        ├── test_auth.py
        └── test_orders.py
```