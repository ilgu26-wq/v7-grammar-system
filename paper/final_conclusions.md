# Final Conclusions: V7 Market State Physics

## Status Declaration

This document records the final conclusions of the V7 Grammar System.

All core hypotheses (H1–H6) have been revalidated on a representative sample
of 19,157 trades across assets, regimes, and execution conditions.

No further logic changes are planned.
V7 is considered a complete **market state observation framework** under the
defined execution and risk constraints.

---

## What Failed: Prediction

Across the full representative sample, predictive approaches failed
to produce stable or repeatable advantages:

- Directional forecasting
- EE / EV-BB–based estimators
- Momentum and candle-based anticipation

Higher estimated “energy” increased impulse volatility
without improving outcome stability or persistence.

**Conclusion:**  
Future market direction is not reliably observable prior to state formation.

---

## What Worked: State Transition and Persistence

Empirical observations across 19,157 trades show:

| Observation | Result |
|------------|--------|
| MFE ≥ 7 | No realized losses at the engine level |
| All realized losses | Occur prior to the MFE threshold |
| Win rate | Strongly correlated with state persistence |

MFE ≥ 7 functions as an **empirical state transition threshold**.
Before this point, energy formation may fail.
After this point, loss becomes structurally constrained under the V7 execution model.

---

## Losses as State Maintenance Failures

Losses are not attributable to incorrect directional entries.
They arise from failures in state persistence.

Observed properties:

- Average loss occurs approximately 22 bars after entry
- 100% of realized losses occur before state transition
- Hard stop-loss enforcement reduces recovery probability

### Soft SL (G3)

Early detection of state collapse reduces loss magnitude:

| Model | PnL | EV |
|------|-----|----|
| G0 (Hard SL 30) | -69,600 | -7.27 |
| G3 (Soft SL) | +16,944 | +1.77 |

Loss reduction is achieved through **collapse detection**, not prediction.

---

## Re-entry Resolved by Persistence

Re-entry as an isolated trading action provides no informational advantage.

Persistence-based continuation does.

| Scenario | Win Rate |
|---------|----------|
| New entry | 20.1% |
| Persistence + price retest | 89.9% |

Energy is not stored in price.
It is expressed and maintained in state space.

---

## Why EE Became Non-Operational

EE attempted to estimate latent energy.
MFE and persistence directly observe realized state behavior.

Empirical results show:

- EE increases impulse volatility
- EE does not improve survival or persistence classification

EE remains explanatory, not operational, within V7.

---

## Final Constitutional Statement

The V7 Grammar System is not a trading strategy.

It is a **market state observation and control framework** that formalizes:

- State creation
- State persistence
- State collapse

### Locked Core Parameters

- Entry: STB
- State transition: MFE ≥ 7
- Management: Trailing offset = MFE − 1.5
- Loss defense: Soft SL (G3)
- Measurement: PersistenceScore
- Re-entry: Persistence + price retest only
- Predictive filters: None

---

## One-Line Conclusion

Markets are not forecastable systems.
They are state-driven processes.

V7 formalizes this observation.
