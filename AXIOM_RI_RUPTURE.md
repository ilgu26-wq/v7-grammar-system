# AXIOM: RI Rupture Rules (봉인 문서)

**승격일:** 2026-02-02
**검증:** EXP-RULE-CONSISTENCY-VALIDATION-01 (3/4 테스트 통과)

---

## 핵심 선언

> "RI SPIKE는 시장에서의 혈관 파열에 해당하며, 위치·시간·자산에 무관한 금지 상태다."

---

## 검증된 AXIOM 규칙

### R-SPIKE (Hard Kill)
```
IF RI > q95:
    KILL  # 71.1% collapse
```
- **Precision:** 71.1%
- **Coverage:** 5.0%
- **Lift:** 1.77x
- **위치 독립성:** ✓ (Q1-Q4 모두 69-77%)
- **시간 독립성:** ✓ (CV=0.10)
- **무작위성 반증:** ✓ (셔플 시 39.6%로 붕괴)

### R-PLATEAU_90 (Soft Kill)
```
IF RI > q90 for ≥3 bars:
    THROTTLE  # 53.2% collapse
```
- **Precision:** 53.2%
- **Coverage:** 6.1%
- **Lift:** 1.34x

---

## 극단 조합

| 조건 | Collapse Rate |
|------|---------------|
| ZPOC DEAD + SPIKE | **91.7%** |
| ZPOC ALIVE + SPIKE | 43.3% |
| ZPOC DEAD + NONE | 84.8% |
| ZPOC ALIVE + NONE | 36.8% |

---

## 최종 실행 로직 (튜닝 금지)

```python
# World Validity Layer
if IE < 2.0 or IE > 4.5:
    kill()  # 세계 사망/과잉

# AXIOM: Hard Rupture
elif RI > q95:
    kill()

# Soft Pressure
elif RI > q90 for >= 3 bars:
    throttle()

# Safe Zone
else:
    allow()
```

---

## 시스템 구조 (확정)

```
[IE]           세계 생존 여부 (2.0 ≤ IE ≤ 4.5)
   ↓
[ZPOC/ECS]     기준 좌표 + 연결 구조
   ↓
[RI]           혈류 압력
   ↓
[RI Pattern]   파열 형태 ← AXIOM RULES
   - SPIKE (q95) → Hard Kill ⛔
   - PLATEAU_90 → Soft Kill ⚠️
   ↓
[V7 Grammar]   결정 문법
```

---

## 불변 원칙

1. **SPIKE는 예측이 아니라 금지다** - 이 상태에서 판단하면 안 됨
2. **위치·시간·자산 무관** - 어디서든 같은 의미
3. **Recovery는 손상 신호** - 안정이 아니라 부상 표시
4. **IE U-curve** - 과소/과잉 연결 모두 위험, 중간이 안전

---

## 검증 데이터

- **데이터:** MNQ December 2025 (19,400 bars)
- **Collapse 정의:** Strict (ER<0.15 OR ER_drop>0.5 OR Price_drop>5x, 2/3 조건)
- **Threshold:** q95=143.41, q90=69.14

---

*이 문서는 수정 대상이 아닌 봉인 문서입니다.*
