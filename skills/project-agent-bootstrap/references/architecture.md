# Reference Architecture

## Target flow

```text
Feishu event adapter
  -> ingress policy and durable idempotency
  -> topic FIFO and Agent thread mapping
  -> Codex Agent runtime
       -> knowledge/code reader
       -> capability gateway
            -> read-only database adapter
            -> read-only log adapter
            -> read-only Git ref adapter
            -> delivery registration
  -> persisted final answer
  -> idempotent Feishu delivery
  -> reconciliation and audit
```

## Required module boundaries

Keep these modules separate even for a small project:

1. `config`: typed settings, secret references, fail-closed validation.
2. `ingress`: Feishu event parsing, chat/sender allowlists, mention handling.
3. `state`: topic, turn, tool, approval, answer, and delivery state.
4. `agent_runtime`: Codex Thread/Turn lifecycle and bounded synthesis.
5. `capabilities`: one adapter per external system with explicit schemas.
6. `policy`: authorization and side-effect checks independent of business intent.
7. `delivery`: reply, artifact, mention, retry, and reconciliation.
8. `operations`: health, metrics, retention, backup, migration, and service control.

Do not place configuration parsing, database connections, Feishu delivery, business heuristics, and state transitions in one event handler.

## Reasoning versus policy

Let Codex decide:

- whether code, data, logs, or documents are relevant;
- which safe tool to call;
- how to combine evidence;
- how to answer follow-ups.

Let deterministic policy decide:

- who may trigger the bot;
- which environment, schema, repo, namespace, or file root is allowed;
- whether an operation is read-only or requires exact approval;
- timeout, row, size, concurrency, and call budgets;
- idempotency and terminal-state validity.

Do not create an ever-growing business-keyword router outside the Agent.

## Topic and reliability model

Use one logical Agent thread per Feishu topic. Store every incoming message before starting work. Serialize turns per topic, but allow independent topics to run concurrently.

Model at least these durable states:

```text
received -> queued -> active -> answer_persisted -> delivery_pending -> delivered
                    \-> retry_pending
                    \-> cancelled
                    \-> failed_visible
```

Require these invariants:

- One message ID can be claimed once.
- A later turn cannot pass an unfinished earlier turn in the same topic.
- No success state exists without a persisted answer.
- No delivered state exists without a verifiable external message ID.
- A retry reuses the same operation/idempotency key.
- A withdrawn source message releases the queue without inventing a reply.
- Restart recovery is deterministic and independently testable.

## Database model

Use a dedicated, least-privilege, read-only principal for every environment. Add application checks only as defense in depth:

- accept one statement;
- accept `SELECT`/`WITH` only;
- reject locking clauses and known side-effect packages;
- set timeout and row limits;
- set a read-only transaction/session where supported;
- redact sensitive columns;
- log normalized query hashes and environment, never credentials.

For privileged or owner accounts, a `SELECT` can still invoke a user-defined function or package with side effects. Do not expose such accounts through a free-form query tool.

## Migration from a monolith

Extract in this order while preserving behavior:

1. Typed settings and secret providers.
2. Database migrations and repository layer.
3. Feishu adapter and delivery adapter.
4. Codex App Server client.
5. Capability gateway and individual tools.
6. Approval registry.
7. Learning/analytics into a separate process.
8. Remove unreachable legacy routes and stale documentation.

Add characterization tests before each extraction. Avoid a simultaneous rewrite of transport, state, and runtime.
