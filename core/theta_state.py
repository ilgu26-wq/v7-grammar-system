"""
θ State Engine
==============

θ 상태 계산 및 전이 로직

θ = 0: No State (DENY)
θ = 1: Birth (ALLOW, Fixed TP)
θ = 2: Transition (ALLOW, Retry 가능)
θ ≥ 3: Lock-in (ALLOW, Extension 가능)
"""

from dataclasses import dataclass
from typing import Optional, List


@dataclass
class ThetaState:
    """θ 상태"""
    value: int
    name: str
    bars_in_state: int = 0
    mfe: float = 0.0
    
    @property
    def is_certified(self) -> bool:
        return self.value >= 1


THETA_NAMES = {
    0: "NO_STATE",
    1: "BIRTH",
    2: "TRANSITION",
    3: "LOCK_IN",
}


class ThetaEngine:
    """θ 상태 계산 엔진"""
    
    def __init__(self):
        self.current_state = ThetaState(value=0, name="NO_STATE")
        self.history: List[ThetaState] = []
    
    def compute(self, mfe: float, bars: int, impulse_count: int = 0, 
                recovery_time: float = 0) -> ThetaState:
        """현재 상태 계산"""
        
        if mfe <= 0 and bars < 3:
            theta = 0
        elif mfe > 0 and mfe < 10:
            theta = 1
        elif mfe >= 10 and mfe < 15:
            if impulse_count > 2 and recovery_time < 4:
                theta = 2
            else:
                theta = 1
        else:
            theta = 3
        
        name = THETA_NAMES.get(theta, "LOCK_IN")
        
        new_state = ThetaState(
            value=theta,
            name=name,
            bars_in_state=bars,
            mfe=mfe,
        )
        
        if new_state.value != self.current_state.value:
            self.history.append(self.current_state)
        
        self.current_state = new_state
        return new_state
    
    def reset(self):
        """상태 리셋"""
        self.current_state = ThetaState(value=0, name="NO_STATE")
        self.history = []
    
    def get_history(self) -> List[ThetaState]:
        """상태 히스토리 반환"""
        return self.history + [self.current_state]
