# Code Guide

A file-by-file, function-by-function map of what the code does and which
concept from [CONCEPTS.md](CONCEPTS.md) it implements. Use this to explain
the pipeline to the jury without re-deriving it from scratch.

## Pipeline overview

```
universe.py  →  data.py  →  factors.py  →  portfolio.py  →  backtest.py  →  metrics.py  →  export_excel.py
  ticker         prices/       factor          weights          NAV +          performance      submission
  lists          returns       scores          per date          trades         report           .xlsx
                                                                                                        ↑
                                                                                              citadel.py runs
                                                                                              all of the above
```

Run the whole thing with `python citadel.py`.

---

## `universe.py`

Pulls `NIFTY100_TICKERS`, `NIFTY_MIDCAP_100_TICKERS`, `NIFTY_SMALLCAP_100_TICKERS`
**live** from niftyindices.com on import (`load_universe()`), combined
into `FULL_UNIVERSE` (300 tickers). This is the hard constraint everything
downstream respects ("only stocks from the specified investment
universe") — being live means it can't go stale the way a hand-typed
snapshot would. Falls back to `universe_cache.csv` if the live pull fails;
re-run with network access before a real submission.

---

## `data.py`

| Function | What it does | Concept |
|---|---|---|
| `download_prices()` | Pulls adjusted-close daily prices via yfinance | Raw input data |
| `download_ohlcv()` | Pulls Close, High, Low, Volume together — genuinely point-in-time-safe, unlike `.info` | CONCEPTS §24 |
| `compute_log_returns()` | `ln(P_t/P_{t-1})` per stock per day | CONCEPTS §1 |
| `flag_suspicious_moves()` | Separates market-wide crashes from single-stock data glitches (demergers, ticker renames) by checking what fraction of the universe moved >20% on the same day | Data-quality check, not a factor |
| `filter_by_history_length()` | Drops tickers with <N years of history or a large date gap (recent IPO, suspension, delisting) | Ensures every stock has a full, clean lookback window before it can be scored |
| `sanity_check()` | Bundles the above into one report | — |

---

## `factors.py`

| Function | What it does | Concept |
|---|---|---|
| `zscore()` | Standardizes a cross-section to mean 0, std 1 | CONCEPTS §2 |
| `momentum_factor()` | 12-1 month cumulative price return | CONCEPTS §3 |
| `low_vol_factor()` | Negative trailing annualized volatility (close-to-close) | CONCEPTS §4 |
| `parkinson_vol_factor()` | Negative trailing volatility from the daily High/Low range — used alongside `low_vol_factor()` in the shipped default (they're complementary, not redundant — see CONCEPTS §34) | CONCEPTS §26, §34 |
| `high52_factor()` | Proximity to the trailing 52-week high | CONCEPTS §24 |
| `liquidity_factor()` | Negative Amihud illiquidity (price move per rupee traded), sign-flipped to prefer liquid stocks | CONCEPTS §24 |
| `reversal_factor()` | Most recent 1-month return, sign-flipped (recent losers score higher) | CONCEPTS §28 |
| `idiosyncratic_vol_factor()` | Negative volatility of returns *after* removing market beta — stock-specific risk only | CONCEPTS §28 |
| `downside_vol_factor()` | Negative volatility computed from down-days only (semi-deviation) | CONCEPTS §28 |
| `garch_vol_factor()` | GARCH(1,1) one-step-ahead volatility forecast, sign-flipped (forecasts *risk*, not return — see CONCEPTS §32 for the distinction from GARCH-in-Mean) | CONCEPTS §32 |
| `fetch_fundamentals()` | Pulls trailing P/E, P/B, ROE, D/E from yfinance `.info` — **lookahead-bias caveat, CONCEPTS §18** | Raw input for §5–6 |
| `value_factor()` | Average z-score of earnings yield and book yield | CONCEPTS §5 |
| `quality_factor()` | Average z-score of ROE and negative leverage | CONCEPTS §6 |
| `composite_score()` | Z-scores and blends *any* named dict of factors — generalized to support both `portfolio.FACTOR_SETS` recipes | CONCEPTS §7, §25 |

This is the module to point to when explaining **why these 10 stocks and
not others** — every score is a deterministic function of the code above,
nothing discretionary. `momentum_factor()`, `low_vol_factor()`,
`parkinson_vol_factor()`, `high52_factor()`, `liquidity_factor()`,
`reversal_factor()`, `idiosyncratic_vol_factor()`, `downside_vol_factor()`,
and `garch_vol_factor()` are all built from historical price/volume data
only, so none of them carry the lookahead-bias caveat that
`value_factor()`/`quality_factor()` do — see
`portfolio.FACTOR_SETS["lookahead_free"]`. Note: `reversal_factor()`,
`idiosyncratic_vol_factor()`, `downside_vol_factor()`, and
`garch_vol_factor()` are implemented and tested but **not currently used
by any shipped `FACTOR_SETS` entry** — walk-forward validation (CONCEPTS
§29, §32) found each looked promising in-sample but failed to beat the
shipped strategy out-of-sample, so none of the four is adopted. They
remain available via `build_portfolio_weights(..., factor_names=,
factor_weights=)` for future work.

---

## `portfolio.py`

| Function | What it does | Concept |
|---|---|---|
| `rebalance_dates()` | First trading day on/after each period start (default monthly, `freq="MS"`) | CONCEPTS §10 |
| `select_top_n()` | Top 10 stocks by composite score | CONCEPTS §8 |
| `inverse_vol_weights()` | `w_i ∝ 1/σ_i`, normalized to sum to 1 | CONCEPTS §9 |
| `cap_weights()` | Caps any single position at 20%, redistributing the excess | CONCEPTS §9 |
| `portfolio_realized_vol()`, `portfolio_garch_vol()`, `volatility_target_exposure()` | Optional vol-targeting overlay (rolling-window or GARCH-forecasted) — implemented, **off by default** (both tested, neither helped; see CONCEPTS §19, §33) | CONCEPTS §19, §33 |
| `_compute_weights()` | Dispatches to one of `WEIGHTING_SCHEMES` — `"inverse_vol"` (this file), `"ledoit_wolf"` / `"hrp"` (`optimizers.py`) | CONCEPTS §20–22 |
| `_factor_series()` | Dispatches to the right `factors.py` function for one named factor, given a shared date/data context | CONCEPTS §25 |
| `build_portfolio_weights()` | Orchestrates the above across every rebalance date, returns `{date: weights}`; `weighting_scheme=` selects the weighting scheme, `factor_set=` selects the composite-score recipe | Ties selection + weighting together over time |

`DEFAULT_FACTOR_WEIGHTS = {"momentum": 0.28, "low_vol": 0.30, "value": 0.21, "quality": 0.21}`
— the **retired** "original" set's weights (CONCEPTS §7), kept for
reference/comparison, no longer shipped by default.

`FACTOR_SETS = {"original": (...), "lookahead_free": (...)}` — two
composite-score recipes (CONCEPTS §25). **`"lookahead_free"` is now the
default factor_set**, using **five** factors:
`(momentum, low_vol, parkinson_vol, high52, liquidity)`, weighted
`{momentum: 0.40, low_vol: 0.25, parkinson_vol: 0.10, high52: 0.15,
liquidity: 0.10}` — chosen via **four independent validation checks**
(two train/test splits plus fine-grid neighborhood checks on each; see
CONCEPTS §34 and CHANGELOG.md for the complete methodology). Needs
`high=`/`low=`/`volume=` passed to `build_portfolio_weights()` (from
`data.download_ohlcv()`), which `citadel.py` does by default. This is
the module to point to when explaining **why these 10 stocks, weighted
this way, were chosen** — the weights aren't arbitrary or guessed;
they're a point deliberately centered in a cluster of consistently good
performance across four separate robustness checks, not just the single
best score on the data being reported.

`build_portfolio_weights(..., factor_names=, factor_weights=)`: an
override path that bypasses `FACTOR_SETS` entirely, for testing custom
factor combinations without editing the registry (used for the CONCEPTS
§28-29 signal search — `reversal`/`idio_vol`/`downside_vol` are wired
into `_factor_series()` but have no named entry in `FACTOR_SETS` since
none was adopted). Also needs `benchmark_log_ret=` if `idio_vol` is
among the requested factor names.

---

## `optimizers.py`

Two weighting schemes that use the full covariance/correlation structure
between stocks, as alternatives to `portfolio.inverse_vol_weights()`.

| Function | What it does | Concept |
|---|---|---|
| `ledoit_wolf_cov()` | Shrinkage-estimated covariance matrix (`sklearn.covariance.LedoitWolf`) | CONCEPTS §21 |
| `_min_variance_from_cov()` | Closed-form min-variance weights `w ∝ Σ⁻¹·1`, negative weights clipped, capped at 20% | CONCEPTS §20 |
| `ledoit_wolf_weights()` | Full pipeline: shrinkage covariance → min-variance weights | CONCEPTS §21 |
| `_correlation_distance()`, `_quasi_diagonalize()`, `_cluster_variance()`, `_recursive_bisection()` | The four steps of Hierarchical Risk Parity | CONCEPTS §22 |
| `hrp_weights()` | Full HRP pipeline | CONCEPTS §22 |

**`weighting_scheme` defaults to `"ledoit_wolf"`** (also available:
`"hrp"`, `"inverse_vol"`). See CONCEPTS §23 for the three-way comparison
results and CONCEPTS §31 for the correlation/diversification analysis —
including a concrete demonstration that Ledoit-Wolf gives a real, higher
weight to a negatively-correlated pair than inverse-vol does. This is
the module to point to when explaining **why 10% in each of 10 stocks
(or 1/vol-weighted) isn't the only option, and how much of each stock we
hold and why** — it's the one that actually uses the fact that some of
the 10 picks move together (or don't).

---

## `backtest.py`

`run_backtest(prices, weights_by_date, capital, txn_cost)` — CONCEPTS §11–12.

Simulates share-level holdings day by day: freezes shares between
rebalances (so returns reflect only real price moves), and on each
rebalance date computes the trades needed to hit target weights, charges
0.1% cost on traded value, and updates cash. Returns:
- `nav` — daily portfolio value series (used for all return/risk metrics)
- `trades` — one row per executed trade (ticker, date, shares, price,
  cost) — feeds turnover and gain-to-loss/accuracy
- `holdings_log` — share counts after each rebalance, for audit/debugging

This is the module to point to when explaining **how realistic the
simulation is** — it's not just "NAV = weighted sum of returns," it
actually executes trades and pays for them.

---

## `metrics.py`

| Function | Concept |
|---|---|
| `annualized_return()` | CONCEPTS §13 |
| `max_drawdown()` | CONCEPTS §14 |
| `sharpe_ratio()` | CONCEPTS §15 |
| `total_net_pnl()` | The competition's primary ranking metric (final NAV − starting capital) |
| `_fifo_round_trip_pnl()`, `gain_to_loss_ratio()`, `accuracy()` | CONCEPTS §16 |
| `turnover_stats()` | CONCEPTS §10 |
| `full_report()` | Bundles everything, plus benchmark comparison (CONCEPTS §17) |

This is the module to point to for **every number in the rubric** —
Total Net PNL, Annualized Return, MDD, Sharpe, Gain-to-Loss, Accuracy,
Trade Statistics all trace back to a single function here.

---

## `export_excel.py`

`build_workbook()` writes the required submission format: one sheet each
for Composition & Weights, Returns, Drawdown, Summary Metrics, Trade Log,
and Model Logic/Assumptions — directly matching the brief's "Submission
Requirements" checklist.

---

## `citadel.py`

The main script. Reads top to bottom as the whole strategy story:
1. Filter universe to clean-history stocks (`data.filter_by_history_length`)
2. Download OHLCV — Close, High, Low, Volume (`data.download_ohlcv`) —
   no fundamentals fetch, since the default factor set doesn't need one
3. Build the monthly-rebalanced portfolio (`portfolio.build_portfolio_weights`,
   default: lookahead-free factor set, Ledoit-Wolf weighting)
4. Backtest it (`backtest.run_backtest`)
5. Download and index both benchmarks (Nifty 50, Nifty 500 TMI)
6. Compute the full metrics report (`metrics.full_report`)
7. Export the submission workbook (`export_excel.build_workbook`)

If asked "walk me through your code," this is the file to open first —
every step is one function call into a module documented above.

---

## Talking points for the jury

- **Methodology is fully rules-based**: no manual stock picks; every
  selection and weight is reproducible from the code.
- **Zero lookahead bias**: all four shipped factors (momentum, low-vol,
  52-week-high, liquidity) are built purely from historical price/volume
  data — none of them could have used information unavailable at the
  time of any simulated decision (CONCEPTS §24, §30).
- **Risk-aware by construction**: the low-volatility factor and
  Ledoit-Wolf minimum-variance weighting both explicitly target lower
  drawdown, not just higher return.
- **Weights are walk-forward validated, not just backtested**: tuned on
  a training window (2021-2023), then confirmed — not re-tuned — on a
  genuinely unseen test window (2024-2025). CONCEPTS §30 has the full
  story, including every combination that *failed* this test, which is
  as important to the credibility of the result as the one that passed.
- **Costs are real**: the backtest executes actual trades and pays 0.1%
  on every one, so the reported PNL is genuinely net, not a gross-return
  approximation.
- **Diversification is honest, not oversold**: only ~7% of the actual
  holding pairs are negatively correlated (CONCEPTS §31) — a realistic
  number for a long-only single-market portfolio, and the report says so
  plainly rather than implying more diversification than the numbers show.
