"""
Fine-grid neighborhood robustness check around the weight combination
chosen by tune_weights.py's grid search (momentum 0.50 / low_vol 0.10 /
parkinson_vol 0.0 / high52 0.30 / liquidity 0.10), for the large-cap +
midcap (Nifty 50 + Nifty Next 50 + Nifty Midcap 100) universe.

A single best grid point can be a lucky spike rather than a real,
generalizable optimum - this checks whether nearby combinations (step
0.05, total deviation from the best point capped at 0.20) also perform
well on both train and test, or whether performance craters just one
step away.

Run:
    python neighborhood_check.py
"""
import numpy as np
import pandas as pd

import data
import metrics
import portfolio
from tune_weights import (FACTOR_NAMES, START, END, TRAIN_END, TEST_START, STARTING_CAPITAL,
                           precompute_factor_series, sharpe_for_combo, _integer_partitions)
from universe import FULL_UNIVERSE

BEST = {"momentum": 0.50, "low_vol": 0.10, "parkinson_vol": 0.0, "high52": 0.30, "liquidity": 0.10}
STEP = 0.05
MAX_DEVIATION = 0.20  # total absolute deviation from BEST, in weight units


def neighborhood_grid(best, names, step=STEP, max_deviation=MAX_DEVIATION):
    steps = round(1.0 / step)
    best_steps = {k: round(v / step) for k, v in best.items()}
    combos = []
    for parts in _integer_partitions(len(names), steps):
        combo = dict(zip(names, parts))
        deviation = sum(abs(combo[k] - best_steps[k]) for k in names) * step
        if deviation <= max_deviation:
            combos.append({k: round(v * step, 2) for k, v in combo.items()})
    return combos


def main():
    print("=== Loading data ===")
    history_report = data.filter_by_history_length(FULL_UNIVERSE, min_years=6, start="2019-01-01")
    clean_universe = history_report[history_report["passes"]].index.tolist()

    ohlcv = data.download_ohlcv(tickers=clean_universe, start="2019-06-01", end=END)
    prices = ohlcv["close"].dropna(axis=1, thresh=int(len(ohlcv["close"]) * 0.95))
    valid_tickers = prices.columns
    high, low, volume = ohlcv["high"][valid_tickers], ohlcv["low"][valid_tickers], ohlcv["volume"][valid_tickers]
    log_ret = data.compute_log_returns(prices)

    train_dates = portfolio.rebalance_dates(prices.index, START, TRAIN_END)
    test_dates = portfolio.rebalance_dates(prices.index, TEST_START, END)
    all_dates = sorted(set(train_dates) | set(test_dates))
    factor_cache = precompute_factor_series(prices, log_ret, high, low, volume, all_dates)

    grid = neighborhood_grid(BEST, FACTOR_NAMES)
    print(f"\n=== Neighborhood grid: {len(grid)} points within {MAX_DEVIATION} of the best combo ===")

    results = []
    for w in grid:
        train_sharpe, train_ret, train_dd = sharpe_for_combo(prices, log_ret, factor_cache, w, train_dates)
        test_sharpe, test_ret, test_dd = sharpe_for_combo(prices, log_ret, factor_cache, w, test_dates)
        if np.isnan(train_sharpe) or np.isnan(test_sharpe):
            continue
        results.append({**w, "train_sharpe": train_sharpe, "test_sharpe": test_sharpe,
                         "min_sharpe": min(train_sharpe, test_sharpe)})

    df = pd.DataFrame(results).sort_values("min_sharpe", ascending=False)
    best_row = df[(df[list(FACTOR_NAMES)] == pd.Series(BEST)).all(axis=1)]

    print(f"\nBest point itself: train={best_row['train_sharpe'].values[0]:.3f}, "
          f"test={best_row['test_sharpe'].values[0]:.3f}")
    print(f"\nNeighborhood test Sharpe range: {df['test_sharpe'].min():.3f} to {df['test_sharpe'].max():.3f}")
    print(f"Neighborhood train Sharpe range: {df['train_sharpe'].min():.3f} to {df['train_sharpe'].max():.3f}")

    baseline_test_sharpe = 1.36  # the 100-stock (Nifty 100 only) universe's chosen result, for comparison
    beats_baseline = df[(df["train_sharpe"] > baseline_test_sharpe) & (df["test_sharpe"] > baseline_test_sharpe)]
    print(f"\nFraction of neighborhood beating {baseline_test_sharpe} Sharpe on BOTH windows: "
          f"{len(beats_baseline)}/{len(df)} ({len(beats_baseline) / len(df):.0%})")

    print("\n=== Full neighborhood, sorted by min(train,test) Sharpe ===")
    print(df.to_string(index=False))

    df.to_csv("neighborhood_check_results.csv", index=False)
    print("\nWrote neighborhood_check_results.csv")
    return df


if __name__ == "__main__":
    main()
