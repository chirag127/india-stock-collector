"""Engine/session + tiny migration runner (create_all + settings seed)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from . import models
from .config import get_settings

SCHEMA_VERSION = 1


def db_path() -> Path:
    p = Path(get_settings().app_db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


_engines: dict[str, object] = {}


def make_engine(db_file: str | None = None):
    target = db_file or str(db_path())
    if target == ":memory:":
        # Fresh isolated engine per call (unit tests are single-threaded).
        return create_engine("sqlite:///:memory:", future=True)
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    cached = _engines.get(target)
    if cached is None:
        # One shared engine: TestClient serves requests from another thread.
        cached = create_engine(f"sqlite:///{target}", future=True,
                               connect_args={"check_same_thread": False})
        _engines[target] = cached
    return cached


def init_db(db_file: str | None = None):
    """Create tables and seed settings/charge schedule. Never touches network."""
    engine = make_engine(db_file)
    models.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        if s.query(models.Setting).filter_by(key="schema_version").first() is None:
            s.add(models.Setting(key="schema_version", value=str(SCHEMA_VERSION)))
        defaults = {
            "kill_switch": "off",
            "paper_funds_inr": "100000",
            "fee_schedule_version": "v1",
            "market_calendar_source": "config-fallback 09:15-15:30 IST",
        }
        for k, v in defaults.items():
            if s.query(models.Setting).filter_by(key=k).first() is None:
                s.add(models.Setting(key=k, value=v))
        if s.query(models.ChargeSchedule).filter_by(version="v1").first() is None:
            s.add(
                models.ChargeSchedule(
                    version="v1",
                    stt_pct=0.1,
                    stamp_pct=0.015,
                    exch_pct=0.00325,
                    gst_pct=18.0,
                    sebi_flat_per_crore=10.0,
                    broker_flat_inr=0.0,
                    active=True,
                )
            )
        s.commit()
    return engine


def get_session(db_file: str | None = None):
    engine = make_engine(db_file)
    return sessionmaker(bind=engine, future=True)()


def is_kill_switch_on(session) -> bool:
    row = session.query(models.Setting).filter_by(key="kill_switch").first()
    return row is not None and row.value.strip().lower() == "on"


def audit(session, kind: str, detail: str = "") -> None:
    session.add(models.AuditEvent(kind=kind, detail=detail[:2000]))
    session.commit()


def setting_get(session, key: str, default: str = "") -> str:
    row = session.query(models.Setting).filter_by(key=key).first()
    return row.value if row else default


def setting_set(session, key: str, value: str) -> None:
    row = session.query(models.Setting).filter_by(key=key).first()
    if row:
        row.value = value
    else:
        session.add(models.Setting(key=key, value=value))
    session.commit()
    audit(session, "settings_change", f"{key} updated")
