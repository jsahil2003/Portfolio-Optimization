"""
Performance & risk metrics required by the challenge rubric. See CONCEPTS.md
for the formula behind each function and why it measures what it claims to.
"""
import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def daily_returns(nav: pd.Series) -> pd.Series:
    return nav.pct_change(fill_method=None).dropna()


def annualized_return(nav: pd.Series) -> float:
    """Geometric average annual return, compounded from the full-period total return."""
    n_days = len(nav) - 1
    if n_days <= 0:
        return np.nan
    total_return = nav.iloc[-1] / nav.iloc[0]
    years = n_days / TRADING_DAYS_PER_YEAR
    return total_return ** (1 / years) - 1


def max_drawdown(nav: pd.Series) -> float:
    """Largest peak-to-trough decline, as a negative fraction (e.g. -0.23 = -23%)."""
    running_max = nav.cummax()
    drawdown = nav / running_max - 1.0
    return drawdown.min()


def sharpe_ratio(nav: pd.Series, risk_free: float = 0.0) -> float:
    """Annualized Sharpe: annualized mean daily excess return / annualized std dev.
    Risk-free rate is assumed 0%, per the challenge's evaluation spec."""
    rets = daily_returns(nav)
    excess = rets - risk_free / TRADING_DAYS_PER_YEAR
    if excess.std(ddof=0) == 0:
        return np.nan
    return (excess.mean() / excess.std(ddof=0)) * np.sqrt(TRADING_DAYS_PER_YEAR)


def total_net_pnl(nav: pd.Series, starting_capital: float) -> float:
    """The competition's primary ranking metric: final value minus starting capital."""
    return nav.iloc[-1] - starting_capital


def _fifo_round_trip_pnl(trades: pd.DataFrame) -> pd.Series:
    """FIFO-match BUY lots against SELL lots per ticker to realize round-trip P&L.

    Needed because gain-to-loss ratio and accuracy are defined on *closed
    trades*, not on daily NAV moves - and a rebalanced portfolio only
    partially closes/opens positions at each rebalance, so a proper FIFO
    lot matcher is the honest way to get real trade-level P&L.
    """
    realized = []
    for ticker, grp in trades.sort_values("date").groupby("ticker"):
        buy_lots = []  # list of [shares_remaining, price]
        for _, row in grp.iterrows():
            shares = row["shares"]
            price = row["price"]
            if shares > 0:
                buy_lots.append([shares, price])
            else:
                to_close = -shares
                while to_close > 1e-9 and buy_lots:
                    lot_shares, lot_price = buy_lots[0]
                    matched = min(lot_shares, to_close)
                    pnl = matched * (price - lot_price)
                    realized.append(pnl)
                    buy_lots[0][0] -= matched
                    to_close -= matched
                    if buy_lots[0][0] <= 1e-9:
                        buy_lots.pop(0)
    return pd.Series(realized)


def gain_to_loss_ratio(trades: pd.DataFrame) -> float:
    """Average profit of winning round-trip trades / average loss of losing ones."""
    if trades.empty:
        return np.nan
    pnl = _fifo_round_trip_pnl(trades)
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    if len(wins) == 0 or len(losses) == 0:
        return np.nan
    return wins.mean() / abs(losses.mean())


def accuracy(trades: pd.DataFrame) -> float:
    """Fraction of closed round-trip trades that were profitable."""
    if trades.empty:
        return np.nan
    pnl = _fifo_round_trip_pnl(trades)
    if len(pnl) == 0:
        return np.nan
    return (pnl > 0).mean()


def turnover_stats(trades: pd.DataFrame, nav: pd.Series) -> dict:
    """Trade-count and turnover summary for the rubric's 'Trade Statistics' line."""
    if trades.empty:
        return {"total_trades": 0, "trades_per_stock": pd.Series(dtype=int), "avg_turnover_per_rebalance": np.nan}

    trades_per_stock = trades.groupby("ticker").size()
    turnover_by_date = trades.groupby("date")["trade_value"].sum()
    avg_nav = nav.mean()
    avg_turnover = (turnover_by_date / avg_nav).mean()

    return {
        "total_trades": len(trades),
        "trades_per_stock": trades_per_stock,
        "avg_turnover_per_rebalance": avg_turnover,
        "total_transaction_cost": trades["cost"].sum(),
    }


def full_report(nav: pd.Series, trades: pd.DataFrame, starting_capital: float,
                 benchmark_nav: pd.Series = None, benchmark_navs: dict = None) -> dict:
    """benchmark_nav: single legacy benchmark (kept for backward compatibility).
    benchmark_navs: {name: nav_series} for one or more named benchmarks -
    each gets its own annualized_return/max_drawdown/sharpe_ratio/excess_return,
    prefixed by name (e.g. "NIFTY50_annualized_return")."""
    report = {
        "total_net_pnl": total_net_pnl(nav, starting_capital),
        "annualized_return": annualized_return(nav),
        "max_drawdown": max_drawdown(nav),
        "sharpe_ratio": sharpe_ratio(nav),
        "gain_to_loss_ratio": gain_to_loss_ratio(trades),
        "accuracy": accuracy(trades),
    }
    report.update(turnover_stats(trades, nav))

    all_benchmarks = dict(benchmark_navs or {})
    if benchmark_nav is not None:
        all_benchmarks.setdefault("benchmark", benchmark_nav)

    for name, bench_nav in all_benchmarks.items():
        bench_ann_return = annualized_return(bench_nav)
        report[f"{name}_annualized_return"] = bench_ann_return
        report[f"{name}_max_drawdown"] = max_drawdown(bench_nav)
        report[f"{name}_sharpe_ratio"] = sharpe_ratio(bench_nav)
        report[f"{name}_excess_annualized_return"] = report["annualized_return"] - bench_ann_return

    return report
