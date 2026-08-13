# Project bot rules

- Default to read-only diagnosis. Do not infer permission for real writes, deployments, restarts, messages, or permission changes.
- Treat a Feishu topic as one logical Agent task and preserve FIFO ordering within the topic.
- Keep authentication, authorization, idempotency, approvals, and delivery in deterministic adapters outside the model prompt.
- Never read credentials from this file, README files, source code, or generated artifacts.
- Never log secret values, authentication headers, cookies, connection strings, or raw sensitive query results.
- Require a dedicated read-only database principal. SQL text validation is defense in depth only.
- Add each tool as a bounded capability with an input schema, allowlist, timeout, output limit, audit fields, and explicit failure behavior.
- Keep `dry_run=true` and `allow_real_writes=false` until the user explicitly requests and reviews one exact write capability.
- Preserve existing user changes and keep project-specific facts in local configuration rather than the reusable framework.
- Before deployment, test duplicate events, restart recovery, delivery timeout, revoked authentication, denied SQL, missing allowlist, and tool timeout.
