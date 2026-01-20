# Post-Entry Continuation Control in V7 Grammar System

This document defines how EE (Expansion Eligibility) is formally integrated
into the V7 Grammar System as a post-entry continuation controller.

EE is not part of entry logic, not predictive, and not an alpha source.
It governs whether an already-entered position is structurally worth maintaining.

---

## Position of EE in the V7 Architecture

The V7 system is explicitly divided into Entry Grammar and Post-Entry Control.

```
Market Data
     ↓
STATE (Directional Stabilization)
     ↓
STB (Entry Timing & Execution Ordering)
     ↓
V7 Grammar (Entry Authorization)
     ↓
Execution (Initial Risk Defined)
     ↓
Post-Entry Observation Window
     ↓
EE (Expansion Eligibility)
     ↓
CONTINUE / TERMINATE
```

### Key Boundary

EE is evaluated strictly after entry.
It has zero influence on entry selection.

---

## Role Separation (Critical)

| Component | Function | Timing |
|-----------|----------|--------|
| STATE | Directional regime stabilization | Pre-entry |
| STB | Noise suppression & timing | Pre-entry |
| V7 Grammar | Entry authorization | Pre-entry |
| EE | Continuation / termination | Post-entry only |

EE cannot:
- generate entries
- filter entries
- improve win rate pre-entry

EE only determines whether continuation is structurally justified.

---

## Definition of EE (Expansion Eligibility)

EE is defined as a post-entry expansion ratio:

```
EE = MFE / MAE
```

Where:
- MFE = Maximum Favorable Excursion after entry
- MAE = Maximum Adverse Excursion after entry

EE is undefined before entry and has no predictive interpretation.

---

## Post-Entry Evaluation Logic

EE is evaluated only after a minimum structural time has elapsed.

```python
def manage_position(mfe, mae, bars_since_entry):
    if bars_since_entry < N:
        return HOLD  # structural observation delay

    ee = mfe / max(0.01, mae)

    if ee >= 1.0:
        return HOLD
    else:
        return EXIT
```

This logic enforces continuation eligibility, not outcome prediction.

---

## Empirical Observation (Post-Entry Only)

After entry, trades separate into two regimes:

| Group | Observed Outcome |
|-------|------------------|
| EE ≥ 1.0 | Structurally expandable |
| EE < 1.0 | Structurally non-expandable |

This separation has been observed across:
- multiple assets,
- multiple regimes,
- out-of-sample segments.

These observations do not imply predictability
and do not justify EE-based entry selection.

---

## Hierarchy of Control

EE is not the highest-level control mechanism.

The following conditions override EE:
- STATE_FLIP
- DISTRIBUTIVE_CLOSURE
- EXECUTION_CONSTRAINT_VIOLATION

EE only governs continuation within an already valid structural state.

---

## Practical Meaning

The V7 system does not aim to trade continuously.

Instead, it enforces the following invariant:

> Positions without post-entry expansion capability
> are removed as early as structurally justified.

This minimizes:
- time spent in non-productive positions,
- exposure to stagnant risk,
- reliance on predictive accuracy.

---

## Scope & Limitations

EE:
- cannot be used pre-entry
- does not guarantee profit
- does not replace execution constraints
- does not override structural exits

EE improves capital survival, not entry quality.

---

## Final Statement

**V7 Grammar decides when to enter.**
**EE decides whether staying makes sense.**

EE is a continuation controller,
not a strategy, not an alpha signal, and not a prediction module.

---

## Status

**Integrated — Post-Entry Continuation Layer**
