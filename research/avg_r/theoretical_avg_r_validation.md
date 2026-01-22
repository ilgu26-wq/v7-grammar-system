# Theoretical Avg R Consistency Validation Plan

## Objective

Validate whether the realized average R under live execution
remains **structurally consistent** with the theoretical expectation
implied by a fixed TP/SL geometry.

This validation **does not aim to prove profitability**.
Its sole purpose is to verify whether execution realities
materially degrade the expected payoff geometry.

---

## Theoretical Reference (Upper-Bound)

| Parameter | Value |
|-----------|-------|
| STB TP-first rate | 94.1% |
| TP | +2R (20pt) |
| SL | -1R (10pt) |
| **Theoretical Reference Avg R** | **1.82R (upper-bound)** |

### Reference Calculation

Avg R = 0.941 × (+2R) + 0.059 × (−1R) = **1.82R**

> **Note**  
> This value represents an **idealized upper-bound reference**, assuming
> immediate TP/SL resolution without slippage, latency, or execution friction.
> It is **not** a claim about realized performance.

---

## Hypothesis

**H₀ (Consistency Hypothesis):**  
The realized Avg R does not exhibit statistically significant
*structural degradation* relative to the theoretical upper-bound (1.82R),
within predefined tolerance.

**H₁ (Degradation Hypothesis):**  
The realized Avg R shows material deviation inconsistent with
the expected TP/SL payoff geometry.

---

## Validation Phases

| Phase | Min Trades | Purpose | Status |
|-------|------------|---------|--------|
| 1 | n ≥ 30 | Sanity & distribution check | DATA_COLLECTION |
| 2 | n ≥ 100 | README registration threshold | DATA_COLLECTION |
| 3 | n ≥ 300 | Confidence stabilization | DATA_COLLECTION |

---

## Acceptance Criteria  
*(Phase 2 – README Eligibility)*

The theoretical payoff geometry is considered **consistent** if **all**
conditions below are satisfied:

- n ≥ 100 (STB signals only)
- |ΔR| ≤ 0.30R relative to 1.82R
- 95% confidence interval of realized Avg R includes 1.82R
- No persistent skew indicating systematic payoff degradation

Failure to meet these criteria does **not** invalidate the system;
it flags execution-driven degradation for further analysis.

---

## Statistical Methods

**Primary Test**
- One-sample t-test
- Significance level: α = 0.05
- Null mean: μ = 1.82R

**Robustness Checks**
- Bootstrap confidence interval of mean R
- Median R comparison against theoretical expectation
- Distribution shape inspection (skew / tail dominance)

---

## Current Status

**DATA_COLLECTION**

- Theoretical upper-bound reference defined
- No STB-only realized Avg R dataset available yet
- Validation will begin automatically once minimum sample thresholds are met

---

## Notes

- This validation explicitly separates **decision quality**
  from portfolio-level profitability.
- Existing historical metrics (e.g., system-wide Avg R ≈ 0.28R)
  are **not comparable**, as they include non-STB signals.
- All results will be evaluated exclusively on
  **real-time recorded STB executions**.

---

*Last Updated: 2026-01-20*
