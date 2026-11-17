"""Central settings. Live trading is impossible unless explicitly enabled locally."""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_db_path: str = "data/app.db"

    # Broker OAuth (empty by default). Tokens live in local cred.yml, never in git.
    shoonya_client_id: str = ""
    shoonya_secret_code: str = ""
    shoonya_uid: str = ""
    shoonya_api_key: str = ""
    shoonya_whitelisted_ip: str = ""

    live_trading_enabled: bool = False

    # Candidate policy defaults (locally configurable via settings page).
    price_ceiling_inr: float = 10.0
    default_quantity: int = 1
    max_slippage_pct: float = 0.5
    safety_buffer_pct: float = 2.0
    session_start_ist: str = "09:15"
    session_end_ist: str = "15:30"
    per_order_cap_inr: float = 0.0  # 0 = unset -> live blocked until set
    per_batch_cap_inr: float = 0.0
    per_day_cap_inr: float = 0.0
    order_throttle_seconds: float = 1.0
    confirmation_phrase: str = "PLACE LIVE CNC ORDERS"
    amo_enabled: bool = False  # default off; enable only after doc/account verification

    @property
    def paper_mode(self) -> bool:
        return not self.live_trading_enabled

    def live_blockers(self) -> list[str]:
        """Reasons live trading is currently impossible. Empty = technically enabled."""
        blockers: list[str] = []
        if not self.live_trading_enabled:
            blockers.append("LIVE_TRADING_ENABLED is not true")
        if not (self.shoonya_client_id and self.shoonya_uid):
            blockers.append("Shoonya credentials not configured locally")
        if self.per_order_cap_inr <= 0 or self.per_batch_cap_inr <= 0 or self.per_day_cap_inr <= 0:
            blockers.append("per-order/per-batch/per-day guardrails not set")
        return blockers


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def reset_settings_cache() -> None:
    get_settings.cache_clear()


def env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() == "true"
