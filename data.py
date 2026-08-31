"""
Data pipeline: download historical prices for an Indian equity universe,
compute log returns, and do basic sanity checks.
"""
import numpy as np
import pandas as pd
# yfinance imported lazily inside download_prices() so the rest of this module
# (cleaning/sanity-check functions) can be used/tested without it installed.

# Nifty 50 constituents (verified Aug 2026 - 48 confirmed; recheck against
# niftyindices.com before finalizing, since composition is reviewed twice yearly).
# Note: excludes Tata Motors post-demerger pending yfinance ticker confirmation.
NIFTY50_TICKERS = [
    "RELIANCE.NS", "BHARTIARTL.NS", "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS",
    "TCS.NS", "BAJFINANCE.NS", "LT.NS", "HINDUNILVR.NS", "INFY.NS",
    "SUNPHARMA.NS", "MARUTI.NS", "TITAN.NS", "M&M.NS", "ADANIENT.NS",
    "KOTAKBANK.NS", "ADANIPORTS.NS", "AXISBANK.NS", "HCLTECH.NS", "ITC.NS",
    "ULTRACEMCO.NS", "NTPC.NS", "BAJAJFINSV.NS", "BAJAJ-AUTO.NS", "JSWSTEEL.NS",
    "ETERNAL.NS", "ONGC.NS", "BEL.NS", "SHRIRAMFIN.NS", "ASIANPAINT.NS",
    "COALINDIA.NS", "POWERGRID.NS", "HINDALCO.NS", "TATASTEEL.NS", "GRASIM.NS",
    "EICHERMOT.NS", "INDIGO.NS", "SBILIFE.NS", "WIPRO.NS", "JIOFIN.NS",
    "TECHM.NS", "TRENT.NS", "APOLLOHOSP.NS", "CIPLA.NS", "HDFCLIFE.NS",
    "TATACONSUM.NS", "MAXHEALTH.NS", "DRREDDY.NS",
]

# Smaller 20-name subset for faster iteration during development
DEFAULT_UNIVERSE = NIFTY50_TICKERS[:20]


def _download_ohlcv_raw(tickers, start, end=None, chunk_size=50):
    """Batch-download OHLCV, chunked and retried per-ticker.

    A single giant yf.download() call over a large universe silently drops
    some tickers under load/rate-limiting - they come back as "possibly
    delisted; no price data found" even though the ticker has real,
    fetchable history (confirmed by re-requesting them individually).
    Chunking bounds the blast radius of one bad batch, and any ticker still
    missing after that gets retried individually with a backoff delay - an
    immediate retry hits the same rate limit that caused the drop, so it
    needs a moment to clear first.
    """
    import time
    import yfinance as yf

    tickers = list(tickers)
    chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]
    frames = [yf.download(chunk, start=start, end=end, auto_adjust=True, progress=False)
              for chunk in chunks]
    combined = pd.concat(frames, axis=1)

    close = combined["Close"]
    missing = [t for t in tickers if t not in close.columns or close[t].dropna().empty]

    for attempt, delay in enumerate([5, 20, 60]):
        if not missing:
            break
        time.sleep(delay)
        still_missing = []
        for t in missing:
            retry = yf.download(t, start=start, end=end, auto_adjust=True, progress=False)
            if retry.empty:
                still_missing.append(t)
                continue
            for field in ["Close", "High", "Low", "Open", "Volume"]:
                if field in retry.columns:
                    combined[(field, t)] = retry[field]
        missing = still_missing

    return combined


def download_prices(tickers=DEFAULT_UNIVERSE, start="2015-01-01", end=None):
    """Download adjusted close prices for the given tickers."""
    return _download_ohlcv_raw(tickers, start=start, end=end)["Close"]


def download_ohlcv(tickers=DEFAULT_UNIVERSE, start="2015-01-01", end=None) -> dict:
    """Download adjusted Close, High, Low, and Volume together.

    Unlike fetch_fundamentals() (a live snapshot from yfinance .info - see
    factors.py's lookahead-bias caveat), this is genuinely point-in-time
    correct: each date's OHLCV reflects only what was observable on that
    date, so any signal built from it (52-week-high proximity, Amihud
    illiquidity, Parkinson range volatility - see factors.py) carries none
    of the lookahead-bias risk that value_factor()/quality_factor() do.

    Returns {"close": df, "high": df, "low": df, "volume": df}, each a
    date x ticker DataFrame.
    """
    raw = _download_ohlcv_raw(tickers, start=start, end=end)
    return {
        "close": raw["Close"],
        "high": raw["High"],
        "low": raw["Low"],
        "volume": raw["Volume"],
    }


def compute_log_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Convert a price panel into daily log returns, dropping the first NaN row."""
    log_ret = np.log(prices / prices.shift(1))
    return log_ret.dropna(how="all")


def flag_suspicious_moves(log_ret: pd.DataFrame, threshold: float = 0.20, market_wide_frac: float = 0.30):
    """
    Distinguish real market-wide events (many assets move together - e.g. a crash)
    from likely corporate-action/data artifacts (one asset moves alone, everything
    else is normal that day - e.g. a demerger, bad ticker rename, or data glitch).

    yfinance auto-adjusts for ordinary splits and dividends, but does NOT correct
    for demergers, mergers, delistings, or ticker renames - those show up here.
    """
    extreme = log_ret.abs() > threshold
    n_assets = log_ret.shape[1]

    daily_extreme_frac = extreme.sum(axis=1) / n_assets
    flagged_dates = daily_extreme_frac[daily_extreme_frac > 0]

    report_rows = []
    for date, frac in flagged_dates.items():
        assets_hit = extreme.columns[extreme.loc[date]].tolist()
        classification = "MARKET-WIDE (likely real event)" if frac >= market_wide_frac \
            else "IDIOSYNCRATIC (investigate - likely corporate action or data error)"
        report_rows.append({
            "date": date, "assets_affected": assets_hit,
            "frac_of_universe": round(frac, 3), "classification": classification,
        })
    return pd.DataFrame(report_rows)


def filter_by_history_length(tickers, min_years=10, max_gap_days=10, start="2010-01-01"):
    """
    Empirically filter to tickers with long, continuous price history - rather than
    trusting a name/reputation to imply stability. This directly operationalizes
    "avoid recent IPOs, demergers, and ticker renames": any of those show up here
    as either a short history or a large gap, with no need to research each
    company's corporate history by hand.

    Returns a DataFrame report; use report[report.passes].index.tolist() for the
    filtered ticker list.
    """
    raw = _download_ohlcv_raw(tickers, start=start)["Close"]

    rows = []
    min_days = int(min_years * 252)
    for ticker in raw.columns:
        series = raw[ticker].dropna()
        n_obs = len(series)
        if n_obs == 0:
            rows.append({"ticker": ticker, "years_available": 0, "max_gap_days": None,
                         "first_date": None, "passes": False, "reason": "no data"})
            continue

        years_available = n_obs / 252
        gaps = series.index.to_series().diff().dt.days.dropna()
        max_gap = gaps.max() if len(gaps) > 0 else 0

        passes = (n_obs >= min_days) and (max_gap <= max_gap_days)
        reason = "OK" if passes else (
            f"only {years_available:.1f}y history" if n_obs < min_days
            else f"gap of {max_gap:.0f} days found (possible suspension/relist)"
        )
        rows.append({
            "ticker": ticker, "years_available": round(years_available, 1),
            "max_gap_days": max_gap, "first_date": series.index.min(),
            "passes": passes, "reason": reason,
        })

    return pd.DataFrame(rows).set_index("ticker")


def sanity_check(prices: pd.DataFrame, log_ret: pd.DataFrame):
    """Basic data-quality checks worth running before trusting anything downstream."""
    report = {}
    report["date_range"] = (prices.index.min(), prices.index.max())
    report["n_assets"] = prices.shape[1]
    report["n_days"] = prices.shape[0]
    report["missing_pct"] = prices.isna().mean().sort_values(ascending=False)
    report["suspicious_moves"] = flag_suspicious_moves(log_ret)
    return report


if __name__ == "__main__":
    print("=== Step 1: Filtering to stocks with >=10 years of clean, continuous history ===")
    history_report = filter_by_history_length(NIFTY50_TICKERS, min_years=10)
    print(history_report.to_string())

    clean_universe = history_report[history_report["passes"]].index.tolist()
    excluded = history_report[~history_report["passes"]]
    print(f"\n{len(clean_universe)}/{len(NIFTY50_TICKERS)} tickers passed the history filter.")
    if len(excluded) > 0:
        print("Excluded (recent IPO, demerger gap, or suspension):")
        print(excluded[["years_available", "reason"]].to_string())

    print("\n=== Step 2: Downloading full price history for the clean universe ===")
    prices = download_prices(tickers=clean_universe)
    log_ret = compute_log_returns(prices)
    report = sanity_check(prices, log_ret)

    print("Date range:", report["date_range"])
    print("Assets:", report["n_assets"], "| Days:", report["n_days"])
    print("\nMissing data %:\n", report["missing_pct"])
    print("\nSuspicious moves (idiosyncratic vs market-wide):\n", report["suspicious_moves"])
