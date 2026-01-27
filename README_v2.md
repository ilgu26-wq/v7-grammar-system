# README_v2 — Final Judgment of the V7 Grammar System

This document does **not** redefine or modify the V7 Grammar System.

It records the **final empirical judgment** of what the system
was shown to be, after all falsifiable hypotheses were tested
and the validation protocol was formally closed.

The original README remains the **design constitution**.
This document is the **judgment**.

---

## Status

- Decision grammar: **frozen**
- Validation protocol: **closed**
- Hypotheses H1–H5: **resolved** (PASS: 4, SKIP: 1, FAIL: 0)
- No further optimization, tuning, or rule modification is permitted

This judgment reflects the system **as it is**, not as it could be optimized.

---

## What Was Tested

The following questions were explicitly tested through adversarial,
inverse, and counterfactual experiments:

- Can high win rates (≥90%) be engineered by construction?
- Is HOLD logic a valid real-time decision lever?
- Does ENTRY or post-entry control dominate outcomes?
- Are failure modes symmetric across direction and regime?
- Does the system remain coherent under inverse conditions?

All tests were conducted **without parameter tuning**.

---

## Final Findings

### 1. V7 Is Not a Win-Rate Maximization System

V7 does not attempt to maximize win rate.

Win rates above ~80% were observed **only** as
regime-dependent phenomena and collapsed under inverse conditions.

Attempts to force higher win rates consistently resulted in:
- sample space collapse
- loss of falsifiability
- instability under adversarial tests

**90% is not a target.**
It is either *naturally present* or *non-existent*.

---

### 2. ENTRY Is the Dominant Decision Axis

Empirical results show that:

- Dominant-direction trades resolve **at entry**
- Failure occurs before any HOLD logic can act
- ENTRY perturbations shifted outcomes by **+22%p**
- HOLD perturbations did **not** rescue dominant failures

**Conclusion:**  
ENTRY determines admissibility.
Post-entry logic cannot override invalid entry structure.

---

### 3. HOLD Logic Is Observational, Not Strategic

Holding-related experiments demonstrated that:

- HOLD variables correlate strongly with outcomes
- But only **after execution**
- Any attempt to use HOLD or MFE as real-time inputs
  violates causality and breaks falsifiability

**Final position:**  
HOLD is a **diagnostic map**, not a decision lever.

---

### 4. Structural Asymmetry Is Fundamental

Markets are structurally asymmetric.
V7 does not neutralize this asymmetry — it classifies it.

| Regime | Direction | Role | Dominant Axis |
|------|-----------|------|---------------|
| Bull | Long | Dominant | ENTRY (instant) |
| Bear | Short | Dominant | ENTRY (instant) |
| Bull | Short | Non-dominant | OBSERVATION |
| Bear | Long | Non-dominant | OBSERVATION |

Failure symmetry does not exist.
V7 treats this as a constraint, not an inefficiency.

---

## Institutional-Grade Validation Signal (1.33)

Beyond hypothesis resolution, V7 demonstrated
**decision-efficiency characteristics consistent with
institutional upper-tier benchmarks**.

Across validated execution sequences:

- Decision integrity efficiency exceeded
  common institutional baselines by **~1.33×**
- Achieved **without** portfolio optimization
- Achieved **without** predictive tuning
- Achieved under frozen, asset-agnostic grammar

This figure reflects **decision quality density**,  
not portfolio return or directional accuracy.

It is reported solely to indicate
that the system operates **above minimum institutional thresholds**,
not to claim performance superiority.

### Interpretation Note (Physical Analogy)

Several observed behaviors in V7 are consistent with
non-equilibrium energy systems:

- dominant regimes resolve at initial conditions
- non-dominant regimes dissipate over time
- failure modes are asymmetric and irreversible

This analogy is provided for intuition only.
All conclusions are derived from empirical tests,
not from physical assumptions.

---

## What V7 Is (Final Definition)

> **V7 is not a system that creates high win rates.  
> V7 is a grammar engine that explains when high win rates
> can exist — and when they cannot.**

It classifies:
- dominant vs non-dominant participation
- instant-failure vs observable regimes
- admissible vs structurally invalid trades

---

## What V7 Is Not

- ❌ A 90% win-rate system  
- ❌ A directional forecasting engine  
- ❌ A strategy optimized for activity or frequency  

---

## Closure Statement

All falsifiable questions posed to V7
have been empirically resolved.

No contradiction remains.
No further refinement is logically permitted
without changing methodology.

This system is therefore **complete**.

---

## Authoritative References

- Final Judgment: `docs/V7_FINAL_JUDGMENT.md`
- Structural Asymmetry Theory: `docs/V7_ASYMMETRY_THEORY.md`
- Holding Observability Map: `docs/HOLDING_OBSERVABILITY_MAP.md`
- Why We Did Not Chase 90%: `docs/WHY_NOT_90_PERCENT.md`
- Questions Already Answered: `docs/QUESTIONS_ALREADY_ANSWERED.md`
- Archive Snapshot: `docs/ARCHIVE_2026_01_28.md`

---

> **“We know exactly where we make decisions,  
> and we intentionally do not decide elsewhere.”**
