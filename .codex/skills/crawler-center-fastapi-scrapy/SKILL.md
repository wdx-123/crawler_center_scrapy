# Skill: crawler-center-fastapi-scrapy

## Purpose
用于 `crawler_center_scrapy` 仓库的日常开发、重构、修复和代码评审，确保改动符合本项目分层与协议约束。

## Use when
- 新增或修改 API 路由（`crawler_center/api/routers/*`）
- 新增或修改业务服务（`crawler_center/services/*`）
- 新增或修改 spider/parser/runner（`crawler_center/crawler/*`）
- 调整错误模型、日志、配置、安全策略（`crawler_center/core/*`）

## Core workflow (in order)
1. 明确改动边界  
   先定位是「协议层」「编排层」「抓取层」「解析层」中的哪几层需要修改。
2. 先定契约再改实现  
   明确请求模型、响应字段、错误码与 HTTP 状态映射，再改代码。
3. 分层落地改动  
   - `schema`：请求/响应模型  
   - `router`：入参校验与调用 service  
   - `service`：编排流程、异常提升  
   - `spider/parser`：抓取与解析逻辑  
4. 补齐测试  
   至少覆盖：成功路径 + 参数错误或上游错误路径。
5. 回归验证  
   跑相关测试并确认 README/API 文档是否需要同步。

## Mandatory project constraints
- 路由层不直接 new 业务对象；依赖来自 `app.state` + `Depends`。
- 统一响应结构：  
  - success: `{"ok": true, "data": {...}}`  
  - error: `{"ok": false, "error": "...", "code": "..."}`
- Spider 的可恢复异常以 `{"_error": "...", ...}` 上报，交由 service 转为业务异常。
- Parser 保持纯函数，不做网络请求，不引入全局状态。
- 修改异常类型后，必须同步 `api.main` 的异常处理器映射。

## Quick file map
- App entry: `crawler_center/api/main.py`
- Routers: `crawler_center/api/routers/`
- Schemas: `crawler_center/api/schemas/`
- Services: `crawler_center/services/`
- Runner: `crawler_center/crawler/runner.py`
- Spiders: `crawler_center/crawler/spiders/`
- Parsers: `crawler_center/crawler/parsers/`
- Errors/config/security/logging: `crawler_center/core/`

## Suggested test commands
```bash
pytest -q tests/api
pytest -q tests/crawler
pytest -q tests/services
```

## Done checklist
- [ ] API 契约与实际返回一致
- [ ] 错误码与状态码映射正确
- [ ] 目标站点字段命名保持向后兼容
- [ ] 相关测试已通过
- [ ] README 或注释已按需同步

