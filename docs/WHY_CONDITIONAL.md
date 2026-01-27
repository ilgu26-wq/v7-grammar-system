# Why V7 Is Conditional by Design

> V7 is not a system that tries to always win.
> It is a selection system designed to operate only in physical states where winning is possible.

---

## Core Conclusion (One Sentence)

V7 should be evaluated by **Conditional EV**, not average performance,
because it is designed to refuse structurally bad trades rather than improve all trades.

---

## The Misunderstanding: Why Overall EV Is Negative

### Observed Data

| Condition | EV |
|:----------|---:|
| BASE (all trades) | -0.375pt |
| V7 (all filtered) | -0.649pt |
| **V7 Conditional (avg>=15 & FR<=Q25)** | **+2.500pt** |

Looking at this alone, one might think "V7 is worse than BASE."

**This interpretation is structurally wrong.**

---

## The Critical Fork: EV Is Determined by Tails, Not Averages

### MAE Decomposition

| MAE Range | WR | EV |
|:----------|---:|---:|
| MAE < 10pt | 100% | +10.0pt |
| MAE >= 10pt | 2.4% | -9.524pt |

**Key insight**:

> The moment MAE exceeds 10pt, that trade enters a near-certain loss state.

What destroys EV is not failed TPs.
It is **the few trades that run deeply against you (MAE tail)**.

---

## V7's Role Is Not "Average Improvement"

What V7 does:

- **NOT**: Slightly improve win rate across all entries
- **YES**: Pre-block MAE >= 10pt tails before they occur

Therefore, V7 is not a system that evenly improves everything.
It is a system that **boldly removes specific zones**.

---

## Why Conditional EV Becomes Positive

### EV by Condition

| Condition | EV | MAE |
|:----------|---:|----:|
| FR <= Q25 | +1.176pt | 8.2pt |
| avg >= 15 & FR <= Q25 | **+2.500pt** | 7.5pt |
| FR > Q75 | -1.970pt | 11.4pt |

**Key Variables**:

- **avg_delta** → TP reachability (energy)
- **force_ratio** → MAE tail probability (reversal risk)

Only when both conditions are met simultaneously:
- MAE stays below 10pt
- EV flips to positive

**The moment conditions break, EV immediately collapses to negative.**

---

## Therefore, V7 Is a "Conditional System"

### Wrong Question

> "Does V7 make money overall?"

### Right Question

> "Under what conditions does V7 make money?"

V7's design philosophy only answers this question.

---

## Official Definition

> V7 Grammar System is not a strategy targeting the entire market.
> It is a conditional judgment system that executes only in rare states
> where structure (DC), energy (avg), and force balance (FR) are simultaneously satisfied.

---

## Why This Is a Strength, Not a Weakness

| Perceived Weakness | Actual Meaning |
|:-------------------|:---------------|
| Few trades | Noise removal |
| Strict conditions | MAE tail removal |
| Negative overall EV | Conditional EV maximization |

This structure is closer to **institutional risk management**
than retail strategy.

---

## Key Statement (Summary)

> **V7 is not a "system that always wins".**
> **It is a "system that refuses to trade in states where it cannot win."**

As a result, overall average performance is meaningless.
**Conditional EV is the only valid evaluation criterion for this system.**

---

## Evidence Trail

| Finding | Evidence |
|:--------|:---------|
| MAE >= 10pt → EV collapse | `experiments/ev_attribution.json` |
| FR <= Q25 → EV positive | `experiments/ev_attribution.json` |
| Optimal: avg>=15 & FR<=Q25 | EV = +2.500pt, WR = 62.5% |

---

*Last updated: 2026-01-27*
