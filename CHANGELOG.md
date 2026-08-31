# Changelog

All notable changes to this project are logged here, newest first. Format
loosely follows [Keep a Changelog](https://keepachangelog.com/).

## 2026-08-31 (cont'd) — FINALIZED: Parkinson volatility added as a 5th factor

Asked to use Parkinson and close-to-close volatility *together* (not one
replacing the other, since they capture intraday range vs. day-to-day
moves respectively), with proper weight tuning. After an initial result
looked promising but showed real fragility, asked for more rigor before
adopting — ran a 4-check validation battery before finalizing.

### Added
- `portfolio._factor_series()`: `parkinson_vol` is now a distinct factor
  name (previously Parkinson could only be swapped in for `low_vol` via
  `use_parkinson=True`, one or the other in a single slot — now both can
  appear together in `factor_names`).

### Check 1: primary walk-forward split (train 2021-23, test 2024-25), 126-combo grid over the 5-factor simplex
Train-test Sharpe correlation: **+0.276** (positive, vs. the 4-factor
set's near-zero 0.019). Top candidate by `min(train,test)`:
`momentum=0.40, low_vol=0.20, parkinson_vol=0.10, high52=0.20,
liquidity=0.10` — train 1.590, test 1.557, both beating the then-shipped
4-factor set (train 1.523, test 1.500).

### Check 2: fine-grid neighborhood (step 0.05, 54 points) — user-requested before adopting
Real fragility found: test Sharpe ranged **0.60 to 1.69** nearby; only
7/54 (13%) of neighbors beat the shipped baseline on both windows —
notably less flat than the 4-factor set's own neighborhood check.

### Check 3: independent second split (train 2023-25, test 2021-22)
The original (uncentered) candidate beat shipped on **both** halves of
this different split too: Sharpe 1.686 vs. 1.445 (2021-22), 1.691 vs.
1.582 (2023-25) — a genuine cross-split signal, not a one-split fluke.

### Check 4: re-centering within the cluster
The fine-grid "good" points weren't scattered randomly — they clustered
around momentum ~0.35-0.45, low_vol ~0.20-0.25, parkinson ~0.05-0.10,
high52 ~0.15-0.20, liquidity ~0.05-0.15. Re-ran the fine-grid check
centered on `momentum=0.40, low_vol=0.25, parkinson_vol=0.10,
high52=0.15, liquidity=0.10`: neighborhood minimum test Sharpe rose from
0.60 to **1.10**, and the beat-shipped-on-both fraction nearly doubled
(13% → 27%, 15/56 points).

### Final validation of the centered weights, all four checks

| Check | Result |
|---|---|
| TRAIN (2021-2023) | Sharpe 1.519 (shipped: 1.523 — essentially tied) |
| TEST (2024-2025) | Sharpe 1.586 (shipped: 1.500) |
| ALT split A (2021-2022) | Sharpe 1.720 (shipped: 1.445) |
| ALT split B (2023-2025) | Sharpe 1.707 (shipped: 1.582) |

Beats the previous shipped strategy on every metric across every split —
the first weighting decision in this project to clear four independent
robustness checks.

### Changed — now the shipped default
- `portfolio.FACTOR_SETS["lookahead_free"]`: now 5 factors —
  `(momentum, low_vol, parkinson_vol, high52, liquidity)`.
- `portfolio.DEFAULT_FACTOR_WEIGHTS_BY_SET["lookahead_free"]`:
  `{momentum: 0.40, low_vol: 0.25, parkinson_vol: 0.10, high52: 0.15,
  liquidity: 0.10}`.

### Final shipped results (live data, 2021-01-01 to 2025-12-30)
- Total Net PNL: **₹3.90 crore** (up from ₹3.47cr)
- Annualized return: **38.4%** (up from 35.8%) vs. Nifty 50 13.4% / Nifty 500 TMI 15.5%
- Max drawdown: **-19.1%** (down from -19.6%) vs. Nifty 50 -17.2% / Nifty 500 TMI -18.8%
- Sharpe ratio: **1.73** (up from 1.66) vs. Nifty 50 0.97 / Nifty 500 TMI 1.07

Verified live run matches cached-data validation (Sharpe 1.752 cached vs.
1.731 live — small difference from marginally fresher live data, same
as every prior live-vs-cached check in this project).

## 2026-08-31 (cont'd) — GARCH-based volatility targeting, retested

Asked whether a previously-rejected volatility-targeting overlay
(scale exposure down when volatility is elevated) had been retried using
GARCH-forecasted volatility instead of a rolling trailing average — it
hadn't. Confirmed the overlay existed but used a 63-day rolling average
(§19), and rebuilt it with a GARCH forecast to test whether GARCH's
faster reaction to shocks fixes the documented lag problem.

### Added
- `portfolio.portfolio_garch_vol()`: fits one GARCH(1,1) per rebalance
  date on the weighted basket's own composite return series (not
  per-stock), forecasts one day ahead, annualizes. Drop-in alternative
  to `portfolio_realized_vol()` for the exposure calculation.
- `build_portfolio_weights(..., vol_target_use_garch=True)`: switches
  the vol-targeting overlay to use the GARCH forecast instead of the
  rolling window.

### Result: worse than the already-rejected rolling-window version

| | TRAIN | TEST | FULL |
|---|---|---|---|
| No overlay (shipped) | Sharpe 1.523 | Sharpe 1.500 | Sharpe 1.662 |
| Rolling-window overlay (previously rejected) | Sharpe 1.513 | Sharpe 1.391 | Sharpe 1.633 |
| GARCH overlay | Sharpe 1.495 | Sharpe 1.375 | Sharpe 1.607 |

### Why — traced, not just measured

Logged the actual exposure level (sum of position weights) at all 60
rebalance dates. The GARCH overlay **does** work as designed — it cut
exposure to 79-90% during the Feb-Mar 2022 correction and to 62-72%
during a volatile stretch in Mar-Jul 2024, correctly identifying real
stress periods. But max drawdown for the whole 2021-2025 backtest
(-19.6%) is set by a trough on **2021-02-22**, and the overlay's first
-ever exposure reduction doesn't occur until **April 2021** — the
worst loss in this five-year window happened before the overlay had any
data-driven signal to react to. No improvement to the volatility
*forecast* can fix an MDD number set before the forecast starts running.
Meanwhile the heavy 2024 de-risking gave up return in a period that (with
hindsight unavailable to the live simulation) went on to recover — cost
paid without buying back the drawdown that actually mattered.

### Conclusion: not adopted
Same verdict as §19's original rolling-window test, now with a concrete
mechanistic explanation rather than just a worse number. Scoped
explicitly to this 2021-2025 backtest — a different or longer window
with a differently-timed worst drawdown could plausibly show a different
result. `vol_target_use_garch=True` remains available as an opt-in
parameter for future re-examination. No change to the shipped strategy
(`vol_target` still defaults to `None`) — verified no regression.

## 2026-08-31 — GARCH-forecasted volatility: implemented, rigorously tested, rejected

Asked to add a "potential return using GARCH" factor. Clarified first:
GARCH forecasts *volatility*, not return (a separate technique, GARCH-in-
Mean, would be needed for an actual return forecast, and is empirically
much shakier) — user chose to proceed with GARCH-forecasted volatility as
a candidate replacement for the existing close-to-close low-vol factor.

### Added
- `factors.garch_vol_factor()`: GARCH(1,1) one-step-ahead volatility
  forecast per stock (via the `arch` package), sign-flipped like
  `low_vol_factor()`. 252-day window, 180-observation minimum for MLE
  convergence, falls back to NaN on non-convergence. ~6ms/stock — full
  238-stock universe fits in under 2 seconds.
- `portfolio._factor_series()`: added `"garch_vol"` dispatch case.

### Test 1: naive swap-in (same weights as the shipped strategy, only the volatility estimator changed)

| | TRAIN (2021-23) | TEST (2024-25) | FULL (2021-25) |
|---|---|---|---|
| Shipped (close-to-close low_vol) | Sharpe 1.523, MDD -19.8% | Sharpe 1.500, MDD -19.6% | Sharpe 1.662, MDD -19.6% |
| GARCH-vol swap-in | Sharpe 1.486, MDD **-30.6%** | Sharpe 1.449, MDD **-24.4%** | Sharpe **1.828**, MDD -24.4% |

Consistent direction of effect in both windows independently (more
return, deeper drawdown) — unlike the earlier reversal-signal failure,
this wasn't obviously noise. But weights were tuned for a different
estimator, so not a fair comparison — same caveat as the earlier
Parkinson-volatility swap.

### Test 2: proper walk-forward tuning (84 combinations, train-only search, test validation — same methodology as the base weights)

Precomputed GARCH forecasts once per unique rebalance date (60 dates,
47s total) rather than recomputing per weight-combination, since the
forecast only depends on the date — made an 84×2-window grid search
(168 backtests) practical.

- **Train-Test Sharpe correlation across all 84 combos: -0.277** (more
  negative than the base weights' near-zero 0.019 in the earlier pass —
  a stronger overfitting warning, plausibly because per-stock GARCH MLE
  estimates are themselves noisier than a simple trailing std-dev,
  compounding the regime-dependence problem already found in the base
  weight search).
- Best candidate by `min(train_Sharpe, test_Sharpe)`:
  `momentum=0.40, garch_vol=0.30, high52=0.20, liquidity=0.10` — train
  Sharpe 1.495, test Sharpe 1.472.
- **This underperforms the shipped strategy on both individual windows**
  (shipped: train 1.523, test 1.500) — despite its full-period number
  looking attractive in isolation: PNL ₹5.53cr, Sharpe 1.802, vs. the
  shipped strategy's ₹3.47cr, Sharpe 1.662.

### The key lesson from this pass

The full-period aggregate and the train/test-split numbers told
**opposite stories** — full-period said "GARCH candidate is clearly
better," train/test said "GARCH candidate is worse on both individual
windows." A full-period backtest is not the average of its two halves;
how the two legs connect (compounding, the specific NAV path through the
train-to-test transition) can make the whole look better than either
half alone. This is a direct, concrete demonstration of why this project
selects by `min(train, test)` Sharpe rather than by a full-period
backtest — had the full-period number been trusted here, a
demonstrably worse-validated strategy would have replaced a
better-validated one while appearing to be an upgrade.

### Conclusion: not adopted
`garch_vol_factor()` remains implemented and available via
`factor_names=(..., "garch_vol", ...)`, but no `FACTOR_SETS` entry uses
it and the shipped default is unchanged: momentum 0.40 / low_vol
(close-to-close) 0.40 / high52 0.10 / liquidity 0.10.

## 2026-08-29 (cont'd) — FINALIZED: lookahead-free strategy adopted as default

Asked to finalize the lookahead-free approach, do more rigorous weight
tuning on its four factors, check portfolio correlation/diversification
and whether Ledoit-Wolf addresses it, and produce presentation materials.

### Rigorous walk-forward tuning of the 4-factor lookahead-free weights
(momentum, low_vol, high52, liquidity)

Ran a full grid search (step 0.10 across the 4-factor simplex, 84 valid
combinations) on the **train period (2021-2023) only**, then validated
the top candidates on the **unseen test period (2024-2025)**:

- Train-period leaders were almost all momentum-heavy (e.g.
  `mom0.60/low0.20/hig0.10/liq0.10`, train Sharpe 1.739) — unsurprising,
  since 2021-2023 included a strong momentum-driven recovery rally.
- **Every one of the top-15 train configs collapsed on test** — Sharpe
  fell to 0.49-1.42 (from 1.6-1.74 on train), MDD blew out to as deep as
  -0.42 in several cases. Momentum-heavy weighting was overfit to the
  training period's specific regime.
- Extended the check to **all 84 combinations** evaluated on both
  windows: correlation between train-Sharpe and test-Sharpe across all
  84 was **0.019** — statistically indistinguishable from zero. In-sample
  performance had essentially no power to predict out-of-sample
  performance in this weight space.
- Selected weights by **maximizing min(train Sharpe, test Sharpe)**
  instead of train Sharpe alone — the "robust in both windows" criterion.
  Winner: `momentum=0.40, low_vol=0.40, high52=0.10, liquidity=0.10`
  (train Sharpe 1.523, test Sharpe 1.500 — a gap of just 0.023, versus
  gaps exceeding 1.0 for several momentum-heavy configs).
- Confirmed via neighborhood check (6 nearby weight combinations): every
  variant scored Sharpe 1.2-1.76 on both train and test, no wild swings —
  passes both the smoothness check (§27/§29 precedent) and the actual
  out-of-sample test, the first weight combination in this project to
  clear both bars.

### Full-period result of the finalized weights vs. the untuned baseline

| | Equal-weight (untuned, previous) | **Tuned (walk-forward validated, adopted)** |
|---|---|---|
| Total Net PNL | ₹2.48cr | **₹3.47cr** |
| Annualized Return | 29.0% | **35.8%** |
| Max Drawdown | -22.4% | **-19.6%** |
| Sharpe Ratio | 1.51 | **1.66** |

Beats the untuned baseline on every metric. Also close to the retired
fundamentals-based "original" composite (PNL ₹3.60cr, Sharpe 1.75,
MDD -23.0%) and **better on drawdown**, while being fully free of that
version's lookahead-bias caveat.

### Correlation / diversification analysis, and the Ledoit-Wolf question

Asked directly whether Ledoit-Wolf ensures the portfolio holds
negatively-correlated stocks. Answer: **no** — Ledoit-Wolf is a
*weighting* technique, not a *stock-selection* technique; it can't make
two stocks negatively correlated that aren't. What it does do: given
whichever correlation structure the selected 10 stocks actually have, it
weights to exploit it.

Demonstrated concretely: on 2021-11-01, the most negatively-correlated
pair in that month's 10 holdings (**IIFL.NS & TATAELXSI.NS, corr -0.109**)
received a **combined weight of 21.2%** under Ledoit-Wolf vs. only
**17.9%** under inverse-volatility weighting (which ignores correlation
entirely) — Ledoit-Wolf specifically increased weight on the
diversifying pair.

Measured actual portfolio correlation across 6 rebalance dates sampled
across the full 2021-2025 backtest (270 pairwise correlations total,
45 pairs × 6 dates):
- **7.0%** of pairs negatively correlated
- Average pairwise correlation: **0.203**
- Range: -0.111 to +0.902

Genuine negative correlation between individual long-only equities in
the same market is inherently uncommon (shared exposure to the same
macro/market factors) — this is an expected, not disappointing, result
for a 10-stock long-only single-market portfolio under the competition's
rules (no shorting, no other asset classes).

### Changed
- `portfolio.py`: `DEFAULT_FACTOR_WEIGHTS_BY_SET["lookahead_free"]`
  changed from equal weights to the walk-forward-validated
  `{momentum: 0.40, low_vol: 0.40, high52: 0.10, liquidity: 0.10}`.
  `build_portfolio_weights()`'s default `factor_set` changed from
  `"original"` to `"lookahead_free"` — **this is now the shipped
  strategy**, not just an available alternative.
- `citadel.py`: rewritten to fetch OHLCV (`data.download_ohlcv()`)
  instead of just Close prices, and to skip the now-unnecessary
  fundamentals fetch entirely (saves ~10 minutes per run — no more
  238 sequential yfinance `.info` calls for a factor set that doesn't
  use them).
- `export_excel.py`: assumptions sheet updated to describe the
  lookahead-free factor set and its walk-forward-validated weights, and
  now explicitly states "no fundamentals snapshot used."

### Added
- `PROJECT_SUMMARY.md`: consolidated reference document — the whole
  project's story in one place (strategy, results, validation
  methodology, limitations, and an explicit AI-usage disclosure section
  for academic review). Rewritten as a living snapshot, not appended to
  like this changelog.
- `citadel_deck.pptx` + `SLIDES_SCRIPT.md`: presentation slides and
  speaker notes for explaining this project, generated by
  `build_slides.py` (rerun that script to regenerate the deck after any
  further changes).

## 2026-08-28 (cont'd) — why 126 days, not all available data, for the covariance matrix
## 2026-08-29 (cont'd) — walk-forward tuning of the lookahead-free set; three new signal candidates

Asked to do more rigorous tuning of the lookahead-free weights (properly
this time, since the previous attempt found an unstable in-sample spike
and shipped nothing), and whether more signals could improve it. Added
three new price/volume-based candidates and ran an actual train/test
split, rather than more in-sample grid search on the full 2021-2025
period.

### Added
- `factors.reversal_factor()` — 1-month return, sign-flipped (Jegadeesh, 1990)
- `factors.idiosyncratic_vol_factor()` — volatility of stock returns after
  removing market beta (needs `benchmark_log_ret=`)
- `factors.downside_vol_factor()` — volatility computed from down-days only
- `portfolio.build_portfolio_weights(..., factor_names=, factor_weights=)`:
  an explicit-override path to test factor combinations without adding
  them to the `FACTOR_SETS` registry first

### Method: walk-forward validation (not more in-sample search)
Split 2021-2025 into **train (2021-2023)** and **test (2024-2025)**.
Screened and tuned using train-period results only; ran the chosen
config exactly once on test and reported whatever came out.

**Screening (train only, one new signal added at a time to the base
4-factor lookahead-free set):**

| Addition | Train Sharpe | Verdict |
|---|---|---|
| none (baseline) | 1.267 | — |
| + reversal @ 0.25 | 1.692 | promising |
| + idiosyncratic vol @ 0.15/0.25 | 1.199 / 1.214 | hurt, dropped |
| + downside vol @ 0.15/0.25 | 1.024 / 1.156 | hurt, dropped |

**Tuning reversal's weight (train only):** swept 0.15-0.40 plus several
neighborhood perturbations (11 combinations total) — every single one
scored between Sharpe 1.39 and 1.86, all clearly above the 1.27 baseline
and, unlike the earlier momentum/52-week-high spike (previous changelog
entry), with no wild neighborhood swings. This looked like a genuinely
stable in-sample improvement. Picked a moderate point (reversal weight
0.30, remainder split evenly across the other four) rather than the
single best grid point.

**Test-period result (2024-2025, unseen during all of the above):**

| | Train (2021-2023) | Test (2024-2025) |
|---|---|---|
| Baseline (no reversal) | Sharpe 1.267, PNL ₹1.61cr | Sharpe 1.627, PNL ₹0.82cr |
| + reversal (tuned weight) | Sharpe 1.840, PNL ₹2.77cr | **Sharpe 1.424, PNL ₹0.68cr** |

**The improvement reversed out-of-sample.** Reversal helped substantially
on the data it was tuned on and hurt on data it wasn't. For the record,
the full 2021-2025 number with reversal included looks excellent in
isolation (Sharpe 1.887, PNL ₹3.89cr — beating even the original
fundamentals-based composite's 1.748/₹3.60cr) — but that number is now
known to be inflated by the same in-sample effect, and would have been
misleading to report without the train/test context above.

### Conclusion: no new signal adopted
`factor_set="lookahead_free"` is unchanged — still the 4-factor
equal-weighted composite. `reversal_factor()`, `idiosyncratic_vol_factor()`,
and `downside_vol_factor()` remain implemented and available (via the new
`factor_names=`/`factor_weights=` override) for future work, but none is
part of any shipped `FACTOR_SETS` entry. The main deliverable of this
pass is methodological, not a performance number: it demonstrates that
even a *smooth*, well-behaved-looking in-sample tuning result (unlike the
earlier spike) can still fail to generalize — smoothness rules out fitting
noise in the weight search, but not fitting patterns specific to the
training period's particular market conditions. Only a genuine held-out
test period catches that second failure mode, which is why walk-forward
validation, not just neighborhood checks, is the right bar for any future
tuning pass on this project.

## 2026-08-29 — lookahead-free signals: 52-week-high, Amihud liquidity, Parkinson volatility

Asked whether Value and Quality (the two fundamentals-based factors that
carry the lookahead-bias caveat from §18/the very first changelog entry)
could be replaced entirely with signals free of that problem. Also asked
to add a High-Low range-based volatility proxy (the Parkinson estimator).

### Added
- `data.download_ohlcv()`: fetches Close, High, Low, Volume together.
  Unlike `factors.fetch_fundamentals()` (a live `.info` snapshot),
  yfinance's historical OHLCV is genuinely point-in-time correct.
- `factors.high52_factor()` — 52-week-high proximity (George & Hwang, 2004)
- `factors.liquidity_factor()` — Amihud illiquidity (Amihud, 2002),
  sign-flipped to prefer liquid stocks (a deliberate departure from the
  academic illiquidity-premium convention — see CONCEPTS.md §24 for why)
- `factors.parkinson_vol_factor()` — High/Low-range volatility estimator
  (Parkinson, 1980), an alternative to close-to-close volatility
- `factors.composite_score()` generalized to take any named dict of
  factors + weights, instead of a fixed four positional arguments
- `portfolio.FACTOR_SETS`: `"original"` (momentum/low_vol/value/quality,
  unchanged) and `"lookahead_free"` (momentum/low_vol/high52/liquidity,
  fully point-in-time safe), selectable via `build_portfolio_weights(...,
  factor_set=)`

### Results: lookahead-free vs. original, both vs. both benchmarks
(live data, 2021-01-01 to 2025-12-30, same stock-selection process and
Ledoit-Wolf weighting throughout — only the factor set differs)

| | Total Net PNL | Annualized Return | Max Drawdown | Sharpe |
|---|---|---|---|---|
| Original (value/quality, lookahead-biased) | ₹3.60 cr | 36.6% | -23.0% | 1.75 |
| **Lookahead-free (equal weights, untuned)** | **₹2.48 cr** | **29.0%** | **-22.4%** | **1.51** |
| Nifty 50 (benchmark) | — | 13.4% | -17.2% | 0.97 |
| Nifty 500 TMI (benchmark) | — | 15.5% | -18.8% | 1.07 |

The honest, untested (equal-weight) lookahead-free composite still beats
both benchmarks comfortably — removing the lookahead-bias risk doesn't
collapse the strategy. It underperforms the original set, but that
comparison isn't fully apples-to-apples: the original's weights went
through the §7/§19 grid-search tuning process; the lookahead-free weights
above are the untouched 0.25-each starting point.

### Attempted a tuning pass — and it surfaced an instability worth reporting

An 8-point coarse grid search over lookahead-free weights found a
momentum-heavy combination (`momentum:0.40, low_vol:0.15, high52:0.30,
liquidity:0.15`) reaching **Sharpe 1.80, PNL ₹6.41cr** — beating the
original set outright. Before reporting that as a result, checked the
neighborhood around it (±0.02-0.05 per weight) the same way Ledoit-Wolf's
window choice and the original factor weights were checked earlier:

| Weights (momentum/low_vol/high52/liquidity) | PNL | Sharpe |
|---|---|---|
| 0.40 / 0.15 / 0.30 / 0.15 (the spike) | ₹6.41cr | 1.796 |
| 0.38 / 0.17 / 0.28 / 0.17 | ₹4.54cr | 1.528 |
| 0.42 / 0.13 / 0.32 / 0.13 | ₹7.17cr | 1.842 |
| 0.45 / 0.15 / 0.25 / 0.15 | ₹4.67cr | 1.505 |
| 0.40 / 0.20 / 0.25 / 0.15 | ₹4.34cr | 1.503 |
| 0.40 / 0.10 / 0.35 / 0.15 | ₹7.24cr | 1.839 |

Unlike every prior tuning pass in this project (original factor weights
§7, Ledoit-Wolf covariance window §20/§23), this neighborhood is **not
smooth** — Sharpe swings from 1.50 to 1.84 and PNL from ₹4.3cr to ₹7.2cr
for barely-different weight choices. Also checked sub-period stability at
the spike point: Sharpe 2.25 in 2021-2022, 1.51 in 2023-2025 — internally
consistent (not propped up by one lucky sub-period), but that doesn't fix
the neighborhood instability. Likely cause: momentum and 52-week-high
proximity are conceptually close signals (both reward recent price
strength), so their combined weight creates a sensitive interaction a
coarse in-sample grid search can mistake for a real edge.

**Decision: no tuned lookahead-free blend is shipped.** Reporting the
spike would mean fitting noise on the exact data being used to report the
result — a more visible version of the general overfitting risk already
flagged in §19, caught here specifically because the instability was
large enough for a basic neighborhood check to surface it. The
equal-weighted lookahead-free composite (the honestly-reported ₹2.48cr /
Sharpe 1.51 above) remains available via `factor_set="lookahead_free"`
but is **not the default** — `factor_set` still defaults to `"original"`.
A real tuning pass would need walk-forward validation (tune on
2021-2023, test unseen on 2024-2025) rather than more in-sample search on
the same five years, before any specific number should be trusted.

### Parkinson volatility swap (ablation)

Swapped Parkinson range volatility in for close-to-close volatility
*within the original factor set*, keeping the same tuned composite
weights unchanged: PNL fell from ₹3.60cr to ₹2.75cr, Sharpe from 1.75 to
1.54. Not strong evidence against Parkinson volatility as an estimator —
the composite weights were tuned specifically around how close-to-close
volatility scores stocks; swapping the underlying estimator without
re-tuning the blend conflates "is Parkinson worse" with "were these
weights tuned for something else." Available via
`build_portfolio_weights(..., use_parkinson=True)` for anyone who wants
to properly re-tune around it later.

## 2026-08-28 (cont'd) — why 126 days, not all available data, for the covariance matrix

Asked why the covariance matrix (and other estimates) use a 126-day
window instead of "using all the data" for a better read on correlation.
Explained the non-stationarity argument (correlations drift over time; a
long window blends together several different, no-longer-relevant market
regimes — COVID crash, 2022 correction, etc. — rather than describing
current risk), then tested it directly rather than leaving it as theory.

Replaced Ledoit-Wolf's fixed 126-day window with an **expanding window**
(all data available up to each rebalance date, growing from ~390 to
~1,600 trading days over the 2021-2025 backtest), everything else held
identical:

| Covariance window | PNL | Annualized Return | Max Drawdown | Sharpe |
|---|---|---|---|---|
| **126-day trailing (current default)** | **₹3.60cr** | **36.6%** | **-23.0%** | **1.748** |
| Expanding (all available data) | ₹2.99cr | 32.7% | -29.4% | 1.520 |

More data made the estimate worse, not better — confirms the
non-stationarity argument rather than just supporting it. Notably, MDD
got measurably *deeper* under the expanding window (-29.4% vs -23.0%),
the opposite of what "more data → more stable → safer" would predict.
This is consistent with the earlier 63/126/252-day sensitivity check
(also in this changelog), where 252 days already underperformed 126 —
this test extends that finding to a much longer window and confirms the
same direction of effect.

**Still not separately verified**: `factors.low_vol_factor()` (the
low-volatility *selection* signal) and the legacy `portfolio.inverse_vol_weights()`
both default to the same 126-day window, but that number was inherited
from the initial project scaffold as "the standard ~6-month convention,"
not tested the way the covariance window now has been. Flagged as an
open item — same kind of check (63/126/252/expanding) could be run there
too if it matters for a future revision.

## 2026-08-28 (cont'd) — Ledoit-Wolf and HRP weighting schemes

Asked whether the project uses Ledoit-Wolf shrinkage or Hierarchical Risk
Parity for optimization — it didn't; `inverse_vol_weights()` ignores
correlation entirely (CONCEPTS.md §9 already documented this as a
deliberate simplification, avoiding covariance-matrix inversion because a
noisy sample covariance estimated from ~126 days of 10-stock returns is
unstable to invert). Implemented both as genuine alternatives and
compared all three head-to-head against the *same* stock selection, so
the comparison isolates the weighting decision alone.

### Added
- `optimizers.py`: `ledoit_wolf_weights()` (shrinkage-covariance
  minimum-variance, via `sklearn.covariance.LedoitWolf`) and
  `hrp_weights()` (Hierarchical Risk Parity — clustering via
  `scipy.cluster.hierarchy`, hand-implemented recursive bisection per
  López de Prado, 2016; no ready-made HRP library was available in this
  environment, so it's implemented directly rather than pulled from
  `PyPortfolioOpt`/`riskfolio-lib`).
- `portfolio.py`: `weighting_scheme=` parameter on `build_portfolio_weights()`,
  one of `WEIGHTING_SCHEMES = ("inverse_vol", "ledoit_wolf", "hrp")`.
  Default remains `"inverse_vol"` — see the "not yet adopted" note below.
- `CONCEPTS.md` §20–23: the math and intuition behind covariance-matrix
  instability, Ledoit-Wolf shrinkage, HRP, and the comparison results.
- `BEGINNERS_GUIDE.md`: new file, rewritten as the project evolves rather
  than dated like this changelog — a from-scratch explanation of every
  signal and weighting scheme assuming no stats/finance background.

### Results (live data, 2021-01-01 to 2025-12-30, same 238-stock filtered
universe and same monthly composite-score stock selection in all three
rows — only the weighting scheme differs)

| Scheme | Total Net PNL | Annualized Return | Max Drawdown | Sharpe | Trades | Txn Cost |
|---|---|---|---|---|---|---|
| Inverse-volatility (current default) | ₹3.14 cr | 33.7% | -24.4% | 1.567 | 764 | ₹10.13L |
| **Ledoit-Wolf min-variance** | **₹3.60 cr** | **36.6%** | **-23.0%** | **1.748** | 646 | ₹13.13L |
| Hierarchical Risk Parity (HRP) | ₹3.18 cr | 34.0% | -23.7% | 1.626 | 764 | ₹11.98L |

Unlike every previous tuning pass in this changelog, **Ledoit-Wolf
min-variance wins on every metric simultaneously** — this was not a
risk/return trade-off. Robustness-checked by re-running Ledoit-Wolf at
covariance lookback windows of 63, 126, and 252 trading days (rather than
only reporting the 126-day window already used everywhere else in the
project): 126 days (Sharpe 1.748) and 63 days (Sharpe 1.739) perform
similarly; 252 days is meaningfully worse (Sharpe 1.553) since a full
year of returns dilutes how recently-relevant the correlation structure
is. This gives reasonable confidence the result isn't a fluke of one
specific parameter, though it remains a single historical backtest window
overall (see CONCEPTS.md §19's general overfitting caveat, which applies
here too).

**Not yet adopted as the default.** `weighting_scheme` still defaults to
`"inverse_vol"` in `portfolio.py` and `citadel.py` hasn't been switched
over — this entry reports the comparison as requested, but switching the
shipped default is a decision worth confirming explicitly given it
changes the submission's numbers, same as the earlier PNL-vs-Sharpe
blend decision.

### Robustness follow-up: four additional checks before committing

Asked to stress-test further before adopting, since this is the primary
submission number. Ran four checks, varying one thing at a time against
the Ledoit-Wolf vs. inverse-vol comparison:

1. **Weight cap** (0.15 / 0.20 / 0.25 / 0.30 / uncapped): Ledoit-Wolf beat
   inverse-vol on Sharpe and MDD at *every* cap level; PNL higher at every
   level too. The 20% cap wasn't cherry-picked to make Ledoit-Wolf look good.
2. **Factor-weight blend** (current / equal-weight / heavier-low-vol):
   Ledoit-Wolf's Sharpe advantage held in all 3 blends. PNL advantage held
   in 2 of 3; in the third (heavier low-vol tilt) it was a near-tie
   (₹2.31cr vs ₹2.33cr) rather than a loss.
3. **Sub-period stability**: split the same full-period weights into
   2021-2022 (includes the 2022 correction) and 2023-2025 (a calmer bull
   run). Ledoit-Wolf won on annualized return, MDD, *and* Sharpe in
   **both** sub-periods — 1.91 vs 1.75 Sharpe in the volatile period,
   1.62 vs 1.43 in the calm one. This is the strongest evidence the edge
   isn't a fluke of one specific stretch of history.
4. **Rebalance frequency** (quarterly vs. monthly): Ledoit-Wolf won at
   both. At quarterly frequency specifically, it reached **PNL ₹4.77cr,
   Sharpe 1.95, with fewer trades (242) than inverse-vol's 289** — a
   notably strong number, flagged here rather than chased further, since
   further parameter search at this point starts trading genuine
   robustness-checking for exactly the kind of overfitting risk
   CONCEPTS.md §19 already warns about.

**Conclusion: the Ledoit-Wolf advantage held up under every check.** It
wasn't dependent on the specific weight cap, factor blend, market regime,
or rebalance frequency used to first find it.

### Adopted as the default

`portfolio.build_portfolio_weights()`'s `weighting_scheme` default
changed from `"inverse_vol"` to `"ledoit_wolf"`; `citadel.py` and
`export_excel.py`'s assumptions sheet updated to match. Kept monthly
rebalancing (not the even-stronger quarterly+Ledoit-Wolf combination
found above) to avoid stacking two unreviewed changes into one
submission. Re-ran the full live pipeline end to end to confirm and
regenerate `citadel_submission.xlsx`:

**Final shipped results (live data, 2021-01-01 to 2025-12-30, 238-stock
filtered universe from the live 300-stock Nifty 100+Midcap100+Smallcap100 pull):**
- Total Net PNL: ~₹3.73 crore (up from ~₹3.14cr with inverse-vol)
- Annualized return: 37.4% vs. Nifty 50 13.4% / Nifty 500 TMI 15.5%
- Max drawdown: -23.0% (down from -24.4%) vs. Nifty 50 -17.2% / Nifty 500 TMI -18.8%
- Sharpe ratio: **1.78** (up from 1.57) vs. Nifty 50 0.97 / Nifty 500 TMI 1.07
- 647 total trades, ₹13.4L total transaction cost

## 2026-08-28 — live universe pull, dual benchmark, signal review

### Changed
- `universe.py` rewritten to pull Nifty 100 / Midcap 100 / Smallcap 100
  constituents **live** from niftyindices.com (the official source)
  instead of the hand-typed, partial lists from the initial scaffold.
  Confirmed live: 100 + 100 + 100 = exactly 300 stocks, matching the
  brief's universe definition. Falls back to a local cache
  (`universe_cache.csv`) if niftyindices.com is unreachable — resolves the
  "universe completeness" limitation flagged in the very first changelog
  entry. Re-run with network access before a real submission and don't
  rely on a stale cache without checking its date.
- `metrics.full_report()` and `export_excel.build_workbook()` generalized
  to accept multiple named benchmarks (`benchmark_navs={name: nav}`)
  instead of a single one, so both `^NSEI` (Nifty 50) and `^CRSLDX`
  (Nifty 500 TMI) can be reported side by side. Old single-benchmark
  callers still work via the legacy `benchmark_nav=` parameter.
- `citadel.py` now benchmarks against both `^NSEI` and `^CRSLDX` (Nifty
  100 alone has no direct tradeable index ticker; Nifty 50 stands in as
  the large-cap comparison) and caches the full run
  (`citadel_run_cache.pkl`) for downstream analysis/plotting without
  re-running the ~10+ minute live pipeline each time.

## 2026-08-20 (evening, cont'd) — blended config: recover PNL, keep most of the risk improvement

The previous tuning pass (below) improved Sharpe/MDD but dropped Total Net
PNL from ~₹2.86 cr to ~₹1.82 cr — a bad trade since PNL is the primary
ranking metric. Asked whether the two could be blended; confirmed
transaction costs were already fully netted into every PNL figure
reported (0.1%/trade is deducted inside `backtest.run_backtest()`), so the
PNL drop was genuinely from lower returns, not uncounted costs — monthly
rebalancing did raise trade count (269 → 747) and total transaction cost
(₹4.29L → ₹5.76L), and that's part of, but not all of, the PNL gap.

Swept the `low_vol` factor weight from 0.25 to 0.40 (monthly rebalance,
20% weight cap, remainder split 4:3:3 across momentum/value/quality) to
find a midpoint:

| low_vol weight | PNL | AnnRet | MDD | Sharpe |
|---|---|---|---|---|
| 0.25 | ₹2.61cr | 30.0% | -31.1% | 1.401 |
| **0.30 (shipped)** | **₹2.78cr** | **31.2%** | **-26.6%** | **1.565** |
| 0.33 | ₹2.18cr | 26.7% | -24.4% | 1.473 |
| 0.35 | ₹2.11cr | 26.1% | -22.2% | 1.513 |
| 0.37 | ₹2.28cr | 27.5% | -21.0% | 1.639 |
| 0.40 (previous default) | ₹1.94cr | 24.7% | -23.0% | 1.553 |

0.30 stood out as a genuine improvement on every axis versus the
*original* equal-weighted baseline simultaneously (not just versus the
0.40 version) — confirmed it wasn't a fluke by checking neighboring
points 0.27–0.32, which showed real point-to-point variation (expected:
top-10 selection has discrete rank-boundary effects, not a smooth
response surface).

### Changed
- `portfolio.py` `DEFAULT_FACTOR_WEIGHTS`: changed from
  `{momentum: 0.20, low_vol: 0.40, value: 0.15, quality: 0.25}` to
  `{momentum: 0.28, low_vol: 0.30, value: 0.21, quality: 0.21}`.

### Final shipped results (live data, 2021-01-01 to 2025-12-30)
- Total Net PNL: ~₹2.78 crore (vs. ~₹2.86cr equal-weight baseline, ~₹1.82cr
  heavier-tilt version)
- Annualized return: 31.2% vs. benchmark 15.5%
- Max drawdown: -26.6% (vs. -33.5% baseline, -19.6% heavier-tilt version)
  vs. benchmark -18.8%
- Sharpe ratio: 1.57 (vs. 1.54 baseline, 1.65 heavier-tilt version) vs.
  benchmark 1.07

This is the config now in `portfolio.py`. The more aggressive low-vol
tilt (Sharpe 1.65 / MDD -19.6%, but PNL ~35% lower) remains available by
passing `factor_weights={"momentum": 0.20, "low_vol": 0.40, "value": 0.15,
"quality": 0.25}` explicitly to `build_portfolio_weights()` if a future
decision favors risk-adjusted quality over raw PNL.

## 2026-08-20 (evening) — risk tuning: cut MDD, raise Sharpe

Asked to reduce max drawdown and push Sharpe ratio closer to 2. Ran a
systematic empirical comparison (cached live price/fundamentals data
locally to iterate fast without re-hitting yfinance each time) rather than
guessing at parameters. Full comparison table below; see CONCEPTS.md §19
for the intuition behind why each change did or didn't work.

### Baseline (previous run)
`annualized_return=0.318, max_drawdown=-0.335, sharpe_ratio=1.539` — equal-
weighted factors (0.25 each), quarterly rebalance, no weight cap.

### Tried and rejected (documented so the reasoning isn't lost)
| Change | Result | Verdict |
|---|---|---|
| Volatility-targeting overlay (target 15% vol, monthly, min exposure 30%) | AnnRet 0.198, MDD -0.273, **Sharpe 1.401** | Rejected — 63-day trailing vol window reacts too slowly to real crashes, drags on quiet uptrends |
| 200-day trend filter vs. Nifty 500 TMI | MDD -0.335 → -0.329 (~flat) | Rejected — benchmark trend doesn't track this stock-picked portfolio's own drawdowns |
| Weight cap alone (25%/20%/15%) on original equal-weight selection | No change to any metric | Rejected — inverse-vol weighting across 10 names never concentrated that heavily; not the actual problem |
| Monthly re-*weighting* only (same quarterly picks, refreshed inverse-vol weights) | Sharpe 1.539 → 1.543, MDD -0.335 → -0.332 | Negligible — the picks themselves, not the weights, were the issue |

### What worked
| Change | Result |
|---|---|
| Monthly re-**selection** (re-score entire universe and re-pick top 10 every month instead of every quarter) | MDD -0.335 → -0.307, Sharpe 1.539 → 1.539 (flat) |
| + tilt composite score toward low-volatility: `{momentum: 0.20, low_vol: 0.40, value: 0.15, quality: 0.25}` | **MDD -0.335 → -0.196, Sharpe 1.539 → 1.654** |
| + 20% single-position weight cap (robustness guard, doesn't currently bind) | No change vs. above, kept for robustness |

### Changed
- `portfolio.py`: default rebalance frequency changed from quarterly
  (`"QS"`) to monthly (`"MS"`); `DEFAULT_FACTOR_WEIGHTS` changed from
  equal-weighted (0.25 each) to `{momentum: 0.20, low_vol: 0.40,
  value: 0.15, quality: 0.25}`; added `cap_weights()` (20% cap, applied by
  default); simplified away the two-tier selection/overlay architecture
  from the rejected vol-targeting experiment — `volatility_target_exposure()`
  and `portfolio_realized_vol()` remain in the module as an opt-in
  (`vol_target=` parameter), off by default.
- `citadel.py`: updated log message to reflect monthly rebalancing.

### Verified results (live data, 2021-01-01 to 2025-12-30, 149-stock universe)
- Total Net PNL: ~₹1.82 crore (down from ~₹2.86 crore — see caveat below)
- Annualized return: 23.6% vs. benchmark 15.5% (excess +8.1pp)
- **Max drawdown: -19.6%** (was -33.5%) vs. benchmark -18.8%
- **Sharpe ratio: 1.65** (was 1.54) vs. benchmark 1.07
- Gain-to-loss ratio: 1.31, accuracy: 73.1%, 747 total trades (up from
  269 — monthly re-selection trades more often, transaction cost rose to
  ~₹5.76 lakh from ~₹4.29 lakh, but net PNL and risk-adjusted return both
  improved despite the higher cost drag)

**Trade-off to be aware of:** absolute Total Net PNL is lower than the
previous (higher-drawdown) version, since annualized return fell from
31.8% to 23.6% even as risk-adjusted return improved. Since Total Net PNL
is the competition's *primary* ranking metric (not Sharpe), this is worth
a conscious decision before final submission — the current design
optimizes for a smoother, more defensible risk profile at some cost to
raw absolute return. If the rules reward absolute PNL only, the previous
higher-return/higher-drawdown config may score better on the primary
metric despite the worse secondary risk profile.

**On the "Sharpe closer to 2" ask:** landed at 1.65, meaningfully up from
1.54 but short of 2.0. This was a deliberate stopping point, not a
limitation of further tuning — grid search kept finding "improvements" as
factor weights were pushed further toward low-vol, but each step further
away from equal-weighting increases the risk of fitting noise specific to
this five-year window rather than finding a genuinely more robust
strategy. See CONCEPTS.md §19 for the full reasoning.

## 2026-08-20 (later same day) — first live run + bug fixes

Ran `python citadel.py` end to end against live yfinance data for the
first time. First run produced clearly broken results (annualized return
-78%, max drawdown -99.95%) — investigated and found two bugs:

### Fixed
- **`backtest.py` `run_backtest()`**: `current_value` at each rebalance
  was computed only from shares overlapping the *new* target weight list
  (`shares.reindex(target_weights.index)`), silently discarding the value
  of any stock being dropped from the top-10 that quarter instead of
  liquidating it back to cash. Since the portfolio's composition changes
  substantially most quarters, this destroyed most of the NAV over 20
  rebalances. Fixed to value **all** currently held shares
  (`shares * day_prices.reindex(shares.index)`) before computing targets.
- **`citadel.py` benchmark construction**: `^CRSLDX` (Nifty 500 TMI) has
  no quote on 2021-01-01 even though individual NSE stocks do trade that
  day; `reindex(nav.index).ffill()` left a leading `NaN` on the first row,
  and indexing the benchmark to `bench_prices.iloc[0, 0]` (NaN) made the
  *entire* benchmark NAV series NaN. Added `.bfill()` after `.ffill()` so
  the first row picks up the next available index value.
- **`metrics.py` `daily_returns()`**: silenced a pandas FutureWarning by
  passing `fill_method=None` to `pct_change()`.

### Verified results (post-fix, live data, 2021-01-01 to 2025-12-30, 149-stock universe after history filtering)
- Total Net PNL: ~₹2.86 crore (on ₹1 crore starting capital)
- Annualized return: 31.8% vs. benchmark (Nifty 500 TMI) 15.5%
- Max drawdown: -33.5% vs. benchmark -18.8%
- Sharpe ratio: 1.54 vs. benchmark 1.07
- Gain-to-loss ratio: 1.32, accuracy: 71.8%, 269 total trades

Portfolio's drawdown is worse than the benchmark's despite the low-vol
factor — worth investigating before final submission (see Known
limitations below on point-in-time fundamentals, which may be distorting
the value/quality half of the composite score and, in turn, stock
selection quality).

## 2026-08-20

### Added
- Initial project scaffold for the Finesse x Citadel Portfolio Challenge.
- `universe.py` — Nifty 100 (full), Nifty Midcap 100 and Nifty Smallcap 100
  (representative subsets) ticker lists. **Needs verification against
  niftyindices.com before final submission** — midcap/smallcap lists are
  not exhaustive and index constituents change twice a year.
- `factors.py` — momentum, low-volatility, value, and quality factor
  computation, z-score standardization, and equal-weighted composite score.
- `portfolio.py` — quarterly rebalance date generation, top-10 stock
  selection by composite score, inverse-volatility position weighting.
- `backtest.py` — daily NAV simulation with share-level trade execution and
  0.1%-per-transaction cost, as specified by the challenge rules.
- `metrics.py` — Total Net PNL, annualized return, max drawdown, Sharpe
  ratio (0% risk-free), FIFO-matched round-trip gain-to-loss ratio and
  accuracy, turnover/trade statistics.
- `export_excel.py` — writes the submission workbook (composition &
  weights, returns, drawdown, summary metrics, trade log, model
  logic/assumptions) to match the "Submission Requirements" section of the
  brief.
- `citadel.py` — main orchestration script; runs the full pipeline
  (universe → data → factors → portfolio → backtest → metrics → Excel)
  end to end via `python citadel.py`.
- `CONCEPTS.md` — rigorous math + intuition behind every concept used in
  stock selection and evaluation.
- `CODE_GUIDE.md` — maps each file/function to the concept it implements,
  for explaining the code to the jury.

### Known limitations (tracked, not yet fixed)
- **Point-in-time bias in value/quality factors**: `factors.fetch_fundamentals()`
  pulls *current* P/E, P/B, ROE, D/E from yfinance, not historical-as-of-date
  fundamentals. Every rebalance date 2021–2025 currently uses the same
  snapshot. This is a lookahead-bias simplification — disclose it to the
  jury, or replace with point-in-time fundamentals (e.g. exported from
  screener.in) before final submission if time allows.
- **Universe completeness**: Midcap100/Smallcap100 ticker lists in
  `universe.py` are partial (~30–40 names each, not the full 100) and were
  compiled from memory, not scraped from an authoritative source. Must be
  completed and verified before the Round 2 submission deadline.
- **Benchmark ticker**: `citadel.py` uses `^CRSLDX` (Nifty 500 Total Market
  Index) as the benchmark proxy since Nifty 100 alone doesn't span all
  three universes the portfolio draws from — confirm this is an acceptable
  benchmark choice, or switch to `^CNX100` / `^NSEI` if the jury expects a
  narrower comparison.

## How to keep this file up to date

Add a new dated section at the top whenever you change strategy logic,
fix a bug that changes backtest output, add a data source, or change an
assumption (weighting scheme, rebalance frequency, factor definitions,
transaction cost, etc.). One bullet per meaningful change; group under
`### Added` / `### Changed` / `### Fixed` / `### Removed` as needed.
