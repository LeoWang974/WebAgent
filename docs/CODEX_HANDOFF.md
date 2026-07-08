# Codex Handoff

更新时间：2026-07-08

## 1. 当前开发目标

本阶段目标是把 WebAgent 从前端 mock 原型推进到可联调 FastAPI 后端的 MVP 骨架：

- 前端保留当前 Codex 风格双栏工作台，继续支持 mock 模式可运行。
- 补齐前端 API adapter 契约，为后续真实 FastAPI 接入做准备。
- 初始化 `services/api` FastAPI 后端骨架，包括配置、路由、Pydantic schema、SQLAlchemy model scaffold、Alembic、Redis/Celery scaffold。
- 暂不接真实数据库业务逻辑，后端先用 `app.services.mock_store` 提供可运行的 mock API。
- 暂不继续开发新功能，下一步应先验证后端 Python 环境、启动 API，并做前后端联调。

## 2. 已完成内容

### 前端主页面与设置页，来自本次会话前面的连续开发

已完成内容包括：

- Codex 风格双栏 UI：左侧历史会话、右侧聊天工作区和 artifact 预览面板。
- `/app/settings`、`/app/settings/profile`、`/app/settings/models`、`/app/admin` 在同一个工作台 App Shell 内打开。
- 基础交互：搜索、发送快捷键、会话切换、空状态、窄屏 artifact 抽屉。
- Mock SSE / Agent Run UI。
- Markdown/PPT/图片/数据表格预览组件。
- 中文/英文 i18n、主题、发送快捷键、artifact 面板宽度等界面设置。
- 侧边栏会话删除、置顶/取消置顶。
- 工作区聊天区与产物区比例拖拽。
- 设置页重构为设置导航 + 多 section 布局。
- 模型配置 UI + mock CRUD。
- 个人信息表单 + mock 保存。
- Skill 管理页。
- 数据与上下文设置页：保存历史、保存上传文件、自动压缩上下文、保留天数、最大上下文消息数、危险操作按钮。

### 本轮完成：前端 API adapter 契约补齐

主要文件：

- `apps/web/src/services/adapters/types.ts`
- `apps/web/src/services/adapters/mock-adapter.ts`
- `apps/web/src/services/adapters/fastapi-adapter.ts`
- `apps/web/src/services/api-client.ts`
- `apps/web/src/types/artifact.ts`
- `apps/web/.env.local.example`

核心逻辑：

- `WebAgentApiAdapter` 增加以下能力：
  - `login(input)`
  - `register(input)`
  - `logout()`
  - `getCurrentUser()`
  - `createSession(input)`
  - `updateSession(sessionId, input)`
  - `deleteSession(sessionId)`
  - `listSessions()`
  - `listMessages(sessionId?)`
  - `sendMessage(input)`
  - `listArtifacts(sessionId?)`
  - `getArtifact(artifactId)`
  - `deleteArtifact(artifactId)`
  - `downloadArtifact(artifactId)`
  - `listFiles(sessionId?)`
  - `uploadFile(input)`
  - `createAgentRun(input)`
  - `getAgentRun(runId)`
  - `cancelAgentRun(runId)`
  - `subscribeAgentRun(runId, onEvent)`
  - `listModels()`
  - `listSkills()`
- `fastApiAdapter` 对应路径包括：
  - `POST /api/auth/login`
  - `POST /api/auth/register`
  - `POST /api/auth/logout`
  - `GET /api/auth/me`
  - `GET/POST /api/sessions`
  - `PATCH/DELETE /api/sessions/{session_id}`
  - `GET/POST /api/sessions/{session_id}/messages`
  - `GET /api/sessions/{session_id}/artifacts`
  - `GET /api/sessions/{session_id}/files`
  - `GET /api/messages`
  - `GET /api/artifacts`
  - `GET/DELETE /api/artifacts/{artifact_id}`
  - `GET /api/artifacts/{artifact_id}/download`
  - `GET/POST /api/files`
  - `POST /api/agent-runs`
  - `GET /api/agent-runs/{run_id}`
  - `POST /api/agent-runs/{run_id}/cancel`
  - `GET /api/agent-runs/{run_id}/events`
  - `GET /api/models`
  - `GET /api/skills`
- `apiClient<T>()` 增强：
  - 从 `localStorage.webagent_access_token` 读取 token，自动加 `Authorization: Bearer ...`。
  - `FormData` 请求不强制设置 `Content-Type`。
  - `204` 返回 `undefined`。
  - 非 JSON 响应按 `Blob` 返回，用于 artifact download。
- `FileAsset` 类型加入 `apps/web/src/types/artifact.ts`，用于上传文件和文件列表。

### 本轮完成：FastAPI 后端骨架初始化

主要目录：

- `services/api/app/main.py`
- `services/api/app/core`
- `services/api/app/db`
- `services/api/app/api`
- `services/api/app/schemas`
- `services/api/app/services/mock_store.py`
- `services/api/app/models`
- `services/api/app/workers`
- `services/api/alembic`

核心逻辑：

- `create_app()` 在 `services/api/app/main.py` 创建 FastAPI app，挂载 CORS 和 `api_router`。
- `services/api/app/core/config.py` 使用 `pydantic-settings` 读取：
  - `APP_NAME`
  - `ENVIRONMENT`
  - `API_PREFIX`
  - `BACKEND_CORS_ORIGINS`
  - `DATABASE_URL`
  - `REDIS_URL`
  - `JWT_SECRET_KEY`
  - `JWT_ALGORITHM`
  - `ACCESS_TOKEN_EXPIRE_MINUTES`
  - `SENSENOVA_API_KEY`
  - `SENSENOVA_BASE_URL`
- `services/api/app/api/router.py` 统一注册 route modules：
  - `health`
  - `auth`
  - `sessions`
  - `messages`
  - `artifacts`
  - `files`
  - `agent_runs`
  - `models`
  - `skills`
  - `settings`
- `services/api/app/schemas/base.py` 定义 `ApiModel`，使用 `alias_generator=to_camel`，后端字段 snake_case、响应 JSON camelCase，对齐前端 TS 类型。
- `services/api/app/services/mock_store.py` 是当前后端 mock 数据源，包含 `user`、`sessions`、`messages`、`artifacts`、`files`、`runs`、`models`、`skills`、`data_context_settings`。
- `services/api/app/api/routes/agent_runs.py` 提供 mock SSE：
  - `GET /api/agent-runs/{run_id}/events`
  - 通过 `StreamingResponse(media_type="text/event-stream")` 输出 `agent_run_event`。
- `services/api/app/models/*` 是 SQLAlchemy model scaffold，尚未接入 route repository。
- `services/api/alembic/*` 是 Alembic scaffold，尚未生成具体 migration revision。
- `services/api/app/workers/celery_app.py` 和 `tasks.py` 是 Celery scaffold，当前只有 `agent_runs.mock_run` 占位 task。

## 3. 当前仓库状态

当前分支：

```text
main
```

当前有大量未提交改动，包含本轮改动和之前会话留下的前端 UI/设置/预览相关改动。

`git status --short` 摘要：

```text
 M apps/web/.env.local.example
 M apps/web/src/app/app/admin/page.tsx
 M apps/web/src/components/layout/main-layout.tsx
 M apps/web/src/components/settings/index.ts
 M apps/web/src/components/settings/model-settings.tsx
 M apps/web/src/components/settings/profile-settings.tsx
 M apps/web/src/services/adapters/fastapi-adapter.ts
 M apps/web/src/services/adapters/mock-adapter.ts
 M apps/web/src/services/adapters/types.ts
 M apps/web/src/services/api-client.ts
 M apps/web/src/services/index.ts
 M apps/web/src/services/mock-data.ts
 M apps/web/src/stores/chat-store.ts
 M apps/web/src/stores/index.ts
 M apps/web/src/stores/user-store.ts
 M apps/web/src/styles/globals.css
 M apps/web/src/types/artifact.ts
 M apps/web/src/types/index.ts
 M apps/web/src/types/model.ts
 M apps/web/src/types/skill.ts
 M services/api/README.md
?? apps/web/src/app/icon.svg
?? apps/web/src/components/artifacts/artifact-fullscreen.tsx
?? apps/web/src/components/artifacts/data-table-viewer.tsx
?? apps/web/src/components/artifacts/image-viewer.tsx
?? apps/web/src/components/artifacts/markdown-viewer.tsx
?? apps/web/src/components/artifacts/ppt-viewer.tsx
?? apps/web/src/components/chat/route-session-sync.tsx
?? apps/web/src/components/chat/workspace-state.tsx
?? apps/web/src/components/layout/mobile-sidebar-drawer.tsx
?? apps/web/src/components/layout/theme-effect.tsx
?? apps/web/src/components/settings/data-context-settings.tsx
?? apps/web/src/components/settings/language-settings.tsx
?? apps/web/src/components/settings/settings-overview.tsx
?? apps/web/src/components/settings/skill-settings.tsx
?? apps/web/src/lib/artifact-actions.ts
?? apps/web/src/lib/i18n.ts
?? apps/web/src/lib/status.ts
?? apps/web/src/services/agent-run-sse.ts
?? apps/web/src/services/settings-adapters/
?? apps/web/src/stores/settings-store.ts
?? apps/web/src/types/agent-run.ts
?? apps/web/src/types/settings.ts
?? scripts/api-dev.ps1
?? scripts/api-worker.ps1
?? services/api/.env.example
?? services/api/alembic.ini
?? services/api/alembic/
?? services/api/app/
?? services/api/pyproject.toml
```

`git diff --stat` 只统计已跟踪文件，不包含大量 untracked 新文件：

```text
21 files changed, 994 insertions(+), 83 deletions(-)
```

注意：很多新增文件处于 untracked 状态，`git diff --stat` 没有统计它们。

## 4. 修改文件清单

### 本轮重点修改：前端 adapter 契约

- `apps/web/src/services/adapters/types.ts`
  - 增加 `LoginInput`、`AuthResult`、`UpdateSessionInput`、`CreateAgentRunInput`、`UploadFileInput`、`AgentRunEventHandler`、`AgentRunUnsubscribe`。
  - 扩展 `WebAgentApiAdapter`，覆盖 auth、session、message、artifact、file、agent run、models、skills。
  - 目的：让前端所有核心业务访问都通过统一 adapter 契约。

- `apps/web/src/services/adapters/mock-adapter.ts`
  - 增加内存态 `artifacts`、`files`、`runs`。
  - 实现 `login`、`register`、`logout`、`deleteSession`、`updateSession`、`uploadFile`、`createAgentRun`、`cancelAgentRun`、`subscribeAgentRun` 等。
  - 目的：保持 `NEXT_PUBLIC_API_ADAPTER=mock` 时前端继续可运行。

- `apps/web/src/services/adapters/fastapi-adapter.ts`
  - 实现完整 FastAPI 路径契约。
  - `login`/`register` 成功后写入 `localStorage.webagent_access_token`。
  - `subscribeAgentRun()` 使用 `EventSource` 订阅 `/api/agent-runs/{run_id}/events`。
  - 目的：前端可切换到 `NEXT_PUBLIC_API_ADAPTER=fastapi`。

- `apps/web/src/services/api-client.ts`
  - 添加 token 注入、FormData 处理、204 处理、Blob 下载处理。
  - 目的：适配登录鉴权、文件上传、artifact 下载。

- `apps/web/src/types/artifact.ts`
  - 增加 `FileAsset` 类型。
  - 目的：前端文件上传/文件列表类型契约。

- `apps/web/.env.local.example`
  - 增加注释说明 `NEXT_PUBLIC_API_ADAPTER=fastapi`。
  - 目的：明确 mock/fastapi 切换方式。

### 本轮重点新增：FastAPI 后端骨架

- `services/api/pyproject.toml`
  - 定义 Python 依赖：FastAPI、Uvicorn、SQLAlchemy、Alembic、Redis、Celery、Pydantic Settings、python-jose、passlib、python-multipart 等。
  - 目的：后端依赖清单。

- `services/api/.env.example`
  - 定义本地配置样例。
  - 目的：后端启动前复制为 `.env`。

- `services/api/app/main.py`
  - `create_app()` 创建 FastAPI app。
  - 挂载 CORS 和 `api_router`。

- `services/api/app/core/config.py`
  - `Settings(BaseSettings)` 读取环境变量。
  - `cors_origins` 从逗号分隔字符串生成 list。

- `services/api/app/core/redis.py`
  - 初始化 `redis_client = Redis.from_url(settings.redis_url, decode_responses=True)`。

- `services/api/app/db/base.py`
  - 定义 SQLAlchemy `Base(DeclarativeBase)`。

- `services/api/app/db/session.py`
  - 定义 `engine`、`AsyncSessionLocal`、`get_db()`。

- `services/api/app/api/router.py`
  - 注册所有 API routes。

- `services/api/app/api/routes/health.py`
  - `GET /api/health` 返回 `{"status": "ok"}`。

- `services/api/app/api/routes/auth.py`
  - `POST /api/auth/login`
  - `POST /api/auth/register`
  - `POST /api/auth/logout`
  - `GET /api/auth/me`
  - 当前使用 mock user，不验证密码。

- `services/api/app/api/routes/sessions.py`
  - `GET /api/sessions`
  - `POST /api/sessions`
  - `PATCH /api/sessions/{session_id}`
  - `DELETE /api/sessions/{session_id}`
  - `GET /api/sessions/{session_id}/messages`
  - `POST /api/sessions/{session_id}/messages`
  - `GET /api/sessions/{session_id}/artifacts`
  - `GET /api/sessions/{session_id}/files`
  - 当前基于 `mock_store.sessions/messages/artifacts/files`。

- `services/api/app/api/routes/messages.py`
  - `GET /api/messages`。

- `services/api/app/api/routes/artifacts.py`
  - `GET /api/artifacts`
  - `GET /api/artifacts/{artifact_id}`
  - `DELETE /api/artifacts/{artifact_id}`
  - `GET /api/artifacts/{artifact_id}/download`

- `services/api/app/api/routes/files.py`
  - `GET /api/files`
  - `POST /api/files`
  - 使用 `UploadFile` 和 `Form` 接收文件及可选 `session_id`。

- `services/api/app/api/routes/agent_runs.py`
  - `POST /api/agent-runs`
  - `GET /api/agent-runs/{run_id}`
  - `POST /api/agent-runs/{run_id}/cancel`
  - `GET /api/agent-runs/{run_id}/events`
  - SSE 当前发送固定 mock steps：queued、running、tool_calling、rendering、completed。

- `services/api/app/api/routes/models.py`
  - `GET /api/models`。

- `services/api/app/api/routes/skills.py`
  - `GET /api/skills`。

- `services/api/app/api/routes/settings.py`
  - `PUT /api/settings/profile`
  - `GET /api/settings/data-context`
  - `PUT /api/settings/data-context`
  - `POST /api/settings/models`
  - `PUT /api/settings/models/{model_id}`
  - `DELETE /api/settings/models/{model_id}`
  - `POST /api/settings/models/default`
  - `POST /api/settings/models/{model_id}/test`
  - `POST /api/settings/skills/default`
  - `POST /api/settings/skills/{skill_key}/toggle`
  - `POST /api/settings/skills/{skill_key}/version`

- `services/api/app/schemas/*.py`
  - Pydantic schema 层。
  - `ApiModel` 使用 camelCase alias 输出，兼容前端 TS。

- `services/api/app/services/mock_store.py`
  - 后端 mock 数据源。
  - 注意：已改成 ASCII 英文 mock 文案，避免 Windows PowerShell 编码导致字符串损坏。

- `services/api/app/models/*.py`
  - SQLAlchemy model scaffold。
  - 尚未通过 Alembic 生成 migration。

- `services/api/alembic.ini`
  - Alembic 配置。

- `services/api/alembic/env.py`
  - 使用 `settings.database_url`，导入 `app.models` 让 metadata 可见。

- `services/api/app/workers/celery_app.py`
  - Celery app 初始化，broker/backend 使用 Redis。

- `services/api/app/workers/tasks.py`
  - `mock_agent_run(run_id)` 占位 task。

- `services/api/README.md`
  - 更新本地 setup、API 启动、worker 启动说明。

- `scripts/api-dev.ps1`
  - 进入 `services/api`，自动复制 `.env.example` 为 `.env`，运行 `uvicorn app.main:app --reload --port 8000`。

- `scripts/api-worker.ps1`
  - 进入 `services/api`，运行 Celery worker。

### 此前会话中已产生但仍未提交的重要前端文件

- `apps/web/src/components/settings/settings-overview.tsx`
  - 设置页导航 + 多 section 布局。

- `apps/web/src/components/settings/data-context-settings.tsx`
  - 数据与上下文设置 UI。

- `apps/web/src/stores/settings-store.ts`
  - Zustand store，调用 `settingsApi.getDataContextSettings()` 和 `settingsApi.updateDataContextSettings()`。

- `apps/web/src/services/settings-adapters/*`
  - 设置专用 adapter：mock/fastapi/types/index。
  - 注意：它和 `services/adapters/*` 是两套 adapter；后续可考虑合并，但当前不要贸然大改。

- `apps/web/src/components/settings/model-settings.tsx`
  - 模型配置 UI 和 mock CRUD。

- `apps/web/src/components/settings/profile-settings.tsx`
  - 个人信息表单和 mock 保存。

- `apps/web/src/components/settings/skill-settings.tsx`
  - Skill 管理 UI。

- `apps/web/src/lib/i18n.ts`
  - 中英文翻译字典。

- `apps/web/src/components/artifacts/*`
  - Markdown/PPT/图片/数据表格 artifact 预览相关组件。

- `apps/web/src/components/layout/mobile-sidebar-drawer.tsx`
  - 移动端侧边栏抽屉。

- `apps/web/src/components/layout/theme-effect.tsx`
  - 根据 UI store 应用主题。

- `apps/web/src/components/chat/workspace-state.tsx`
  - 工作区状态组件。

- `apps/web/src/services/agent-run-sse.ts`
  - 前端 mock SSE 逻辑。

## 5. 关键约束

- 不要随意回滚未提交改动；当前工作区有大量前序会话成果，全部视为用户已有工作。
- 不要用 `git reset --hard`、`git checkout --` 等破坏性命令。
- 当前前端必须继续支持 `NEXT_PUBLIC_API_ADAPTER=mock`，不能为了 FastAPI 联调破坏 mock 模式。
- FastAPI adapter 路径应保持和当前后端 route 一致，除非同时更新前后端和本文档。
- 后端 schema 输出需要保持 camelCase，因为前端 TS 类型使用 camelCase，例如 `sessionId`、`updatedAt`、`isDefault`。
- 后端内部 Python 字段可用 snake_case，通过 `ApiModel` alias 转换。
- 当前后端 route 是 mock store，不要误以为已经接 PostgreSQL。
- 当前 `services/api/app/models/*` 只是 SQLAlchemy model scaffold，尚未生成 Alembic revision。
- 当前 Python 环境不可用，不能假设后端已通过启动验证。
- 本机 PowerShell 对非 ASCII 写入曾出现乱码，后端新增 Python mock 文案尽量使用 ASCII，或确保编辑器/终端 UTF-8 配置正确。
- 文件编辑继续优先使用 `apply_patch`。
- 前端 UI 设计要继续保持当前 Codex 风格：双栏、紧凑 sidebar、对话气泡、artifact 预览面板。

## 6. 已运行命令

### 成功命令

```powershell
pnpm --filter web build
```

结果：成功。最近一次输出摘要：

```text
▲ Next.js 15.5.20
Creating an optimized production build ...
✓ Compiled successfully
Linting and checking validity of types ...
✓ Generating static pages (12/12)
Route (app)
○ /app
○ /app/admin
○ /app/settings
○ /app/settings/models
○ /app/settings/profile
ƒ /app/chat/[sessionId]
```

此前也运行过：

```powershell
Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }; Start-Sleep -Seconds 1; Remove-Item -Recurse -Force D:\gitWorkSpace\WebAgent\apps\web\.next -ErrorAction SilentlyContinue; Start-Process -FilePath powershell -ArgumentList '-NoProfile','-Command','cd D:\gitWorkSpace\WebAgent; pnpm --filter web dev' -WindowStyle Hidden; Start-Sleep -Seconds 8; try { (Invoke-WebRequest -Uri http://localhost:3000/app/settings -UseBasicParsing).StatusCode } catch { $_.Exception.Message }
```

结果：

```text
200
```

此前用浏览器自动化检查过 `/app/settings`：

```text
hasDataSection: true
hasDangerZone: true
consoleErrors: []
url: http://localhost:3000/app/settings
```

### 失败命令

```powershell
python -m compileall services\api\app
```

结果：失败，无 Python 语法输出。

进一步检查：

```powershell
python -m compileall -q services\api\app; if ($LASTEXITCODE -ne 0) { Write-Output "compileall_exit=$LASTEXITCODE" }
```

结果：

```text
compileall_exit=9009
```

含义：Windows 找不到可用 Python 命令，9009 是命令不可用/无法执行，不是后端代码语法报错。

检查 Python：

```powershell
python --version
py --version
where.exe python
where.exe py
where.exe uvicorn
```

结果摘要：

```text
python --version 失败
py : The term 'py' is not recognized...
where.exe python -> C:\Users\zhuchangbiaozhu_xyl\AppData\Local\Microsoft\WindowsApps\python.exe
where.exe py -> INFO: Could not find files for the given pattern(s).
where.exe uvicorn -> INFO: Could not find files for the given pattern(s).
```

怀疑原因：当前机器只有 Microsoft Store 的 Python alias 占位，没有真实 Python 3.11+ 和 uvicorn。

## 7. 当前问题

1. 后端未完成实际启动验证。
   - 原因：本机 `python`/`py`/`uvicorn` 不可用。
   - 失败码：`compileall_exit=9009`。
   - 需要先安装 Python 3.11+，并确保 PATH 指向真实 Python，而不是 WindowsApps alias。

2. 后端 route 当前使用 `mock_store`。
   - PostgreSQL、Redis、SQLAlchemy repository、真实 auth、JWT 校验都还没有接入业务路径。
   - `services/api/app/db/session.py` 和 model scaffold 已有，但 routes 未使用 `get_db()`。

3. Alembic 尚未生成第一版 migration。
   - 已有 `alembic.ini`、`alembic/env.py`、`script.py.mako`。
   - 尚未运行 `alembic revision --autogenerate -m "init schema"`。

4. Settings adapter 与 WebAgent adapter 目前是两套。
   - `apps/web/src/services/settings-adapters/*`：设置页专用。
   - `apps/web/src/services/adapters/*`：WebAgent 通用 adapter。
   - 当前能工作，但后续可考虑统一；不要在未测试前大规模合并。

5. `git status` 中有大量 untracked 文件。
   - 很多是此前功能开发成果，不是本轮新增。
   - 新窗口不要误删。

6. PowerShell 显示/写入非 ASCII 曾导致 Python 文件乱码。
   - 已把后端 mock 文案改为 ASCII。
   - 前端 i18n 本身包含中文，已能通过 Next build。

## 8. 下一步建议

建议新窗口按以下顺序继续：

1. 只做环境验证，不开发新业务。
   - 安装/确认 Python 3.11+。
   - 确认 `python --version` 或 `py --version` 可用。
   - 进入 `services/api` 创建 venv。

2. 安装后端依赖。

   ```powershell
   cd D:\gitWorkSpace\WebAgent\services\api
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -U pip
   pip install -e ".[dev]"
   Copy-Item .env.example .env
   ```

3. 启动基础依赖。

   ```powershell
   cd D:\gitWorkSpace\WebAgent
   docker compose -f infra\docker-compose.yml up -d
   ```

4. 验证后端可启动。

   ```powershell
   cd D:\gitWorkSpace\WebAgent\services\api
   .\.venv\Scripts\Activate.ps1
   uvicorn app.main:app --reload --port 8000
   ```

   另开 PowerShell：

   ```powershell
   Invoke-WebRequest -Uri http://localhost:8000/api/health -UseBasicParsing
   ```

5. 验证 mock API 契约。

   ```powershell
   Invoke-WebRequest -Uri http://localhost:8000/api/auth/me -UseBasicParsing
   Invoke-WebRequest -Uri http://localhost:8000/api/sessions -UseBasicParsing
   Invoke-WebRequest -Uri http://localhost:8000/api/models -UseBasicParsing
   Invoke-WebRequest -Uri http://localhost:8000/api/skills -UseBasicParsing
   ```

6. 前端切 FastAPI adapter 做联调。

   在 `apps/web/.env.local` 中设置：

   ```text
   NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
   NEXT_PUBLIC_API_ADAPTER=fastapi
   ```

   然后：

   ```powershell
   cd D:\gitWorkSpace\WebAgent
   pnpm --filter web dev
   ```

7. 检查页面：
   - `http://localhost:3000/app`
   - `http://localhost:3000/app/settings`
   - `http://localhost:3000/app/settings/profile`
   - `http://localhost:3000/app/settings/models`

8. 后端可启动后再生成 Alembic migration。

   ```powershell
   cd D:\gitWorkSpace\WebAgent\services\api
   .\.venv\Scripts\Activate.ps1
   alembic revision --autogenerate -m "init schema"
   alembic upgrade head
   ```

9. 迁移完成后，再规划 repository 层替换 `mock_store`。
   - 优先顺序：auth/user/settings -> sessions/messages -> artifacts/files -> agent_runs/SSE。

## 9. 验收方式

### 前端验收

运行：

```powershell
cd D:\gitWorkSpace\WebAgent
pnpm --filter web build
```

应通过，无 TypeScript 或 Next build error。

mock 模式页面检查：

```text
NEXT_PUBLIC_API_ADAPTER=mock
```

访问：

- `http://localhost:3000/app`
- `http://localhost:3000/app/settings`
- `http://localhost:3000/app/settings/profile`
- `http://localhost:3000/app/settings/models`

应检查：

- 左侧历史会话显示正常。
- 会话切换、删除、置顶/取消置顶可用。
- 输入框可发送 mock 消息。
- artifact 面板可显示已有预览。
- 设置页可切换语言/主题。
- 模型配置可 add/edit/delete/test/default。
- 个人信息可保存。
- Skill 管理可启用/禁用、设默认、版本操作。
- 数据与上下文设置可修改并保存。

FastAPI 模式页面检查：

```text
NEXT_PUBLIC_API_ADAPTER=fastapi
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

前提：后端 `/api/health` 返回 200。

访问：

- `http://localhost:3000/app`
- `http://localhost:3000/app/settings`

应检查：

- 前端不报 `API request failed`。
- sessions/models/skills 能从后端 mock API 加载。
- 设置页 profile/data-context/model/skill 操作能调用后端对应 endpoint。

### 后端验收

环境检查：

```powershell
python --version
uvicorn --version
```

启动 API：

```powershell
cd D:\gitWorkSpace\WebAgent\services\api
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

接口检查：

```powershell
Invoke-WebRequest -Uri http://localhost:8000/api/health -UseBasicParsing
Invoke-WebRequest -Uri http://localhost:8000/api/auth/me -UseBasicParsing
Invoke-WebRequest -Uri http://localhost:8000/api/sessions -UseBasicParsing
Invoke-WebRequest -Uri http://localhost:8000/api/models -UseBasicParsing
Invoke-WebRequest -Uri http://localhost:8000/api/skills -UseBasicParsing
```

期望：

- `/api/health` 返回 `{"status":"ok"}`。
- `/api/auth/me` 返回 user JSON，字段应为 camelCase，如 `avatarUrl`。
- `/api/sessions` 返回数组，字段应为 camelCase，如 `updatedAt`。
- `/api/models` 返回数组，字段应为 camelCase，如 `isDefault`。
- `/api/skills` 返回数组。

SSE 检查：

1. 先创建 run：

   ```powershell
   Invoke-WebRequest -Uri http://localhost:8000/api/agent-runs -Method POST -ContentType "application/json" -Body '{"sessionId":"session_demo","content":"test"}' -UseBasicParsing
   ```

2. 用浏览器或支持 SSE 的工具访问：

   ```text
   http://localhost:8000/api/agent-runs/{run_id}/events
   ```

期望事件包含：

```text
event: agent_run_event
data: {"runId": "...", "status": "queued", ...}
...
status: "completed"
```

### 数据库/Alembic 验收

在 Python 环境可用且 PostgreSQL 启动后：

```powershell
cd D:\gitWorkSpace\WebAgent
docker compose -f infra\docker-compose.yml up -d

cd D:\gitWorkSpace\WebAgent\services\api
.\.venv\Scripts\Activate.ps1
alembic revision --autogenerate -m "init schema"
alembic upgrade head
```

期望：

- `services/api/alembic/versions/*.py` 生成 migration。
- `alembic upgrade head` 成功。

## 新窗口启动提示词

请在新窗口使用下面的提示词：

```text
请先阅读 D:\gitWorkSpace\WebAgent\docs\CODEX_HANDOFF.md，不要重做已有功能，不要回滚未提交改动。当前任务是继续 WebAgent 项目交接后的下一步：先验证并修复 FastAPI 后端骨架的本地启动流程，然后把前端切到 NEXT_PUBLIC_API_ADAPTER=fastapi 做最小联调。请严格按交接文档的“下一步建议”和“验收方式”执行，优先处理 Python 环境、后端 /api/health、/api/auth/me、/api/sessions、/api/models、/api/skills，再做前端页面联调。除非为修复启动/联调问题，不要开发新功能或做大规模重构。
```
