# Skill: crawler-center-test-release

## Purpose
用于 `crawler_center_scrapy` 的测试回归与发布前检查，确保改动可上线、可维护、可回滚。

## Use when
- 准备提交 PR 或推送到 GitHub
- 进行代码评审（review）
- 做版本发布前验收
- 改动涉及 API 契约、解析逻辑、代理逻辑、配置项

若当前任务会继续落代码或改规则，先按项目根目录 `plan/README.md` 生成 `plan/<module>/pending-<task>.md`，待用户明确确认后再执行。

## Release validation workflow
1. 变更分类  
   将改动归类为：API / Parser / Spider / Proxy / Config / Docs。
2. 最小测试矩阵  
   - API 变更：`tests/api/*`  
   - Parser/Spider/Runner 变更：`tests/crawler/*`  
   - Proxy 变更：`tests/services/test_proxy_service.py`
3. 契约检查  
   确认成功响应和错误响应结构未被破坏，关键字段名未变更。
4. 配置检查  
   确认新增配置支持 `env > config.yaml > default`。
5. 文档检查  
   README 的接口、配置、运行方式与当前代码一致。

## Commands
```bash
pytest -q
```

若只需快速检查受影响范围：
```bash
pytest -q tests/api
pytest -q tests/crawler/test_parsers.py
pytest -q tests/services/test_proxy_service.py
```

## Review focus (severity first)
- P0: API 返回结构破坏、状态码错误、鉴权绕过、异常未收敛
- P1: 解析器在上游轻微波动时崩溃、代理状态更新不正确、超时处理缺失
- P2: 日志不可观测、默认值不合理、文档不同步

## Pre-push checklist
- [ ] 所有相关测试通过
- [ ] 无敏感信息（token/cookie/password）进入日志与仓库
- [ ] README 与当前实现一致
- [ ] 关键路由可本地 smoke test（`/v2/healthz` + 至少一个业务接口）
- [ ] 确认没有误改无关文件

