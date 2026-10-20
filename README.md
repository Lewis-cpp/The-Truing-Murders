# The Truing Murders

基于多智能体与状态机的交互式 AI 探案推理解谜平台。
程序负责游戏流程、证据规则和结案判定，LLM 负责授权范围内的角色表达。

## 当前状态

v0.2 把《停电之夜》切片变成了可保存的网页游戏：浏览器开局 → 调查取证 → 审讯并出示证据 →
刷新或重启后端后继续 → 正式指控 → 固定复盘。所有规则和对白仍是固定内容，
没有 Agent、模型 SDK 或模型调用。进度保存在 PostgreSQL，每次操作在一个事务内提交，
数据库失败时页面不会显示保存成功。重开会创建独立的新局，旧局保留为只读。
交付范围与限制见 [v0.2 交付记录](docs/18-v0.2-delivery.md)。

切片 `2-slice` 让审讯需要判断：追问预设话题会把回答记为未核验证词，可以用证词和证据指出矛盾；
出示与当前谎言无关的材料或指错矛盾会让角色更戒备，连续两次后角色回避，直到结束审讯。
是否成立都由规则表判定，界面不显示压力和信任数值。指控候选也换成了更像真相的干扰项。

W1 的离线命令行切片继续保留：1 场景、1 NPC、3 条证据、1 条单层谎言、结构化指控、
三类判定与固定复盘，进度只在内存，不需要数据库。

同案的 [完整案件草稿](backend/assets/cases/case_001/v1/full-case-draft.md) 已列出真相、知识权限、
4 NPC／4 场景／12 条证据／3 条谎言链与评分；全案尚未实现，细节待人工审阅。
可执行配置为 [W1 案件切片](backend/assets/cases/case_001/v1/slice.json)。

网页链路：Vue 页面 → Vite 同源代理 → FastAPI `/api/v1` → PostgreSQL 18。

仓库分为两个独立子项目：`backend/`（Python、FastAPI、数据库）和 `frontend/`（Vue、Vite）。
各自带依赖、锁文件和命令，以下命令均在对应子目录内执行。项目按一人独立开发安排，
排期见 [开发路线图](docs/16-development-roadmap.html)。

## 先玩第一周切片

首次准备 Python 依赖，然后启动。CLI 不需要 `.env`、数据库、Node.js 或模型密钥。
首次安装可能下载依赖；安装完成后，运行和 W1 测试均可离线进行。

```bash
cd backend
uv sync --locked
uv run --offline truing-play
```

进入游戏后输入 `look` 看调查点，`help` 看操作。以下是一条调查与审讯路径，
你也可以先调查 A02，或完全跳过审讯后指控：

```text
look
inspect A01
inspect A02
inspect A03
bag
talk NPC01
ask 停电时你在哪里？
topics
topic Q01
contradict K03 E03
present E01
present E03
back
accuse
submit
```

`submit` 会依次询问凶手、凶器、动机、过程步骤、引用证据、步骤证据关联和解释。
候选均在 `accuse` 中列出，过程编号按顺序用逗号分隔，关联使用 `步骤编号:证据编号`。
引用与解释可留空，解释不计分；仅持有证据不自动取得证据关联分。
填写中输入 `/cancel` 可取消，`back` 可返回调查。
只有最终输入 `确认` 才正式结案，之后不能修改本局。`review` 重读复盘，`quit` 退出。

错误答案正常结案；无效编号、未持有的引用、非法阶段会拒绝且不改变状态。
普通问题只取得当前固定说法，不解析自由文本、不加压、不发放证据。
`topic` 追问预设话题，回答记为该角色的未核验证词；`contradict` 用已记录的证词和持有的证据指出矛盾，
成立时首次加压，但不直接击破谎言。出示无关证据或指错矛盾会让角色更戒备，
连续两次后角色回避，`back` 结束审讯再进入即可恢复。
证词标为未经核验，NPC 只承认已获准的那一层信息。

W1 检查不需要启动数据库，在 `backend/` 内执行：

```bash
uv run --offline ruff format --check src tests
uv run --offline ruff check src tests
uv run --offline pytest -q tests/domain tests/application tests/test_cli.py
```

静态评分样例在 `backend/tests/data/expected/week_one_verdicts.json`，与被测评分函数独立编写；
覆盖三结局、75分无证据猜测、30／85分边界、错误凶手覆盖高分。
另检查取证依赖、阻断循环、数值上下界、六种出示顺序、知识投影、重复收益、
非法动作、结案冻结和实际终端交互。CLI 交互测试禁止套接字连接。
这些预期尚待真人复核，不冒充人工验收结果。

`.github/workflows/ci.yml` 分三个任务：后端离线任务运行 Ruff 和上述离线检查；
数据库任务启动与 `compose.yaml` 同一摘要的 PostgreSQL 18 服务，运行完整 pytest；
前端运行格式、类型、lint、测试和构建。CI 不使用模型密钥。
交付范围与验证记录见 [W1 交付记录](docs/17-week-one-delivery.md)。

## 开发环境

采用**数据库用 Docker、前后端本机运行**的方式。Docker 不是架构上的硬性要求，
但本仓库的标准启动流程使用 Compose 管理 PostgreSQL，不需要另装本机数据库。
不需要 Redis、消息队列、向量数据库或本地大模型；当前启动与测试不调用模型 API，
不需要 API 密钥。

| 工具 | 本项目基线 | 用途 |
| --- | --- | --- |
| Python | 3.12，见 `backend/.python-version` | FastAPI、SQLAlchemy、Alembic |
| uv | 当前验证为 0.12.23 | 安装 Python 依赖，创建项目内 `.venv` |
| Node.js / npm | Node.js 24，见 `frontend/.nvmrc`；本机 npm 11 | Vue 3、TypeScript、Vite |
| Docker / Compose | 支持 `docker compose up --wait` | 启动独立数据库容器 |
| PostgreSQL | 18；当前固定镜像为 18.6 | 开发库 `truing`、测试库 `truing_test` |

Python 和前端的具体依赖版本分别固定在 `backend/uv.lock` 和 `frontend/package-lock.json`。
前端已安装设计中使用的 Element Plus、ECharts、Pinia、Vue Router；页面与状态模块随业务开发添加。
数据库镜像使用摘要固定，升级补丁版本时需要显式更新 `backend/compose.yaml` 中的摘要并重新验证。

本机已有 Python、Node.js 和 Docker，本次新增的 uv 位于 `~/.local/bin/uv`。
其他机器可参考 [uv 官方安装说明](https://docs.astral.sh/uv/getting-started/installation/)。
Node.js 版本要求参见 [Vite 官方文档](https://vite.dev/guide/)。
PostgreSQL 18 的持久卷挂载到 `/var/lib/postgresql`，遵循
[官方镜像说明](https://hub.docker.com/_/postgres)，不沿用旧版本的挂载目录。

### 首次安装

只在首次创建配置时复制 `.env`，不要覆盖已有配置。`.env` 只供后端和数据库使用，放在 `backend/` 内。

```bash
cd backend
cp .env.example .env
uv sync --locked
docker compose up -d --wait
uv run alembic upgrade head
uv run python -m backend.import_case assets/cases/case_001/v1/slice.json

cd ../frontend
npm ci
```

`import_case` 是离线发布步骤：校验案件文件，写入静态定义表，确认数据库能还原出同一份定义后发布。
同一版本重复导入内容一致时不做修改；已发布版本内容不同会被拒绝，修订必须换版本号。
后端启动时不会自动导入案件。

`backend/.env.example` 中是仅限本机开发的示例数据库账号，不含模型密钥。
数据库端口只绑定 `127.0.0.1`，开发账号具有数据库管理权限；正式部署需要单独配置运行与维护权限。
项目数据库使用独立 Compose 项目和命名卷，不复用其他项目的 MySQL 或 Redis。
`backend/assets/database/init.sql` 仅在数据卷首次初始化时建立 `truing_test`。

### 日常启动与停止

终端一在 `backend/` 内启动数据库和后端，修改后端文件后自动重载：

```bash
cd backend
docker compose up -d --wait
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir src/backend
```

终端二在 `frontend/` 内启动前端，修改页面后热更新：

```bash
cd frontend
npm run dev
```

- 游戏页面：[http://127.0.0.1:5173](http://127.0.0.1:5173)。
- API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。
- `GET /api/v1/health`：进程存活检查，不依赖数据库。
- `GET /api/v1/ready`：真实执行数据库查询，成功返回 200，连接失败返回 503。

前端通过 `/api/v1` 代理访问本机 8000 端口，无需配置跨域通配符。
后端用 HttpOnly 匿名 Cookie 识别访问者，写请求校验 `Origin`（默认允许 5173 和 4173 端口的
`127.0.0.1` 与 `localhost`，可用 `ALLOWED_ORIGINS` 环境变量覆盖）。
前端静态资源仅来自 `frontend/public/`，案件和提示词只在 `backend/assets/`，不对外提供。
当前所有服务均只绑定本机地址，适用于本机开发。

前后端分别按 `Ctrl+C` 停止。在 `backend/` 内停止数据库并保留数据：

```bash
docker compose stop
```

需要移除本项目容器及网络时执行 `docker compose down`，命名卷仍保留。
不要在保留存档时加 `-v`，该参数会删除本项目数据库卷。
容器没有配置开机自启，重启电脑后按上述步骤启动即可。

### 检查与测试

先启动数据库，再分别在两个子目录内执行：

```bash
cd backend
uv run ruff format --check src tests
uv run ruff check src tests
uv run pytest -q
uv run alembic check

cd ../frontend
npm run format:check
npm run typecheck
npm run lint
npm test
npm run build
```

后端检查在真实 PostgreSQL 18 上验证：迁移可升级、可回退且与模型一致；复合外键、唯一效果和唯一结案；
写入证据后注入故障整体回滚；同键重发、同键异载荷、跨访客访问、过期版本和并发提交；
API 完整通关并在重启后续玩；追问、指出矛盾、回避和不兼容旧存档的处理；迁移带数据往返不丢失追问证词。
前端检查验证写请求协议、断线后查询原请求、保存失败不显示成功、用同一键重试，
以及追问、指出矛盾、回避提示和旧存档进入大厅。数据库缺失时集成检查直接失败，不跳过。
测试通过 `TEST_DATABASE_URL` 使用独立库，要求数据库名以 `_test` 结尾，且不能与开发库相同；
测试会重建该库的表结构。

pytest 禁止自动加载宿主机插件，避免本机 ROS 的 `PYTHONPATH` 干扰；
未来引入异步或浏览器插件时需显式通过 `-p` 启用。
普通检查不使用真实模型；真实模型评测将在对应阶段实现后单独启用。

自动格式化命令：

```bash
cd backend
uv run ruff format src tests

cd ../frontend
npm run format
```

构建产物位于 `frontend/dist/`，不纳入 Git。
`npm run preview` 可在本机 4173 端口预览构建，后端仍需运行。
这些命令用于开发验证，尚未配置正式部署。

### 数据库迁移

Alembic 已连接 `DATABASE_URL`，模型统一从
`backend/src/backend/infrastructure/database/models/__init__.py` 的 `Base.metadata` 注册。
首个迁移 `0001` 只建切片用到的 15 张表：案件版本、人物、私有知识、场景、证据与前置依赖、谎言层，
以及访问者、游戏会话、已持有证据、NPC 状态、幂等请求、事件日志、一次性效果和正式指控。
对话、模型调用、关系图和时间线的表随后续版本加入。修改模型后，可在 `backend/` 内生成和执行迁移：

```bash
uv run alembic revision --autogenerate -m "Add case tables"
uv run alembic upgrade head
```

自动生成的迁移必须检查约束、索引和数据变更，再执行。
迁移文件保存在 `backend/src/backend/infrastructure/database/migrations/versions/`。

迁移 `0002` 为追问证词和回避增加字段。已有开发库升级后，需要导入新版切片：

```bash
uv run alembic upgrade head
uv run python -m backend.import_case assets/cases/case_001/v1/slice.json
```

规则执行版本升为 `w1-slice-2` 后，旧的 `1-slice` 存档原样保留，但不能继续。
页面会提示存档无法读取并显示案件列表；玩家确认后，新局取代它成为当前存档。

### 常见问题

- 找不到 `uv`：将 `~/.local/bin` 加入当前终端的 `PATH`，或用 `~/.local/bin/uv` 执行。
- uv 提示无法硬链接：缓存与仓库在不同分区时会自动复制，不影响运行；可设置 `UV_LINK_MODE=copy`。
- 数据库端口占用：同时修改 `backend/.env` 的 `POSTGRES_PORT`、`DATABASE_URL` 和 `TEST_DATABASE_URL` 中的端口，再重建本项目容器。
- 前端 5173 端口被占用：开发服务会明确退出；可用 `npm run dev -- --port 5174` 指定其他端口。
- 后端 8000 端口被占用：启动时修改 `--port`，并同步修改 `frontend/vite.config.ts` 的代理地址。
- 修改数据库账号后无法连接：镜像中的初始化变量只对空卷生效，已有卷的账号不会随 `backend/.env` 自动更改。
- 页面显示连接失败：在 `backend/` 内检查 `docker compose ps`、`docker compose logs db` 和后端终端，然后点击“重新检查”。
- 已有开发卷但缺少测试库：在 `backend/` 内执行 `docker compose exec db sh -c 'createdb -U "$POSTGRES_USER" truing_test'`，不必删除开发数据。

## 目录结构

以下结构依据 [后端开发计划](docs/15-development-plan.md)、
[前端设计](docs/11-frontend-design.md) 和 [测试设计](docs/14-testing.md)。
仅列出主要模块目录，省略入口、工具配置和 `.gitkeep` 文件。
空目录暂用零字节 `.gitkeep` 纳入 Git，添加实际文件后移除对应占位。

```text
.
├── backend/                             # Python 子项目：pyproject.toml、uv.lock、alembic.ini、compose.yaml
│   ├── src/backend/
│   │   ├── api/                         # HTTP 输入、响应与错误适配
│   │   │   ├── routes/                  # 按业务资源组织路由
│   │   │   └── schemas/                 # 公开请求与响应模型
│   │   ├── application/                 # 用例、事务、生成与记忆编排
│   │   ├── domain/                      # 状态机、证据、规则与领域模型
│   │   └── infrastructure/              # 数据库与 LLM 接入
│   │       └── database/
│   │           ├── models/              # 数据表映射
│   │           ├── repositories/        # 数据读取与保存
│   │           └── migrations/
│   │               └── versions/        # 数据库迁移历史
│   ├── assets/                          # 仅后端读取的资源
│   │   ├── database/                    # 本地数据库初始化资源
│   │   ├── cases/
│   │   │   └── case_001/
│   │   │       └── v1/                  # 首个案件版本的导入资源
│   │   └── prompts/                     # 后端角色提示词模板
│   └── tests/
│       ├── data/
│       │   ├── cases/                   # 合成测试案件
│       │   ├── expected/                # 人工独立预期与通关路径
│       │   └── agent/                   # 异常输出与模型评测题集
│       ├── domain/                      # 领域行为检查
│       ├── application/                 # 应用编排与角色隔离检查
│       ├── infrastructure/              # 数据库与模型接入检查
│       ├── integration/                 # 事务、并发与恢复检查
│       ├── api/                         # HTTP 契约检查
│       ├── e2e/                         # 浏览器完整流程检查
│       └── agent_eval/                  # 显式启用的真实模型评测
├── frontend/                            # Node 子项目：package.json、Vite、TS、ESLint、Prettier
│   ├── src/
│   │   ├── router/                      # 页面路由
│   │   ├── layouts/                     # 游戏主界面布局
│   │   ├── views/                       # 路由页面
│   │   ├── components/
│   │   │   ├── game/                    # 导航与公共游戏界面
│   │   │   ├── investigation/           # 场景调查与固定结果
│   │   │   ├── interrogation/           # 审讯对话
│   │   │   ├── evidence/                # 证据背包与详情
│   │   │   └── reasoning/               # 关系图、时间线与过程编辑
│   │   ├── stores/                      # 前端状态
│   │   ├── api/                         # 公开 API 客户端与类型
│   │   ├── composables/                 # 回复轮询与图表逻辑
│   │   └── styles/                      # 主题与样式
│   ├── public/                          # 可公开的图片与字体
│   └── tests/                           # 组件与页面状态检查
└── docs/                                # 需求、架构与开发计划
```

## 模块边界

- 后端采用 `api / application / domain / infrastructure` 四层模块化单体。
  具体模块文件名和依赖方向见后端开发计划，随实现建立。
- 前后端是两个独立子项目，互不读取对方目录；前端只通过 `/api` 访问后端。
- 案件包与提示词只放在 `backend/assets/`，仅供后端读取。前端公开资源放在 `frontend/public/`。
- 自动化检查放在各子项目的 `tests/`；后端按源码层级组织，跨层流程和浏览器检查单列。
- 工具配置随子项目放置，根目录只留文档、CI 和 `.gitignore`。Python 源码采用 `src` 包布局。
  `.gitignore` 排除本地配置、依赖、缓存、构建、测试报告和数据库备份。

## 设计文档

- [项目范围与 MVP](docs/01-project-scope.md)
- [总体架构](docs/03-architecture-design.md)
- [前端设计](docs/11-frontend-design.md)
- [测试架构与矩阵](docs/14-testing.md)
- [后端目录与开发边界](docs/15-development-plan.md)
- [开发路线图（一人开发）](docs/16-development-roadmap.html)
- [技术栈概览](tech-stack.html)
