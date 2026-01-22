# 🧪 Experiments Directory

This directory contains research variants and aggressive options.

**Rule:** Never modify `core/` directly.  
**Flow:** `experiments/` → `validation/` → `core/` (promotion)

---

## Available Experiments

### mfe5_aggressive/
- MFE threshold = 5pt (higher harvest rate)
- Trade-off: Physical guarantee lost

### dynamic_tp/
- EV-BB based dynamic TP
- Status: Failed (prediction-based, not observation-based)

### evbb_variants/
- Various EV-BB implementations
- Status: Rejected for V7 core

### sl_defense_tests/
- SL defense variations (G1-G6)
- Winner: G3 (4 bars, SL-12)

---

## Experiment Protocol

1. Create subdirectory with descriptive name
2. Implement variant
3. Run backtest (N ≥ 100)
4. Document in `validation/`
5. If 6/6 passed → propose core promotion
