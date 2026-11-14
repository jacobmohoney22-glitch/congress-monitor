from __future__ import annotations

from datetime import date, timedelta

import requests


class InsiderContext:
    """Read-only view of your insider-monitor's saved purchases (SEC Form 4 open-market buys)."""

    def __init__(self, purchases: list[dict]):
        self.purchases = purchases

    @classmethod
    def load(cls, url: str, session: requests.Session | None = None):
        """None if disabled or unreachable: the cross-check is a bonus, never a requirement."""
        if not url:
            return None
        try:
            r = (session or requests).get(url, timeout=30)
            r.raise_for_status()
            return cls(list((r.json().get("purchases") or {}).values()))
        except (requests.RequestException, ValueError, AttributeError):
            return None

    def lookup(self, ticker: str, today: date, lookback_days: int) -> tuple[int, float] | None:
        """(distinct insiders, total $) who bought this ticker recently, or None."""
        cutoff = (today - timedelta(days=lookback_days)).isoformat()
        hits = [p for p in self.purchases
                if str(p.get("ticker", "")).upper() == ticker and str(p.get("tx_date", "")) >= cutoff]
        if not hits:
            return None
        return len({p.get("insider_key") for p in hits}), sum(float(p.get("value") or 0) for p in hits)
