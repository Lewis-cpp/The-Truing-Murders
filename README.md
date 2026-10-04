# The Truing Murders

基于多智能体与状态机的交互式 AI 探案推理解谜平台。
程序负责游戏流程、证据规则和结案判定，LLM 负责授权范围内的角色表达。

## 当前状态

当前已建立设计文档与目录占位。空目录使用零字节 `.gitkeep` 文件纳入 Git，
添加实际文件后可删除该目录的占位文件。尚未实现应用、案件内容、迁移或测试，
也未配置依赖与构建工具；目前没有可运行的启动、格式化、检查或测试命令。

## 目录结构

以下结构依据 [后端开发计划](docs/15-development-plan.md)、
[前端设计](docs/11-frontend-design.md) 和 [测试设计](docs/14-testing.md)。
仅列出目录，省略 `.gitkeep` 文件。

```text
.
├── src/
│   ├── backend/
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
│   └── frontend/
│       ├── router/                      # 页面路由
│       ├── layouts/                     # 游戏主界面布局
│       ├── views/                       # 路由页面
│       ├── components/
│       │   ├── game/                    # 导航与公共游戏界面
│       │   ├── investigation/           # 场景调查与固定结果
│       │   ├── interrogation/           # 审讯对话
│       │   ├── evidence/                # 证据背包与详情
│       │   └── reasoning/               # 关系图、时间线与过程编辑
│       ├── stores/                      # 前端状态
│       ├── api/                         # 公开 API 客户端与类型
│       ├── composables/                 # 回复轮询与图表逻辑
│       └── styles/                      # 主题与样式
├── assets/
│   ├── cases/
│   │   └── case_001/
│   │       └── v1/                      # 首个案件版本的导入资源
│   ├── prompts/                         # 后端角色提示词模板
│   └── frontend/                        # 可公开的图片与字体
├── tests/
│   ├── data/
│   │   ├── cases/                       # 合成测试案件
│   │   ├── expected/                    # 人工独立预期与通关路径
│   │   └── agent/                       # 异常输出与模型评测题集
│   ├── backend/
│   │   ├── domain/                      # 领域行为检查
│   │   ├── application/                 # 应用编排与角色隔离检查
│   │   ├── infrastructure/              # 数据库与模型接入检查
│   │   ├── integration/                 # 事务、并发与恢复检查
│   │   └── api/                         # HTTP 契约检查
│   ├── frontend/                        # 组件与页面状态检查
│   ├── e2e/                             # 浏览器完整流程检查
│   └── agent_eval/                      # 显式启用的真实模型评测
└── docs/                                # 需求、架构与开发计划
```

## 模块边界

- 后端采用 `api / application / domain / infrastructure` 四层模块化单体。
  具体模块文件名和依赖方向见后端开发计划，随实现建立。
- 案件包与提示词仅供后端读取。前端公开资源放在 `assets/frontend/`，
  不能将整个 `assets/` 目录公开托管。
- 自动化检查统一放在 `tests/`；后端按源码层级组织，跨层流程和浏览器检查单列。
- 引入首个工具链时，在本文件补充实际可运行的安装、启动、迁移和检查命令，
  并扩展 `.gitignore` 排除相应缓存与生成输出。

## 设计文档

- [项目范围与 MVP](docs/01-project-scope.md)
- [总体架构](docs/03-architecture-design.md)
- [前端设计](docs/11-frontend-design.md)
- [测试架构与矩阵](docs/14-testing.md)
- [后端目录与开发边界](docs/15-development-plan.md)
- [开发路线图](docs/16-development-roadmap.html)
- [技术栈概览](tech-stack.html)
