"""
OPA Engine - Operational Policy Architecture

V7 헌법을 실행체로 변환한 권한 통제 계층

OPA는 판단하지 않는다.
OPA는 허가/거부만 한다.
"""

from dataclasses import dataclass
from typing import Dict, Optional, List
from datetime import datetime

from .authority_rules import (
    Authority, DenyReason, AuthorityResult,
    check_layer0_identity,
    check_layer1_state_authority,
    check_layer2_temporal_authority,
    check_layer3_execution,
    TIER1_SIGNALS
)
from .mode_switch import ModeController, OperationMode, ModeState


@dataclass
class OPARequest:
    """OPA 권한 요청"""
    signal_name: str
    state_certified: bool
    theta: int
    consecutive_loss_same_zone: int = 0
    slippage: float = 0.0
    spread: float = 0.0
    timestamp: Optional[datetime] = None


@dataclass 
class OPAResponse:
    """OPA 권한 응답"""
    authority: Authority
    mode: OperationMode
    reason: DenyReason
    layer_failed: int
    theta_threshold_used: int
    is_tier1: bool
    details: Optional[str] = None


class OPAEngine:
    """
    OPA 엔진 - 4계층 권한 검사 실행
    
    Layer 0: Identity (누가 제안했는가)
    Layer 1: State Authority (상태가 인증됐는가) ← 핵심
    Layer 2: Temporal Authority (시간 권한)
    Layer 3: Execution Authority (실행 환경)
    """
    
    def __init__(self, mode: OperationMode = OperationMode.NORMAL):
        self.mode_controller = ModeController()
        if mode == OperationMode.CONSERVATIVE:
            self.mode_controller.force_conservative()
        
        self.allow_count = 0
        self.deny_count = 0
        self.deny_by_layer: Dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}
    
    def check_authority(self, request: OPARequest) -> OPAResponse:
        """
        4계층 권한 검사 실행
        
        순서: Layer 0 → 1 → 2 → 3
        어느 계층에서든 DENY면 즉시 반환
        """
        mode_state = self.mode_controller.get_mode_state()
        is_tier1 = request.signal_name in TIER1_SIGNALS
        
        # CONSERVATIVE 모드에서 Tier1만 허용
        if mode_state.tier1_only and not is_tier1:
            self.deny_count += 1
            self.deny_by_layer[0] += 1
            return OPAResponse(
                authority=Authority.DENY,
                mode=mode_state.mode,
                reason=DenyReason.UNDEFINED_SIGNAL,
                layer_failed=0,
                theta_threshold_used=mode_state.theta_threshold,
                is_tier1=is_tier1,
                details="Conservative mode: Tier1 only"
            )
        
        # Layer 0: Identity
        result = check_layer0_identity(request.signal_name)
        if result.authority == Authority.DENY:
            self.deny_count += 1
            self.deny_by_layer[0] += 1
            return OPAResponse(
                authority=Authority.DENY,
                mode=mode_state.mode,
                reason=result.reason,
                layer_failed=0,
                theta_threshold_used=mode_state.theta_threshold,
                is_tier1=is_tier1,
                details=result.details
            )
        
        # Layer 1: State Authority (핵심!)
        result = check_layer1_state_authority(
            request.state_certified, 
            request.theta,
            mode_state.theta_threshold
        )
        if result.authority == Authority.DENY:
            self.deny_count += 1
            self.deny_by_layer[1] += 1
            return OPAResponse(
                authority=Authority.DENY,
                mode=mode_state.mode,
                reason=result.reason,
                layer_failed=1,
                theta_threshold_used=mode_state.theta_threshold,
                is_tier1=is_tier1,
                details=result.details
            )
        
        # Layer 2: Temporal Authority
        result = check_layer2_temporal_authority(request.consecutive_loss_same_zone)
        if result.authority == Authority.DENY:
            self.deny_count += 1
            self.deny_by_layer[2] += 1
            return OPAResponse(
                authority=Authority.DENY,
                mode=mode_state.mode,
                reason=result.reason,
                layer_failed=2,
                theta_threshold_used=mode_state.theta_threshold,
                is_tier1=is_tier1,
                details=result.details
            )
        
        # Layer 3: Execution Authority
        result = check_layer3_execution(request.slippage, request.spread)
        if result.authority == Authority.DENY:
            self.deny_count += 1
            self.deny_by_layer[3] += 1
            return OPAResponse(
                authority=Authority.DENY,
                mode=mode_state.mode,
                reason=result.reason,
                layer_failed=3,
                theta_threshold_used=mode_state.theta_threshold,
                is_tier1=is_tier1,
                details=result.details
            )
        
        # 모든 계층 통과 → ALLOW
        self.allow_count += 1
        return OPAResponse(
            authority=Authority.ALLOW,
            mode=mode_state.mode,
            reason=DenyReason.NONE,
            layer_failed=-1,
            theta_threshold_used=mode_state.theta_threshold,
            is_tier1=is_tier1
        )
    
    def get_stats(self) -> Dict:
        """통계 반환"""
        total = self.allow_count + self.deny_count
        return {
            "total_requests": total,
            "allowed": self.allow_count,
            "denied": self.deny_count,
            "allow_rate": self.allow_count / total if total > 0 else 0,
            "deny_by_layer": dict(self.deny_by_layer),
            "mode": self.mode_controller.current_mode.value
        }
    
    def reset_stats(self):
        """통계 리셋"""
        self.allow_count = 0
        self.deny_count = 0
        self.deny_by_layer = {0: 0, 1: 0, 2: 0, 3: 0}
