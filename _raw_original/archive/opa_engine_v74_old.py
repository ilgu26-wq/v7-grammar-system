"""
OPA Engine v7.4 - Operational Policy Architecture

v7.3 → v7.4 변경:
- θ=2를 운용 분기점으로 승격
- Size 정책 추가 (SMALL, MEDIUM, LARGE)
- Retry 정책 추가

철학 불변:
- θ 구조 불변
- STB 역할 불변
- OPA 권한 개념 불변
"""

from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum


class Authority(Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class Size(Enum):
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"


class ExitPolicy(Enum):
    FIXED_TP = "FIXED_TP"
    EXTENSION = "EXTENSION"


@dataclass
class PolicyConfig:
    """θ별 실행 정책"""
    size: Size
    exit_policy: ExitPolicy
    allow_retry: bool
    allow_trailing: bool
    tp: float
    sl: float


THETA_POLICIES = {
    0: None,
    1: PolicyConfig(
        size=Size.SMALL,
        exit_policy=ExitPolicy.FIXED_TP,
        allow_retry=False,
        allow_trailing=False,
        tp=20,
        sl=12,
    ),
    2: PolicyConfig(
        size=Size.SMALL,
        exit_policy=ExitPolicy.FIXED_TP,
        allow_retry=True,
        allow_trailing=False,
        tp=20,
        sl=12,
    ),
    3: PolicyConfig(
        size=Size.LARGE,
        exit_policy=ExitPolicy.EXTENSION,
        allow_retry=True,
        allow_trailing=True,
        tp=20,
        sl=12,
    ),
}


@dataclass
class OPARequest:
    signal_name: str
    theta: int
    zone: str = ""
    is_retry: bool = False
    consecutive_loss_same_zone: int = 0


@dataclass
class OPAResponse:
    authority: Authority
    theta: int
    policy: Optional[PolicyConfig]
    reason: str = ""


class OPAEngineV74:
    """
    OPA v7.4 엔진
    
    변경점:
    - θ=2 정책 분리
    - Size/Retry 정책 추가
    - θ 계산 로직 불변
    """
    
    def __init__(self):
        self.stats = {
            "allow": 0,
            "deny": 0,
            "by_theta": {0: 0, 1: 0, 2: 0, 3: 0},
            "retries": 0,
        }
    
    def check_authority(self, request: OPARequest) -> OPAResponse:
        if request.theta == 0:
            self.stats["deny"] += 1
            return OPAResponse(
                authority=Authority.DENY,
                theta=request.theta,
                policy=None,
                reason="θ=0: No state certified"
            )
        
        if request.consecutive_loss_same_zone >= 2:
            self.stats["deny"] += 1
            return OPAResponse(
                authority=Authority.DENY,
                theta=request.theta,
                policy=None,
                reason="State collapse detected (2+ losses in same zone)"
            )
        
        policy = THETA_POLICIES.get(request.theta, THETA_POLICIES[3])
        
        if request.is_retry and not policy.allow_retry:
            self.stats["deny"] += 1
            return OPAResponse(
                authority=Authority.DENY,
                theta=request.theta,
                policy=None,
                reason=f"Retry not allowed at θ={request.theta}"
            )
        
        if request.is_retry:
            self.stats["retries"] += 1
        
        self.stats["allow"] += 1
        self.stats["by_theta"][min(request.theta, 3)] += 1
        
        return OPAResponse(
            authority=Authority.ALLOW,
            theta=request.theta,
            policy=policy
        )
    
    def get_stats(self) -> Dict:
        total = self.stats["allow"] + self.stats["deny"]
        return {
            **self.stats,
            "total": total,
            "allow_rate": self.stats["allow"] / total if total > 0 else 0,
        }


def run_v74_tests():
    """OPA v7.4 테스트"""
    print("=" * 70)
    print("OPA v7.4 테스트")
    print("=" * 70)
    
    engine = OPAEngineV74()
    
    test_cases = [
        OPARequest(signal_name="STB숏", theta=0),
        OPARequest(signal_name="STB숏", theta=1),
        OPARequest(signal_name="STB숏", theta=2),
        OPARequest(signal_name="STB숏", theta=2, is_retry=True),
        OPARequest(signal_name="STB숏", theta=3),
        OPARequest(signal_name="STB숏", theta=1, is_retry=True),
        OPARequest(signal_name="STB숏", theta=1, consecutive_loss_same_zone=2),
    ]
    
    print(f"\n📊 테스트 케이스:")
    print(f"\n| θ | Retry | Loss | Authority | Size | Trailing | Reason |")
    print(f"|---|-------|------|-----------|------|----------|--------|")
    
    for req in test_cases:
        resp = engine.check_authority(req)
        size = resp.policy.size.value if resp.policy else "-"
        trail = "✅" if resp.policy and resp.policy.allow_trailing else "❌"
        reason = resp.reason[:20] if resp.reason else "-"
        print(f"| {req.theta} | {'✅' if req.is_retry else '❌'} | {req.consecutive_loss_same_zone} | {resp.authority.value} | {size} | {trail} | {reason} |")
    
    print(f"\n📊 통계: {engine.get_stats()}")
    
    print("\n" + "=" * 70)
    print("📜 OPA v7.4 정책 구조")
    print("=" * 70)
    
    print("""
┌─────────────────────────────────────────────────────────────────┐
│ θ = 0 → DENY                                                    │
│                                                                 │
│ θ = 1 → ALLOW                                                   │
│         Size = SMALL                                            │
│         Exit = Fixed TP                                         │
│         Retry = ❌                                               │
│         Trailing = ❌                                            │
│                                                                 │
│ θ = 2 → ALLOW                                                   │
│         Size = SMALL (or MEDIUM)                                │
│         Exit = Fixed TP                                         │
│         Retry = ✅ (조건부)                                      │
│         Trailing = ❌                                            │
│                                                                 │
│ θ ≥ 3 → ALLOW                                                   │
│         Size = LARGE                                            │
│         Exit = Fixed TP or Extension                            │
│         Retry = ✅                                               │
│         Trailing = ✅ (옵션)                                     │
└─────────────────────────────────────────────────────────────────┘
""")
    
    return engine.get_stats()


if __name__ == "__main__":
    run_v74_tests()
