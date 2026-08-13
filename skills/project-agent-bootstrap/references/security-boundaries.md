# Security Boundaries

## Secret handling

- Keep secret values out of Git, `AGENTS.md`, README files, service definitions, logs, screenshots, generated documents, and prompts.
- Use environment-variable names, OS keychains, vault references, or deployment-managed secret injection.
- Provide `.env.example`, never a populated `.env`.
- Redact authentication headers, cookies, tokens, passwords, connection strings, phone numbers, and private keys before logging.
- Scan the exact Git diff before publishing.

## Fail-closed startup

Refuse live startup when any required control is missing:

- empty chat allowlist;
- unverified bot identity;
- missing project root;
- writable production database credential;
- unknown environment label;
- state directory outside the approved root;
- real writes enabled without a capability registry.

Allow a separate `--preflight` or dry-run mode to report missing inputs without sending messages.

## Database controls

Use three layers:

1. Database grants: dedicated read-only principal with minimal objects.
2. Session controls: read-only transaction/session and statement timeout where supported.
3. Application policy: parser/lexer checks, environment allowlist, row limit, redaction, and audit.

Block known side-effect surfaces such as network, file, scheduler, Java, queue, pipe, alert, or lock packages. Because user-defined functions may still have side effects, never treat application SQL validation as a replacement for least privilege.

## Tool controls

Define each capability with:

- name and purpose;
- exact JSON input schema;
- environment/resource allowlist;
- timeout and output limit;
- idempotency behavior;
- audit fields;
- failure classification;
- whether explicit approval is required.

Do not expose arbitrary shell, arbitrary PL/SQL, unrestricted browser automation, Kubernetes exec, or cloud-admin tools to the Agent.

## Approval controls

Bind approval to:

- original topic and requester;
- exact capability and normalized parameter hash;
- environment;
- expiry;
- one execution;
- final audit result.

An approval response must not change parameters or authorize future operations.

## Publishing controls

Before GitHub upload:

1. Include only generic skill/template files.
2. Exclude state databases, logs, attachments, generated evidence, `.env`, service files with real IDs, internal addresses, credentials, and organization-specific procedures.
3. Run a secret scan and inspect the file list.
4. Prefer a new private repository when content contains any company-specific material.
5. For a public repository, include only sanitized examples and placeholders.
