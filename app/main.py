"""Single-process local dashboard: FastAPI + Jinja2 + HTMX + SQLite. Binds 127.0.0.1."""
from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Form
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from . import models
from .broker import OrderRequest, ShoonyaBroker
from .config import get_settings, reset_settings_cache
from .db import (
    audit,
    get_session,
    init_db,
    is_kill_switch_on,
    setting_get,
    setting_set,
)
from .fixtures import load_fixtures
from .services import (
    build_candidates,
    create_paper_intents,
    ist_today,
    live_gate,
    make_remarks,
    paper_funds,
    reserved_total,
    throttle_ok,
)

BASE = Path(__file__).resolve().parent.parent
jinja = Environment(
    loader=FileSystemLoader(str(BASE / "templates")),
    autoescape=select_autoescape(["html"]),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    s = get_session()
    try:
        if s.query(models.Company).count() == 0:
            load_fixtures(s)
    finally:
        s.close()
    yield


app = FastAPI(title="India Stock Collector", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


def db() -> Session:
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def ctx(s: Session) -> dict:
    return {"kill_on": is_kill_switch_on(s)}


def render(name: str, **kw) -> HTMLResponse:
    return HTMLResponse(jinja.get_template(name).render(**kw))


def broker_status() -> str:
    cfg = get_settings()
    if cfg.paper_mode:
        return "simulator (paper)"
    return "shoonya-oauth (live-armed)" if cfg.shoonya_client_id else "simulator (no creds)"


@app.get("/", response_class=HTMLResponse)
def overview(s: Session = Depends(db)):
    cfg = get_settings()
    events = s.query(models.AuditEvent).order_by(models.AuditEvent.id.desc()).limit(20).all()
    snaps = s.query(models.SourceSnapshot).order_by(models.SourceSnapshot.id.desc()).limit(1).all()
    return render(
        "overview.html", title="Overview",
        live=not cfg.paper_mode,
        holdings=s.query(models.Holding).count(),
        queue=s.query(models.OrderIntent).count(),
        funds=paper_funds(s), reserved=reserved_total(s),
        freshness=snaps[0].retrieved_at if snaps else "fixtures only",
        calendar=setting_get(s, "market_calendar_source", "config-fallback 09:15-15:30 IST"),
        fees=setting_get(s, "fee_schedule_version", "v1"),
        blockers=cfg.live_blockers(), events=events, **ctx(s),
    )


@app.get("/universe", response_class=HTMLResponse)
def universe(q: str = "", f: str = "", s: Session = Depends(db)):
    cfg = get_settings()
    cands = {c["company"].id: c for c in build_candidates(s, cfg)}
    rows = []
    for comp in s.query(models.Company).order_by(models.Company.name).all():
        secs = s.query(models.Security).filter_by(isin=comp.isin).all()
        venue = ", ".join(f"{x.exchange}:{x.tsym}" for x in secs) or "—"
        blob = f"{comp.name} {comp.isin} {venue}".lower()
        if q and q.lower() not in blob:
            continue
        ev = (s.query(models.EligibilityEvaluation).filter_by(company_id=comp.id)
              .order_by(models.EligibilityEvaluation.id.desc()).first())
        eligible, reason = (ev.eligible, ev.reason) if ev else (False, "unknown")
        if f == "eligible" and not eligible:
            continue
        if f == "excluded" and eligible:
            continue
        rows.append({"company": comp, "venue": venue, "eligible": eligible, "reason": reason})
    void = cands  # noqa: F841 (evaluations persisted inside build_candidates)
    return render("universe.html", title="Universe", rows=rows, q=q, f=f, **ctx(s))


@app.get("/queue", response_class=HTMLResponse)
def queue(s: Session = Depends(db)):
    cfg = get_settings()
    cands = build_candidates(s, cfg)
    intents = s.query(models.OrderIntent).order_by(models.OrderIntent.id.desc()).limit(50).all()
    return render("queue.html", title="Queue", cands=cands, intents=intents, **ctx(s))


@app.post("/queue/build", response_class=HTMLResponse)
def queue_build(s: Session = Depends(db)):
    cfg = get_settings()
    cands = build_candidates(s, cfg)
    intents = s.query(models.OrderIntent).order_by(models.OrderIntent.id.desc()).limit(50).all()
    return render("queue.html", title="Queue", cands=cands, intents=intents, **ctx(s))


@app.post("/queue/paper-run", response_class=HTMLResponse)
def queue_paper(s: Session = Depends(db)):
    cfg = get_settings()
    if not cfg.paper_mode:
        audit(s, "paper_blocked_in_live", "paper-run refused while live-armed")
    else:
        create_paper_intents(s, cfg, build_candidates(s, cfg))
    cands = build_candidates(s, cfg)
    intents = s.query(models.OrderIntent).order_by(models.OrderIntent.id.desc()).limit(50).all()
    return render("queue.html", title="Queue", cands=cands, intents=intents, **ctx(s))


@app.get("/review", response_class=HTMLResponse)
def review(msg: str = "", s: Session = Depends(db)):
    cfg = get_settings()
    now = datetime.now(UTC)
    _ok, blockers = live_gate(s, cfg, phrase="__probe__", now=now)
    intents = s.query(models.OrderIntent).order_by(models.OrderIntent.id.desc()).limit(50).all()
    rows = []
    for i in intents:
        ce = s.query(models.CostEstimate).filter_by(intent_public_id=i.public_id).first()
        sec = s.get(models.Security, i.security_id)
        rows.append({"public_id": i.public_id, "tsym": sec.tsym if sec else "?",
                     "quantity": i.quantity, "limit_price": i.limit_price,
                     "total": ce.total if ce else 0.0, "status": i.status})
    return render("review.html", title="Order review", intents=rows,
                  blockers=[b for b in blockers if b != "confirmation phrase mismatch"],
                  msg=msg, **ctx(s))


@app.post("/review/live", response_class=HTMLResponse)
def review_live(phrase: str = Form(""), s: Session = Depends(db)):
    """Guarded live batch. Blocked unless every precondition passes. Never auto-fires."""
    cfg = get_settings()
    now = datetime.now(UTC)
    ok, blockers = live_gate(s, cfg, phrase=phrase, now=now)
    if not ok:
        audit(s, "live_blocked", "; ".join(blockers))
        return review(msg="BLOCKED: " + "; ".join(blockers), s=s)
    # Throttled, one CNC limit order per symbol, unique remarks, reconcile after.
    broker = ShoonyaBroker()
    try:
        broker.order_book()
    except RuntimeError as exc:
        audit(s, "live_blocked", str(exc))
        return review(msg="BLOCKED: " + str(exc), s=s)
    cands = build_candidates(s, cfg)
    placed = 0
    for c in cands:
        if not throttle_ok(cfg):
            audit(s, "throttled", "1 order/sec limiter held a submission")
            break
        public_id = f"live-{ist_today()}-{c['company'].isin}-{c['security'].exchange}"
        if s.query(models.OrderIntent).filter_by(public_id=public_id).first():
            continue
        intent = models.OrderIntent(
            public_id=public_id, company_id=c["company"].id,
            security_id=c["security"].id, quantity=cfg.default_quantity,
            limit_price=c["price"], remarks=make_remarks(public_id),
            mode="queued_amo" if cfg.amo_enabled else "live", status="submitted")
        s.add(intent)
        s.flush()
        resp = broker.place_order(OrderRequest(
            uid=cfg.shoonya_uid, actid=cfg.shoonya_uid,
            exchange=c["security"].exchange, tsym=c["security"].tsym,
            quantity=cfg.default_quantity, limit_price=c["price"],
            remarks=intent.remarks))
        s.add(models.BrokerOrder(intent_id=intent.id, norenordno=resp.norenordno,
                                 stat=resp.stat, emsg=resp.emsg,
                                 reconciled_status="pending"))
        s.commit()
        audit(s, "live_submitted" if resp.stat == "Ok" else "live_rejected",
              f"{intent.remarks} {resp.norenordno} {resp.emsg}")
        placed += 1
    return review(msg=f"Live batch attempted: {placed} submitted (see audit).", s=s)


@app.get("/simulator", response_class=HTMLResponse)
def simulator(s: Session = Depends(db)):
    fills = s.query(models.Fill).filter_by(source="simulator").order_by(
        models.Fill.id.desc()).limit(100).all()
    runs = []
    for fl in fills:
        bo = s.get(models.BrokerOrder, fl.broker_order_id)
        intent = s.get(models.OrderIntent, bo.intent_id) if bo else None
        runs.append({"intent": intent.public_id if intent else "?",
                     "qty": fl.quantity, "price": fl.price,
                     "ref": bo.norenordno if bo else ""})
    return render("simulator.html", title="Simulator", runs=runs, **ctx(s))


@app.post("/simulator/reset", response_class=HTMLResponse)
def simulator_reset(s: Session = Depends(db)):
    for m in (models.Fill, models.BrokerOrder, models.OrderIntent,
              models.FundReservation, models.CostEstimate, models.Holding,
              models.CandidateAttempt):
        s.query(m).delete()
    s.commit()
    audit(s, "simulator_reset", "isolated simulated runs cleared")
    return simulator(s)


@app.get("/orders", response_class=HTMLResponse)
def orders(s: Session = Depends(db)):
    holdings = [{"name": s.get(models.Company, h.company_id).name,
                 "qty": h.quantity, "avg": h.avg_price}
                for h in s.query(models.Holding).all()]
    rows = []
    for i in s.query(models.OrderIntent).order_by(models.OrderIntent.id.desc()).all():
        bo = s.query(models.BrokerOrder).filter_by(intent_id=i.id).first()
        rows.append({"intent": i.public_id, "mode": i.mode, "status": i.status,
                     "ref": bo.norenordno if bo and bo.norenordno else "—",
                     "rec": bo.reconciled_status if bo else "—"})
    return render("orders.html", title="Orders", holdings=holdings, orders=rows, **ctx(s))


@app.get("/company/{cid}", response_class=HTMLResponse)
def dossier(cid: int, s: Session = Depends(db)):
    comp = s.get(models.Company, cid)
    if comp is None:
        return HTMLResponse("unknown company", status_code=404)
    return render(
        "dossier.html", title=comp.name, company=comp,
        securities=s.query(models.Security).filter_by(isin=comp.isin).all(),
        filings=s.query(models.Filing).filter_by(company_id=cid).all(),
        reports=s.query(models.AnnualReport).filter_by(company_id=cid).all(),
        contacts=s.query(models.InvestorContact).filter_by(company_id=cid).all(),
        drafts=s.query(models.ReportRequest).filter_by(company_id=cid).all(), **ctx(s),
    )


DRAFT = (
    "To: [RTA / Company Secretary — see contacts above]\n"
    "Subject: Request for physical copy of Annual Report {fy} — {name} ({isin})\n\n"
    "Respected Sir/Madam,\n"
    "I hold equity shares of {name} (ISIN {isin}). Kindly send a physical copy of "
    "the Annual Report for {fy} to:\n[Shareholder name]\n[DP ID / Client ID]\n[Postal address]\n\n"
    "I confirm I will verify my holding before sending this request personally.\n"
)


@app.post("/company/{cid}/draft", response_class=HTMLResponse)
def make_draft(cid: int, fy: str = Form("2024-25"), s: Session = Depends(db)):
    comp = s.get(models.Company, cid)
    if comp is None:
        return HTMLResponse("unknown company", status_code=404)
    text = DRAFT.format(fy=fy, name=comp.name, isin=comp.isin)
    s.add(models.ReportRequest(company_id=cid, financial_year=fy, draft_text=text))
    s.commit()
    audit(s, "draft_created", f"company {cid} fy {fy}")
    return dossier(cid, s)


@app.get("/contacts", response_class=HTMLResponse)
def contacts(q: str = "", s: Session = Depends(db)):
    rows = []
    for c in s.query(models.InvestorContact).all():
        comp = s.get(models.Company, c.company_id)
        blob = f"{comp.name if comp else ''} {c.email} {c.kind}".lower()
        if q and q.lower() not in blob:
            continue
        rows.append({"id": c.id, "company": comp.name if comp else "?",
                     "kind": c.kind, "email": c.email, "verified": c.verified,
                     "source_url": c.source_url})
    return render("contacts.html", title="Contacts", contacts=rows, q=q, **ctx(s))


@app.post("/contacts/verify", response_class=HTMLResponse)
def contacts_verify(contact_id: int = Form(0), s: Session = Depends(db)):
    c = s.get(models.InvestorContact, contact_id)
    if c:
        c.verified = not c.verified
        s.add(models.ContactSource(contact_id=c.id, source_url=c.source_url or "manual",
                                   note="manual verification toggle"))
        s.commit()
        audit(s, "contact_verified" if c.verified else "contact_unverified",
              f"contact {c.id}")
    return contacts(s=s)


@app.get("/contacts/export")
def contacts_export(ids: str = "", s: Session = Depends(db)):
    wanted = {x.strip() for x in ids.split(",") if x.strip()}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["company", "kind", "name", "email", "source_url", "last_checked"])
    for c in s.query(models.InvestorContact).all():
        if str(c.id) not in wanted or not c.verified or not c.email:
            continue  # only selected + verified + provenance-backed
        comp = s.get(models.Company, c.company_id)
        w.writerow([comp.name if comp else "", c.kind, c.name, c.email,
                    c.source_url, c.last_checked])
    audit(s, "contacts_export", f"{len(wanted)} requested (verified-only)")
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=recipients.csv"})


@app.get("/settings", response_class=HTMLResponse)
def settings(msg: str = "", s: Session = Depends(db)):
    cfg = get_settings()
    snapshots = s.query(models.SourceSnapshot).order_by(
        models.SourceSnapshot.id.desc()).limit(20).all()
    return render(
        "settings.html", title="Settings",
        s={"price_ceiling_inr": setting_get(s, "price_ceiling", str(cfg.price_ceiling_inr)),
           "default_quantity": setting_get(s, "default_quantity", str(cfg.default_quantity)),
           "max_slippage_pct": setting_get(s, "max_slippage", str(cfg.max_slippage_pct)),
           "safety_buffer_pct": setting_get(s, "safety_buffer", str(cfg.safety_buffer_pct)),
           "per_order_cap_inr": setting_get(s, "per_order_cap", "0"),
           "per_batch_cap_inr": setting_get(s, "per_batch_cap", "0"),
           "per_day_cap_inr": setting_get(s, "per_day_cap", "0"),
           "session_start": setting_get(s, "session_start", cfg.session_start_ist),
           "session_end": setting_get(s, "session_end", cfg.session_end_ist),
           "paper_funds": setting_get(s, "paper_funds_inr", "100000")},
        broker=broker_status(),
        amo="UNVERIFIED — off" if not cfg.amo_enabled else "enabled by local operator",
        snapshots=snapshots, msg=msg, **ctx(s),
    )


@app.post("/settings", response_class=HTMLResponse)
def settings_save(
    price_ceiling_inr: str = Form("10"), default_quantity: str = Form("1"),
    max_slippage_pct: str = Form("0.5"), safety_buffer_pct: str = Form("2.0"),
    per_order_cap_inr: str = Form("0"), per_batch_cap_inr: str = Form("0"),
    per_day_cap_inr: str = Form("0"), session_start: str = Form("09:15"),
    session_end: str = Form("15:30"), paper_funds: str = Form("100000"),
    s: Session = Depends(db),
):
    for k, v in {"price_ceiling": price_ceiling_inr, "default_quantity": default_quantity,
                 "max_slippage": max_slippage_pct, "safety_buffer": safety_buffer_pct,
                 "per_order_cap": per_order_cap_inr, "per_batch_cap": per_batch_cap_inr,
                 "per_day_cap": per_day_cap_inr, "session_start": session_start,
                 "session_end": session_end, "paper_funds_inr": paper_funds}.items():
        setting_set(s, k, v)
    reset_settings_cache()
    return settings(msg="Saved locally.", s=s)


@app.post("/kill", response_class=HTMLResponse)
def kill(s: Session = Depends(db)):
    on = is_kill_switch_on(s)
    setting_set(s, "kill_switch", "off" if on else "on")
    audit(s, "kill_released" if on else "kill_engaged", "operator action")
    return settings(msg="Kill switch released." if on else "Kill switch ENGAGED.", s=s)


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"


def run() -> None:
    import uvicorn
    cfg = get_settings()
    uvicorn.run("app.main:app", host=cfg.app_host, port=cfg.app_port)


if __name__ == "__main__":
    run()
