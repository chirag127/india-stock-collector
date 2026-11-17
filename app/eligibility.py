"""Candidate eligibility engine. Fail closed; every exclusion carries a reason."""
from __future__ import annotations

import re
from dataclasses import dataclass

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{10}$")


@dataclass
class EligibilityResult:
    eligible: bool
    reason: str
    security_id: int | None = None


def valid_isin(isin: str) -> bool:
    return bool(ISIN_RE.match((isin or "").strip()))


def evaluate_company(company, securities: list, quotes: dict,
                     seen_isins: set[str], price_ceiling: float) -> EligibilityResult:
    """Pure function over ORM-ish objects. `quotes`: security_id -> MarketQuote."""
    if not valid_isin(company.isin):
        return EligibilityResult(False, "excluded: invalid/missing ISIN")
    if company.isin in seen_isins:
        return EligibilityResult(False, "excluded: duplicate ISIN across venues (dedupe)")
    if (company.status or "").lower() not in ("active", "listed"):
        return EligibilityResult(False, f"excluded: status={company.status}")
    if not securities:
        return EligibilityResult(False, "excluded: no exchange listings")
    # Venue choice: executable ask + lowest all-in share value proxy (ask price).
    best = None
    best_ask = None
    reasons: list[str] = []
    for s in securities:
        q = quotes.get(s.id)
        if q is None or q.ask <= 0:
            reasons.append(f"{s.exchange}:{s.tsym} no executable ask")
            continue
        if q.volume <= 0:
            reasons.append(f"{s.exchange}:{s.tsym} no recent trading (vol=0)")
            continue
        if not (q.lower_circuit > 0 and q.upper_circuit > 0):
            reasons.append(f"{s.exchange}:{s.tsym} missing circuit band")
            continue
        if not (q.lower_circuit <= q.ask <= q.upper_circuit):
            reasons.append(f"{s.exchange}:{s.tsym} ask outside circuit band")
            continue
        if q.ask > price_ceiling:
            reasons.append(f"{s.exchange}:{s.tsym} ask {q.ask} above ceiling {price_ceiling}")
            continue
        if best is None or q.ask < best_ask:
            best, best_ask = s, q.ask
    if best is None:
        return EligibilityResult(False, "excluded: " + "; ".join(reasons) if reasons else "excluded: unknown")
    return EligibilityResult(True, f"eligible via {best.exchange}:{best.tsym} @ {best_ask}", best.id)


def limit_price_from_ask(ask: float, upper_circuit: float, max_slippage_pct: float,
                         ltp: float) -> tuple[float | None, str]:
    """Best ask only when within slippage vs LTP and inside upper circuit. Never chase."""
    if ask <= 0:
        return None, "no executable ask"
    if ltp > 0 and (ask - ltp) / ltp * 100 > max_slippage_pct:
        return None, f"ask {ask} exceeds slippage {max_slippage_pct}% over LTP {ltp}"
    if ask > upper_circuit:
        return None, f"ask {ask} above upper circuit {upper_circuit}"
    return round(ask, 2), "ask within slippage + circuit"
