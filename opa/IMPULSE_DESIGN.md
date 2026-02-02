# Impulse as a First-Class Object in OPA

## Design Motivation

In OPA, delta (Δ) is explicitly treated as an **impulse**.

This choice is motivated by prior analysis showing that
impulse-like delta events were the dominant trigger of loss
when excluded from decision admissibility.

## Key Distinction

| System | Δ Treatment | Consequence |
|--------|-------------|-------------|
| V7 Grammar | Observed quantity | Classification only |
| OPA Policy | Impulse | Policy perturbation |

## Mathematical Formulation

```python
# V7: Δ = observation
state = classify(Δ)  # Deterministic

# OPA: Δ = impulse
Policy(t+1) = Policy(t) + f(Δ_t)  # Policy integrator
```

## Design Requirements

Unlike V7, OPA admits impulse as a policy input
and therefore must explicitly manage:

### 1. Impulse Accumulation Control
```
Risk: Silent drift from cumulative impulse effects
Solution: Accumulation decay function
```

### 2. Policy Drift Prevention
```
Risk: Policy diverges from constitutional bounds
Solution: Policy clipping / reset mechanisms
```

### 3. Boundary Sensitivity State
```
Risk: Impulse triggers loss only when boundary is fragile
Solution: Boundary sensitivity score tracking
```

### 4. Reset and Decay Mechanisms
```
Risk: Accumulated impulse persists beyond relevance
Solution: Time-based decay + event-triggered reset
```

## Impulse Definition

```python
IMPULSE_PROXIMITY = True if:
    |Δ_t| > quantile_90(|Δ|)
    AND t ∈ [STATE_lock − n₁, ENTRY + n₂]
```

Key: Use **quantile-based threshold**, not fixed value (regime independence).

## Why Not in V7?

V7 intentionally excluded impulse handling because:
1. Impulse introduces policy uncertainty
2. Constitutional defense requires deterministic classification
3. Execution integrity cannot be maintained with impulse admission

> **"V7 was not incorrect.  
> It was simply not designed to admit impulse."**

## OPA's Answer

OPA treats impulse as a first-class input, accepting the trade-off:
- More adaptive policy
- Higher complexity
- Requires explicit drift management

---

## Impulse Response Rule v0 (Defense Mechanism)

### Impulse Warning (IW) Definition

```python
IMPULSE_WARNING = True if:
    trade_open == True
    AND bar_index == entry_bar + 1
    AND |Δ_1| > quantile_90(|Δ|)
```

**Critical**: This is a post-entry signal, NOT a prediction.

### Defense Actions (on IW trigger)

| Option | Action | Risk |
|--------|--------|------|
| A | SL reduction | Less profit on recovery |
| B | Partial position close | Reduced exposure |
| C | Force EE evaluation | May exit prematurely |

### Evaluation Metrics

**DO NOT measure:**
- Total profit
- Win rate

**MUST measure:**
- Avg Loss reduction
- 95% tail loss reduction  
- Worst 5 losses reduction
- Non-impulse loss side effects

### Expected Outcome

```
Success: Loss severity ↓, Non-impulse unchanged
→ "Impulse cannot be predicted, but damage can be bounded"

Failure: No effect at 1-bar lag
→ "Response latency too high" → design constraint
```

---

## Boundary-Aware Impulse (COMMIT-023-B)

### Key Insight

```
Δ is NOT always an impulse.
Δ becomes impulse ONLY when decision boundary is fragile.

Impulse(Δ) = Δ × BoundarySensitivity
```

### BoundarySensitivity Formula

```python
BoundarySensitivity = (
    0.4 * state_sensitivity +    # STATE just locked?
    0.4 * stb_sensitivity +      # STB at minimum?
    0.2 * entry_sensitivity      # Just entered?
)

state_sensitivity = 1.0 if state_age <= 3 else 0.0
stb_sensitivity = 1.0 - clamp(stb_margin / 5.0, 0, 1)
entry_sensitivity = 1.0 if bars_since_entry <= 1 else 0.0
```

### Impulse Judgment (Formal)

```python
def is_impulse(delta, boundary_sensitivity, delta_q90):
    return (
        abs(delta) > delta_q90 and
        boundary_sensitivity >= 0.6
    )
```

### Defense Variants

| Variant | Action | Characteristic |
|---------|--------|----------------|
| A | SL *= 0.7 | Most conservative |
| B | Force EE | Structure-preserving |
| C | Position *= 0.5 | Maximum risk reduction |

### Core Statement

```
Δ is a value.
Impulse is "value acting as force on decision boundary."
Therefore, Δ is treated as impulse only when boundary is fragile.
```

---

**Source**: COMMIT-022, COMMIT-023, COMMIT-023-B  
**Status**: Design Specification  
**Date**: 2026-01-23
