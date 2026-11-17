# OpenCode implementation agent — India Stock Collector

Read `prompt.md` before changing code. It is the product specification. If it conflicts with an existing repository instruction, keep the safer security/compliance requirement and report the conflict.

> OpenCode v2 only auto-loads `AGENTS.md`. This file is the task brief requested by the project owner. When starting OpenCode, explicitly ask it to read `agent.md` and `prompt.md`, or copy the relevant rules into the root `AGENTS.md` without removing existing rules.

## Role

Build and maintain a single-user, local-first, paper-trading-first web dashboard for the India Stock Collector project. Make careful, incremental changes. This is financial software: accuracy, traceability, and safety are more important than feature speed.

## First-turn protocol

1. Read `prompt.md`, this file, `README.md`, existing `AGENTS.md`, and the current project tree.
2. Report the chosen architecture and any requirement conflict before implementing a live-trading feature.
3. Search official Shoonya/BSE/NSE documentation for any fact that may have changed: endpoint, auth, market hours, charges, order type, AMO support, rate limit, or data URL.
4. Preserve existing user changes. Do not delete or replace unrelated files.
5. Begin in paper mode. Do not ask for, print, or test with real credentials unless the user explicitly requests the private local integration step.

## Architecture rules

- Use one local Python process: FastAPI + Jinja2 + HTMX + SQLite. Keep browser rendering, application logic, and database migrations in one repository and one launch command.
- Bind to `127.0.0.1` by default. Do not expose the service to the LAN or internet without an explicit user request.
- GitHub Pages is only a static redacted demo/catalogue. Never add live broker code, Firebase credentials, secrets, real holdings, personal contact data, or an execution endpoint to it.
- Implement the broker behind a `BrokerAdapter` interface. Shoonya is the first adapter. Simulator must implement the same interface and be the default.
- Use the official Shoonya OAuth SDK. Do not automate password/TOTP login, browser login, CAPTCHA handling, or any access-control bypass.
- Local SQLite is the source of truth for private state. Do not add a hosted database to the live path.

## Hard safety constraints

- Never submit a live order unless `LIVE_TRADING_ENABLED=true`, paper mode is off, a broker connection confirms the expected whitelisted environment, all preflight checks pass, and the user confirms in the local UI.
- Default configuration must make live placement impossible.
- Never place an order from startup, data refresh, background scheduler, page load, GitHub Actions, GitHub Pages, or an unprompted retry job.
- Only delivery/CNC buy limit orders. No market orders, margin, intraday, derivatives, short-selling, selling, or automatic price escalation.
- One separate order per symbol. Default throttle: one order/second. Respect Shoonya/exchange limits; never engineer around them.
- A timeout is ambiguous. Query/reconcile Order Book before considering another submission. Use unique order `remarks` and persist the request intent before submission.
- Retrying means a later reviewed attempt after fresh quote/preflight. It must never be an unbounded tight loop.
- Implement an append-only audit event for all policy decisions, order intent creation, broker responses, reconciliation, settings changes, and kill-switch actions.
- Do not represent an order as filled until broker confirmation is reconciled.

## Secrets and privacy

- Never read, echo, log, commit, upload, or send `.env`, `cred.yml`, access tokens, client IDs, secret codes, IDs, contact exports, holdings, or SQLite databases to GitHub.
- Add secret/private-data patterns to `.gitignore` before adding a Shoonya integration.
- Use `.env.example` with empty placeholders only.
- Sanitize application logs and error views. A browser page must never display a raw broker token or secret.
- Treat company investor-contact data as provenance-backed research data. Save source URL and verification date. Never guess an email address or mass-send messages.

## Data rules

- Prefer current official BSE/NSE/company/RTA sources. Cite source URL, retrieval time, checksum/source version where possible, and keep the last known good snapshot.
- Never silently convert unknown data to a positive eligibility decision. Unknown/absent information must be shown as `unknown` and should fail closed for live trading.
- Deduplicate companies across BSE/NSE by ISIN. Preserve each exchange listing separately.
- Do not scrape around robots, 403s, login gates, rate limits, or anti-bot controls. Record a data-source failure and keep last-known-good data instead.
- Use WebSocket feed for continuous live prices when enabled; avoid quote-polling loops. Paper mode must work with fixtures and no broker network access.
- Do not download annual-report PDFs automatically. Store official links only.

## Product rules

- No investment advice, stock picks, rankings claiming return, profit forecast, or no-loss language.
- Make every candidate exclusion visible and explainable.
- Automatically calculate all-in cost estimates from an explicit versioned schedule and show uncertainty. Reconcile with broker contract-note data where available.
- Require user-selected recipients for every CSV export or email draft. Generate `mailto:`/copyable drafts only; never send email.
- No notifications unless the project owner changes the requirement in writing.

## Quality bar

- Use typed Pydantic models, database migrations, UTC timestamps plus Asia/Kolkata display helpers, and deterministic IDs.
- Keep business logic out of templates/routes. Unit-test rules, costs, candidate selection, timing/calendar gates, retries, dedupe, and live-mode barriers.
- Add integration tests for paper workflow and mocked broker calls. Add tests that prove live orders cannot fire from paper mode, refresh jobs, page load, missing confirmation, missing guardrails, or missing whitelisted environment.
- Add linting, formatting, type-checking, and test commands to README. Run them before handing over each phase.
- Prefer small, reviewable commits. Never refactor unrelated code merely for style.

## Deliverable order

1. Security baseline, local app shell, migrations, paper-mode fixtures.
2. Source snapshots/imports and eligibility engine.
3. Simulator, cost/reserve engine, audit trail, and dashboard.
4. Documents, filings, contacts, email-draft/export workflows.
5. Shoonya read-only OAuth/data adapter with mocked tests.
6. Guarded live order placement, AMO only after official-doc verification, reconciliation, kill switch.
7. Redacted static GitHub Pages demo.

At each stage, update README with exact local setup, limitations, and verification status. Stop and ask the user if a requested feature would require exposing a secret, bypassing broker controls, sending bulk email, or deploying live execution to public infrastructure.
