# Strategy Overview

This document provides a **high-level structural overview** of the V7 Grammar System.

It intentionally omits implementation details and performance claims.
All execution behavior is governed by validated decision grammar and
operational policy (OPA).

---

## Core Principle

V7 does not predict price direction.

It classifies **decision-admissible market states** and constrains execution
through fixed grammar and policy layers.

Prediction modules, if any, are strictly optional and non-authoritative.

---

## Structural Flow

Market Data  
→ Decision Grammar (STATE / STB / EE)  
→ OPA (Execution Authorization)  
→ Execution Constraints  
→ Capital / Risk

---

## Methodological Boundary

- Decision grammar is **structurally validated**
- OPA governs **execution permission**
- Portfolio optimization is **explicitly out of scope**

This separation is intentional and non-negotiable.

For empirical validation and execution constraints,
refer to the validation documents.
