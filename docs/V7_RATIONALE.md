# Why V7 Changed

> Original Assumptions → Empirical Revision

---

## Original Assumption (V6 / Early V7)

V7's initial assumption was simple:

> "If we find structurally strong signals (STB, IGNITION),
> higher win rates and larger TPs are possible."

Based on this, the system:

- Used STB / spot logic as ENTRY signals
- Interpreted high z-score / cumulative ratios as strength evidence
- Assumed TP expansion (2R+) was a rational goal

In other words, early V7 believed:

> **"Strong signal → Goes further"**

---

## What the Data Broke

Large-scale backtests and decomposition experiments repeatedly shattered this assumption.

### 1. Strong Signal ≠ Goes Further

- TP expansion caused hit-rate collapse
- RR expansion resulted in negative expected value (E)
- "Strong-looking signals" showed increased early failures

**Conclusion**:

> Energy is consumed "faster", not "further".

### 2. STB / Spot Logic Was Not ENTRY

STB, SPS, z-score family showed:

- Redundancy
- Time instability
- Window dependency

Residual verification results:

- Already explained by DC × avg_delta
- Adding them caused performance degradation or no change

**Conclusion**:

> STB was not "a reason to enter".
> It was a trace of energy that had already passed.

### 3. Win Rate Could Not Be a Goal

Combinations that improved win rate:

- Reduced entry count
- Reduced TP
- Loss avoidance

That is:

> "A structure that predicts well" did not exist.
> Only "a structure that fails less" existed.

---

## The Core Insight

> The market does not reward "winning structures".
> It only allows survival in "non-punishing structures".

This realization completely changed V7's direction.

---

## Structural Revision

### What Was Abandoned

| Abandoned | Reason |
|:----------|:-------|
| STB = ENTRY signal | Redundant, time-unstable |
| Cumulative ratio = strength evidence | Already captured by DC |
| TP expansion = rational reward | Energy conservation violation |
| Win rate maximization = goal | Only loss avoidance worked |

### What Was Adopted

#### 1. ENTRY is only a "possibility threshold"

```
DC_pre >= 0.7
```

- Only confirms structural validity
- No further judgment

#### 2. Energy determines only "reward size"

```
avg_delta
```

- Low energy → Reduce TP
- No energy → No trade
- Energy is "distance", not "direction"

#### 3. Force (relative) determines "rejection condition"

```
force_ratio
```

- Bad force → Don't enter at all
- Don't reduce SL, don't increase TP
- **Don't look for reasons to win. Remove reasons to lose.**

---

## Final Philosophy

> V7 does not ask "why should I enter?"
> Instead, it asks "why would I die here?"

Therefore, V7:

- Enters less
- Adverse excursion is less
- Breaks less

---

## One-Line Evolution Summary

> **V7 evolved from "finding strong signals"**
> **to "refusing structurally bad trades" —**
> **because the data never rewarded conviction, only restraint.**

---

## Empirical Evidence Trail

| Claim | Evidence Path |
|:------|:--------------|
| STB redundancy | `experiments/hr0_redundancy.json` |
| Force Ratio causality | `experiments/f_overfit_suite.json` |
| RR expansion failure | `experiments/rr_grid_test.json` |
| Common denominator test | `experiments/common_denominator_test.json` |
| Full validation | `experiments/v7_revalidation.json` |

---

## Key Metrics Comparison

| Metric | BASE | V7 | Delta |
|:-------|-----:|---:|------:|
| Entries | 5,363 | 77 | -98.6% |
| Win Rate | 48.1% | 49.4% | +1.3%p |
| Early SL | 31.8% | 27.3% | -4.5%p |
| Avg MAE | 9.4pt | 9.0pt | -0.5pt |
| Total PnL | -2,010pt | -24pt | +1,986pt |

---

*Last updated: 2026-01-27*
