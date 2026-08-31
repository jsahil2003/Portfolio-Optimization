"""
Finesse x Citadel Portfolio Challenge - main entry point.

Wires together the full pipeline: universe -> data -> factors -> portfolio
construction -> backtest -> metrics -> Excel export. Run this file directly
to reproduce the submission workbook end to end.

    python citadel.py

Uses the lookahead-free factor set by default (CONCEPTS.md §24-34):
momentum, close-to-close low-volatility, Parkinson intraday volatility,
52-week-high proximity, and liquidity, all built purely from historical
price/volume data, walk-forward validated (tuned on 2021-2023, confirmed
on unseen 2024-2025, then re-validated with a 5th factor added and
stress-tested via fine-grid neighborhood + independent split checks, see
CONCEPTS.md §34). No fundamentals snapshot is fetched, since the default
factor set doesn't need one - see CONCEPTS.md §18 for why the retired
"original" set (value/quality from current-snapshot fundamentals) carried
a lookahead-bias caveat this one doesn't.

See CONCEPTS.md for the math/intuition behind every step, CODE_GUIDE.md
for a file-by-file map, and PROJECT_SUMMARY.md for the consolidated
narrative version of this whole project.
"""
import pickle

import pandas as pd

import data
import metrics
import portfolio
from export_excel import build_workbook
from backtest import run_backtest
from universe import FULL_UNIVERSE

START = "2021-01-01"
END = "2025-12-31"
N_STOCKS = 10
STARTING_CAPITAL = 1_00_00_000

# Both benchmarks named in the brief: Nifty 100 isn't a single index we can
# fetch directly, so Nifty 50 (^NSEI) stands in as the large-cap benchmark,
# and Nifty 500 TMI (^CRSLDX) as the broadest applicable comparison given
# the strategy also draws from mid/smallcap.
BENCHMARKS = {"NIFTY50": "^NSEI", "NIFTY500_TMI": "^CRSLDX"}


def main():
    print("=== Step 1: Filter universe to stocks with clean, continuous history ===")
    # Extra lookback before START so momentum/vol factors have data on day 1.
    history_report = data.filter_by_history_length(FULL_UNIVERSE, min_years=6, start="2019-01-01")
    clean_universe = history_report[history_report["passes"]].index.tolist()
    print(f"{len(clean_universe)}/{len(FULL_UNIVERSE)} tickers passed the history filter.")

    print("\n=== Step 2: Download OHLCV (Close, High, Low, Volume) ===")
    ohlcv = data.download_ohlcv(tickers=clean_universe, start="2019-06-01", end=END)
    prices = ohlcv["close"].dropna(axis=1, thresh=int(len(ohlcv["close"]) * 0.95))
    valid_tickers = prices.columns
    high, low, volume = ohlcv["high"][valid_tickers], ohlcv["low"][valid_tickers], ohlcv["volume"][valid_tickers]
    log_ret = data.compute_log_returns(prices)

    report = data.sanity_check(prices, log_ret)
    print("Date range:", report["date_range"], "| Assets:", report["n_assets"])

    print("\n=== Step 3: Build monthly-rebalanced, Ledoit-Wolf min-variance-weighted portfolio ===")
    print("    (lookahead-free factor set: momentum, low-vol, parkinson-vol, 52-week-high, liquidity)")
    weights_by_date = portfolio.build_portfolio_weights(
        prices, log_ret, fundamentals=None, start=START, end=END, n_stocks=N_STOCKS,
        high=high, low=low, volume=volume,
    )
    print(f"{len(weights_by_date)} rebalance dates generated.")

    print("\n=== Step 4: Backtest ===")
    nav, trades, holdings_log = run_backtest(prices, weights_by_date, capital=STARTING_CAPITAL)

    print("\n=== Step 5: Benchmarks ===")
    benchmark_navs = {}
    for name, ticker in BENCHMARKS.items():
        bench_prices = data.download_prices(tickers=[ticker], start=nav.index.min(), end=END)
        bench_prices = bench_prices.reindex(nav.index).ffill().bfill()
        benchmark_navs[name] = STARTING_CAPITAL * (bench_prices.iloc[:, 0] / bench_prices.iloc[0, 0])

    print("\n=== Step 6: Metrics ===")
    perf_report = metrics.full_report(nav, trades, STARTING_CAPITAL, benchmark_navs=benchmark_navs)
    for k, v in perf_report.items():
        if not isinstance(v, pd.Series):
            print(f"  {k}: {v}")

    print("\n=== Step 7: Export submission workbook ===")
    build_workbook("citadel_submission.xlsx", weights_by_date, nav, None, perf_report, trades,
                    benchmark_navs=benchmark_navs)
    print("Wrote citadel_submission.xlsx")

    with open("citadel_run_cache.pkl", "wb") as f:
        pickle.dump({
            "nav": nav, "trades": trades, "benchmark_navs": benchmark_navs,
            "perf_report": perf_report, "weights_by_date": weights_by_date,
        }, f)

    return nav, trades, perf_report


if __name__ == "__main__":
    main()
