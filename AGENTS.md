# d:\workspace_python\crawler_center_scrapy 的 AGENTS.md 说明

## 项目规则（仅自用）

### 1) 架构与职责
- 严格保持分层：`api/router -> services -> crawler(spider/parser/runner) -> core`。
- Router 层只做协议转换和依赖注入，不承载爬虫业务逻辑。
- Service 层是编排层，也是唯一可以聚合多个 spider 的地方。
- Parser 层必须保持纯函数风格：不发网络请求、无副作用、返回结构可预测。

### 2) API 契约稳定性
- 除非明确计划破坏性变更，否则 `/v2/*` 路由需保持向后兼容。
- 成功响应保持 `{"ok": true, "data": {...}}`。
- 失败响应保持 `{"ok": false, "error": "...", "code": "..."}`。
- 新增错误优先复用 `crawler_center.core.errors`，并在 `api.main` 中完成异常映射。

### 3) 爬虫与解析规范
- Spider 侧可恢复的上游异常使用 `{"_error": "...", ...}` item 上报。
- Service 层必须将 `_error` item 转为项目异常，以保证稳定的 HTTP 映射。
- 需要代理健康追踪时，请求必须携带 `meta["target_site"]`。
- 解析逻辑优先“健壮默认值”，避免过度脆弱的强假设解析。

### 4) 配置与安全
- 配置优先级必须保持：`env > config.yaml > code defaults`。
- 内部代理路由必须持续使用 `X-Internal-Token` 保护。
- 日志中禁止暴露 secret/token/cookie，统一使用结构化日志脱敏。

### 5) 测试纪律
- 任何 API 契约变更都要同步更新 API 测试。
- 任何 Parser 行为变更都要同步更新或新增快照测试。
- 任何代理或中间件行为变更都要同步更新 service 测试。
- 完成改动前，至少运行受影响模块的针对性测试。

### 6) 可读性与可维护性
- 命名与现有模块保持一致（`leetcode_*`、`luogu_*`、`lanqiao_*`）。
- 仅在非显而易见逻辑处添加简短注释。
- 不要静默修改响应字段名。
- 优先小步、可组合的改动，避免大范围重写。

## 技能（Skills）

Skill 是存放在 `SKILL.md` 中的本地指令集。任务匹配时应使用对应 skill。

### 可用技能
- crawler-center-fastapi-scrapy：本项目通用开发技能，覆盖路由/服务/爬虫/解析器/错误映射的端到端改动流程。  
  文件：`D:/workspace_python/crawler_center_scrapy/.codex/skills/crawler-center-fastapi-scrapy/SKILL.md`
- crawler-center-test-release：本项目测试与发布前检查技能，覆盖最小测试矩阵、回归风险检查和 README/API 同步。  
  文件：`D:/workspace_python/crawler_center_scrapy/.codex/skills/crawler-center-test-release/SKILL.md`

## 技能使用方式
- 在本仓库进行功能开发/重构/排障时，使用 `crawler-center-fastapi-scrapy`。
- 在验收/评审/发布准备时，使用 `crawler-center-test-release`。
- 如果两者都适用，先用 `crawler-center-fastapi-scrapy`，再用 `crawler-center-test-release`。
