## Paper Consistency Summary

This report verifies that all paper executions
are preceded by valid V7 decisions.

No execution was observed without a decision.


> Generated: 2026-01-23T20:52:55.051953
> Source: v7-grammar-system/opa/paper_mode_logs.json

---

## 1. Basic Statistics

| Metric | Value |
|--------|-------|
| Total Trades | 133 |
| Win Rate | 52.6% |
| Total PnL | 455.0 pt |
| Avg PnL | 3.42 pt |
| Audit All Pass | ✅ |
| Ready for Live | ✅ |

---

## 2. Theta Breakdown

| Theta | Entries | TP | SL | Win Rate | Total PnL |
|-------|---------|----|----|----------|-----------|
| theta_0 | 134 | 70 | 63 | 52.6% | 455.0 |

**Analysis:**
- All entries occur at theta=0 (pre-confirmation phase)
- SL occurrence in theta=0 is structurally expected
- theta≥3 execution attempts = 0 ✅

---

## 3. Direction Breakdown

| Direction | Entries | TP | SL | Win Rate | Total PnL |
|-----------|---------|----|----|----------|-----------|
| SHORT | 122 | 64 | 57 | 52.9% | 425.0 |
| LONG | 12 | 6 | 6 | 50.0% | 30.0 |

---

## 4. Channel Performance

| Channel % | Trades | Win Rate | Total PnL | Avg PnL |
|-----------|--------|----------|-----------|---------|
| 0-20 | 31 | 74.2% | 340.0 | 10.97 |
| 20-50 | 40 | 55.0% | 170.0 | 4.25 |
| 50-80 | 35 | 45.7% | 35.0 | 1.0 |
| 80-100 | 27 | 33.3% | -90.0 | -3.33 |

---

## 5. Honesty Check

| Check | Result |
|-------|--------|
| All Theta = 0 | ✅ |
| No Theta≥3 Execution | ✅ |
| Scope = t-ε | ✅ |
| Audit Violations = 0 | ✅ |

---

## 6. Conclusion

### System Integrity: ✅ VERIFIED

1. **Decision-Execution Consistency:** All entries go through OPA layer
2. **Theta Protection:** No theta≥3 execution attempts
3. **SL Explanation:** All SL occur in theta=0 (structurally expected)
4. **Audit Status:** All checks passed

> "This system does not lie to me."

---

**Document Type:** Analysis Report
**Purpose:** Verify Paper execution reflects V7 decisions faithfully
