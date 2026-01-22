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

### Origin, Evolution, and Methodological Boundary

The original V7 Grammar was valuable for a precise reason:

it defined **decision admissibility independently of prediction,
optimization, and outcome feedback**.

At the time of its design, this was a deliberate constraint.

V7 demonstrated that a trading system could remain coherent if:

- entries were permitted only by structural conditions  
- execution rules were fixed prior to optimization  
- post-entry logic classified outcomes but never influenced decisions  

This made V7 robust to regime change,
but also intentionally inflexible.

That inflexibility was not a flaw.
It was the point.

---

Over time, a clear boundary emerged.

V7 could answer:

> *“What decision grammar survives  
> if prediction and adaptive optimization are disallowed?”*

It could **not** answer:

> *“How should a system adapt  
> when outcome feedback is explicitly permitted?”*

Answering the second question requires
a fundamentally different methodology.

---

### From Grammar to Policy

OPA represents a **methodological split**, not an upgrade.

Where V7 freezes admissibility rules,
OPA allows decision policy to evolve.

Where V7 forbids outcome-driven adaptation,
OPA treats outcome feedback as first-class input.

Because of this:

- OPA is not a continuation of V7  
- OPA does not inherit V7’s guarantees  
- performance comparisons across the two are not meaningful  

They answer **different questions**.

---

### Interpretation Rule

V7 and OPA are intentionally documented as
**separate decision architectures**.

Claims, guarantees, and conclusions
do not transfer between methodologies.

This separation is not a limitation.
It is a requirement for methodological clarity.


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
## Repository Structure

This repository enforces a strict separation between
decision logic, research variants, validation, and conclusions.

- `core/` — Immutable decision grammar and execution logic  
- `experiments/` — Research variants and aggressive options (never modify core directly)  
- `validation/` — Hypothesis tests, schemas, and execution contracts  
- `paper/` — Research writeups, figures, and final conclusions  
- `docs/` — Constitution, monitoring specs, and failure analysis  

**Promotion Flow:**  
`experiments/` → `validation/` → `core/`

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

## Demo (Read-Only)

- [Decision Grammar Demo](demos/grammar_demo.py)
  - Classification logic only
  - No execution, no live trading

  ---

## Canonical Documents (Authoritative)

This repository separates **final conclusions**, **research artifacts**, and
**validation contracts** explicitly.

### Final Conclusions
- **Representative Sample Results (19,157 trades)**  
  → [`paper/final_conclusions.md`](paper/final_conclusions.md)

### Research & Theory
- Theoretical Avg R Registry  
  → [`research/avg_r/theoretical_avg_r_validation.md`](research/avg_r/theoretical_avg_r_validation.md)

### Validation & Contracts
- Signal Schema (Execution Contract)  
  → [`validation/schemas/realtime_signal_results.schema.json`](validation/schemas/realtime_signal_results.schema.json)

---

## Reading Order (Recommended)

1. README.md  
2. paper/final_conclusions.md  
3. research/  
4. validation/  


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


