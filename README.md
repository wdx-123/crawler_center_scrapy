# crawler_center_scrapy

基于 **FastAPI + Scrapy** 的聚合爬虫服务，提供统一 HTTP API，用于抓取并标准化以下站点的用户公开数据：

- LeetCode（已实现）
- 洛谷 Luogu（已实现）
- 蓝桥 Lanqiao（已实现单接口抓取）

## 目录

- [项目特点](#项目特点)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [接口总览](#接口总览)
- [请求示例](#请求示例)
- [配置说明](#配置说明)
- [代理池（内部接口）](#代理池内部接口)
- [错误响应与错误码](#错误响应与错误码)
- [测试](#测试)
- [Docker 部署](#docker-部署)
- [已知限制](#已知限制)

## 项目特点

- 统一响应协议：成功与失败都返回稳定 JSON 结构，便于调用方处理。
- 分层清晰：`Router -> Service -> Runner/Spider -> Parser`，便于扩展和维护。
- 可插拔代理池：支持内部同步代理、按站点维度健康探测、自动降级坏代理。
- 统一异常映射：将抓取超时、上游错误、鉴权失败等映射为明确 HTTP 状态码。
- 结构化日志：默认输出 JSON 日志，并对敏感字段做脱敏处理。

## 技术栈

- Python 3.12（建议）
- FastAPI / Uvicorn
- Scrapy + Twisted
- Pydantic
- requests / lxml / PyYAML
- pytest / pytest-asyncio / respx

## 项目结构

```text
crawler_center_scrapy/
├─ crawler_center/
│  ├─ api/                  # FastAPI 入口、路由、Schema、依赖注入
│  ├─ core/                 # 配置、错误模型、安全、日志
│  ├─ crawler/              # Scrapy runner、spider、parser、中间件
│  └─ services/             # 业务服务层（leetcode/luogu/lanqiao/proxy）
├─ tests/                   # API / Service / Parser / Runner 测试
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

默认读取根目录 `config.yaml`。你也可以通过环境变量覆盖配置（见下文“配置说明”）。

### 3. 启动服务

```bash
uvicorn crawler_center.api.main:app --host 0.0.0.0 --port 8001 --reload
```

启动后可访问：

- OpenAPI: `http://127.0.0.1:8001/docs`
- ReDoc: `http://127.0.0.1:8001/redoc`
- 健康检查: `http://127.0.0.1:8001/v2/healthz`

## 接口总览

### 公共接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/v2/healthz` | 健康检查 |
| POST | `/v2/leetcode/profile_meta` | LeetCode 用户主页元信息 |
| POST | `/v2/leetcode/recent_ac` | LeetCode 最近 AC 记录 |
| POST | `/v2/leetcode/submit_stats` | LeetCode 提交统计 |
| POST | `/v2/leetcode/public_profile` | LeetCode 公开资料 |
| POST | `/v2/leetcode/crawl` | LeetCode 聚合抓取（meta + recent + stats） |
| POST | `/v2/luogu/practice` | 洛谷练题/通过题数据 |
| POST | `/v2/lanqiao/solve_stats` | 蓝桥做题统计（登录+拉取一体化） |

### 内部接口（代理池）

> 需要请求头：`X-Internal-Token: <your-token>`  
> 若未配置 `INTERNAL_TOKEN` / `config.yaml.internal.token`，接口会返回 `503`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/internal/proxies` | 查询代理列表（支持状态筛选，默认按 OK/SUSPECT/DEAD 排序） |
| POST | `/internal/proxies/sync` | 全量替换代理池 |
| POST | `/internal/proxies/remove` | 删除指定代理 |

## 请求示例

### 1) 健康检查

```bash
curl http://127.0.0.1:8001/v2/healthz
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
curl -X POST http://127.0.0.1:8001/v2/leetcode/crawl \
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
curl -X POST http://127.0.0.1:8001/v2/luogu/practice \
  -H "Content-Type: application/json" \
  -d "{\"uid\":1,\"sleep_sec\":0.8}"
```

### 4) 蓝桥做题统计（单接口）

```bash
curl -X POST http://127.0.0.1:8001/v2/lanqiao/solve_stats \
  -H "Content-Type: application/json" \
  -d "{\"phone\":\"13800000000\",\"password\":\"your-password\",\"sync_num\":0}"
```

`sync_num` 规则：

- `-1`：只返回 `stats`
- `0`：返回 `stats + problems`
- `>0`：仅在前 N 条原始提交范围内筛选去重后返回 `problems`

### 5) 代理池同步（内部接口）

```bash
curl -X POST http://127.0.0.1:8001/internal/proxies/sync \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: secret-token" \
  -d "{\"proxies\":[\"http://127.0.0.1:9000\",\"http://127.0.0.1:9001\"]}"
```

### 6) 代理池查询（内部接口）

```bash
curl -X GET "http://127.0.0.1:8001/internal/proxies?global_status=OK&target_site=leetcode" \
  -H "X-Internal-Token: secret-token"
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
crawler:
  default_timeout: 15
  default_sleep_sec: 0.8
  default_user_agent: "Mozilla/5.0 ..."
  run_timeout_sec: 30
  concurrent_requests: 16
  retry_times: 2
  proxy_active_probe_interval_sec: 300
api:
  title: "crawler_center"
  version: "2.0.0"
internal:
  token: ""
```

### 环境变量覆盖

程序会按以下优先级读取配置：**环境变量 > config.yaml > 代码默认值**

| 环境变量 | 说明 |
| --- | --- |
| `LEETCODE_BASE_URL` | LeetCode 站点地址 |
| `LUOGU_BASE_URL` | 洛谷站点地址 |
| `LANQIAO_BASE_URL` | 蓝桥站点地址 |
| `DEFAULT_TIMEOUT_SEC` | 单请求超时（秒） |
| `DEFAULT_SLEEP_SEC` | 默认抓取间隔（秒） |
| `DEFAULT_USER_AGENT` | 默认 UA |
| `CRAWLER_RUN_TIMEOUT_SEC` | 单次爬虫运行超时（秒） |
| `CRAWLER_CONCURRENT_REQUESTS` | Scrapy 并发请求数 |
| `CRAWLER_RETRY_TIMES` | Scrapy 重试次数 |
| `PROXY_ACTIVE_PROBE_INTERVAL_SEC` | 代理主动探测周期（秒） |
| `API_TITLE` | FastAPI 标题 |
| `API_VERSION` | API 版本号 |
| `INTERNAL_TOKEN` | 内部接口鉴权 token |
| `LOG_LEVEL` | 日志级别（如 `INFO`/`DEBUG`） |

## 代理池（内部接口）

代理池能力由 `ProxyService` 提供：

- 代理全量同步与删除
- 代理列表查询（支持全局状态筛选 + 站点状态筛选）
- 按站点维护健康状态：`leetcode` / `luogu` / `lanqiao`
- 状态机：`OK -> SUSPECT -> DEAD`
- 后台主动探测（定时轮询 probe URL）
- 请求后自动回传代理成功/失败与延迟统计

说明：

- 新增代理请通过 `POST /internal/proxies/sync` 提交全量列表。
- 删除代理请通过 `POST /internal/proxies/remove` 传入待删 `proxy_url`（精确到 `ip:port`）。
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
| 422 | `validation_error` | 请求参数不合法 |
| 502 | `upstream_request_error` / `crawler_execution_error` | 上游请求或爬虫执行失败 |
| 503 | `proxy_unavailable` / `http_error` | 无可用代理或内部 token 未配置 |
| 504 | `crawler_timeout` | 爬虫执行超时 |
| 500 | `internal_error` | 未捕获异常 |

## 测试

```bash
pytest -q
```

测试覆盖：

- API 路由协议与错误映射
- Parser 快照解析
- Scrapy Runner 超时与收集逻辑
- ProxyService 代理池状态流转

## Docker 部署

### 本地构建并运行

```bash
docker build -t crawler_center:local .
docker run --rm -p 8001:8001 -v $(pwd)/config.yaml:/app/config.yaml crawler_center:local
```

Windows PowerShell 可用：

```powershell
docker run --rm -p 8001:8001 -v ${PWD}\config.yaml:/app/config.yaml crawler_center:local
```

### 使用 `docker-compose.yml`

```bash
docker compose up -d
```

> 当前 `docker-compose.yml` 默认镜像为 `ghcr.io/wdx-123/crawler_center:0.1`。  
> 发布你自己的版本时，请替换为你的镜像地址与标签。

## 已知限制

- 代理池为进程内内存实现，服务重启后不会持久化。
- 对目标站点的抓取能力依赖页面结构/接口稳定性，若上游变更需要同步调整 parser/spider。

---

如果这个项目对你有帮助，欢迎 Star 或提交 Issue/PR 交流改进。
