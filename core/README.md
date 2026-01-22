# ⚠️ LOCKED CONSTITUTION

This directory contains the production-grade,
hypothesis-validated V7 trading system.

**Any modification requires:**
- N ≥ 100
- OOS validation
- Loss physics audit

**DO NOT EDIT casually.**

---

## Git Lock Date: 2026-01-21

## Pre-Git Protocol: 6/6 Passed

| Test | Result | Key Metric |
|------|--------|------------|
| H0-1 Time OOS | ✅ | Train 80.8% → Test 83.1% |
| H0-2 Bootstrap | ✅ | G3 > G0 ratio 57.5% |
| H0-3 Role Separation | ✅ | MFE≥7 LOSS = 0 |
| H0-4 Threshold Stability | ✅ | EV plateau 0.44pt |
| H0-5 Loss Grammar | ✅ | Avg loss -30 → -25.8pt |
| H0-6 Regime Independence | ✅ | All regimes EV positive |

---

## Core Files

| File | Purpose |
|------|---------|
| `v7_energy_engine.py` | MFE trailing + SL Defense (G3) |
| `execution_doctrine.md` | Trading rules (LOCKED) |
| `stb_entry.py` | STB entry conditions |
| `risk_engine.py` | Risk management |

---

## Constitutional Statement

> "MFE 7pt is a physics-level invariant (loss-free after state transition).
> MFE 5pt is a probabilistic optimization option that increases harvest rate
> at the cost of physical guarantees."

---
## Core Contract

Files in this directory define the **immutable decision grammar** of V7.

Rules:
- No predictive logic
- No parameter tuning based on market outcomes
- No experimental code

Any modification here must preserve:
- execution ordering invariants
- post-entry non-predictive evaluation
- risk semantics consistency

## Locked Parameters

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `MFE_THRESHOLD` | 7pt | State transition threshold |
| `TRAIL_OFFSET` | 1.5pt | Energy conservation (78%) |
| `LWS_BARS` | 4 | Loss Warning State trigger |
| `LWS_MFE_THRESHOLD` | 1.5pt | Energy failure threshold |
| `DEFENSE_SL` | 12pt | Reduced SL for LWS |
| `DEFAULT_SL` | 30pt | Base failure cost |


