"""
V7 Grammar System - Main Pipeline
==================================

파이프라인 연결만 담당

main.py에서:
- θ 계산 ❌
- Size 판단 ❌
- Retry 판단 ❌
→ 전부 OPA 내부에서만
"""

import sys
sys.path.insert(0, '/home/runner/workspace/v7-grammar-system')

from core.theta_state import ThetaEngine
from core.stb_sensor import is_stb_signal, parse_stb_signal
from core.transition_sensor import check_transition
from opa.authority_engine import AuthorityEngine, AuthorityRequest, Authority
from opa.size_manager import get_position_size, AccountConfig
from opa.retry_manager import RetryManager
from opa.state_logger import StateLogger
from execution.entry_gate import EntryGate
from execution.exit_rules import ExitRules


class V7Pipeline:
    """V7 시스템 파이프라인"""
    
    def __init__(self, account: AccountConfig = None):
        self.theta_engine = ThetaEngine()
        self.opa_engine = AuthorityEngine()
        self.retry_manager = RetryManager()
        self.state_logger = StateLogger()
        self.entry_gate = EntryGate(account)
        self.exit_rules = ExitRules()
        self.account = account or AccountConfig()
    
    def on_signal(self, signal_name: str, direction: str, 
                  mfe: float, bars: int, impulse_count: int = 0,
                  recovery_time: float = 0, is_retry: bool = False,
                  consecutive_loss: int = 0) -> dict:
        """신호 처리"""
        
        theta_state = self.theta_engine.compute(
            mfe=mfe,
            bars=bars,
            impulse_count=impulse_count,
            recovery_time=recovery_time,
        )
        
        request = AuthorityRequest(
            signal_name=signal_name,
            theta=theta_state.value,
            is_retry=is_retry,
            impulse_count=impulse_count,
            recovery_time=recovery_time,
            consecutive_loss=consecutive_loss,
        )
        
        decision = self.opa_engine.evaluate(request)
        
        if decision.authority == Authority.DENY:
            return {
                "action": "DENY",
                "theta": theta_state.value,
                "reason": decision.reason,
            }
        
        size = get_position_size(theta_state.value, self.account)
        
        self.state_logger.start_trade(signal_name)
        self.state_logger.log_state(
            bar=bars,
            theta=theta_state.value,
            event="ENTRY",
            sensors={"impulse": impulse_count, "recovery": recovery_time}
        )
        
        return {
            "action": "ALLOW",
            "theta": theta_state.value,
            "size": size,
            "size_name": decision.size,
            "can_retry": decision.can_retry,
            "can_trail": decision.can_trail,
        }
    
    def get_stats(self) -> dict:
        """통계 반환"""
        return {
            "opa": self.opa_engine.get_stats(),
            "state_logger": self.state_logger.get_summary(),
        }


def run_pipeline_test():
    """파이프라인 테스트"""
    print("=" * 70)
    print("V7 Pipeline Test")
    print("=" * 70)
    
    pipeline = V7Pipeline()
    
    test_cases = [
        {"signal_name": "STB숏", "direction": "SHORT", "mfe": 0, "bars": 1, "impulse_count": 1, "recovery_time": 6},
        {"signal_name": "STB숏", "direction": "SHORT", "mfe": 5, "bars": 5, "impulse_count": 2, "recovery_time": 5},
        {"signal_name": "STB숏", "direction": "SHORT", "mfe": 12, "bars": 10, "impulse_count": 3, "recovery_time": 3},
        {"signal_name": "STB숏", "direction": "SHORT", "mfe": 20, "bars": 15, "impulse_count": 4, "recovery_time": 2},
        {"signal_name": "매수스팟", "direction": "LONG", "mfe": 20, "bars": 15, "impulse_count": 4, "recovery_time": 2},
    ]
    
    print(f"\n| Signal | θ | Action | Size | Reason |")
    print(f"|--------|---|--------|------|--------|")
    
    for tc in test_cases:
        result = pipeline.on_signal(**tc)
        size = result.get("size_name", "-")
        reason = result.get("reason", "-")[:20]
        print(f"| {tc['signal_name'][:10]} | {result['theta']} | {result['action']} | {size} | {reason} |")
    
    print(f"\n📊 통계: {pipeline.get_stats()}")
    
    return pipeline.get_stats()


if __name__ == "__main__":
    run_pipeline_test()
