> ⚠️ **Research Note**
>  
> This README describes the **design constitution** of the V7 Grammar System.  
> The **final empirical judgment and alpha interface** are documented in  
> 👉 [README_v2 — Final Judgment & Forward Interface](README_v2.md)


## Project Status

The V7 Grammar System decision grammar is **structurally frozen**.

No further changes are planned to:
- V7 decision grammar
- core admissibility rules
- validated execution constraints

Ongoing work is limited to:
- live data observation
- execution-layer integration
- risk behavior monitoring

These activities do not modify decision logic.
They operate strictly on top of the frozen grammar.





# V7 Grammar System

*An institutional-grade decision grammar framework for futures markets,
validated across assets, regimes, and execution constraints.*

## A Decision Grammar System, Not a Forecasting Engine

> **"This system does not predict markets.
> It classifies decision states.
> Prediction modules can be added without destabilizing the core."**

## Operational Status

As of 2026-01-25, the V7 Grammar System is in a
**coverage-complete, paper-validated state**.

All observed trades are guaranteed to be classified into
predefined coverage buckets (UNKNOWN rate = 0%).

The main branch represents:
- Decision grammar (V7)
- Policy layer (OPA v7.4)
- Coverage audit and residual failure registry

Execution logic and real-time usage are introduced incrementally
and do not alter the underlying decision grammar.

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

This repository enforces a **strict separation** between
decision logic, research variants, validation, and conclusions.

Each directory has a **non-overlapping responsibility**.

core/         — Immutable decision grammar and execution logic
experiments/ — Research variants and aggressive options
validation/  — Hypothesis tests, schemas, and execution contracts
paper/       — Research writeups, figures, and final conclusions
docs/        — Constitution, monitoring specs, and failure analysis

### Directory Contracts

- `core/`
  - Contains only **fully validated decision logic**
  - No experimental parameters
  - Modified **only after passing validation**

- `experiments/`
  - Free-form research and exploratory logic
  - May fail, overfit, or be discarded
  - **Never modifies core directly**

- `validation/`
  - Formal hypothesis tests
  - Statistical and structural verification
  - Defines promotion eligibility

- `paper/`
  - Human-readable research conclusions
  - Final results suitable for external review

- `docs/`
  - System constitution and operational doctrine
  - Monitoring rules and failure analysis

### Promotion Flow

All logic follows a one-way promotion pipeline:

experiments/ → validation/ → core/

No logic or parameter is allowed into `core/`
without passing explicit validation criteria.

### Design Philosophy

Prediction may fail.
Experiments may fail.
But decision logic must not.

This structure ensures that
research volatility never contaminates execution integrity.


## Authoritative Documents (Frozen)

The following documents represent **finalized, non-experimental conclusions**.
They are not subject to further modification.

## Archived Snapshot

A frozen archival snapshot of verified conclusions
(as of **2026-01-23**) is preserved here:

→ `docs/ARCHIVE_2026_01_23.md`

This snapshot marks the formal closure of V7 grammar research.
Any future changes require a new dated archive.

### Final Conclusions
- **Representative Sample Results (19,157 trades)**  
  → [`paper/final_conclusions.md`](paper/final_conclusions.md)

These conclusions are considered **structurally complete**.
No further logic changes are planned.

## Research, Validation & Contracts

This repository explicitly separates
research artifacts, validation logic, and execution contracts.

### OPA (Operational Policy Authority)

OPA defines **execution permission and sizing policy**
on top of the immutable V7 decision grammar.

- **OPA v7.4 Operator Guide (Production)**  
  → [`docs/OPA_V74_OPERATOR_GUIDE.md`](docs/OPA_V74_OPERATOR_GUIDE.md)

- **STB Sensor vs OPA Execution Analysis (Empirical)**  
  → [`docs/opa/opa_stb_sensor_analysis.md`](docs/opa/opa_stb_sensor_analysis.md)

OPA is a policy layer, not a strategy.
Performance claims do not transfer back to V7.

### Research & Theory
- Theoretical Avg R Registry  
  → [`research/avg_r/theoretical_avg_r_validation.md`](research/avg_r/theoretical_avg_r_validation.md)

### Validation & Contracts
- Signal Schema (Execution Contract)  
  → [`validation/schemas/realtime_signal_results.schema.json`](validation/schemas/realtime_signal_results.schema.json)


### Current Status (OPA)

- V7 decision grammar: frozen as a reference baseline
- OPA decision policy: under active development
- Outcome-driven adaptation: enabled in a controlled manner
- Live shadow trading: in progress (policy learning phase)

Structural guarantees apply **only** to the V7 grammar.
OPA operates under a separate, explicitly adaptive methodology.

As OPA evolves, policy updates may occur.
Validation focuses primarily on stability bounds and failure containment,
rather than on strict frozen-rule invariance.
---

### Empirical Validation Anchor (OPA θ=2)

The validity of θ=2 as a state transition point and linear size scaling
is empirically supported by reproducible research artifacts:

- `research/opa_theta2/theta2_sensor_results.json`
- `research/opa_theta2/theta_2_transition_results.json`
- `research/opa_theta2/size_scaling_results.json`

These artifacts demonstrate that OPA operates as a **state machine**,
not a probabilistic filter.


---

## Communication Samples

Application-style communication examples are provided separately
for illustrative purposes only.

→ [Sample Application Document](cover_letter.md)

---


## Documentation

- [V7 Grammar Table v1.0](docs/grammar/v7_grammar_table.md)
- [Strategy Overview](docs/strategy_overview.md)
- [Validation Cases (A–F)](validation/validation_cases.md)
- [Live Results](live_results.md) *(In Progress)*

---

## Demo (Read-Only)

- [Decision Grammar Demo](demos/grammar_demo.py)
  - Classification logic only
  - No execution, no live trading

  ---
## Thinking Evolution

This system was not designed in a single step.

Its development history is documented as a git-style commit timeline,
showing how unstable ideas were systematically eliminated:

- [Thinking Evolution (Git-style)](docs/THINKING_EVOLUTION_GIT_STYLE.md)
- [V7 Constitution](docs/V7_CONSTITUTION.md)
> The Graveyard Appendix documents hundreds of tested ideas that failed,
> and explains why only the current V7 Grammar survived.

## System Integrity & Validation

This repository includes an explicit system integrity audit
based on live paper execution.

**Guarantees:**
- No execution without a prior V7 decision
- No execution at theta ≥ 3
- No hidden or silent signal influence
- Fully reproducible results

Representative validation:
- [System Integrity Validation Summary](analysis/validation/validation_summary.md)

Full validation suite:
- [`analysis/validation/`](analysis/validation/)



## Key Statement

> **"We know exactly where we make money,
> and we intentionally do not try elsewhere."**


---

## Grade

**S (Superior)** — Institutional-grade validation achieved

Grade reflects validation rigor and execution integrity,
not portfolio return.

---

*Updated: 2026-01-25*


