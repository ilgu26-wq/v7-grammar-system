# OPA v7.4 Policy Document

## 헌법 (DO NOT MODIFY)

```
θ = 0 → DENY
θ = 1 → ALLOW (SMALL, No Retry, No Trail)
θ = 2 → ALLOW (SMALL/MEDIUM, Retry 조건부, No Trail)
θ ≥ 3 → ALLOW (LARGE, Retry, Trail Optional)
```

## Size 정의

| Size | Multiplier |
|------|------------|
| SMALL | 1.0x |
| MEDIUM | 2.0x |
| LARGE | 4.0x |

## Retry 조건 (θ=2 only)

```
impulse_count > 2 AND recovery_time < 4
```

## 금지 신호 (Blacklist)

- 매수스팟
- 매도스팟
- 빗각버팀
- 저점상승
- 횡보예상_v1

## Tier1 신호

- STB숏
- STB롱
- RESIST_zscore_0.5
- RESIST_zscore_1.0
- RESIST_zscore_1.5

---

**확정일: 2026-01-22**
**버전: v7.4**

이 문서는 수정 금지. 실험 결과에 따른 변경은 v7.5로 새 버전 생성.
