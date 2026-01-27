# Why STB Was Removed

> STB looked strong, but all its effects were absorbed by DC and Energy.
> Nothing remained as a real-time judgment axis.

---

## STB's Original Role (Initial Assumption)

STB (Spot / Strong Trigger Bar) originally meant:

- Strong energy concentration
- Abnormal price reaction
- "Something happened here" signal

In early V7, STB was used as:

- ENTRY trigger
- Strength evidence
- TP expansion justification

**Assumption**: "Strong spot → Goes further"

---

## What the Data Showed

### 1. STB Was Not Independent

Full decomposition results:

- STB effect only occurred within `DC_pre × avg_delta` conditions
- When controlling for those conditions:
  - STB = Zero residual effect
  - No improvement in Survival / WR / MAE

**Conclusion**: STB was not a cause, but a shadow of the result.

### 2. STB Was Time-Unstable

- Only worked in specific periods
- Performance collapsed with window changes
- High parameter dependency

**Result**: Cannot be used as real-time judgment logic.

### 3. STB Was Not a "Reason to Enter"

Even when STB = True:

- Below-average survival
- STB-only zones showed worst performance
- Non-STB zones often survived better

**Conclusion**: STB was not a signal saying "enter here",
but a post-hoc tag meaning "energy already released".

---

## Final Verdict

| Criterion | Result |
|:----------|:-------|
| Independent axis | NO |
| Real-time stability | NO |
| ENTRY justification | NO |
| Residual information | NO |

**STB was structurally removed.**

---

## One-Line Summary

> "STB looked strong, but all its effects were absorbed by DC and Energy.
> Nothing remained as a real-time judgment axis."

---

## Evidence Trail

| Test | Path |
|:-----|:-----|
| Redundancy check | `experiments/hr0_redundancy.json` |
| Ablation test | `experiments/f_overfit_suite.json` |
| Leave-one-out | `experiments/v7_revalidation.json` |

---

*Last updated: 2026-01-27*
