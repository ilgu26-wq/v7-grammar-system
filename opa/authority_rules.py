"""
OPA Authority Rules - V7 Constitution Implementation

4계층 권한 검사:
- Layer 0: Identity (신호 자격)
- Layer 1: State Authority (상태 인증) ← 90% 차단
- Layer 2: Temporal Authority (시간 권한)
- Layer 3: Execution Authority (실행 환경)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict


class Authority(Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class DenyReason(Enum):
    UNDEFINED_SIGNAL = "undefined_signal"
    STATE_NOT_CERTIFIED = "state_not_certified"
    CONSECUTIVE_LOSS_ZONE = "consecutive_loss_same_zone"
    EXECUTION_ENVIRONMENT = "execution_environment"
    NONE = "none"


@dataclass
class AuthorityResult:
    authority: Authority
    reason: DenyReason
    layer_failed: int
    details: Optional[str] = None


# 정의된 신호 목록 (Layer 0에서 사용)
DEFINED_SIGNALS = {
    "숏-정체",
    "숏 교집합 스팟",
    "STB숏",
    "STB롱", 
    "SCALP_A",
    "HUNT_1",
    "RESIST_zscore",
    "POC_LONG",
}

TIER1_SIGNALS = {
    "숏-정체",
    "숏 교집합 스팟",
}


def check_layer0_identity(signal_name: str) -> AuthorityResult:
    """
    Layer 0: Identity - 신호가 정의되어 있는가?
    """
    if signal_name not in DEFINED_SIGNALS:
        return AuthorityResult(
            authority=Authority.DENY,
            reason=DenyReason.UNDEFINED_SIGNAL,
            layer_failed=0,
            details=f"Signal '{signal_name}' not in defined signals"
        )
    
    return AuthorityResult(
        authority=Authority.ALLOW,
        reason=DenyReason.NONE,
        layer_failed=-1
    )


def check_layer1_state_authority(state_certified: bool, theta: int, theta_threshold: int = 1) -> AuthorityResult:
    """
    Layer 1: State Authority - 상태가 인증되었는가?
    
    핵심: θ >= threshold → 인증
    이 계층에서 90%의 잘못된 진입이 차단된다.
    """
    if not state_certified or theta < theta_threshold:
        return AuthorityResult(
            authority=Authority.DENY,
            reason=DenyReason.STATE_NOT_CERTIFIED,
            layer_failed=1,
            details=f"theta={theta} < threshold={theta_threshold}"
        )
    
    return AuthorityResult(
        authority=Authority.ALLOW,
        reason=DenyReason.NONE,
        layer_failed=-1
    )


def check_layer2_temporal_authority(consecutive_loss_same_zone: int) -> AuthorityResult:
    """
    Layer 2: Temporal Authority - 권한 박탈 조건
    
    규칙: 같은 존에서 연속 2회 손실 → 권한 박탈
    
    ⚠️ 중요: 이 값은 zone 기준으로만 누적!
    - 동일 STATE
    - 동일 방향 (direction)
    - 동일 구간 (zone_id)
    
    loss_key = (state, direction, zone_id)
    """
    if consecutive_loss_same_zone >= 2:
        return AuthorityResult(
            authority=Authority.DENY,
            reason=DenyReason.CONSECUTIVE_LOSS_ZONE,
            layer_failed=2,
            details=f"consecutive_loss_same_zone={consecutive_loss_same_zone}"
        )
    
    return AuthorityResult(
        authority=Authority.ALLOW,
        reason=DenyReason.NONE,
        layer_failed=-1
    )


def check_layer3_execution(slippage: float = 0.0, spread: float = 0.0) -> AuthorityResult:
    """
    Layer 3: Execution Authority - 실행 환경 검사
    
    규칙: slippage > 3pt OR spread > 2pt → DENY
    
    ⚠️ 실시간에서는 보수 추정치 사용:
    - spread = (ask - bid) from latest tick
    - slippage = max(spread * 0.5, 0.5)
    
    정확한 체결 슬리피지 불가 → 과대추정이 안전
    """
    if slippage > 3.0 or spread > 2.0:
        return AuthorityResult(
            authority=Authority.DENY,
            reason=DenyReason.EXECUTION_ENVIRONMENT,
            layer_failed=3,
            details=f"slippage={slippage}, spread={spread}"
        )
    
    return AuthorityResult(
        authority=Authority.ALLOW,
        reason=DenyReason.NONE,
        layer_failed=-1
    )


def estimate_slippage(spread: float, min_slippage: float = 0.5) -> float:
    """보수적 슬리피지 추정"""
    return max(spread * 0.5, min_slippage)
