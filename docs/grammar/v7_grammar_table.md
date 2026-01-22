# V7 Grammar Table v1.0

## 0. Purpose

V7 is not a system that "generates signals."
It is a grammar system that interprets market sentences and distinguishes what to speak from what to stop.

Grammar Table serves as a coordinate system clarifying where, what, and why each element restricts.

## 1. Sentence Structure

```
[ STATE ] + [ VERB ] + [ ADVERB ] + [ RISK ]
```

| Element | Role |
|---------|------|
| STATE | What sentence state is the market in? |
| VERB | What action (entry/strategy) is possible? |
| ADVERB | What tone restricts/adjusts that action? |
| RISK | How is risk managed according to that tone? |

## 2. STATE (Sentence State)

| STATE | Meaning | Description |
|-------|---------|-------------|
| SIDE | Consolidation | Directional sentence invalid |
| TREND | Trend | Directional sentence valid |
| TRANSITION | Transition | Sentence change zone |

STATE only permits or prohibits actions.
It does not regulate the size of expectation or greed.

## 3. VERB (Action Verbs)

| VERB | Role |
|------|------|
| STB | Structure-based entry |
| BREAK | Breakout-based entry |
| RETEST | Re-entry / reconfirmation |

VERB defines only "what can be done."
"How aggressively" is the role of ADVERB.

## 4. ADVERB (Adverb System)

### Danger Category — "Still dangerous"

| Item | Content |
|------|---------|
| Adverb | FALLING_KNIFE |
| Intervention | Pre-entry + Post-entry |
| Meaning | Loss probability accumulation |
| Effect | Size reduction, aggression decrease |
| Problem Addressed | Loss risk |

### Invalidity Category — "Cannot speak"

| Item | Content |
|------|---------|
| Adverb | SIDEWAYS |
| Intervention | Pre-entry |
| Meaning | Sentence invalid |
| Effect | Directional action blocked |
| Problem Addressed | Wrong sentence |

### Closure Category — "Enough has been said"

| Item | Content |
|------|---------|
| Adverb | DISTRIBUTIVE_CLOSURE |
| Status | Conditional |
| Intervention | Post-entry management |
| Meaning | Expectancy exhaustion / Distribution complete |
| Effect | Long chase disabled, TP extension disabled |
| Problem Addressed | Excess profit expectation |

> Not stopping because wrong, but stopping because spent.

### Meta Category (Non-operational)

| Adverb | SPS / Weak etc. |
|--------|-----------------|
| Role | Explanation only |
| Status | Inactive |

## 5. RISK (Risk Management)

| Element | Description |
|---------|-------------|
| Size | Adjusted according to ADVERB tone |
| TP Policy | Extension allowed / prohibited |
| Trail | Applied by state |

RISK is not an independent rule but a layer that translates ADVERB tone into execution.

## 5.5 Adverb Application Examples (Representative Cases)

### Example 1 — DISTRIBUTIVE_CLOSURE (TREND)

- **State**: TREND
- **Context**: Upward angle + Channel ≥70% + POC proximity
- **Adverb Applied**: DISTRIBUTIVE_CLOSURE
- **Effect**:
  - Long chase disabled
  - TP extension disabled
- **Interpretation**:
  The upward structure remained valid,
  but expansion expectancy was exhausted.

### Example 2 — DISTRIBUTIVE_CLOSURE (SIDE)

- **State**: SIDE → SIDE
- **Context**: Compression rally into POC
- **Adverb Applied**: DISTRIBUTIVE_CLOSURE
- **Effect**:
  - No pursuit beyond initial expansion
- **Interpretation**:
  Movement was accepted as distribution, not continuation.

### Example 3 — FALLING_KNIFE vs DISTRIBUTIVE_CLOSURE (Contrast)

- **State**: TREND
- **Difference**:
  - FALLING_KNIFE → risk accumulation
  - DISTRIBUTIVE_CLOSURE → expectancy exhaustion
- **Interpretation**:
  Risk was not elevated; expectation was completed.

## 6. Grammar Separation Principle (Core)

- Grammar for losses ≠ Grammar for profit expectation
- Consecutive loss data ≠ Expectancy closure data
- Entry judgment ≠ Expectation management

If this separation breaks:
- Backtests become contaminated
- Explanations become tangled
- System credibility collapses

V7 intentionally completed this separation structure.

## 7. Version Declaration

```
V7 Grammar Table v1.0
Status: Operational
Adverb System: Active (danger, invalidity, closure)
Created: 2026-01-19
```
