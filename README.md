# Finesse x Citadel Portfolio Challenge

A quantitative long-only equity portfolio built from Nifty 100 + Nifty
Midcap 100 + Nifty Smallcap 100 (300 stocks), backtested 2021-01-01 to
2025-12-31 against a ₹1,00,00,000 starting capital with 0.1% transaction
cost per trade, benchmarked against NIFTY 50 and NIFTY 500 TMI.

## Strategy

Every month, every eligible stock is scored on five signals, each
z-scored and combined into one composite score. The top 10 stocks by
composite score are held for that month.

| Signal | Weight | What it measures |
|---|---|---|
| Momentum | 40% | 12-month return, most recent month excluded — stocks that have been rising tend to keep rising over medium horizons |
| Low-volatility (close-to-close) | 25% | Trailing 6-month realized volatility, inverted — calmer stocks have historically shown better risk-adjusted returns |
| Parkinson volatility (intraday range) | 10% | Trailing 6-month volatility from each day's High-Low range, inverted — captures intraday swings that close-to-close volatility misses |
| 52-week-high proximity | 15% | Current price ÷ trailing 12-month high — stocks near their own recent high tend to keep outperforming |
| Liquidity | 10% | Amihud illiquidity, sign-flipped — the strategy trades often enough that easy-to-trade names matter |

All five signals are computed purely from historical price/volume data
(no company fundamentals), so the backtest carries no lookahead bias.

Once the 10 stocks are picked, capital is allocated across them using
Ledoit-Wolf shrinkage minimum-variance weighting, capped at 20% per name
and 35% per NSE industry sector (the sector cap prevents the picks from
concentrating in one sector when momentum/low-vol/52-week-high all favor
it at once — backtested to remove every >40%-in-one-sector rebalance
while slightly improving return, drawdown, and Sharpe). Rebalanced
monthly, in whole shares only.

The factor weights (40/25/10/15/10) were tuned on 2021-2023 data and
confirmed out-of-sample on unseen 2024-2025 data — see
[`validate_walkforward.py`](validate_walkforward.py).

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
| `optimizers.py` | Weighting-scheme helpers used by `portfolio.py` |
| `export_excel.py` | Builds the submission workbook |
| `validate_walkforward.py` | Train (2021-2023) / test (2024-2025) walk-forward validation |
| `citadel_submission.xlsx` | The generated submission workbook (deliverable) |

## Setup

Requires Python 3.10+.

```bash
pip install numpy pandas scipy scikit-learn requests yfinance openpyxl
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

## Testing

To confirm the strategy generalizes out-of-sample rather than being
overfit to one period, run the walk-forward validation:

```bash
python validate_walkforward.py
```

This runs the same pipeline separately on the 2021-2023 training window
and the unseen 2024-2025 test window, then prints annualized return, max
drawdown, Sharpe ratio, and total net P&L for both, side by side.
