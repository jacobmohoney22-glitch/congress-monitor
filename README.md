# Government Filings Monitor

Sends a Telegram alert when a U.S. Senator, Representative, or senior executive-branch official
**discloses new stock trades** (STOCK Act periodic transaction reports and OGE 278-T filings).

Data comes from the open dataset behind kadoa.com's Congress Trading Monitor
(`kadoa-org/congress-trading-monitor`, MIT), which parses the House Clerk, Senate eFD and Office of
Government Ethics disclosure systems. Read-only; not financial advice.

## What you get

One alert **per filing** (not per trade), bundled into one Telegram message per run:

```
🏛 GOVERNMENT FILING · Jane Roe
Representative (D-CA)
Filed 2026-11-10 · 3 matching trades

• BUY AAPL · $15,001 - $50,000 · traded 2026-11-02 · 8d to file
• SELL (partial) MSFT · $50,001 - $100,000 · traded 2026-10-27 · 14d to file  [spouse]
   ↳ Insiders also bought MSFT: 2 insiders, $120,000 (SEC Form 4, last 14 days)
View filing
```

* **LATE** marks filings made more than 45 days after the trade.
* The **"Insiders also bought"** line is an optional cross-check against your own insider-monitor's
  saved purchases (it reads that repo's public `monitor-state` branch; set `INSIDER_STATE_URL=none` to disable).
* Names in `WATCH_FILERS` always alert (marked with a star), ignoring the amount/ticker rules.

## How fast is it? (be realistic)

* Officials may file up to 45 days after a trade (median in this data: about 30 days), so this is
  never a real-time signal about the trade itself.
* Kadoa refreshes the dataset about once a day, so an alert can arrive up to a day after the filing.
* The bot checks twice an hour; an unchanged file is skipped using its ETag.

## Rules (all adjustable with repository *variables*)

| Variable | Default | Meaning |
|---|---|---|
| `MIN_AMOUNT` | 15001 | Lower bound of the disclosed range must be at least this (disclosures are ranges) |
| `ONLY_TICKERS` | true | Skip assets with no ticker (private funds, bonds, ...) |
| `BRANCH` | all | `all`, `congress` or `executive` |
| `MAX_FILING_AGE_DAYS` | 10 | Ignore filings older than this (backfills / re-parsed old filings) |
| `WATCH_FILERS` | (none) | Comma-separated names that always alert, e.g. `pelosi,tuberville` |
| `INSIDER_STATE_URL` | auto | Insider-monitor state URL; `none` disables the cross-check |

## Setup

1. Create a **new empty public GitHub repo** (e.g. `congress-monitor`) and push this folder.
2. Add secrets (Settings > Secrets and variables > Actions > **Secrets**): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
3. Actions tab > *Government filings monitor* > *Run workflow* with **Dry run** ticked. Read the log.
4. Run once without dry run (baseline: records existing trades silently and sends "Monitor started").

## Known limits

* Depends on Kadoa's public dataset staying available and keeping its current format.
* The file holds only the latest ~5,000 trades; the bot only needs new ones.
* Amounts are disclosed ranges, not exact values. Some filings are parsed late or with gaps.
