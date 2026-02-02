"""
DECISION SELECTOR v1.0 (IGNITION_CANDIDATE 권한 적용)
-----------------------------------------------------
역할: 판단을 바꾸지 않고, 권한 수준에 따라 사이즈 조정

v0.1 → v1.0 변경:
- IGNITION_CANDIDATE 권한 연동
- ELEVATED 권한 시 SIZE_DOWN 스킵

핵심 원칙:
- θ 예측 시도 ❌
- SKIP 하지 않음
- 결정은 그대로, 권한만 다르게

허용 행동:
  1. EXECUTE (기본)
  2. SIZE_DOWN (LONG 관찰 모드) - ELEVATED면 스킵

금지 행동:
  - SKIP (θ 예측 불가)
  - 신호 생성
  - 방향 변경
  - SIZE_UP ❌
"""

from dataclasses import dataclass
from typing import Tuple, Optional
from enum import Enum
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from opa.ignition_guard import IgnitionGuard, PrivilegeLevel, PolicyContext


class SelectorAction(Enum):
    EXECUTE = "EXECUTE"


@dataclass
class BucketStats:
    win_rate: float
    avg_pnl: float
    sample_size: int


class DecisionSelector:
    """
    V7 판단 위에서 작동하는 실행 선택기 (v1.0 IGNITION 권한 적용)
    
    핵심 원칙:
    - θ 예측 시도 ❌
    - SKIP 하지 않음
    - 결정은 그대로, 권한만 다르게
    - ELEVATED → SIZE_DOWN 스킵
    """
    
    def __init__(self):
        self.default_size = 1.0
        self.long_size_multiplier = 0.5
        self.ignition_guard = IgnitionGuard()
    
    def select(
        self, 
        direction: str, 
        layer: str = None,
        delta: float = None,
        channel_pct: float = None,
        stb_index: str = "N/A",
        stb_confirmed: bool = False,
        in_cooldown: bool = False
    ) -> Tuple[SelectorAction, float, PolicyContext]:
        """
        ENTRY 시점 결정 선택 (v1.0)
        
        Args:
            direction: 'LONG' or 'SHORT'
            layer: 'OPA' or 'STB' (미사용)
            delta: ENTRY 시점 delta (미사용)
            channel_pct: ENTRY 시점 channel % (미사용)
            stb_index: 'first' or 're-entry'
            stb_confirmed: STB 확정 여부
            in_cooldown: 쿨다운 여부
            
        Returns:
            (EXECUTE, size_multiplier, PolicyContext)
        """
        ctx = self.ignition_guard.evaluate(stb_index, stb_confirmed, in_cooldown)
        
        size = self.default_size
        
        if direction == 'LONG':
            if ctx.privilege == PrivilegeLevel.ELEVATED and ctx.allow_size_down_skip:
                pass
            else:
                size *= self.long_size_multiplier
        
        return (SelectorAction.EXECUTE, size, ctx)
    
    def get_decision_reason(self, direction: str, ctx: PolicyContext) -> str:
        if ctx.privilege == PrivilegeLevel.ELEVATED:
            return f"ELEVATED: {ctx.reason}"
        if direction == 'LONG':
            return "SIZE_DOWN: LONG observation mode"
        return "STANDARD_EXECUTE"


class KillSwitch:
    """
    실사용 안전장치 v0.1
    
    조건 충족 시 시스템 OFF
    """
    
    def __init__(self, use_r_units: bool = False, r_value: float = 15.0):
        self.use_r_units = use_r_units
        self.r_value = r_value
        
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.theta3_failures = 0
        self.trade_count = 0
        
        # 임계값 (GPT 권장)
        self.max_daily_loss_r = -2.0
        self.max_daily_loss_pt = -30.0
        self.max_consecutive_losses = 2
        self.max_theta3_failures = 2
        self.max_trades_per_day = 3
    
    def _get_daily_loss_limit(self) -> float:
        if self.use_r_units:
            return self.max_daily_loss_r * self.r_value
        return self.max_daily_loss_pt
    
    def check(self) -> Tuple[bool, str]:
        limit = self._get_daily_loss_limit()
        
        if self.daily_pnl <= limit:
            return (True, f"DAILY_LOSS_LIMIT: {self.daily_pnl:.1f}pt")
        
        if self.consecutive_losses >= self.max_consecutive_losses:
            return (True, f"CONSECUTIVE_LOSSES: {self.consecutive_losses}")
        
        if self.theta3_failures >= self.max_theta3_failures:
            return (True, f"THETA3_FAILURES: {self.theta3_failures}")
        
        if self.trade_count >= self.max_trades_per_day:
            return (True, f"MAX_TRADES: {self.trade_count}")
        
        return (False, "OK")
    
    def update(self, pnl: float, theta_final: int = None):
        self.daily_pnl += pnl
        self.trade_count += 1
        
        if pnl < 0:
            self.consecutive_losses += 1
            if theta_final is not None and theta_final >= 3:
                self.theta3_failures += 1
        else:
            self.consecutive_losses = 0
    
    def reset_daily(self):
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.theta3_failures = 0
        self.trade_count = 0
    
    def get_status(self) -> dict:
        should_stop, reason = self.check()
        return {
            'daily_pnl': self.daily_pnl,
            'consecutive_losses': self.consecutive_losses,
            'theta3_failures': self.theta3_failures,
            'trade_count': self.trade_count,
            'should_stop': should_stop,
            'reason': reason
        }


if __name__ == "__main__":
    selector = DecisionSelector()
    kill_switch = KillSwitch(use_r_units=False)
    
    print("="*60)
    print("DECISION SELECTOR v1.0 (IGNITION PRIVILEGE)")
    print("="*60)
    print("\n핵심: 결정은 그대로, 권한만 다르게")
    print("      ELEVATED → SIZE_DOWN 스킵\n")
    
    test_cases = [
        ('SHORT', 'first', True, False),
        ('SHORT', 're-entry', True, False),
        ('LONG', 'first', True, False),
        ('LONG', 're-entry', True, False),
        ('LONG', 'first', True, True),
    ]
    
    print(f"{'Dir':<6} {'STB':<10} {'Size':>6} {'Privilege':<10} {'Reason'}")
    print("-"*70)
    
    for direction, stb_index, confirmed, cooldown in test_cases:
        action, size, ctx = selector.select(
            direction, 
            stb_index=stb_index, 
            stb_confirmed=confirmed, 
            in_cooldown=cooldown
        )
        reason = selector.get_decision_reason(direction, ctx)
        print(f"{direction:<6} {stb_index:<10} {size:>6.2f} {ctx.privilege.value:<10} {reason}")
    
    print("\n" + "="*60)
    print("KILL SWITCH v0.1")
    print("="*60)
    print(f"\nLimits:")
    print(f"  Daily: {kill_switch.max_daily_loss_pt}pt")
    print(f"  Consecutive: {kill_switch.max_consecutive_losses}")
    print(f"  Max trades: {kill_switch.max_trades_per_day}")
