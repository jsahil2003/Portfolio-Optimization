"""
Backtest engine: simulates holding the quarterly-rebalanced portfolio from
portfolio.py against real daily prices, charging 0.1% transaction cost on
every trade. Produces a daily NAV series and a trade log for the metrics
in metrics.py. See CONCEPTS.md for the simulation logic and cost model.
"""
import numpy as np
import pandas as pd

TXN_COST = 0.001  # 0.1% per transaction, per the challenge rules


def run_backtest(prices: pd.DataFrame, weights_by_date: dict,
                  capital: float = 1_00_00_000, txn_cost: float = TXN_COST):
    """Simulate the portfolio day by day.

    Returns:
        nav: pd.Series, daily portfolio value
        trades: pd.DataFrame, one row per executed trade (for turnover/trade stats)
        holdings_log: pd.DataFrame, shares held per ticker after each rebalance
    """
    rebalance_dates = sorted(weights_by_date.keys())
    dates = prices.index[(prices.index >= rebalance_dates[0]) & (prices.index <= prices.index.max())]

    shares = pd.Series(dtype=float)
    cash = capital
    nav = pd.Series(index=dates, dtype=float)
    trade_rows = []
    holdings_rows = []

    for day in dates:
        day_prices = prices.loc[day]

        if day in weights_by_date:
            target_weights = weights_by_date[day]
            current_value = cash + (shares * day_prices.reindex(shares.index)).fillna(0).sum()
            all_tickers = sorted(set(shares.index) | set(target_weights.index))

            current_shares = shares.reindex(all_tickers).fillna(0.0)
            target_shares = pd.Series(0.0, index=all_tickers)
            for t in target_weights.index:
                px = day_prices.get(t, np.nan)
                if pd.notna(px) and px > 0:
                    target_shares[t] = (current_value * target_weights[t]) / px

            trade_shares = target_shares - current_shares
            trade_shares = trade_shares[trade_shares.abs() > 1e-9]

            total_cost = 0.0
            for t, delta in trade_shares.items():
                px = day_prices.get(t, np.nan)
                if pd.isna(px):
                    continue
                trade_value = abs(delta) * px
                cost = trade_value * txn_cost
                total_cost += cost
                trade_rows.append({
                    "date": day, "ticker": t, "side": "BUY" if delta > 0 else "SELL",
                    "shares": delta, "price": px, "trade_value": trade_value, "cost": cost,
                })

            cash = current_value - (target_shares.reindex(target_weights.index) * day_prices.reindex(target_weights.index)).sum() - total_cost
            shares = target_shares
            holdings_rows.append({"date": day, **shares[shares.abs() > 1e-9].to_dict()})

        portfolio_value = cash + (shares * day_prices.reindex(shares.index)).fillna(0).sum()
        nav.loc[day] = portfolio_value

    trades = pd.DataFrame(trade_rows)
    holdings_log = pd.DataFrame(holdings_rows).set_index("date") if holdings_rows else pd.DataFrame()
    return nav, trades, holdings_log
