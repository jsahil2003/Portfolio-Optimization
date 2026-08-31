# Finesse x Citadel Portfolio Challenge

A quantitative long-only equity portfolio built from Nifty 100 + Nifty
Midcap 100 + Nifty Smallcap 100 (300 stocks), backtested 2021-01-01 to
2025-12-31 against a ₹1,00,00,000 starting capital, benchmarked against
NIFTY 50 and NIFTY 500 TMI.

Every month, stocks are scored on five lookahead-free factors (momentum,
close-to-close low-volatility, Parkinson intraday volatility, 52-week-high
proximity, liquidity), the top 10 by composite score are selected, and
position sizes are set with Ledoit-Wolf shrinkage minimum-variance
weighting (capped at 20% per name).

See [`PROJECT_SUMMARY.md`](PROJECT_SUMMARY.md) for the full write-up,
[`CONCEPTS.md`](CONCEPTS.md) for the math behind every technique, and
[`CODE_GUIDE.md`](CODE_GUIDE.md) for a function-by-function map of the
code.

## Project structure

| File | Purpose |
|---|---|
| `citadel.py` | Main entry point — wires the full pipeline together |
| `universe.py` | Pulls the live 300-stock universe from niftyindices.com |
| `data.py` | Downloads OHLCV price/volume data and computes returns |
| `factors.py` | Computes the five composite selection factors |
| `portfolio.py` | Stock selection and Ledoit-Wolf min-variance weighting |
| `backtest.py` | Simulates the monthly-rebalanced portfolio with transaction costs |
| `metrics.py` | Performance metrics (returns, MDD, Sharpe, etc.) |
| `export_excel.py` | Builds the submission workbook |
| `build_slides.py` | Builds the presentation deck (`citadel_deck.pptx`) |
| `backtest.py` / `optimizers.py` | Supporting backtest and optimization utilities |
| `citadel_submission.xlsx` | The generated submission workbook (deliverable) |
| `citadel_deck.pptx` | The generated presentation deck (deliverable) |

## Setup

Requires Python 3.10+.

```bash
pip install numpy pandas scipy scikit-learn requests yfinance openpyxl python-pptx
```

## How to run

Reproduce the full pipeline (universe pull -> data download -> factor
scoring -> portfolio construction -> backtest -> Excel export) end to end:

```bash
python citadel.py
```

This downloads live market data, runs the backtest, prints a summary
report to the console, and writes `citadel_submission.xlsx` (the
submission workbook: portfolio composition & weights, returns, maximum
drawdown, benchmark comparison, and model logic/assumptions, each on its
own sheet).

To rebuild the slide deck from the cached run:

```bash
python build_slides.py
```

## Testing

There is no dedicated test suite; correctness is validated via the
walk-forward methodology described in `PROJECT_SUMMARY.md` (§3) and
`CONCEPTS.md` (§34) — the factor weights were tuned on 2021-2023 data and
confirmed out-of-sample on unseen 2024-2025 data. To sanity-check a run,
inspect the console output from `python citadel.py` (date range, asset
count) and the `Summary_Metrics` / `Drawdown` sheets in the generated
workbook.
