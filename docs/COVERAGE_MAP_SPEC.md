# Coverage Map Specification

> **목적**: 모든 이벤트가 어딘가에 속하도록 보장. UNKNOWN = 0%

---

## 1. Coverage 계약

```
모든 ENTER는 반드시 다음 3개 버킷에 귀속된다:
  1. STATE_bucket  (방향 상태)
  2. STB_bucket    (진입 허용 조건)
  3. POST_bucket   (사후 결과 레이블)

UNKNOWN_BUCKET_RATE = 0% → Coverage 완료 선언
```

---

## 2. 버킷 정의

### STATE_bucket (방향 안정화 상태)
| ID | 조건 | 설명 |
|----|------|------|
| S0 | default | 기본 상태 |
| S1 | RISE detected | 상승 구조 감지 |
| S2 | FALL detected | 하락 구조 감지 |
| S3 | SIDEWAYS | 횡보 (range < 30pt) |

### STB_bucket (진입 허용 조건)
| ID | 조건 | 설명 |
|----|------|------|
| T0 | OPA layer | OPA 진입 허용 |
| T1 | STB layer | STB 진입 허용 |
| T2 | DEFENSE applied | 방어 모드 |
| T_DENY | 진입 거부 | 어떤 조건도 미충족 |

### POST_bucket (사후 결과 레이블)
| ID | 조건 | 설명 |
|----|------|------|
| θ=0 | MFE < TP*0.3 | 미도달 |
| θ=1 | TP*0.3 ≤ MFE < TP*0.7 | 부분 도달 |
| θ=3 | MFE ≥ TP*0.7 | 확정 도달 |
| P_OPEN | 미청산 | 진행 중 |

---

## 3. BUCKET_ID 생성 규칙

```python
BUCKET_ID = f"{STATE_bucket}_{STB_bucket}_{POST_bucket}"

# 예시:
# "S1_T0_θ3" = RISE + OPA진입 + 확정도달
# "S3_T_DENY_P_OPEN" = 횡보 + 진입거부 + 진행중
```

---

## 4. Coverage 검증 프로세스

```
1. 모든 trades 로드
2. 각 trade에 BUCKET_ID 부여
3. UNKNOWN 개수 카운트
4. UNKNOWN > 0 → Coverage 실패
5. UNKNOWN = 0 → Coverage 완료 선언
```

---

## 5. 설명 책임 범위

| 항목 | 책임 | 비고 |
|------|------|------|
| 가격 방향 예측 | ❌ 책임 없음 | 예측 시스템 아님 |
| 결정 영역 분류 | ✅ 책임 있음 | 문법의 핵심 역할 |
| 결과 귀속 | ✅ 책임 있음 | θ 레이블로 완료 |
| 실패 설명 | ✅ 책임 있음 | RESIDUAL_REGISTER로 완료 |

---

## 6. θ≥3 실패 처리

θ≥3에서 실패가 발생해도:
- **문법 위반 아님**: 허용 영역 내 확률적 결과
- **설명 완료**: RESIDUAL_REGISTER.json에 등록
- **규칙 추가 금지**: 사후 최적화는 overfitting

```
θ≥3 실패 = EXPLAINED_FAILURE
         ≠ UNEXPLAINED_GAP
```

---

## 7. 최종 선언

```
V7 Grammar System의 Coverage 목표:

"모든 이벤트는 어딘가에 속한다.
 설명 못 하는 이벤트는 존재하지 않는다.
 
 실패는 확률이지, 구멍이 아니다."
```

---

*Created: 2026-01-25*
*Status: ACTIVE*
