"""
Entry Gate
==========

OPA 통과 후 진입 실행

main.py에서 호출:
- OPA 권한 확인
- Size 결정
- 진입 실행
"""

from dataclasses import dataclass
from typing import Optional

import sys
sys.path.insert(0, '/home/runner/workspace/v7-grammar-system')

from opa.authority_engine import AuthorityEngine, AuthorityRequest, Authority
from opa.size_manager import get_position_size, AccountConfig
from opa.state_logger import StateLogger


@dataclass
class EntryOrder:
    """진입 주문"""
    signal: str
    direction: str
    size: float
    theta: int
    tp: float
    sl: float


class EntryGate:
    """진입 게이트"""
    
    def __init__(self, account: AccountConfig = None):
        self.authority_engine = AuthorityEngine()
        self.state_logger = StateLogger()
        self.account = account or AccountConfig()
    
    def evaluate_entry(self, signal: str, theta: int, direction: str,
                       is_retry: bool = False, impulse_count: int = 0,
                       recovery_time: float = 0, consecutive_loss: int = 0) -> Optional[EntryOrder]:
        """진입 평가"""
        
        request = AuthorityRequest(
            signal_name=signal,
            theta=theta,
            is_retry=is_retry,
            impulse_count=impulse_count,
            recovery_time=recovery_time,
            consecutive_loss=consecutive_loss,
        )
        
        response = self.authority_engine.evaluate(request)
        
        if response.authority == Authority.DENY:
            return None
        
        size = get_position_size(theta, self.account)
        
        from opa.policy_v74 import get_policy
        policy = get_policy(theta)
        
        return EntryOrder(
            signal=signal,
            direction=direction,
            size=size,
            theta=theta,
            tp=policy.get("tp", 20),
            sl=policy.get("sl", 12),
        )
    
    def execute(self, order: EntryOrder):
        """주문 실행 (시뮬레이션)"""
        self.state_logger.start_trade(order.signal)
        self.state_logger.log_entry(bar=0, theta=order.theta)
        
        return {
            "status": "EXECUTED",
            "order": order,
        }
