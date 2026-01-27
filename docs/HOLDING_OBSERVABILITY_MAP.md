# Holding Observability Map

## Critical Statement

> **Holding logic was never intended as a profit maximization tool.**
>
> It was used exclusively to observe:
> - failure latency
> - energy dissipation
> - regime observability
>
> **Any use of MFE or Depth as real-time inputs is prohibited.**

---

## Purpose of HOLD/CUT Logic

HOLD/CUT is an **observation instrument**, not a trading strategy.

### What HOLD reveals:

| Observation | Meaning |
|:------------|:--------|
| HOLD improves outcome | Trade had observable failure mode |
| HOLD has no effect | Trade was instant-death structure |
| CUT reduces loss | Early exit captured dissipation point |

---

## Empirical Findings

### Dominant Direction (BULL∧LONG, BEAR∧SHORT)

```
HOLD contribution = 0
Failure mode = Instant (Bar1)
Optimization axis = ENTRY only
```

### Non-dominant Direction (BULL∧SHORT, BEAR∧LONG)

```
HOLD contribution > 0 (potential)
Failure mode = Gradual (observable)
Optimization axis = ENTRY × HOLD
```

---

## Data Rules (Strict)

### Allowed Inputs

| Variable | Time | Usage |
|:---------|:-----|:------|
| DC_pre | t-ε | Entry gate |
| DC_post | t~5 | Reaction observation |
| ER_5 | t~5 | Initial response |

### Prohibited Inputs

| Variable | Reason |
|:---------|:-------|
| MFE | Post-hoc (future information) |
| Depth | Post-hoc (future information) |

---

## Why MFE/Depth Are Prohibited

MFE (Maximum Favorable Excursion) and Depth are **results**, not **inputs**.

Using them as real-time decision variables creates:
1. Look-ahead bias
2. Impossible-to-execute logic
3. False performance inflation

They may only be used for:
- Post-trade analysis
- Labeling (not input)
- Structural classification

---

## H3 Verification Result

| Test | Dominant | Non-dominant |
|:-----|:---------|:-------------|
| HOLD ON vs OFF | No difference | Potential improvement |
| Verdict | **PASS** | Needs more data |

**Conclusion**: HOLD is structurally irrelevant for dominant-direction trades.

---

**Date**: 2026-01-27
**Status**: Protocol established
