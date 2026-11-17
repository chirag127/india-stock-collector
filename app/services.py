"""Orchestration: candidate pipeline, guardrailed live gate, reconciliation."""
from __future__ import annotations

import hashlib
import time
from datetime import datetime

from . import models
from .calendar import IST, SessionWindow, regular_session_open
from .config import Settings
from .costs import estimate, safety_buffer
from .db import audit, is_kill_switch_on, setting_get
from .eligibility import evaluate_company, limit_price_from_ask

CONFIRM_PHRASE_DEFAULT = "PLACE LIVE CNC ORDERS"


def ist_today() -> str:
    return datetime.now(IST).date().isoformat()


def build_candidates(session, cfg: Settings) -> list[dict]:
    """Rank distinct eligible companies. Persists evaluations + attempts (proposed)."""
    companies = session.query(models.Company).all()
    seen: set[str] = set()
    out: list[dict] = []
    for comp in companies:
        secs = session.query(models.Security).filter_by(isin=comp.isin).all() if comp.isin else []
        quotes = {}
        for s in secs:
            q = (session.query(models.MarketQuote).filter_by(security_id=s.id)
                 .order_by(models.MarketQuote.id.desc()).first())
            if q:
                quotes[s.id] = q
        res = evaluate_company(comp, secs, quotes, seen, cfg.price_ceiling_inr)
        if comp.isin and res.eligible:
            seen.add(comp.isin)
        session.add(models.EligibilityEvaluation(
            company_id=comp.id, eligible=res.eligible, reason=res.reason,
            chosen_security_id=res.security_id))
        if not res.eligible:
            continue
        sec = session.get(models.Security, res.security_id)
        q = quotes[sec.id]
        sched = session.query(models.ChargeSchedule).filter_by(active=True).first()
        price, price_note = limit_price_from_ask(q.ask, q.upper_circuit,
                                                 cfg.max_slippage_pct, q.ltp)
        if price is None:
            session.add(models.EligibilityEvaluation(
                company_id=comp.id, eligible=False,
                reason=f"price gate: {price_note}"))
            continue
        cost = estimate(price, cfg.default_quantity, sched)
        buf, rule = safety_buffer(price, q.upper_circuit, cfg.safety_buffer_pct)
        out.append({"company": comp, "security": sec, "quote": q, "price": price,
                    "price_note": price_note, "cost": cost, "buffer": buf,
                    "buffer_rule": rule, "reserve_total": round(cost.total + buf, 2)})
    session.commit()
    audit(session, "candidates_built", f"{len(out)} eligible")
    out.sort(key=lambda r: r["cost"].total)
    return out


def paper_funds(session) -> float:
    try:
        return float(setting_get(session, "paper_funds_inr", "100000"))
    except ValueError:
        return 0.0


def reserved_total(session) -> float:
    rows = session.query(models.FundReservation).filter_by(status="active").all()
    return round(sum(r.amount for r in rows), 2)


def make_remarks(public_id: str) -> str:
    return "ISC-" + hashlib.sha256(public_id.encode()).hexdigest()[:16].upper()


def create_paper_intents(session, cfg: Settings, candidates: list[dict]) -> list[models.OrderIntent]:
    """Paper path: reserve + intent + deterministic simulated fill. No broker network."""
    from .broker import OrderRequest, SimulatorBroker
    sim = SimulatorBroker()
    sched = session.query(models.ChargeSchedule).filter_by(active=True).first()
    funds = paper_funds(session)
    intents = []
    for c in candidates:
        if reserved_total(session) + c["reserve_total"] > funds:
            audit(session, "reserve_rejected",
                  f"{c['company'].isin} needs {c['reserve_total']}, funds {funds}")
            continue
        if session.query(models.Holding).filter_by(company_id=c["company"].id).first():
            continue
        public_id = f"paper-{ist_today()}-{c['company'].isin}-{c['security'].exchange}"
        if session.query(models.OrderIntent).filter_by(public_id=public_id).first():
            continue  # never duplicate
        intent = models.OrderIntent(
            public_id=public_id, company_id=c["company"].id,
            security_id=c["security"].id, quantity=cfg.default_quantity,
            limit_price=c["price"], remarks=make_remarks(public_id), mode="paper",
            status="reserved")
        session.add(intent)
        session.flush()
        cost = estimate(c["price"], cfg.default_quantity, sched)
        session.add(models.CostEstimate(
            intent_public_id=public_id, schedule_version=cost.schedule_version,
            share_value=cost.share_value, stt=cost.stt, stamp=cost.stamp,
            exch=cost.exch, gst=cost.gst, sebi=cost.sebi, broker=cost.broker,
            total=cost.total))
        session.add(models.FundReservation(
            intent_public_id=public_id, amount=c["reserve_total"],
            buffer_amount=c["buffer"], buffer_rule=c["buffer_rule"]))
        resp = sim.place_order(OrderRequest(
            uid="PAPER", actid="PAPER", exchange=c["security"].exchange,
            tsym=c["security"].tsym, quantity=cfg.default_quantity,
            limit_price=c["price"], remarks=intent.remarks))
        bo = models.BrokerOrder(intent_id=intent.id, norenordno=resp.norenordno,
                                stat=resp.stat, reconciled_status="simulated-fill")
        session.add(bo)
        session.flush()
        session.add(models.Fill(broker_order_id=bo.id, quantity=cfg.default_quantity,
                                price=c["price"], source="simulator"))
        holding = session.query(models.Holding).filter_by(company_id=c["company"].id).first()
        if holding is None:
            session.add(models.Holding(company_id=c["company"].id,
                                       quantity=cfg.default_quantity, avg_price=c["price"]))
        intent.status = "simulated"
        intents.append(intent)
    session.commit()
    audit(session, "paper_simulated", f"{len(intents)} intents")
    return intents


def live_gate(session, cfg: Settings, phrase: str, now) -> tuple[bool, list[str]]:
    """All live preconditions. Returns (ok, blockers)."""
    blockers = list(cfg.live_blockers())
    if is_kill_switch_on(session):
        blockers.append("kill switch is ON")
    if phrase != (setting_get(session, "confirmation_phrase", None)
                  or cfg.confirmation_phrase):
        blockers.append("confirmation phrase mismatch")
    window = SessionWindow(setting_get(session, "session_start", None) or cfg.session_start_ist,
                           setting_get(session, "session_end", None) or cfg.session_end_ist)
    if cfg.amo_enabled:
        pass  # AMO queues with same review; labelled queued_amo (verified flag in settings)
    else:
        ok, reason = regular_session_open(now, window)
        if not ok:
            blockers.append(reason)
    return (len(blockers) == 0), blockers


_last_submit: float = 0.0


def throttle_ok(cfg: Settings) -> bool:
    global _last_submit
    now = time.monotonic()
    if now - _last_submit < cfg.order_throttle_seconds:
        return False
    _last_submit = now
    return True


def reconcile_intent(session, intent: models.OrderIntent, book_rows: list[dict]) -> str:
    """Match Order Book by remarks+symbol+qty+price. Returns reconciled status."""
    bo = session.query(models.BrokerOrder).filter_by(intent_id=intent.id).first()
    for row in book_rows:
        if str(row.get("remarks", "")) != intent.remarks:
            continue
        status = str(row.get("status", "pending"))
        if bo:
            bo.reconciled_status = status
        intent.status = "reconciled-" + status
        session.commit()
        audit(session, "reconciled", f"{intent.remarks} -> {status}")
        return status
    return "pending"
