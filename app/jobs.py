"""Local scheduled-job commands for Windows Task Scheduler. Never submits live orders."""
from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime

from . import models
from .db import audit, get_session, init_db
from .fixtures import FIXTURE_COMPANIES

# Official reference sources (cited; importer preserves raw metadata + last-known-good).
SOURCES = {
    "bse_listing": "https://www.bseindia.com/download/Equity/EQ_ScripMaster.csv",
    "nse_master": "https://nsearchives.nseindia.com/content/cm/cm_security_master.csv",
    "nse_holidays": "https://nsearchives.nseindia.com/content/holidays/cm_holidays.csv",
}


def snapshot(source_name: str, url: str, payload: str = "") -> int:
    init_db()
    s = get_session()
    try:
        checksum = hashlib.sha256(payload.encode()).hexdigest() if payload else ""
        prev = (s.query(models.SourceSnapshot).filter_by(source_name=source_name)
                .order_by(models.SourceSnapshot.id.desc()).first())
        if not payload and prev is not None:
            audit(s, "refresh_skipped_no_network",
                  f"{source_name}: kept last-known-good from {prev.retrieved_at}")
            return prev.id
        snap = models.SourceSnapshot(
            source_name=source_name, source_url=url,
            retrieved_at=datetime.now(UTC),
            checksum=checksum or (prev.checksum if prev else ""),
            payload=payload[:5000], is_last_known_good=True)
        s.add(snap)
        if prev is not None:
            prev.is_last_known_good = False
        s.commit()
        audit(s, "snapshot_saved", f"{source_name} {url}")
        return snap.id
    finally:
        s.close()


def cmd_refresh_reference(polite: bool = True) -> None:
    """Daily reference-data refresh. Fixture-backed offline; HTTP only if reachable."""
    import urllib.request
    for name, url in [("bse_listing", SOURCES["bse_listing"]),
                      ("nse_master", SOURCES["nse_master"])]:
        payload = ""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "india-stock-collector/0.1"})
            with urllib.request.urlopen(req, timeout=20) as r:
                payload = r.read(200000).decode("utf-8", "replace")
        except Exception:
            payload = ""  # keep last-known-good, record failure
        snapshot(name, url, payload)


def cmd_refresh_filings() -> None:
    """Daily filing/contact-link refresh placeholder: polite, no scraping bypass."""
    snapshot("filings_refresh", "https://www.bseindia.com/corporates/ann.html", "")
    snapshot("filings_refresh_nse", "https://www.nseindia.com/companies-listing/corporate-filings-announcements", "")


def cmd_refresh_calendar() -> None:
    snapshot("market_calendar", SOURCES["nse_holidays"], "")


def cmd_paper_rebuild() -> None:
    from .config import get_settings
    from .fixtures import load_fixtures
    from .services import build_candidates
    init_db()
    s = get_session()
    try:
        load_fixtures(s)
        cands = build_candidates(s, get_settings())
        print(f"paper candidates: {len(cands)}")
    finally:
        s.close()


def main() -> None:
    p = argparse.ArgumentParser(description="india-stock-collector local jobs")
    p.add_argument("cmd", choices=["refresh-reference", "refresh-filings",
                                   "refresh-calendar", "paper-rebuild"])
    a = p.parse_args()
    {"refresh-reference": cmd_refresh_reference, "refresh-filings": cmd_refresh_filings,
     "refresh-calendar": cmd_refresh_calendar,
     "paper-rebuild": cmd_paper_rebuild}[a.cmd]()


if __name__ == "__main__":
    print([c["isin"] for c in FIXTURE_COMPANIES])
    main()
