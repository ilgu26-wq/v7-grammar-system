# STATUS — Final Causal Boundary Declaration

**Updated: 2026-02-01**

This document defines:
1. What is empirically supported
2. What has been explicitly falsified
3. What remains open but bounded

**Any claim outside this boundary is unsupported by this repository.**

---

## 🟢 LAYER A — EMPIRICALLY LOCKED (반증 불가)

These conclusions are validated through multiple experiments and cannot be overturned without new data that contradicts the falsification criteria.

---

### A1. Phase Taxonomy (LOCKED)

```
ZPOC → TRANSITION → SPS → NORMAL
```

| Phase | Definition | Coverage |
|-------|------------|----------|
| ZPOC | ER < 0.20 (efficiency collapse) | 35.5% |
| TRANSITION | Depth side flip | 4.9% |
| SPS | Extreme depth + ER > 0.30 | 23.5% |
| NORMAL | All other states | 36.1% |

**Validation:**
- Random shift test: structure collapses under temporal displacement
- Distribution test: KS > 0.1 between all phase pairs
- Definition locked, modification forbidden

---

### A2. Dual Causal Structure (LOCKED)

| Phenomenon | Direct Cause | Mechanism | Evidence |
|------------|--------------|-----------|----------|
| **ZPOC** (ER collapse) | force_ratio velocity | Microstructural shock | Conditional independence lift = 1.16 |
| **TRANSITION** | DEPTH velocity | State displacement | KS = 0.448, proxy test pass |

**Critical Finding:**
```
force_ratio velocity:
  - ZPOC: Independent causal driver (lift 1.16 after depth control)
  - TRANSITION: Pure proxy (lift 1.06 → effect disappears)
```

**Falsification Criteria (passed):**
- Counterfactual test: Smooth force_ratio → 38.6% break reduction
- Random shift: Structure collapses (preservation 0.19-0.22)
- Conditional independence: Lift separation validated

---

### A3. FORCE System Definition (LOCKED)

```
FORCE = Microstructural shock channel
      = force_ratio velocity
      = (close-low)/(high-close) change rate
```

**What FORCE Does:**
| Function | Status |
|----------|--------|
| Detect ZPOC onset | ✅ Valid |
| Predict TRANSITION | ❌ Invalid (proxy only) |
| Predict direction | ❌ Invalid |
| Generate entry signals | ❌ Not designed for this |

**Why Not Multidimensional:**
```
Multidimensional norm ‖State‖₂:
  - Treats all axes equally
  - Dilutes dominant axis (force_ratio = 94.8%)
  - Maintains structure under random shift (false stability)

Current FORCE:
  - Single dominant axis measurement
  - Random shift destroys structure (true causality)
```

---

### A4. Universality Boundary (LOCKED)

| Causality Type | Target | Universality | Evidence |
|----------------|--------|--------------|----------|
| Relative (z-score) | TRANSITION | Frame-invariant | All TF pass |
| Absolute (magnitude) | ER collapse | Resolution-dependent | 1m only |

**Physical Interpretation:**
```
TRANSITION = "Has state changed?" 
  → Relative comparison → TF invariant (Einstein-type)

ER collapse = "Was shock large enough?"
  → Absolute magnitude → High-resolution required (Newton-type)
```

---

### A5. STB Validity (LOCKED)

| Phase | STB Persistence | Action |
|-------|-----------------|--------|
| ZPOC | 42.1% | ❌ FORBIDDEN |
| TRANSITION | 46.3% | ❌ FORBIDDEN |
| SPS | 46.0% | ⚠️ OBSERVE ONLY |
| NORMAL | 56.6% | ✅ VALID |

**Falsification Criteria (passed):**
- Chi-square test: Phase-persistence association significant
- STB meaning changes by phase, not universal signal

---

## 🔴 LAYER B — EXPLICITLY FALSIFIED (실패 선언)

These hypotheses were tested and rejected. Including them prevents future re-testing of dead ends.

---

### B1. Rejected Causal Hypotheses

| Hypothesis | Test | Result | Reason |
|------------|------|--------|--------|
| Seller impotence causes ZPOC | EXP-SELLER-IMPOTENCE-01 | ❌ REJECTED | Symmetry confirmed (ratio 0.70 both phases) |
| Stop hunt causes TRANSITION | EXP-STOPHUNT-ADVERSARIAL-01 | ❌ REJECTED | Direction symmetry, channel independence |
| DEPTH accumulation threshold | EXP-DEPTH-CAUSAL-01 | ❌ REJECTED | Instantaneous change matters, not cumulative |
| Single universal cause | EXP-PHASE-CAUSAL-COMPARE-01 | ❌ REJECTED | Phase-conditional effects validated |
| force_ratio = mere correlation | EXP-PROXY-CAUSALITY-01 | ❌ REJECTED | Conditional lift 1.16 for ZPOC |
| Pure relative causality | EXP-RELATIVE-FORCE-TWIST-01 | ❌ REJECTED | ABS→ER independent effect |
| Multidimensional norm superior | EXP-FORCE-TRIGGER-MAP-01 | ❌ REJECTED | 94.8% single-axis dominance |

---

### B2. Rejected Control Hypotheses

| Hypothesis | Test | Result | Reason |
|------------|------|--------|--------|
| **Post-ZPOC direction control** | EXP-MICRO-DIRECTION-CONTROL-01 | ❌ REJECTED | Hit rate 51.3%, Z-score 1.14 |
| Post-TRANSITION direction control | Implied by ZPOC test | ❌ REJECTED | Organizer absence = no persistence |

**Critical Conclusion:**
```
FORCE indicates WHEN collapse occurs, NOT WHICH DIRECTION.
Collapse is truly chaotic — no directional edge exists at the micro level.

Evidence:
  - Best hit rate: 51.3% (not different from 50%)
  - Z-score: 1.14 (< 2.0 threshold)
  - Depth-controlled bins: 48.4% - 53.8% (no consistent edge)
```

---

## 🟡 LAYER C — OPEN BUT BOUNDED (미해결)

These questions remain open but are strictly bounded. Any investigation must respect the boundary conditions.

---

### C1. Pre-Collapse Micro-Direction Control (OPEN)

**Hypothesis (H_MICRO_CTRL_PRE):**
```
Immediately before ER collapse (w = -5 to -10),
microstructural force asymmetry may retain directional bias
that dissipates as organizer absence completes.
```

**Boundary Conditions:**
- Applies only BEFORE ZPOC onset (w < 0)
- Does not imply TRANSITION prediction
- Does not apply after ER < 0.20 is established
- Window: w = -5 to -10 only (not -1 to -3, already failed)

**Falsification Criteria:**
```
If micro-directional alignment at w=-5~-10 does not exceed 55%
under random-shift control, the hypothesis is rejected.
```

**Current Status:** NOT YET TESTED

---

### C2. Asset-Class Generalization (OPEN)

**Question:**
Does the dual causal structure hold for ES, BTC, or other assets?

**Boundary Conditions:**
- TRANSITION universality is expected (relative causality)
- ER collapse may require resolution adjustment
- Definition changes are forbidden

**Falsification Criteria:**
```
If H_U1 + H_U2 pass rate < 50% across 3+ assets,
the structure is asset-specific, not universal.
```

**Current Status:** NQ only validated

---

## EXPERIMENTAL VALIDATION CHAIN

| # | Experiment | Question | Result |
|---|------------|----------|--------|
| 1 | EXP-DEPTH-CAUSAL-01 | Does DEPTH precede ER? | ✅ YES (85.6%) |
| 2 | EXP-FORCE-ALIGNMENT-BREAK-01 | What causes alignment breaks? | ✅ Multidimensional collapse |
| 3 | EXP-FORCE-TRIGGER-MAP-01 | Which axis dominates? | ✅ force_ratio (94.8%) |
| 4 | EXP-FORCE-RATIO-DECOMPOSE-01 | Level or velocity? | ✅ Velocity dominant |
| 5 | EXP-COUNTERFACTUAL-FORCE-01 | Is force_ratio causal? | ✅ YES (38.6% reduction) |
| 6 | EXP-RELATIVE-FORCE-TWIST-01 | Absolute or relative? | ✅ Dual structure |
| 7 | EXP-UNIVERSALITY-VALIDATION-01 | Frame invariant? | ✅ Partial (REL universal) |
| 8 | EXP-PHASE-CAUSAL-COMPARE-01 | Phase-conditional causes? | ✅ DEPTH dominates TR |
| 9 | EXP-PROXY-CAUSALITY-01 | Proxy or independent? | ✅ ZPOC: independent |
| 10 | EXP-MICRO-DIRECTION-CONTROL-01 | Direction control? | ❌ NO (51.3%) |

---

## INTEGRATED CAUSAL ARCHITECTURE (FINAL)

```
[ Micro Layer ]
force_ratio velocity
   └─(Independent Cause)→ ER Collapse (ZPOC)
   └─(Proxy)→ DEPTH velocity

[ State Layer ]
DEPTH velocity
   └─(Direct Cause)→ TRANSITION

[ Phase Flow ]
ZPOC → TRANSITION → SPS → NORMAL

[ Validation Layer ]
STB (Valid only in NORMAL)

[ Control Layer ]
Direction control: ❌ INVALID (post-collapse)
Direction control: ? OPEN (pre-collapse, w=-5~-10)
```

---

## DATA INTEGRITY STATEMENT

- All experiments included, including failures
- No selection of favorable results
- Contradictions preserved and explained
- Random shift tests validate structural claims
- Conditional independence confirms causal claims

---

## FINAL DECLARATION

```
This research establishes a hierarchical causal architecture
with explicit boundaries on what can and cannot be claimed.

LOCKED CLAIMS:
- Microstructural shocks cause efficiency collapse
- State displacement governs phase transitions
- The same signal acts as cause or proxy depending on phenomenon
- Direction control is invalid after collapse

REJECTED CLAIMS:
- Universal predictability
- Single causal mechanism
- Post-collapse directional edge

OPEN QUESTIONS:
- Pre-collapse directional bias (bounded to w=-5~-10)
- Asset-class generalization

No component is predictive.
Each operates within a strictly defined causal layer.
```

---

**Frozen Timestamp: 2026-02-01T20:00:00**
**Status: LOCKED (Layer A/B), OPEN (Layer C)**
