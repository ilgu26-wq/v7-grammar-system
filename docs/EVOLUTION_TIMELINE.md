# V7 Grammar System: Evolution Timeline

*How this system destroyed every idea that failed,  
and what remained after 6 weeks of systematic elimination.*

---

## Why This Document Exists

> "I did not arrive at this design directly.  
> I arrived here by systematically destroying every alternative."

This document records the **thinking evolution**, not just the results.  
Every major transition is backed by data in this repository.

---

## Phase 1: Initial Exploration (Dec 29-31)

### What I Tried
- 13 different formula approaches
- Multiple SPS ratio variants
- Z-score combinations
- Trend-based sector analysis

### Key Files Created
```
backtest_2024_1min.json
formula_verification.json
sps_ratio_formula.json
triple_intersection.json
```

### What I Learned
- Raw signal count ≠ edge
- Formula complexity ≠ robustness
- **Most ideas looked good in backtest but had no structural basis**

### What I Killed
- Pure z-score strategies
- Complex intersection formulas
- Sector-weighted approaches

---

## Phase 2: The Verification Crisis (Jan 6-7)

### The Turning Point
**I deployed unverified signals to live trading. All failed.**

| Signal | Expected | Actual |
|--------|----------|--------|
| S+ | ~80% | **0%** |
| S | ~70% | **0%** |
| A | ~60% | **0%** |

### What This Taught Me
> **"Claims without data are dangerous."**  
> **"Verification is not optional."**

### Structural Change
Created mandatory verification protocol:
- Every signal must have sample count
- Every claim must have JSON evidence
- Unverified = blocked from Telegram

### Key Files Created
```
verification_20260106_*.json
.jason_verification_state.json
verification_all_signals_20260106.json
```

---

## Phase 3: Grammar Discovery (Jan 10-12)

### The Insight
**Prediction is unstable. Classification is stable.**

I stopped asking "Where will price go?"  
I started asking "What state is the market in?"

### What I Built
| Component | Role |
|-----------|------|
| θ (Theta) | State classification |
| STB | Ignition sensor |
| Persistence | State certification |

### Key Validation Results
```
STB immediate (θ=0): 0% win rate (55 trades)
STB + θ≥1: 100% win rate (297 trades)
```

### What I Killed
- All prediction-based entries
- Dynamic parameter tuning
- Exit-based alpha attempts

---

## Phase 4: Expansion Under Stress (Jan 18)

### The Explosion
**73 files in one day.** This was the stress test phase.

### What I Tested
| Case | Target | Result |
|------|--------|--------|
| A | ES (S&P 500) | PASS |
| B | BTC + Roll Events | PASS |
| C | Multi-Timeframe | PASS |
| D | COVID / CPI / Banking | PASS |
| E | Portfolio Independence | PASS |
| F | Execution Integrity | PASS |

### What This Proved
- **Asset-agnostic**: Same logic, different markets
- **Regime-robust**: Structure survives stress
- **Time-invariant**: Works across timeframes

### Key Files Created
```
btc1_robustness_test_results.json
case_c_mtf_results.json
case_d_event_stress_results.json
case_e_complete.json
```

---

## Phase 5: Constitutional Lock (Jan 22)

### The Final Step
**"This system is no longer an experiment."**

### What I Locked
| Policy | Rule |
|--------|------|
| θ=0 | DENY (no exceptions) |
| θ=2 | Retry conditions required |
| θ≥3 | LARGE size allowed |
| Trailing | θ≥3 only |

### What I Created
```
opa/policy_v74.py (FROZEN)
docs/V7_CONSTITUTION.md
docs/OPA_V74_POLICY.md
```

### What This Means
> **"No further logic changes planned.  
> Only data accumulation ongoing."**

---

## Ideas That Were Killed (Graveyard)

### Killed for Structural Instability
| Idea | Why Killed | Evidence |
|------|------------|----------|
| Prediction-based entry | Regime-dependent | θ=0 = 100% SL |
| Dynamic SL tuning | Tail risk explosion | Backtest divergence |
| MFE-based exit | Correlated with entry, not independent | Ablation test |
| Sector weighting | Added complexity, no benefit | Removed |

### Killed for Insufficient Sample
| Idea | Sample | Decision |
|------|--------|----------|
| 횡보예상_v1 | 25% accuracy | Blocked |
| ELEV_SHORT | 63.8% | Not promoted |
| PE_SHORT_S2 | 59% | Blocked |

### Killed for Verification Failure
| Signal | Claimed | Actual |
|--------|---------|--------|
| 매수스팟 | High | 0% |
| 매도스팟 | High | 0% |
| 빗각버팀 | Medium | Failed |

---

## Key Transitions Summary

| Week | Before | After | Trigger |
|------|--------|-------|---------|
| 1 | "Find alpha" | "Classify states" | Prediction failures |
| 2 | "Optimize exit" | "Entry determines success" | Exit ablation |
| 3 | "Add signals" | "Kill weak signals" | Verification crisis |
| 4 | "NQ only" | "Asset-agnostic" | ES/BTC validation |
| 5 | "Tune parameters" | "Lock parameters" | Consistency tests |
| 6 | "Experiment" | "Operate" | OPA v7.4 frozen |

---

## What Makes This Different

### Most Researchers
- Show final results only
- Hide failed experiments
- Optimize for metrics

### This Repository
- **Every failure is preserved**
- **Every killed idea is documented**
- **Evolution is traceable**

---

## The Core Lesson

> **"I don't know where the market will go.  
> But I know exactly which states allow execution,  
> and I intentionally do not try elsewhere."**

---

## Evidence Paths

| Claim | Evidence |
|-------|----------|
| Verification crisis | `verification_20260106_*.json` |
| State classification works | `experiments/theta_consistency_results.json` |
| θ=0 = 100% failure | `docs/V7_CONSTITUTION.md` |
| Stress test passed | `case_d_event_stress_results.json` |
| Ideas killed | `archive/`, `blocked_signals` in state file |

---

**This document is part of the V7 Grammar System.**  
**Version**: 1.0  
**Date**: 2026-01-22
