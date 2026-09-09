# WebAgent

WebAgent 是一个以 Hermes 为唯一执行引擎的多用户 AI 工作台。用户可以在浏览器中配置模型、发起长对话、上传资料，并让 Hermes 生成 Markdown、HTML、PPT 等文件产物。项目已经移除 OpenClaw 运行链路；“模型”表示 Hermes 实际调用的模型，不是独立 Agent。

## 功能概览

- 多用户登录、会话和权限隔离
- Hermes 长对话与后台任务执行
- OpenAI 兼容模型配置，支持 SenseNova、DeepSeek 以及其他兼容服务
- API Key 加密保存，前端不回显明文
- 文件上传、产物登记、Markdown/HTML 预览与下载
- 运行事件、任务进度、失败原因和产物状态展示
- 本地开发、Windows 启动脚本和 CCI 部署脚本

## 系统结构

浏览器（Next.js，默认 3000 端口） → FastAPI（默认 8010 端口） → PostgreSQL / Redis / Celery → Hermes CLI。
前端只负责选择模型和提交任务；真正的模型请求由后端根据用户配置启动 Hermes 完成。不同用户、不同会话使用各自的模型运行时配置，不会覆盖后台 Hermes 的环境变量。

主要目录：

- `apps/web`：Next.js 前端
- `services/api/app`：FastAPI、数据库模型、Hermes 适配器和任务执行器
- `services/api/alembic`：数据库迁移
- `scripts`：本地及 CCI 启停脚本
- `docs`：公开文档；私密交接文档为 `docs/PROJECT_HANDOVER_PRIVATE.md`，不会提交到 Git

## 环境要求

- Node.js 20+、pnpm 9+
- Python 3.12+
- PostgreSQL 14+
- Redis 6+
- Hermes CLI；本地可通过 `HERMES_COMMAND` 或 `HERMES_BIN` 指定
- Windows PowerShell 或 Linux shell（CCI 使用 Linux）

## 配置

复制示例配置并按环境修改：

```powershell
Copy-Item .env.example .env
Copy-Item services/api/.env.example services/api/.env
```

最小配置项：

```dotenv
WEB_PORT=3000
API_PORT=8010
NEXT_PUBLIC_API_BASE_URL=
API_INTERNAL_BASE_URL=http://127.0.0.1:8010
DATABASE_URL=postgresql+asyncpg://user:password@127.0.0.1:5432/webagent
REDIS_URL=redis://127.0.0.1:6379/0
JWT_SECRET_KEY=请替换为随机长字符串
MODEL_ENCRYPTION_KEY=请替换为32字节密钥
HERMES_COMMAND=hermes
HERMES_WORKDIR=
HERMES_TIMEOUT_SECONDS=1800
ARTIFACT_STORAGE_ROOT=./runtime/artifacts
ARTIFACT_PREVIEW_MAX_BYTES=8388608
ARTIFACT_DISCOVERY_MAX_FILES=1000
```

不要把真实 API Key 写入 Git。生产环境建议使用环境变量或密钥管理服务；数据库中保存的是加密后的 Key，接口和日志只返回掩码。

### SenseNova 配置

SenseNova 使用 OpenAI 兼容接口。模型配置页中填写：

- 提供方：SenseNova（或 OpenAI compatible）
- Base URL：`https://token.sensenova.cn/v1`
- 模型名：`sensenova-6.8-flash-lite`
- API Key：填写你自己的 Key

等价的 Python 调用示例：

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://token.sensenova.cn/v1",
    api_key="YOUR_SENSENOVA_API_KEY",
)

response = client.chat.completions.create(
    model="sensenova-6.8-flash-lite",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

如果本机或 CCI 存在 TLS 证书链问题，可设置自定义 CA bundle：

```powershell
$env:SENSENOVA_CA_BUNDLE="C:\path\to\ca-bundle.pem"
```

也可以在 API 服务的 `.env` 中设置 `SENSENOVA_CA_BUNDLE`。证书文件必须对运行 FastAPI/Celery 的用户可读。可用 `SENSENOVA_REQUEST_TIMEOUT_SECONDS` 调整连接超时；网络问题应先查看模型测试返回的具体错误，不要把不可用状态硬编码成“已连接”。

## 本地启动

安装依赖：

```powershell
pnpm install
cd services/api
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
cd ..\..
```

确认 PostgreSQL、Redis 和 Hermes 已启动后，一键启动：

```powershell
.\scripts\dev-all.ps1
```

访问：

- 前端：http://127.0.0.1:3000
- API：http://127.0.0.1:8010
- OpenAPI：http://127.0.0.1:8010/docs

停止服务：

```powershell
.\scripts\dev-stop.ps1
```

若需要分别启动，可在两个终端执行：

```powershell
pnpm --dir apps/web dev
cd services/api
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8010
```

首次部署或升级数据库时，务必执行 `alembic upgrade head`。本次运行时查询优化对应迁移 `20260904_0014_runtime_query_indexes.py`。

## 模型与 Hermes 运行方式

1. 在“设置 → 模型配置”新增或编辑模型，填写名称、提供方、Base URL 和 API Key。
2. 点击“测试连接”，只有实际请求成功才会显示可用。
3. 在对话框选择模型并发送任务。
4. 后端为该任务生成独立的 Hermes 运行时快照，再调用 Hermes CLI。
5. 任务完成后，产物必须同时满足“已发现、已登记、状态为 ready”才会在产物列表和预览区呈现。

后台直接运行的 Hermes 可以继续使用自己的环境变量。WebAgent 任务通过快照传入用户选择的模型配置，SenseNova 与 DeepSeek 的 Key 相互隔离。

## 文件产物

支持的产物类型包括 Markdown、HTML、图片和演示文稿。生成文件后，Hermes 应将文件写入任务工作区；WebAgent 会进行产物发现、清单登记和内容预览。

- Markdown：显示渲染后的正文，也可下载原文件
- HTML：在隔离预览区展示网页
- 大文件：预览读取受 `ARTIFACT_PREVIEW_MAX_BYTES` 限制，避免一次性加载过多内容
- 文件扫描：单次发现受 `ARTIFACT_DISCOVERY_MAX_FILES` 限制

## 测试与质量检查

前端：

```powershell
pnpm test
pnpm exec tsc --noEmit
pnpm lint
pnpm build
```

后端：

```powershell
cd services/api
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check app
```

长任务排查重点：

- SSE 断线是否按退避策略重连，并在 401/403/404 时停止重连
- 任务事件是否持续增长到异常规模
- 多个产物是否都登记为 ready
- Markdown 和 HTML 是否能在页面预览及下载
- 模型健康检查结果是否与真实请求一致
- 上传、预览和发现文件是否命中大小及数量上限

## CCI 部署

CCI 持久化根目录约定为 `/mnt/afs/tj_share/webagent-cci`，代码仓库位于其下的 `repo/WebAgent`。在 CCI 上同步代码：

```bash
cd /mnt/afs/tj_share/webagent-cci/repo/WebAgent
git pull --ff-only origin main
cd services/api
/mnt/afs/tj_share/webagent-cci/runtime/conda-webagent/bin/python -m alembic upgrade head
cd ../..
WEBAGENT_ROOT=/mnt/afs/tj_share/webagent-cci bash scripts/cci-status.sh
WEBAGENT_ROOT=/mnt/afs/tj_share/webagent-cci bash scripts/cci-app-start.sh
```

启动、查看状态和停止：

```bash
WEBAGENT_ROOT=/mnt/afs/tj_share/webagent-cci bash scripts/cci-app-start.sh
WEBAGENT_ROOT=/mnt/afs/tj_share/webagent-cci bash scripts/cci-status.sh
WEBAGENT_ROOT=/mnt/afs/tj_share/webagent-cci bash scripts/cci-stop.sh
```

CCI 的 `.env`、API Key、JWT 密钥、数据库、Redis、运行时目录和产物目录均属于部署机私有数据，禁止提交到 GitHub。升级前先确认是否有正在运行的 Hermes 任务；如有长任务，先完成或安排维护窗口，再重启 API/Celery。

## 交接资料

- 公开开发说明：本文件
- 本机私密交接：`docs/PROJECT_HANDOVER_PRIVATE.md`
- 数据库迁移：`services/api/alembic/versions`
- Hermes 适配器：`services/api/app/integrations/hermes`
- 任务执行器：`services/api/app/services/agent_run_executor.py`
- 产物发现与登记：`services/api/app/services/artifact_discovery.py`

交接前请检查 `git status`、环境变量、数据库迁移状态和 CCI 进程状态，并确认没有把密钥、运行时产物或本地虚拟环境加入提交。
