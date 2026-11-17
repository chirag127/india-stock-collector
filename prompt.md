# India Stock Collector — implementation brief

## Mission

Build a private, local-first web dashboard for a single Indian retail investor. It is a **collecting and learning tool**, not investment advice. It should discover eligible low-priced Indian equities, simulate and review one-share delivery purchases, maintain a shareholder-document/contact directory, and optionally submit carefully reviewed Shoonya orders.

The system must maximise transparency and control. It must never promise profit, a no-loss outcome, or liquidity.

## Decisions already made

- Broker: Shoonya/Finvasia, using its official OAuth Python SDK only.
- UI: web dashboard, not a command-line-only app.
- Runtime: one local process at `http://127.0.0.1:8000`; no separately deployed frontend and backend to maintain.
- Framework: Python 3.12+, FastAPI, Jinja2 templates, HTMX, SQLite, SQLAlchemy, Pydantic, and minimal vanilla CSS/JS. This is a single full-stack application, not a SPA plus API estate.
- Data: live Shoonya data plus end-of-day/reference data. Refresh official exchange reference files automatically each day.
- Orders: delivery/CNC only; regular-session orders and AMO support; limit orders only. No market, intraday, margin, short-selling, derivatives, or selling.
- Trading goal: maximise distinct eligible company holdings. Default candidate quantity is one share. This is configurable only in the local settings page.
- Retries: there is no lifetime retry limit. A candidate may be retried on later sessions, but the system must never spin in an infinite loop, submit duplicate orders, or raise the limit price automatically.
- Documents: keep annual-report and filing links; do not bulk-download PDFs. Create editable physical-report email drafts and CSV recipient exports. Never send email automatically.
- Notifications: do not implement push, email, Telegram, rejected-order, skipped-order, or budget-complete notifications.
- Source repository: public GitHub. It must contain no credentials, personal identifiers, holdings, contact exports, or private database.

## Important architecture resolution

GitHub Pages is static hosting. It cannot safely run a broker SDK, keep Shoonya secrets private, host SQLite, guarantee the IP required by broker API controls, or perform scheduled order execution. Therefore:

1. **Live dashboard:** local FastAPI site only. It holds the local SQLite database and calls Shoonya from the whitelisted machine/IP.
2. **GitHub Pages:** optional public read-only simulator/demo and redacted sample catalogue only. It must contain no real account data, real trades, credentials, login, or order controls.
3. **Hosted database:** do not use one for live trading. A free hosted database is neither a reliable private ledger nor a replacement for the local execution environment. Firebase may be evaluated later for a public demo login only, never for Shoonya secrets or live execution.

If a requirement conflicts with these boundaries, preserve the local live-trading design and explain the conflict in the README instead of weakening security.

## Security and compliance requirements

- This is strictly single-user software for the account owner; no multi-user brokerage platform features.
- Read the current Shoonya documentation before implementing authentication, AMO, order fields, rate limits, or static-IP behaviour. Do not infer endpoints from blogs or unofficial forks.
- Use the official OAuth SDK (`NorenRestApiOAuth` / official Shoonya OAuth repository). Do not automate password/TOTP login or embed Shoonya credentials in browser code.
- Store `SHOONYA_CLIENT_ID`, `SHOONYA_SECRET_CODE`, user ID, refresh/access tokens, and static-IP details only in local environment variables or a local ignored credential file. Never expose them in templates, JavaScript, logs, browser responses, GitHub Actions, screenshots, or error messages.
- Include `.env.example` with empty placeholders and an aggressive `.gitignore` for `.env`, `cred.yml`, `*.db`, `data/private/`, exports, logs, and tokens.
- Live trading must be disabled by default. Enable it only when all of these are true: an explicit local `LIVE_TRADING_ENABLED=true` setting exists; OAuth succeeds; the runtime is on the broker-whitelisted IP; the user types a deliberate confirmation phrase in the UI; and a complete pre-trade review passes.
- Never run live orders from GitHub Actions, GitHub Pages, a public cloud function, a browser-only client, or an unverified IP.
- Rate-limit order submission to one request per second by default, even though Shoonya documents up to 10 order operations/sec. Each order is a separate call for a separate symbol.
- Assign a unique `remarks` value to every order. On timeout or ambiguous response, reconcile with Shoonya Order Book using `remarks`, symbol, quantity, and price before any retry.
- Implement a visible kill switch that disables new live order submissions immediately. It must not alter existing broker orders without an explicit user action.

## Scope

### Company universe and eligibility

Create a daily importer for official BSE/NSE listings/security masters. Preserve raw source metadata, retrieval time, source URL, checksum, and last-known-good copy.

Create a configurable candidate policy with safe defaults:

- active, tradeable equities only;
- delivery/CNC eligible;
- default price ceiling ₹10, configurable locally, including shares below ₹1;
- no suspended, delisted, or explicitly broker-restricted symbols;
- exclude invalid/missing ISINs and duplicate ISINs across exchanges;
- require recent trading and a current executable sell-side quote before an order can be proposed;
- require a valid circuit band and reject a proposed price outside it;
- surface ASM/GSM/other surveillance status where official data is available; default to exclude when status is known to be restricted;
- choose the eligible venue with an executable ask and the lowest all-in estimated purchase cost; do not duplicate a company just because it trades on BSE and NSE.

Show every exclusion reason. Missing data means `unknown`, not an invented value.

### Trading workflow

Use Asia/Kolkata time and an explicit exchange-calendar service. Normal order submission is allowed only during configured regular-session windows on exchange trading days. Start with a configurable fallback of 09:15–15:30 IST and make the calendar/data source visible.

AMO must be supported only if the current Shoonya API/account supports the required AMO field. It queues an order; it is not permission to bypass the regular-session rule. Require the same pre-trade review and label the order as `queued_amo` until broker confirmation.

For every proposed order:

1. Fetch/consume current quote and market depth.
2. Calculate a limit price: use the best available ask only when it is within both the configured maximum-slippage rule and the upper circuit. Never chase a price after a miss.
3. Estimate all-in cost using an explicit, versioned charge schedule: share value, STT, stamp duty, exchange transaction charges, GST, SEBI/IPFT or other applicable levies, and broker charges. Mark it as an estimate, show inputs, and reconcile with the contract note later.
4. Reserve the estimated cost plus an automatically calculated safety buffer before it enters the queue. The buffer must be configurable and derived from price/circuit/rounding risk; never silently reserve a hard-coded arbitrary amount.
5. Verify available funds, duplicate holding/order state, daily/batch guardrails, circuit limits, and candidate eligibility.
6. In simulator mode, create a deterministic simulated result without calling Shoonya.
7. In live mode, require the typed confirmation phrase and submit one `CNC` limit order only.
8. Reconcile accepted, partial, rejected, cancelled, or timed-out orders from Order Book and order-update feed. A network error is not a failed order until reconciliation is complete.

Retry policy: cancel DAY orders at the appropriate broker/session boundary. Record the failure reason. Reconsider the same candidate only on a later eligible session, with a new quote and new all-in estimate. Never retry in a tight loop and never alter the price upward automatically.

There is no lifetime portfolio cap. However, live trading must not activate until the user sets explicit local per-order, per-batch, and per-day guardrails. The UI must show that these are safeguards, not investment recommendations.

### Paper trading

Paper trading is the default launch mode and must work fully without credentials. It uses downloaded reference data and recorded/sample quotes. It must exercise the exact candidate, charge-estimation, reserve, queue, retry, audit, and dashboard paths used by live mode.

No code path may place a live order from paper mode.

### Research, filings, reports, and shareholder contacts

For each company/ISIN, track where available:

- company name, symbol, ISIN, exchange, sector/industry, status, and source provenance;
- official BSE/NSE filing/company page URL;
- company investor-relations URL;
- annual-report URL and financial year;
- RTA name, website, and investor-service URL;
- investor-relations/company-secretary/RTA email address(es), source URL, last checked date, and verification status.

Do not mass-scrape websites, guess email addresses, or collect emails from uncontrolled third-party lists. Prefer official company/exchange/RTA sources. Allow the user to add or correct records manually, retain a source and timestamp, and flag records for review.

Provide a searchable contacts table, per-company edit history, and a CSV export/copy action for only user-selected verified email addresses. The user must explicitly select recipients; never create a bulk-mail send mechanism.

Generate an editable physical-annual-report request draft with placeholders for shareholder name, DP ID/client ID, company/ISIN, postal address, and financial year. Provide `mailto:` and clipboard-copy actions only. Explain in the UI that the user must verify shareholding and send each request personally.

### Dashboard pages

- **Overview:** data freshness, active mode (paper/live), kill-switch status, holding count, queue count, funds/reservations, and trade-audit status.
- **Universe:** every imported company, filters, eligibility result, exclusion reason, source links, and last refresh.
- **Candidate queue:** ranked distinct companies, quote/depth, limit price, all-in estimate, reservation, and review status.
- **Order review:** one clear approval screen before any live batch; no auto-submit on page load.
- **Simulator:** create/reset isolated simulated runs; compare proposed versus simulated fills/costs.
- **Orders and holdings:** immutable local audit trail plus reconciliation status; never imply an order was filled until broker data confirms it.
- **Company dossier:** filings, annual-report links, RTA/investor contacts, notes, and physical-report draft.
- **Contacts:** manual verification workflow, selected-recipient export, and no-send policy.
- **Settings and data health:** source URLs, import status, policy controls, fee-schedule version, market calendar, local guardrails, broker connection status, and kill switch.

## Data model

Use SQLite migrations. At minimum model: `companies`, `securities`, `exchange_listings`, `source_snapshots`, `market_quotes`, `eligibility_evaluations`, `candidate_attempts`, `order_intents`, `broker_orders`, `fills`, `holdings`, `charge_schedules`, `cost_estimates`, `fund_reservations`, `filings`, `annual_reports`, `investor_contacts`, `contact_sources`, `report_requests`, `settings`, and append-only `audit_events`.

All records that come from an external source need a source URL and retrieval/verification timestamp. Keep secrets out of the database wherever practical.

## Automated jobs

Provide local scheduled-job commands that the user can register with Windows Task Scheduler:

- daily reference-data refresh before market activity;
- daily filing/report/contact-link refresh with polite rate limits and last-known-good preservation;
- optional market-calendar refresh;
- no job may submit a live order automatically.

GitHub Actions may build/test the public repository and deploy the static demo only. It must never access live credentials, private data, or broker APIs.

## Implementation phases

1. Bootstrap the local FastAPI/HTMX app, SQLite migrations, settings, `.gitignore`, documentation, and paper-mode fixture data.
2. Build source snapshot/import interfaces and the candidate/eligibility engine with exhaustive tests.
3. Build the simulator, all-in cost estimator, reserve engine, audit trail, and dashboard.
4. Add filings/contact/draft-email workflows with provenance and manual corrections.
5. Add a Shoonya adapter behind an interface. Implement OAuth, instrument lookup, quote/depth, order book, and paper/live separation. Do not enable live placement yet.
6. Add live preflight, confirmation, one-order-per-second limiter, AMO only after documentation/account verification, reconciliation, and kill switch.
7. Add the public GitHub Pages demo with fabricated/redacted data only.

At the end of each phase, run tests and update README setup instructions.

## Acceptance criteria

- One command starts a local dashboard without any cloud account or credentials in paper mode.
- Paper mode can import fixture data, generate candidates, estimate costs, reserve funds, simulate fills, retry on later sessions, and show audit history without network calls to Shoonya.
- A candidate with missing/old quote, no executable ask, invalid ISIN, restriction, duplicate ISIN, or insufficient local guardrail fails visibly with a reason.
- The application never places orders on startup, refresh, background jobs, page load, or a GitHub deployment.
- Live placement is impossible without explicit opt-in, a whitelisted environment, pre-trade checks, and typed local confirmation.
- Every live order has a unique `remarks` value and can be reconciled after timeout without duplicate placement.
- The repository scans clean for secrets and excludes private data.
- The contacts workflow can export only selected, provenance-backed emails; it cannot bulk-send mail.
- GitHub Pages, if deployed, contains no live trading code, database, credentials, user data, or broker calls.

## Research sources to verify during implementation

- Shoonya API documentation: https://shoonya.com/api-documentation
- Shoonya official OAuth Python SDK: https://shoonya.com/api-documentation/python-sdk
- Shoonya order API and rate limits: https://shoonya.com/api-documentation/place-order
- Shoonya AMO field reference: https://shoonya.com/static/website/pdf/shoonya-Python-API.pdf
- BSE/NSE official listings, filings, holidays, and issuer pages — locate and cite the current official URLs; do not depend on unofficial scraped datasets.
- GitHub Pages static-hosting boundary: https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages
- Firebase Spark plan, only if a later public-demo login is proposed: https://firebase.google.com/docs/projects/billing/firebase-pricing-plans

## Non-goals

- investment advice, profit predictions, or no-loss claims;
- multi-user brokerage, account aggregation, margin, intraday, derivatives, selling, rebalancing, or copy trading;
- unattended live order placement;
- mass email dispatch or bulk downloading company reports;
- bypassing broker, exchange, website, IP-whitelisting, authentication, rate-limit, or anti-bot controls;
- paid data vendors, paid hosting, or paid databases for the initial local application.
