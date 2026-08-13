# __BOT_TITLE__

这是由 `project-agent-bootstrap` 生成的安全起步项目。它提供配置校验、会话状态、幂等事件、只读 SQL 防护和部署模板；飞书与 Codex 的真实适配器需要按项目环境接入。

## 默认边界

- 实时模式必须配置非空的飞书群白名单。
- `BOT_DRY_RUN=true`，`BOT_ALLOW_REAL_WRITES=false`。
- 数据库必须使用专用只读账号；SQL 检查只是第二道防线。
- 密码、Token、Cookie 和私钥只从本地密钥设施或环境变量注入。
- 一个飞书话题对应一个 Agent 任务；同一话题内按 FIFO 顺序处理。
- 回答先持久化，再尝试发送，避免发送超时后丢失结果。

## 用户需要准备

1. 项目根目录、知识库目录、代码仓库与允许读取的分支。
2. 飞书中国版或 Lark 国际版、已有应用/机器人、事件订阅、权限范围，以及允许使用机器人的群。
3. 已登录的 `lark-cli` 身份或官方 SDK 所需凭据；凭据值不要写入本项目。
4. Codex 路径、版本、模型、沙箱范围、单轮超时和并发限制。
5. 每个数据库环境的引擎、地址、库/服务名、Schema、专用只读账号、VPN要求、查询超时和行数上限。
6. 日志平台、允许访问的环境/命名空间/工作负载，以及脱敏规则。
7. 部署主机、服务管理器、状态/日志/附件目录、监控与回滚方式。

只有确实需要真实写操作时，才另外定义“单一业务动作 + 固定参数结构 + 一次性审批 + 审计证据”。不要启用自由 SQL、自由 Shell 或通用生产写权限。

## 本地启动

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .
cp .env.example .env
```

把 `.env` 中的非敏感配置补齐，并通过本机密钥设施设置秘密变量。先运行离线预检：

```bash
.venv/bin/python -m __PACKAGE_NAME__ preflight
.venv/bin/python -m unittest discover -s tests -v
```

准备连接真实飞书环境前，再运行严格预检：

```bash
.venv/bin/python -m __PACKAGE_NAME__ preflight --live
```

严格预检不会发送消息，但会要求群白名单和运行目录有效。

## 目录

- `src/__PACKAGE_NAME__/config.py`：单一配置入口与安全默认值。
- `src/__PACKAGE_NAME__/policy.py`：群白名单、只读 SQL 与写能力授权边界。
- `src/__PACKAGE_NAME__/approvals.py`：精确参数、限时、一次性审批账本；默认没有启用任何写能力。
- `src/__PACKAGE_NAME__/state.py`：SQLite 话题、事件幂等和状态迁移。
- `src/__PACKAGE_NAME__/runtime.py`：适配器协议与可测试的处理骨架。
- `config/bot.example.json`：不含秘密的配置蓝图。
- `service/`：launchd/systemd 模板；本次选择为 `__SERVICE_KIND__`。

生成的服务文件只运行一次严格预检，不是常驻机器人服务。完成飞书、Codex 和所选连接器适配后，必须把它替换为真实 `serve` 入口并做测试租户 E2E；在此之前 manifest 会保持 `scaffold_only=true`。

## 接入顺序

1. 完成 `preflight` 与配置测试。
2. 实现飞书事件接收、回复和文件适配器，并验证事件去重。
3. 实现 Codex App Server 适配器，并建立“话题 → Agent 任务”映射。
4. 逐个接入只读知识、代码、数据库和日志能力。
5. 做重启恢复、重复事件、发送超时、撤回消息、权限失效和工具超时测试。
6. 完成真实环境 dry-run 后，才安装服务。

接入常驻 worker 时，轮询 `StateStore.ready_event_ids()` 取得每个话题的 FIFO 队首；失败使用 `schedule_retry()` 写入到期时间和次数。不要依赖飞书重复投递来推进队列。

## 秘密变量

模板只声明变量名，不包含值。常见变量包括：

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_VERIFICATION_TOKEN`（仅所选接入方式需要时）
- `DB_<ENV>_USER`
- `DB_<ENV>_PASSWORD`
- `LOG_PROVIDER_TOKEN`（仅所选日志平台需要时）

生产只读机器人不需要生产写账号。
