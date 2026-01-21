# V7 Grammar System

*An institutional-grade decision grammar framework for futures markets,
validated across assets, regimes, and execution constraints.*

## A Decision Grammar System, Not a Forecasting Engine

> **"This system does not predict markets.
> It classifies decision states.
> Prediction modules can be added without destabilizing the core."**

---

## Core Philosophy

V7 Grammar System was intentionally designed **not to predict market direction**.

Instead, it defines a **decision grammar** that classifies market states and
constrains execution under uncertainty.

Because the decision layer is structurally independent from prediction,
any forecasting or alpha-generating module can be integrated without
destabilizing execution integrity, risk semantics, or portfolio behavior.

> **In this architecture, prediction is optional; decision quality is mandatory.**

---

## Why This Matters

| Approach | Stability |
|----------|-----------|
| Prediction without decision grammar | Unstable |
| Decision grammar without prediction | **Stable** |

Decision criteria are fixed by design.
Predictions may fail; the judgment framework must not.

---

## Extensibility Declaration

> Any predictive alpha can be plugged into this system
> without affecting execution integrity or risk semantics.

[ Market Data ]
        ↓
[ Decision Grammar (V7) ]   ← Core (Immutable)
        ↓
[ Execution Constraints ]
        ↓
[ Capital / Risk ]

[ Predictive Alpha (Optional) ]
                ↓
       (feeds into Decision Grammar)

---

## Overview

V7 Grammar System is a quantitative decision-grammar framework for futures
markets (NQ / ES / BTC).

The system does not forecast price direction.
Instead, it classifies **market decision states**
and enables **conditional alpha expression**
under explicitly constrained execution rules.

Trade frequency is intentionally limited.
The system prioritizes **decision quality over activity**.

Conditional alpha is expressed only after structural validity
has been established, and never alters entry criteria.


## System Architecture

| Layer | Module | Function |
|------:|--------|----------|
| 1 | STATE | Direction stabilization (Long / Short) |
| 2 | STB | Entry timing & execution ordering |
| 3 | V7 Grammar | Outcome classification & continuation control (EE / HL) |

Post-entry continuation control (EE) is strictly non-predictive
and evaluated **after execution**.

Detailed definitions and empirical validation:
→ [EE Definition](docs/grammar/ee_definition.md) 
→ [EE Continuation Manager](docs/validation/ee_continuation_manager.md)

## Key Metrics

| Component | Metric | Definition |
|-----------|--------|------------|
| Ratio | Price Momentum | (close - low) / (high - close) |
| Channel% | Price Position | Relative position in 20-bar range |

---
## Validation Summary (Decision-Grammar Level)

### 24 / 24 Independent Tests Passed

| Case | Target | Result |
|------|--------|--------|
| A | ES (S&P 500) | 5 / 5 PASS |
| B | BTC1 + Roll Events | 6 / 6 PASS |
| C | Multi-Timeframe (1m–1h) | 4 / 4 PASS |
| D | Event Stress (COVID / CPI / Banking) | 5 / 5 PASS |
| E | Portfolio Independence | H_E1, H_E3 PASS |
| F | Execution Integrity | 4 / 4 PASS |

**Logic Modifications: 0**

All validation results were obtained
without parameter tuning or rule adjustment.

### Proven Properties

- **Asset-Agnostic**: Identical logic across NQ / ES / BTC
- **Time-Invariant**: Structural consistency from 1-minute to 1-hour
- **Regime-Robust**: COVID, CPI shocks, banking crisis survived
- **Roll-Robust**: Stable behavior during futures roll events
- **Portfolio-Ready**: Zero triple-simultaneous occurrence
- **Operationally Sound**: Human-followable execution

---

## Decision-Integrity Metrics (Non-Portfolio Scope)

The following metrics are reported solely to validate
execution ordering and decision integrity
under fixed grammar and execution rules.

| Metric | Value | Scope |
|--------|-------|-------|
| STB TP-first Rate | 94.1% | Conditional STB execution |
| Sharpe Ratio | 3.84 | Conditional execution sequence |
| Sortino Ratio | 21.34 | Conditional execution sequence |

Portfolio-level performance metrics are intentionally excluded.

These metrics do not imply directional forecasting accuracy.

---

## Documentation

- [V7 Grammar Table v1.0](v7_grammar_table.md)
- [Strategy Overview](strategy_overview.md)
- [Validation Cases (A–F)](validation/validation_cases.md)
- [Live Results](live_results.md) *(In Progress)*

---

## Repository Data Policy

- Live operational data files
  (`realtime_signal_results.json`, `ops_log.json`)
  are **explicitly excluded from version control**.
- This repository contains **definitions, contracts,
  and validation results**, not live performance outcomes.

  
---

## Communication Samples

Application-style communication examples are provided separately
for illustrative purposes only.

→ [Sample Application Document](cover_letter.md)

---

## Current Stage

- Core decision grammar: **COMPLETE & LOCKED**
- Structural validation: **FINISHED (24/24 tests passed)**
- Live shadow trading: **IN PROGRESS (metric promotion pending)**

No further logic changes are planned.
Only data accumulation is ongoing.

---

## Key Statement

> **"We know exactly where we make money,
> and we intentionally do not try elsewhere."**


---

## Grade

**S (Superior)** — Institutional-grade validation achieved

Grade reflects validation rigor and execution integrity,
not portfolio return.

---

*Updated: 2026-01-20*


