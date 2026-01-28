# README_v2 — Final Judgment & Forward Interface of the V7 Grammar System

This document does **not** redefine or modify the V7 Grammar System.

It records the **final empirical judgment** of what the system
was shown to be, after all falsifiable hypotheses were tested
and the validation protocol was formally closed — **and clarifies how new alpha can be layered without violating that judgment**.

The original README remains the **design constitution**.
This document is the **judgment and interface boundary**.

---

## Status

* Decision grammar: **frozen**
* Validation protocol: **closed**
* Hypotheses H1–H5: **resolved** (PASS: 4, SKIP: 1, FAIL: 0)
* No further optimization, tuning, or rule modification is permitted **inside the grammar**

This judgment reflects the system **as it is**, not as it could be optimized.

---

## What Was Tested

The following questions were explicitly tested through adversarial,
inverse, and counterfactual experiments:

* Can high win rates (≥90%) be engineered by construction?
* Is HOLD logic a valid real-time decision lever?
* Does ENTRY or post-entry control dominate outcomes?
* Are failure modes symmetric across direction and regime?
* Does the system remain coherent under inverse conditions?

All tests were conducted **without parameter tuning**.

---

## Final Findings

### 1. V7 Is Not a Win-Rate Maximization System

V7 does not attempt to maximize win rate.

Win rates above ~80% were observed **only** as
regime-dependent phenomena and collapsed under inverse conditions.

Attempts to force higher win rates consistently resulted in:

* sample space collapse
* loss of falsifiability
* instability under adversarial tests

**90% is not a target.**
It is either *naturally present* or *non-existent*.

---

### 2. ENTRY Is the Dominant Decision Axis

Empirical results show that:

* Dominant-direction trades resolve **at entry**
* Failure occurs before any HOLD logic can act
* ENTRY perturbations shifted outcomes by **+22%p**
* HOLD perturbations did **not** rescue dominant failures

**Conclusion:**
ENTRY determines admissibility.
Post-entry logic cannot override invalid entry structure.

---

### 3. HOLD Logic Is Observational, Not Strategic

Holding-related experiments demonstrated that:

* HOLD variables correlate strongly with outcomes
* But only **after execution**
* Any attempt to use HOLD or MFE as real-time inputs
  violates causality and breaks falsifiability

**Final position:**
HOLD is a **diagnostic map**, not a decision lever.

---

### 4. Structural Asymmetry Is Fundamental

Markets are structurally asymmetric.
V7 does not neutralize this asymmetry — it classifies it.

| Regime | Direction | Role         | Dominant Axis   |
| ------ | --------- | ------------ | --------------- |
| Bull   | Long      | Dominant     | ENTRY (instant) |
| Bear   | Short     | Dominant     | ENTRY (instant) |
| Bull   | Short     | Non-dominant | OBSERVATION     |
| Bear   | Long      | Non-dominant | OBSERVATION     |

Failure symmetry does not exist.
V7 treats this as a constraint, not an inefficiency.

---

## What the Experiments Ultimately Revealed

Through exhaustive comparison with WHEN / intersection-based systems:

* V7 isolates **common structural denominators** across market states
* It deliberately ignores frequency expansion
* It preserves sample stability and falsifiability

This means:

> **V7 is a distributional classifier, not an execution optimizer.**

It identifies *where structure exists*, not *how often to trade it*.

---

## Alpha Is External by Design

A critical conclusion of the validation process:

> **Any increase in frequency, win rate, or PnL must come from external alpha — not from grammar mutation.**

V7 provides:

* a verified admissibility filter
* regime / role classification
* causal separation between decision and outcome

Alpha modules may:

* source additional signals
* expand frequency
* introduce predictive bias

**Only if** they:

* operate upstream of ENTRY
* do not alter grammar invariants
* remain independently falsifiable

V7 is therefore an **alpha host**, not an alpha generator.

## What V7 Actually Provides to Alpha Design

V7 does not generate alpha,
but it **defines the distributional coordinate system
in which alpha may operate meaningfully**.

Concretely, V7:

- isolates empirically verified common structural regions
- rejects non-stationary or non-falsifiable regimes
- maps market participation into stable, comparable buckets

This allows external alpha to:

- import additional data sources
- express predictive bias conditionally
- operate only within structurally admissible regions

In this sense, V7 is not merely a filter.

It is a **distributional reference frame**
against which alpha hypotheses can be tested,
rejected, or validated without contaminating the grammar itself.

---

## Practical Implication

The system you built does not say:

> “Trade more to make more.”

It says:

> “Only trade where structure is provably real — and let alpha decide *how often*.”

This is why:

* signal counts are sparse
* win rate ceilings exist
* frequency expansion requires external design

These are **features**, not limitations.

---

## What V7 Is (Final Definition)

> **V7 is not a system that creates high win rates.
> V7 is a grammar engine that explains when high win rates
> can exist — and when they cannot.**

It classifies:

* dominant vs non-dominant participation
* instant-failure vs observable regimes
* admissible vs structurally invalid trades

---

## What V7 Is Not

* ❌ A 90% win-rate system
* ❌ A directional forecasting engine
* ❌ A strategy optimized for activity or frequency

---

## Closure Statement

All falsifiable questions posed to V7
have been empirically resolved.

The grammar is complete.
Future work belongs **outside** the grammar boundary.

---

## Authoritative References

* Final Judgment: `docs/V7_FINAL_JUDGMENT.md`
* Structural Asymmetry Theory: `docs/V7_ASYMMETRY_THEORY.md`
* Holding Observability Map: `docs/HOLDING_OBSERVABILITY_MAP.md`
* Why We Did Not Chase 90%: `docs/WHY_NOT_90_PERCENT.md`
* Questions Already Answered: `docs/QUESTIONS_ALREADY_ANSWERED.md`
* Archive Snapshot: `docs/ARCHIVE_2026_01_28.md`

---

> **“We know exactly where we make decisions,
> and we intentionally do not decide elsewhere.”**
