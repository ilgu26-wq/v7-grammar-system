# EE (Expansion Eligibility) Definition

## Overview

EE is a post-entry continuation eligibility metric
used to determine whether a position is structurally worth maintaining.

---

## Formula

```
EE = MFE / MAE
```

Where:
- **MFE** = Maximum Favorable Excursion after entry
- **MAE** = Maximum Adverse Excursion after entry

---

## Classification

| EE Value | State | Action |
|----------|-------|--------|
| ≥ 1.0 | EE_HIGH | HOLD / CONTINUE |
| < 1.0 | EE_LOW | EXIT / TERMINATE |

---

## Key Properties

1. **Post-Entry Only**: EE is undefined before entry
2. **Non-Predictive**: EE does not forecast outcomes
3. **Structural**: EE reflects expansion capability, not edge

---

## Implementation

```python
def evaluate_ee(mfe, mae, min_bars=3):
    if bars_since_entry < min_bars:
        return "PENDING"
    
    ee = mfe / max(0.01, mae)
    
    if ee >= 1.0:
        return "EE_HIGH"
    else:
        return "EE_LOW"
```

---

## Role in V7 Grammar

EE is the continuation controller in the V7 system.
It does not influence entry decisions.

| Layer | Component | Function |
|-------|-----------|----------|
| Pre-Entry | STATE | Direction stabilization |
| Pre-Entry | STB | Entry timing |
| Pre-Entry | V7 Grammar | Entry authorization |
| Post-Entry | **EE** | Continuation control |

---

## Status

**Validated** — Integrated as post-entry continuation layer
