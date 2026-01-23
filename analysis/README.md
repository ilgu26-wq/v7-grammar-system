# Analysis Directory

This analysis verifies that Paper execution reflects V7 decisions faithfully, without signal leakage or execution-layer distortion.

## Files

| File | Description |
|------|-------------|
| `paper_consistency_report.json` | Full analysis data (machine-readable) |
| `paper_consistency_summary.md` | Human-readable summary report |
| `paper_consistency_analysis.py` | Analysis script |

## Purpose

- Verify V7_DECISION → OPA_EXECUTION consistency
- Confirm theta-based protection (no theta≥3 execution)
- Validate that SL occurrences are structurally expected
- Ensure no audit violations

## Key Findings

- All entries occur at theta=0 (pre-confirmation phase)
- SL occurrence is structurally expected in t-ε scope
- Audit checks: ALL PASS
- System integrity: VERIFIED

## Paper Consistency Analysis

This module verifies that paper-mode executions faithfully reflect
V7 decision outputs without distortion.

It audits:
- V7 decision ↔ OPA execution identity
- Theta-bound execution constraints
- Structurally expected SL behavior
- Scope (t-ε) execution timing
- Reproducibility and audit honesty

Outputs:
- paper_consistency_report.json
- paper_consistency_summary.md

---

**Generated:** 2026-01-23
