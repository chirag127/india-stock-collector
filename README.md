# India Stock Collector

Private, local-first collecting & learning tool for one Indian retail investor.
Paper-trading-first. **Not investment advice. No profit, no-loss, or liquidity claims.**

## Architecture (read first)

- **Live dashboard:** local FastAPI app only (`http://127.0.0.1:8000`). Holds SQLite,
  calls Shoonya from the whitelisted machine/IP. One process, one launch command.
- **GitHub Pages (`docs/`):** static redacted simulator demo only. No broker code,
  database, credentials, user data, or order controls.
- **No hosted database** on the live path. No live orders from Actions/Pages/cloud/browser.
- Broker behind a `BrokerAdapter` interface (`app/broker.py`); `SimulatorBroker` is default.
  Live uses the official OAuth SDK (`NorenRestApiOAuth`, class `NorenApi`) only —
  no password/TOTP automation.

Conflict note: the brief asks for Windows Task Scheduler jobs and Python 3.12+.
Jobs are CLI commands (`python -m app.jobs ...`); scheduler registration is manual
(see below). Code targets 3.12+ but also runs on 3.11/3.13.

## Verified against official docs (2026-09-11)

- OAuth SDK: `NorenRestApiOAuth` / `NorenApi`, `getOAuthURL → getAccessToken →
  injectOAuthHeader`; `cred.yml` holds secrets (ignored). No auto-refresh.
- PlaceOrder: `LMT`/`SL-LMT` only (`MKT` rejected; `CO`/`BO` unsupported as `prd`),
  `C|M|I` products, `DAY|IOC`, `ordersource=API`, HTTP 200 for accept AND reject
  (check `stat`), 10 ops/sec documented — we throttle to **1 order/sec**.
- AMO: no AMO field in current PlaceOrder docs → `amo_enabled` defaults **off**;
  turning it on still requires the same review and labels intents `queued_amo`.

## Quick start (paper mode, no credentials)

```powershell
py -3.13 -m pip install -e ".[test]"
py -3.13 -m pytest
py -3.13 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000 — fixtures load automatically, mode = PAPER
```

Click **Queue → Rebuild candidates → Run paper simulation** to exercise
candidate → cost → reserve → simulate → audit end-to-end with zero network calls.

## Live trading (disabled by default)

All true at once, or nothing submits: `LIVE_TRADING_ENABLED=true` in local `.env`
(never committed); Shoonya OAuth connected; whitelisted IP; per-order/per-batch/
per-day guardrails set in Settings; typed confirmation phrase in Order review;
regular-session window (default 09:15–15:30 IST, trading days); kill switch off.
Each order is one CNC limit buy with a unique `remarks`; timeouts reconcile via
Order Book before any retry; no price is ever raised automatically.

## Scheduled jobs (Windows Task Scheduler, user registers manually)

- `python -m app.jobs refresh-reference` — daily, before market activity
- `python -m app.jobs refresh-filings` — daily, polite, keeps last-known-good
- `python -m app.jobs refresh-calendar` — optional
- No job submits live orders. Actions/CI runs tests + builds the static demo only.

## Layout

`app/` (config, db+migrations seed, models, eligibility, costs, broker adapters,
services, main routes, jobs, fixtures) · `templates/` (9 pages) · `static/`
· `tests/` (15 tests) · `docs/` (Pages demo) · `.env.example`

## Checks

```powershell
py -3.13 -m pytest
py -3.13 -m ruff check app tests
py -3.13 -m mypy app
```

## Limitations

- Reference importers cite official BSE/NSE URLs but run fixture-backed offline
  until the operator verifies current file formats; failures keep last-known-good.
- Charge schedule `v1` is an estimate (STT/stamp/exchange/GST/SEBI/broker flat);
  reconcile with contract notes. Surcharges not modelled.
- Surveillance (ASM/GSM) surfaces as `unknown` unless official data provides it.
