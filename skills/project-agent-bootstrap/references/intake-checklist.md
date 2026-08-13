# Project Bot Intake Checklist

Use this checklist to collect only what is needed. Prefer discovering local facts over asking the user to repeat them. Mark missing secrets as `set locally` or `not ready`; never record secret values in this file.

## 1. Project and users

- Project display name and short slug
- Project root and expected artifact directory
- Business scope and explicit out-of-scope topics
- Primary users, administrators, and approval owners
- Preferred language, tone, and answer structure
- Authoritative knowledge order: `AGENTS.md`, wiki, docs, code, database, logs
- Retention and privacy classification

## 2. Feishu/Lark

Required for a Feishu bot:

- Tenant/region: Feishu China or Lark international
- Existing app/bot or permission to create one
- Bot display name and unique mention names
- Authentication method: existing `lark-cli` bot identity, official SDK, or another approved adapter
- Event subscription: normally `im.message.receive_v1`
- Target chat allowlist: chat names plus resolved IDs
- Whether P2P messages are allowed; default `false`
- Required scopes for message read/reply, reactions, files, contacts, docs, or wiki
- User identity needed for online-document creation, if any
- Attachment size/type limits
- Reply-in-thread and mention behavior
- Event verification or long-connection requirements

Do not request app secret, user token, bot token, cookies, or master-key contents in chat. Ask the user to authenticate locally and verify readiness.

## 3. Codex runtime

- Codex CLI path and version
- App Server support confirmed or not
- Model and reasoning effort
- Workspace/sandbox boundary
- Topic policy: one Feishu topic to one logical thread
- Per-turn timeout, final-answer reserve, tool-call budget, and concurrency
- Thread archive/retention rule
- Whether images and local files may be passed to Codex
- Weekly quota telemetry needed or not

## 4. Knowledge and code

- Project instruction file path; it must not contain credentials for the bot to parse
- Knowledge-base paths and freshness rules
- Repository roots, owners, default branches, and allowlisted remote branches
- Whether remote fetch is allowed; default read-only refs only
- Build/test tools and the exact user wording that authorizes their execution
- File types that may be generated and delivered

## 5. Databases

Repeat for every environment and engine:

- Logical environment label: DEV, SIT, UAT, PROD_DG, PROD, etc.
- Engine and driver: Oracle, PostgreSQL, MySQL, other
- Host, port, service/database name, and schema
- Read-only principal name and how its password is provided locally
- Network/VPN dependency and connection probe
- Maximum query time and row count
- Allowed schemas/views and sensitive columns to redact
- Whether metadata queries are allowed
- Whether user-defined functions or external packages are callable
- Whether the connection/session can be forced read-only

Prefer a dedicated read-only principal with no `EXECUTE`, DDL, DML, network package, scheduler, file, or Java permissions. Do not rely on keyword scanning to make a powerful account safe.

## 6. Logs and infrastructure

- Log provider: Rancher/Kubernetes, files, Sentry, another system
- Environments, clusters, namespaces, workloads, containers, and allowed log roots
- Read-only credentials or authenticated local CLI
- Tail/window limits and redaction rules
- Whether VPN recovery is permitted
- Explicitly forbidden operations: restart, scale, delete, deploy, exec shell

## 7. Deployment and operations

- Host OS and architecture
- Python/runtime path and dependency strategy
- Service manager: launchd, systemd, container, manual
- Working directory, state path, log path, and artifact path
- Health check, monitoring, log rotation, and backup
- Graceful drain and restart behavior
- Rollback version/source
- Who rotates secrets and how often

## 8. Optional write capabilities

Default to no write capabilities. For each requested capability, collect:

- Exact business operation and environment
- Deterministic executor, not free-form shell or SQL
- Exact parameter schema and allowlist
- Requester/approver rules
- Expiry, one-time consumption, idempotency key, and audit evidence
- Dry-run/preview behavior
- Rollback or compensating action

Never generalize one approved operation into arbitrary database, browser, shell, cloud, or production access.

## 9. GitHub publishing

- Account or organization
- Existing repository or authorization to create one
- Repository name, visibility, default branch, and license
- Whether company intellectual property is approved for publication
- CI and secret-scanning expectations
- Exact content scope: generic Skill, generated scaffold, project profile, or application source

Default to a new private repository when the destination or intellectual-property status is unclear. A public repository may contain only sanitized generic files and placeholders. Publishing is an external write; perform it only when the user explicitly requests it.

## Intake completion states

- `ready_to_scaffold`: project identity and deployment target known; secrets may still be placeholders.
- `ready_for_dry_run`: Feishu auth and allowlist verified; no real replies required.
- `ready_for_live_readonly`: live message and read-only tool checks passed.
- `ready_for_write_capability`: exact executor and approval workflow independently reviewed.
