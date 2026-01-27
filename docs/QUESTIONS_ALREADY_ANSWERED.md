# Questions Already Answered by Experiment

This document lists questions that were explicitly tested and resolved through empirical experiments in V7.

No interpretation is included.

---

## Q1. Can win rates above 90% be engineered?

**Answer**: No

**Evidence**: H-CONQUEST, A-Track, Entry perturbation tests

**Result**: High WR only appears conditionally and collapses under adversarial tests.

---

## Q2. Is entry or holding more important?

**Answer**: It depends on direction and regime.

| Case | Dominant Factor | Evidence |
|:-----|:----------------|:---------|
| BULL SHORT | HOLD / CUT | MAE@Bar3 split |
| BEAR LONG | ENTRY | Bar1 instant failure |
| BULL LONG | ENTRY | Entry-close distribution |
| BEAR SHORT | ENTRY | Symmetric instant failure |

---

## Q3. Does HOLD logic improve dominant trades?

**Answer**: No

**Evidence**: HOLD perturbation tests

**Result**: SL occurs before HOLD can act.

---

## Q4. Does ENTRY refinement improve non-dominant trades?

**Answer**: Marginally

**Evidence**: ENTRY perturbation suite

**Result**: N changes, WR remains bounded.

---

## Q5. Are MFE and Depth valid real-time signals?

**Answer**: No

**Evidence**: Holding Observability Map

**Result**: Strong correlation with outcomes, invalid as inputs.

---

## Q6. Is V7 regime-independent?

**Answer**: No — and intentionally so

**Evidence**: Regime split experiments

**Result**: V7 classifies regimes; it does not neutralize them.

---

## Q7. Is failure symmetric between long and short?

**Answer**: No

**Evidence**: Bar1 vs Bar3 failure timing

**Result**: Structural asymmetry confirmed.

---

## Q8. Does adding more conditions increase robustness?

**Answer**: No

**Evidence**: WHEN / Intersection comparisons

**Result**: WR increases while falsifiability decreases.

---

## Summary

V7 answers questions.
It does not optimize answers.
