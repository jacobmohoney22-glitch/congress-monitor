"""Synthetic rows shaped like Kadoa's public/data/trades.json."""
from __future__ import annotations

from congress_monitor.data import parse_trades


def row(rid, *, filer="Jane Roe", filer_id=None, branch="congress", chamber="house", party="D",
        state="CA", ticker="AAPL", ttype="Purchase", low=15001, high=50000, tx="2026-11-02",
        filed="2026-11-10", days=8, late=0, owner=None, doc="https://disclosures.example/1.pdf",
        asset="Apple Inc.", office=None, agency=None):
    return {"id": rid, "source_id": "house_clerk", "filer_id": filer_id or filer.lower().replace(" ", "_"),
            "filer_name": filer, "branch": branch, "chamber": chamber, "party": party, "state": state,
            "agency": agency, "office": office, "ticker": ticker, "asset_name": asset,
            "transaction_type": ttype, "amount_range_low": low, "amount_range_high": high,
            "amount_range_label": (f"${low:,} - ${high:,}" if low is not None and high is not None else None), "transaction_date": tx,
            "filing_date": filed, "days_to_file": days, "is_late": late, "owner": owner,
            "doc_url": doc}


class FakeClient:
    """fetch(etag) like DataClient: returns (None, etag) when the 'file' hasn't changed."""

    def __init__(self, rows=()):
        self.rows, self.version, self.fetches = list(rows), 1, 0

    def set_rows(self, rows):
        self.rows, self.version = list(rows), self.version + 1

    def fetch(self, etag=""):
        self.fetches += 1
        tag = f"v{self.version}"
        return (None, etag) if etag == tag else (parse_trades(self.rows), tag)


class FakeNotifier:
    def __init__(self, ok=True):
        self.sent, self.ok = [], ok

    def send(self, text):
        self.sent.append(text)
        return self.ok


class FakeInsiders:
    def __init__(self, hits):
        self.hits = hits

    def lookup(self, ticker, today, lookback_days):
        return self.hits.get(ticker)
