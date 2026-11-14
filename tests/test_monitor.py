from datetime import date, datetime, timezone

import pytest

from congress_monitor.alerts import format_group, group_by_filing, select
from congress_monitor.config import Config
from congress_monitor.data import parse_trade, parse_trades
from congress_monitor.insider import InsiderContext
from congress_monitor.notify import pack_messages, split_message
from congress_monitor.runner import run_once
from congress_monitor.state import State
from tests.helpers import FakeClient, FakeInsiders, FakeNotifier, row

NOW = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


def cfg(tmp_path, **kw):
    return Config(state_path=str(tmp_path / "state.json"), **kw)


def trades(*rows):
    return parse_trades(list(rows))


# ---------- parsing ----------
def test_parse_trade():
    t = parse_trade(row("h1", owner="SP", late=1))
    assert (t.filer, t.ticker, t.amt_low, t.is_late, t.owner) == ("Jane Roe", "AAPL", 15001, True, "SP")


def test_unusable_rows_are_skipped():
    assert parse_trade({"id": "x"}) is None
    assert parse_trades([{"id": "x"}, "junk", row("ok")]) != []
    assert len(parse_trades([{"id": "x"}, "junk", row("ok")])) == 1


def test_missing_amounts_and_ticker_dont_crash():
    t = parse_trade(row("h1", ticker=None, low=None, high=None))
    assert t.ticker == "" and t.amt_low is None


# ---------- selection rules ----------
@pytest.mark.parametrize("kw,expected", [
    ({}, True),
    ({"low": 1001, "high": 15000}, False),            # below the $15,001 floor
    ({"ticker": None}, False),                        # no ticker (private fund etc.)
    ({"filed": "2026-10-20"}, False),                 # filed 23 days ago: stale news
    ({"filed": "2026-11-05"}, True),                  # 7 days: still fresh
    ({"ttype": "Sale (Full)"}, True),                 # sales count too
])
def test_default_rules(tmp_path, kw, expected):
    assert bool(select(trades(row("h1", **kw)), cfg(tmp_path), TODAY)) is expected


def test_watchlist_bypasses_amount_and_ticker_rules(tmp_path):
    c = cfg(tmp_path, watch_filers=("jane",))
    t = trades(row("h1", ticker=None, low=1001, high=15000), row("h2", filer="Bob Other", low=1001, high=15000))
    assert [x.id for x in select(t, c, TODAY)] == ["h1"]


def test_watchlist_does_not_bypass_filing_age(tmp_path):
    c = cfg(tmp_path, watch_filers=("jane",))
    assert select(trades(row("h1", filed="2026-09-01")), c, TODAY) == []


def test_branch_filter(tmp_path):
    t = trades(row("h1"), row("e1", branch="executive", chamber=None, party=None, state=None,
                              filer="Some Official", office="Secretary", agency="Dept of X"))
    assert [x.id for x in select(t, cfg(tmp_path, branch="executive"), TODAY)] == ["e1"]
    assert [x.id for x in select(t, cfg(tmp_path, branch="congress"), TODAY)] == ["h1"]
    assert len(select(t, cfg(tmp_path), TODAY)) == 2


def test_config_rejects_bad_branch():
    with pytest.raises(SystemExit):
        Config.from_env({"BRANCH": "judicial"})


def test_config_insider_url_defaults_to_same_owner():
    c = Config.from_env({"GITHUB_REPOSITORY_OWNER": "jane"})
    assert c.insider_state_url == "https://raw.githubusercontent.com/jane/insider-monitor/monitor-state/state.json"
    assert Config.from_env({"GITHUB_REPOSITORY_OWNER": "jane", "INSIDER_STATE_URL": "none"}).insider_state_url == ""
    assert Config.from_env({}).insider_state_url == ""


# ---------- grouping / formatting ----------
def test_one_alert_per_filing_not_per_trade(tmp_path):
    t = trades(row("a1", ticker="AAPL"), row("a2", ticker="MSFT"), row("b1", filer="Bob", doc="https://x/2.pdf"))
    groups = group_by_filing(t, cfg(tmp_path))
    assert len(groups) == 2 and sorted(len(g.trades) for g in groups) == [1, 2]


def test_message_content(tmp_path):
    c = cfg(tmp_path)
    t = trades(row("a1", ticker="AAPL", late=1, owner="SP", ttype="Sale (Partial)", days=61))
    msg = format_group(group_by_filing(t, c)[0], None, TODAY, c)
    for piece in ("GOVERNMENT FILING", "Jane Roe", "Representative (D-CA)", "SELL (partial) AAPL",
                  "LATE", "spouse", "61d to file", "View filing"):
        assert piece in msg


def test_executive_filer_shows_office_and_agency(tmp_path):
    c = cfg(tmp_path)
    t = trades(row("e1", branch="executive", chamber=None, party=None, state=None,
                   filer="Some Official", office="Governor", agency="Federal Reserve"))
    assert "Governor, Federal Reserve" in format_group(group_by_filing(t, c)[0], None, TODAY, c)


def test_long_filings_are_capped(tmp_path):
    c = cfg(tmp_path, max_lines_per_filing=5)
    t = trades(*[row(f"r{i}", ticker="AAPL", high=50000 + i) for i in range(40)])
    msg = format_group(group_by_filing(t, c)[0], None, TODAY, c)
    assert msg.count("\u2022") == 5 and "+ 35 more matching trades" in msg


def test_watched_filer_is_starred_and_listed_first(tmp_path):
    c = cfg(tmp_path, watch_filers=("bob",))
    t = trades(row("a1", high=900000), row("b1", filer="Bob Watched", doc="https://x/2.pdf", high=20000))
    g = group_by_filing(t, c)
    assert g[0].filer == "Bob Watched" and "\u2b50" in format_group(g[0], None, TODAY, c)


def test_insider_cross_check_line(tmp_path):
    c = cfg(tmp_path)
    t = trades(row("a1", ticker="AAPL"), row("a2", ticker="MSFT"))
    msg = format_group(group_by_filing(t, c)[0], FakeInsiders({"AAPL": (2, 120000.0)}), TODAY, c)
    assert "Insiders also bought AAPL: 2 insiders, $120,000" in msg and "MSFT: " not in msg


def test_insider_context_lookup_and_failure_modes():
    ctx = InsiderContext([{"ticker": "AAPL", "insider_key": "1", "tx_date": "2026-11-08", "value": 1000},
                          {"ticker": "AAPL", "insider_key": "2", "tx_date": "2026-11-09", "value": 500},
                          {"ticker": "AAPL", "insider_key": "1", "tx_date": "2026-11-09", "value": 250},
                          {"ticker": "AAPL", "insider_key": "3", "tx_date": "2026-09-01", "value": 9999},
                          {"ticker": "MSFT", "insider_key": "9", "tx_date": "2026-11-09", "value": 1}])
    assert ctx.lookup("AAPL", date(2026, 11, 12), 14) == (2, 1750.0)      # old buy and other ticker excluded
    assert ctx.lookup("TSLA", date(2026, 11, 12), 14) is None
    assert InsiderContext.load("") is None                               # disabled
    assert InsiderContext.load("http://127.0.0.1:9/none") is None        # unreachable -> silently skipped


# ---------- end to end ----------
def test_baseline_then_alert_once_then_nothing(tmp_path):
    c, n = cfg(tmp_path), FakeNotifier()
    client = FakeClient([row("old1", filed="2026-11-09")])
    s1 = run_once(c, client, n, insider_loader=lambda: None, now=NOW)
    assert s1["first_run"] and len(n.sent) == 1 and "Monitor started" in n.sent[0]   # silent baseline

    client.set_rows([row("old1", filed="2026-11-09"), row("new1", ticker="NVDA", filed="2026-11-11")])
    s2 = run_once(c, client, n, insider_loader=lambda: None, now=NOW)
    assert s2["alert_filings"] == 1 and "NVDA" in n.sent[-1] and len(n.sent) == 2

    sent = len(n.sent)
    client.set_rows(client.rows)                              # file changed, nothing new in it
    assert run_once(c, client, n, insider_loader=lambda: None, now=NOW)["alert_filings"] == 0
    assert len(n.sent) == sent


def test_unchanged_file_is_skipped_via_etag(tmp_path):
    c, n = cfg(tmp_path), FakeNotifier()
    client = FakeClient([row("a")])
    run_once(c, client, n, insider_loader=lambda: None, now=NOW)
    s = run_once(c, client, n, insider_loader=lambda: None, now=NOW)       # same version: 304
    assert s["unchanged"] is True and s["rows"] == 0


def test_failed_send_is_retried_even_with_etag(tmp_path):
    c = cfg(tmp_path)
    client = FakeClient([])
    run_once(c, client, FakeNotifier(), insider_loader=lambda: None, now=NOW)
    client.set_rows([row("new1", filed="2026-11-11")])
    s = run_once(c, client, FakeNotifier(ok=False), insider_loader=lambda: None, now=NOW)
    assert s["alert_filings"] == 0
    good = FakeNotifier()
    s = run_once(c, client, good, insider_loader=lambda: None, now=NOW)    # file NOT re-served as 304
    assert s["alert_filings"] == 1 and len(good.sent) == 1


def test_rows_that_never_qualify_do_not_alert_or_repeat(tmp_path):
    c, n = cfg(tmp_path), FakeNotifier()
    client = FakeClient([])
    run_once(c, client, n, insider_loader=lambda: None, now=NOW)
    client.set_rows([row("small", low=1001, high=15000, filed="2026-11-11"),
                     row("fund", ticker=None, filed="2026-11-11"),
                     row("stale", filed="2026-08-01")])
    s = run_once(c, client, n, insider_loader=lambda: None, now=NOW)
    assert s["new_rows"] == 3 and s["alert_filings"] == 0 and len(n.sent) == 1
    assert set(State.load(c.state_path).seen) == {"small", "fund", "stale"}


def test_many_filings_are_bundled_into_one_message(tmp_path):
    c, n = cfg(tmp_path), FakeNotifier()
    client = FakeClient([])
    run_once(c, client, n, insider_loader=lambda: None, now=NOW)
    client.set_rows([row(f"r{i}", filer=f"Person {i}", doc=f"https://x/{i}.pdf", filed="2026-11-11")
                     for i in range(4)])
    s = run_once(c, client, n, insider_loader=lambda: None, now=NOW)
    assert s["alert_filings"] == 4 and s["alert_messages"] == 1 and len(n.sent) == 2


def test_cross_check_is_attached_to_real_alerts(tmp_path):
    c, n = cfg(tmp_path), FakeNotifier()
    client = FakeClient([])
    run_once(c, client, n, insider_loader=lambda: None, now=NOW)
    client.set_rows([row("n1", ticker="AAPL", filed="2026-11-11")])
    run_once(c, client, n, insider_loader=lambda: FakeInsiders({"AAPL": (3, 500000.0)}), now=NOW)
    assert "Insiders also bought AAPL: 3 insiders" in n.sent[-1]


def test_seen_ids_are_pruned_to_whats_in_the_file(tmp_path):
    c = cfg(tmp_path)
    client = FakeClient([row("a"), row("b")])
    run_once(c, client, FakeNotifier(), insider_loader=lambda: None, now=NOW)
    client.set_rows([row("b")])
    run_once(c, client, FakeNotifier(), insider_loader=lambda: None, now=NOW)
    assert set(State.load(c.state_path).seen) == {"b"}


def test_corrupt_state_not_silently_reset(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{nope")
    with pytest.raises(SystemExit):
        State.load(str(p))


def test_pack_and_split():
    assert pack_messages([]) == []
    assert len(pack_messages(["a" * 1800, "b" * 1800, "c" * 100], 3500)) == 2
    assert all(len(x) <= 4096 for x in split_message("\n".join("x" * 90 for _ in range(200))))
