"""
Two portfolio-weighting schemes that use the full covariance/correlation
structure between stocks, instead of treating each stock's risk as
independent the way inverse-vol weighting (portfolio.py) does:

    ledoit_wolf_weights() - shrinkage-covariance minimum-variance
    hrp_weights()         - Hierarchical Risk Parity

See CONCEPTS.md sections 20-22 for the full math and intuition, and
BEGINNERS_GUIDE.md for a plain-language walkthrough. CHANGELOG.md has the
head-to-head comparison against the inverse-vol default.
"""
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, dendrogram
from scipy.spatial.distance import squareform
from sklearn.covariance import LedoitWolf


def _returns_window(log_ret: pd.DataFrame, tickers: list, as_of: pd.Timestamp,
                     window_days: int) -> pd.DataFrame:
    window = log_ret.loc[:as_of, tickers].tail(window_days).dropna(axis=1, how="any")
    return window


# ============================================================
# Ledoit-Wolf shrinkage minimum-variance
# ============================================================

def ledoit_wolf_cov(returns_window: pd.DataFrame) -> pd.DataFrame:
    """Shrinkage-estimated covariance matrix (Ledoit & Wolf, 2004).

    The raw sample covariance matrix, estimated from ~126 days of returns
    for ~10 stocks, is noisy - off-diagonal (cross-stock) entries in
    particular are unreliable with that little data. Ledoit-Wolf shrinkage
    blends the noisy sample covariance toward a well-conditioned target
    (a scaled identity matrix), controlled by a shrinkage intensity the
    method picks automatically to minimize expected estimation error. The
    result is less extreme, more stable, and safe to invert - which the
    plain sample covariance often is not.
    """
    lw = LedoitWolf().fit(returns_window.values)
    return pd.DataFrame(lw.covariance_, index=returns_window.columns, columns=returns_window.columns)


def _min_variance_from_cov(cov: pd.DataFrame, max_weight: float = 1.0) -> pd.Series:
    """Closed-form long-only-ish minimum-variance weights: w ∝ Σ^-1 · 1.

    This is the textbook unconstrained min-variance solution (minimizes
    w'Σw subject to Σw=1, no bound on individual weights). Any negative
    weights it produces are clipped to 0 and the rest renormalized - a
    common, simple way to approximate the long-only-constrained solution
    without a full quadratic-programming solver. Then capped the same way
    as inverse-vol weighting, for the same concentration-control reason.
    """
    tickers = cov.index
    inv_cov = np.linalg.pinv(cov.values)
    ones = np.ones(len(tickers))
    raw = inv_cov @ ones
    w = pd.Series(raw, index=tickers)

    w = w.clip(lower=0)
    if w.sum() <= 0:
        # Degenerate case (e.g. all-negative solution) - fall back to equal weight.
        return pd.Series(1.0 / len(tickers), index=tickers)
    w = w / w.sum()

    from portfolio import cap_weights
    return cap_weights(w, max_weight=max_weight)


def ledoit_wolf_weights(log_ret: pd.DataFrame, tickers: list, as_of: pd.Timestamp,
                         window_days: int = 126, max_weight: float = 0.20) -> pd.Series:
    """Minimum-variance weights using a Ledoit-Wolf shrinkage covariance
    matrix instead of the raw sample covariance. Uses correlations between
    stocks (unlike inverse-vol weighting), while shrinkage keeps the
    matrix well-behaved enough to actually invert safely."""
    window = _returns_window(log_ret, tickers, as_of, window_days)
    if window.shape[1] < 2:
        return pd.Series(1.0, index=window.columns) if window.shape[1] == 1 else pd.Series(dtype=float)
    cov = ledoit_wolf_cov(window)
    return _min_variance_from_cov(cov, max_weight=max_weight)


# ============================================================
# Hierarchical Risk Parity (Lopez de Prado, 2016)
# ============================================================

def _correlation_distance(corr: pd.DataFrame) -> pd.DataFrame:
    """Turn a correlation matrix into a proper distance metric.

    Correlation ranges [-1, 1] and isn't a distance (perfectly correlated
    stocks should have distance 0, uncorrelated stocks should be far
    apart) - this transform, standard in the HRP literature, produces a
    real Euclidean-compatible distance from correlation.
    """
    return np.sqrt(0.5 * (1 - corr))


def _quasi_diagonalize(link: np.ndarray) -> list:
    """Recover the leaf order from a hierarchical clustering linkage
    matrix, i.e. reorder assets so similar (highly correlated) ones sit
    next to each other - the "quasi-diagonalization" step of HRP.
    Equivalent to reading a dendrogram's leaves left to right."""
    dendro = dendrogram(link, no_plot=True)
    return dendro["leaves"]


def _cluster_variance(cov: pd.DataFrame, cluster_items: list) -> float:
    """Variance of an inverse-variance-weighted sub-portfolio made only of
    the assets in one cluster - used to compare the risk of a cluster's
    two children during recursive bisection."""
    sub_cov = cov.loc[cluster_items, cluster_items]
    inv_diag = 1.0 / np.diag(sub_cov.values)
    weights = inv_diag / inv_diag.sum()
    return float(weights @ sub_cov.values @ weights)


def _recursive_bisection(cov: pd.DataFrame, sorted_tickers: list) -> pd.Series:
    """Allocate risk top-down: split the ordered list of tickers into two
    halves, size each half inversely to its own variance (the riskier half
    gets less), then recurse into each half. This never touches the
    off-diagonal covariance terms directly during allocation - only
    through which assets end up clustered together - which is what makes
    HRP stable even when the covariance matrix itself is noisy or singular
    (unlike Ledoit-Wolf min-variance, HRP never inverts a matrix at all).
    """
    weights = pd.Series(1.0, index=sorted_tickers)
    clusters = [sorted_tickers]

    while clusters:
        clusters = [c[start:end] for c in clusters
                    for start, end in ((0, len(c) // 2), (len(c) // 2, len(c)))
                    if len(c) > 1]
        for i in range(0, len(clusters), 2):
            if i + 1 >= len(clusters):
                continue
            left, right = clusters[i], clusters[i + 1]
            var_left = _cluster_variance(cov, left)
            var_right = _cluster_variance(cov, right)
            alloc_left = 1 - var_left / (var_left + var_right)
            weights[left] *= alloc_left
            weights[right] *= (1 - alloc_left)

    return weights / weights.sum()


def hrp_weights(log_ret: pd.DataFrame, tickers: list, as_of: pd.Timestamp,
                window_days: int = 126, max_weight: float = 0.20) -> pd.Series:
    """Hierarchical Risk Parity weights (Lopez de Prado, 2016): cluster
    stocks by correlation, order them by that clustering, then allocate
    risk top-down via recursive bisection. Uses correlation structure like
    Ledoit-Wolf min-variance, but never inverts the covariance matrix -
    generally more robust to estimation noise as a result.
    """
    window = _returns_window(log_ret, tickers, as_of, window_days)
    if window.shape[1] < 2:
        return pd.Series(1.0, index=window.columns) if window.shape[1] == 1 else pd.Series(dtype=float)

    cov = window.cov()
    corr = window.corr()
    dist = _correlation_distance(corr)
    condensed = squareform(dist.values, checks=False)
    link = linkage(condensed, method="single")

    sorted_tickers = [dist.columns[i] for i in _quasi_diagonalize(link)]
    weights = _recursive_bisection(cov, sorted_tickers)

    from portfolio import cap_weights
    return cap_weights(weights, max_weight=max_weight)
