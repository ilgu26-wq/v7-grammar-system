# Depth Realtime Tracking Schema v1

## 목적

Depth를 '결과 요약값'이 아니라 '시간에 따른 상태변수'로 추적한다.
이를 통해 "수렴 가능 조건이 언제 성립하는가?"에 답한다.

---

## 핵심 공식

```python
depth = (high_20 - close) / range_20

# range_20 = high_20 - low_20
# depth ∈ [0, 1]
# depth = 0 → 가격이 20봉 고점에 있음
# depth = 1 → 가격이 20봉 저점에 있음
```

---

## 로그 스키마 (v1)

```
ts, idx, depth, depth_slope, terminal, island_id, burst_event, dc_pre, er, delta, channel
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `ts` | int | Unix timestamp (ms) |
| `idx` | int | 바 인덱스 |
| `depth` | float | 현재 depth 값 [0, 1] |
| `depth_slope` | float | 최근 5바 depth 변화율 |
| `terminal` | str | FAST / SLOW |
| `island_id` | str | FAST일 때만, 8축 조합 ID |
| `burst_event` | int | 0/1 (Bar1/Burst 감지 여부) |
| `dc_pre` | float | 직전 압축도 |
| `er` | float | 효율 비율 |
| `delta` | float | 델타 절대값 |
| `channel` | float | 채널 % |

---

## 이벤트 레이블 (3개)

| 레이블 | 정의 | 조건 |
|--------|------|------|
| **FORM** | Depth 형성 시작 | depth < 0.3 → slope > +0.15 |
| **DISSIPATE** | Depth 소산 시작 | depth > 0.7 → slope < -0.15 |
| **TRANSITION** | 경계 교차 | depth가 0.5를 넘는 순간 |

---

## 실험 설계

### 목표
Depth 형성/소산/전이의 **선행 조건**이 존재하는지 검증

### 프로토콜
1. 전 구간에서 `depth_t` 시계열 생성
2. FORM/DISSIPATE/TRANSITION 이벤트 타임스탬프 생성
3. 각 이벤트의 직전 윈도우(-30bar ~ -1bar)에서 조건 피처 집계
4. 이벤트 없는 구간(랜덤 샘플)과 비교
5. 리프트/우도비/재현율로 판정

### 판정 기준
- event 대비 non-event에서 LR ≥ 3
- OOS fold 5개 중 4/5 이상 재현

---

## 핵심 원칙

```
실시간에서 하는 일:
  depth_t 갱신 + state(world) 갱신 + event 기록

사후에서 하는 일:
  이벤트 직전 조건을 모아서 "선행 조건"인지 검정
```

이 분리는 "관측/비예측" 원칙과 충돌하지 않는다.

---

## 다음 단계

EXP-DEPTH-DYNAMICS-01 실행 후:

1. FORM/DISSIPATE/TRANSITION 각각의 유의미한 선행 조건 식별
2. 조건이 사전 정의 가능한지 판정
3. 가능하다면 → 실시간 "수렴 가능 상태" 플래그 추가
4. 불가능하다면 → 사후 관측으로만 사용 (여전히 유효)

---

*Created: 2026-02-01*
*Phase: Causal Dynamics*
