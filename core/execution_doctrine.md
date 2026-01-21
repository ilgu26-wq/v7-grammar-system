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

### Base Unit Definition
```
1R = 10pt (SL-based risk unit)
```

### Account-Based Risk Formula
```python
contracts_base = Account × 0.25% / (10pt × pt_value)
```

**Example (NQ, 1pt = $20, Account = $50,000):**
```
1R = 10pt = $200
Risk allowance = $125 (0.25%)
→ base_size ≈ 0.62 contracts → 1 micro
```

### Stage-Based Sizing (PE × EV-BB)
```python
size = base_contracts × multiplier
```

| Stage | Condition | Multiplier |
|-------|-----------|------------|
| Stage 0 | STB + EE approved | 1.0x |
| Stage 1 | EV-BB + MFE ≥ 0.8×TP | 1.3x |
| Stage 2 | EV-BB + MFE ≥ 1.2×TP | 1.7x |
| Stage 3 | Micro+Macro EXTREME + EV-BB | 2.0x (max) |

### Safety Constraints
```
Maximum exposure: 2.0× base (NEVER exceed)
```

### Reset Rules
```python
if consecutive_losses >= 2:
    size = base_contracts
    freeze_scaling(5)  # 5 trades

if daily_drawdown >= 2R:
    stop_trading_today()
```

### Sizing Doctrine (Summary)
```
Base risk is defined by fixed SL (10pt).
Position size scales only after market approval (EV-BB),
never at entry.
Maximum exposure is capped at 2.0× base size.
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

## 7. TP Expansion Algorithm (PE × EV-BB)

### Design Principle
```
Expansion happens AFTER winning, not BEFORE.
```

### Prerequisites (Gate)
```
REQUIRED:
- STB fired
- EE >= 2.0 (CONFIRMED or higher)
```

### Stage 1: PE-Based Base TP
```python
if PE < 40:
    TP_base = 10   # PE_LOW
elif PE < 60:
    TP_base = 15   # PE_HIGH
else:
    TP_base = 25   # PE_EXTREME
```

### Stage 2: EV-BB Expansion Switch
```python
if EV_BB:
    expansion_allowed = True
else:
    expansion_allowed = False
```

### Stage 3: Step-by-Step Expansion
| Stage | Condition | TP |
|-------|-----------|-----|
| BASE | EE approved | TP_base |
| EXT_1 | EV-BB ON + MFE ≥ 0.8×TP | TP_base × 1.4 |
| EXT_2 | EV-BB ON + MFE ≥ 1.2×TP | TP_base × 2.0 |
| EXT_3 | Micro+Macro EXTREME + EV-BB | TP_base × 2.4 |

### Termination Rules
```python
# Immediate exit
if EE < 1.0:
    exit()

# Freeze expansion (keep current TP)
if not EV_BB:
    freeze_TP()

# Protection
if MAE > 0.6 * MFE:
    freeze_TP()
```

### Immutable Rules
```
- TP reduction is FORBIDDEN
- EV-BB standalone expansion is FORBIDDEN
- EE < 1.0 triggers immediate exit
- Expansion must follow stage order
```

### Validated Performance
| Metric | Fixed TP=25 | Dynamic TP |
|--------|-------------|------------|
| Total Profit | 12,029pt | 29,262pt |
| Avg Profit | 4.79pt | 11.65pt |
| Win Rate | 63.7% | 88.1% |
| Improvement | - | **+143%** |

| Stage | Win Rate | Avg PnL |
|-------|----------|---------|
| Stage 0 | 86.9% | 9.63pt |
| Stage 1 | 91.6% | 17.64pt |
| Stage 2 | **100%** | 25.13pt |
| Stage 3 | 88.2% | 48.87pt |

---

## 8. Execution Order (Fixed)

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

## 9. Core Principle

> "STB starts the sentence,
> EE approves the sentence,
> PE determines how long the sentence can be written,
> EV-BB only allows the sentence to be extended."

---

## 10. Performance Baseline (Validated)

| Metric | STB + EE ≥ 2.0 | Micro+Macro EXTREME |
|--------|----------------|---------------------|
| Win Rate | ~83% | ~97% |
| Avg RR (TP=25 / SL=10) | 2.99 | 5.03 |
| Avg MFE | ~30pt | ~50pt |
| Optimal Fixed TP | ~20pt | ~25pt |
| Trade EV (Fixed TP) | ~6.4pt | ~15.9pt |

**Daily Simulation (EXTREME only, Fixed TP):**
- Avg signals/day: ~31.7
- Avg PnL/day: ~244pt
- Profitable days: 100% (N=32)

**Note:**
Dynamic TP (PE × EV-BB) increases average EV to ~11–12pt
and daily PnL to ~700pt/day.

---

## 11. One-Line Summary

> "We don't profit by entering often.
> We profit by entering only twice at a time,
> at the most asymmetric moments."

---

*This document is the operational constitution of the V7 Grammar System.*
*Any modification requires validation with N ≥ 100 and OOS testing.*
