# V7 Grammar System

**NQ/MNQ Futures Trading System**  
**Git Lock Date:** 2026-01-21

---

## Overview

V7 is a probability system based on energy threshold crossing (MFE ≥ 7).

**Key Properties:**
- Losses only occur before energy state transition
- Post-transition loss probability = 0
- Soft SL reduces failure cost without altering alpha generation

---

## Directory Structure

```
v7-grammar-system/
├── core/                    # 🔒 LOCKED (production-grade)
│   ├── v7_energy_engine.py  # MFE trailing + SL Defense
│   ├── execution_doctrine.md # Trading rules
│   └── README.md
│
├── live/                    # 🚗 Execution engine
│   └── README.md
│
├── experiments/             # 🧪 Research variants
│   └── README.md
│
├── validation/              # 📊 Hypothesis tests
│   └── hypothesis_tests.md
│
├── paper/                   # 📄 Academic documentation
│   └── README.md
│
└── README.md                # This file
```

---

## Pre-Git Protocol: 6/6 Passed

| Test | Result |
|------|--------|
| H0-1 Time OOS | ✅ |
| H0-2 Bootstrap | ✅ |
| H0-3 Role Separation | ✅ |
| H0-4 Threshold Stability | ✅ |
| H0-5 Loss Grammar | ✅ |
| H0-6 Regime Independence | ✅ |

---

## Locked Parameters

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `MFE_THRESHOLD` | 7pt | State transition threshold |
| `TRAIL_OFFSET` | 1.5pt | Energy conservation (78%) |
| `LWS_BARS` | 4 | Loss Warning State trigger |
| `DEFENSE_SL` | 12pt | Reduced SL for LWS |
| `DEFAULT_SL` | 30pt | Base failure cost |

---

## Performance

| Metric | Base V7 | G3 Applied |
|--------|---------|------------|
| Win Rate | 80.9% | 78.6% |
| EV | +3.18pt | **+3.35pt** |
| Total PnL | +12,091pt | **+12,642pt** |
| Avg Loss | -30pt | **-25.2pt** |

---

## Constitutional Statement

> "MFE 7pt is a physics-level invariant (loss-free after state transition).
> MFE 5pt is a probabilistic optimization option that increases harvest rate
> at the cost of physical guarantees."

---

## Modification Policy

**core/ modifications require:**
- N ≥ 100
- OOS validation
- Loss physics audit
- 6/6 hypothesis tests passed

**DO NOT EDIT casually.**
# V7 Grammar System

An institutional-grade decision grammar framework for futures markets.

## Structure

- core/        : immutable decision grammar
- execution/   : execution constraints
- opa/         : optional policy agents
- docs/        : formal documentation

Research artifacts, experiments, and historical drafts are preserved in
`_raw_original/` for reference and auditability.

> This README is a structural entry point, not a full research narrative.

## Design Boundaries

- `core/` defines *what decisions are allowed*
- `execution/` defines *how allowed decisions are executed*
- `opa/` may influence execution **but can never override core decisions**

The core grammar remains invariant regardless of policy agents.
