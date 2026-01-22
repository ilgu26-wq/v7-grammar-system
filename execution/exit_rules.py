"""
Exit Rules
==========

청산 규칙

규칙:
- θ < 3: Fixed TP/SL only
- θ ≥ 3: Fixed TP or Extension (optional trailing)
"""

from dataclasses import dataclass
from typing import Optional

import sys
sys.path.insert(0, '/home/runner/workspace/v7-grammar-system')

from opa.policy_v74 import get_policy, can_trail


@dataclass
class ExitDecision:
    """청산 결정"""
    action: str  # "HOLD", "EXIT_TP", "EXIT_SL", "EXIT_TIMEOUT"
    reason: str
    pnl: float = 0


class ExitRules:
    """청산 규칙 엔진"""
    
    def __init__(self, tp: float = 20, sl: float = 12, timeout: int = 180):
        self.tp = tp
        self.sl = sl
        self.timeout = timeout
    
    def evaluate(self, theta: int, current_pnl: float, bars: int,
                 trailing_enabled: bool = False, peak_pnl: float = 0) -> ExitDecision:
        """청산 결정"""
        
        if current_pnl <= -self.sl:
            return ExitDecision(
                action="EXIT_SL",
                reason=f"Stop loss hit at {current_pnl:.2f}",
                pnl=current_pnl,
            )
        
        if current_pnl >= self.tp:
            return ExitDecision(
                action="EXIT_TP",
                reason=f"Take profit hit at {current_pnl:.2f}",
                pnl=current_pnl,
            )
        
        if bars >= self.timeout:
            return ExitDecision(
                action="EXIT_TIMEOUT",
                reason=f"Timeout at {bars} bars",
                pnl=current_pnl,
            )
        
        if theta >= 3 and trailing_enabled and can_trail(theta):
            trailing_sl = peak_pnl * 0.5
            if current_pnl < trailing_sl and peak_pnl > 10:
                return ExitDecision(
                    action="EXIT_TRAIL",
                    reason=f"Trailing stop at {current_pnl:.2f} (peak: {peak_pnl:.2f})",
                    pnl=current_pnl,
                )
        
        return ExitDecision(
            action="HOLD",
            reason="Position open",
            pnl=current_pnl,
        )
