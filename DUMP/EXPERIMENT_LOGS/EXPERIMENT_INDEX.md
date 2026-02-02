# Experiment Index

All experiments conducted during the Depth-Based World Partition phase.

## Core Experiments (Phase O)

| Experiment | File | Purpose | Result |
|------------|------|---------|--------|
| EXP-ALL-LAWS-JOINT-01 | exp_all_laws_joint_01.py | 8-axis full combination analysis | **PROOF A confirmed** |
| EXP-OOS-VALIDATION-01 | exp_oos_validation_01.py | 5-fold OOS validation | 3/4 islands stable |
| EXP-CONSOLIDATED-01 | exp_consolidated_01.py | H1-H5 hypothesis test | 4/5 PASS |
| EXP-RANGE-TERMINAL-01 | exp_range_terminal_01.py | Range normalization | Fast/Slow separation |
| EXP-TYPEC-RESOLUTION-01 | exp_typec_resolution_01.py | Type C false positive analysis | All Type C = Soft Terminal |
| EXP-E-RESP-SPEED-01 | exp_e_resp_speed_01.py | Transition speed measurement | Median 8.0 bars |

## Supporting Experiments

| Experiment | File | Purpose | Result |
|------------|------|---------|--------|
| EXP-ABSORB-OPS-01 | exp_absorb_ops_01.py | Absorb operation analysis | Completed |
| EXP-GRAMMAR-GEN-01 | exp_grammar_gen_01.py | Grammar generation test | Completed |
| EXP-GRAMMAR-ROBUST-01 | exp_grammar_robust_01.py | Grammar robustness test | Completed |
| EXP-E-RESP-ADV-01 | exp_e_resp_adv_01.py | E_RESP adversarial test | Completed |
| ADVERSARIAL-TESTS | adversarial_tests.py | Full adversarial suite | Completed |

## Output Files

Each experiment produces:
- `*_full.txt` - Full console output
- `*.json` - Machine-readable results

## Data Source

All experiments use:
- `data/chart_combined_full.csv` (27,973 bars)
- Sample step: every 10 bars = 2,783 events

## Reproducibility

To reproduce any experiment:
```bash
cd /home/runner/workspace
PYTHONPATH=v7-grammar-system python v7-grammar-system/analysis/phase_o/<experiment>.py
```
