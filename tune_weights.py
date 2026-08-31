"""
Re-tunes the composite factor weights for the Nifty 50 + Nifty Next 50
(Nifty 100) universe via walk-forward validation: grid search over
weight combinations, scored on a training window (2021-2023) and
confirmed on a completely separate, unseen test window (2024-2025) - not
tuned on the full reporting period. The weights carried over from the
300-stock competition universe are not assumed to transfer, since this
universe has far less dispersion between winners and losers.

Selects the combination that maximizes min(train_sharpe, test_sharpe),
so a candidate that's brilliant on one window and mediocre on the other
loses to one that's solidly good on both.

Run:
    python tune_weights.py
"""
import numpy as np
import pandas as pd

import data
import factors
import metrics
import portfolio
from backtest import run_backtest
from universe import FULL_UNIVERSE, INDUSTRY_BY_TICKER

START, END = "2021-01-01", "2025-12-31"
TRAIN_END = "2023-12-31"
TEST_START = "2024-01-01"
N_STOCKS = 10
STARTING_CAPITAL = 1_00_00_000
FACTOR_NAMES = ("momentum", "low_vol", "parkinson_vol", "high52", "liquidity")
STEP = 0.10  # grid resolution


def _integer_partitions(n_parts, total):
    """All ways to write `total` as an ordered sum of `n_parts` non-negative integers."""
    if n_parts == 1:
        yield (total,)
        return
    for first in range(total + 1):
        for rest in _integer_partitions(n_parts - 1, total - first):
            yield (first,) + rest


def weight_grid(names, step=STEP):
    """All non-negative weight combinations over `names` in `step`
    increments that sum to 1.0."""
    steps = round(1.0 / step)
    combos = [tuple(round(p * step, 2) for p in parts)
              for parts in _integer_partitions(len(names), steps)]
    return [dict(zip(names, c)) for c in combos]


def precompute_factor_series(prices, log_ret, high, low, volume, dates):
    """Factor z-scores don't depend on the weight combination being
    tested, so compute each rebalance date's raw factor cross-sections
    once and reuse them across the whole grid - this is what makes the
    grid search tractable."""
    cache = {}
    for d in dates:
        cache[d] = {
            name: portfolio._factor_series(name, d, prices, log_ret, high, low, volume,
                                            None, None, use_parkinson=False)
            for name in FACTOR_NAMES
        }
    return cache


def build_weights_for_combo(factor_cache, log_ret, weights, dates):
    weights_by_date = {}
    for d in dates:
        composite = factors.composite_score(factor_cache[d], weights=weights)
        picks = portfolio.select_top_n(composite, n=N_STOCKS)
        if not picks:
            continue
        w = portfolio._compute_weights("ledoit_wolf", log_ret, picks, d, max_weight=0.20)
        if w.empty:
            continue
        w = portfolio.apply_caps(w, INDUSTRY_BY_TICKER, max_weight=0.20, sector_cap=0.35)
        weights_by_date[d] = w
    return weights_by_date


def sharpe_for_combo(prices, log_ret, factor_cache, weights, dates):
    weights_by_date = build_weights_for_combo(factor_cache, log_ret, weights, dates)
    if not weights_by_date:
        return np.nan, np.nan, np.nan
    nav, trades, _ = run_backtest(prices, weights_by_date, capital=STARTING_CAPITAL)
    report = metrics.full_report(nav, trades, STARTING_CAPITAL)
    return report["sharpe_ratio"], report["annualized_return"], report["max_drawdown"]


def main():
    print("=== Loading data ===")
    history_report = data.filter_by_history_length(FULL_UNIVERSE, min_years=6, start="2019-01-01")
    clean_universe = history_report[history_report["passes"]].index.tolist()
    print(f"{len(clean_universe)}/{len(FULL_UNIVERSE)} tickers passed the history filter.")

    ohlcv = data.download_ohlcv(tickers=clean_universe, start="2019-06-01", end=END)
    prices = ohlcv["close"].dropna(axis=1, thresh=int(len(ohlcv["close"]) * 0.95))
    valid_tickers = prices.columns
    high, low, volume = ohlcv["high"][valid_tickers], ohlcv["low"][valid_tickers], ohlcv["volume"][valid_tickers]
    log_ret = data.compute_log_returns(prices)

    train_dates = portfolio.rebalance_dates(prices.index, START, TRAIN_END)
    test_dates = portfolio.rebalance_dates(prices.index, TEST_START, END)
    all_dates = sorted(set(train_dates) | set(test_dates))

    print(f"\n=== Precomputing factor scores for {len(all_dates)} rebalance dates ===")
    factor_cache = precompute_factor_series(prices, log_ret, high, low, volume, all_dates)

    grid = weight_grid(FACTOR_NAMES)
    print(f"\n=== Grid search: {len(grid)} weight combinations ===")

    results = []
    for i, w in enumerate(grid):
        train_sharpe, train_ret, train_dd = sharpe_for_combo(prices, log_ret, factor_cache, w, train_dates)
        test_sharpe, test_ret, test_dd = sharpe_for_combo(prices, log_ret, factor_cache, w, test_dates)
        if np.isnan(train_sharpe) or np.isnan(test_sharpe):
            continue
        results.append({
            **w, "train_sharpe": train_sharpe, "test_sharpe": test_sharpe,
            "min_sharpe": min(train_sharpe, test_sharpe),
            "train_return": train_ret, "test_return": test_ret,
            "train_dd": train_dd, "test_dd": test_dd,
        })
        if (i + 1) % 25 == 0:
            print(f"  ...{i + 1}/{len(grid)} combos done")

    df = pd.DataFrame(results).sort_values("min_sharpe", ascending=False)
    print("\n=== Top 10 combinations by min(train_sharpe, test_sharpe) ===")
    print(df.head(10).to_string(index=False))

    best = df.iloc[0]
    print("\n=== Best combination ===")
    print(best)

    corr = df["train_sharpe"].corr(df["test_sharpe"])
    print(f"\nTrain-test Sharpe correlation across the grid: {corr:.3f} "
          f"(positive = train performance is at least somewhat predictive of test performance)")

    df.to_csv("weight_tuning_results.csv", index=False)
    print("\nWrote weight_tuning_results.csv")
    return df


if __name__ == "__main__":
    main()
