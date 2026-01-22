"""
Authority Engine
================

OPA 권한 판정 엔진

계층:
- Layer 0: Identity (신호 검증)
- Layer 1: State Authority (θ 검증) ← 핵심
- Layer 2: Temporal Authority (시간 권한)
- Layer 3: Execution Authority (실행 환경)
"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum

from .policy_v74 import (
    is_allowed, get_size, can_retry, can_trail,
    BLACKLIST_SIGNALS, TIER1_SIGNALS
)


class Authority(Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


@dataclass
class AuthorityRequest:
    """권한 요청"""
    signal_name: str
    theta: int
    is_retry: bool = False
    impulse_count: int = 0
    recovery_time: float = 0
    consecutive_loss: int = 0


@dataclass
class AuthorityResponse:
    """권한 응답"""
    authority: Authority
    theta: int
    size: str
    can_retry: bool
    can_trail: bool
    reason: str = ""
    layer_failed: int = -1


class AuthorityEngine:
    """OPA 권한 엔진"""
    
    def __init__(self):
        self.stats = {
            "allow": 0,
            "deny": 0,
            "deny_by_layer": {0: 0, 1: 0, 2: 0, 3: 0},
        }
    
    def evaluate(self, request: AuthorityRequest) -> AuthorityResponse:
        """권한 평가"""
        
        if request.signal_name in BLACKLIST_SIGNALS:
            self.stats["deny"] += 1
            self.stats["deny_by_layer"][0] += 1
            return AuthorityResponse(
                authority=Authority.DENY,
                theta=request.theta,
                size="NONE",
                can_retry=False,
                can_trail=False,
                reason=f"Blacklisted signal: {request.signal_name}",
                layer_failed=0,
            )
        
        if not is_allowed(request.theta):
            self.stats["deny"] += 1
            self.stats["deny_by_layer"][1] += 1
            return AuthorityResponse(
                authority=Authority.DENY,
                theta=request.theta,
                size="NONE",
                can_retry=False,
                can_trail=False,
                reason=f"θ={request.theta}: State not certified",
                layer_failed=1,
            )
        
        if request.consecutive_loss >= 2:
            self.stats["deny"] += 1
            self.stats["deny_by_layer"][2] += 1
            return AuthorityResponse(
                authority=Authority.DENY,
                theta=request.theta,
                size="NONE",
                can_retry=False,
                can_trail=False,
                reason="State collapse: 2+ consecutive losses",
                layer_failed=2,
            )
        
        if request.is_retry:
            if not can_retry(request.theta, request.impulse_count, request.recovery_time):
                self.stats["deny"] += 1
                self.stats["deny_by_layer"][3] += 1
                return AuthorityResponse(
                    authority=Authority.DENY,
                    theta=request.theta,
                    size="NONE",
                    can_retry=False,
                    can_trail=False,
                    reason=f"Retry conditions not met at θ={request.theta}",
                    layer_failed=3,
                )
        
        self.stats["allow"] += 1
        
        return AuthorityResponse(
            authority=Authority.ALLOW,
            theta=request.theta,
            size=get_size(request.theta),
            can_retry=can_retry(request.theta, request.impulse_count, request.recovery_time),
            can_trail=can_trail(request.theta),
        )
    
    def get_stats(self) -> dict:
        """통계 반환"""
        total = self.stats["allow"] + self.stats["deny"]
        return {
            **self.stats,
            "total": total,
            "allow_rate": self.stats["allow"] / total if total > 0 else 0,
        }
