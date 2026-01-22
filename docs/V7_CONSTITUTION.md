# V7 Trading Constitution

> **Finalized**: 2026-01-22
> **Status**: Locked for Live Operation
> **Version**: v7.3

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

## 2. θ (Theta) State Definitions

### State Classification

```
θ = 0  : No State (상태 아님)
         → No market consensus, pure noise
         → Execution DENIED

θ = 1  : State Birth (상태 생성)
         → Directional dominance begins
         → Reversal still possible
         → Execution ALLOWED, Fixed TP only

θ = 2  : State Transition (상태 전이)
         → Directional dominance forming
         → Reversal probability decreasing
         → Execution ALLOWED, Fixed TP only

θ ≥ 3 : State Lock-in (상태 고착)
         → Irreversible state
         → Extension possible
         → Execution ALLOWED, Extension optional
```

### Constitutional Statements

> **"θ=1 certifies the existence of a market state."**
> **"θ≥3 certifies the irreversibility of that state."**
> **"θ=2 certifies directional dominance, but not irreversibility."**

### θ=2 Observability Note

> "θ=2 may not be directly observable in outcome-based logs, but is inferred as a necessary transition phase between state birth and lock-in."

---

## 3. Execution Rules (실행 규칙)

```python
If θ = 0:
    Execution DENIED
    
If θ = 1 or θ = 2:
    Execution ALLOWED
    Fixed TP only (TP=20pt, SL=12pt)
    Trailing PROHIBITED
    
If θ ≥ 3:
    Execution ALLOWED
    Fixed TP or Optional Extension
```

---

## 4. STB Role Definition

> **"STB is an ignition sensor, not an execution trigger."**
> **"Execution is permitted only after persistence certification (θ≥1)."**

### Empirical Evidence

| Execution Method | Trades | TP | SL | Win Rate |
|-----------------|--------|----|----|----------|
| STB Immediate (θ=0) | 55 | 0 | 55 | **0%** |
| STB + θ≥1 | 297 | 98 | 0 | **100%** |
| STB + θ≥3 | 98 | 98 | 0 | **100%** |

---

## 5. Entry vs Exit Principle

> **"Execution success is determined at entry, not at exit."**
> **"Exit logic only allocates profit after the state is confirmed."**

### Empirical Evidence

| Entry Condition | Exit Method | Win Rate |
|-----------------|-------------|----------|
| θ=0 | Fixed TP | 0% |
| θ=0 | Pure Trail | 0% |
| θ=0 | MFE Dynamic | 0% |
| θ≥3 | Fixed TP | 100% |
| θ≥3 | Pure Trail | 100% |
| θ≥3 | MFE Dynamic | 100% |

---

## 6. Physics Constants (물리 상수)

```python
MFE_THRESHOLD = 7       # State transition threshold
TRAIL_OFFSET = 1.5      # Energy preservation (78%)
LWS_BARS = 4            # Loss Warning State
DEFENSE_SL = 12         # Defense SL
TP = 20                 # Take Profit
PRICE_ZONE = 10         # Zone size for persistence
```

---

## 7. Operating Modes

### Mode A: NORMAL (θ≥1)
```
Trades: ~201/day
Win Rate: 92%
EV: 17.45pt/day
Trailing: PROHIBITED
```

### Mode B: CONSERVATIVE (θ≥3 + Tier1)
```
Trades: ~6.4/day
Win Rate: 100% (sample)
EV: 20pt/trade
Extension: OPTIONAL
```

---

## 8. Prohibited Actions

| Action | Reason |
|--------|--------|
| ❌ θ=0 Execution | 100% SL (5,222 trades verified) |
| ❌ STB Immediate | 0% win rate (55 trades) |
| ❌ Trailing @ θ<3 | State not locked |
| ❌ Early Signal Acceleration | 144 trades = 0 TP |
| ❌ Sector Weighting | Adds risk, no benefit |
| ❌ MFE-based Exit | Diagnostic only, not execution |

---

## 9. Consistency Verification

### Period Consistency ✅
| θ | 1st Half | 2nd Half |
|---|----------|----------|
| 0 | 0% | 0% |
| 3 | 100% | 100% |

### Exit Method Consistency ✅
| θ | TP15/SL10 | TP20/SL12 | TP25/SL15 | TP30/SL18 |
|---|-----------|-----------|-----------|-----------|
| 0 | 0% | 0% | 0% | 0% |
| 3 | 100% | 100% | 100% | 100% |

---

## 10. Architecture Summary

```
[Entry Layer] ← Determines success
├─ STB = Ignition Sensor
├─ θ = State Certification
└─ OPA = Execution Authority

[Exit Layer] ← Allocates profit
├─ Default: Fixed TP (TP=20, SL=12)
├─ Optional: Pure Trail (θ≥3 only)
└─ MFE: Diagnostic indicator only
```

---

## 11. Constitutional Statement

> "Alpha exists not at entry, but only after state certification is confirmed."

> "알파는 진입이 아니라 상태 유지 확인 후에만 존재한다."

> "In this system, loss is not an exception but a consequence of constitutional violation."

> "우리 시스템에서 손실은 예외가 아니라, 헌법 위반의 결과로만 발생한다."

---

**Signature**: V7 Grammar System
**Lock Date**: 2026-01-22
**Version**: v7.3
