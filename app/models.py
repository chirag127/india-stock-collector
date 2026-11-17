"""SQLite models. Secrets are never stored here; provenance timestamps are."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    isin: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    sector: Mapped[str] = mapped_column(String(128), default="unknown")
    industry: Mapped[str] = mapped_column(String(128), default="unknown")
    status: Mapped[str] = mapped_column(String(64), default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Security(Base):
    __tablename__ = "securities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(64), index=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)  # NSE/BSE
    tsym: Mapped[str] = mapped_column(String(128))
    isin: Mapped[str] = mapped_column(String(12), index=True)
    tick_size: Mapped[float] = mapped_column(Float, default=0.05)
    lot_size: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("exchange", "tsym", name="uq_security_venue"),)


class ExchangeListing(Base):
    __tablename__ = "exchange_listings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(512))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    raw_status: Mapped[str] = mapped_column(String(64), default="unknown")
    tradeable: Mapped[bool] = mapped_column(Boolean, default=False)
    surveillance: Mapped[str] = mapped_column(String(64), default="unknown")  # ASM/GSM/etc


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(128), index=True)
    source_url: Mapped[str] = mapped_column(String(512))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    checksum: Mapped[str] = mapped_column(String(128), default="")
    payload: Mapped[str] = mapped_column(Text, default="")  # raw content or fixture ref
    is_last_known_good: Mapped[bool] = mapped_column(Boolean, default=False)


class MarketQuote(Base):
    __tablename__ = "market_quotes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(64), default="fixture")  # fixture|shoonya
    source_url: Mapped[str] = mapped_column(String(512), default="")
    bid: Mapped[float] = mapped_column(Float, default=0.0)
    ask: Mapped[float] = mapped_column(Float, default=0.0)
    ltp: Mapped[float] = mapped_column(Float, default=0.0)
    lower_circuit: Mapped[float] = mapped_column(Float, default=0.0)
    upper_circuit: Mapped[float] = mapped_column(Float, default=0.0)
    volume: Mapped[int] = mapped_column(Integer, default=0)


class EligibilityEvaluation(Base):
    __tablename__ = "eligibility_evaluations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(Text, default="unknown")
    chosen_security_id: Mapped[int] = mapped_column(Integer, nullable=True)


class CandidateAttempt(Base):
    __tablename__ = "candidate_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), index=True)
    session_date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD IST
    status: Mapped[str] = mapped_column(String(32), default="proposed")  # proposed|queued|...
    limit_price: Mapped[float] = mapped_column(Float, default=0.0)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    failure_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OrderIntent(Base):
    __tablename__ = "order_intents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    limit_price: Mapped[float] = mapped_column(Float)
    remarks: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    mode: Mapped[str] = mapped_column(String(16), default="paper")  # paper|live|queued_amo
    status: Mapped[str] = mapped_column(String(32), default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BrokerOrder(Base):
    __tablename__ = "broker_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intent_id: Mapped[int] = mapped_column(ForeignKey("order_intents.id"), index=True)
    norenordno: Mapped[str] = mapped_column(String(64), default="", index=True)
    stat: Mapped[str] = mapped_column(String(16), default="")
    emsg: Mapped[str] = mapped_column(Text, default="")
    raw_response: Mapped[str] = mapped_column(Text, default="")
    reconciled_status: Mapped[str] = mapped_column(String(32), default="pending")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Fill(Base):
    __tablename__ = "fills"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broker_order_id: Mapped[int] = mapped_column(ForeignKey("broker_orders.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(64), default="simulator")  # simulator|broker


class Holding(Base):
    __tablename__ = "holdings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), unique=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    avg_price: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChargeSchedule(Base):
    __tablename__ = "charge_schedules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    stt_pct: Mapped[float] = mapped_column(Float, default=0.1)
    stamp_pct: Mapped[float] = mapped_column(Float, default=0.015)
    exch_pct: Mapped[float] = mapped_column(Float, default=0.00325)
    gst_pct: Mapped[float] = mapped_column(Float, default=18.0)  # on brokerage+exch
    sebi_flat_per_crore: Mapped[float] = mapped_column(Float, default=10.0)
    broker_flat_inr: Mapped[float] = mapped_column(Float, default=0.0)
    active: Mapped[bool] = mapped_column(Boolean, default=False)


class CostEstimate(Base):
    __tablename__ = "cost_estimates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intent_public_id: Mapped[str] = mapped_column(String(64), index=True)
    schedule_version: Mapped[str] = mapped_column(String(32))
    share_value: Mapped[float] = mapped_column(Float)
    stt: Mapped[float] = mapped_column(Float)
    stamp: Mapped[float] = mapped_column(Float)
    exch: Mapped[float] = mapped_column(Float)
    gst: Mapped[float] = mapped_column(Float)
    sebi: Mapped[float] = mapped_column(Float)
    broker: Mapped[float] = mapped_column(Float)
    total: Mapped[float] = mapped_column(Float)
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FundReservation(Base):
    __tablename__ = "fund_reservations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intent_public_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    amount: Mapped[float] = mapped_column(Float)
    buffer_amount: Mapped[float] = mapped_column(Float, default=0.0)
    buffer_rule: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")  # active|released|consumed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Filing(Base):
    __tablename__ = "filings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    title: Mapped[str] = mapped_column(String(256))
    filing_url: Mapped[str] = mapped_column(String(512))
    source_url: Mapped[str] = mapped_column(String(512), default="")
    filed_on: Mapped[str] = mapped_column(String(10), default="")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnnualReport(Base):
    __tablename__ = "annual_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    financial_year: Mapped[str] = mapped_column(String(9))
    report_url: Mapped[str] = mapped_column(String(512))
    source_url: Mapped[str] = mapped_column(String(512), default="")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InvestorContact(Base):
    __tablename__ = "investor_contacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # ir|cs|rta
    name: Mapped[str] = mapped_column(String(256), default="")
    email: Mapped[str] = mapped_column(String(256), default="")
    source_url: Mapped[str] = mapped_column(String(512), default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_checked: Mapped[str] = mapped_column(String(10), default="")
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)


class ContactSource(Base):
    __tablename__ = "contact_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("investor_contacts.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(512))
    noted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    note: Mapped[str] = mapped_column(Text, default="")


class ReportRequest(Base):
    __tablename__ = "report_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    financial_year: Mapped[str] = mapped_column(String(9))
    draft_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
