# Execution Doctrine

> V7 Grammar System - Operational Constitution
> Last Updated: 2026-01-20

---

## 1. Market Coverage

```
STB signals:        ~15.5% of total candles
EE ≥ 2.0:           ~5.7%
Micro+Macro EXTREME: ~1.1%
```

**Core Statement:**
> This system does not aim to trade the market.
> It extracts 6–12% of directional points
> from the highest-quality 1% regime.

---

## 2. Role Separation (Immutable)

| Element | Role | Usage |
|---------|------|-------|
| STB | Direction definition | ENTRY trigger |
| EE | Market acceptance verdict | HOLD / EXIT |
| PE | Distance estimator | TP calculation |
| EV-BB | Expansion permission | Extension only |

**Forbidden:**
```
EV-BB must NEVER be used as a standalone entry signal.
```

---

## 3. Sideways Doctrine

```
Sideways is a PAUSE, not an opportunity.
```

```python
if is_sideways:
    if breakout and ee1 >= 2.0:
        enter()        # Breakout
    elif micro_pe_extreme and macro_pe_extreme and ee1 >= 2.0:
        enter()        # Internal explosion
    else:
        wait()         # Rest
```

---

## 4. Position Management

| Parameter | Value |
|-----------|-------|
| Max simultaneous positions | **2** |
| TP | 25pt |
| SL | 10pt |

---

## 5. Sizing Constitution

| Verdict | Condition | Contracts |
|---------|-----------|-----------|
| **STRONG_CONFIRM** | EE ≥ 2.0 + RISING + Micro&Macro EXTREME | 2 |
| **EXTREME** | EE ≥ 2.0 + Micro&Macro EXTREME | 1 |
| CONFIRMED | EE ≥ 2.0 | 0 (analysis only) |
| OBSERVE | EE 0.5~2.0 | 0 |
| REJECT | EE < 0.5 | 0 |

```python
if STRONG_CONFIRM:
    size = 2
elif EXTREME:
    size = 1
else:
    trade = False
```

---

## 6. Position Energy (PE) Physics

PE represents the potential distance available after market acceptance.
It does NOT determine entry eligibility.

### Definition
```
PE_short = (channel_pct / 100) × rolling_range
PE_long  = ((100 - channel_pct) / 100) × rolling_range
```

### Interpretation
- PE measures "how far price can travel" after acceptance
- Higher PE implies larger potential MFE
- PE does NOT imply directional correctness

> Price can only fall far if it is both:
> 1) Positioned high (PE)
> 2) Pushed by the market (EE)

### PE Grades (Operational)
| Grade | Condition | Distance |
|-------|-----------|----------|
| PE_LOW | < 40pt | Short distance |
| PE_HIGH | 40–60pt | Medium distance |
| PE_EXTREME | ≥ 60pt | Long distance / expansion eligible |

### Role Constraint
```
PE is NOT an entry signal.
```

PE can only be evaluated AFTER:
- STB has defined direction
- EE has confirmed acceptance (EE ≥ 2.0)

**Forbidden:**
- Entry based on PE alone
- PE used to override EE rejection

### TP Mapping (Distance Only)
| PE Grade | TP Range |
|----------|----------|
| PE_LOW | ~10pt |
| PE_HIGH | 15–20pt |
| PE_EXTREME | 25–50pt |

---

## 7. Execution Order (Fixed)

```
1. STB occurs → Direction defined
2. EE ≥ 2.0 → Market approval
3. PE/EV-BB → Expansion permission (optional)
```

**System collapses if:**
- EV-BB standalone entry
- Frequent re-entry during sideways
- STB → EE → PE order ignored

---

## 8. Core Principle

> "STB starts the sentence,
> EE approves the sentence,
> PE determines how long the sentence can be written,
> EV-BB only allows the sentence to be extended."

---

## 9. Performance Baseline (Validated)

| Metric | STB+EE | EXTREME |
|--------|--------|---------|
| Win Rate | 83% | 97% |
| Avg RR | 2.99 | 5.03 |
| Avg MFE | 30pt | 50pt |
| Optimal TP | 20pt | 25pt |
| EV per trade | 6.4pt | 15.9pt |

**Daily Simulation (EXTREME only):**
- Avg signals: 31.7/day
- Avg profit: 244pt/day
- Profitable days: 100% (N=32)

---

## 10. One-Line Summary

> "We don't profit by entering often.
> We profit by entering only twice at a time,
> at the most asymmetric moments."

---

*This document is the operational constitution of the V7 Grammar System.*
*Any modification requires validation with N ≥ 100 and OOS testing.*
