# FastAPI 项目目录与开发边界

本文依据 `docs/01`～`docs/14` 和 [项目设计原则](AI_rules.md)，将现有设计落实到 Python 模块、目录职责和开发顺序。本次只提供目录规划，不创建应用脚手架，不表示接口、数据库或测试已经实现。

**采用 `backend/src/backend/` 下的 `api / application / domain / infrastructure` 四层模块化单体。Game Engine 编排用例，领域层决定玩法，Repositories 保存结果，LLM Gateway 只生成受约束的表达。**

## 1. 目录选择与设计基线

仓库拆为 `backend/` 和 `frontend/` 两个独立子项目，各自带依赖、锁文件、工具配置和 `src/`、`tests/`；根目录只放文档、CI 和 `.gitignore`（见仓库 `AGENTS.md`）。后端 Python 包仍名为 `backend`，位于 `backend/src/backend/`，不再增加职责相同的 `app/` 层；启动对象为 `backend.main:app`。前后端只通过 `/api` 通信，互不读取对方目录。

各 Engine 是同一个后端进程内的模块或普通对象，不拆成服务。Repositories 使用 SQLAlchemy 的具体查询与保存函数，不为每张表增加接口、实现、基类和通用 CRUD 层。

前后文已经发生的细化，按下表落实，避免同时维护两种方案：

| 主题 | 实现依据 | 本目录采用的约定 |
| --- | --- | --- |
| 分层与部署 | [03 总体架构](03-architecture-design.md) | FastAPI 模块化单体；领域不依赖 HTTP、数据库和 LLM |
| 领域对象 | [04 领域模型](04-domain-model.md) | `CaseTemplate`、`GameSession`、`Conversation` 分离；领域对象不等同于 ORM 表 |
| 游戏阶段 | [05 状态机](05-state-machine.md) | 九个概念阶段，六个持久阶段；`INIT`、`INTRO`、`JUDGEMENT` 仅在事务内部存在 |
| 规则与谎言 | [06 证据引擎](06-evidence-engine.md)、[08 谎言机制](08-lie-system.md) | 固定步骤求值、分层谎言、一次性效果、独立 JUDGE 分支 |
| 物理存储 | [09 数据库](09-database-design.md) | 20 张关系表与有限 JSON；不沿用早期完整案件包和整局 JSON 双重可写方案 |
| HTTP 契约 | [10 API](10-api-design.md) | `/api/v1`；聊天和出示受理后返回 201，普通 HTTP 轮询表达结果 |
| Memory | [12 Memory](12-memory-design.md) | 加入 `npc_memory_summary`，总计 21 张表；保留 `memory_epoch` 和摘要修订检查 |
| 模型稳定性 | [13 安全](13-security.md) | 严格输出协议、一次生成命令最多一次上游请求、显式重试、主备路由与有界清理 |
| 测试 | [14 测试](14-testing.md) | pytest 按源码层级组织，跨层与浏览器测试单列，真实模型评测单独启用 |

数据库沿用第 09 篇的 PostgreSQL 建议基线，落地时只实现一种数据库。若部署最终选 MySQL，修改基础设施映射和迁移并重跑实库测试，领域目录不变；本方案不新增双库兼容层。

## 2. 完整目标目录树

以下是后端及其配套资源的完整目标清单，按开发阶段逐步建立，不预先创建空文件。前端内部结构沿用 [11 前端设计](11-frontend-design.md)，这里只标明位置。树中的案件文件、测试数据和迁移文件均为待实现文件名，不代表完整案件已经存在。

```text
The-Truing-Murders/
├── AGENTS.md
├── README.md                             # 两个子项目的安装、配置、启动、迁移与检查命令
├── .gitignore                            # 忽略环境、缓存、日志、报告和备份
├── .github/workflows/                    # 后端、前端分别运行检查
├── backend/                              # Python 子项目；所有后端命令在此目录执行
│   ├── pyproject.toml                    # Python 包、依赖、Ruff 与 pytest 配置
│   ├── uv.lock
│   ├── alembic.ini                       # 迁移位置；不写数据库密码
│   ├── compose.yaml                      # 本地 PostgreSQL
│   ├── .env.example                      # 配置项示例；不含真实密钥
│   ├── src/
│   │   └── backend/
│   │       ├── __init__.py
│   │       ├── main.py                   # FastAPI 装配与应用生命周期
│   │       ├── config.py                 # 读取并验证服务端配置
│   │       ├── cli.py                    # W1 命令行切片入口
│   │       ├── import_case.py            # 离线案件导入命令入口
│   │       ├── api/
│   │       │   ├── __init__.py
│   │       │   ├── dependencies.py       # Cookie、请求头与用例依赖获取
│   │       │   ├── middleware.py         # Origin、请求体大小、trace 与缓存策略
│   │       │   ├── errors.py             # 安全的 HTTP 错误映射
│   │       │   ├── routes/
│   │       │   │   ├── __init__.py       # 汇总 /api/v1 路由
│   │       │   │   ├── visitors.py       # 匿名访问者初始化
│   │       │   │   ├── cases.py          # 公开案件列表与简介
│   │       │   │   ├── sessions.py       # 创建、重开、继续、加载与请求查询
│   │       │   │   ├── investigation.py  # 场景、取证、背包、NPC 档案、图与时间线
│   │       │   │   ├── conversations.py  # 审讯、聊天、出示、历史与表达重试
│   │       │   │   └── accusations.py    # 准备、草稿、指控、复盘与完成
│   │       │   └── schemas/
│   │       │       ├── __init__.py
│   │       │       ├── common.py         # 公开错误、请求元数据与响应外壳
│   │       │       ├── sessions.py       # 访问者、案件、会话与请求记录 DTO
│   │       │       ├── investigation.py  # 场景、证据、人物与图表 DTO
│   │       │       ├── conversations.py  # 审讯输入与玩家可读对话 DTO
│   │       │       └── accusations.py    # 草稿、提交、判定与复盘 DTO
│   │       ├── application/
│   │       │   ├── __init__.py
│   │       │   ├── auth.py               # 匿名令牌签发、摘要与身份核验
│   │       │   ├── game.py               # Game Engine；游戏用例与业务事务
│   │       │   ├── generation.py         # Game Engine 的表达任务与计量编排
│   │       │   ├── case.py               # Case Service；载入、校验与离线发布
│   │       │   ├── save_load.py          # Save/Load；一致读取与版本兼容检查
│   │       │   ├── memory.py             # Memory Service；上下文、摘要与 epoch
│   │       │   ├── agents.py             # Agent Manager；受限角色路由
│   │       │   ├── conversation.py       # 输出内容检查与固定降级
│   │       │   └── contracts.py          # 跨应用模块使用的内部 DTO
│   │       ├── domain/
│   │       │   ├── __init__.py
│   │       │   ├── models.py             # 案件、会话、状态、规则输入与结果类型
│   │       │   ├── case_validation.py    # 定义引用、规则配置与发布不变量
│   │       │   ├── state_machine.py      # 阶段枚举、允许动作、转换与守卫
│   │       │   ├── evidence.py           # Evidence Engine；持有、披露与安全投影
│   │       │   ├── rules.py              # Rule Engine；数值、谎言、进度与评分
│   │       │   └── errors.py             # 与 HTTP 无关的领域错误
│   │       └── infrastructure/
│   │           ├── __init__.py
│   │           ├── llm_client.py         # 唯一 LLM Gateway 与供应商协议适配
│   │           └── database/
│   │               ├── __init__.py
│   │               ├── session.py        # Engine、Session 工厂与隔离级别配置
│   │               ├── models/
│   │               │   ├── __init__.py   # Base、metadata 与映射注册
│   │               │   ├── case.py       # 9 张静态案件表
│   │               │   ├── game.py       # 8 张身份、游戏与审计表
│   │               │   └── conversation.py  # 4 张对话、尝试与摘要表
│   │               ├── repositories/
│   │               │   ├── __init__.py
│   │               │   ├── visitors.py   # 凭据摘要、访问者锁与当前局入口
│   │               │   ├── cases.py      # 固定版本读取、组装与维护账号导入
│   │               │   ├── games.py      # 会话快照、证据、NPC、请求、事件与指控
│   │               │   └── conversations.py  # 对话、attempt、用量与摘要条件写入
│   │               └── migrations/
│   │                   ├── env.py        # Alembic 环境与 metadata 接入
│   │                   ├── script.py.mako  # Alembic 标准迁移模板
│   │                   └── versions/
│   │                       └── 0001_initial_schema.py
│   ├── assets/                           # 仅后端读取，含答案和秘密
│   │   ├── database/
│   │   │   └── init.sql                  # 首次初始化时建立测试库
│   │   ├── cases/
│   │   │   └── case_001/
│   │   │       └── v1/
│   │   │           ├── slice.json        # W1 切片
│   │   │           └── case.json         # 人工审核的完整版本包；仅后端导入
│   │   └── prompts/
│   │       └── npc_system_v1.txt         # 受版本管理的 NPC 系统模板
│   └── tests/                            # 结构见第 14 篇第 13 节
│       ├── conftest.py
│       ├── data/                         # 合成案件、人工预期、模型评测题集
│       ├── domain/
│       ├── application/
│       ├── infrastructure/
│       ├── integration/
│       ├── api/
│       ├── e2e/                          # 浏览器到数据库，由 pytest 驱动
│       └── agent_eval/                   # 显式启用、限制预算的真实模型评测
├── frontend/                             # Node 子项目；所有前端命令在此目录执行
│   ├── package.json                      # npm scripts：dev、build、typecheck、lint、test
│   ├── package-lock.json
│   ├── vite.config.ts                    # 开发代理 /api → 127.0.0.1:8000
│   ├── tsconfig.json
│   ├── eslint.config.js
│   ├── .prettierrc.json
│   ├── src/                              # Vue 应用；内部目录见第 11 篇
│   ├── public/                           # 可公开且不剧透的图片、字体
│   └── tests/                            # 组件与页面状态检查
└── docs/
    ├── AI_rules.md
    ├── 01-project-scope.md … 14-testing.md
    ├── 15-development-plan.md
    ├── 16-development-roadmap.html       # 一人开发排期
    └── 17-week-one-delivery.md
```

`backend/src/` 是源码容器，`backend` 包及其普通 Python 子包放置 `__init__.py`；资源、文档和迁移版本目录不需要伪装成业务包。`backend/pyproject.toml` 配置 `src` 包发现。案件和模板使用显式配置的资源根路径，不依赖启动时的当前工作目录。

## 3. 每个目录的职责

### 3.1 后端源码目录

除源码容器一行外，下表路径均相对于 `backend/src/backend/`。

| 目录 | 职责 | 明确边界 |
| --- | --- | --- |
| `backend/src/`、`backend/src/backend/` | 前者容纳源码，后者是后端包与装配入口 | `main.py` 连接各层、注册路由和生命周期，不写玩法规则 |
| `api/` | HTTP 适配、输入结构检查、Cookie/Origin、异常映射 | 不执行规则，不查询 ORM，不请求模型 |
| `api/routes/` | 按玩家业务资源组织端点，将合法输入交给用例 | 不暴露通用 Agent、规则执行或状态补丁 API |
| `api/schemas/` | Pydantic 请求与响应模型；拒绝未知输入字段，白名单输出 | 请求、响应分别定义；不能复用 ORM 或完整领域对象作为公开响应 |
| `application/` | 授权、用例协作、事务、存档、生成与记忆流程 | 调用领域规则和具体基础设施；不自行决定谎言、分值或证据奖励 |
| `domain/` | 领域类型、不变量、确定性规则和信息披露政策 | 仅依赖 Python 数据与纯函数；禁止 FastAPI、ORM、外部网络和密钥 |
| `infrastructure/` | 数据库和 LLM 等外部系统的技术适配 | 不决定何时招供、发证据或结案；基础设施之间也不能任意互调 |
| `infrastructure/database/` | 连接、数据库会话、关系映射、持久化与迁移 | 是生产代码执行数据库操作的唯一模块区域 |
| `infrastructure/database/models/` | SQLAlchemy 表、字段、索引、外键与 CHECK | 不挂载 LLM 调用、玩法状态流转或 ORM 自动业务钩子 |
| `infrastructure/database/repositories/` | 具体读取、行锁、条件更新，以及 ORM 与领域数据转换 | 接收调用方 Session；可以 flush，禁止自行 commit 或决定游戏效果 |
| `infrastructure/database/migrations/` | Alembic 标准环境和迁移入口 | 维护操作独立执行，Web 启动不自动升级数据库 |
| `infrastructure/database/migrations/versions/` | 有顺序的 schema、索引、约束迁移 | 保留历史迁移；变更数据格式不等于换绑案件答案或规则版本 |

`api/dependencies.py` 可以读取 Cookie 并调用 `application/auth.py`，不能自己执行 `select(Visitor)`。数据库连接和客户端由 `main.py` 装配，路由取得的是用例依赖；业务认证查询仍经过应用层和 Repository。

### 3.2 资源与其他目录

| 目录 | 职责 | 边界 |
| --- | --- | --- |
| 仓库根目录 | 项目级说明、CI 和 `.gitignore` | 不放依赖清单、工具配置、Engine、数据库脚本或业务代码 |
| `backend/` | 后端子项目：依赖、锁文件、迁移配置、Compose 与 `.env` | 不读取 `frontend/` 下任何文件 |
| `frontend/` | 前端子项目：npm 依赖、Vite、TypeScript、ESLint、Prettier | 不读取 `backend/` 下任何文件，只通过 `/api` 访问后端 |
| `frontend/src/` | 浏览器页面、交互和公开 API 客户端 | 不保存模型密钥，不持有完整案件包，不作权威判定 |
| `backend/assets/` | 后端读取的版本化非代码资源 | 不能挂成前端静态目录 |
| `backend/assets/cases/` | 离线案件导入源 | 含答案和秘密，仅后端维护流程读取 |
| `backend/assets/cases/case_001/` | 按案件 ID 组织内容 | 不存任何玩家运行状态 |
| `backend/assets/cases/case_001/v1/` | 某次审核发布的固定内容版本 | 修订发布新版本，不覆盖已被会话引用的定义 |
| `backend/assets/prompts/` | 后端维护的系统模板与模板版本 | 模板不内嵌密钥或全案真相；固定承认和回避台词属于案件包 |
| `frontend/public/` | 可直接公开的图片、字体等素材 | 位于另一个子项目，与含秘密的 cases、prompts 物理隔离 |
| `docs/` | 需求、架构、契约、验收和开发计划 | 记录设计，不把规划写成已完成的实现 |

### 3.3 测试目录

| 目录 | 职责 |
| --- | --- |
| `backend/tests/` | 后端检查入口，以及实库、应用的共用配置 |
| `backend/tests/data/` | 受版本管理的合成输入和独立预期，不放真实凭据 |
| `backend/tests/data/cases/` | 小型完整测试案件；录像例与分层实验室例相互独立 |
| `backend/tests/data/expected/` | 人工评分答案和合法通关路径，不能调用被测函数生成 expected |
| `backend/tests/data/agent/` | 固定恶意输出、异常响应、正常与攻击评测题集 |
| `backend/tests/domain/` | 规则、证据、状态机、谎言与评分，无数据库和模型 |
| `backend/tests/application/` | 角色隔离、Memory、Agent 和表达降级，使用可控模型替身 |
| `backend/tests/infrastructure/` | Gateway 真实解析配假传输；数据库映射、权限和迁移配真实目标库 |
| `backend/tests/integration/` | Game Engine 的事务、幂等、并发、存档恢复、计量和故障闭环 |
| `backend/tests/api/` | 真实 FastAPI、应用与测试数据库的 HTTP 契约；不 mock Game Engine |
| `backend/tests/e2e/` | 浏览器到数据库的完整通关、恢复与可访问性，由 pytest 驱动 |
| `backend/tests/agent_eval/` | 独立开启的真实模型语义评测，记录样本、用量和可见违规 |
| `frontend/tests/` | 组件、状态更新和迟到响应隔离 |

Rule Test、State Machine Test、Agent Test 等使用第 14 篇的 marker 分类，不复制同一测试。测试文件按行为拆分即可，例如 `test_lie_system.py` 和 `test_judgement.py` 都可以验证 `domain/rules.py`，不要求新增同名生产模块。

## 4. 核心系统模块的具体落点

| 系统模块 | 文件 | 负责的内容 | 不负责的内容 |
| --- | --- | --- | --- |
| Game Engine | `application/game.py` | 创建与重开、调查、审讯切换、出示、草稿、指控、授权、幂等、版本和业务事务 | 不实现反证、承认阈值和计分公式；不直接访问供应商 |
| 生成编排 | `application/generation.py` | 受理后的生成流程、占位、预留、派发抢占、表达保存、计量、过期清理与摘要维护 | 是 Game Engine 的子流程，不是独立 Agent 或通用任务平台；不授予游戏效果 |
| Agent Manager | `application/agents.py` | 校验受信任角色、上下文与 permit，调用统一 Gateway | 不选调查策略、不读案件库、不调规则；4 个 NPC 共用实现 |
| Evidence Engine | `domain/evidence.py` | 持有与引用校验、应用获批披露、背包、关系图、时间线及 NPC 安全投影 | 不从聊天生成证据，不独立决定解锁条件，不读库 |
| Rule Engine | `domain/rules.py` | 条件白名单、EVENT 固定流水线、效果去重、数值、分层谎言、PROGRESS、JUDGE 评分 | 不持久化、不请求 LLM、不执行任意脚本、不递归派发事件 |
| State Machine | `domain/state_machine.py` | 游戏阶段、动作允许表、合法转换、阶段不变量与 NPC 展示态派生 | 不把模型状态当游戏阶段，不为每种情绪组合建状态类 |
| Repositories | `infrastructure/database/repositories/` | 按已授权用例读取和保存领域数据，落实锁与条件更新 | 不评分、不判断承认、不自行提交调用方事务 |
| LLM Gateway | `infrastructure/llm_client.py` | 连接复用、主备路由、一次请求、容量与冷却、deadline、严格结构校验、usage 归一化 | 不持有 Session、不保存额度、不运行工具、不自动重发或换模追加请求 |
| Case Service | `application/case.py` | 载入绑定版本、调用领域校验；离线导入发布 | 运行时不改定义，不让模型补齐案件 |
| Save/Load Service | `application/save_load.py` | 通过 Repository 装配一致 GameSnapshot，检查摘要、结构和执行版本，保存获批快照 | 不维护第二份存档，不从事件或聊天重新运行整局 |
| Memory Service | `application/memory.py` | `build_context()`、`summarize_history()`、`update_state()` 的既有契约 | 不读写数据库，不调用 LLM，不自行推进承认；Builder 不另建一套 |
| Conversation Service | `application/conversation.py` | 校验候选表达、拒绝越权内容、选择同状态固定回复 | 不写对话表，不执行规则，不让另一个模型裁决业务 |

`generation.py` 从 Game Engine 的表达流程中按职责拆出，防止 `game.py` 同时承载玩法编排和全部超时恢复代码。它可以拥有表达及计量的短事务，但不能提供修改证据、压力、谎言或 Verdict 的入口。其数据库操作仍全部经过 Repository。

Host 和 Review 默认采用固定介绍、阶段提示和已冻结判定的复盘投影，分别由相应用例组合。没有 `HostAgent`、`ReviewAgent`、`JudgeAgent` 的类继承树。以后启用润色时才增加对应模板，复用现有 Agent Manager 和生成流程；GET 复盘始终只读已有结果。

## 5. 依赖方向与禁止事项

### 5.1 允许的调用关系

```text
main.py                                  装配配置、数据库、Gateway、用例与路由
api                                      → application
application/game.py                      → domain + repositories + save_load/case
application/generation.py                → repositories + memory + conversation
application/conversation.py              → agents
application/agents.py                    → infrastructure/llm_client.py
infrastructure/database/repositories     → ORM models + domain 数据类型
domain                                   → Python 标准库
```

应用层可以直接依赖这些具体 Repository 模块，这是现有设计选择；不为追求形式上的依赖倒置增加只有一个实现的 Repository 接口或 Unit of Work 框架。

只有 `main.py`、离线导入入口和测试装配需要把各层连接起来。基础设施不反向调用应用用例，领域层不导入其他三层。API 响应模型与领域模型分开；ORM 实例在 Repository 内转换，不能沿返回链泄露到 API、Memory 或 Agent。

### 5.2 哪些地方禁止直接调用 LLM

**只有 `infrastructure/llm_client.py` 可以向模型服务发送网络请求或使用供应商 SDK。** Agent Manager 调用 Gateway 的 Python 方法，不自行创建第二个客户端。

| 位置 | LLM 调用限制 |
| --- | --- |
| `api/` 全部代码 | 禁止直接调用；只受理业务用例或读取已有结果 |
| `domain/` 全部代码 | 禁止直接或间接依赖 LLM 计算；规则、状态、投影必须可以离线运行 |
| `application/game.py`、`case.py`、`save_load.py`、`auth.py` | 禁止直接调用；需要表达时由既有生成子流程发起 |
| `application/memory.py` | MVP 禁止模型调用；默认摘要由程序完成，必要上下文放不下就降级 |
| `application/conversation.py` | 仅经 Agent Manager 发起授权表达；禁止额外模型审核或修复循环 |
| `application/agents.py` | 仅经唯一 Gateway 调用；不得授予工具、规划游戏动作或自行重试 |
| `infrastructure/database/` | 禁止任何 LLM 调用，包括 Repository、ORM hook 和迁移 |
| `frontend/` 全部代码 | 禁止直连模型服务或保存模型密钥 |

探索、图表查询、指控评分和存档恢复均为零模型调用路径。获取证据、谎言击破、数值变化和状态转换的计算也禁止调用模型；出示证据提交后可以另行生成 NPC 表达。每个首次生成或显式重试命令最多一次上游调用；模型输出只有文本候选及调用元数据，永远不能变成 `RuleOutcome`、规则事件或状态补丁。

### 5.3 哪些地方禁止直接操作数据库

这里的“直接操作”指执行 SQL/ORM 查询、增删改或触发懒加载。应用层通过 Repository 读写，同时保留开启、提交和回滚事务的职责。

| 位置 | 数据库限制 |
| --- | --- |
| `api/` | 禁止导入 ORM、执行 SQL 或持有数据库 Session；认证也通过应用服务 |
| `domain/` | 禁止数据库连接、Repository、查询和持久化副作用 |
| `application/agents.py`、`memory.py`、`conversation.py` | 禁止 Session、Repository 和数据库凭据；只接收已加载的普通数据 |
| `infrastructure/llm_client.py` | 禁止访问数据库；用量返回应用层，不能自行写入 `llm_attempt` |
| 其他应用用例 | 可以通过 Repository 读写，并用 SQLAlchemy Session 的事务机制定义边界；禁止散写 SQL、操作 ORM 实体 |
| `infrastructure/database/repositories/` | 允许执行明确范围的数据库读写；不自行 commit，不绕过调用方的会话锁协议 |
| `infrastructure/database/migrations/` | 允许在维护流程执行 schema 和必要数据迁移；不在玩家请求中运行 |

应用层使用 `Session.begin()` 或对应异步事务管理提交和回滚，Repository 接收同一个 Session 完成跨表操作。所有会话子表写入先锁同一 `game_session`；需要访问者锁时统一按 visitor → session 顺序。Case 和 Save/Load 参与调用方事务，不在中途提交。

Memory 生成摘要候选、epoch 变更建议；Game Engine 在相应事务中经 Repository 保存。摘要 CAS、来源指纹和 epoch 检查不能仅靠 Python 对象上的 `frozen=True` 替代。

### 5.4 哪些地方应该放业务规则

| 规则或决策 | 唯一主要落点 |
| --- | --- |
| 阶段内允许动作、合法转换、结案后只读 | `domain/state_machine.py` |
| 反证条件、心理增量、先求和再截断、谎言击破与承认、深入调查条件 | `domain/rules.py` |
| 固定 EVENT → 谎言检查 → 承认披露 → 一次 PROGRESS 顺序 | `domain/rules.py` |
| 结构化指控、步骤与证据关联评分、类别阈值 | `domain/rules.py` 的独立 JUDGE 分支 |
| 证据持有、引用同案、获批信息应用、玩家和 NPC 可见字段 | `domain/evidence.py`，条件判断复用规则的只读求值 |
| 案件引用、数值配置、层顺序、规则动作白名单与发布不变量 | `domain/case_validation.py` |
| 会话归属、当前局、幂等、版本、事务、生成额度与重试次数 | `application/` 的相应用例；属于用例和运行策略 |
| 历史后缀、摘要来源、token 分配与授权段同步 | `application/memory.py`；不得据此新增玩法权限 |
| 输出结构安全 | `infrastructure/llm_client.py`；游戏语义一致性由 `application/conversation.py` 检查 |
| 案件答案、证据内容、数值参数、固定说法和评分配置 | `backend/assets/cases/` 审核后导入固定数据库版本，由领域代码解释 |

API 只判断字段是否符合协议，例如整数、长度和必填；“持有的证据是否能击破某层谎言”必须进入领域规则。数据库唯一键、外键和 CHECK 是一致性保护，不能代替业务判定；Prompt 只能描述已经确定的表达权限，不能成为业务规则的执行位置。

## 6. 数据模型与 Repository 分工

### 6.1 三种模型不混用

| 模型 | 位置 | 用途 |
| --- | --- | --- |
| API DTO | `api/schemas/` | 验证公开请求，限制公开响应字段；不含完整秘密、条件树和 Prompt |
| 领域数据 | `domain/models.py` | `CaseTemplate`、`GameSnapshot`、`NPCState`、`LieProgress`、`Discovery`、`RuleOutcome`、`AccusationContent`、`Verdict` 等 |
| ORM 模型 | `infrastructure/database/models/` | 表字段、复合外键、唯一约束和 JSON 物理映射 |

`application/contracts.py` 只放实际跨应用模块共享的 `AuthorizedContext`、`GenerationPermit`、`ConversationResult` 等内部契约。供应商请求和 `GatewayResult` 与 `llm_client.py` 放在一起，不建一个包罗所有模型的 `common/` 或 `core/`。

领域层使用 `dataclass`、`Enum`、不可变集合和普通函数。一个业务对象只有实际需要的身份与字段，不为每个 Entity 新建目录。固定案件构建成领域对象前，先做结构校验，再做引用、权限与可解性校验。

### 6.2 表与文件的映射

| ORM 文件 | 表 |
| --- | --- |
| `models/case.py` | `case_template`、`character`、`character_secret`、`scene`、`evidence`、`evidence_dependency`、`lie_rule`、`relationship`、`timeline_event` |
| `models/game.py` | `visitor`、`game_session`、`player_evidence`、`npc_state`、`accusation`、`game_event_log`、`action_request`、`rule_effect` |
| `models/conversation.py` | `conversation`、`conversation_message`、`llm_attempt`、`npc_memory_summary` |

Repository 按一起读取和提交的业务数据分组，不与表一一对应：

- `visitors.py`：令牌摘要查询、访问者行锁、当前会话指针；不设置 HTTP Cookie。
- `cases.py`：将静态表装配成固定 `CaseTemplate`；离线维护路径写入并发布，运行时连接只有静态表读取权限。
- `games.py`：加载和保存 GameSnapshot 的关系行与剩余 JSON，管理请求、事件、效果和冻结指控的持久化；不决定快照应该如何变化。
- `conversations.py`：有界历史查询、生成占位、attempt 条件更新、用量结算、摘要读写；只能按应用层给定范围操作，不授予角色知识。

`GameSnapshot` 是同一数据库版本的领域视图，不是另一份可写的完整 JSON。证据来自 `player_evidence`，NPC 来自 `npc_state`，效果键来自 `rule_effect`；剩余场景、非证据已知信息和草稿放在第 09 篇规定的 `state_json`。保存与恢复均保持唯一权威来源。

## 7. 典型请求如何穿过目录

### 7.1 出示证据

1. `api/routes/conversations.py` 校验请求结构、凭据和请求头，调用 `application/game.py`。
2. Game Engine 校验归属并查询旧幂等结果；新请求在短事务内锁定会话，重新检查幂等、当前入口、版本、生成占位和审讯目标。
3. `domain/state_machine.py` 检查动作权限，`domain/evidence.py` 检查持有与引用，`domain/rules.py` 计算反证、数值、谎言、披露和一次 PROGRESS。
4. Game Engine 比较前后各 NPC 授权投影，调用 Memory 的纯计算同步 epoch；通过 Repositories 同事务保存全部业务效果、来源、摘要失效、固定结果和对话占位。
5. 提交成功后 API 返回 201 和已保存的固定结果；登记的表达任务进入 `application/generation.py`，前端轮询该轮对话。
6. 生成流程加载一致数据，经 `memory.py` 构建受限上下文；短事务复核版本、epoch 和额度，登记 attempt，并在发送前条件抢占 DISPATCHING。
7. 事务外执行 `conversation.py → agents.py → llm_client.py`。候选必须通过结构和内容检查，失败使用本轮固定回复。
8. 新短事务结算用量，复核当前局、NPC、版本、epoch、deadline 和 active attempt，才保存有效表达。迟到只结算可得用量，不覆盖新回复，不再运行规则。

**任何 LLM 等待都发生在数据库事务之外。** 前四步决定游戏结果，后四步只完成表达和记录；模型失败不能撤销已经保存的承认或再次发放证据。

### 7.2 普通聊天、查询与正式指控

| 用例 | 调用路径与区别 |
| --- | --- |
| 普通聊天 | API → Game Engine 受理轮次 → 生成流程；不执行 EVENT、不增加心理值、不推进谎言，表达记录不增加 `state_version` |
| 背包、关系图、时间线 | API → 应用读取 → Repository 一致快照 → Evidence 安全投影；不调用模型、不补跑规则 |
| 恢复存档 | API → Save/Load → 只读一致事务 → 领域不变量校验；读到完整旧版本或完整新版本，不自动派发遗留模型请求 |
| 正式指控 | API → Game Engine 短事务 → 状态与引用校验 → Rule Engine 的 JUDGE → 同事务保存 accusation 与 REVIEW；全程无 LLM |
| 读取复盘 | API → 应用读取冻结结果与获准真相 → 固定复盘投影；不重新评分，不把漏收证据补进背包 |

GET 不承担写清理或生成任务。第 13 篇要求的过期维护由 `main.py` 生命周期启动 `generation.py` 的有界批次清理协程，新写命令也可清理本局过期占位；进程重启后只恢复记录和清理，不自动重发结果未知的调用。首版按单异步进程部署，本地容量与熔断不宣称具备跨实例协调能力。

## 8. 配置、资源和开发顺序

### 8.1 配置与维护入口

`config.py` 统一校验数据库地址、同源地址、模型启用状态、主备路由、超时、token 与调用限额等服务端参数。具体密钥只由装配层传给对应适配器，不把包含全部秘密的 Settings 传入 Agent 或领域对象。玩法阈值和评分权重属于固定案件配置，不能用环境变量随意改变进行中的案件。

`import_case.py` 是离线 CLI 适配入口：读取 JSON，调用 Case Service 和领域发布校验，经维护账号在事务中写入静态表并发布。它不挂到玩家 API，不覆盖已发布版本，不在 FastAPI 启动时自动导入。案件完整路径和无招供路径由同一领域规则执行验证。

根 `.gitignore` 覆盖两个子项目，随工具链加入 `.env`、`.venv/`、`__pycache__/`、pytest/Ruff 缓存、覆盖率、构建输出、日志、测试报告和数据库备份；保留不含秘密的 `.env.example`。后端部署需要随附案件导入源或模板资源时明确打包路径，前端发布只包含 `frontend/` 的构建产物和 `frontend/public/` 的公开资源。

### 8.2 分阶段实现

以下阶段与一人开发路线图的版本一一对应，排期、估时和任务见 [开发路线图](16-development-roadmap.html)。阶段 1 已随 W1 切片完成最小版本。

| 阶段 | 版本 | 建立的主要内容 | 完成标准 |
| --- | --- | --- | --- |
| 1：领域与案件 | v0.1（已完成切片）→ v0.3 | `domain/`、案件定义、领域测试和人工预期 | 固定输入完成取证、分层谎言和三类评分；无招供也存在正确路径 |
| 2：持久化闭环 | v0.2 | ORM、迁移、Repositories、Case、Game、Save/Load | 创建、取证、出示、指控、恢复可原子提交；实库验证锁、约束与幂等 |
| 3：HTTP 与固定回复 | v0.2 → v0.3 | `api/`、匿名凭据、固定 Conversation、API 测试 | 第 10 篇端点闭环；无模型可完整通关，GET 无副作用 |
| 4：一个 NPC 的受限表达 | v0.4 | Memory、Agent Manager、Conversation、Gateway、生成编排 | 最终 messages 知识隔离，超时、未知用量、迟到及显式重试符合契约 |
| 5：完整 MVP | v0.5 → v0.6 | 四 NPC、全部场景证据、三级记忆、前端、E2E | 第 14 篇 P0、不同调查顺序、故障恢复和固定模式全路径通过 |
| 6：表达评测与发布 | v1.0 | 模型题集、长对话、实际延迟和成本记录、UI 美化 | 分别报告程序越权、候选违规和最终可见违规；性能有实测环境 |

一人开发同一时间只推进一个阶段，测试随相应实现加入。阶段 1 不先创建所有 API 和 ORM 文件；阶段 4 不为四个 NPC 复制四套代码。Host/Review 润色、语义摘要、SSE、向量检索和多人能力不进入默认实现清单。

### 8.3 首个工具链的命令约定

以下命令是实现对应文件后的约定，现在不能据此宣称游戏检查通过。后端使用 uv 管理依赖，所有后端命令在 `backend/` 内执行；FastAPI、SQLAlchemy、psycopg 和 Alembic 已在 `backend/pyproject.toml` 中，开发检查用 Ruff、pytest，浏览器阶段再加入第 14 篇所需工具，不增加只重命名这些命令的包装脚本。前端命令见 README。

```bash
cd backend
uv sync --locked
uv run uvicorn backend.main:app --reload --reload-dir src/backend
uv run alembic upgrade head
uv run python -m backend.import_case assets/cases/case_001/v1/case.json
uv run ruff format --check src tests
uv run ruff check src tests
uv run pytest tests/domain -q
uv run pytest tests/application tests/infrastructure/test_llm_client.py -q
uv run pytest tests -m "integration and not api and not performance" -q
uv run pytest tests/api -q
```

README 应记录实际可运行的命令、测试数据库准备与环境变量；E2E、性能和真实模型评测沿用第 14 篇。默认测试禁止外部模型调用，真实数据库或浏览器环境缺失不能伪装成通过。本次交付验收仅针对本文目录、职责和依赖边界的完整性。
