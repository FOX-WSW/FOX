---
name: project-agent-bootstrap
description: Build, modernize, or audit a project-specific intelligent bot with Feishu/Lark and Codex, including requirements intake, secure scaffolding, read-only data/code/log tools, topic-level sessions, reliability controls, validation, and deployment preparation. Use when a user asks to quickly create a project bot, reproduce an existing project assistant for another project, collect the Feishu/database/environment information needed for setup, generate a reusable bot starter, or assess whether a bot is safe to deploy.
---

# Project Agent Bootstrap

Build a project bot from a small, security-first foundation. Keep business reasoning inside the Agent runtime and keep authentication, authorization, idempotency, and side-effect control in deterministic outer adapters.

## Choose the work mode

Identify the requested mode before changing files:

- `intake`: list what the user must provide and produce a fillable blueprint.
- `scaffold`: generate a new starter project from `assets/project-bot-starter/`.
- `integrate`: connect Feishu, Codex, databases, code repositories, logs, or document delivery.
- `audit`: inspect an existing bot and rank changes by safety, reliability, and maintainability.
- `deploy`: validate and install a service only after the user explicitly authorizes the external writes involved.
- `publish`: upload only the sanitized reusable Skill or scaffold to an explicitly selected GitHub destination.

Combine modes when requested. For an existing bot, audit first and preserve unrelated user changes.

## Collect the minimum project facts

Read [references/intake-checklist.md](references/intake-checklist.md) whenever required facts are missing. Resolve facts from the workspace before asking the user.

Ask only for decisions that materially change the result. Never ask the user to paste real passwords, tokens, cookies, private keys, or production connection strings into chat. Ask them to place secrets in their approved secret store or local environment and provide only the environment-variable names or a confirmation that they are set.

At minimum, establish:

1. Project name, project root, business scope, owners, and expected answer style.
2. Feishu tenant/app readiness, bot identity, event subscription, target chat allowlist, and needed scopes.
3. Codex path/version, runtime model, sandbox, timeout, and topic-session policy.
4. Each data source's engine, environment label, read-only account, schema, network/VPN needs, row limit, and timeout.
5. Code repositories, allowed branches, documentation roots, log provider, and artifact types.
6. Host OS, service manager, working directory, retention, monitoring, and rollback expectations.
7. Whether any real write capability is required. Default to none.

If credentials are not ready, continue with placeholders and a preflight report instead of blocking the scaffold.

## Generate the starter safely

Run the bundled scaffolder for a new project:

```bash
python scripts/scaffold_project_bot.py \
  --name "示例项目智能机器人" \
  --slug "example-project-bot" \
  --output "/absolute/output/path" \
  --service launchd \
  --databases oracle \
  --database-env UAT:oracle \
  --database-env PROD_DG:oracle
```

Use `systemd` or `none` for other deployment targets. Supply `--slug` for Chinese or other non-ASCII project names. The script refuses to overwrite a non-empty directory and never accepts secret values as arguments.

The generated starter is intentionally small and sets `scaffold_only=true`. Its service file is a one-shot strict preflight template, not a running bot. Extend its adapter interfaces, add a real `serve` entrypoint, and complete live tests before changing the readiness marker. Follow [references/architecture.md](references/architecture.md) for module boundaries and migration order.

## Apply hard safety defaults

Keep these defaults unless the user explicitly narrows and authorizes a change:

- Require a non-empty chat allowlist; fail startup when it is absent.
- Set `dry_run=true` and `allow_real_writes=false`.
- Use genuinely read-only database principals. Treat SQL text inspection as defense in depth, not the primary permission boundary.
- Store credentials only in environment variables or a secret manager. Never parse credentials from `AGENTS.md`, README files, source code, service files, or generated artifacts.
- Allowlist environments, schemas, repositories, branches, namespaces, file roots, and delivery targets.
- Bind approval to the original requester, topic, exact operation hash, expiry, and one-time consumption.
- Separate answer generation from Feishu delivery. Persist the answer before attempting external delivery.
- Make one Feishu topic one logical Agent thread and process turns FIFO with durable idempotency.
- Keep production writes disabled. Do not request production write credentials for a read-only assistant.

Read [references/security-boundaries.md](references/security-boundaries.md) before adding database, log, deployment, or write tools.

## Implement in layers

Build in this order:

1. Preflight and configuration validation.
2. Feishu event receive/read/reply adapter with allowlists and idempotency.
3. Durable topic/turn state and restart recovery.
4. Codex topic runtime with bounded tools and visible terminal outcomes.
5. Read-only knowledge, code, database, and log tools.
6. Artifact delivery and exact one-time approval capabilities.
7. Service installation, health checks, retention, and rollback.

Do not mix project-specific table names, stored procedures, chat IDs, internal addresses, or usernames into the generic framework. Put project facts in local configuration and project-owned references.

## Validate before deployment

Run the skill validator and generated-project checks:

```bash
python /path/to/skill-creator/scripts/quick_validate.py /path/to/project-agent-bootstrap
python scripts/validate_scaffold.py /path/to/generated-project
PYTHONPATH=/path/to/generated-project/src python -m unittest discover -s /path/to/generated-project/tests -v
```

The Skill Creator validator imports PyYAML. Run it with an environment that already provides `yaml`; do not add PyYAML to the generated bot merely for this external validation step. `validate_scaffold.py` certifies scaffold hygiene only and intentionally reports `deployment_ready=false`. Live adapter evidence, fault tests, and an implemented `serve` entrypoint require a separate deployment review.

Then follow [references/acceptance-matrix.md](references/acceptance-matrix.md). Test failure paths as first-class behavior: duplicate events, restart during a turn, delivery timeout, revoked auth, SQL denial, missing allowlist, tool timeout, and withdrawn source messages.

Do not claim deployment readiness when only mocked tests passed. State which live checks remain.

## Deploy and hand off

Before installing or restarting a service:

1. Show the resolved non-secret configuration and intended external effects.
2. Confirm the queue is idle or use a graceful drain.
3. Back up the state database.
4. Confirm `scaffold_only=false`, then install the rendered service definition whose command starts the implemented `serve` entrypoint. Do not install the generated preflight-only template as the bot service.
5. Verify process health, Feishu event readiness, one dry-run message, and restart recovery.
6. Record start, stop, status, rollback, log, and secret-rotation procedures.

Never send a real Feishu message, create cloud resources, change permissions, or enable write tools unless the user's request explicitly authorizes that action.

For GitHub publishing, read the exact staged file list and diff, run both a dedicated secret scanner and the bundled heuristic check, and exclude all instance configuration, state, logs, attachments, credentials, internal addresses, and real IDs. If the user did not name a repository, prefer a new private repository; do not silently put company-specific material in a public profile repository.

## Deliverables

Return:

- the completed non-secret intake summary;
- the generated project path;
- enabled and disabled capabilities;
- validation results and live checks not performed;
- required secret variable names without values;
- deployment/rollback commands when deployment was requested;
- a prioritized audit when modernizing an existing bot.
