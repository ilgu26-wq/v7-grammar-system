# H6 실험: State Continuation Clause

## 핵심 질문

> 가격이 동일한 레벨로 복귀했을 때,
> '상태가 유지된 경우'에 한해 재숏이 알파를 가지는가?

---

## 기본 실험 결과 (H6)

### 데이터: state_backtest_result.json (1,154 trades)

| 지표 | Group A (신규 진입) | Group B (재도달+Persistence) |
|------|---------------------|------------------------------|
| 거래 | 935 | 24 |
| 승률 | 30.2% | **91.7%** |
| 총 PnL | -3,988 | **+380** |
| EV | -4.71pt | **+15.83pt** |

### 판정: ✅ H6 채택

```
Group B EV (+15.83pt) >> Group A EV (-4.71pt)
→ 상태가 유지되면 가격 재도달 시 재숏 가능
→ "에너지는 가격이 아니라 상태 공간에 저장된다"
```

---

## Persistence 조건 정의

**재숏 허용 조건 (모두 충족 시):**

```python
# 1. 이전 트레이드가 성공 (MFE >= 7pt 도달)
prev_result in ['TP', 'WIN']

# 2. 같은 가격대 재도달
abs(price_now - price_prev_entry) <= 2pt

# 3. 적정 간격 (너무 빠르면 노이즈)
idx_diff >= 10 bars
```

---

## H6 헌법 조항 (State Continuation Clause)

```
[H6 — State Continuation Clause]

If a position has reached the energy threshold (MFE >= 7pt)
and the previous trade was successful,
a revisit to the same price zone (±2pt) is not a new prediction,
but a continuation of the same state.

Rules:
1. Re-entry permitted only after successful previous trade
2. Maximum 2 re-entries per state
3. Re-entry uses fast SL (-12pt) after 4 bars
4. State is DEAD if consecutive loss occurs

Expected EV: +15.83pt per re-entry
```

---

## 물리학적 해석

### ❌ 틀린 사고

```
"가격이 같은 자리니까 또 떨어지겠지"
"고점 리테스트니까 숏"
→ 예측 사고
```

### ✅ V7식 사고

```
"이전에 에너지가 발생했고, 상태가 아직 살아있다"
"같은 가격은 새로운 좌표가 아니라 상태 연장"
→ 상태 연속 사고
```

---

## H5와 H6의 관계

| 가설 | 내용 | 판정 |
|------|------|------|
| H5 | 재진입(STB 재발생)은 정보 없음 | ✅ 폐기 |
| H6 | 재도달 + Persistence는 정보 있음 | ✅ 채택 |

```
차이점:
H5 = "다시 불을 붙이려는 시도" → ❌
H6 = "아직 타고 있는 불에 연료 추가" → ✅
```

---

## 강화 실험 제약

현재 데이터 구조 제약:
- state_backtest_result.json에 MFE 값 없음
- Persistence Score 정확한 계산 불가

향후 필요:
- 개별 트레이드 MFE 데이터
- 실시간 Persistence Score 로깅

---

## 결론

> V7에서는 가격은 반복될 수 있지만
> 상태는 반복되지 않는다.
>
> 단, Persistence가 유지되면
> 같은 가격대에서 상태가 "연장"된다.
> 이때만 재숏 허용.
