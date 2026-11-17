"""Deterministic paper-mode fixtures. Fabricated data only — no real securities."""
from __future__ import annotations

FIXTURE_COMPANIES = [
    {
        "isin": "INE000A01012",
        "name": "Fixture Agro Foods Ltd",
        "sector": "FMCG",
        "industry": "Food Processing",
        "status": "active",
        "securities": [
            {"symbol": "FIXAGRO", "exchange": "NSE", "tsym": "FIXAGRO-EQ", "tick": 0.05},
            {"symbol": "FIXAGRO", "exchange": "BSE", "tsym": "FIXAGRO", "tick": 0.05},
        ],
        "quote": {"bid": 8.40, "ask": 8.52, "ltp": 8.50, "lc": 7.60, "uc": 9.40, "vol": 120400},
    },
    {
        "isin": "INE000B01011",
        "name": "Fixture Poly Pipes Ltd",
        "sector": "Industrials",
        "industry": "Pipes",
        "status": "active",
        "securities": [
            {"symbol": "FIXPIPE", "exchange": "NSE", "tsym": "FIXPIPE-EQ", "tick": 0.05},
        ],
        "quote": {"bid": 4.10, "ask": 4.21, "ltp": 4.20, "lc": 3.75, "uc": 4.65, "vol": 88300},
    },
    {
        # Suspended — must be excluded with a visible reason.
        "isin": "INE000C01010",
        "name": "Fixture Suspended Textiles Ltd",
        "sector": "Textiles",
        "industry": "Spinning",
        "status": "suspended",
        "securities": [
            {"symbol": "FIXSUSP", "exchange": "BSE", "tsym": "FIXSUSP", "tick": 0.05},
        ],
        "quote": {"bid": 3.00, "ask": 3.10, "ltp": 3.05, "lc": 2.70, "uc": 3.40, "vol": 0},
    },
    {
        # Missing ISIN — must be excluded.
        "isin": "",
        "name": "Fixture Bad Record Ltd",
        "sector": "unknown",
        "industry": "unknown",
        "status": "active",
        "securities": [],
        "quote": {},
    },
]


def load_fixtures(session) -> int:
    """Idempotent fixture import. Returns number of companies present afterwards."""
    from . import models

    for fc in FIXTURE_COMPANIES:
        if not fc["isin"]:
            continue
        comp = session.query(models.Company).filter_by(isin=fc["isin"]).first()
        if comp is None:
            comp = models.Company(
                isin=fc["isin"], name=fc["name"], sector=fc["sector"],
                industry=fc["industry"], status=fc["status"],
            )
            session.add(comp)
            session.flush()
        for sec in fc["securities"]:
            exists = session.query(models.Security).filter_by(
                exchange=sec["exchange"], tsym=sec["tsym"]).first()
            if exists is None:
                s = models.Security(
                    company_id=comp.id, symbol=sec["symbol"], exchange=sec["exchange"],
                    tsym=sec["tsym"], isin=fc["isin"], tick_size=sec["tick"],
                )
                session.add(s)
                session.flush()
                session.add(models.ExchangeListing(
                    security_id=s.id,
                    source_url="fixture://paper-mode",
                    raw_status="active",
                    tradeable=fc["status"] == "active",
                    surveillance="unknown",
                ))
        if fc.get("quote"):
            for sec in fc["securities"]:
                s = session.query(models.Security).filter_by(
                    exchange=sec["exchange"], tsym=sec["tsym"]).first()
                if s is None:
                    continue
                q = fc["quote"]
                session.add(models.MarketQuote(
                    security_id=s.id, source="fixture", source_url="fixture://paper-mode",
                    bid=q["bid"], ask=q["ask"], ltp=q["ltp"],
                    lower_circuit=q["lc"], upper_circuit=q["uc"], volume=q["vol"],
                ))
    session.commit()
    return session.query(models.Company).count()
