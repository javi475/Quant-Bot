# Pine Scripts

TradingView implementations of the strategy in
[`.docs/01_CRT_STRATEGY.md`](../.docs/01_CRT_STRATEGY.md), used to validate the
edge before any bot is built. See
[`.docs/02_PINE_VALIDATION.md`](../.docs/02_PINE_VALIDATION.md) for why this
comes first.

| File | Setup |
|---|---|
| `crt_setup_b.pine` | **Setup B — reversal.** Level swept, closes back inside, retest rejects |
| — | Setup A (continuation) not yet written |

## Chart setup — required

| Setting | Value | Why |
|---|---|---|
| Symbol | ES (or MES) | The instrument being traded |
| Timeframe | **15 minutes** | The strategy's only timeframe |
| **Extended hours** | **ON** | **Overnight levels cannot be computed without it.** With regular hours only, ONH/ONL are never populated and half the setups vanish silently |
| Bar Magnifier | ON if available | The stop sits just past a wick, so bars that touch both stop and target are common. Without it, results are optimistic |

Commission defaults to $2.50/contract and slippage to 1 tick. Both are guesses
— set them to your broker's actual figures before believing any number.

## First run: verify the levels before trusting a single trade

Do not look at the performance summary yet.

1. Load the script and check the plotted PDH/PDL (orange) and ONH/ONL (aqua)
   against what you'd mark by hand for a few sessions.
2. Confirm they step at the right moments — new overnight levels at the open,
   new prior-day levels after the close.
3. Check a DST changeover week. A session boundary off by an hour produces
   plausible-looking results that are entirely wrong.

If the levels are wrong, every downstream number is wrong in a way that still
looks credible. This is why level verification is its own milestone.

## The experiment this exists to run

The retest target is a switch because the operator and the source material
describe it differently, and nobody knows which is right:

| Mode | Pullback destination |
|---|---|
| `Level` | The swept level itself — the operator's description |
| `Liquidation candle zone` | That candle's full range — the source's "extreme point of interest" |
| `Imbalance (FVG)` | The gap the sweep left — the source's preferred, shallower entry |

**Run all three over identical data and compare.** They produce different
entries, stops, and therefore different 3R targets — they are three different
strategies, not three settings.

Record trade count alongside performance. A mode that wins on percentages
across nine trades has told you nothing.

## Second experiment: does CRT need directional bias?

The source states the model is *"absolutely useless"* without a daily bias.
This script has none — it takes every qualifying sweep in both directions.

If results are poor, that is the first thing to test before concluding the
strategy doesn't work: add an HTF trend filter and compare. If they are good
without one, that is a genuinely useful finding.

## Reading the results honestly

- **~5 months of data on Essentials is one market regime.** A good result means
  "worth continuing", not "proven".
- **Don't tune the inputs until it looks good.** ATR multiple, max stop, and
  expiry bars are all tempting dials. Turning them until the equity curve
  improves measures the tuning, not the strategy.
- **A bot takes every setup meeting its criteria.** The source insists on
  trading only "A+" setups — discretion this cannot reproduce. Expect
  mechanical results to come in below what the source implies.

## Known limitations

- Setup A (continuation) is not implemented — its rules are specified but the
  strategy has only been written for reversals.
- One setup armed at a time. A newer sweep replaces an older unfilled one.
- The imbalance is detected as a simple three-bar gap around the liquidation
  candle. If no gap formed, the setup is skipped in FVG mode — expect a lower
  trade count there.
- Entries fill at the close of the retest bar (`process_orders_on_close`).
  Live fills would differ by slippage.
- **Unverified.** This has not been run on a chart. Treat the first session as
  a debugging pass, not a result.
