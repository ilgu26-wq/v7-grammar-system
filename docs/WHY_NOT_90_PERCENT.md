# Why We Did Not Chase 90% Win Rates

Most trading systems pursue higher win rates by adding conditions.

V7 did not.

This was not a philosophical choice.
It was an empirical conclusion.

---

## 1. 90% Is Not a Target — It Is a Phenomenon

Through repeated experiments, we observed:

- Win rates above ~80% do not emerge gradually.
- They appear abruptly, only under very specific structural conditions.
- When they appear, they collapse just as abruptly when conditions shift.

This suggests that 90% is not an optimizable metric, but a regime-dependent phenomenon.

---

## 2. What Happens When You Try to "Make" 90%

We attempted to push win rates higher using:

- Additional entry filters
- Multi-condition intersections
- Ratio and sector constraints
- Time-based segmentation

The result was consistent:

| Action | Effect |
|:-------|:-------|
| Add conditions | WR ↑ |
| Sample size | N ↓ |
| Stability | ↓ |
| Falsifiability | ↓ |

High win rates were achievable only by shrinking the sample space to the point where the result could no longer be disproven.

This was rejected.

---

## 3. Structural Limits Observed in V7

Across all validated experiments:

- Non-dominant trades (e.g. BULL shorts) failed gradually.
- Dominant-direction trades failed instantly.
- Instant-failure regimes allowed entry-only decisions.
- Gradual-failure regimes required observability and CUT logic.

These structures impose natural ceilings on achievable win rates.

For non-dominant trades, the ceiling consistently appeared between 70–80%.

Attempts to exceed this ceiling resulted in:

- regime dependence
- temporal instability
- inverse performance under adversarial tests

---

## 4. Why 90% Was Explicitly Rejected

A system that cannot explain why it fails is not a system.

Pursuing 90% by construction required:

- accepting untestable assumptions
- ignoring counterfactuals
- allowing post-hoc justification

V7 rejects this.

The goal of V7 is not to win often,
but to never trade when the grammar is invalid.

---

## 5. Final Position

V7 does not aim for 90%.

If a 90% regime exists naturally, V7 will identify it.
If it does not, V7 will explain why.

This is not restraint.
It is correctness.

> **90% is not a goal.**
> **It is evidence — or it is nothing.**
