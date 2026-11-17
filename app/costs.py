"""Versioned all-in cost estimator (delivery/CNC buy). Explicit schedule, marked estimate."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostBreakdown:
    share_value: float
    stt: float
    stamp: float
    exch: float
    gst: float
    sebi: float
    broker: float
    total: float
    schedule_version: str
    is_estimate: bool = True


def estimate(price: float, qty: int, sched) -> CostBreakdown:
    """sched: ChargeSchedule row. Delivery buy: STT on share value, stamp on value,
    exchange txn %, GST on (broker+exch), SEBI flat per crore, broker flat."""
    share_value = round(price * qty, 2)
    stt = round(share_value * sched.stt_pct / 100, 2)
    stamp = round(share_value * sched.stamp_pct / 100, 2)
    exch = round(share_value * sched.exch_pct / 100, 2)
    broker = round(sched.broker_flat_inr, 2)
    gst = round((broker + exch) * sched.gst_pct / 100, 2)
    sebi = round(share_value / 1e7 * sched.sebi_flat_per_crore, 2)
    total = round(share_value + stt + stamp + exch + gst + sebi + broker, 2)
    return CostBreakdown(share_value, stt, stamp, exch, gst, sebi, broker,
                         total, sched.version, True)


def safety_buffer(price: float, upper_circuit: float, buffer_pct: float) -> tuple[float, str]:
    """Derived buffer: max(configured % of value, gap-to-circuit rounding risk). Never hard-coded."""
    base = round(price * buffer_pct / 100, 2)
    gap = round(max(0.0, upper_circuit - price), 2)
    circuit_risk = round(min(gap, price * buffer_pct / 100), 2)
    amount = round(base + circuit_risk + 0.05, 2)  # 0.05 = tick rounding headroom
    rule = (f"buffer_pct={buffer_pct}% of {price} + circuit-gap headroom "
            f"(uc={upper_circuit}) + tick 0.05")
    return amount, rule
