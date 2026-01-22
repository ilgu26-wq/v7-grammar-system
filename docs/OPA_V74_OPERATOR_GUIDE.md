# OPA v7.4 Operator Guide

> **Version**: v7.4  
> **Status**: Production Ready  
> **Date**: 2026-01-22

---

## 1. OPA의 역할

```
OPA = Operational Policy Authority (운용 정책 권한)

❌ OPA는 시장을 예측하지 않는다
✅ OPA는 시장의 상태를 판별하고, 실행 권한을 부여한다
```

핵심 원칙:
- **"V7은 시장을 예측하지 않는다. 시장이 스스로 위치를 드러내게 한다."**
- **"실행 성공은 진입 시점에 결정된다. 청산 시점이 아니다."**

---

## 2. θ (Theta) 상태 정의

| θ | 이름 | 의미 | 실행 |
|---|------|------|------|
| 0 | No State | 상태 아님, 순수 노이즈 | **DENY** |
| 1 | State Birth | 방향성 우위 시작, 반전 가능 | ALLOW |
| 2 | State Transition | 방향성 우위 형성 중 | ALLOW (조건부) |
| ≥3 | State Lock-in | 비가역 상태, 확장 가능 | ALLOW |

---

## 3. θ별 허용 행동 테이블

| θ | Size | Retry | Trailing | 비고 |
|---|------|-------|----------|------|
| 0 | - | - | - | **실행 금지** |
| 1 | SMALL | ❌ | ❌ | 고정 TP만 |
| 2 | SMALL/MEDIUM | 조건부 | ❌ | Retry 조건 충족 시 MEDIUM |
| ≥3 | LARGE | ✅ | Optional | 확장 가능 |

---

## 4. Size 정책

| Size | Multiplier | 적용 조건 |
|------|------------|-----------|
| SMALL | 1.0x | θ=1, θ=2 (기본) |
| MEDIUM | 2.0x | θ=2 + Retry 조건 충족 |
| LARGE | 4.0x | θ≥3 |

**DD 선형성 검증 완료**: Size를 2배로 올리면 DD도 정확히 2배.  
이는 시스템이 확률 시스템이 아닌 **상태 기계**임을 증명.

---

## 5. Retry 정책 (θ=2 Only)

### 조건
```
impulse_count > 2 AND recovery_time < 4
```

### 동작
- 조건 충족 시: MEDIUM Size 허용
- 조건 미충족 시: SMALL Size만 허용
- θ=1, θ≥3에서는 Retry 조건 미적용

### 검증 결과
- Precision: 100%
- Recall: 99.8%
- 평균 리드타임: 11.4 bars

---

## 6. Trailing 정책

| θ | Trailing | 이유 |
|---|----------|------|
| 0 | 금지 | 상태 없음 |
| 1 | 금지 | 반전 가능성 |
| 2 | 금지 | 상태 미고착 |
| ≥3 | Optional | 비가역 상태 확인됨 |

**원칙**: θ<3에서 Trailing 시도 = 헌법 위반

---

## 7. 절대 금지 규칙

| 금지 행동 | 이유 |
|----------|------|
| θ=0 실행 | 100% SL (5,222건 검증) |
| STB 즉시 실행 | 0% 승률 (55건) |
| θ<3 Trailing | 상태 미고착 |
| 조기 신호 가속 | 144건 = 0 TP |
| Blacklist 신호 실행 | 검증 실패 |

### Blacklist 신호
- 매수스팟, 매도스팟
- 빗각버팀, 저점상승
- 횡보예상_v1

---

## 8. 실운용 체크리스트 (배포 전)

### 필수 확인
- [ ] θ=0에서 실행 차단 확인
- [ ] θ=2 Retry 조건 검증
- [ ] θ≥3 LARGE Size 적용 확인
- [ ] Blacklist 신호 차단 확인
- [ ] Trailing은 θ≥3에서만 활성화

### 금지 확인
- [ ] experiments/ 폴더가 운용 코드에 import 안 됨
- [ ] policy_v74.py 수정 없음
- [ ] 실험 결과로 정책 변경 시도 없음

---

## 9. 운용 모드

### Mode A: NORMAL (θ≥1)
```
거래 수: ~201/일
승률: 92%
EV: 17.45pt/일
Trailing: 금지
```

### Mode B: CONSERVATIVE (θ≥3 + Tier1)
```
거래 수: ~6.4/일
승률: 100%
EV: 20pt/거래
확장: 선택적
```

---

## 10. 핵심 파라미터 (물리 상수)

```python
TP = 20              # Take Profit
SL = 12              # Stop Loss (Defense)
MFE_THRESHOLD = 7    # State transition
TRAIL_OFFSET = 1.5   # Energy preservation
LWS_BARS = 4         # Loss Warning State
PRICE_ZONE = 10      # Zone size
```

---

**이 문서는 운용 가이드입니다.**  
**정책 변경은 v7.5로 새 버전 생성 필요.**
