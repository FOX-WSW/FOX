# Acceptance Matrix

## Static and unit checks

- Skill metadata validation passes.
- Generated scaffold contains no unresolved template tokens.
- Generated scaffold reports `scaffold_only=true` and `deployment_ready=false` until real adapters and live tests exist.
- Secret scan finds no credential values or internal addresses.
- Configuration rejects an empty live chat allowlist.
- Live configuration rejects an implicit project root and a state path outside its approved root.
- Defaults are `dry_run=true` and `allow_real_writes=false`.
- SQL policy rejects DML/DDL, multiple statements, locking clauses, and known side-effect packages.
- Topic state deduplicates the same event ID and the same Feishu message ID.
- Topic state preserves FIFO ordering.
- Delivery cannot become `delivered` without a verifiable external message ID.
- Approval records bind exact parameters and cannot execute twice.

## Fault injection

- Duplicate Feishu event
- Event stream disconnect and reconnect
- Service restart before and after answer persistence
- Codex timeout before any tool call
- Codex timeout after successful tools but before synthesis
- Database timeout, permission denial, and malformed SQL
- Feishu reply timeout, 429, ambiguous result, and withdrawn source message
- Artifact upload succeeds but local acknowledgement is lost
- State database locked or temporarily unavailable
- Secret/authentication revoked during operation

Every path must become either a verified success, a scheduled retry, a cancellation, or a visible failure. No message may remain silently `processing`.

## Live read-only checks

Perform only when authorized:

- Verify bot identity and event subscription.
- Resolve target chat IDs and confirm the allowlist.
- Receive one controlled dry-run mention without sending a reply.
- Send one controlled reply in a test chat.
- Run one bounded query per configured read-only data source.
- Fetch one bounded log sample.
- Restart the service with an empty queue and verify readiness.
- Restart during a synthetic turn and verify recovery.

## Production readiness evidence

Record:

- exact source revision;
- non-secret configuration snapshot;
- validation commands and results;
- live checks performed and skipped;
- service status and health output;
- state backup path;
- rollback command;
- secret owner and rotation procedure;
- enabled capability list.
