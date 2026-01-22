# V7 Trading Constitution

> **Finalized**: 2026-01-22
> **Status**: Locked for Live Operation

---

## 1. Core Principle (헌법 제1조)

```
Ignition signals PROPOSE a state.
Persistence CERTIFIES the state.
Trading is allowed ONLY AFTER certification.
```

점화 신호는 상태를 **제안**하고,
Persistence는 상태를 **인증**하며,
거래는 인증 **이후에만** 허용된다.

---

## 2. Definitions

### Eligibility (점화 자격) - Tier1
| Model | Transition | Persistence | DD |
|-------|-----------|-------------|-----|
| 숏-정체 | 35/50 | 70%+ | <100pt |
| 숏 교집합 스팟 | 20/30 | 66%+ | <100pt |

Entry Eligibility Criteria:
- Transition Rate ≥ 60%
- Persistence ≥ 85%
- Max DD ≤ 100pt

### Certification (상태 인증) - θ
| θ | Meaning | Mode |
|---|---------|------|
| 0 | Ignition only (no certification) | Observation |
| 1 | 1+ consecutive success | **Practical** |
| ≥3 | 3+ consecutive success | **Conservative** |

### Physics Constants (물리 상수)
```python
MFE_THRESHOLD = 7       # State transition threshold (LOSS=0 after)
TRAIL_OFFSET = 1.5      # Energy preservation (78%)
LWS_BARS = 4            # Loss Warning State
DEFENSE_SL = 12         # G3 Soft SL
DEFAULT_SL = 30         # Default SL
TP = 20                 # Take Profit
PRICE_ZONE = 10         # Zone size for persistence
```

---

## 3. Why θ is NOT a Filter

θ is **Proof-of-State**, not a filter.

```
EV = E[Return | Eligibility] × P(State persists | θ)
```

As θ increases:
- ❌ Trade count ↓
- ❌ State uncertainty ↓
- ✅ DD ↓
- ✅ Variance ↓

This is not optimization. It is **paying more certification cost**.

| θ | Trades | Win Rate | EV | DD |
|---|--------|----------|-----|-----|
| 0 | 9,575 | 45.5% | 1.77pt | 5,524 |
| 1 | 4,261 | 90.2% | 16.65pt | 288 |
| 3 | 3,432 | 93.7% | 17.77pt | 132 |

---

## 4. Why 100% is NOT Overconfidence

### Tier1 + θ≥3 Results
| Split | Trades | Win Rate | EV | DD |
|-------|--------|----------|-----|-----|
| Train (60%) | 38 | 100% | 20.00pt | 0 |
| Test (40%) | 26 | 100% | 20.00pt | 0 |

### Constitutional Interpretation

✅ **Sample-bound statement**:
"In this data period, 0 losses occurred."

⚠️ **Conservative interpretation**:
"We do NOT claim 100% in the future."
"We expect very low DD, not zero DD."

### Adversarial Validation Passed (6/6)
1. SL-first worst-case → EV positive
2. Slippage -2pt → EV 15pt+ maintained
3. OOS 60/40 → Test performance improved
4. Bootstrap 10x → 100% structure maintained
5. G3 perturbation → Ranking preserved
6. Tier1 removal → Eligibility required

---

## 5. Authority Revocation Rules (권한 박탈 조건)

```python
# V7 EXECUTION AUTHORITY CHECK

# Basic condition
IF state_certified == False:
    TRADE = DENY  # No trading without certification

# State Collapse Prevention
IF consecutive_loss >= 2 in same_zone:
    TRADE = DENY  # State collapse detected

# Execution Friction Prevention
IF slippage > 3pt OR spread > 2pt:
    TRADE = DENY  # Execution conditions insufficient
```

### What These Rules Do NOT Include
- ❌ Win rate thresholds
- ❌ EV minimum requirements
- ❌ Time limits (verified: EV increases with time)

---

## 6. What is NOT Optimized

This system deliberately avoids:

| NOT Optimized | Reason |
|---------------|--------|
| Win rate | Post-hoc metric |
| EV maximization | Leads to overfit |
| Trade frequency | Quantity ≠ Quality |
| Parameter tuning | Physics constants fixed |

---

## 7. Operating Modes

### Mode A: Practical (θ=1)
```
Trades: 4,261 (90.7/day)
Win Rate: 90.2%
EV: 16.65pt
Daily EV: 1,509pt
DD: 288pt
```

### Mode B: Conservative (θ≥3)
```
Trades: 91 (1.9/day)
Win Rate: 100% (sample)
EV: 20.00pt
DD: 0pt (sample)
```

Use Case:
- **Mode A**: Normal operation
- **Mode B**: First live deployment, stress periods, survival mode

---

## 8. Constitutional Statement

> "Alpha exists not at entry, but only after state certification is confirmed."

> "알파는 진입이 아니라 상태 유지 확인 후에만 존재한다."

---

**Signature**: V7 Grammar System
**Lock Date**: 2026-01-22
