# Graveyard Appendix — Discarded Ideas Log

*This appendix lists ideas that were tested and discarded before reaching the documented evolution timeline.*

*These ideas failed early, failed silently, or failed without producing reusable structure.*

*They are preserved here for completeness, not justification.*

---

## 1. Killed Without Promotion (Early Death)

### 1.1 SPS배율숏 / SPS배율롱
```json
{
  "signal": "SPS배율숏",
  "win_rate": 25.6,
  "sample": 1658,
  "reason": "50% 미달",
  "blocked_date": "2026-01-12"
}
{
  "signal": "SPS배율롱", 
  "win_rate": 25.7,
  "sample": 1415,
  "reason": "50% 미달",
  "blocked_date": "2026-01-12"
}
```
**Death cause:** Random-level accuracy (~25% = worse than coin flip)
**Sample size:** Large (1400-1600+), so failure is statistically significant

### 1.2 배율>=1.5_숏 / 배율>=2.0_숏
```json
{
  "signal": "배율>=1.5_숏",
  "win_rate": 24.6,
  "sample": 3955,
  "reason": "50% 미달"
}
{
  "signal": "배율>=2.0_숏",
  "win_rate": 26.2,
  "sample": 1681,
  "reason": "50% 미달"
}
```
**Original hypothesis:** "High ratio = overbought = short signal"
**Reality:** Ratio alone has NO predictive power
**Learning:** Ratio only works as STATE classifier, not entry trigger

### 1.3 저배율_돌파
```json
{
  "signal": "저배율_돌파",
  "win_rate": 24.2,
  "sample": 389,
  "reason": "예측력 없음 (랜덤수준)"
}
```
**Original hypothesis:** "Low ratio + breakout = long signal"
**Reality:** 24.2% = worse than random
**Death sentence:** "예측력 없음"

---

## 2. Looked Promising, Collapsed Later

### 2.1 공식1: ≤5캔들 + ≥7%
```json
{
  "formula": "공식1: ≤5캔들 + ≥7%",
  "total": 25,
  "reach_rate": 100.0,
  "win_rate": 36.0
}
```
**Initial excitement:** 100% reach rate!
**Collapse:** 36% win rate (losing money)
**Learning:** Reach ≠ Win

### 2.2 Dual AI Verification System
```json
{
  "architecture": "Trading AI + Validator AI",
  "goal": "0% 손실률 A급 신호 시스템",
  "status": "abandoned"
}
```
**Original concept:**
- Trading AI generates signals
- Validator AI confirms
- Dual consensus = A-grade

**Why it died:**
- Complexity ≠ accuracy
- AI consensus ≠ market consensus
- Eventually replaced by simple θ classification

### 2.3 A-Grade Detection System
```json
{
  "total_bars": 4532,
  "a_grade_count": 1110,
  "a_grade_percentage": 24.5
}
```
**Fatal flaw:** If 24% of bars are "A-grade," there is no edge.
**Original rules:**
- SPS Z-score >= 2.0
- Cluster count >= 4
- VPOC retest <= 15 ticks

**Why it died:** Over-detection. Signal became noise.

---

## 3. Regime-Dependent Inversions

### 3.1 Spread Day Logic
```json
{
  "S1": "안정화 실패 - ATR 스파이크 후 7봉 이상",
  "S2": "구조적 스트레스 - PingPong, Gap, WickExcess",
  "TRUE_BLACK": "S1 AND S2",
  "threshold": "TRUE BLACK 비율 >= 0.35%"
}
```
**Original purpose:** Avoid trading on chaotic days
**Problem:** Definition was regime-dependent
**Death:** Replaced by θ state system (simpler, more robust)

### 3.2 Sector-Based SPS
```json
{
  "상승/상상": {"bull_sps": 0.162, "bear_sps": 0.142, "n": 451},
  "상승/상중": {"bull_sps": 0.161, "bear_sps": -0.159, "n": 135},
  "하락/상상": {"bull_sps": 0.055, "bear_sps": 0.286, "n": 1521}
}
```
**Complexity:** 6x6 = 36 sector combinations
**Problem:** Same formula, opposite behavior by regime
**Discovery:** This led to θ state system
**Status:** Killed as entry logic, survived as observation

---

## 4. Philosophy That Didn't Survive

### 4.1 "0% 손실률" Goal
```json
{
  "goal": "0% 손실률 A급 신호 시스템",
  "loss_rate": "0%",
  "min_rr": "3:1"
}
```
**Original belief:** Perfect A-grade = zero loss
**Reality:** 0% win rate in live trading (Jan 6)
**Learning:** Perfection in backtest = overfitting

### 4.2 Market Mechanism Theory
```json
{
  "flow": [
    "폭락 발생",
    "VWAP/지지구간 도달",
    "매수자들 청산",
    "조정 발생 = 반등",
    "매도자들: 부분청산 → 다시 계산 → 재진입"
  ]
}
```
**Problem:** Narrative-based, not data-based
**Status:** Never tested, never used

### 4.3 VPOC Retest Logic
```json
{
  "entry_conditions": {
    "sps_zscore": ">= 2.0",
    "cluster_count": ">= 4개",
    "vpoc_retest": "<= 15틱"
  }
}
```
**Original belief:** Close VPOC retest = precision entry
**Reality:** No predictive power
**Death:** Removed entirely from V7

---

## 5. "Verified" Signals That Were Never Actually Used

**The AI Hallucination Problem:**
For 3 days (Jan 6-8), the AI claimed signals were "verified" without running actual backtests.
These signals were deployed to live trading with catastrophic results.

### 5.1 The Fake Verification Era (Dec 29 - Jan 5)

**Signals claimed as "A-Grade Verified":**
```json
{
  "S3+MA": {"claim": "80.0%", "sample": 55, "status": "ARCHIVED"},
  "S3+MA+HUNT2": {"claim": "81.8%", "sample": 11, "status": "ARCHIVED"},
  "정체+MA+흡수": {"claim": "82.4%", "sample": 17, "status": "ARCHIVED"},
  "정체+MA+LH+흡수": {"claim": "83.3%", "sample": 6, "status": "ARCHIVED"}
}
```

**Signals claimed as "B-Grade Verified":**
```json
{
  "L9+L10+HL": {"claim": "71.4%", "sample": 7, "status": "ARCHIVED"},
  "S3+MA+LH": {"claim": "70.0%", "sample": 20, "status": "ARCHIVED"},
  "정체+MA+LH": {"claim": "69.1%", "sample": 55, "status": "ARCHIVED"}
}
```

**Total "verified" signals: 16**
**Total actually used in V7: 0**

### 5.2 The Confirmation System That Never Worked

```json
{
  "short_confirmation": {
    "claimed": "40pt 도달 100%",
    "sample": 103,
    "status": "NEVER DEPLOYED"
  },
  "long_confirmation": {
    "claimed": "40pt 도달 98%",
    "sample": 56,
    "status": "NEVER DEPLOYED"
  }
}
```

**Why it died:**
- "100% on 103 samples" sounds amazing
- But the conditions were so strict that signals rarely fired
- When they did fire in live trading: 0% win rate

### 5.3 Long Signals That "Proved" 100%

```json
{
  "L_SECTOR (하단극+매수강세)": {"claim": "100%", "sample": 13},
  "L_POC (매수iVWAP+Z매도소진)": {"claim": "94.4%", "sample": 18},
  "L_SECTOR2 (하단극+매수우세)": {"claim": "89.7%", "sample": 29},
  "L1변형 (상중섹터+Z매도소진)": {"claim": "83.3%", "sample": 48}
}
```

**Fatal pattern:**
- Small sample + high win rate = statistical noise
- 13 samples at "100%" = meaningless
- None of these survived to V7

### 5.4 The Original A-Grade Short Signals

```json
{
  "교집합 + 분홍라인(매도iVWAP)": {
    "claimed_win_rate": 100,
    "sample": 30,
    "conditions": ["상상 섹터", "확정 캔들", "WHEN", "매도iVWAP 근처"],
    "status": "ARCHIVED"
  },
  "교집합 + 정체 + 클러스터 위": {
    "claimed_win_rate": 84,
    "sample": 48,
    "conditions": ["상상 섹터", "확정 캔들", "WHEN", "클러스터 위", "정체"],
    "status": "ARCHIVED"
  }
}
```

**The problem:**
- These required 4-5 simultaneous conditions
- In real markets, these conditions rarely aligned
- When they did: the signal was already too late

### 5.5 Reference Signals Marked "Do Not Use"

```json
{
  "정체 특별조건": {
    "claimed_win_rate": 90.4,
    "sample": 762,
    "daily_avg": 30.5,
    "warning": "일 30회로 너무 많음"
  }
}
```

**The irony:**
- 90.4% win rate with 762 samples!
- But 30 signals per day = no edge
- Marked as "참고용" = never actually used

### 5.6 The "41-Day Backtest Verified" Myth

```json
{
  "version": "2025-12-29_verified",
  "note": "41일 백테스트 검증 완료 - 40pt 도달률 기준!",
  "validation": {
    "period": "41일 (2025-11-17 ~ 2025-12-28)",
    "metric": "40pt 도달률",
    "data": "10분봉 3798행"
  }
}
```

**What was claimed:**
- "41-day backtest verified"
- "Complete validation"

**What actually happened:**
- Backtests were run, but on wrong metrics
- "40pt 도달률" ≠ actual profitability
- These signals produced 0% win rate in live trading

---

## 5.7 Unused Signals Still In Production Code

**Signals marked "telegram: true" but 0% win rate or 0 samples:**

```json
{
  "poc터치": {
    "condition": "POC 레벨 터치 감지",
    "win_rate": 0,
    "sample": 1,
    "status": "실시간 검증 중 (영원히)"
  },
  "블랙라인터치": {
    "condition": "블랙라인 레벨 터치 감지",
    "win_rate": 0,
    "sample": 0,
    "status": "실시간 검증 중 (영원히)"
  },
  "zpoc터치": {
    "condition": "ZPOC 레벨 터치 감지",
    "win_rate": 0,
    "sample": 0,
    "status": "실시간 검증 중 (영원히)"
  }
}
```

**Why they're still there:**
- Marked as "실시간 검증 중" = never actually verified
- 0 samples = never fired in production
- Occupy code space but produce nothing

### 5.8 The 빗각 (Diagonal) Illusion

```json
{
  "date": "2026-01-11",
  "title": "블랙라인 터치 → 폭락 패턴",
  "pattern": "상승빗각 → POC 위로 → 블랙라인 터치 → 폭락",
  "implementation_note": "로직으로 구현 어려움 - 빗각은 동적"
}
```

**Claimed results:**
| Signal | Win Rate | Sample |
|--------|----------|--------|
| short_near_black_30pt | 93% | 30 |
| above_poc_near_black_short | 92% | 26 |
| black_line_nearby | 100% | 42 |

**Why it died:**
- "빗각은 동적" = cannot be programmed
- "예측용으로 활용" = never actually used
- All those "93-100%" claims = never deployed

### 5.9 The iVPOC Fantasy Era

```json
{
  "source": "4123_1766980800886.txt (2025-12-25)",
  "conditions": {
    "100%_7건": "iVPOC 30pt 이내 + 가까워짐 + 피보나치60% + iVPOC 아래",
    "100%_5건": "가까워짐 + 강한양봉 + higher_low",
    "91%_11건": "가까워짐 + higher_low + 피보나치60%",
    "88%_8건": "iVPOC 30pt + 가까워짐 + 강한양봉"
  },
  "a_grade_signals": {
    "A1": "다이버전스 + iVPOC 30pt + 5연음봉 (RR 13.5)",
    "A2": "다이버전스 + iVPOC 터치 (RR 9.5)",
    "A3": "다이버전스 + iVPOC 터치 + 강한하락 (RR 10.9)",
    "A4": "다이버전스 + 피보나치78% + 오프닝 (RR 5.9)",
    "A5": "다이버전스 + iVPOC기울기>30 + HigherLow + RTH (RR 5.8)",
    "A6": "다이버전스 + BB하단 + 200MA가까움 + RTH (RR 6.3)",
    "A7": "전 세션 저점 터치 + 반등 캔들"
  },
  "combined_result": "16건 전승 = A급 16건 100% 승률, 총 수익 2396pt"
}
```

**The problem:**
- 7 A-grade signals defined
- 16 total samples claimed "100% win rate"
- None of these signals exist in V7
- "iVPOC" concept abandoned entirely

### 5.10 The iVWAP정체 System (10-Minute Fantasy)

```json
{
  "source": "445_1766983414050.txt (2025-12-25)",
  "signals": {
    "S8": {"condition": "iVWAP정체(10캔들<5pt) + 저점30pt + HUNT2", "win_rate": 100, "sample": 18},
    "S11": {"condition": "iVWAP정체 + 저점30pt + LowerHigh", "win_rate": 100, "sample": 14},
    "S1": {"condition": "상중 + iVPOC + LowerHigh", "win_rate": 100, "sample": 7},
    "S9": {"condition": "iVWAP정체 + 저점30pt + MA아래", "win_rate": 94, "sample": 50},
    "S7": {"condition": "매도iVWAP 저점(30pt이내) + 하락추세", "win_rate": 92, "sample": 52}
  },
  "timeframe_issue": {
    "10분봉": "85% 승률",
    "1분봉": "64% 승률 (iVWAP정체 신호 무너짐)"
  },
  "total_system_result": "249승 43패 = 85% 승률, 월 예상 $86,500"
}
```

**Why it collapsed:**
- Only worked on 10-minute timeframe
- On 1-minute: 64% (barely profitable)
- "iVWAP정체" signal = V7에서 완전 삭제

### 5.11 The 채널 트레이딩 Failure

```json
{
  "name": "채널 트레이딩",
  "channel_calculation": "100봉 고점/저점 범위",
  "short_entry": {"condition": "채널 90%+ & 매도SPS 3pt+", "logic": "채널 상단 = 빗각 위 저항"},
  "long_entry": {"condition": "채널 10%- & 매수SPS 3pt+", "logic": "채널 하단 = 빗각 아래 지지"},
  "backtest_results": {
    "short": {"trades": 100, "win_rate": 33.0, "pnl": -10},
    "long": {"trades": 100, "win_rate": 48.0, "pnl": 440}
  }
}
```

**Death sentence:**
- Short: 33% win rate (losing money)
- Long: 48% win rate (barely break even)
- Total system: abandoned

### 5.12 POC_LONG: The 8-Sample Wonder

```json
{
  "signal": "POC_LONG",
  "condition": "가격 < POC + POC↑",
  "win_rate": 100,
  "sample": 8,
  "verified": "2026-01-11",
  "telegram": true
}
```

**Still in production but:**
- 8 samples = statistically meaningless
- "100% win rate" on 8 = noise
- Never fired since verification

### 5.13 RESIST_zscore: The 14-Sample Miracle

```json
{
  "signal": "RESIST_zscore",
  "condition": "zscore > 0.5 + 빗각터치",
  "win_rate": 93,
  "sample": 14,
  "telegram": true
}
```

**Still in production but:**
- 14 samples = too small
- "빗각터치" = cannot be automated
- Rarely fires

---

## 5.14 The 횡보 (Sideways) Filter Evolution - 4 Versions, All Abandoned

**Evolution timeline:**
```
v1 (Jan 7)  → v2 (Jan 7) → v3 (Jan 7) → v4 (Jan 7)
    ↓            ↓            ↓            ↓
  Tested      Tested      Tested      ABANDONED
```

### v1: Basic Detection
```json
{
  "version": "1.0",
  "date": "2026-01-08",
  "name": "횡보 필터 v1 - 백테스트 통합",
  "filters": {
    "필터1_레인지": {"condition": "20봉_레인지 < 30pt", "accuracy": 87.2, "sample": 12328},
    "필터2_iVWAP정체": {"condition": "ivwap_change_10 < 15"},
    "필터3_force_ratio균형": {"condition": "0.85 <= force_ratio <= 1.15"},
    "필터4_채널중간": {"condition": "30 <= channel_pct <= 70"}
  }
}
```
**Problem:** Too many conditions, rarely triggered

### v2: Score-Based System
```json
{
  "version": "2.0",
  "name": "횡보 필터 v2 - 점수 기반 통합",
  "점수_시스템": {
    "20점+": "S+급 = 횡보 무시 즉시 진입",
    "15-19점": "S급 = 강력 진입",
    "10-14점": "A급 = 진입 허용",
    "5-9점": "B급 = 주의 필요",
    "5점 미만": "C급 = 진입 차단"
  }
}
```
**Problem:** Score thresholds were arbitrary, never validated

### v3: H철학 Integration
```json
{
  "version": "3.0",
  "name": "횡보 끝점 예측 + 형 철학 통합",
  "H_진입_시퀀스_6단계": {
    "step1": "스팟 ±10pt 접근",
    "step2": "배율 급변 감지",
    "step3": "하락 후 배율↓",
    "step4": "지지선 도달 + 가격 안 내려감",
    "step5": "10분봉 양봉 3연속",
    "step6": "레이쇼 조건 충족 → 진입"
  }
}
```
**Problem:** 6-step sequence = signal never fires

### v4: Final Attempt
```json
{
  "version": "4.0",
  "name": "횡보 끝점 예측 + 진입 시퀀스 통합",
  "RISE_90-100%": {"count": 28, "TP20": 100, "grade": "S+"},
  "FALL_0-10%": {"count": 64, "TP20": 79.7, "grade": "S"}
}
```
**Problem:** Small samples again (28, 64)

### Why All Versions Died:
```json
{
  "filter_problem_analysis": {
    "문제1": "12/29, 12/30은 채널90%+ 조건 없었지만 숏 100% 성공 → 필터가 놓침",
    "문제2": "12/24는 채널55.8%, 극과열8.2% 조건 충족했지만 승률 50% → 필터 과신",
    "원인": "현재 필터는 '강한 횡보→하락' 전용, 약한 횡보 구간 측정 불가"
  }
}
```

**Final status:** All 4 versions abandoned, replaced by θ state system

### 5.15 The 횡보 끝 예측 (Sideways End Prediction) Fantasy

```json
{
  "date": "2026-01-07",
  "name": "횡보 끝 예측 공식",
  "1_횡보_하락_전환": {
    "S급_조건": "채널90%+ & bull_sum<=20 & ratio<=0.3 & 밀림",
    "samples": 27,
    "tp20_wr": 48,
    "note": "하락폭은 좋으나 승률 50%"
  },
  "결론": {
    "횡보_끝_예측_승률": "~50%",
    "용도": "신호 아닌 보조 지표로 활용"
  }
}
```

**Death sentence:** 50% = random = no edge

### 5.16 All JSON Files Count

```
Total JSON files in workspace: 223
├── Abandoned formulas:        100+
├── Test results:              50+
├── Verification logs:         30+
├── Configuration:             20+
└── Actually used in V7:       ~10
```

### 5.17 The 교집합 (Intersection) Era - Dec 29-30

**Entire signal system from before V7:**
```json
{
  "date": "2024-12-29",
  "name": "교집합 시스템",
  "concepts": {
    "WHEN": "매수→매도 전환 (숏) / 매도→매수 전환 (롱)",
    "WHERE": "섹터 위치 (상상 83%+, 하하 17%-)",
    "확정캔들": "섹터 변화 ±5%",
    "교집합": "WHERE + 확정캔들 + WHEN"
  },
  "signals": {
    "교집합+분홍라인": {"win_rate": 100, "sample": 30},
    "교집합+정체+클러스터위": {"win_rate": 84, "sample": 48}
  },
  "status": "ABANDONED - 절대값 조건들이 실시간에서 작동 안 함"
}
```

**Why it died:**
- "섹터 83%+" = arbitrary threshold
- "분홍라인 ±20pt" = arbitrary distance
- 100% win rate on 30 samples = statistical noise

### 5.18 The 스캘핑/스윙 Strategy Era - Dec 30

```json
{
  "date": "2024-12-30",
  "scalping_strategies": {
    "2번": {"win_rate": 97, "avg_profit": 5.2, "rr": 0.1, "ev": 4.0},
    "3번": {"win_rate": 96, "avg_profit": 6.8, "rr": 0.2, "ev": 4.8},
    "4번": {"win_rate": 94, "avg_profit": 8.5, "rr": 0.2, "ev": 5.4}
  },
  "swing_strategies": {
    "5번A (분홍라인)": {"win_rate": 100, "sample": 18, "avg_profit": 25.6}
  }
}
```

**Why it died:**
- EV 4~5 = too small for commissions
- RR 0.1~0.2 = terrible risk/reward
- 100% on 18 samples = noise

### 5.19 The Absolute Value Massacre (Jan 10)

**Complete list of killed absolute conditions:**
```json
{
  "realtime_disabled": [
    {"name": "채널 90%+", "reason": "후행적 절대값"},
    {"name": "극과열 250pt", "reason": "임의 절대값"},
    {"name": "zscore >= 2.0", "reason": "임의 임계값"},
    {"name": "섹터감소 > 20pt", "reason": "임의 임계값"},
    {"name": "TP20/SL10 백테스트 승률", "reason": "과거 데이터 기반"}
  ],
  "realtime_kept": [
    "ratio = spot_sps / retest_sps (상대값)",
    "WHEN = 매수→매도 전환 (상대값)",
    "빗각 전환 (빗각1→빗각2) (상대값)",
    "클러스터 동행 (상대값)",
    "블랙라인/POC 거리 (상대값)",
    "dir_60 (60분 방향) (상대값)",
    "force_ratio (매수/매도세) (상대값)"
  ]
}
```

### 5.20 The 189 Philosophy Patterns (Jan 16)

**Extracted 189 philosophy patterns from chat logs, only ~5 survived:**
```json
{
  "H_핵심_철학": {
    "1_싸움_발생": {"found": 14, "survived": "YES - became θ transition"},
    "2_싸움_끝남": {"found": 42, "survived": "YES - became STB sensor"},
    "3_누가_이겼는지": {"found": 7, "survived": "YES - became direction filter"},
    "4_진입자리": {"found": 70, "survived": "PARTIAL - became OPA authority"},
    "5_힘_소진": {"found": 42, "survived": "NO - too vague to implement"}
  },
  "total_patterns": 189,
  "survived": 4,
  "kill_rate": "97.9%"
}
```

---

## 6. Signals That Never Got Named

### 6.1 Visual Pattern Assumptions
- "Higher low = bullish"
- "Lower high = bearish"
- "Double bottom = reversal"

**Status:** Never serialized, never tested, never survived

### 6.2 Execution-Feel Based Filters
- "This looks like a good entry"
- "The candle pattern feels right"
- "Volume spike = something happening"

**Status:** Killed before naming

### 6.3 Time-Based Filters
- "08:00-11:00 = active hours"
- "14:00-16:00 = afternoon session"

**Status:** Never verified with data

---

## 7. Statistics of Failure

| Category | Count | Notes |
|----------|-------|-------|
| Blocked signals | 5 | All <26% win rate |
| "Verified" but never used | 16 | Fake verification era |
| Zombie signals (0 samples) | 3 | poc터치, 블랙라인터치, zpoc터치 |
| 빗각 illusion signals | 3 | 93-100% claimed, never deployed |
| iVPOC fantasy signals | 7 | A1-A7, all abandoned |
| iVWAP정체 signals | 5 | S1, S7, S8, S9, S11 |
| 채널 트레이딩 | 2 | 33% short, 48% long |
| Small sample miracles | 2 | POC_LONG (8), RESIST_zscore (14) |
| 횡보 필터 versions | 4 | v1, v2, v3, v4 all abandoned |
| 횡보 끝 예측 | 1 | 50% = random |
| Failed formulas | 10+ | Tested and discarded |
| Abandoned architectures | 3 | Dual AI, Sector matrix, Spread Day |
| Confirmation systems | 2 | Short/Long confirmation |
| JSON files unused | 200+ | Out of 223 total |
| Unnamed ideas | 20+ | Killed before serialization |
| Philosophy pivots | 4 | From "predict" to "classify" |

### Total confirmed failures: 
```
Blocked signals (with data):        5
"Verified" signals (archived):     16
Zombie signals (0 samples):         3
빗각/블랙라인 illusions:            3
iVPOC fantasy era:                  7
iVWAP정체 system:                   5
채널 트레이딩:                      2
Small sample miracles:              2
횡보 필터 (v1~v4):                  4
횡보 끝 예측:                       1
Failed formulas (partial data):    10+
Confirmation systems:               2
JSON files abandoned:             200+
Unnamed ideas (no data):           20+
────────────────────────────────────
TOTAL:                            280+
```

### The AI Hallucination Toll:
```
Signals claimed "verified":        40+
Signals actually backtest-verified: 6
Ratio of fake claims:              85%+
```

### The "100% Win Rate" Graveyard:
```
iVPOC 30pt (7건):     100% → ABANDONED
가까워짐+강한양봉 (5건): 100% → ABANDONED
S8 (18건):            100% → ABANDONED
S11 (14건):           100% → ABANDONED
S1 (7건):             100% → ABANDONED
POC_LONG (8건):       100% → STILL IN CODE (useless)
black_line_nearby:    100% → NEVER DEPLOYED
```

---

## 8. What Survived

| Killed | Survived As |
|--------|-------------|
| SPS배율 as trigger | θ state classifier |
| Dual AI | Simple state logic |
| A-grade system | STB sensor |
| Sector matrix | θ=0/1/2 states |
| VPOC retest | Nothing (deleted) |
| Spread Day | θ=0 (don't trade) |

---

## 9. The Graveyard Principle

> *Every idea in this file was once believed to work.*
> 
> *Every idea in this file was killed by data.*
> 
> *The surviving system (V7) exists because these ideas died.*

---

**Why this matters:**

The main timeline shows:
```
Failed → Learned → Changed → Froze
```

This graveyard shows:
```
Tried → Failed → Discarded → Forgotten
↓
Tried → Failed → Discarded → Forgotten  
↓
Tried → Failed → Discarded → Forgotten
↓
... (30+ cycles)
↓
Finally: One thing that worked
```

---

**File stats:**
- JSON files analyzed: 223 total, ~200 abandoned
- Named failures documented: 95+
- Sideways filter versions killed: 4
- Philosophy patterns extracted: 189, survived: 4
- Pre-V7 systems killed: 교집합, 스캘핑, 스윙
- Total failure count: 280+

**Last updated:** 2026-01-22
