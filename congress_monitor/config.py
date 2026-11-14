from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_DATA_URL = ("https://raw.githubusercontent.com/kadoa-org/congress-trading-monitor/"
                    "main/public/data/trades.json")
BRANCHES = ("all", "congress", "executive")


def _get(env, key, default):
    v = env.get(key)
    return default if v is None or str(v).strip() == "" else str(v).strip()


def _bool(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    data_url: str = DEFAULT_DATA_URL
    # what counts as worth an alert
    min_amount: int = 15_001          # disclosed range's LOWER bound must be at least this
    only_tickers: bool = True         # skip private funds, bonds, etc. that have no ticker
    branch: str = "all"               # all | congress | executive
    max_filing_age_days: int = 10     # ignore filings older than this (backfills, re-parses)
    watch_filers: tuple = ()          # names that ALWAYS alert, ignoring the rules above
    max_lines_per_filing: int = 12
    # optional cross-check against your insider-monitor's saved state
    insider_state_url: str = ""       # "" = disabled
    insider_lookback_days: int = 14
    # delivery / storage
    telegram_token: str = ""
    telegram_chat_id: str = ""
    state_path: str = "state/state.json"

    @classmethod
    def from_env(cls, env=None) -> "Config":
        env = os.environ if env is None else env
        g = lambda k, d: _get(env, k, d)
        branch = g("BRANCH", "all").lower()
        if branch not in BRANCHES:
            raise SystemExit(f"BRANCH must be one of {BRANCHES}, got {branch!r}")
        # default: read the insider-monitor repo owned by the same GitHub user, if any
        owner = env.get("GITHUB_REPOSITORY_OWNER", "")
        ins = g("INSIDER_STATE_URL", "")
        if ins.lower() == "none":
            ins = ""
        elif not ins and owner:
            ins = (f"https://raw.githubusercontent.com/{owner}/insider-monitor/"
                   "monitor-state/state.json")
        return cls(
            data_url=g("DATA_URL", DEFAULT_DATA_URL),
            min_amount=int(g("MIN_AMOUNT", 15001)),
            only_tickers=_bool(g("ONLY_TICKERS", "true")),
            branch=branch,
            max_filing_age_days=int(g("MAX_FILING_AGE_DAYS", 10)),
            watch_filers=tuple(w.strip().lower() for w in g("WATCH_FILERS", "").split(",")
                               if w.strip()),
            max_lines_per_filing=int(g("MAX_LINES_PER_FILING", 12)),
            insider_state_url=ins,
            insider_lookback_days=int(g("INSIDER_LOOKBACK_DAYS", 14)),
            telegram_token=g("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=g("TELEGRAM_CHAT_ID", ""),
            state_path=g("STATE_PATH", "state/state.json"),
        )

    def require_telegram(self) -> None:
        if not (self.telegram_token and self.telegram_chat_id):
            raise SystemExit("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required "
                             "(or use --dry-run).")
