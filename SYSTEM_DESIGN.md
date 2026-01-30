# V7 Grammar System — Design & Construction Document

## Objective

This document records **how the V7 Grammar System was designed** and  
**what logical verification stages it passed through to reach its current structure**.

The system has one goal:

> **To explain entry and holding through "observation data", not "strategy"**

That is:
- No prediction
- No optimization
- Minimal judgment

Decisions are made solely through **observable state** and **verified grammar**.

---

## Core Declaration

- This system is **not a prediction engine**
- This system is **a decision grammar**
- All actions must be **rare**; inaction is the default state

---

## System Architecture Overview

```
[ Raw Candle Data (1m) ]
        ↓
[ Feature Builder ]              (Non-ML, Deterministic)
        ↓
[ Observation Encoder ]          (ML Slot / Optional)
        ↓
[ State Validator ]              (Grammar, Sealed)
        ↓
[ State Mediator ]               (Grammar, Sealed)
        ↓
[ Action Gate ]                  (Grammar, Sealed)
        ↓
[ Logger / Risk Annotation ]     (Post-hoc Recording)
```

**Key Principles:**
- Decision authority exists **only in Action Gate**
- ML **cannot modify state coordinates**
- ML provides **only observation reliability (uncertainty)**

---

## Phase A — 4D State Space Establishment

### Question
"What is the minimum state dimensionality required to explain entry/holding?"

### Verification Result
The following 4 state variables were verified as sufficient:

```
State = (Force, DC, Delta, τ)
```

| Variable | Description |
|----------|-------------|
| **Force** | Energy magnitude |
| **DC** | Energy position (0~1) |
| **Delta** | Release result |
| **τ (tau)** | Dwell time in DC extreme region |

### Key Findings
- Direction prediction is impossible (Bar1 = 50%)
- All failed signals can be explained by insufficient τ
- τ is not a time axis, but a **state maturity axis**

→ **4-dimensional state space confirmed**

---

## Phase B — τ ≥ 5 Survival Condition Verification

### Question
"Is τ a performance parameter or a survival condition?"

### Experiment
τ threshold sweep (35,064 candles)

| τ_min | ENTER% | Verdict |
|-------|--------|---------|
| 2 | 9.45% | FAIL |
| 3 | 5.68% | FAIL |
| 4 | 3.55% | FAIL |
| **5** | **2.44%** | **PASS** |
| 6+ | Decreasing | PASS |

### Conclusion
- τ ≥ 5 is **not a performance optimum** but a **survival threshold**
- Relaxing this condition causes:
  - ENTER explosion
  - Structural collapse

---

## Phase C — Real-time Stability Verification

### Verification Items
- Input delay
- Order changes
- Candle dropouts

### Results
- ENTER decreases under delay
- No MAE increase
- No excessive entries

### Interpretation
The system **fails conservatively** in real-time environments.

→ **Production-ready**

---

## Phase D — ML Slot Isolation Design

### Question
"Can ML be used without contaminating the system?"

### Design Principles
- ML **cannot judge**
- ML **cannot modify coordinates**
- ML **cannot access actions**

### ML Role
- Used only in Observation Encoder
- Output: **uncertainty / confidence only**

```python
# Allowed
encoder.encode(features) -> uncertainty

# Forbidden
encoder.modify_state()
encoder.modify_action()
```

---

## Phase E — ML Constitution Verification

### ML v0.1
- DC estimation intervention
- Distribution distortion detected
- ❌ **FAIL**

### ML v0.2
- DC/τ untouched
- Uncertainty logging only
- Distribution change within ±2%
- ✅ **PASS**

### Core Statement
> "ML does not change coordinates. It only reports coordinate reliability."

---

## Phase F — Integrity Hardening

### Common Trait of All Removed Elements
> "The possibility of producing different outputs for the same input"

### Removed Items

| Before | After |
|--------|-------|
| float boundary comparison | Decimal bucketing |
| datetime.now() | candle.close_time_utc |
| Undefined cold start | ColdStartGuard |
| τ=4 allowed | τ≥5 enforced |
| ML action modification | Log-only |

### Integrity Checks
- I-1 ~ I-5: **ALL PASS**
- Same input → Same output: **100%**

---

## How Entry and Holding Are "Explained" by Data

In this system, entry and holding are  
**not decisions** but **observation results**.

The purpose of this section is to explain  
"why we entered / why we held"  
**through data, not rules or intuition**.

---

### 1. Entry Is Not a "Choice"

#### Entry Is an Intersection

Entry is defined solely by simultaneous satisfaction of these conditions:

```
ENTER ⟺ {
  DC ∈ {0.0, 1.0}    # Energy at distribution extreme
  τ ≥ 5              # Extreme state sustained long enough
  dir ≥ 3            # Direction formed and maintained
}
```

If any condition is unmet:
```
Action ∈ {WAIT, OBSERVE}
```

#### Important
- These conditions are **not selection criteria to improve probability**
- These conditions are **survival constraints to restrict entry**
- The system has no state of "wanting to enter"

> 📌 **Entry is a result, not a choice.**

---

### 2. Entry Is Verified by Its Rarity

Full dataset (35,064 candles):

| Action | Ratio |
|--------|-------|
| WAIT | ~79% |
| OBSERVE | ~20% |
| ENTER | **0.026%** |

→ This ratio is not the result of parameter tuning  
→ It is the **natural result of condition intersection**

If τ condition is relaxed:
- ENTER explosion
- Structural collapse
- Experimentally refuted in Phase B

> 📌 **Rarity itself is part of the entry definition.**

---

### 3. Holding Is Not a "Strategy"

#### No Additional Judgment in Holding

This system does not have:
- "When should I exit?"
- "Should I hold a bit longer?"
- "Is this a holding strategy?"

Holding is simply the continuation of two observations:

```
1. DC remains at extreme
2. τ increases
```

#### Mathematical Expression

```
τ_{t+1} = {
  τ_t + 1    if DC_t ∈ {0.0, 1.0}
  0          otherwise
}
```

→ **Holding is the process of τ increasing**

---

### 4. Holding Is "Natural Continuation", Not "Decision"

#### Key Observations
- Average Delta spikes in τ ≥ 7 regions
- Most failed signals have τ < 3
- Without sufficient τ, results don't materialize regardless of other conditions

That is:

> "Why did you hold so long?"  
> → Not because we decided to hold  
> → Because **the state continued to be maintained**

> 📌 **Holding is the observation result of state persistence.**

---

### 5. What Changes When Entry/Holding Are Explained by Data

#### Traditional Trading Questions
- Why did I enter here?
- Why did I hold here?
- Why couldn't I enter here?

#### This System's Questions
- Was DC at an extreme at this moment?
- Was that state maintained with τ ≥ 5?
- Was dir ≥ 3 satisfied?

---
### Verification Method Summary

All claims in this document are derived from:
- Full historical replay (35,064 candles)
- Phase A–F hypothesis tests with pre-fixed conditions
- Integrity checks (I-1~I-5) ensuring determinism and non-contamination
- Theory–code mapping audit confirming 1:1 correspondence

No simulated or optimized data was used.
All explanations are observational, not inferential.

## Final Declaration

This system:
- Was **not** built to predict better
- Was **not** built to enter more often

This system was built to:
> **Explain "when NOT to act" through data**

- Entry is a result.
- Holding is explained.
- Judgment is minimized.

---

## Current Status

| Phase | Status |
|-------|--------|
| Phase A–F | ✅ Complete |
| Theory–Code Consistency | ✅ Verified |
| Integrity Checks I-1~I-5 | ✅ ALL PASS |
| Post-Audit H-SHADOW-1~6 | ✅ ALL PASS |
| Real-time Shadow Mode | ✅ Ready |

> **The system is no longer "in development".**
