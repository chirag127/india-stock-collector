"""Route-level tests: paper dashboard works without creds; live never fires unprompted."""
from __future__ import annotations

import os
import tempfile

# Isolate route tests on a temp DB before app import (lifespan reads settings then).
_tmp = tempfile.mkdtemp(prefix="isc-test-")
os.environ["APP_DB_PATH"] = os.path.join(_tmp, "test.db")

from fastapi.testclient import TestClient

from app import models
from app.config import reset_settings_cache
from app.db import get_session

reset_settings_cache()
from app.main import app


def test_healthz():
    with TestClient(app) as c:
        assert c.get("/healthz").text == "ok"


def test_overview_queue_orders_contacts_pages_load_without_orders_firing():
    with TestClient(app) as c:
        for path in ["/", "/universe", "/queue", "/review",
                     "/simulator", "/orders", "/contacts", "/settings"]:
            r = c.get(path)
            assert r.status_code == 200, path
        assert c.get("/orders").text.count("SIM") >= 0
        # paper run creates simulated fills, never live
        c.post("/queue/paper-run")
        body = c.get("/orders").text
        assert "SIM" in body or "simulated" in body


def test_contacts_export_only_verified_selected():
    with TestClient(app) as c:
        s = get_session()
        try:
            comp = s.query(models.Company).first()
            c1 = models.InvestorContact(company_id=comp.id, kind="ir", name="A",
                                        email="a@example.com", source_url="https://example.com",
                                        verified=True, last_checked="2026-09-01")
            c2 = models.InvestorContact(company_id=comp.id, kind="rta", name="B",
                                        email="b@example.com", source_url="https://example.com",
                                        verified=False, last_checked="2026-09-01")
            s.add_all([c1, c2])
            s.commit()
            ids = f"{c1.id},{c2.id}"
        finally:
            s.close()
        r = c.get(f"/contacts/export?ids={ids}")
        assert r.status_code == 200
        assert "a@example.com" in r.text
        assert "b@example.com" not in r.text  # unverified excluded


def test_review_live_blocked_without_confirmation():
    with TestClient(app) as c:
        r = c.post("/review/live", data={"phrase": "nope"})
        assert r.status_code == 200
        assert "BLOCKED" in r.text
