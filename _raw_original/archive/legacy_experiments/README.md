### 🧪 experiments/

This directory contains **research variants and aggressive options**.
All experimental logic must be isolated here.

**Rule:** Never modify `core/` directly.  
**Promotion Flow:** `experiments/` → `validation/` → `core/`

This ensures execution integrity and prevents unvalidated logic
from contaminating the core system.

---

#### mfe5_aggressive/
- MFE threshold = 5pt (higher harvest rate)
- Trade-off: physical profit guarantee lost

#### dynamic_tp/
- EV-BB based dynamic TP
- Status: **Failed**
- Reason: prediction-based, not observation-based

#### evbb_variants/
- Various EV-BB implementations
- Status: **Rejected for V7 core**

#### sl_defense_tests/
- Stop-loss defense variations (G1–G6)
- Winner: **G3** (4 bars, SL −12)

---

#### Experiment Protocol

1. Create a subdirectory with a descriptive name
2. Implement the variant
3. Run backtests (N ≥ 100)
4. Document results in `validation/`
5. If all criteria pass → propose promotion to `core/`
