# crawler_center_scrapy

基于 **FastAPI + Scrapy** 的聚合爬虫服务，提供统一 HTTP API，用于抓取并标准化以下站点的用户公开数据；其中蓝桥接口支持基于账号密码登录后拉取个人做题统计。

- LeetCode（已实现）
- 洛谷 Luogu（已实现）
- 蓝桥 Lanqiao（已实现）

## 目录

- [项目特点](#项目特点)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [接口总览](#接口总览)
- [请求示例](#请求示例)
- [配置说明](#配置说明)
- [可观测性 / 链路追踪](#可观测性--链路追踪)
- [代理池（内部接口）](#代理池内部接口)
- [错误响应与错误码](#错误响应与错误码)
- [测试](#测试)
- [Docker 部署](#docker-部署)
- [已知限制](#已知限制)

## 项目特点

- **多站点统一抓取服务**：统一封装 LeetCode / Luogu / Lanqiao 抓取能力，对下游暴露稳定的 HTTP 协议。
- **清晰分层设计**：严格遵循 `api/router -> services -> crawler -> core`，Router 只做协议转换，Service 负责编排，Parser 保持纯函数。
- **异步抓取架构**：结合 `FastAPI (ASGI)` 与 `Scrapy (Twisted)`，在单进程内完成接口请求与爬虫调度衔接。
- **代理池健康管理**：内置站点级代理状态维护、主动探测与失败回传，代理池为空时自动降级为直连。
- **统一错误映射**：成功响应固定为 `{"ok": true, "data": {...}}`，失败响应固定为 `{"ok": false, "error": "...", "code": "..."}`。
- **Redis Stream 可观测性**：支持 W3C Trace Context 入站透传，并将 `http.request -> crawler.run -> outbound.http -> crawler.callback` span 链路批量写入 Redis Stream。
- **测试驱动回归**：覆盖 API 契约、Parser、Runner、ProxyService 和 observability 链路，方便迭代时快速回归。

## 技术栈

- Python 3.12
- FastAPI / Uvicorn
- Scrapy + Twisted
- Pydantic
- requests / lxml / PyYAML
- Redis（可选，仅用于 tracing backend）
- pytest / pytest-asyncio / respx

## 项目结构

```text
crawler_center_scrapy/
├─ crawler_center/
│  ├─ api/                  # FastAPI 入口、路由、Schema、依赖注入
│  ├─ core/                 # 配置、错误模型、安全、日志
│  ├─ crawler/              # Scrapy runner、spider、parser、中间件
│  ├─ observability/        # Trace context、middleware、Redis trace backend
│  └─ services/             # 业务服务层（leetcode/luogu/lanqiao/proxy）
├─ tests/                   # API / Service / Parser / Runner / Observability 测试
├─ .env.example             # 服务器部署环境变量模板
├─ .github/workflows/       # CI/CD 工作流
├─ config.yaml              # 默认配置文件
├─ requirements.txt
├─ Dockerfile
└─ docker-compose.yml
```

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. 配置（可选）

默认读取仓库根目录下的 `config.yaml`。如需覆盖，可通过环境变量注入配置，优先级为：

**环境变量 > config.yaml > 代码默认值**

### 3. 启动服务

Windows 开发环境推荐：

```bash
python -m crawler_center.api.run
```

请先激活已经安装 `requirements.txt` 的虚拟环境或 Conda 环境，再执行这条命令。这个入口会先切换到 `WindowsSelectorEventLoopPolicy`，用于规避 Windows 下 `ProactorEventLoop` 与 Scrapy/Twisted `AsyncioSelectorReactor` 的兼容问题。

macOS / Linux 或已确认事件循环兼容时，可直接使用：

```bash
uvicorn crawler_center.api.main:app --host 0.0.0.0 --port 8000 --reload
```

启动后默认访问地址：

- OpenAPI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- 健康检查: `http://127.0.0.1:8000/v2/healthz`

如果你在 Windows 上直接使用 `uvicorn` 并看到 `AsyncioSelectorReactor` 相关报错，或出现 `ModuleNotFoundError: No module named 'scrapy'` 这类依赖缺失错误，通常是因为当前 `uvicorn` 和 `python` 不在同一个环境中。请先激活安装了项目依赖的环境，再执行 `python -m crawler_center.api.run`。

## 接口总览

### 公共接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/v2/healthz` | 健康检查 |
| POST | `/v2/leetcode/profile_meta` | LeetCode 用户主页元信息 |
| POST | `/v2/leetcode/recent_ac` | LeetCode 最近 AC 记录 |
| POST | `/v2/leetcode/submit_stats` | LeetCode 提交统计 |
| POST | `/v2/leetcode/public_profile` | LeetCode 公开资料 |
| POST | `/v2/leetcode/crawl` | LeetCode 聚合抓取（`meta + recent_ac + stats`） |
| POST | `/v2/luogu/practice` | 洛谷练题 / 通过题数据 |
| POST | `/v2/lanqiao/solve_stats` | 蓝桥做题统计（登录 + 拉取一体化） |

### 内部接口（代理池）

> 需要请求头：`X-Internal-Token: <your-token>`  
> 若未配置 `INTERNAL_TOKEN` 或 `config.yaml.internal.token`，接口会返回 `503`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/internal/proxies` | 查询代理列表，支持 `global_status` / `target_site` / `target_status` 筛选 |
| POST | `/internal/proxies/sync` | 全量替换代理池 |
| POST | `/internal/proxies/remove` | 批量删除指定代理 |

## 请求示例

### 1) 健康检查

```bash
curl http://127.0.0.1:8000/v2/healthz
```

```json
{
  "ok": true,
  "data": {
    "status": "ok",
    "version": "2.0.0"
  }
}
```

### 2) LeetCode 聚合抓取

```bash
curl -X POST http://127.0.0.1:8000/v2/leetcode/crawl \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"demo\",\"sleep_sec\":0.8}"
```

示例返回（字段会随目标站点实际数据变化）：

```json
{
  "ok": true,
  "data": {
    "meta": {
      "exists": true,
      "url_final": "https://leetcode.cn/u/demo/",
      "og_title": "leetcode profile",
      "og_description": "public profile desc"
    },
    "recent_accepted": [
      {
        "title": "Two Sum CN",
        "slug": "two-sum",
        "timestamp": 1700000000,
        "time": "2023-11-14 22:13:20"
      }
    ],
    "stats": {
      "userProfileUserQuestionSubmitStats": {},
      "userProfileUserQuestionProgress": {}
    }
  }
}
```

### 3) Luogu 抓取

```bash
curl -X POST http://127.0.0.1:8000/v2/luogu/practice \
  -H "Content-Type: application/json" \
  -d "{\"uid\":1,\"sleep_sec\":0.8}"
```

### 4) 蓝桥做题统计

```bash
curl -X POST http://127.0.0.1:8000/v2/lanqiao/solve_stats \
  -H "Content-Type: application/json" \
  -d "{\"phone\":\"13800000000\",\"password\":\"your-password\",\"sync_num\":0}"
```

`sync_num` 规则：

- `-1`：只返回 `stats`
- `0`：返回 `stats + problems`
- `>0`：仅在前 N 条原始提交范围内筛选去重后返回 `problems`

若蓝桥账号或密码无效，会返回统一错误而不是空 `problems`：

```json
{
  "ok": false,
  "error": "Lanqiao credentials invalid",
  "code": "upstream_auth_failed"
}
```

### 5) 代理池同步（内部接口）

```bash
curl -X POST http://127.0.0.1:8000/internal/proxies/sync \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: secret-token" \
  -d "{\"proxies\":[\"http://127.0.0.1:9000\",\"http://127.0.0.1:9001\"]}"
```

### 6) 代理池查询（内部接口）

```bash
curl -X GET "http://127.0.0.1:8000/internal/proxies?target_site=leetcode&target_status=OK" \
  -H "X-Internal-Token: secret-token"
```

说明：

- `target_status` 仅在同时提供 `target_site` 时有效。
- 若只关心全局状态，可改为 `?global_status=OK`。

### 7) 代理池删除（内部接口）

```bash
curl -X POST http://127.0.0.1:8000/internal/proxies/remove \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: secret-token" \
  -d "{\"proxy_urls\":[\"http://127.0.0.1:9000\",\"http://127.0.0.1:9001\"]}"
```

## 配置说明

### `config.yaml`（默认）

```yaml
leetcode:
  base_url: "https://leetcode.cn"

luogu:
  base_url: "https://www.luogu.com.cn"

lanqiao:
  base_url: "https://www.lanqiao.cn"
  login_url: "https://passport.lanqiao.cn/api/v1/login/?auth_type=login"
  user_url: "https://passport.lanqiao.cn/api/v1/user/"

crawler:
  default_timeout: 15
  default_sleep_sec: 0.8
  default_user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
  run_timeout_sec: 30
  concurrent_requests: 16
  retry_times: 2
  proxy_active_probe_interval_sec: 300

api:
  title: "crawler_center"
  version: "2.0.0"

internal:
  token: ""

redis:
  address: "127.0.0.1:6379"
  password: ""
  db: 0

observability:
  enabled: true
  service_name: "crawler_center"
  traces:
    stream_key: "traces:stream"
    stream_maxlen: 10000
    queue_size: 2048
    flush_interval_ms: 500
    flush_batch_size: 50
    max_payload_bytes: 4096

logging:
  level: "INFO"
```

### 环境变量覆盖

程序按以下优先级读取配置：**环境变量 > config.yaml > 代码默认值**

| 环境变量 | 说明 |
| --- | --- |
| `LEETCODE_BASE_URL` | LeetCode 站点地址 |
| `LUOGU_BASE_URL` | 洛谷站点地址 |
| `LANQIAO_BASE_URL` | 蓝桥站点地址 |
| `LANQIAO_LOGIN_URL` | 蓝桥登录接口地址 |
| `LANQIAO_USER_URL` | 蓝桥用户信息接口地址 |
| `DEFAULT_TIMEOUT_SEC` | 单请求超时（秒） |
| `DEFAULT_SLEEP_SEC` | 默认抓取间隔（秒） |
| `DEFAULT_USER_AGENT` | 默认 User-Agent |
| `CRAWLER_RUN_TIMEOUT_SEC` | 单次爬虫运行超时（秒） |
| `CRAWLER_CONCURRENT_REQUESTS` | Scrapy 并发请求数 |
| `CRAWLER_RETRY_TIMES` | Scrapy 重试次数 |
| `PROXY_ACTIVE_PROBE_INTERVAL_SEC` | 代理主动探测周期（秒） |
| `API_TITLE` | FastAPI 标题 |
| `API_VERSION` | API 版本号 |
| `INTERNAL_TOKEN` | 内部接口鉴权 token |
| `REDIS_ADDRESS` | tracing backend 使用的 Redis 地址 |
| `REDIS_PASSWORD` | Redis 密码 |
| `REDIS_DB` | Redis DB 编号 |
| `OBS_ENABLED` | 是否启用 observability 中间件 |
| `OBS_SERVICE_NAME` | span 中记录的 service 名称 |
| `LOG_LEVEL` | 日志级别，例如 `INFO` / `DEBUG` |

说明：

- `observability.traces.stream_key`、`stream_maxlen`、`queue_size`、`flush_interval_ms`、`flush_batch_size`、`max_payload_bytes` 目前通过 `config.yaml` 配置，不提供独立环境变量。
- `.env` 会在应用启动时自动加载，适合本地开发和单机部署。

## 可观测性 / 链路追踪

当 `observability.enabled=true` 或 `OBS_ENABLED=true` 时，应用会注册 tracing middleware，并在 FastAPI 请求与 Scrapy 执行之间透传 trace context。

### 入站请求支持的 header

- `traceparent`
- `tracestate`
- `X-Request-ID`

说明：

- 若传入合法 `traceparent`，服务会复用已有 `trace_id` 和父 `span_id`。
- 若未传入 `X-Request-ID`，服务会自动生成一个 request id。
- 即使不接入完整 tracing，也建议传 `X-Request-ID` 便于日志关联。

### span 链路

默认链路为：

```text
http.request -> crawler.run -> outbound.http -> crawler.callback
```

其中：

- `http.request`：FastAPI 入站请求
- `crawler.run`：单次 spider 运行
- `outbound.http`：Scrapy 发起的上游 HTTP 请求
- `crawler.callback`：Scrapy callback 执行过程

### 后端与降级行为

- span 后端默认写入 Redis Stream，stream key 默认为 `traces:stream`
- Redis 写入通过内存队列异步批量 flush，不阻塞业务请求主路径
- 遇到以下情况时会自动降级为 `NoopTraceBackend`，服务继续可用：
  - `OBS_ENABLED=false`
  - 未配置 `REDIS_ADDRESS`
  - Redis 初始化或 `ping` 失败

### 部署建议

- **有 Redis**：保持 `OBS_ENABLED=true`，并在 `.env` 或 `config.yaml` 中配置 `REDIS_ADDRESS`、`REDIS_PASSWORD`、`REDIS_DB`
- **无 Redis**：显式设置 `OBS_ENABLED=false`，避免容器启动时出现 tracing backend 降级告警

## 代理池（内部接口）

代理池能力由 `ProxyService` 提供：

- 代理全量同步与批量删除
- 代理列表查询，支持 `global_status` / `target_site` / `target_status`
- 按站点维护健康状态：`leetcode` / `luogu` / `lanqiao`
- 状态机：`OK -> SUSPECT -> DEAD`
- 后台主动探测（定时轮询 probe URL）
- 请求完成后自动回传代理成功 / 失败与延迟统计

说明：

- 新增代理请通过 `POST /internal/proxies/sync` 提交全量列表。
- 删除代理请通过 `POST /internal/proxies/remove` 传入 `proxy_urls` 数组。
- 使用 `target_status` 查询时，必须同时提供 `target_site`。
- 若代理池为空，抓取流程会自动退化为直连请求。
- 内部接口建议仅在内网或网关后暴露。

## 错误响应与错误码

统一失败格式：

```json
{
  "ok": false,
  "error": "error message",
  "code": "machine_readable_code"
}
```

常见错误码与 HTTP 状态：

| HTTP 状态 | `code` | 场景 |
| --- | --- | --- |
| 401 | `http_error` | 内部 token 错误 |
| 401 | `upstream_auth_failed` | 蓝桥账号或密码无效 |
| 422 | `validation_error` | 请求参数不合法 |
| 502 | `upstream_request_error` / `crawler_execution_error` | 上游请求或爬虫执行失败 |
| 503 | `proxy_unavailable` / `http_error` | 无可用代理或内部 token 未配置 |
| 504 | `crawler_timeout` | 爬虫执行超时 |
| 500 | `internal_error` | 未捕获异常 |

## 测试

全量测试：

```bash
pytest -q
```

最小回归集：

```bash
pytest -q tests/api/test_api_routes.py
pytest -q tests/core/test_observability.py
pytest -q tests/crawler/test_runner.py
```

测试覆盖：

- API 路由协议与错误映射
- Parser 快照解析
- Scrapy Runner 超时、收集与 reactor 兼容逻辑
- ProxyService 代理池状态流转
- `tests/core/test_observability.py` 中的 HTTP -> Scrapy trace 链路与错误 item 标记

## Docker 部署

### 本地构建并运行

```bash
docker build -t ghcr.io/wdx-123/crawler_center_scrapy:local .
docker run --rm -p 8000:8000 -v $(pwd)/config.yaml:/app/config.yaml:ro -e OBS_ENABLED=false ghcr.io/wdx-123/crawler_center_scrapy:local
```

Windows PowerShell 可用：

```powershell
docker run --rm -p 8000:8000 -v ${PWD}\config.yaml:/app/config.yaml:ro -e OBS_ENABLED=false ghcr.io/wdx-123/crawler_center_scrapy:local
```

说明：

- 容器默认监听 `8000`。
- 如果你已有可用 Redis，可移除 `-e OBS_ENABLED=false`，并通过环境变量或 `config.yaml` 提供 Redis 配置。

本地 smoke test：

```bash
curl http://127.0.0.1:8000/v2/healthz
```

### 发布到 GHCR（自动）

本仓库使用 GitHub Actions 工作流 [`.github/workflows/cd.yml`](./.github/workflows/cd.yml) 自动发布镜像：

- 触发：`push` 到 `main` 或手动 `workflow_dispatch`
- 平台：`linux/amd64` + `linux/arm64`
- 镜像：`ghcr.io/wdx-123/crawler_center_scrapy`
- 标签：`v0.0.<run_number>`、`sha-<short_sha>`、`latest`

> 如果你是 fork 本仓库，请同步修改 `.github/workflows/cd.yml` 与 `docker-compose.yml` 中的镜像地址。

### 服务器部署（docker compose）

1. 在服务器准备目录：

```bash
mkdir -p /opt/crawler_center_scrapy
cd /opt/crawler_center_scrapy
```

2. 准备配置文件 `/opt/crawler_center_scrapy/config.yaml`。

3. 复制本仓库的 `docker-compose.yml` 和 `.env.example`，并创建 `.env`：

```bash
cp .env.example .env
```

`.env` 关键项示例：

```env
IMAGE_TAG=latest
CONFIG_PATH=/opt/crawler_center_scrapy/config.yaml
TZ=Asia/Shanghai
LOG_LEVEL=INFO
INTERNAL_TOKEN=replace-with-your-token

# Redis 配置（若启用 tracing，需指向已存在的 Redis 服务）
REDIS_ADDRESS=127.0.0.1:6379
REDIS_PASSWORD=
REDIS_DB=0

# Observability
OBS_ENABLED=true
OBS_SERVICE_NAME=crawler_center
```

说明：

- 自动部署时会把 `IMAGE_TAG` 更新为本次发布的 `sha-<short_sha>`。
- 当前 `docker-compose.yml` 仅编排本服务，不会额外启动 Redis；如果没有现成 Redis，请把 `OBS_ENABLED=false` 写入 `.env`。

4. 拉取并启动：

```bash
docker compose pull crawler_center
docker compose up -d crawler_center
```

5. 验证：

```bash
curl http://127.0.0.1:8000/v2/healthz
docker compose logs --tail=100 crawler_center
```

### GitHub 仓库配置

1. `Settings -> Actions -> General`

- `Workflow permissions` 允许 `Read and write permissions`

2. `Settings -> Secrets and variables -> Actions`

- 必填 Secrets：
  - `DEPLOY_HOST`
  - `DEPLOY_USER`
  - `DEPLOY_SSH_KEY`
  - `GHCR_USERNAME`
  - `GHCR_TOKEN`
- 可选 Variables：
  - `DEPLOY_PORT`，默认 `22`
  - `DEPLOY_PATH`，默认 `/opt/crawler_center_scrapy`
  - `HEALTHCHECK_URL`，默认 `http://127.0.0.1:8000/v2/healthz`

3. `Settings -> Branches -> Branch protection rules (main)`

- 开启 `Require a pull request before merging`
- 开启 `Require status checks to pass before merging`
- 勾选状态检查 `CI - Test / tests`

### 自动部署行为

`cd.yml` 会在镜像推送后自动完成以下动作：

- 上传 `docker-compose.yml` 与 `.env.example`
- 校验远端 `config.yaml` 存在
- 把 `.env` 中的 `IMAGE_TAG` 更新为本次 `sha-<short_sha>`
- 执行 `docker compose pull crawler_center && docker compose up -d crawler_center`
- 健康检查失败时输出 `docker compose logs --tail=200 crawler_center`

### 回滚

当新版本异常时，修改 `.env` 中的 `IMAGE_TAG` 为历史 `sha-xxxxxxx` 后重新启动：

```bash
docker compose up -d crawler_center
```

### 多架构镜像检查

```bash
docker buildx imagetools inspect ghcr.io/wdx-123/crawler_center_scrapy:latest
```

输出中应包含 `linux/amd64` 和 `linux/arm64`。

## 已知限制

- 代理池当前为进程内内存实现，服务重启后不会持久化。
- 抓取能力依赖目标站点页面结构与上游接口稳定性，上游改版后可能需要同步调整 spider / parser。
- observability 的 trace stream 细粒度参数目前仅支持通过 `config.yaml` 配置。

---

如果这个项目对你有帮助，欢迎 Star 或提交 Issue / PR 交流改进。
