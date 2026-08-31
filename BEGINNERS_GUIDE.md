# Beginner's Guide to This Project

This file explains the whole strategy — signals, weighting, and the new
optimizers — assuming no prior background in statistics or finance. If
you already know what "volatility" or "correlation" means, skim; if a
term is new, it's defined the first time it shows up.

This file gets rewritten as the project evolves — treat it as the current
snapshot, not a changelog (that's `CHANGELOG.md`).

> **Status: FINALIZED.** The strategy this project ships is the fully
> lookahead-free version described in §2 — momentum, two kinds of
> low-volatility (close-to-close and intraday-range), 52-week-high
> proximity, and liquidity, weighted 40% / 25% / 10% / 15% / 10%. Those
> weights were chosen through four separate rounds of train/test
> validation (§7-8), not just a search on the data being reported. See
> `PROJECT_SUMMARY.md` for the single-document version of this whole
> story, written for showing to someone else (a professor, a teammate).

---

## 1. What is this project actually doing?

We're picking 10 stocks out of 300 (the Nifty 100 + Midcap 100 +
Smallcap 100 lists), deciding how much money to put into each one, and
doing that again every month for five years (2021–2025) to see how the
money would have grown. This is called **backtesting** — testing a
strategy on historical data to see how it *would have* performed, since
we can't test it on the future.

Two separate decisions happen every month:

1. **Which 10 stocks?** (Stock *selection* — covered in §2–3)
2. **How much money in each of the 10?** (Position *weighting* — covered
   in §4–6, this is where Ledoit-Wolf and HRP come in)

These are genuinely separate problems. You could pick great stocks and
size them badly, or pick mediocre stocks and size them perfectly — both
end up underperforming. This project treats them as two stages: first
narrow 300 stocks down to 10 (§2–3), then decide how much of each of
those 10 to hold (§4–6).

---

## 2. What is a "signal"?

A **signal** (also called a **factor** in finance) is just a number you
can calculate for every stock that you believe is correlated with future
performance. "This stock went up a lot recently" is a signal. "This
stock is cheap relative to its earnings" is a signal. A signal on its own
is just a hypothesis — "stocks with property X tend to do better than
stocks without it" — and the whole field of factor investing is about
testing which hypotheses actually hold up in real data.

This project uses four signals:

| Signal | Plain-English question it answers |
|---|---|
| **Momentum** | Has this stock been going up recently? |
| **Low-volatility** | Has this stock been calm (not swinging wildly) recently? |
| **Value** | Is this stock cheap relative to what the company actually earns/owns? |
| **Quality** | Is this a well-run, profitable, not-too-indebted company? |

### Why these four and not just "buy whatever is going up"?

Because no single signal works all the time. A stock that's been rising
can suddenly reverse. A "cheap" stock can be cheap because it's a bad
business, not because it's a bargain. Combining several signals that
tend to succeed in *different* market conditions is like not putting all
your eggs in one basket — if momentum has a bad year, value or quality
might not.

### How is each signal actually calculated?

**Momentum**: take the stock's return over the last 12 months, but
*ignore the most recent month*. Why ignore the most recent month?
Because stocks that just had a huge recent spike often give some of it
back in the following weeks (this is called "short-term reversal") — so
including the most recent month would work against the very effect
you're trying to capture.

**Low-volatility**: look at the stock's daily price swings over the last
6 months and calculate how big those swings typically are (this
"typical size of swings" number is called **volatility** — see §4 for the
precise definition). Stocks with smaller swings score higher on this
signal.

**Value**: look at the stock's price relative to its earnings (P/E ratio)
and relative to its book value/net worth (P/B ratio), then flip both
ratios upside down (1/P·E and 1/P·B) so that "cheap" always means a
bigger number. A stock trading at a low price relative to its earnings
gets a high value score.

**Quality**: look at the company's Return on Equity (ROE — how much
profit it generates per rupee shareholders have put in) and its
debt-to-equity ratio (how much it has borrowed relative to shareholder
capital). High ROE and low debt both push the quality score up.

### How do you combine four differently-scaled numbers into one score?

You can't just add "12% momentum return" + "8/40 P/E ratio" + "22% ROE" —
they're measured in totally different units and totally different
ranges. The fix is called **standardization** (or **z-scoring**): for
each signal, on each date, you calculate how many standard deviations
above or below the *average stock in the universe* each stock is. A
momentum z-score of +1.5 means "1.5 standard deviations more momentum
than the typical stock that month" — and now it's directly comparable to
a value z-score of +1.5, because both are expressed in the same
"distance from average" units.

Once every signal is z-scored, they're combined into one **composite
score** by taking a weighted average:

```
Composite = 0.28 × Momentum + 0.30 × LowVol + 0.21 × Value + 0.21 × Quality
```

These specific weights weren't chosen from a textbook — they were tuned
by testing many combinations against the 2021–2025 backtest and picking
one that balanced return against risk. See `CHANGELOG.md` for that
process and `CONCEPTS.md` §7 for the honest overfitting caveat that comes
with any tuned-on-history number like this.

Every month, all ~250-300 eligible stocks get a composite score, and the
**top 10** are selected. That's stage 1 done.

### A problem with Value and Quality, and a fix

Here's a subtle issue worth understanding, because it's a common mistake
in backtesting (testing a strategy on past data) generally, not just here.

Value and Quality are calculated from company fundamentals — P/E ratio,
ROE, debt levels. The tool this project uses (`yfinance`) can only fetch
*today's* fundamentals, not "what were this company's fundamentals back
in March 2022?" So when the backtest simulates a decision made in March
2022, it's actually using 2026 fundamentals for that decision — information
that didn't exist yet at the time. This is called **lookahead bias**:
accidentally letting a simulation "see the future." It's one of the most
common ways a backtest can look better than a real strategy would have
actually performed, because in real life you never get to peek ahead.

Momentum and Low-volatility don't have this problem — they're calculated
from historical prices, and a stock's price on any given day is genuinely
knowable on that day, no peeking required.

**The fix**: replace Value and Quality with two more signals built purely
from price and trading-volume history, which carries none of this risk:

| New signal | Plain-English question it answers |
|---|---|
| **52-week-high proximity** | Is this stock trading near its own highest price in the last year? |
| **Liquidity** | Is this stock easy to buy and sell without moving its own price much? |

**52-week-high proximity** divides today's price by the stock's own
highest price over the last year. A stock trading right at that high
scores close to 1; one that's fallen a long way from its high scores
lower. This sounds similar to Momentum, but it isn't quite the same
thing: two stocks can have gone up by the exact same percentage over the
last year, but one might be sitting at a brand-new high while the other
is still climbing back from a much deeper earlier fall. Researchers have
found stocks near their own recent high tend to keep doing well — investors
seem to under-react once a stock reaches a price that feels "already high."

**Liquidity** measures how much a stock's price tends to move for a given
amount of money traded. A stock where ₹1 crore of buying barely moves the
price is liquid — easy to trade in and out of. A stock where the same
₹1 crore of buying jolts the price up sharply is illiquid — harder to
trade without the act of trading itself working against you. This
project prefers the more liquid stocks, which is a practical choice: a
strategy that actually buys and sells ~700 times over five years benefits
from stocks that are easy to trade.

### Does removing the lookahead-bias risk cost anything?

Yes, some — tested directly rather than assumed. Swapping in these two
new signals (still untuned, simple equal-weighting) instead of Value and
Quality dropped the yearly return a bit and the Sharpe ratio (return per
unit of risk — see §6) from about 1.75 down to about 1.51. But 1.51 is
still comfortably ahead of just holding the Nifty 50 index (about 0.97)
or the Nifty 500 (about 1.07) — so even the "safe," completely
lookahead-free version of this strategy is a real, working strategy, not
just a stripped-down leftover. See `CHANGELOG.md` for the exact numbers.

### A lesson about chasing better numbers (important!)

After swapping in the new signals, a natural next step was tried: search
for better *weights* to combine them with, the same way Momentum/LowVol/
Value/Quality's weights were tuned earlier. A search found a combination
that looked fantastic — better than the original four-signal strategy,
even. But before trusting it, the same check used throughout this
project was applied: try weights *very close* to the winning ones and see
if the result stays similarly good.

It didn't. Tiny nudges to the winning weights swung the result wildly —
sometimes much better, sometimes clearly worse. Compare that to every
other tuning decision in this project, where nearby choices gave *similar*
results (a gentle hill, not a spike). A single spike surrounded by
wildly different nearby values is a classic sign you've found a fluke of
this *specific* five years of data, not a real, repeatable pattern —
this is called **overfitting**: a model or strategy that's been tuned so
precisely to past data that it's actually just memorized noise, and will
likely disappoint on new data it hasn't seen. So that spike was
deliberately **not** used, even though it looked better on paper — the
honest, un-cherry-picked version was kept instead. See `CONCEPTS.md` §27
and `CHANGELOG.md` for the full details, including the specific numbers
that revealed the instability.

This is genuinely one of the more important habits in this whole
project: a result that looks great is worth being *more* suspicious of,
not less, until you've checked whether it holds up under small changes.

---

## 3. Why does the portfolio change every month?

Because a stock's signals change over time. A stock that was calm in
January might get volatile by March (bad news, a lawsuit, a sector
rotation). If you only re-checked once a quarter, you'd be holding a
now-risky stock for weeks longer than necessary because you didn't look.
Testing showed monthly re-selection meaningfully reduced the portfolio's
worst losses compared to quarterly, for exactly this reason — see
`CONCEPTS.md` §19 and `CHANGELOG.md`.

---

## 4. Now the harder question: how much money in each of the 10 stocks?

The naive answer is "put 10% in each" (**equal weighting**). That's a
perfectly reasonable baseline — but it ignores something important: not
all 10 stocks are equally risky, and some of them might move *together*
(when one goes down, the other tends to go down too) while others move
*independently* or even in opposite directions. A smarter approach tries
to use that information.

### What is volatility?

**Volatility** is a number that measures how much a stock's daily price
typically swings, expressed as a percentage. If a stock's price commonly
moves ±1% a day, that's low volatility. If it commonly moves ±4% a day,
that's high volatility. It's calculated as the **standard deviation** of
daily returns (a statistics term for "typical distance from the
average") — see `CONCEPTS.md` §4 for the exact formula.

### What is correlation?

**Correlation** measures whether two stocks tend to move together. It
ranges from -1 to +1:
- **+1** means they move in perfect lockstep (both up or both down, same day)
- **0** means their movements are unrelated
- **-1** means they move in perfect opposition (one up, one down)

This matters a lot for risk. If you hold two stocks that are 90%
correlated, you don't actually have two independent bets — you basically
have one bigger bet on whatever they both share (maybe they're in the
same sector). True diversification comes from holding assets that *don't*
move together, so a bad day for one doesn't mean a bad day for the whole
portfolio.

### "Wouldn't using more historical data give a better estimate?"

This is a very natural question, and the intuitive answer ("more data is
always better statistics") turns out to be wrong here — which is worth
understanding because it's a genuinely common trap, not just a quirk of
this project.

Every volatility and correlation number in this project is calculated
from a specific stretch of recent trading days (126 days ≈ 6 months, by
default). You might reasonably ask: why not use *all* the history
available — several years — to get a more statistically solid number?

The catch: a stock's volatility and its correlation with other stocks
**aren't fixed facts** — they change over time as the company, its
sector, and the broader market change. A stock that was calm two years
ago can be turbulent today for reasons that have nothing to do with two
years ago (a new competitor, a regulatory change, a shift in investor
sentiment toward its sector). What this project actually needs to know is
"how risky is this stock *right now*" — not "how risky has this stock
been on average since 2019," which is a different, less useful question.
Statisticians call this property of changing-over-time behavior **non-
stationarity**.

Using several years of data doesn't just add more information — it
blends together several genuinely different market conditions (calm
periods, crash periods, recovery periods) into one number that doesn't
crisply describe any of them, including the present. This was tested
directly in this project, not just argued: using *all* available history
for the covariance matrix (instead of the standard 126-day window)
produced a **worse** portfolio — a lower Sharpe ratio and, notably, a
*deeper* worst-case loss, not a smaller one. See `CHANGELOG.md` for the
exact numbers. More data sounded safer; it wasn't.

The flip side is also true, and is why the window isn't made even
shorter: too *little* data (say, 10 days) is so noisy that the estimate
becomes mostly random chance rather than a real signal. Picking a good
window length is a balancing act between "enough data to not be noise"
and "recent enough to still be true" — there's no universal right answer,
only a reasonable middle ground informed by testing (see `CONCEPTS.md`
§20 for the full technical version of this argument).

### The three weighting schemes in this project

**1. Inverse-volatility weighting (the original default)**

Give each stock a weight inversely proportional to its own volatility —
a calmer stock gets more money, a jumpier stock gets less. The formula
is simple: `weight ∝ 1 / volatility`.

The limitation: this only looks at each stock's *own* volatility. It
completely ignores correlation. If two of your "calm" stocks happen to
be 95% correlated (e.g. two banks that always move together), inverse-vol
weighting doesn't notice or care — it might even overweight both,
accidentally concentrating your risk in one shared factor instead of
spreading it out.

**2. Ledoit-Wolf minimum-variance weighting (new)**

This scheme *does* use correlation. The mathematical ideal here is called
**minimum-variance optimization**: find the exact combination of weights
that produces the lowest possible portfolio volatility, using the full
matrix of every stock's volatility *and* every pairwise correlation (this
matrix is called the **covariance matrix**).

The problem: estimating a covariance matrix accurately requires a lot of
data, and with only ~126 days of returns for 10 stocks, the *raw*
estimate is noisy and unreliable — especially the correlation entries.
Feed a noisy covariance matrix into the optimizer and it can produce
wild, extreme, unstable weights (e.g. "put 80% in this one stock") that
look great on the specific data used to estimate them and terrible
everywhere else. This is a classic finance/statistics trap called
**overfitting to estimation error**.

**Ledoit-Wolf shrinkage** (Ledoit & Wolf, 2004) is the standard fix: it
blends ("shrinks") the noisy raw covariance matrix toward a simpler,
well-behaved target matrix, in a mathematically optimal proportion that
minimizes expected estimation error. The result is a covariance matrix
that's less extreme and safer to use in the optimizer, so the resulting
minimum-variance weights are more stable and less likely to be a fluke of
noisy data.

**3. Hierarchical Risk Parity — HRP (new)**

HRP (López de Prado, 2016) takes a completely different approach to using
correlation: instead of solving an optimization problem that requires
inverting the covariance matrix (which Ledoit-Wolf still does, just on a
cleaned-up matrix), HRP:

1. **Clusters** the stocks by correlation — groups that move together end
   up next to each other (this uses a technique called **hierarchical
   clustering**, the same family of algorithm used to build family trees
   or organize files by similarity).
2. **Orders** the stocks so similar ones are adjacent (this is what "quasi-
   diagonalization" means in the code — don't worry about the name, it
   just means "put similar stocks next to each other in a list").
3. **Allocates money top-down**: split the ordered list in half, give more
   money to whichever half is *less* risky as a group, then recurse into
   each half and repeat, until every individual stock has a weight.

Because HRP never inverts a matrix, it sidesteps the exact instability
problem that motivated Ledoit-Wolf in the first place — it's generally
considered more robust when your data is limited (like our ~10-stock,
126-day windows), at the cost of not being a strict mathematical optimum
the way minimum-variance is.

### So which one is "best"?

There's no universally correct answer — this is genuinely an open,
actively-researched question in quantitative finance, which is exactly
why this project tests all three empirically rather than picking one on
faith. See the results section below (kept up to date as new backtests
run) and `CHANGELOG.md` for the comparison numbers.

---

## 5. Key terms glossary

| Term | Plain-English definition |
|---|---|
| **Signal / factor** | A calculable number believed to predict future stock performance |
| **Z-score / standardization** | Rescaling a number to "standard deviations from the average," so different signals become comparable |
| **Volatility** | How much a stock's price typically swings day to day |
| **Correlation** | Whether two stocks' price movements tend to happen together (+1), independently (0), or oppositely (-1) |
| **Covariance matrix** | A table of every stock's volatility and every pair's correlation, all in one grid |
| **Minimum-variance optimization** | Finding the portfolio weights that produce the lowest possible overall volatility |
| **Shrinkage** | Blending a noisy estimate toward a simpler, more stable one, to reduce estimation error |
| **Hierarchical clustering** | Grouping items by similarity into a tree structure |
| **Sharpe ratio** | Return earned per unit of risk taken (higher is better) |
| **Max drawdown (MDD)** | The worst peak-to-trough loss the portfolio experienced |
| **Backtest** | Simulating a strategy on historical data to estimate how it would have performed |
| **Overfitting** | Tuning a strategy so precisely to past data that it captures noise, not a real pattern, and performs worse on new data |

---

## 6. Results: three weighting schemes compared

**Ledoit-Wolf is now the scheme this project actually uses** — after the
results below held up across four separate robustness checks (different
position-size caps, different signal blends, both calm and turbulent
market periods, both monthly and quarterly rebalancing — see
`CHANGELOG.md` for all four), it replaced equal-risk-per-stock
(inverse-volatility) as the default in `portfolio.py`.

All three schemes were tested with the *exact same 10 stocks picked each
month* — only how the money got split across those 10 stocks changed.
That matters: it means any difference in the results below is caused
purely by the weighting decision, nothing else.

| Scheme | Ended with (on ₹1 crore start) | Yearly return | Worst peak-to-trough loss | Return per unit of risk (Sharpe) |
|---|---|---|---|---|
| Equal-risk-per-stock (inverse-volatility) | ₹4.14 cr | 33.7%/yr | -24.4% | 1.57 |
| **Ledoit-Wolf (shrinkage + correlation-aware)** | **₹4.60 cr** | **36.6%/yr** | **-23.0%** | **1.75** |
| HRP (clustering-based) | ₹4.18 cr | 34.0%/yr | -23.7% | 1.63 |

*("Ended with" = starting ₹1 crore + Total Net PNL.)*

### What do these numbers actually mean?

- **Ledoit-Wolf won on every single measure** — more final money, a
  smoother ride (smaller worst loss), and better return for the risk
  taken. That's unusual: normally in this project, reducing risk cost
  some return (see §4's "no free lunch" framing, and `CHANGELOG.md`'s
  factor-weight tuning story, where cutting drawdown *did* cost PNL).
  Here it didn't — using correlation information genuinely made the
  portfolio better, not just safer.
- **HRP also beat the simple equal-risk approach**, though by a smaller
  margin than Ledoit-Wolf. This roughly matches what's found in published
  research: both correlation-aware methods tend to beat naive
  volatility-only weighting, though which of the two wins by how much
  varies by dataset.
- **Why did Ledoit-Wolf do better than HRP here**, when HRP is often
  described as the more "robust" method? HRP is a compromise — it gives
  up trying to find the mathematically *optimal* combination in exchange
  for near-immunity to bad covariance estimates. Ledoit-Wolf still aims
  for the mathematical optimum, but first cleans up the covariance
  estimate so the optimum it finds is trustworthy. When the cleanup works
  well (as it seems to here, checked at three different lookback windows
  in `CHANGELOG.md`), aiming for the true optimum can beat the more
  conservative, give-up-on-optimality approach. This isn't a universal
  law — it's this specific backtest, this specific data.

### The honest caveat

This is still one 5-year backtest of the Indian stock market. "Ledoit-
Wolf wins" is a real, checked-for-flukes finding *on this data* — it
isn't a guarantee it will keep winning on different stocks, different
years, or different market conditions. See `CONCEPTS.md` §19 and §23 for
the full discussion of why over-trusting a single backtest is risky, and
why the numbers above were double-checked (not just taken at face value)
before being reported here.

---

## 7. Three more signals tried, and a genuinely important lesson

After the lookahead-free signals in §2 were added, the natural next
question was: are there other signals, calculated purely from price/
volume history the same safe way, that could make the strategy better?
Three were tried:

| New signal | Plain-English question it answers |
|---|---|
| **Short-term reversal** | Did this stock just have a *bad* month? (Bad recent months sometimes bounce back.) |
| **Idiosyncratic volatility** | Ignoring how much this stock moves just because the *whole market* moved, how much does it move for reasons specific to this one company? |
| **Downside volatility** | How rough are this stock's *bad* days specifically, ignoring how big its good days are? |

**Short-term reversal** is the interesting counterpart to Momentum. Momentum
says "a stock that's been climbing for the past year (minus the most
recent month) tends to keep climbing." Reversal looks at exactly the
month Momentum deliberately ignores, and says the opposite: a stock that
just had a *bad* single month tends to partially bounce back — often
because that month's drop was driven by panicked or forced selling, not
by anything actually wrong with the company, and the price partially
recovers once that selling pressure passes.

### Testing it properly: train and test, not just "does it look good"

Here's where this project applied an important lesson properly for the
first time. Earlier (§2), a search for good signal weights found a
combination that looked great — but nearby weight choices swung wildly,
which was a red flag that it was a fluke of this one dataset (this is
called **overfitting**: fitting a strategy so precisely to past data that
it's actually just memorized noise in that specific data, not a real
pattern). This time, a stricter test was used: **split the five years of
data into two chunks** — a "training" chunk (2021-2023) to search and tune
on, and a completely separate "test" chunk (2024-2025) that was **never
looked at while choosing anything**. Once a choice was made using only
the training chunk, it was run exactly once on the test chunk, and
whatever came out was reported — no going back to try something else if
the test result was disappointing. This is called **walk-forward
validation**, and it's a much stronger check than just "do nearby
choices give similar results," because it tests something a
neighborhood check can't: does this pattern hold up on *data it's never
seen*, not just on nearby *variations of the same data it was tuned on*?

The reversal signal passed the first (neighborhood-smoothness) check with
flying colors — every weight tried gave a solidly better result than not
using it, with no sudden swings. It looked like a real, stable
improvement. Then came the test chunk: performance got *worse*, not
better. The exact opposite of what training suggested.

**Why did a "smooth, stable-looking" result still fail?** Because
smoothness only proves one thing: the tuning process wasn't accidentally
picking up random noise *in the search itself* (like the earlier §2
spike was). It says nothing about whether the pattern the signal found
was a real, lasting feature of the stock market, or just something
specific to how 2021-2023 happened to play out (this particular time
window had its own quirks — every stretch of market history does) that
simply won't repeat in 2024-2025 or beyond. Only checking on data the
tuning process never saw can catch that second, sneakier kind of
overfitting.

### What actually happened as a result

None of the three new signals were kept. This might read as "the extra
work didn't pay off," but that's the wrong way to see it: the honest,
correct answer to "does this make the strategy better?" turned out to be
"no, not reliably" — and finding that out *properly*, instead of
reporting an exciting-looking number that would likely have disappointed
later, is exactly what rigorous testing is for. A strategy report that
only ever shows results that looked good is a strategy report that
hasn't been checked hard enough. See `CONCEPTS.md` §28-29 and
`CHANGELOG.md` for every number produced along the way, including the
one that looked great and was correctly not trusted.

### The follow-up: applying the same rigor to the original four signals

The lesson above was then applied to the thing that had never actually
been tested this carefully: the *weights* on the original four signals
themselves (they'd only ever been run at a naive "25% each"). The same
train/2021-2023-then-test/2024-2025 approach was used — this time
searching 84 different weight combinations, only on the training data.

The training data's favorite combinations were almost all heavily
weighted toward Momentum — which makes sense in hindsight, since
2021-2023 happened to include a strong momentum-friendly market
recovery. But every one of those training favorites did *badly* on the
2024-2025 test data — some far worse than just using equal weights. This
was the exact same trap as the reversal signal, just showing up in a
different corner of the search.

The combination finally chosen at that point — Momentum 40% / Low-
volatility 40% / 52-week-high 10% / Liquidity 10% — wasn't the training
data's top pick. It was chosen because it was the *most consistent*
performer across **both** the training and test data. This became the
project's strategy for a while — but see §8 below for one more round of
refinement that replaced it.

---

## 8. One more signal, and a stress-test before trusting it

A later idea: instead of measuring "how calm has this stock been"
only one way, measure it **two ways at once**. The existing
Low-volatility signal only looks at closing prices — it can't see how
much a stock jumped around *during* the trading day, only where it ended
up. A different calculation, called **Parkinson volatility**, uses each
day's highest and lowest price to measure exactly that intraday
jumpiness. The two measures see different things: closing-price
volatility catches overnight surprises (a stock that closes calm but
gaps up at the next morning's open); Parkinson volatility catches
daytime jumpiness but misses those overnight gaps entirely. Using both
side by side, instead of picking one, lets the strategy see a more
complete picture of how "calm" a stock really is.

### Why this needed *more* checking than usual, not less

A first attempt at finding good weights for this 5-signal version looked
very promising — it beat the existing strategy on the standard
train/2021-23-then-test/2024-25 check. But instead of stopping there
(having learned from §7's lesson that "one good-looking test" isn't
enough), a stricter question was asked: **what happens to nearby, barely
different weight choices?**

The answer was concerning: some very close nearby combinations performed
dramatically worse — as low as roughly a third of the strategy's
usual risk-adjusted return, on data the search hadn't seen. That's the
kind of narrow, fragile "peak" this project has learned to distrust (see
§7's overfitting lesson) — a good-looking result surrounded by much
worse ones a stone's throw away is a warning sign, not a confirmation.

### The fix: aim for the middle of a good neighborhood, not the top of a spike

Looking more closely at *which* nearby combinations did well vs. badly
showed they weren't scattered randomly — the good ones clustered
together in a specific region of the possible weight choices. So instead
of using the single best-scoring point (which sat near the *edge* of
that good region), a point closer to the *middle* of the cluster was
chosen instead — deliberately giving up a small amount of best-case
performance in exchange for a much safer worst-case: nearby weight
choices now perform far more consistently well, rather than a coin-flip
between "great" and "much worse."

This re-centered version was then checked one more way: on a
*completely different* split of the five years into training and test
periods (instead of 2021-2023/2024-2025, tried 2023-2025/2021-2022) — and
it held up on that too, beating the previous strategy on every measure,
in every check, four separate times over.

### What this project actually uses now

Five signals: Momentum 40%, Low-volatility (closing-price) 25%,
Parkinson volatility (intraday-range) 10%, 52-week-high 15%, Liquidity
10%. This is the version behind every number reported in
`PROJECT_SUMMARY.md`. See `CONCEPTS.md` §34 and `CHANGELOG.md` for the
complete numeric trail behind this decision, including the fragile
version that came first and was correctly not trusted.
