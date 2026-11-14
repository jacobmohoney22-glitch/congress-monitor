from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date

from .config import Config
from .data import Trade

ACTION = {"purchase": "BUY", "sale (full)": "SELL", "sale (partial)": "SELL (partial)",
          "exchange": "EXCHANGE"}
OWNER = {"sp": "spouse", "spouse": "spouse", "dc": "dependent child", "jt": "joint",
         "joint": "joint"}


@dataclass(frozen=True)
class Group:
    """All matching trades from ONE filing (one alert per filing, not per trade)."""
    key: str
    filer: str
    trades: tuple[Trade, ...]
    watched: bool


def is_watched(t: Trade, cfg: Config) -> bool:
    return any(w in t.filer.lower() for w in cfg.watch_filers)


def select(trades: list[Trade], cfg: Config, today: date) -> list[Trade]:
    """Trades worth an alert. Watched names bypass the amount/ticker/branch rules."""
    out = []
    for t in trades:
        try:
            age = (today - date.fromisoformat(t.filing_date)).days
        except ValueError:
            continue
        if age > cfg.max_filing_age_days:        # old filing surfacing late: not news
            continue
        if not is_watched(t, cfg):
            if cfg.branch != "all" and t.branch != cfg.branch:
                continue
            if cfg.only_tickers and not t.ticker:
                continue
            if (t.amt_low or 0) < cfg.min_amount:
                continue
        out.append(t)
    return out


def group_by_filing(trades: list[Trade], cfg: Config) -> list[Group]:
    by: dict[str, list[Trade]] = {}
    for t in trades:
        by.setdefault(t.doc_url or f"{t.filer_id}|{t.filing_date}", []).append(t)
    size = lambda t: t.amt_high or t.amt_low or 0
    groups = [Group(k, v[0].filer, tuple(sorted(v, key=size, reverse=True)),
                    is_watched(v[0], cfg)) for k, v in by.items()]
    groups.sort(key=lambda g: (g.watched, size(g.trades[0])), reverse=True)
    return groups


def _esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def _who(t: Trade) -> str:
    if t.branch == "congress":
        title = "Senator" if t.chamber == "senate" else "Representative"
        tag = "-".join(x for x in (t.party, t.state) if x)
        return f"{title}" + (f" ({tag})" if tag else "")
    return ", ".join(x for x in (t.office, t.agency) if x) or "Executive branch"


def _line(t: Trade, ctx, today: date, cfg: Config) -> list[str]:
    action = ACTION.get(t.ttype.lower(), t.ttype.upper() or "TRADE")
    asset = t.ticker or (t.asset[:45] + ("..." if len(t.asset) > 45 else ""))
    bits = [f"{action} {_esc(asset)}", _esc(t.amt_label or "amount n/a")]
    if t.tx_date:
        bits.append(f"traded {t.tx_date}")
    if t.days_to_file is not None:
        bits.append(f"{t.days_to_file}d to file")
    extras = []
    if t.is_late:
        extras.append("LATE")
    if OWNER.get(t.owner.lower()):
        extras.append(OWNER[t.owner.lower()])
    lines = ["\u2022 " + " \u00b7 ".join(bits) + (f"  [{', '.join(extras)}]" if extras else "")]
    if ctx and t.ticker:
        hit = ctx.lookup(t.ticker, today, cfg.insider_lookback_days)
        if hit:
            n, usd = hit
            lines.append(f"   \u21b3 Insiders also bought {t.ticker}: {n} insider"
                         f"{'s' if n != 1 else ''}, ${usd:,.0f} (SEC Form 4, last "
                         f"{cfg.insider_lookback_days} days)")
    return lines


def format_group(g: Group, ctx, today: date, cfg: Config) -> str:
    t0 = g.trades[0]
    star = "\u2b50 " if g.watched else ""
    n = len(g.trades)
    lines = [f"\U0001F3DB {star}<b>GOVERNMENT FILING \u00b7 {_esc(g.filer)}</b>",
             f"{_esc(_who(t0))}",
             f"Filed {t0.filing_date} \u00b7 {n} matching trade{'s' if n != 1 else ''}", ""]
    for t in g.trades[:cfg.max_lines_per_filing]:
        lines += _line(t, ctx, today, cfg)
    if n > cfg.max_lines_per_filing:
        lines.append(f"+ {n - cfg.max_lines_per_filing} more matching trades in this filing")
    text = "\n".join(lines)
    if t0.doc_url:
        text += f'\n<a href="{html.escape(t0.doc_url, quote=True)}">View filing</a>'
    return text
