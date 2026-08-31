"""
Walk-forward validation: confirms the strategy's factor weights (tuned on
the 2021-2023 window) still hold up on the unseen 2024-2025 window,
rather than being overfit to one period.

Run this file directly to reproduce both legs:

    python validate_walkforward.py

For each window it runs the same pipeline as citadel.py (universe filter
-> data download -> factor scoring -> portfolio construction -> backtest
-> metrics) and prints annualized return, max drawdown, and Sharpe ratio
side by side.
"""
import pandas as pd

import data
import metrics
import portfolio
from backtest import run_backtest
from universe import FULL_UNIVERSE

N_STOCKS = 10
STARTING_CAPITAL = 1_00_00_000

WINDOWS = {
    "train_2021_2023": ("2021-01-01", "2023-12-31"),
    "test_2024_2025": ("2024-01-01", "2025-12-31"),
}


def run_window(start: str, end: str) -> dict:
    history_report = data.filter_by_history_length(FULL_UNIVERSE, min_years=6, start="2019-01-01")
    clean_universe = history_report[history_report["passes"]].index.tolist()

    ohlcv = data.download_ohlcv(tickers=clean_universe, start="2019-06-01", end=end)
    prices = ohlcv["close"].dropna(axis=1, thresh=int(len(ohlcv["close"]) * 0.95))
    valid_tickers = prices.columns
    high, low, volume = ohlcv["high"][valid_tickers], ohlcv["low"][valid_tickers], ohlcv["volume"][valid_tickers]
    log_ret = data.compute_log_returns(prices)

    weights_by_date = portfolio.build_portfolio_weights(
        prices, log_ret, fundamentals=None, start=start, end=end, n_stocks=N_STOCKS,
        high=high, low=low, volume=volume,
    )
    nav, trades, _ = run_backtest(prices, weights_by_date, capital=STARTING_CAPITAL)
    report = metrics.full_report(nav, trades, STARTING_CAPITAL)
    return {
        "annualized_return": report["annualized_return"],
        "max_drawdown": report["max_drawdown"],
        "sharpe_ratio": report["sharpe_ratio"],
        "total_net_pnl": report["total_net_pnl"],
    }


def main():
    results = {}
    for label, (start, end) in WINDOWS.items():
        print(f"\n=== {label}: {start} to {end} ===")
        results[label] = run_window(start, end)
        for k, v in results[label].items():
            print(f"  {k}: {v}")

    print("\n=== Summary: train vs. unseen test ===")
    print(pd.DataFrame(results).T)
    return results


if __name__ == "__main__":
    main()
