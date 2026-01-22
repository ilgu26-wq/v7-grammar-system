"""
OPA Mode Switch - 운용 모드 전환

NORMAL MODE: θ=1, 모든 Tier 허용
CONSERVATIVE MODE: θ≥3, Tier1 only

Emergency Clause: fast_collapse 급증 시 자동 전환
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class OperationMode(Enum):
    NORMAL = "NORMAL"           # θ=1, 전체 커버리지
    CONSERVATIVE = "CONSERVATIVE"  # θ≥3, Tier1 only


@dataclass
class ModeState:
    mode: OperationMode
    theta_threshold: int
    tier1_only: bool
    reason: Optional[str] = None


class ModeController:
    """
    운용 모드 컨트롤러
    
    Emergency Clause:
    - fast_collapse 5건/일 초과 → CONSERVATIVE 전환
    - ordering_violation 발생 → PAUSE (별도 처리)
    """
    
    FAST_COLLAPSE_THRESHOLD = 5  # 일일 한도
    
    def __init__(self):
        self.current_mode = OperationMode.NORMAL
        self.fast_collapse_count = 0
        self.daily_trades = 0
    
    def get_mode_state(self) -> ModeState:
        """현재 모드 상태 반환"""
        if self.current_mode == OperationMode.NORMAL:
            return ModeState(
                mode=OperationMode.NORMAL,
                theta_threshold=1,
                tier1_only=False,
                reason="Normal operation"
            )
        else:
            return ModeState(
                mode=OperationMode.CONSERVATIVE,
                theta_threshold=3,
                tier1_only=True,
                reason="Emergency mode active"
            )
    
    def record_fast_collapse(self):
        """빠른 붕괴 기록"""
        self.fast_collapse_count += 1
        self._check_emergency()
    
    def record_trade(self):
        """거래 기록"""
        self.daily_trades += 1
    
    def reset_daily(self):
        """일일 리셋"""
        self.fast_collapse_count = 0
        self.daily_trades = 0
        self.current_mode = OperationMode.NORMAL
    
    def _check_emergency(self):
        """Emergency Clause 체크"""
        if self.fast_collapse_count > self.FAST_COLLAPSE_THRESHOLD:
            self.current_mode = OperationMode.CONSERVATIVE
    
    def force_conservative(self, reason: str = "Manual override"):
        """수동 보수 모드 전환"""
        self.current_mode = OperationMode.CONSERVATIVE
    
    def force_normal(self):
        """수동 일반 모드 전환"""
        self.current_mode = OperationMode.NORMAL


# 모드별 예상 성능 (검증 결과 기반)
MODE_EXPECTED_PERFORMANCE = {
    OperationMode.NORMAL: {
        "theta": 1,
        "expected_trades_per_day": 90,
        "expected_winrate": 0.902,
        "expected_ev": 16.65,
        "max_dd": 288,
    },
    OperationMode.CONSERVATIVE: {
        "theta": 3,
        "expected_trades_per_day": 2,
        "expected_winrate": 1.0,
        "expected_ev": 20.0,
        "max_dd": 0,
    }
}
