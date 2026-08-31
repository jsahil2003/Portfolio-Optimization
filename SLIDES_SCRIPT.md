# Speaker Script — `citadel_deck.pptx`

Talking notes for each slide. Numbers here should always match
`PROJECT_SUMMARY.md`, `CHANGELOG.md`, and `citadel_submission.xlsx` — if
you re-run `citadel.py` and get different numbers, update all four
together, then regenerate the deck with `python build_slides.py`.

Keep this file and the deck in sync: slide numbers below match the deck
exactly. If you reorder or add slides, update both this file and
`build_slides.py`.

---

**Slide 1 — Title**
"This is my submission for the Finesse x Citadel Portfolio Challenge — a
quantitative equity portfolio strategy that's fully free of a specific,
common backtesting mistake called lookahead bias, which I'll explain
shortly. I built this with heavy use of Claude Code, an AI coding
assistant — I'll be upfront about exactly how throughout this
presentation, and there's a dedicated slide on it near the end."

**Slide 2 — The Problem**
"The brief asks for up to 10 stocks from a 300-stock universe — Nifty
100, Midcap 100, and Smallcap 100 combined — backtested over the last
five years with realistic transaction costs. The primary ranking metric
is Total Net PNL, but they also score risk-adjusted metrics like Sharpe
ratio and drawdown, and want everything benchmarked against the market."

**Slide 3 — Approach: Four Stages**
"I split the problem into four stages. First, where do the candidate
stocks come from — I pull that list live from the official NSE indices
source every time I run this, so it's never stale. Second, which 10 do I
actually pick each month. Third, given those 10, how much money goes into
each. Fourth, does this actually work when simulated realistically, and
how do I know I'm not fooling myself."

**Slide 4 — The Five Signals**
"These are the five numbers I calculate for every stock to decide who
makes the top 10. Momentum gets the most weight, 40%, since it's the
single most historically well-supported factor for this kind of
strategy. I actually measure 'how calm has this stock been' two
different ways — 25% on closing-price volatility and 10% on intraday
range volatility — because they genuinely see different things: one
catches overnight surprises, the other catches how much a stock jumps
around during the trading day itself. 52-week-high gets 15%, and
liquidity 10%. I'll explain over the next several slides exactly how I
landed on these specific weights, not just picked them — and it took
more rounds of checking than I originally expected."

**Slide 5 — Why No Fundamentals**
"You might notice there's no P/E ratio, no ROE, nothing about company
fundamentals here — and that's deliberate. My data source can only give
me a company's fundamentals as they are *today*. If I used today's P/E
ratio to simulate a stock-picking decision from March 2022, I'd be
letting my backtest use information that didn't exist yet — that's
called lookahead bias, and it's one of the most common ways a backtest
lies to you. I did build an earlier version using fundamentals, and it's
still in the code for comparison, but I retired it in favor of this
fully clean version."

**Slide 6 — Ledoit-Wolf Weighting**
"Once I've picked 10 stocks, I don't just split the money evenly, and I
don't just look at each stock's own risk in isolation either. I use a
technique called Ledoit-Wolf shrinkage minimum-variance weighting, which
looks at how all 10 stocks move *together* — their correlation — and
sizes positions to actually minimize the whole portfolio's risk, not
just each piece's risk separately. I tested this against two alternatives
and it won clearly, which I verified four different ways before trusting
it."

**Slide 7 — Diversification / Correlation**
"A natural question is: does this weighting method guarantee I'm
diversified — that some of my stocks move in opposite directions? And
the honest answer is no. That weighting step can't change *which* stocks
get picked — it can only work with whatever correlation those 10 stocks
happen to have. What it *does* do is notice and reward diversification
when it exists — I can show you an exact example where it gave more
money to a genuinely diversifying pair than a simpler method would have.
Across the whole portfolio, only about 7% of stock pairs are actually
negatively correlated, which is realistic — these are all Indian equities
in the same market, so true negative correlation is rare without adding
a different asset class entirely, which the rules don't allow here."

**Slide 8 — Rigor #1: The Spike That Wasn't Real**
"This is one of several mistakes I caught myself making, and I think
it's important to show, not hide. Early on, a search for good signal
weights found a combination that looked amazing. But when I checked
nearby weight combinations — barely different from the winner — the
results swung wildly. That's the signature of a fluke, not a real
pattern, so I threw it out and used the honest, simpler version instead."

**Slide 9 — Rigor #2: Smooth Isn't Enough**
"Later I tried adding a signal, and this time the weight search was
smooth and consistent — which I thought meant it was safe. So I did a
stricter test: I tuned it only on 2021 through 2023, then checked it on
2024 and 2025, data it had never seen. It got *worse* on the new data —
the opposite of what training suggested. That taught me that smoothness
alone isn't proof against overfitting — you need a genuine held-out
test."

**Slide 10 — Rigor #3: Properly Tuning the Base Weights**
"So I applied that lesson properly to the four core signals. I tested 84
different weight combinations, but only picked based on how consistent
they were across both the training years and the untouched test years —
not which one looked best on training data alone. The correlation
between how well a combination did on training data and how well it did
on test data was basically zero, which is itself a striking finding. The
combination I chose became the strategy for a while — but there was one
more round of refinement, which is the next slide."

**Slide 11 — Rigor #4: Adding a 5th Signal, Stress-Tested 4 Ways**
"I later realized I was only measuring volatility one way — from closing
prices — and I could add a second, complementary measure that looks at
each day's actual trading range instead. When I searched for good
weights for this five-signal version, I found something that looked
great on my standard train-and-test check. But instead of stopping
there, I checked something stricter: what happens to weights that are
only *slightly* different from my winner? Some of those nearby
combinations performed dramatically worse — a warning sign I've learned
to take seriously. So rather than use the single best-scoring point, I
found the *middle* of the cluster of genuinely good combinations instead,
which gave up a little peak performance for a much safer, more
consistent result nearby. Then I validated it one more time, on a
completely different way of splitting the five years into training and
test periods. It held up on all four checks. That's the version I'm
actually using."

**Slide 12 — Results**
"Here's where that lands: 38.4% annualized return against the Nifty 50's
13.4%, a Sharpe ratio of 1.73 against 0.97, and a max drawdown close to
the benchmark's. On ₹1 crore of starting capital, that's about ₹3.90
crore of net profit after transaction costs, over the five-year period."

**Slide 13 — The Full Journey**
"I want to be clear this wasn't a straight line to these numbers. I
found and fixed two real bugs on my very first live test run — the
initial numbers looked implausibly bad, which is what made me go look
for the bug instead of just accepting a bad result. I compared multiple
weighting schemes properly instead of guessing. I tried and rejected a
GARCH-based volatility forecast twice — once as a stock-selection signal,
once as a risk-management overlay — because in both cases the properly
validated version didn't actually beat what I already had, even when a
naive look at the numbers suggested otherwise. And as you saw, I caught
myself on the edge of overfitting more than once and backed out or
adjusted every time."

**Slide 14 — Limitations**
"To be upfront about what this doesn't cover: it's still one five-year
stretch of history, and even validated results can be specific to that
period. The stock universe depends on live internet access to stay
current. Transaction costs are modeled simply. And the rules don't allow
shorting or other asset classes, so true diversification is inherently
limited to what's possible within a single country's stock market."

**Slide 15 — AI Usage Disclosure**
"I want to be completely transparent here: I built this with Claude Code,
an AI coding assistant, over about two weeks. Claude wrote all of the
code and ran every single test and backtest you've seen — these are real
numbers from real historical market data, not estimates. My job was to
direct the work, ask hard questions when something didn't sit right with
me — like whether Ledoit-Wolf actually guarantees diversification, or
pushing for more rigor before adopting a promising-looking result — decide
between trade-offs Claude surfaced, and make sure this got documented
honestly, including the mistakes. I can walk through and explain every
concept in this deck myself, using the source documents I've shared,
because understanding this — not just running it — was the point."

**Slide 16 — Questions?**
"Happy to go deeper into any part of this — the math behind any factor,
the validation methodology, or the code itself."
