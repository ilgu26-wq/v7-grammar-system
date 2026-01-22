# V7 Execution Doctrine (LOCKED)

**Git Lock Date:** 2026-01-21  
**Pre-Git Protocol:** 6/6 Passed

---

## ⚠️ LOCKED CONSTITUTION

This document contains the production-grade execution rules.
Any modification requires:
- N ≥ 100
- OOS validation
- Loss physics audit

**DO NOT EDIT casually.**

---

## 1. Entry (STB)

```python
if ratio > 1.5 and channel_pct > 80 and body_z >= 1.0:
    direction = 'SHORT'
elif ratio < 0.7 and channel_pct < 20 and body_z >= 1.0:
    direction = 'LONG'
```

**No EE filter.** All STB signals are allowed.

---

## 2. Energy Management (MFE Trailing)

```python
MFE_THRESHOLD = 7      # State transition threshold (LOCKED)
TRAIL_OFFSET = 1.5     # Energy conservation 78% (LOCKED)

if mfe >= MFE_THRESHOLD:
    trailing_stop = entry + (mfe - TRAIL_OFFSET)  # LONG
    trailing_stop = entry - (mfe - TRAIL_OFFSET)  # SHORT
```

**Physics Law:** Post-threshold (MFE ≥ 7) loss probability = 0

---

## 3. SL Defense (G3)

```python
LWS_BARS = 4           # Loss Warning State trigger
LWS_MFE_THRESHOLD = 1.5
DEFENSE_SL = 12
DEFAULT_SL = 30

if bars >= LWS_BARS and mfe < LWS_MFE_THRESHOLD:
    SL = DEFENSE_SL    # Reduce failure cost
else:
    SL = DEFAULT_SL
```

**Effect:** Average loss -30pt → -25.8pt (14% reduction)

---

## 4. Physics Laws

| Law | Description |
|-----|-------------|
| Energy Threshold | MFE ≥ 7pt = state transition (loss-free) |
| Energy Conservation | trail 1.5pt = 78% conservation |
| No EE Filter | Filter removal = best performance |
| Direction Agnostic | LONG/SHORT same rules |
| IMPULSE | External shock = unpredictable, accept only |
| SL Defense | 4 bars + MFE < 1.5 → SL 12pt |

---

## 5. Prohibited Actions

- ❌ Change MFE threshold (7pt locked)
- ❌ Change trail value (1.5pt locked)
- ❌ Reintroduce EE filter
- ❌ Add dynamic TP (EV-BB/EE based)
- ❌ Session-based retuning

---

## 6. Validated Performance (57,640 candles)

| Metric | Base V7 | G3 Applied |
|--------|---------|------------|
| Signals | 1,167 | 1,167 |
| Win Rate | 80.9% | 78.6% |
| EV | +3.18pt | **+3.35pt** |
| Total PnL | +12,091pt | **+12,642pt** |
| Avg Loss | -30pt | **-25.2pt** |

---

## 7. Constitutional Statement

> "MFE 7pt is a physics-level invariant (loss-free after state transition).
> MFE 5pt is a probabilistic optimization option that increases harvest rate
> at the cost of physical guarantees."

---

**Note:**  
MFE ≥ 7 represents a statistical energy threshold observed across
multiple parameter plateaus (5-7pt).
The value 7 is selected as the conservative core setting.
