from __future__ import annotations

from datetime import datetime, timezone

from .alerts import format_group, group_by_filing, select
from .insider import InsiderContext
from .notify import SEPARATOR, pack_messages
from .state import State


def run_once(cfg, client, notifier, insider_loader=None, now: datetime | None = None,
             persist: bool = True) -> dict:
    now = now or datetime.now(timezone.utc)
    today = now.date()
    state = State.load(cfg.state_path)
    first_run = state.is_new
    summary = {"first_run": first_run, "unchanged": False, "rows": 0, "new_rows": 0,
               "alert_trades": 0, "alert_filings": 0, "alert_messages": 0}

    rows, etag = client.fetch(state.etag)
    if rows is None:                       # file unchanged since last run: nothing to do
        summary["unchanged"] = True
        return summary
    summary["rows"] = len(rows)

    new = [t for t in rows if t.id not in state.seen]
    summary["new_rows"] = len(new)
    wanted = {t.id for t in select(new, cfg, today)}
    for t in new:                          # rows that can never alert are settled right away
        if first_run or t.id not in wanted:
            state.seen[t.id] = t.filing_date

    all_sent = True
    if not first_run and wanted:
        groups = group_by_filing([t for t in new if t.id in wanted], cfg)
        loader = insider_loader or (lambda: InsiderContext.load(cfg.insider_state_url))
        ctx = loader()
        texts = [format_group(g, ctx, today, cfg) for g in groups]
        summary["alert_trades"] = len(wanted)
        for bundle in pack_messages(texts):          # one notification per bundle
            if notifier.send(SEPARATOR.join(texts[i] for i in bundle)):
                summary["alert_messages"] += 1
                for i in bundle:                     # only mark what was actually delivered
                    summary["alert_filings"] += 1
                    for t in groups[i].trades:
                        state.seen[t.id] = t.filing_date
            else:
                all_sent = False

    if first_run:
        state.started = now.isoformat()
        notifier.send(f"\U0001F3DB GOVERNMENT FILINGS \u00b7 Monitor started. Baseline loaded from "
                      f"{len(rows)} recent disclosed trades; alerts begin with the next new filing.")

    current = {t.id for t in rows}
    state.seen = {k: v for k, v in state.seen.items() if k in current}
    # if any alert failed to send, forget the ETag so the next run re-reads the file and retries
    state.etag = etag if all_sent else ""
    if persist:
        state.save(cfg.state_path)
    return summary
