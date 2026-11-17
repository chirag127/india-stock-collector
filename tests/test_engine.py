"""Eligibility, costs, calendar, live-gate and paper-path tests."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy.orm import sessionmaker

from app import models
from app.broker import OrderRequest, ShoonyaBroker, SimulatorBroker
from app.calendar import SessionWindow, is_trading_day, regular_session_open
from app.config import Settings
from app.costs import estimate, safety_buffer
from app.db import init_db, setting_set
from app.eligibility import evaluate_company, limit_price_from_ask, valid_isin
from app.fixtures import load_fixtures
from app.services import build_candidates, create_paper_intents, live_gate


def mem_session():
    engine = init_db(":memory:")
    return sessionmaker(bind=engine, future=True)()


def test_isin_validation():
    assert valid_isin("INE000A01012")
    assert not valid_isin("")
    assert not valid_isin("BAD")


def test_eligible_company_picks_lowest_ask_venue():
    comp = SimpleNamespace(isin="INE000A01012", status="active")
    s1 = SimpleNamespace(id=1, exchange="NSE", tsym="X-EQ")
    s2 = SimpleNamespace(id=2, exchange="BSE", tsym="X")
    q = {1: SimpleNamespace(ask=8.55, volume=100, lower_circuit=7.0,
                            upper_circuit=9.5),
         2: SimpleNamespace(ask=8.40, volume=100, lower_circuit=7.0,
                            upper_circuit=9.5)}
    r = evaluate_company(comp, [s1, s2], q, set(), 10.0)
    assert r.eligible and r.security_id == 2


def test_exclusions_have_reasons():
    comp = SimpleNamespace(isin="INE000A01012", status="suspended")
    r = evaluate_company(comp, [], {}, set(), 10.0)
    assert not r.eligible and "status" in r.reason
    comp2 = SimpleNamespace(isin="", status="active")
    r2 = evaluate_company(comp2, [], {}, set(), 10.0)
    assert not r2.eligible and "ISIN" in r2.reason


def test_limit_price_gates():
    p, _ = limit_price_from_ask(8.55, 9.40, 5.0, 8.50)
    assert p == 8.55
    p2, why = limit_price_from_ask(9.90, 9.40, 50.0, 8.50)
    assert p2 is None and "circuit" in why
    p3, why3 = limit_price_from_ask(9.00, 10.0, 0.5, 8.50)
    assert p3 is None and "slippage" in why3


def test_cost_estimate_marks_estimate_and_sums():
    sched = SimpleNamespace(version="v1", stt_pct=0.1, stamp_pct=0.015,
                            exch_pct=0.00325, gst_pct=18.0,
                            sebi_flat_per_crore=10.0, broker_flat_inr=0.0)
    c = estimate(8.55, 1, sched)
    assert c.is_estimate and c.total >= c.share_value
    assert abs(c.total - (c.share_value + c.stt + c.stamp + c.exch
                          + c.gst + c.sebi + c.broker)) < 0.02


def test_buffer_derived_not_hardcoded():
    b1, rule = safety_buffer(8.55, 9.40, 2.0)
    b2, _ = safety_buffer(4.25, 4.65, 2.0)
    assert b1 != b2 and "buffer_pct" in rule


def test_session_gate_weekend_and_window():
    sat = datetime(2026, 9, 12, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))  # Saturday
    ok, _ = regular_session_open(sat, SessionWindow())
    assert not ok
    assert not is_trading_day(sat.date())
    mon_early = datetime(2026, 9, 14, 8, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    ok2, _ = regular_session_open(mon_early, SessionWindow())
    assert not ok2


def test_paper_path_no_network_and_live_blocked_by_default():
    s = mem_session()
    load_fixtures(s)
    cfg = Settings()
    cands = build_candidates(s, cfg)
    assert len(cands) == 2  # suspended + bad record excluded
    intents = create_paper_intents(s, cfg, cands)
    assert len(intents) == 2
    assert s.query(models.Holding).count() == 2
    # no duplicates on re-run
    intents2 = create_paper_intents(s, cfg, build_candidates(s, cfg))
    assert intents2 == []
    # live impossible by default
    ok, blockers = live_gate(s, cfg, phrase="PLACE LIVE CNC ORDERS",
                             now=datetime.now(ZoneInfo("Asia/Kolkata")))
    assert not ok and blockers


def test_live_requires_phrase_kill_and_guardrails():
    s = mem_session()
    cfg = Settings(live_trading_enabled=True, shoonya_client_id="x",
                   shoonya_uid="u", per_order_cap_inr=100,
                   per_batch_cap_inr=1000, per_day_cap_inr=5000)
    ok, blockers = live_gate(s, cfg, phrase="wrong",
                             now=datetime.now(ZoneInfo("Asia/Kolkata")))
    assert not ok and any("phrase" in b for b in blockers)
    setting_set(s, "kill_switch", "on")
    ok2, blockers2 = live_gate(s, cfg, phrase="PLACE LIVE CNC ORDERS",
                               now=datetime.now(ZoneInfo("Asia/Kolkata")))
    assert not ok2 and any("kill" in b.lower() for b in blockers2)


def test_simulator_rejects_non_cnc():
    sim = SimulatorBroker()
    bad = sim.place_order(OrderRequest(uid="u", actid="a", exchange="NSE",
                                       tsym="X-EQ", quantity=1, limit_price=5.0,
                                       remarks="R1", product="I"))
    assert bad.stat == "Not_Ok"


def test_shoonya_adapter_needs_oauth_and_maps_fields():
    b = ShoonyaBroker(api=None)
    # Ambiguous transport state is returned, never raised through: fail-closed data.
    assert b.order_book()[0]["error"].startswith("ambiguous")
    assert b.get_quote("NSE", "X-EQ")["stat"] == "Not_Ok"
    seen = {}

    class FakeApi:
        def place_order(self, **kw):
            seen.update(kw)
            return {"stat": "Ok", "norenordno": "123"}

    b2 = ShoonyaBroker(api=FakeApi())
    r = b2.place_order(OrderRequest(uid="U", actid="U", exchange="NSE",
                                    tsym="X-EQ", quantity=1, limit_price=5.0,
                                    remarks="ISC-ABC"))
    assert r.stat == "Ok" and seen["product_type"] == "C" and seen["price_type"] == "LMT"
