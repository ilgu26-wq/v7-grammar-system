# A Data-Driven Action Prohibition Layer for Autonomous Trading Systems

---

## Abstract

We do not predict outcomes.

We classify actionable vs non-actionable states.

Irreversibility is freedom collapse, not volatility.

Resonance occurs inside storms, not before them.

Direction emerges only conditionally, near rupture.

---

## What This Is (and Is Not)

This document does not propose a trading strategy.

It does not introduce a prediction model.
It does not optimize alpha.

This is a **safety layer**:
a data-validated mechanism that determines
**when an autonomous system must not act**.

---

## Motivation: Why Prediction Is the Wrong Safety Primitive

Most failures in autonomous trading systems
do not originate from incorrect forecasts.

They originate from **action taken in invalid worlds**.

The central question is not:
“Where will price go?”

But:
“Is action permitted in this world at all?”

---

## Core Concept: Actionable vs Non-Actionable Worlds

We partition market states into:

- Actionable worlds  
- Non-actionable worlds  

This boundary is inferred from data,
not imposed by heuristics or human priors.

The classification is invariant to:
- asset
- direction
- strategy form

---

## Irreversibility as Freedom Collapse

Irreversibility is not volatility.

It is the collapse of available futures:
once crossed, prior alternatives no longer exist.

Before rupture:
multiple futures coexist.

After rupture:
only one world remains.

Action before this boundary is undefined.

---

## Empirical Evidence (Visual Summary)

(Insert: freedom_resonance_chain.png)

Resonance is observed **only after**
the system enters a constrained world.

No pre-rupture signal is sufficient.

(Insert: connectivity_u_curve.png)

Actionability follows a bounded, non-monotonic structure.
More “signal” does not imply more freedom.

---

## Direction Policy (Safety Constraint)

Direction is not predicted.

It appears only as a **side-effect**
inside healthy, constrained worlds
and only near rupture.

Direction is used exclusively for:
- exit
- hedging

Never for entry.

---

## Limitations

This system does not:
- maximize returns
- guarantee profitability
- replace risk management

It only answers one question:

**Is action allowed at all?**

---

## Reproducibility

All experiments, tests, and validations
are available in the public repository:

(link to repo)

This document summarizes observed structure.
It does not speculate beyond validated boundaries.
