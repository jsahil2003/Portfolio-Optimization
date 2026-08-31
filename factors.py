"""
Factor computation: turns raw prices / fundamentals into standardized,
comparable stock scores. See CONCEPTS.md for the math and intuition behind
every function here.

Two families of factor, split by data source:

    Price/volume-based (genuinely point-in-time safe - see CONCEPTS §24):
        momentum_factor()        - 12-1 month return
        low_vol_factor()         - close-to-close realized volatility
        parkinson_vol_factor()   - High/Low-range realized volatility (an
                                    alternative, more efficient estimator
                                    of the same thing - see CONCEPTS §26)
        high52_factor()          - proximity to trailing 52-week high
        liquidity_factor()       - Amihud illiquidity, sign-flipped
        reversal_factor()        - 1-month return, sign-flipped (CONCEPTS §28)
        idiosyncratic_vol_factor() - stock-specific vol after removing
                                    market beta (CONCEPTS §28)
        downside_vol_factor()    - volatility from down-days only (CONCEPTS §28)

    Fundamentals-based (CAVEAT: lookahead bias - see below):
        value_factor()
        quality_factor()

CAVEAT (point-in-time bias): yfinance only exposes *current* fundamentals
(P/E, P/B, ROE, D/E) via fetch_fundamentals(), not the historical-as-of-
date values. value_factor() and quality_factor() therefore use today's
snapshot for every rebalance date in the backtest, which is a lookahead-
bias simplification (CONCEPTS.md §18). The price/volume-based factors
above do NOT have this problem: yfinance's historical OHLCV is genuinely
point-in-time correct, so any signal built from it only uses information
that was actually observable as of that date. See CONCEPTS.md §24-26 and
portfolio.FACTOR_SETS for the two composite variants this enables.
"""
import numpy as np
import pandas as pd


def zscore(series: pd.Series) -> pd.Series:
    """Standardize a cross-section of raw factor values to mean 0, std 1.

    Makes factors measured in unrelated units (percent momentum, ratio-of-
    ratios P/E, decimal ROE) directly comparable and averageable.
    """
    mu, sigma = series.mean(), series.std(ddof=0)
    if sigma == 0 or np.isnan(sigma):
        return series * 0.0
    return (series - mu) / sigma


def momentum_factor(prices: pd.DataFrame, as_of: pd.Timestamp,
                     lookback_days: int = 252, skip_days: int = 21) -> pd.Series:
    """12-1 month momentum: cumulative return from (as_of - 12m) to (as_of - 1m).

    The most recent month is skipped to avoid short-term reversal effects
    (stocks that just spiked tend to mean-revert over the next few weeks).
    """
    window = prices.loc[:as_of].tail(lookback_days)
    if len(window) <= skip_days:
        return pd.Series(np.nan, index=prices.columns)
    start_px = window.iloc[0]
    end_px = window.iloc[-1 - skip_days]
    raw = (end_px / start_px) - 1.0
    return raw


def low_vol_factor(log_ret: pd.DataFrame, as_of: pd.Timestamp,
                    window_days: int = 126) -> pd.Series:
    """Trailing close-to-close realized volatility, sign-flipped so lower
    risk -> higher score. See parkinson_vol_factor() for a range-based
    alternative that uses more information per trading day."""
    window = log_ret.loc[:as_of].tail(window_days)
    vol = window.std(ddof=0) * np.sqrt(252)
    return -vol


def parkinson_vol_factor(high: pd.DataFrame, low: pd.DataFrame, as_of: pd.Timestamp,
                          window_days: int = 126) -> pd.Series:
    """Parkinson (1980) range-based volatility estimator, sign-flipped like
    low_vol_factor (lower risk -> higher score).

    Formula: for each day, variance_t = (ln(High_t/Low_t))^2 / (4*ln2);
    annualize the mean of that over the window the same way as close-to-
    close volatility (x sqrt(252)).

    Why this can beat close-to-close volatility: a close-to-close return
    only uses 2 price points per day (yesterday's close, today's close).
    The day's full High-Low range captures how much the stock actually
    moved intraday, which is strictly more information about that day's
    true volatility - Parkinson showed this makes the estimator more
    *statistically efficient* (lower variance for the same sample size),
    around 5x more efficient under the estimator's idealized assumptions.
    It does NOT capture overnight gaps (a stock that closes flat but gaps
    up at the next open looks calm to Parkinson but wasn't) - close-to-
    close volatility is the one estimator here that does see gaps, so the
    two are complementary rather than one strictly replacing the other.
    """
    h = high.loc[:as_of].tail(window_days)
    l = low.loc[:as_of].tail(window_days)
    log_hl = np.log(h / l)
    daily_var = (log_hl ** 2) / (4 * np.log(2))
    annualized_vol = np.sqrt(daily_var.mean() * 252)
    return -annualized_vol


def garch_vol_factor(log_ret: pd.DataFrame, as_of: pd.Timestamp,
                      window_days: int = 252, min_obs: int = 180) -> pd.Series:
    """GARCH(1,1)-forecasted next-day volatility, annualized and sign-
    flipped like low_vol_factor (lower forecast risk -> higher score).

    Unlike low_vol_factor's trailing standard deviation - which treats
    every day in the window as equally informative about "today's" risk -
    a GARCH(1,1) model treats volatility as mean-reverting and clustered:
    today's variance is modeled as a weighted combination of the long-run
    average variance, yesterday's variance, and yesterday's squared
    return shock. That lets a GARCH forecast react faster to a recent
    volatility spike (a big shock yesterday raises today's forecast more
    than it would nudge a 252-day flat average) while still pulling back
    toward the long-run mean once the shock passes - closer to how
    volatility actually behaves in real markets ("volatility clustering":
    calm periods follow calm periods, turbulent periods follow turbulent
    ones) than a flat trailing-window average captures.

    NOTE: this is a forecast of RISK, not return - GARCH does not predict
    which direction a stock will move, only how much it's expected to
    move. "GARCH expected return" would require a GARCH-in-Mean setup
    (regressing return on the conditional variance) which is a separate,
    empirically much shakier technique not implemented here - see
    CONCEPTS.md for the distinction.

    Needs more data than the other factors (min_obs, default 180 daily
    observations) for the GARCH MLE to converge reliably - falls back to
    NaN (excluded from that date's ranking) for any stock with too short
    a history, or where the optimizer fails to converge.
    """
    from arch import arch_model

    window = log_ret.loc[:as_of].tail(window_days)
    forecasts = {}
    for ticker in window.columns:
        series = window[ticker].dropna()
        if len(series) < min_obs:
            forecasts[ticker] = np.nan
            continue
        try:
            # Returns scaled to percent: arch's optimizer is numerically
            # more stable on data of order ~1 than order ~0.01.
            model = arch_model(series * 100, vol="Garch", p=1, q=1, mean="Zero", dist="normal")
            res = model.fit(disp="off", show_warning=False)
            forecast = res.forecast(horizon=1, reindex=False)
            daily_var_pct2 = forecast.variance.values[-1, 0]
            daily_vol = np.sqrt(daily_var_pct2) / 100
            forecasts[ticker] = daily_vol * np.sqrt(252)
        except Exception:
            forecasts[ticker] = np.nan

    return -pd.Series(forecasts)


def high52_factor(prices: pd.DataFrame, as_of: pd.Timestamp,
                   window_days: int = 252) -> pd.Series:
    """52-week-high proximity (George & Hwang, 2004): current price divided
    by its own trailing 252-day maximum. A stock trading right at its
    52-week high scores near 1.0; one trading well below it scores lower.

    Distinct from momentum_factor(): two stocks can have identical 12-1
    month returns while one is at a new high and the other is recovering
    from a much larger drawdown - this factor tells them apart. The
    documented anomaly is that stocks near their 52-week high tend to
    keep outperforming, an anchoring-bias effect (investors underreact
    near a salient recent reference price) distinct from standard
    momentum's continuation story.
    """
    window = prices.loc[:as_of].tail(window_days)
    if len(window) < 2:
        return pd.Series(np.nan, index=prices.columns)
    rolling_max = window.max()
    current = window.iloc[-1]
    return current / rolling_max


def liquidity_factor(log_ret: pd.DataFrame, prices: pd.DataFrame, volume: pd.DataFrame,
                      as_of: pd.Timestamp, window_days: int = 126) -> pd.Series:
    """Amihud (2002) illiquidity, sign-flipped so MORE liquid -> higher
    score (consistent with every other factor's "higher is better"
    convention, and practically sensible for a strategy that rebalances
    monthly and pays transaction costs on every trade).

    Amihud illiquidity = mean( |daily return| / rupee volume traded ).
    A stock whose price moves a lot on modest trading value has high
    price impact per rupee - illiquid. A stock that barely moves despite
    heavy trading value is liquid; buying or selling it moves the price
    less.

    Note: the academic literature typically studies the *illiquidity
    premium* (illiquid stocks have historically earned higher average
    returns, presumably compensating investors for the extra difficulty
    of trading them) - i.e. NOT sign-flipped, illiquid stocks preferred.
    This project deliberately does the opposite: preferring liquid stocks
    is the more defensible choice for a strategy that actually executes
    ~700 trades over 5 years and pays real transaction costs on each one,
    where execution risk is a real (if not separately modeled) cost.
    """
    rupee_volume = prices.loc[:as_of, volume.columns].tail(window_days) * volume.loc[:as_of].tail(window_days)
    abs_ret = log_ret.loc[:as_of, volume.columns].tail(window_days).abs()
    illiquidity = (abs_ret / rupee_volume.replace(0, np.nan)).mean()
    return -illiquidity


def reversal_factor(prices: pd.DataFrame, as_of: pd.Timestamp,
                     lookback_days: int = 21) -> pd.Series:
    """Short-term reversal (Jegadeesh, 1990): the most recent 1-month
    return, sign-flipped so recent LOSERS score higher.

    This is deliberately the mirror image of the month momentum_factor()
    skips. The two aren't redundant: momentum says "12-1 month winners
    keep winning" (continuation, driven by underreaction to news over
    medium horizons); reversal says "1-month losers tend to bounce back"
    (overreaction/liquidity-provision at short horizons - investors who
    sold in a panic or a forced seller who needed liquidity depress the
    price temporarily below fair value, and it partially corrects). Same
    underlying data (price history), opposite-signed and different-
    horizon hypothesis - about as orthogonal as two price-based factors
    can be.
    """
    window = prices.loc[:as_of].tail(lookback_days)
    if len(window) < 2:
        return pd.Series(np.nan, index=prices.columns)
    raw_return = (window.iloc[-1] / window.iloc[0]) - 1.0
    return -raw_return


def idiosyncratic_vol_factor(log_ret: pd.DataFrame, benchmark_log_ret: pd.Series,
                              as_of: pd.Timestamp, window_days: int = 126) -> pd.Series:
    """Stock-specific volatility left over after removing each stock's
    market-driven co-movement, sign-flipped like low_vol_factor.

    For each stock, estimate beta = Cov(stock, market) / Var(market) over
    the trailing window, then residual_t = stock_return_t - beta * market_return_t.
    idiosyncratic_vol = std(residual) annualized.

    Why this differs from low_vol_factor(): total volatility mixes two
    very different sources of risk - how much a stock moves *because the
    whole market moved* (systematic/market risk, which diversification
    across many stocks can't remove) and how much it moves for reasons
    specific to that company (idiosyncratic risk, which a 10-stock
    portfolio's diversification genuinely reduces). A stock can have
    ordinary total volatility while carrying unusually high company-
    specific risk (a stock with pending litigation, a key-person
    dependency, a single-customer concentration) that total volatility
    alone wouldn't flag as clearly as the residual does.
    """
    window = log_ret.loc[:as_of].tail(window_days)
    market = benchmark_log_ret.loc[:as_of].tail(window_days)
    common_dates = window.index.intersection(market.index)
    window, market = window.loc[common_dates], market.loc[common_dates]

    market_var = market.var(ddof=0)
    betas = window.apply(lambda col: col.cov(market) / market_var if market_var > 0 else np.nan)
    predicted = pd.DataFrame(np.outer(market.values, betas.values), index=window.index, columns=window.columns)
    residuals = window - predicted
    idio_vol = residuals.std(ddof=0) * np.sqrt(252)
    return -idio_vol


def downside_vol_factor(log_ret: pd.DataFrame, as_of: pd.Timestamp,
                         window_days: int = 126) -> pd.Series:
    """Volatility computed only from negative-return days, sign-flipped
    like low_vol_factor (a lower downside vol -> higher score).

    Ordinary volatility (low_vol_factor) treats a big up day and a big
    down day as equally "risky" - both add to the standard deviation. But
    an investor only actually suffers from the down days; the up days are
    the whole point of investing. Downside deviation (semi-deviation)
    keeps only the days with a negative return before computing the
    spread, so it targets the specific kind of risk that drives drawdown
    (MDD) rather than volatility in general. Two stocks with identical
    total volatility can have very different downside-vol if one's swings
    are lopsided toward sharp drops and the other's toward sharp rallies.
    """
    window = log_ret.loc[:as_of].tail(window_days)
    downside = window.where(window < 0)
    downside_vol = downside.std(ddof=0) * np.sqrt(252)
    return -downside_vol.fillna(0)


def _safe_get(info: dict, *keys, default=np.nan):
    for k in keys:
        v = info.get(k)
        if v is not None:
            return v
    return default


def fetch_fundamentals(tickers) -> pd.DataFrame:
    """Pull current-snapshot fundamentals from yfinance for the value/quality factors."""
    import yfinance as yf
    rows = []
    for t in tickers:
        try:
            info = yf.Ticker(t).info
        except Exception:
            info = {}
        rows.append({
            "ticker": t,
            "trailing_pe": _safe_get(info, "trailingPE"),
            "price_to_book": _safe_get(info, "priceToBook"),
            "return_on_equity": _safe_get(info, "returnOnEquity"),
            "debt_to_equity": _safe_get(info, "debtToEquity"),
        })
    return pd.DataFrame(rows).set_index("ticker")


def value_factor(fundamentals: pd.DataFrame) -> pd.Series:
    """Value = average z-score of earnings yield (1/P/E) and book yield (1/P/B).

    Yields, not raw ratios: a higher yield is unambiguously "cheaper", so
    both components point the same direction before z-scoring.

    CAVEAT: lookahead bias - see module docstring.
    """
    earnings_yield = 1.0 / fundamentals["trailing_pe"].replace(0, np.nan)
    book_yield = 1.0 / fundamentals["price_to_book"].replace(0, np.nan)
    return pd.concat([zscore(earnings_yield), zscore(book_yield)], axis=1).mean(axis=1)


def quality_factor(fundamentals: pd.DataFrame) -> pd.Series:
    """Quality = average z-score of ROE (higher better) and -D/E (lower leverage better).

    CAVEAT: lookahead bias - see module docstring.
    """
    roe = fundamentals["return_on_equity"]
    neg_leverage = -fundamentals["debt_to_equity"]
    return pd.concat([zscore(roe), zscore(neg_leverage)], axis=1).mean(axis=1)


def composite_score(factor_series: dict, weights: dict) -> pd.Series:
    """Z-score every factor cross-sectionally, then blend into one score
    via a weighted average. factor_series and weights must share keys.

    Generalized (as of the lookahead-free factor set work) to take any
    named set of factors rather than a fixed four - see
    portfolio.FACTOR_SETS for the two variants currently in use.
    """
    z = {name: zscore(s) for name, s in factor_series.items()}
    df = pd.DataFrame(z)
    composite = sum(df[k] * w for k, w in weights.items())
    return composite.dropna(how="all")
