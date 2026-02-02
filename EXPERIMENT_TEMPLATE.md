# Hypothesis Experiment Design Template

**Core Principle:**
```
"성능을 보지 말고, 같은 세계를 반복해서 가리키는지만 본다."
"Don't look at performance. Only check if it keeps pointing to the same world."
```

---

## 0) Experiment ID + One-liner

- **Experiment ID**: (e.g., PHASE_K_CENSUS_V1, WIND-2_FOLDED_SEAT, ALPHA_L_PRIMITIVES)
- **One-liner**: "(Pattern/Condition) → (State/Session Response) → (Outcome) attribution verified"

---

## 1) World Axioms (LOCKED)

### Axiom Lock
- [ ] Irreversibility basis: Bar1 / DC=1 / (your definition)
- [ ] Frame/Storm basis: Storm-IN only / Storm-IN vs OUT comparison
- [ ] No Prediction: No lookahead
- [ ] Rule Supremacy: ML cannot change action (if applicable)

### Forbidden
- ❌ Changing criteria to optimize performance
- ❌ Adjusting thresholds after seeing conditions
- ❌ Selecting only convenient sample ranges

---

## 2) Data Scope (Fixed)

- **Dataset**: (file/period/asset/timeframe)
- **Unit of analysis**:
  - [ ] Candle-level
  - [ ] Event-level (Bar1 event)
  - [ ] Session-level (ENTER~EXIT)
- **Inclusion filter**: (e.g., storm_state==IN, is_bar1==True)
- **Exclusion filter**: (e.g., cold start, τ<2 = measurement unstable → NA)

---

## 3) Windmill Definition

Windmill = observation window / classification rule (NOT signal)

### Windmill Candidate (rule)
- **Input**: (e.g., VWAP_TOUCH, MA_ALIGN, DELTA_SPIKE)
- **Output**: PASS/REJECT or bucket label

### Windmill Family
- [ ] **Seat type**: Static position (distribution lower q%)
- [ ] **Folded type**: DC extreme, force sustain
- [ ] **Revisit type**: Anchored revisit, return-to-anchor
- [ ] **Session type**: entry→force→hold handoff

---

## 4) Hypothesis Definition

### H0 (null)
Windmill PASS/REJECT is unrelated to outcome (or session response)

### H1 (alt)
PASS creates meaningful difference in specific direction

**Direction must be explicit:**
- [ ] Risk reduction
- [ ] RR increase
- [ ] Revisit increase
- [ ] Other: _______________

**Example thresholds:**
- H1: LossRate(REJECT) - LossRate(PASS) ≥ 15pp
- H1: RR(PASS) - RR(REJECT) ≥ +0.5
- H1: RevisitRate(PASS) - RevisitRate(REJECT) ≥ +20pp

---

## 5) Outcome Metric (ONE only first)

**Rule: 1st experiment = 1 metric. Multi-metric = confirmation only.**

### Available Metrics
- **Risk**: LossRate, MAE_excess, immediate-death rate
- **Return proxy**: RR, forward return (3/5/10bar), MFE
- **Structure**: session duration, HOLD bars, EXTEND rate, handoff success

**Primary metric**: _____________

---

## 6) Judgment Criteria (Pre-registered)

- **Effect threshold**: (e.g., 15pp, +1.0 RR, 2x odds)
- **Sample minimum**:
  - Candle: N ≥ xxxx
  - Session: session ≥ 30 (min), ≥ 100 (strong)
- **Robustness requirement**:
  - [ ] Direction flips by distribution → FAIL
  - [ ] Same direction in 2+ regimes (LOW/MID/HIGH) → PASS

---

## 7) Invariance / Collapse Tests (REQUIRED)

### Invariance Tests
- [ ] Time resolution change (1m/5m) maintains direction?
- [ ] OBS_WINDOW change (2~5) maintains structure?
- [ ] τ_min change (4~6) maintains structure?
- [ ] FORCE_MIN change (8~15) maintains structure?

### Collapse Tests
- [ ] Remove one condition → does hypothesis collapse?
  - If collapse → "core cause candidate"
  - If no collapse → "decoration/component candidate"

---

## 8) Report Format (Fixed)

```
Dataset summary: N, period, asset

PASS/REJECT breakdown:
  PASS:   N=xxx, outcome_mean=xxx
  REJECT: N=xxx, outcome_mean=xxx
  diff=xxx
  verdict=PASS/FAIL

Distribution breakdown: VOL_LOW/MID/HIGH, Storm-IN/OUT

Negative results MUST be included (FAIL reason/counterexample)
```

---

## 9) Next Action Rules

### If PASS:
- ❌ No combination (don't make composite immediately)
- ✅ Next = independence experiment (cross-table/conditional)

### If FAIL:
- ✅ Discard rule (archive only)
- ✅ Propose 1 alternative hypothesis and repeat

---

## Example Request Sentences

### A: Windmill Census
"Treat all 'high-WR/high-RR/high-MFE/deep-Depth/ignition-entry' combinations in my data as windmill candidates, re-classify as PASS/REJECT under Storm-IN/Bar1 criteria. Verify which outcome metrics (RR, LossRate, RevisitRate) each candidate 'consistently' changes with H0/H1, report VOL_LOW/MID/HIGH invariance. Results = PASS/FAIL only, criteria pre-fixed."

### B: Pattern → 4D State Mapping
"View ELLIOT_3/VWAP_TOUCH/MA_ALIGN/DELTA_SPIKE patterns not as 'causes' but observations. Compare (Force, DC, τ, Vol bucket) distribution and session response (handoff, HOLD bars, RR) at each pattern occurrence. Include reverse validation: does same state give same RR even without pattern?"

### C: Alpha Creation
"Design alpha as gate for 'waste removal' only in Entry→Force handoff, not changing action. First verify gate on/off doesn't contaminate structure (H-1~H-5) via chi-square/distribution invariance, then map effect range to VOL_LOW/MID only."

---

**Template Version**: 1.0
**Created**: 2026-01-31
