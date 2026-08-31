"""
Stock selection and weighting: turns per-date composite factor scores into
a sequence of "as-of" target portfolios (top 10 names, capped Ledoit-Wolf
minimum-variance weights - see optimizers.py), re-scored and re-selected
monthly. See CONCEPTS.md for why each piece is used, and CHANGELOG.md for
the tuning history behind these particular defaults.

DEFAULT FACTOR SET: "lookahead_free" (CONCEPTS.md §24-30). Every signal
it uses (momentum, low-vol, 52-week-high, liquidity) is built purely from
historical price/volume data, which yfinance returns correctly as of any
past date - so, unlike the retired "original" set (value/quality from
current-snapshot fundamentals), nothing here could have used information
that would not actually have been available at the time of each simulated
decision. Its weights were chosen via walk-forward validation (tuned on
2021-2023, confirmed on unseen 2024-2025) rather than in-sample search
alone - see CONCEPTS.md §30 for the full methodology and why this
specific combination survived where several others didn't.
"""
import numpy as np
import pandas as pd

import factors

# Retired as the default (kept for comparison/reference - CONCEPTS.md §18
# documents its lookahead-bias caveat). Tuned empirically against the
# 2021-2025 backtest as a deliberate PNL/risk midpoint.
DEFAULT_FACTOR_WEIGHTS = {"momentum": 0.28, "low_vol": 0.30, "value": 0.21, "quality": 0.21}

# Composite-score recipes (CONCEPTS.md §24-34). "original" uses
# value/quality from current-snapshot fundamentals (lookahead-bias caveat,
# CONCEPTS.md §18) - retained for reference, no longer the default.
# "lookahead_free" is built purely from historical price/volume, which is
# genuinely point-in-time safe. As of CONCEPTS.md §34, it uses FIVE
# factors - close-to-close AND Parkinson range volatility together as
# distinct, complementary signals (close-to-close catches overnight
# gaps, Parkinson catches intraday range - neither alone sees both), not
# swapping one for the other. Weights validated across FOUR separate
# checks: the original train(2021-23)/test(2024-25) split, a second
# independent split (2021-22 vs 2023-25), and a fine-grained (step 0.05)
# neighborhood check on both - deliberately chosen as a point centered in
# the neighborhood's cluster of good performance rather than the single
# best grid point, trading a little peak performance for a much higher
# worst-case floor nearby (min neighborhood test Sharpe 1.10 vs. 0.60 for
# the un-centered candidate first found).
FACTOR_SETS = {
    "original": ("momentum", "low_vol", "value", "quality"),
    "lookahead_free": ("momentum", "low_vol", "parkinson_vol", "high52", "liquidity"),
}
DEFAULT_FACTOR_WEIGHTS_BY_SET = {
    "original": DEFAULT_FACTOR_WEIGHTS,
    "lookahead_free": {"momentum": 0.40, "low_vol": 0.25, "parkinson_vol": 0.10,
                        "high52": 0.15, "liquidity": 0.10},
}


def _factor_series(name: str, d: pd.Timestamp, prices: pd.DataFrame, log_ret: pd.DataFrame,
                    high: pd.DataFrame, low: pd.DataFrame, volume: pd.DataFrame,
                    value_static: pd.Series, quality_static: pd.Series,
                    use_parkinson: bool, benchmark_log_ret: pd.Series = None) -> pd.Series:
    """Compute one named factor's raw (pre-zscore) cross-section as of date d.
    Dispatches to the right factors.py function - see FACTOR_SETS for which
    names are actually requested by a given factor_set."""
    if name == "momentum":
        return factors.momentum_factor(prices, d)
    if name == "low_vol":
        if use_parkinson:
            return factors.parkinson_vol_factor(high, low, d)
        return factors.low_vol_factor(log_ret, d)
    if name == "parkinson_vol":
        return factors.parkinson_vol_factor(high, low, d)
    if name == "reversal":
        return factors.reversal_factor(prices, d)
    if name == "idio_vol":
        return factors.idiosyncratic_vol_factor(log_ret, benchmark_log_ret, d)
    if name == "downside_vol":
        return factors.downside_vol_factor(log_ret, d)
    if name == "garch_vol":
        return factors.garch_vol_factor(log_ret, d)
    if name == "high52":
        return factors.high52_factor(prices, d)
    if name == "liquidity":
        return factors.liquidity_factor(log_ret, prices, volume, d)
    if name == "value":
        return value_static
    if name == "quality":
        return quality_static
    raise ValueError(f"Unknown factor name {name!r}")


def rebalance_dates(index: pd.DatetimeIndex, start, end, freq: str = "MS") -> list:
    """Trading-day rebalance dates: the first available trading day on/after
    each period start between start and end (inclusive). Default is
    monthly ("MS") - see CHANGELOG.md for why monthly re-selection beats
    quarterly on this backtest (stale quarterly picks were a bigger driver
    of drawdown than the weighting scheme)."""
    schedule = pd.date_range(start=start, end=end, freq=freq)
    dates = []
    for d in schedule:
        candidates = index[index >= d]
        if len(candidates) > 0:
            dates.append(candidates[0])
    return sorted(set(dates))


def select_top_n(scores: pd.Series, n: int = 10) -> list:
    """Highest composite-score names, dropping any with a missing score."""
    return scores.dropna().sort_values(ascending=False).head(n).index.tolist()


def select_top_n_with_buffer(scores: pd.Series, prev_holdings: list, n: int = 10,
                              buffer: int = 3) -> list:
    """Turnover-reduction "buffer zone" selection: a currently-held stock
    stays in as long as its rank is within top (n + buffer), not strictly
    top n - only new entrants still need to actually rank in the top n.
    Cuts trading driven by noisy near-tied re-ranking each month.

    buffer=3 chosen via walk-forward backtest across {0,2,3,5,8}: 3 beat
    the no-buffer baseline on both an independent train (2021-2023) and
    test (2024-2025) window on every metric (Sharpe, return, drawdown,
    turnover), sitting at the peak of a clean rise-then-fall across the
    grid rather than an isolated spike (CONCEPTS.md §38).
    """
    ranked = scores.dropna().sort_values(ascending=False)
    ranks = {ticker: i + 1 for i, ticker in enumerate(ranked.index)}

    picks = [t for t in prev_holdings if ranks.get(t, float("inf")) <= n + buffer]
    for t in ranked.index:
        if len(picks) >= n:
            break
        if t not in picks:
            picks.append(t)
    return picks[:n]


def inverse_vol_weights(log_ret: pd.DataFrame, tickers: list, as_of: pd.Timestamp,
                         window_days: int = 126) -> pd.Series:
    """Weight each name inversely to its trailing volatility, normalized to sum to 1.

    A rougher (higher-vol) stock gets a smaller position so no single name
    dominates the portfolio's risk - a simple, robust proxy for the
    minimum-variance idea without needing a full covariance-matrix inversion.
    """
    window = log_ret.loc[:as_of, tickers].tail(window_days)
    vol = window.std(ddof=0)
    inv_vol = 1.0 / vol.replace(0, np.nan)
    inv_vol = inv_vol.dropna()
    return inv_vol / inv_vol.sum()


def cap_weights(weights: pd.Series, max_weight: float = 0.20) -> pd.Series:
    """Cap any single position at max_weight, redistributing the excess
    proportionally across the uncapped names, then renormalize.

    Inverse-vol weighting in a 10-name book can otherwise push a single
    unusually-calm stock to dominate the portfolio - defeating the purpose
    of holding 10 names for diversification. Iterates because
    redistribution can itself push another name over the cap. In practice
    this rarely binds with the current universe (see CHANGELOG.md) but is
    kept as a robustness guard against future, more concentrated picks.
    """
    w = weights.copy().astype(float)
    for _ in range(len(w)):
        over = w[w > max_weight]
        if over.empty:
            break
        excess = (over - max_weight).sum()
        w[over.index] = max_weight
        under = w[w < max_weight]
        if under.sum() <= 0:
            break
        w[under.index] += excess * (under / under.sum())
    return w / w.sum()


def apply_sector_cap(weights: pd.Series, industry_by_ticker: pd.Series, sector_cap: float = 0.35) -> pd.Series:
    """Cap total weight per industry, redistributing excess proportionally
    across stocks in under-cap sectors and renormalizing, iterating since
    redistribution can itself push another sector over the cap.

    cap_weights() only bounds a single stock at a time - nothing stops
    several of the top-n picks landing in the same sector when momentum,
    low-vol, and 52-week-high all favor it simultaneously (seen empirically
    reaching 67% in one sector on some rebalance dates). Tested via
    backtest: this cap removed every >40%-in-one-sector rebalance while
    slightly improving return, drawdown, and Sharpe over the full
    2021-2025 backtest - a real diversification benefit, not just a
    risk/return tradeoff.

    NOTE: used standalone, this can push an individual stock's weight
    above max_weight (e.g. the sole holding in an otherwise-empty sector
    absorbing that sector's whole redistributed allowance) - see
    apply_caps() for the version that enforces both caps jointly, used by
    build_portfolio_weights().
    """
    w = weights.copy().astype(float)
    industries = pd.Series(w.index.map(industry_by_ticker).fillna("Unknown"), index=w.index)
    for _ in range(len(w)):
        sector_weight = w.groupby(industries).sum()
        over_sectors = sector_weight[sector_weight > sector_cap]
        if over_sectors.empty:
            break
        excess = 0.0
        for sector in over_sectors.index:
            mask = industries == sector
            sector_total = w[mask].sum()
            excess += sector_total - sector_cap
            w[mask] *= sector_cap / sector_total
        under_mask = ~industries.isin(over_sectors.index)
        under_sum = w[under_mask].sum()
        if under_sum <= 0:
            break
        w[under_mask] += excess * (w[under_mask] / under_sum)
    return w / w.sum()


def apply_caps(weights: pd.Series, industry_by_ticker: pd.Series, max_weight: float = 0.20,
               sector_cap: float = 0.35, max_iter: int = 50) -> pd.Series:
    """Enforce a per-stock cap and a per-sector cap simultaneously.

    Doing these two caps independently (apply_sector_cap() then
    cap_weights(), or the reverse) doesn't reliably converge to a point
    that satisfies both: sector redistribution can push a single stock
    above max_weight (e.g. the lone holding in an otherwise-empty sector
    absorbing that whole sector's redistributed room - observed pushing
    a stock to 30% despite a 20% per-stock cap), and naively alternating
    the two operators can settle at a fixed point where the sector cap
    is violated instead.

    A per-stock or per-sector cap is only an *upper* bound - scaling a
    capped stock/sector back down further never violates it - so each
    iteration simply re-clips every stock to max_weight, scales down any
    over-cap sector (its members included, even ones just clipped),
    then redistributes any resulting shortfall only into stocks that
    have genuine headroom on *both* dimensions. Repeats until stable;
    self-correcting because a redistribution that overshoots either cap
    gets caught and re-clipped on the next pass.

    When the two caps make full investment mathematically impossible
    (e.g. two stocks in one sector each already at max_weight sum to
    more than sector_cap, or a single-member sector is bounded by
    max_weight below what sector_cap would otherwise allow), the
    unallocated remainder is left as cash - same convention as the
    vol_target overlay - rather than breaking a cap to force full
    investment.
    """
    w = (weights / weights.sum()).astype(float)
    industries = pd.Series(w.index.map(industry_by_ticker).fillna("Unknown"), index=w.index)

    for _ in range(max_iter):
        before = w.copy()

        w = w.clip(upper=max_weight)

        sector_weight = w.groupby(industries).sum()
        over_sectors = sector_weight[sector_weight > sector_cap + 1e-10]
        for sector, total in over_sectors.items():
            mask = industries == sector
            w[mask] *= sector_cap / total

        shortfall = 1.0 - w.sum()
        if shortfall > 1e-10:
            sector_weight = w.groupby(industries).sum()
            headroom_mask = (w < max_weight - 1e-10) & (industries.map(sector_weight) < sector_cap - 1e-10)
            headroom_sum = w[headroom_mask].sum()
            if headroom_sum > 0:
                w[headroom_mask] += shortfall * (w[headroom_mask] / headroom_sum)

        if w.sub(before, fill_value=0).abs().max() < 1e-10:
            break

    return w


def portfolio_realized_vol(log_ret: pd.DataFrame, tickers: list, weights: pd.Series,
                            as_of: pd.Timestamp, window_days: int = 63) -> float:
    """Trailing realized volatility of the actual weighted basket (not the
    average of individual vols - this uses the real correlation structure
    since it sums the tickers' returns with weights first)."""
    window = log_ret.loc[:as_of, tickers].tail(window_days)
    port_daily_ret = window.reindex(columns=tickers).fillna(0) @ weights.reindex(tickers).fillna(0)
    return port_daily_ret.std(ddof=0) * np.sqrt(252)


def portfolio_garch_vol(log_ret: pd.DataFrame, tickers: list, weights: pd.Series,
                         as_of: pd.Timestamp, window_days: int = 252, min_obs: int = 180) -> float:
    """GARCH(1,1)-forecasted next-day volatility of the weighted basket's
    own historical return series, annualized - a swap-in for
    portfolio_realized_vol() in the volatility-targeting overlay
    (CONCEPTS.md §33).

    Builds one composite daily-return series (the same weighted-basket
    return portfolio_realized_vol() uses), then fits a single GARCH(1,1)
    to that series and forecasts one day ahead - one fit per rebalance
    date, not one per stock (see factors.garch_vol_factor() for the
    per-stock version used in composite scoring). The motivation is
    exactly the failure mode portfolio_realized_vol() has when used for
    vol-targeting: a flat trailing average reacts slowly to a fresh
    shock, while GARCH's clustering structure explicitly weights the most
    recent shock more heavily.
    """
    from arch import arch_model

    window = log_ret.loc[:as_of, tickers].tail(window_days)
    port_daily_ret = window.reindex(columns=tickers).fillna(0) @ weights.reindex(tickers).fillna(0)
    port_daily_ret = port_daily_ret.dropna()
    if len(port_daily_ret) < min_obs:
        return portfolio_realized_vol(log_ret, tickers, weights, as_of, window_days=63)
    try:
        model = arch_model(port_daily_ret * 100, vol="Garch", p=1, q=1, mean="Zero", dist="normal")
        res = model.fit(disp="off", show_warning=False)
        forecast = res.forecast(horizon=1, reindex=False)
        daily_var_pct2 = forecast.variance.values[-1, 0]
        daily_vol = np.sqrt(daily_var_pct2) / 100
        return daily_vol * np.sqrt(252)
    except Exception:
        return portfolio_realized_vol(log_ret, tickers, weights, as_of, window_days=63)


def volatility_target_exposure(realized_vol: float, target_vol: float = 0.20,
                                min_exposure: float = 0.5, max_exposure: float = 1.0) -> float:
    """Scale exposure so realized risk tracks a fixed annualized target.

    exposure = target_vol / realized_vol, clipped to [min_exposure, max_exposure].
    Available as an opt-in overlay (pass vol_target= to build_portfolio_weights)
    but OFF by default: tested empirically against this backtest and found
    to lag real drawdowns (63-day trailing window reacts too slowly) while
    dragging on quiet uptrends - net effect was neutral-to-negative on
    Sharpe. See CHANGELOG.md for the comparison. Monthly re-selection with
    a low-vol-tilted composite score (DEFAULT_FACTOR_WEIGHTS) proved to be
    the effective lever instead.
    """
    if realized_vol is None or not np.isfinite(realized_vol) or realized_vol <= 0:
        return max_exposure
    return float(np.clip(target_vol / realized_vol, min_exposure, max_exposure))


WEIGHTING_SCHEMES = ("inverse_vol", "ledoit_wolf", "hrp")


def _compute_weights(scheme: str, log_ret: pd.DataFrame, picks: list,
                      d: pd.Timestamp, max_weight: float) -> pd.Series:
    """Dispatch to one of the three weighting schemes. inverse_vol treats
    each stock's risk independently (CONCEPTS.md §9); ledoit_wolf and hrp
    both use the full covariance/correlation structure between stocks
    instead (CONCEPTS.md §20-22, optimizers.py)."""
    if scheme == "inverse_vol":
        return cap_weights(inverse_vol_weights(log_ret, picks, d), max_weight=max_weight)
    if scheme == "ledoit_wolf":
        from optimizers import ledoit_wolf_weights
        return ledoit_wolf_weights(log_ret, picks, d, max_weight=max_weight)
    if scheme == "hrp":
        from optimizers import hrp_weights
        return hrp_weights(log_ret, picks, d, max_weight=max_weight)
    raise ValueError(f"Unknown weighting_scheme {scheme!r}, expected one of {WEIGHTING_SCHEMES}")


def build_portfolio_weights(prices: pd.DataFrame, log_ret: pd.DataFrame,
                             fundamentals: pd.DataFrame, start: str, end: str,
                             n_stocks: int = 10, freq: str = "MS",
                             max_weight: float = 0.20, vol_target: float = None,
                             min_exposure: float = 0.5,
                             factor_weights: dict = None,
                             weighting_scheme: str = "ledoit_wolf",
                             factor_set: str = "lookahead_free",
                             high: pd.DataFrame = None, low: pd.DataFrame = None,
                             volume: pd.DataFrame = None,
                             use_parkinson: bool = False,
                             benchmark_log_ret: pd.Series = None,
                             factor_names: tuple = None,
                             vol_target_use_garch: bool = False,
                             sector_cap: float = 0.35,
                             industry_by_ticker: pd.Series = None,
                             turnover_buffer: int = 3) -> dict:
    """Full pipeline: at every rebalance date, re-score the universe,
    pick the top n_stocks by composite factor score, and weight them
    using weighting_scheme (one of WEIGHTING_SCHEMES - see
    optimizers.py and CONCEPTS.md §20-22 for ledoit_wolf/hrp).

    sector_cap bounds total weight in any one NSE industry (see
    apply_sector_cap) - default 0.35, set to None to disable. Applied on
    top of the per-stock cap. industry_by_ticker defaults to
    universe.INDUSTRY_BY_TICKER when not passed explicitly.

    turnover_buffer (see select_top_n_with_buffer) keeps a held stock in
    the portfolio as long as its rank is within top (n_stocks + buffer),
    reducing trading driven by noisy near-tied re-ranking - default 3,
    set to 0 to disable and select strictly top n_stocks every rebalance.

    factor_set selects which composite-score recipe to use (see
    FACTOR_SETS / CONCEPTS.md §24-26): "original" (momentum, low_vol,
    value, quality - value/quality carry the lookahead-bias caveat) or
    "lookahead_free" (momentum, low_vol, high52, liquidity - built purely
    from historical price/volume, genuinely point-in-time safe). The
    lookahead_free set and use_parkinson=True both require high/low/volume
    (from data.download_ohlcv()) to be passed in.

    vol_target is an optional volatility-targeting overlay (see
    volatility_target_exposure docstring) - None (default) leaves it off.

    Returns {date: pd.Series of weights indexed by ticker}. If vol_target
    is set, weights on a given date may sum to <1 - the remainder is held
    in cash by the backtest engine.
    """
    if factor_names is None:
        if factor_set not in FACTOR_SETS:
            raise ValueError(f"Unknown factor_set {factor_set!r}, expected one of {tuple(FACTOR_SETS)}")
        factor_names = FACTOR_SETS[factor_set]
        factor_weights = factor_weights or DEFAULT_FACTOR_WEIGHTS_BY_SET[factor_set]
    elif factor_weights is None:
        raise ValueError("factor_weights is required when factor_names is passed explicitly")

    if industry_by_ticker is None and sector_cap is not None:
        from universe import INDUSTRY_BY_TICKER
        industry_by_ticker = INDUSTRY_BY_TICKER

    dates = rebalance_dates(prices.index, start, end, freq)
    value_static = factors.value_factor(fundamentals) if "value" in factor_names else None
    quality_static = factors.quality_factor(fundamentals) if "quality" in factor_names else None

    weights_by_date = {}
    prev_holdings = []
    for d in dates:
        factor_series = {
            name: _factor_series(name, d, prices, log_ret, high, low, volume,
                                  value_static, quality_static, use_parkinson, benchmark_log_ret)
            for name in factor_names
        }
        composite = factors.composite_score(factor_series, weights=factor_weights)
        if turnover_buffer:
            picks = select_top_n_with_buffer(composite, prev_holdings, n=n_stocks, buffer=turnover_buffer)
        else:
            picks = select_top_n(composite, n=n_stocks)
        if not picks:
            continue

        weights = _compute_weights(weighting_scheme, log_ret, picks, d, max_weight)
        if weights.empty:
            continue
        prev_holdings = picks
        if sector_cap is not None:
            weights = apply_caps(weights, industry_by_ticker, max_weight=max_weight, sector_cap=sector_cap)
        if vol_target is not None:
            if vol_target_use_garch:
                realized_vol = portfolio_garch_vol(log_ret, picks, weights, d)
            else:
                realized_vol = portfolio_realized_vol(log_ret, picks, weights, d)
            exposure = volatility_target_exposure(realized_vol, target_vol=vol_target, min_exposure=min_exposure)
            weights = weights * exposure

        weights_by_date[d] = weights

    return weights_by_date
