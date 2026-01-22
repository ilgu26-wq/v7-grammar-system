# Live Monitoring Specification

> **Date**: 2026-01-22
> **Purpose**: Define what to monitor in live operation (NOT what to backtest)

---

## Overview

This document marks the transition from:
- ❌ **Research mode** (more experiments)
- ✅ **Monitoring mode** (observe and respond)

The system is validated. No further backtesting is needed.

---

## 1. Metrics TO Monitor

### Primary Metrics

| Metric | What to Track | Alert Threshold |
|--------|---------------|-----------------|
| Fast Collapse Count | Absolute number of 1-2 bar losses | >5 per day |
| θ-Tier Ordering | θ=3 should be most stable | Ordering violation |
| Tier1 Dominance | Tier1 EV > Non-Tier1 EV | Inversion |

### Secondary Metrics

| Metric | What to Track | Purpose |
|--------|---------------|---------|
| Zone Distribution | Active price zones | State space health |
| Persistence Score Distribution | θ distribution | Certification quality |
| G3 Trigger Rate | How often G3 activates | Risk absorption |

---

## 2. Metrics NOT to Monitor

These are explicitly excluded from live monitoring:

| NOT Monitor | Reason |
|-------------|--------|
| Daily Win Rate | Post-hoc, high variance |
| Short-term EV | Noise, not signal |
| Trade Count | Quantity ≠ Quality |
| Consecutive Wins/Losses | Gambler's fallacy |

```
Win rate fluctuation is EXPECTED.
Do not react to short-term performance swings.
```

---

## 3. Operating Modes

### Normal Mode: θ=1 (Practical)
```
Daily trades: ~90
Expected win rate: 90%
Expected EV: 16.65pt
Max DD tolerance: 500pt
```

### Conservative Mode: θ≥3
```
Daily trades: ~2
Expected win rate: 95%+
Expected EV: 18+pt
Max DD tolerance: 100pt
```

---

## 4. Emergency Clause

### Trigger Conditions
```python
IF fast_collapse_absolute_count > 5 in rolling_24h:
    MODE = CONSERVATIVE  # Switch to θ≥3

IF theta_ordering_violated:
    PAUSE = True  # Manual review required

IF tier1_dominance_lost:
    PAUSE = True  # System integrity check
```

### What Emergency Clause Does NOT Do
- ❌ Stop all trading
- ❌ Revert to backtesting
- ❌ Change fundamental parameters

### What Emergency Clause Does
- ✅ Shift to more conservative mode
- ✅ Flag for human review
- ✅ Reduce position sizing automatically

---

## 5. Reporting Cadence

| Report | Frequency | Content |
|--------|-----------|---------|
| Trade Log | Real-time | Every trade with θ, zone, result |
| Daily Summary | End of day | Win rate, EV, DD, mode |
| Weekly Health | Weekly | Metric distributions, anomalies |
| Monthly Review | Monthly | Constitution compliance check |

---

## 6. What Indicates System Health

### Healthy System
- θ-ordering preserved (θ=3 < θ=1 in DD)
- Tier1 outperforms Non-Tier1
- Fast collapse rate stable or decreasing
- G3 triggering at expected rate (15-20%)

### Unhealthy System (Requires Review)
- θ-ordering inverted
- Non-Tier1 outperforms Tier1
- Fast collapse rate spiking
- G3 never triggering or always triggering

---

## 7. Do NOT Do

### Do Not Reoptimize
```
Parameters are LOCKED:
- MFE_THRESHOLD = 7
- TRAIL_OFFSET = 1.5
- LWS_BARS = 4
- DEFENSE_SL = 12
- PERSIST_THETA = 1 (or 3 for conservative)
```

### Do Not Add New Experiments
```
The research phase is CLOSED.
If new experiments are needed, create new branch.
Main branch is for operation, not research.
```

### Do Not React to Single Events
```
One bad day ≠ System failure
One good week ≠ System improvement
Trust the structure, not the noise.
```

---

## 8. Handoff Criteria

This system can be handed off when:

| Criteria | Status |
|----------|--------|
| Constitution documented | ✅ |
| Validation complete (9/9) | ✅ |
| Failure modes analyzed | ✅ |
| Monitoring spec defined | ✅ |
| Parameters locked | ✅ |
| Emergency clause defined | ✅ |

---

## Conclusion

```
┌─────────────────────────────────────────────────────────────────────┐
│  V7 has transitioned from Research to Operation.                    │
│                                                                     │
│  What to do:                                                        │
│  - Monitor the metrics above                                        │
│  - Respond to emergency triggers                                    │
│  - Trust the validated structure                                    │
│                                                                     │
│  What NOT to do:                                                    │
│  - Run more backtests                                               │
│  - Tune parameters                                                  │
│  - React to short-term noise                                        │
│                                                                     │
│  "실험은 끝났다. 이제 운용한다."                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

**Specification Complete**: 2026-01-22
