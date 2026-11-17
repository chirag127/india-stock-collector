"""Exchange calendar + session gates. Asia/Kolkata, configurable fallback 09:15-15:30 IST."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class SessionWindow:
    start_ist: str = "09:15"
    end_ist: str = "15:30"

    def contains(self, moment: datetime) -> bool:
        local = moment.astimezone(IST)
        s_h, s_m = map(int, self.start_ist.split(":"))
        e_h, e_m = map(int, self.end_ist.split(":"))
        return time(s_h, s_m) <= local.time() <= time(e_h, e_m)


def today_ist() -> date:
    return datetime.now(IST).date()


def is_trading_day(day: date, holidays: set[str] | None = None) -> bool:
    if day.weekday() >= 5:  # Sat/Sun
        return False
    return not (holidays and day.isoformat() in holidays)


def regular_session_open(now: datetime, window: SessionWindow,
                         holidays: set[str] | None = None) -> tuple[bool, str]:
    """(open, reason). AMO path uses the same review but labels queued_amo."""
    local = now.astimezone(IST)
    if not is_trading_day(local.date(), holidays):
        return False, "exchange closed (weekend/holiday)"
    if not window.contains(now):
        return False, f"outside regular session {window.start_ist}-{window.end_ist} IST"
    return True, "regular session open"
