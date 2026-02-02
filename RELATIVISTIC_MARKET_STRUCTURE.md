# Relativistic Market Structure Engine

> **This is not a trading strategy.**
> This document formalizes empirically verified market safety laws
> discovered via structural observation.

---

## 1. Problem Statement

### Why Existing Approaches Fail

Price prediction fails repeatedly. The cause is not faulty probability estimation—it is **world state misidentification**.

> **"Markets do not fail because predictions are wrong.**
> **They fail because decisions are made in dead worlds."**

---

## 2. Core Axiom — Irreversibility Reframed

### The Common Misconception

| Belief | Reality |
|--------|---------|
| Irreversibility = Energy loss | Irreversibility = Freedom collapse |
| Storm = Chaos | Storm = Constrained energy paths |

Energy remains present. Only dispersion paths disappear.

> **"Irreversibility is not energy loss.**
> **It is the collapse of degrees of freedom."**

---

## 3. Observables

The system observes structural state, not price movement.

| Observable | Description |
|------------|-------------|
| **IE** (Intersection Energy) | Field coherence measure |
| **RI** (Rupture Index) | Pressure accumulation indicator |
| **ECS** (Energy Connectivity Score) | System connectivity measure |
| **ZPOC** | Volume-weighted price center anchor |
| **Recovery** | Post-collapse momentum flag |
| **HTF** | Higher timeframe trend presence |
| **Freedom Index** | Available energy dispersion paths |

### Freedom Index (v2.1 Core)

> Freedom Index measures the number and quality of
> available energy dispersion paths.

```
Freedom = f(ECS stability, ZPOC presence, transition density, stress flags)
```

| Freedom State | Condition | Action |
|---------------|-----------|--------|
| HIGH | Index ≥ 0.65 | ALLOW possible |
| MEDIUM | 0.45 ≤ Index < 0.65 | THROTTLE |
| LOW | 0.25 ≤ Index < 0.45 | KILL |
| COLLAPSED | Index < 0.25 | KILL |

---

## 4. World Structure

### 4.1 Macro Structure (Solar System)

```
┌─────────────────────────────────────────────────────────┐
│                    RUPTURE_RIDGE                        │
│              (RI > q95 or ZPOC_DEATH)                   │
│                  100% collapse zone                      │
├─────────────────────────────────────────────────────────┤
│                   TRANSITION_ZONE                        │
│                   (IE 2.3 - 2.8)                         │
│              High transition probability                 │
├─────────────────────────────────────────────────────────┤
│                    STABLE_BASIN                          │
│                   (IE 2.8 - 3.8)                         │
│            Hazard stratification applies                 │
├─────────────────────────────────────────────────────────┤
│                    NOISE_FIELD                           │
│                    (IE > 3.8)                            │
│              Statistical noise zone                      │
└─────────────────────────────────────────────────────────┘
```

### 4.2 Micro Structure (Planets)

| Planet | Condition | Hazard | Meaning |
|--------|-----------|--------|---------|
| **P3_CLEAN** | IE ≥ 2.85, Clean | 6% | Safe world |
| **P3_STRESSED** | IE ≥ 2.85 + Recovery/HTF | 26% | Amplifier world |
| **P2_DANGER** | 2.75 ≤ IE < 2.85 | 27% | Danger world |
| **P1_DANGER** | IE < 2.75 | 31% | Maximum danger |

> **"Markets are not a single probability space,**
> **but a relativistic system of multiple worlds."**

---

## 5. Laws

### 5.1 World Transition Law (100% Causal)

| Trigger | Result | Confirmation |
|---------|--------|--------------|
| RI_SPIKE (> q95) | 100% RUPTURE | Empirically verified |
| ZPOC_DEATH | 100% RUPTURE | Empirically verified |

These are not probabilities. They are deterministic transitions.

### 5.2 Resonance Law

> **Definition:** ≥3 planet transitions within 10 bars

| Condition | SPIKE Rate | Amplification |
|-----------|------------|---------------|
| Normal (P3_CLEAN) | 6% | baseline |
| Resonance Zone | 14-17% | ×2.3 |

### 5.3 Freedom Law (v2.1 Core Discovery)

| Freedom Level | SPIKE Rate |
|---------------|------------|
| HIGH | ~8% |
| LOW | ~50% |

> **"Resonance is not the cause of collapse.**
> **It is a byproduct of freedom loss."**

---

## 6. Causal Chain

```
         Freedom Collapse
              ↓
       Path Restriction
              ↓
    Resonance Amplification
         (optional)
              ↓
          RI Spike
              ↓
          RUPTURE
```

This is not unpredictable.
This is an **observable causal chain**.

---

## 6.5 Directional Asymmetry Under Macro Energy

> **Why direction becomes observable only near rupture**

This system does not predict price direction.

However, under specific structural conditions, 
a **directional asymmetry** becomes observable.

This asymmetry is not a signal.
It is a **structural bias revealed only near rupture**.

---

### Macro PE vs Micro PE

We distinguish two forms of potential energy:

| Type | Role |
|------|------|
| **Macro PE** | Determines *whether rupture is possible* (RI, IE) |
| **Micro PE** | Determines *which direction rupture prefers* (Force imbalance) |

> Macro PE controls *possibility*.  
> Micro PE controls *realization*.

---

### Experimental Result (EXP-PE-DUAL-FRAME-01)

| Condition | Direction Accuracy |
|-----------|-------------------|
| Micro PE alone | ~43% (near random) |
| Macro PE Q1 (low) | 37% |
| Macro PE Q4 (high) | **48%** |
| Amplification | **+11%** |

> Directional asymmetry exists **only when macro energy is sufficient**.

---

### Structural Interpretation

Direction is not continuously present in the market.

It emerges only when:

1. Freedom is reduced but not collapsed
2. Resonance is active
3. Macro energy exceeds a critical threshold

In fully stable worlds, asymmetry is absorbed.  
In collapsed worlds, asymmetry is irrelevant.  

**Only near the boundary does direction appear.**

---

### Engine Usage Constraint (Critical)

Directional asymmetry:

- **MUST NOT** be used for entry
- **MUST NOT** be treated as prediction
- **MAY** be used only as:
  - Exit bias
  - Hedge direction hint
  - Risk skew adjustment

```python
if ALLOW and macro_pe >= Q4 and abs(micro_pe) > threshold:
    direction_hint = sign(micro_pe)
else:
    direction_hint = None  # symmetric, no hint
```

---

### Final Statement

> **Direction is not a market property.**
>
> **It is a conditional structural artifact,**
> **visible only when a living world approaches rupture.**

---

## 7. Engine Implementation (v2.1)

### Decision Logic

```python
if FREEDOM == COLLAPSED:
    return KILL, "FREEDOM_COLLAPSE"
elif FREEDOM == LOW:
    return KILL, "LOW_FREEDOM"
elif axiom_triggered:  # RI_SPIKE or ZPOC_DEATH
    return KILL, axiom_reason
elif resonance_detected:
    return KILL, "RESONANCE"
elif planet != P3_CLEAN:
    return KILL, "DANGER_PLANET"
elif FREEDOM == MEDIUM:
    return THROTTLE
else:
    return ALLOW
```

### Engine Philosophy

> **The engine does not optimize profit.**
> **It optimizes survival.**

---

## 8. What This System Is / Is Not

### Is

- Market safety layer
- World validity detector
- Structural risk firewall
- Freedom observation system

### Is Not

- Alpha generator
- Price predictor
- Optimization engine
- Probability calculator

---

## 9. Validation Results

### Engine v2.1 Statistics (19,350 bars)

| Metric | Value |
|--------|-------|
| ALLOW rate | 29.5% |
| KILL rate | 70.5% |
| Avg Freedom Index | 0.789 |

### Freedom Distribution

| State | Percentage |
|-------|------------|
| HIGH | 91.4% |
| MEDIUM | 3.4% |
| LOW | 2.1% |
| COLLAPSED | 3.1% |

### Kill Reasons

| Reason | Percentage |
|--------|------------|
| DANGER_PLANET | 52.2% |
| RESONANCE | 11.0% |
| RI_SPIKE | 5.0% |
| ZPOC_DEATH | 1.1% |
| LOW_FREEDOM | 0.7% |
| FREEDOM_COLLAPSE | 0.5% |

---

## 10. Final Statements

> **"We do not predict prices.**
> **We observe freedom."**

> **"Storms occur not because energy appears,**
> **but because freedom disappears."**

> **"Trading is allowed only in living worlds."**

---

## Appendix: Key Files

| File | Purpose |
|------|---------|
| `engine/realtime_engine_v2.py` | Production engine (v2.1) |
| `NEXT_PHASE/exp_world_transition_01.py` | World transition law verification |
| `NEXT_PHASE/exp_hazard_to_spike_01.py` | Hazard stratification experiment |
| `NEXT_PHASE/exp_microplanet_def_01.py` | Micro-planet definition |
| `NEXT_PHASE/exp_planet_hypothesis_01.py` | Planet-specific laws testing |
| `NEXT_PHASE/exp_interplanet_dynamics_01.py` | Resonance law discovery |
| `NEXT_PHASE/exp_resonance_freedom_01.py` | Freedom-resonance causality |
| `results/*.json` | All experiment results |

---

**Engine Version:** 2.1
**Last Updated:** 2026-02-02
**Status:** Production Ready
