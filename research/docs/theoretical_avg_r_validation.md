# Theoretical Avg R Validation Plan

## Objective

Validate whether the theoretical Avg R derived from fixed TP/SL geometry
remains consistent under realized execution.

## Theoretical Reference

| Parameter | Value |
|-----------|-------|
| STB TP-first rate | 94.1% |
| TP | +2R (20pt) |
| SL | -1R (10pt) |
| **Theoretical Avg R** | **1.823R** |

### Calculation

Avg R = 0.941 × (+2R) + 0.059 × (-1R) = 1.823R


## Hypothesis

**H₀ (Null):** Realized Avg R is statistically consistent with theoretical Avg R (1.82R)
within predefined tolerance.

**H₁ (Alternative):** Realized Avg R deviates significantly from theoretical value.

## Validation Phases

| Phase | Min Trades | Purpose | Status |
|-------|------------|---------|--------|
| 1 | n ≥ 30 | Sanity check | PENDING |
| 2 | n ≥ 100 | README registration threshold | PENDING |
| 3 | n ≥ 300 | Confidence stabilization | PENDING |

## Acceptance Criteria

For README registration (Phase 2):

n ≥ 100
AND |ΔR| ≤ 0.30R
AND 95% CI includes 1.82R


### Statistical Method

- Test: One-sample t-test
- α: 0.05
- Comparison: Realized Avg R vs μ = 1.82R

## Current Status

**PENDING_VALIDATION**

Theoretical value calculated. Awaiting live shadow trades for validation.

## Notes

This validation is not intended to prove profitability.
It verifies whether the TP/SL geometry produces expected outcomes
under real execution conditions.

---

*Last Updated: 2026-01-20*
