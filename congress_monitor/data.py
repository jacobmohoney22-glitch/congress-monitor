from __future__ import annotations

from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter, Retry


@dataclass(frozen=True)
class Trade:
    id: str
    source: str
    filer_id: str
    filer: str
    branch: str            # "congress" | "executive"
    chamber: str           # "house" | "senate" | ""
    party: str
    state: str
    agency: str
    office: str
    ticker: str
    asset: str
    ttype: str             # "Purchase", "Sale (Full)", "Sale (Partial)", "Exchange"
    amt_low: int | None
    amt_high: int | None
    amt_label: str
    tx_date: str
    filing_date: str
    days_to_file: int | None
    is_late: bool
    owner: str
    doc_url: str


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def parse_trade(row: dict) -> Trade | None:
    """One row of Kadoa's trades.json -> Trade (None if unusable)."""
    rid, name, filed = row.get("id"), row.get("filer_name"), row.get("filing_date")
    if not (rid and name and filed):
        return None
    s = lambda k: str(row.get(k) or "").strip()
    return Trade(
        id=str(rid), source=s("source_id"), filer_id=s("filer_id"), filer=str(name).strip(),
        branch=s("branch"), chamber=s("chamber"), party=s("party"), state=s("state"),
        agency=s("agency"), office=s("office"), ticker=s("ticker").upper(),
        asset=s("asset_name"), ttype=s("transaction_type"),
        amt_low=_int(row.get("amount_range_low")), amt_high=_int(row.get("amount_range_high")),
        amt_label=s("amount_range_label"), tx_date=s("transaction_date"),
        filing_date=str(filed)[:10], days_to_file=_int(row.get("days_to_file")),
        is_late=bool(row.get("is_late")), owner=s("owner"), doc_url=s("doc_url"))


def parse_trades(payload) -> list[Trade]:
    rows = payload if isinstance(payload, list) else (payload or {}).get("data", [])
    return [t for t in (parse_trade(r) for r in rows if isinstance(r, dict)) if t]


class DataClient:
    """Downloads the trades file, using ETag so an unchanged file costs almost nothing."""

    def __init__(self, url: str, user_agent: str = "congress-monitor/1.0"):
        self.url = url
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        retries = Retry(total=3, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                        allowed_methods=("GET",))
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def fetch(self, etag: str = "") -> tuple[list[Trade] | None, str]:
        """(trades, new_etag), or (None, etag) when the file hasn't changed."""
        headers = {"If-None-Match": etag} if etag else {}
        resp = self.session.get(self.url, headers=headers, timeout=60)
        if resp.status_code == 304:
            return None, etag
        resp.raise_for_status()
        return parse_trades(resp.json()), resp.headers.get("ETag", "")
