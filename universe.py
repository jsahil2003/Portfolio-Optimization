"""
Investment universe: live pull of Nifty 100, Nifty Midcap 100, and Nifty
Smallcap 100 constituents directly from niftyindices.com - the official
source, so this always reflects the current index composition rather than
a hand-typed snapshot that goes stale when NSE Indices rebalances (twice a
year, Mar/Sep).

Falls back to a local CSV cache (universe_cache.csv, next to this file) if
niftyindices.com is unreachable - constituents only change twice a year,
so a recent cache is a reasonable fallback. Before a real submission,
re-run with network access and check universe_cache.csv's freshness -
grep it for a stock you know was recently added/removed from an index.
"""
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

CACHE_PATH = Path(__file__).parent / "universe_cache.csv"

# niftyindices.com's own file-naming convention for each index's constituent CSV.
INDEX_FILES = {
    "nifty100": "nifty100",
    "midcap100": "niftymidcap100",
    "smallcap100": "niftysmallcap100",
}


def get_index_constituents(index_name: str) -> pd.DataFrame:
    """Pull the live constituent list for one NSE index (e.g. 'nifty100')."""
    url = f"https://niftyindices.com/IndexConstituent/ind_{index_name}list.csv"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return pd.read_csv(StringIO(resp.text))


def load_universe(cache_path: Path = CACHE_PATH) -> pd.DataFrame:
    """Fetch all three index constituent lists live, tag each row with its
    source index, and cache the combined result to disk. Falls back to the
    cache if the live pull fails (e.g. no network) and a cache exists.
    """
    try:
        frames = []
        for universe_label, index_file in INDEX_FILES.items():
            df = get_index_constituents(index_file)
            df["universe"] = universe_label
            frames.append(df)
        combined = pd.concat(frames, ignore_index=True)
        combined.to_csv(cache_path, index=False)
    except Exception as live_pull_error:
        if not cache_path.exists():
            raise RuntimeError(
                f"Live pull from niftyindices.com failed ({live_pull_error}) "
                f"and no cache found at {cache_path}."
            ) from live_pull_error
        combined = pd.read_csv(cache_path)

    combined["ticker"] = combined["Symbol"].str.strip() + ".NS"
    return combined


def _tickers_for(universe_df: pd.DataFrame, label: str) -> list:
    return sorted(universe_df.loc[universe_df["universe"] == label, "ticker"].unique())


_universe_df = load_universe()

NIFTY100_TICKERS = _tickers_for(_universe_df, "nifty100")
NIFTY_MIDCAP_100_TICKERS = _tickers_for(_universe_df, "midcap100")
NIFTY_SMALLCAP_100_TICKERS = _tickers_for(_universe_df, "smallcap100")

FULL_UNIVERSE = sorted(set(
    NIFTY100_TICKERS + NIFTY_MIDCAP_100_TICKERS + NIFTY_SMALLCAP_100_TICKERS
))

# Ticker -> NSE industry classification, from the same niftyindices.com pull
# (not a live fundamentals snapshot, so no lookahead-bias concern). Used by
# portfolio.py to keep the composite-score picks from concentrating in one
# sector.
INDUSTRY_BY_TICKER = _universe_df.drop_duplicates("ticker").set_index("ticker")["Industry"]
