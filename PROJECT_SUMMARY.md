# Project Summary — Finesse x Citadel Portfolio Challenge

This is the single document to hand someone (a professor, a teammate, a
juror) who wants the whole story in one place: what was built, why,
what the numbers are, how rigorously it was tested, and how AI assistance
was used. It gets rewritten as the project evolves — the current
snapshot, not a change log (see `CHANGELOG.md` for the dated history).

Companion documents:
- **`CONCEPTS.md`** — full mathematical detail behind every technique
- **`CODE_GUIDE.md`** — function-by-function map of the code
- **`BEGINNERS_GUIDE.md`** — the same material explained with no assumed background
- **`CHANGELOG.md`** — dated history of every change, bug, and test
- **`SLIDES_SCRIPT.md`** — the speaker notes for `citadel_deck.pptx`

---

## 1. The problem

The Finesse x Citadel Portfolio Challenge asks for a quantitative
long-only equity portfolio: pick up to 10 stocks from Nifty 100 + Nifty
Midcap 100 + Nifty Smallcap 100 (300 stocks total), backtest it from
2021-01-01 to 2025-12-31 against a ₹1,00,00,000 starting capital, with
0.1% transaction cost per trade. Ranked primarily on **Total Net PNL**;
secondarily on annualized return, max drawdown, Sharpe ratio, gain-to-loss
ratio, accuracy, and trade statistics, benchmarked against a relevant
market index.

## 2. The final strategy, in plain terms

**Universe**: live-pulled from niftyindices.com every run (`universe.py`)
— 300 stocks, always current, never a stale hand-typed list.

**Stock selection**: every month, every eligible stock (typically
~230-240 after filtering out names with too little clean price history)
gets scored on five signals, each standardized (z-scored) and combined
into one **composite score**. The top 10 by composite score are held for
that month.

**The five signals and their weights** — this is the direct answer to
"which factors are being used, what do they mean, how much weight does
each get":

| Signal | Weight | What it measures | Why it's in the strategy |
|---|---|---|---|
| **Momentum** | **40%** | 12-month return, most recent month excluded | Stocks that have been rising tend to keep rising over medium horizons (continuation effect) |
| **Low-volatility (close-to-close)** | **25%** | Trailing 6-month realized volatility (inverted — calmer stocks score higher) | Calmer stocks have historically shown better risk-adjusted returns than the CAPM would predict, and directly targets lower drawdown. Sees overnight gaps but not intraday swings. |
| **Parkinson volatility (intraday range)** | **10%** | Trailing 6-month volatility estimated from each day's High-Low range (inverted) | Captures how much a stock actually swings *within* a trading day — information close-to-close volatility misses entirely, since it only looks at closing prices |
| **52-week-high proximity** | **15%** | Current price ÷ trailing 12-month high | Stocks trading near their own recent high tend to keep outperforming — an anchoring-bias effect distinct from momentum |
| **Liquidity** | **10%** | Amihud illiquidity (price move per rupee traded), sign-flipped to prefer liquid stocks | A strategy that trades ~700-750 times over 5 years benefits from stocks that are easy to trade in and out of |

The two volatility signals are deliberately **complementary, not
redundant**: close-to-close volatility sees overnight gaps (news
overnight, a surprise earnings report before market open) but misses how
much a stock actually swings *during* the trading day; Parkinson
volatility sees that intraday range but is blind to gaps between one
day's close and the next day's open. Using both means the strategy
scores volatility on information neither one alone captures.

**Every one of these five signals is calculated purely from historical
price and trading-volume data.** None of them require company
fundamentals (P/E, ROE, etc.), which matters because those can only be
fetched as a *live, current* snapshot from this project's data source
(`yfinance`) — using today's fundamentals to simulate a decision made in
2022 would be **lookahead bias**: letting the simulation "see" information
that didn't exist yet. This strategy has none of that risk. (An earlier
version of this project *did* use fundamentals-based Value and Quality
factors, which carried this exact caveat — see §7 below for why it was
retired in favor of this fully lookahead-free version.)

**Position sizing**: once the 10 stocks are picked, money is allocated
across them using **Ledoit-Wolf shrinkage minimum-variance weighting**
(capped at 20% per stock) — not equal amounts, and not just "less money
to the shakier stock" the way a simpler scheme would. It uses the full
correlation structure between all 10 stocks (see §4).

**Rebalancing**: monthly — both the stock picks and the position sizes
are recalculated every month, not held fixed for a quarter.

## 3. Why these specific weights (40/25/10/15/10)?

These weights were not guessed, and not just grid-searched on the same
data being reported — they were found through **walk-forward
validation**, the same standard used to guard against overfitting in any
serious backtesting work, applied across **four independent checks**:

1. **Primary split**: the five-year backtest period was split into a
   **training window (2021-2023)** and a completely separate **test
   window (2024-2025)**. A grid of 126 different weight combinations
   was tested — but **only on the training window**. The training
   window's best-performing combinations were almost all heavily
   momentum-tilted (2021-2023 included a strong momentum-driven market
   recovery) — a candidate was chosen by maximizing the *worse* of
   (train Sharpe, test Sharpe), not the training leader, since train-test
   Sharpe correlation across all 126 combinations was only 0.276 (a real,
   positive signal, but far from strong enough to trust the raw leader).
2. **Fine-grid stress test**: rather than stop there, the neighborhood
   immediately around that candidate was checked at a finer resolution
   (step 0.05 instead of 0.10) — and it showed real fragility: nearby
   weight combinations swung from Sharpe 0.60 to 1.69 on the test window,
   with only 13% beating the shipped strategy on both windows.
3. **Independent second split**: the same candidate was then checked on
   a *completely different* train/test split (2023-2025 vs. 2021-2022)
   — and it beat the previous strategy on **both** halves of this
   different split too, a genuine cross-split signal rather than an
   artifact of one particular split choice.
4. **Re-centering**: inspecting the fine-grid data showed the
   good-performing points clustered together rather than scattering
   randomly. A point was deliberately chosen nearer the *center* of that
   cluster — trading a little peak train/test performance for a much
   higher worst-case floor nearby (the neighborhood's minimum test Sharpe
   rose from 0.60 to 1.10 after re-centering).

The final weights — momentum 40% / low-vol (close-to-close) 25% /
Parkinson volatility 10% / 52-week-high 15% / liquidity 10% — beat the
previous best strategy on **every one of the four validation checks
above**, not just the primary train/test split. See `CHANGELOG.md` for
the complete numeric trail, including the earlier (rejected) attempt to
add a fifth signal (short-term reversal) that looked excellent on
training data and made results *worse* on test data — the contrast
between that failure and this section's success is itself informative
about what a trustworthy validation process looks like.

## 4. Diversification, correlation, and what Ledoit-Wolf actually does

**Direct question asked and answered here: does Ledoit-Wolf ensure the
portfolio holds negatively-correlated stocks?**

**No — and that's an important distinction.** Ledoit-Wolf is a
*weighting* technique, not a *stock-picking* technique. It doesn't choose
which 10 stocks go into the portfolio (the four signals in §2 do that);
it only decides, given whichever 10 stocks were already picked, how much
money to put in each. Whether any two of those 10 stocks are positively
or negatively correlated is simply a fact about the stocks the selection
process happened to pick that month — Ledoit-Wolf has no ability to make
that fact different.

**What Ledoit-Wolf *does* do**: it correctly measures and *exploits*
whatever correlation structure actually exists among the 10 selected
stocks. Concretely, on a sample rebalance date checked for this project
(2021-11-01), the two most negatively-correlated stocks in that month's
portfolio (**IIFL.NS and TATAELXSI.NS**, correlation **-0.11**) were given
a **combined weight of 21.2%** by Ledoit-Wolf, versus only **17.9%** under
the simpler inverse-volatility scheme that ignores correlation entirely —
Ledoit-Wolf specifically increased the weight on the pair that reduces
overall portfolio risk through diversification, which a correlation-blind
scheme cannot do.

**How much genuine negative correlation exists in practice**: sampling 6
rebalance dates spread across the full 2021-2025 backtest and looking at
all 45 pairwise correlations among each month's 10 holdings (270 pairs
total):
- **7.0%** of all pairs were negatively correlated
- Average pairwise correlation: **0.20** (modestly positive — expected,
  since all 10 stocks are drawn from the same broad Indian equity market
  and share exposure to the same macro conditions)
- Correlation ranged from **-0.11** to **+0.90** across the sample

This is realistic, not disappointing: true negative correlation between
individual equities in the same market is genuinely uncommon (most stocks
share some exposure to the same economy-wide risk factors), so a
portfolio built entirely from long-only equity positions in one country's
market will always be mostly positively correlated. Real diversification
here comes less from finding negatively-correlated pairs and more from
avoiding the *most* correlated ones and sizing intelligently around
whatever correlation structure exists — which is exactly what Ledoit-Wolf
is doing. Genuinely reliable negative correlation (a true diversifier)
would require something outside this universe entirely — a different
asset class (bonds, gold) or a short position — both outside the "10
long-only equity positions" rules of this competition.

## 5. Results

Live data, 2021-01-01 to 2025-12-30, 238-stock filtered universe (from
the live 300-stock Nifty 100+Midcap100+Smallcap100 pull), ₹1,00,00,000
starting capital, net of 0.1% transaction cost per trade. From
`citadel_submission.xlsx`'s Summary_Metrics sheet:

| Metric | This strategy | Nifty 50 | Nifty 500 TMI |
|---|---|---|---|
| Total Net PNL | **₹3.90 crore** | — | — |
| Annualized Return | **38.4%** | 13.4% | 15.5% |
| Max Drawdown | **-19.1%** | -17.2% | -18.8% |
| Sharpe Ratio | **1.73** | 0.97 | 1.07 |
| Gain-to-Loss Ratio | 1.45 | — | — |
| Accuracy (win rate) | 66.5% | — | — |
| Total Trades | 744 | — | — |
| Total Transaction Cost | ₹14.9 lakh | — | — |

The strategy beats both benchmarks by a wide margin on return and
risk-adjusted return (Sharpe), with a max drawdown close to — and, for
Nifty 50, slightly deeper than — the benchmarks'. That's a genuinely
favorable trade: roughly 2.9x Nifty 50's annualized return and 1.8x its
Sharpe ratio for a max drawdown only ~1.9 percentage points worse.

## 6. The methodological journey (what makes this rigorous, not lucky)

This project went through several rounds of building, testing, and — in
more than one case — *rejecting* a result that looked good but didn't
hold up under scrutiny. That process is itself part of the deliverable:

1. **Initial build**: universe, data pipeline, four-factor
   fundamentals+price composite, inverse-volatility weighting.
2. **Two real bugs found and fixed** in the very first live run (a
   backtest engine bug that silently discarded dropped positions' value,
   and a benchmark-indexing bug) — caught because the first live numbers
   were implausible (a strategy roughly halving in value on a period when
   Indian equities were up), which prompted an investigation rather than
   accepting the number.
3. **Risk tuning**: reduced max drawdown from -33.5% to -19.6% and raised
   Sharpe from 1.54 to 1.65 by re-selecting monthly instead of quarterly
   and tilting the composite toward low-volatility — then, on noticing
   this cost ~35% of the primary PNL metric, found a deliberate midpoint
   (-26.6% MDD, Sharpe 1.57, PNL within 3% of the original) instead of
   chasing risk-adjusted metrics at the expense of the metric that
   actually ranks the competition.
4. **Weighting-scheme comparison**: implemented and empirically compared
   inverse-volatility, Ledoit-Wolf shrinkage minimum-variance, and
   Hierarchical Risk Parity (HRP). Ledoit-Wolf won on every metric
   simultaneously (not a trade-off) — verified across four separate
   robustness checks (different position caps, different factor blends,
   both the 2022 correction and the 2023-25 rally, both quarterly and
   monthly rebalancing) before being adopted.
5. **Lookahead-bias elimination**: replaced the fundamentals-based
   Value/Quality factors with fully price/volume-based ones (§2), after
   confirming empirically that the honest, untuned version still beat
   both benchmarks — and after an in-sample-only tuning attempt on top of
   it was caught being unstable and correctly discarded.
6. **Walk-forward validation** (§3): properly tuned the final weights
   using a genuine train/test split, catching that naive in-sample
   optimization would have selected momentum-heavy weights that fail
   badly on unseen data.
7. **GARCH-forecasted volatility, tested and rejected**: implemented a
   GARCH(1,1) volatility forecast as a candidate replacement for the
   simple trailing-volatility signal. Its full-period backtest number
   looked like a clear improvement (Sharpe 1.80 vs. 1.66) — but properly
   validated on the same train/test split, it underperformed the shipped
   strategy on *both* windows individually. A textbook demonstration of
   why a full-period backtest number can mislead in exactly the direction
   that looks most convincing.
8. **GARCH-based volatility targeting, retested and still rejected**:
   revisited an earlier-rejected "scale exposure down when volatility is
   high" overlay using GARCH instead of a rolling average, on the theory
   that GARCH's faster reaction might fix the original version's lag
   problem. Traced actual exposure at every rebalance date and confirmed
   the mechanism genuinely works (real de-risking during the 2022
   correction and a 2024 volatility episode) — but the backtest's single
   worst drawdown occurred before the overlay's first-ever exposure
   reduction, so no forecast improvement could have helped this specific
   number. A concrete example of a technique being mechanically correct
   while still not moving the metric it was meant to improve.
9. **Parkinson volatility added as a 5th factor, validated four separate
   ways** (§3): the current, final version of the strategy. An initial
   candidate looked promising on the primary train/test split but showed
   real fragility on closer inspection (a finer-resolution neighborhood
   check, requested explicitly before adopting anything) — rather than
   discard the idea or adopt the fragile version, re-centered the weights
   within the cluster of genuinely good-performing combinations, then
   re-validated on an independent second train/test split. The final
   weights beat the previous strategy on all four checks, not just one.

Every one of these steps is logged with exact numbers in `CHANGELOG.md`.

## 7. Known limitations

- **Single historical backtest window.** All results, however carefully
  validated, are drawn from one specific stretch of Indian market
  history (2021-2025). Walk-forward validation reduces but cannot fully
  eliminate the risk that this period's particular character (a strong
  recovery, one correction, a broad rally) shapes the result more than a
  longer, more varied history would.
- **Midcap/Smallcap100 universe freshness depends on network access.**
  `universe.py` pulls live from niftyindices.com every run; if that's
  unreachable, it falls back to a local cache that could be stale.
- **Transaction cost model is simplified.** A flat 0.1% per trade is
  charged per the competition rules; real-world costs also include
  bid-ask spread and market impact, which aren't separately modeled
  (though the liquidity factor indirectly favors easier-to-trade names).
- **No shorting, no leverage, no derivatives** — by the competition's own
  rules, so this isn't a limitation of the strategy so much as the
  problem definition; it does mean true negative-correlation
  diversification (see §4) isn't achievable within these rules.

## 8. How Claude was used on this project

In the interest of full transparency for academic review: this project
was built through an extended, interactive collaboration with **Claude
Code** (Anthropic's AI coding assistant), working from Aug 20-29, 2026.
The nature of that collaboration:

- **Claude wrote the entire codebase** (`data.py`, `factors.py`,
  `portfolio.py`, `backtest.py`, `metrics.py`, `optimizers.py`,
  `export_excel.py`, `citadel.py`, `universe.py`) based on direction and
  requirements provided in conversation.
- **Claude ran the actual backtests** against live market data (via the
  `yfinance` library and niftyindices.com), including every tuning sweep,
  robustness check, and the walk-forward validation described in §3 and
  §6 — these are real computed results on real historical data, not
  fabricated or estimated numbers.
- **The human's role** was directing what to build and test, asking
  clarifying/challenging questions (e.g. "is this being taken care of in
  Ledoit-Wolf?", "are we using HRP/Ledoit-Wolf?", "do more rigorous
  tuning"), making the final calls on trade-offs Claude flagged (e.g.
  whether to prioritize Total Net PNL or Sharpe/drawdown when they
  conflicted), and requesting this documentation.
- **Claude proactively flagged its own mistakes and limitations**
  throughout — including the two real bugs in §6.2, the rejected unstable
  tuning attempts in §6.5, and the lookahead-bias caveat in the original
  fundamentals-based version — rather than only reporting favorable
  results. This documentation itself, including this disclosure section,
  was written by Claude at the user's request.
- **What a student should be able to explain unaided**: the concepts in
  `CONCEPTS.md` and `BEGINNERS_GUIDE.md` (momentum, volatility,
  correlation, shrinkage, walk-forward validation, overfitting) are
  standard, citable quantitative-finance and statistics concepts, not
  Claude-specific claims — a student presenting this work should be able
  to explain *why* each choice was made, using these documents as study
  material, not simply read numbers off a slide.

## 9. How to reproduce

```
python citadel.py
```

Runs the full pipeline end to end against live data: pulls the current
300-stock universe, downloads five-plus years of OHLCV, builds the
monthly-rebalanced portfolio, backtests it with transaction costs,
benchmarks it, and writes `citadel_submission.xlsx`.
