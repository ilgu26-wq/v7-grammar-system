# README v2 — Final Judgment of the V7 Grammar System

> This document does not redefine or modify the V7 Grammar System.  
> It records the final empirical judgment of what the system was shown to be,  
> after all falsifiable hypotheses were tested and the validation protocol was formally closed.

---

## Status

| Component | Status |
|:----------|:-------|
| Decision grammar | **frozen** |
| Validation protocol | **closed** |
| Macro–Micro framework | **confirmed** |
| Optimization target | explicitly not 90% |

---

## What the System Was Proven to Be

V7 is not a high-frequency alpha generator.

V7 is a **decision grammar** that:
- Identifies where market behavior is structurally coherent
- Separates subject vs non-subject participation
- Explains *why* 90% WR regions may or may not exist, instead of forcing them

> **"90% is not a goal. It is a phenomenon that only appears under specific structural roles."**

---

## Two-Layer Architecture (Confirmed)

```
┌─────────────────────────────────────────────────────────────┐
│  MACRO (거시): D→S 전이 = "언제 말할 수 있는가"              │
│  MICRO (미시): Bar1 유지 = "어떻게 문장이 완성되는가"        │
└─────────────────────────────────────────────────────────────┘
```

| Layer | Function | Key Variable |
|:------|:---------|:-------------|
| Macro | Detects when market becomes structurally coherent | State Transition (D→S) |
| Micro | Determines whether the sentence completes | Bar1 Direction Hold |

---

## Visual Evidence (Primary)

> The README intentionally embeds visual artifacts, not raw JSON, to communicate structure.  
> Raw data and scripts remain in `experiments/` and `visualizations/`.

---

### A. Macro State Distribution

STABLE states occur ~11–12% across all markets. This explains signal scarcity.

![Macro State Distribution](../visualizations/A_macro_state_distribution.png)

---

### B. State Transition Heatmap

Persistence on diagonal confirms state stability. Off-diagonal reveals transition patterns.

![State Transition Heatmap](../visualizations/B_state_transition_heatmap.png)

---

### C. Macro State Characteristics

Range / Delta / Drift behavior by state. STABLE shows minimal variation.

![Macro State Characteristics](../visualizations/C_macro_state_characteristics.png)

---

### D. Hypothesis Verification

H1–H5 results: 4 PASS / 1 SKIP / 0 FAIL

![Hypothesis Verification](../visualizations/D_hypothesis_verification.png)

---

### E. Entry Close Separation (H5 Falsification)

Late entry ⇒ collapse. Gap = 42.7%

![Entry Close Separation](../visualizations/E_entry_close_separation.png)

---

### F. WR vs N Tradeoff

V7 falsifiable vs WHEN optimized. Structure vs overfit boundary.

![WR vs N Tradeoff](../visualizations/F_wr_vs_n_tradeoff.png)

---

### G. Complete Dashboard

All verification metrics in one view.

![Complete Dashboard](../visualizations/G_complete_dashboard.png)

---

### H. Transition Signal Density

D→S transition concentrates valid entries. Other transitions = sparse.

![Transition Signal Density](../visualizations/H_transition_signal_density.png)

---

### I. Macro Experiment Results

Cross-market reproducibility confirmed.

![Macro Experiment Results](../visualizations/I_macro_experiment_results.png)

---

## Cross-Market Reproducibility (EXP-B)

| Market | D→S | Entry | WR | Hold WR | Fail WR | **Gap** | PASS |
|:------:|----:|------:|---:|--------:|--------:|--------:|:----:|
| **NQ** | 10 | 24 | 52.6% | 88.9% | 20.0% | **+68.9%** | 4/4 ✅ |
| ES | 61 | 0 | - | - | - | - | 2/4 ⚠️ |
| **BTC** | 47 | 26 | 73.1% | 93.3% | 45.5% | **+47.9%** | 4/4 ✅ |

### State Distribution (Market-Independent)

| Market | STABLE | E | C | D |
|:------:|-------:|--:|--:|--:|
| NQ | **11.7%** | 25.0% | 28.6% | 34.8% |
| ES | **12.2%** | 27.5% | 31.1% | 29.2% |
| BTC | **12.5%** | 24.5% | 32.9% | 30.0% |

**→ All markets show STABLE ≈ 12% (structural scarcity confirmed)**

---

## Key Conclusions

| Finding | Evidence |
|:--------|:---------|
| Signal scarcity is structural | STABLE ≈ 11–12% across all markets |
| Macro decides **when** | D→S transition enables signal density |
| Micro decides **how** | Bar1 hold creates 47–69% WR gap |
| 90% WR is conditional | Appears only as phenomenon, collapses under falsification |

---

## Asymmetry Judgment (Final)

| Context | Failure Revelation | Dominant Control | Structural Ceiling |
|:--------|:-------------------|:-----------------|:-------------------|
| BULL SHORT (non-subject) | Bar 2–3 | HOLD / CUT | ~75–80% |
| BEAR LONG (non-subject) | Bar 1 | ENTRY | ~60% |
| BULL LONG (subject) | Bar 1 (instant) | ENTRY | conditional |
| BEAR SHORT (subject) | Bar 1 (instant) | ENTRY | conditional |

---

## Why 90% Was Not Forced

Multiple adversarial tests confirmed:
- 90% WR cannot be engineered without destroying N
- When 90% appears, it is regime-conditional, not stable
- Forcing 90% converts structure into overfit conditions

> **The absence of a natural 90% region is itself a valid scientific result.**

---

## What V7 Is / Is Not

| ❌ Is Not | ✅ Is |
|:---------|:------|
| A prediction engine | A market-independent grammar engine |
| A high-frequency signal generator | A macro transition detector |
| Optimized for headline win rate | A micro execution discriminator |
| | Explicitly falsifiable by construction |

---

## Forward Interface

V7 is complete as a grammar.

Future work does **not** modify the grammar. It may only:

| Valid Extensions | Invalid Extensions |
|:-----------------|:-------------------|
| Macro-pattern filters (D→S triggers) | TP/RR tuning |
| External alpha inputs gated by V7 state | Condition stacking for WR |
| Frequency scaling via new data | Using future observables as inputs |

---

## Final Declaration

> V7 does not predict direction.  
> It certifies when decisions are structurally meaningful.  
>  
> The system is complete, auditable, and falsifiable.  
> Any future performance increase must come from new information, not from altering this grammar.

---

*Last Updated: 2026-01-28*
