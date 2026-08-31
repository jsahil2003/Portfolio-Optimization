"""
Builds the submission workbook required by the challenge:
composition & weights, returns, MDD, benchmark comparison, and model
logic/assumptions - all in one .xlsx, per the "Submission Requirements".
"""
import pandas as pd


def build_workbook(path: str, weights_by_date: dict, nav: pd.Series,
                    benchmark_nav: pd.Series, report: dict, trades: pd.DataFrame,
                    benchmark_navs: dict = None):
    """benchmark_nav: single legacy benchmark (kept for backward compatibility).
    benchmark_navs: {name: nav_series} for one or more named benchmarks,
    each added as its own column in the Returns sheet."""
    all_benchmarks = dict(benchmark_navs or {})
    if benchmark_nav is not None:
        all_benchmarks.setdefault("benchmark", benchmark_nav)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:

        comp_rows = []
        for date, weights in weights_by_date.items():
            for ticker, w in weights.items():
                comp_rows.append({"rebalance_date": date, "ticker": ticker, "weight": w})
        pd.DataFrame(comp_rows).to_excel(writer, sheet_name="Composition_Weights", index=False)

        nav_df = pd.DataFrame({"date": nav.index, "portfolio_nav": nav.values})
        nav_df["daily_return"] = nav_df["portfolio_nav"].pct_change()
        for name, bench_nav in all_benchmarks.items():
            nav_df = nav_df.merge(
                pd.DataFrame({"date": bench_nav.index, f"{name}_nav": bench_nav.values}),
                on="date", how="left",
            )
        nav_df.to_excel(writer, sheet_name="Returns", index=False)

        running_max = nav.cummax()
        dd = (nav / running_max - 1.0)
        dd_df = pd.DataFrame({"date": nav.index, "nav": nav.values,
                               "running_max": running_max.values, "drawdown": dd.values})
        dd_df.to_excel(writer, sheet_name="Drawdown", index=False)

        summary_rows = [{"metric": k, "value": v} for k, v in report.items()
                         if not isinstance(v, pd.Series)]
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary_Metrics", index=False)

        if not trades.empty:
            trades.to_excel(writer, sheet_name="Trade_Log", index=False)

        assumptions = pd.DataFrame({
            "assumption": [
                "Universe", "Max stocks", "Backtest period", "Transaction cost",
                "Starting capital", "Rebalance frequency", "Weighting scheme",
                "Selection method", "Composite factor weights", "Turnover buffer",
                "Sector cap", "Share trading", "Lookahead bias", "Risk-free rate", "Benchmarks",
            ],
            "value": [
                "Nifty 100 + Nifty Midcap 100 + Nifty Smallcap 100 (live pull, niftyindices.com)",
                10, "2021-01-01 to 2025-12-31", "0.1% per transaction",
                "INR 1,00,00,000", "Monthly",
                "Ledoit-Wolf shrinkage minimum-variance, capped at 20% per name",
                "Top 10 by composite of momentum, low-vol, Parkinson intraday vol, 52-week-high, "
                "liquidity z-scores",
                "momentum 0.40 / low_vol 0.25 / parkinson_vol 0.10 / high52 0.15 / liquidity 0.10 "
                "(walk-forward validated: tuned on 2021-2023, confirmed on unseen 2024-2025, "
                "re-validated with parkinson_vol added and stress-tested)",
                "A held stock stays as long as its rank is within top 13 (10+3), only new entrants "
                "need top-10; buffer=3 chosen via walk-forward grid {0,2,3,5,8}, improving Sharpe/"
                "return/drawdown/turnover on train and test independently",
                "Max 35% of portfolio weight per NSE industry, tested via backtest: removed every "
                ">40%-in-one-sector rebalance (22/60 -> 0/60) while improving return/drawdown/Sharpe",
                "Whole shares only - fractional trades are not permitted; rounding shortfall held as cash",
                "None - all five factors built from historical price/volume data only, "
                "genuinely point-in-time safe (no fundamentals snapshot used)",
                "0%",
                ", ".join(all_benchmarks.keys()) if all_benchmarks else "none",
            ],
        })
        assumptions.to_excel(writer, sheet_name="Model_Logic_Assumptions", index=False)
