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

## 计划落盘规则

- 只要任务属于新增、重构、修复、联调、排障、迁移、删除、配置调整这类执行型工作，先写计划，不直接改代码。
- 计划文件固定写到 `plan/<module>/pending-<task>.md`。
- 结构名固定使用英文：根目录为 `plan/`，跨模块目录为 `plan/cross-module/`，状态前缀为 `pending-` 和 `approved-`。
- `<module>` 和 `<task>` 按语义决定中英文：稳定技术名词优先英文，如 `parser`；更自然的业务表达可保留中文，如 `题单`、`接口契约与解析联调`。
- 纯问答、纯解释、纯代码审查、纯只读排查，不强制生成计划文件。
- 计划目录规则以 `plan/README.md` 为准。

## 计划命名规则

- 文件名格式固定为 `pending-<task>.md` 或 `approved-<task>.md`。
- `<task>` 必须直接体现本次执行目标，可用英文技术短语，也可用中文业务短语，但都不能空泛。
- 合格示例：`pending-parser-fallback-refactor.md`、`pending-题单补抓修复.md`、`pending-接口契约对齐.md`。
- 后续若用户直接说“先出计划”，默认先写入对应模块目录下的 `pending-<task>.md`，无需额外指定路径。

## 审查后执行规则

- 生成待审计划后，只允许查代码、读文档、跑非修改型检查；未获明确确认前，不允许实施改动。
- 用户明确确认后，先将计划文件改名为 `approved-<task>.md`，再按计划执行。
- 执行前需要在对话中回报计划路径和摘要，供用户审查。
- 若执行中发现范围明显变化，禁止静默扩项，必须重新生成新的 `pending-<task>.md` 给用户复审。
- 涉及 API 契约、解析逻辑、代理链路或配置行为的执行任务，同样必须先经过待审计划流程。

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
