# Research Status (Updated: 2026-02-01)

## Current State

All structural experiments archived in `/DUMP`.
**Causal phase experiments completed.**

---

## CAUSAL PHASE RESULTS (2026-02-01)

### Core Discovery

**Directional Agency Collapse (Collapse of the decision-making agent)**

The breakdown observed prior to TRANSITION is not driven by the impotence of one side (buyers or sellers), but by a **collapse of market-wide directional efficiency**.

Both buyer and seller activity remain present and symmetric.
What disappears is the market's ability to convert activity into directional progress.

**ZPOC represents a state of directional indeterminacy, not accumulation or distribution by a dominant side.**

---

### Completed Experiments

| Experiment | Result | Status |
|------------|--------|--------|
| EXP-DEPTH-DYNAMICS-01 | ER identified as primary precursor (Lift 0.49-0.57) | PASS |
| EXP-STOPHUNT-ADVERSARIAL-01 | H_SH WEAK (1/4), stop hunt hypothesis rejected | PASS |
| EXP-DEPTH-DYNAMICS-02 | STRONG_PRECEDENCE (Lift 1.39-1.77, w=-10) | PASS |
| EXP-ZPOC-PHASE-DECOMP-01 | ZPOC→TRANSITION 86.1%, Lift 2.20 | PASS |
| EXP-SELLER-IMPOTENCE-01 | Seller impotence rejected, symmetry confirmed | PASS |

---

### Key Findings

#### 1. Transition Precedence (EXP-DEPTH-DYNAMICS-02)

```
w       P(C|Event)   P(C|Base)   Lift
-1      0.1703       0.0994      1.71
-2      0.1521       0.0907      1.68
-3      0.1527       0.0936      1.63
-5      0.1390       0.1001      1.39
-10     0.1321       0.0747      1.77
```

Transition is observable **10 bars in advance** via ER low + depth_trend flip.

#### 2. ZPOC Structure (EXP-ZPOC-PHASE-DECOMP-01)

```
ZPOC zones: 890 (23% coverage)
ZPOC → TRANSITION within 20 bars: 86.1%
Lift vs baseline: 2.20
Post-transition ER recovery: 0.325
```

ZPOC = ER < 0.25 sustained for 5+ bars

#### 3. Symmetric Impotence (EXP-SELLER-IMPOTENCE-01)

```
Phase A (ER > 0.35):
  Seller_Active: 62.9%
  Seller_Effective: 44.1%
  Ratio: 0.70

Phase B (ER < 0.25):
  Seller_Active: 64.2%
  Seller_Effective: 45.1%
  Ratio: 0.70

Impotence drop: -0.2% (NO DIFFERENCE)
```

**Both sides equally ineffective in ZPOC.**

---

### Rejected Hypotheses

| Hypothesis | Evidence | Status |
|------------|----------|--------|
| Stop Hunt | Direction symmetry, channel independence | REJECTED |
| Seller Exhaustion | Seller_Active maintained | REJECTED |
| Buyer Dominance | Buyer_Effective = Seller_Effective | REJECTED |
| Time-based Convergence | Condition-based, not temporal | REJECTED |

---

### Confirmed Structure

```
[ Delta Organizer Present ]
→ Small orders accumulate direction
→ ER high
→ Trend persists

[ Delta Organizer Absent (ZPOC) ]
→ Orders present but direction unfixed
→ ER collapse
→ depth stagnation
→ TRANSITION pending

[ TRANSITION ]
→ Structural phase shift
→ ER recovery begins

[ POC SETTLE ]
→ New equilibrium established
→ Black Line forms
```

---

### Interpretation

The ZPOC phase does not reflect seller or buyer exhaustion.
Instead, it reflects the **absence of a directional delta organizer**.

Market activity remains symmetric on both sides,
but no participant commits directional exposure.
As a result, price movement fails to accumulate efficiency,
leading to a state of **directional indeterminacy**.

---

## What Has Been Validated (Structural Phase)

### 1. World Partition (Empirically Closed)

| Partition | Coverage | E_RESP Lead% | Status |
|-----------|----------|--------------|--------|
| **SLOW Terminal** | 88.9% | 96.8% | Near-deterministic |
| **FAST Terminal** | 11.1% | 63.2% baseline | Conditional judgment possible |

### 2. FAST Terminal Islands (OOS Validated)

| Island State | Avg Lead% | Folds | Status |
|--------------|-----------|-------|--------|
| High_Comp_Large_Weak_Low_Low_Mid | 85.4% | 4/5 | Stable |
| High_Loose_Large_Weak_Low_Low_Mid | 74.3% | 5/5 | Stable |
| Low_Loose_Small_Weak_Low_Low_Mid | 66.7% | 5/5 | Stable |

---

## Next Question

> "Why do some directional indeterminacy states persist longer than others, and what triggers the collapse into TRANSITION?"

Candidates:
- ER decay rate
- depth_trend curvature
- time-in-state

---

## Data Integrity Statement

- All experiments included, including failures
- No selection of favorable results
- Raw notes preserved without editing
- Contradictions and abandoned ideas included

---

## Frozen Timestamp

```
2026-02-01T19:00:00
Causal phase experiments complete.
```
