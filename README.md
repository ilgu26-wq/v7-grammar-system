# V7 Grammar System

*An institutional-grade decision grammar framework for futures markets, validated across assets, regimes, and execution constraints.*

## A Decision Grammar System, Not a Forecasting Engine

> **"This system does not predict markets. It classifies decision states.
> Prediction modules can be added without destabilizing the core."**

---

## Core Philosophy

This system was intentionally designed **not to predict market direction**.
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

This system freezes the decision criteria. Predictions can fail; the judgment framework cannot.

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

V7 Grammar System is a quantitative trading framework for futures markets (NQ/ES/BTC) that generates **Conditional Alpha** through market state classification rather than price prediction.

> **The system averages 50–70 decision-quality trades per month, prioritizing precision over frequency.**

### Key Statement

> "This is not a return-maximizing strategy.  
> It is a conditional alpha system that maximizes  
> decision quality under uncertainty."

---

## System Architecture

| Layer | Module      | Function |
|------|-------------|----------|
| 1    | STATE       | Direction Stabilization (Long / Short) |
| 2    | STB         | Entry Timing (94.1% TP-first) |
| 3 | V7 Grammar | Outcome Classification (EE / HL) |

### Structural Components

SPS (Structural Pressure Score) represents the relative strength of opposing market forces,
used to compare directional pressure rather than to smooth volatility.

STB functions as a stabilization and filtering layer, suppressing noise induced by volatility
and allowing only structurally meaningful conditions to trigger entries.



### Key Metrics

| Component | Metric | Definition |
|-----------|--------|------------|
| Ratio | Price Momentum | (close - low) / (high - close) |
| Channel% | Price Position | Relative position in 20-bar range |

---

## Validation Summary

### 24/24 Independent Tests Passed

| Case | Target | Result |
|------|--------|--------|
| A | ES (S&P 500) | 5/5 PASS |
| B | BTC1 + Roll Events | 6/6 PASS |
| C | Multi-Timeframe (1m~1h) | 4/4 PASS |
| D | Event Stress (COVID/CPI/Bank) | 5/5 PASS |
| E | Portfolio Independence | H_E1,H_E3 PASS |
| F | Execution Integrity | 4/4 PASS |

## Interpretation Scope

This repository evaluates the system at a **decision grammar level**.

Trade-level outcome metrics may differ across documents depending on
their interpretive scope:
- structural validation,
- operational behavior,
- or communication examples.

Numerical differences across documents are expected and intentional,
as each document serves a **distinct evaluation purpose**.


**Logic Modifications: 0**

### Proven Properties

- **Asset-Agnostic**: Identical logic across NQ/ES/BTC
- **Time-Invariant**: 1-minute to 1-hour structure preserved
- **Regime-Robust**: COVID, CPI shocks, banking crisis survived
- **Roll-Robust**: Superior performance during roll events
- **Portfolio-Ready**: Zero triple-simultaneous occurrence
- **Operationally Sound**: Human-followable execution

---

## Performance Metrics (Decision-Integrity Scope)

> **Important:**  
> Metrics reported in this section are provided **only to validate
> decision integrity and execution consistency**.  
> This document does **not** report portfolio-level performance.

All metrics are calculated under **conservative assumptions**, where:
- suppressed states,
- inactive states,
- and non-entry conditions  
are treated as neutral or unfavorable outcomes.

### Reported Metrics

| Metric | Value | Scope |
|------|------|------|
| STB TP-first Rate | 94.1% | Conditional STB execution only |
| Sharpe Ratio | 3.84 | Conditional STB execution sequence |
| Sortino Ratio | 21.34 | Conditional STB execution sequence |

### Theoretical Avg R Registration Policy

The theoretical Avg R (1.823R) is registered as a reference value only.

It will be promoted to an official README metric after all of the following
conditions are satisfied:

- n ≥ 100 live shadow trades
- Absolute deviation |ΔR| ≤ 0.30 compared to the theoretical value
- 95% confidence interval includes 1.823R

Until these conditions are met, the value remains contract-defined
but unverified, and is excluded from performance summaries by design.


### Intentionally Excluded Metrics

The following metrics are **intentionally excluded** from this document:

- Average R per Trade  
- Recovery Factor  
- Portfolio-level P&L  

These metrics are reported **only in operational summaries or
evaluation documents**, as they do **not** serve to validate the grammar itself.

> **This is a design choice, not missing data.**

---

## Repository Structure & Reading Guide

This repository is intentionally structured to separate **definition**, **operation**, and **data integrity**.

### How to Read This Repository

- **README.md**  
  High-level philosophy, system architecture, validation summary, and performance framing.

- **LIVE_TRADING_RESULTS.md**  
  Official live shadow backtest documentation.  
  Defines operational scope, execution constraints, ops-gap exclusion rules, and result interpretation contract.  
  → This document specifies *how live results should be read*, not raw performance data.

- **realtime_signal_results.schema.json**  
  Schema definition for real-time signal result logging.  
  This repository stores **structure only** — no live performance data is committed.

### Data Policy (Important)

- Live operational data files (e.g. `realtime_signal_results.json`, `ops_log.json`)  
  are **explicitly excluded from version control** and remain local-only.
- GitHub contains **definitions and contracts**, not live performance outcomes.


## Documentation

- [V7 Grammar Table v1.0](v7_grammar_table.md)

- [Strategy Overview](strategy_overview.md)
 
- [Validation Cases (A–F)](validation_cases.md)
 
- [Live Results](live_results.md) *(In Progress)*  
  → Reports operational outcome metrics under fixed grammar and execution rules.

---

## Current Stage

> **Live Shadow Trading Validation in Progress**


## Application & Communication Samples

**Application Sample – V7 Grammar System**

Example of application-style technical communication describing the system’s
philosophy, validation approach, and operational framing.

- This document is **illustrative only**
- Not firm-specific
- Not a performance claim
- Provided to demonstrate technical communication and reasoning clarity

[View Sample Application](cover_letter.md)

These materials are intentionally separated from system specifications
to avoid mixing communication examples with execution definitions.


---

## Key Statement

> "We know exactly where we make money,  
> and we intentionally do not try elsewhere."

---

## Grade

**S (Superior)** - Institutional-grade validation complete

---

*Updated: 2026-01-19*
