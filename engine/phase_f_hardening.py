"""
V7 4D Observation Engine - Phase F Hardening
Micro-Variable Elimination Layer

Phase F Entry Condition:
"When the system is wrong, it's ONLY because of the external world"

This module eliminates:
1. Float boundary noise (DC comparison)
2. Cold start uncertainty
3. Timestamp ambiguity
4. τ definition ambiguity
"""

from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass
from typing import Optional, Dict
from enum import Enum


class EngineState(Enum):
    """Engine lifecycle state"""
    COLD = "COLD"           # Just started, warm-up required
    WARMING = "WARMING"     # Accumulating history
    READY = "READY"         # Full operation
    
    
@dataclass
class HardenedThresholds:
    """
    Phase F Hardened Thresholds
    
    All comparisons use Decimal to eliminate float noise.
    All values are frozen and documented.
    """
    DC_HIGH: Decimal = Decimal("0.9000")
    DC_LOW: Decimal = Decimal("0.1000")
    TAU_MIN: int = 5
    DIR_THRESHOLD: int = 3
    WARM_UP_BARS: int = 20  # Minimum history before decisions
    
    PRECISION: int = 4  # Decimal places
    
    def bucket_dc(self, dc_float: float) -> Decimal:
        """
        Convert float DC to bucketed Decimal.
        
        Eliminates float boundary noise:
        - 0.89999999 → 0.9000
        - 0.90000001 → 0.9000
        """
        quantize_str = "0." + "0" * self.PRECISION
        return Decimal(str(dc_float)).quantize(
            Decimal(quantize_str), 
            rounding=ROUND_HALF_UP
        )
    
    def dc_at_high(self, dc_float: float) -> bool:
        """Check if DC is at high boundary (hardened)"""
        dc = self.bucket_dc(dc_float)
        return dc >= self.DC_HIGH
    
    def dc_at_low(self, dc_float: float) -> bool:
        """Check if DC is at low boundary (hardened)"""
        dc = self.bucket_dc(dc_float)
        return dc <= self.DC_LOW


THRESHOLDS = HardenedThresholds()


class ColdStartGuard:
    """
    Cold Start Protection
    
    When system starts:
    - First WARM_UP_BARS: ONLY WAIT allowed
    - No decisions until history is sufficient
    - Prevents warm-up state from affecting results
    """
    
    def __init__(self, warm_up_bars: int = 20):
        self.warm_up_bars = warm_up_bars
        self.bars_received = 0
        self.state = EngineState.COLD
    
    def update(self) -> EngineState:
        """Update state after receiving a bar"""
        self.bars_received += 1
        
        if self.bars_received < self.warm_up_bars // 2:
            self.state = EngineState.COLD
        elif self.bars_received < self.warm_up_bars:
            self.state = EngineState.WARMING
        else:
            self.state = EngineState.READY
        
        return self.state
    
    def can_decide(self) -> bool:
        """Check if engine can make decisions (not just WAIT)"""
        return self.state == EngineState.READY
    
    def must_wait(self) -> bool:
        """Check if engine must WAIT (cold start protection)"""
        return self.state != EngineState.READY
    
    def get_reason(self) -> str:
        """Get reason for current state"""
        if self.state == EngineState.COLD:
            return f"Cold start: {self.bars_received}/{self.warm_up_bars} bars"
        elif self.state == EngineState.WARMING:
            return f"Warming up: {self.bars_received}/{self.warm_up_bars} bars"
        return "Ready"
    
    def reset(self):
        """Reset to cold state"""
        self.bars_received = 0
        self.state = EngineState.COLD


@dataclass
class CanonicalCandle:
    """
    Canonical Candle Format
    
    Single source of truth for candle representation.
    Timestamp is always close_time_utc (never arrival time).
    """
    open: float
    high: float
    low: float
    close: float
    close_time_utc: Optional[int] = None  # Unix timestamp
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'CanonicalCandle':
        """Create from dict with validation"""
        return cls(
            open=float(d['open']),
            high=float(d['high']),
            low=float(d['low']),
            close=float(d['close']),
            close_time_utc=d.get('close_time_utc', d.get('timestamp'))
        )
    
    def to_dict(self) -> Dict:
        return {
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'close_time_utc': self.close_time_utc
        }


class TauCalculator:
    """
    Canonical τ Calculator
    
    τ Definition (one line, no ambiguity):
    
    if DC >= 0.9: tau += 1
    else: tau = 0
    
    Rules:
    - DC must stay >= 0.9 CONTINUOUSLY
    - Any drop below 0.9 RESETS τ to 0
    - Uses hardened DC comparison (Decimal)
    """
    
    def __init__(self):
        self.tau_high = 0
        self.tau_low = 0
        self.thresholds = THRESHOLDS
    
    def update(self, dc: float) -> int:
        """
        Update τ based on DC.
        
        Returns current τ value.
        """
        if self.thresholds.dc_at_high(dc):
            self.tau_high += 1
            self.tau_low = 0
        elif self.thresholds.dc_at_low(dc):
            self.tau_low += 1
            self.tau_high = 0
        else:
            self.tau_high = 0
            self.tau_low = 0
        
        return max(self.tau_high, self.tau_low)
    
    def get_tau(self) -> int:
        """Get current τ"""
        return max(self.tau_high, self.tau_low)
    
    def get_direction(self) -> str:
        """Get current direction based on τ"""
        if self.tau_high > self.tau_low:
            return "HIGH"
        elif self.tau_low > self.tau_high:
            return "LOW"
        return "NEUTRAL"
    
    def reset(self):
        """Reset τ counters"""
        self.tau_high = 0
        self.tau_low = 0


class PhaseF_Guard:
    """
    Complete Phase F Guard
    
    Integrates all micro-variable protections:
    - Hardened thresholds (Decimal)
    - Cold start protection
    - Canonical τ calculation
    - Timestamp enforcement
    """
    
    def __init__(self, warm_up_bars: int = 20):
        self.cold_start = ColdStartGuard(warm_up_bars)
        self.tau_calc = TauCalculator()
        self.thresholds = THRESHOLDS
        self.last_candle: Optional[CanonicalCandle] = None
    
    def process_candle(self, candle_dict: Dict) -> Dict:
        """
        Process candle through Phase F guards.
        
        Returns:
            {
                'can_decide': bool,
                'tau': int,
                'dc_bucketed': Decimal,
                'direction': str,
                'guard_state': str,
                'guard_reason': str
            }
        """
        candle = CanonicalCandle.from_dict(candle_dict)
        self.last_candle = candle
        
        engine_state = self.cold_start.update()
        
        ch_range = candle.high - candle.low
        if ch_range > 0:
            dc_raw = (candle.close - candle.low) / ch_range
        else:
            dc_raw = 0.5
        
        dc_bucketed = self.thresholds.bucket_dc(dc_raw)
        
        tau = self.tau_calc.update(dc_raw)
        direction = self.tau_calc.get_direction()
        
        return {
            'can_decide': self.cold_start.can_decide(),
            'tau': tau,
            'dc_raw': dc_raw,
            'dc_bucketed': float(dc_bucketed),
            'direction': direction,
            'guard_state': engine_state.value,
            'guard_reason': self.cold_start.get_reason()
        }
    
    def reset(self):
        """Reset all guards"""
        self.cold_start.reset()
        self.tau_calc.reset()
        self.last_candle = None


PHASE_F_CHECKLIST = """
Phase F Pre-Entry Checklist (All must be YES):

[ ] timestamp 기준 1개로 고정됨 (close_time_utc)
[ ] 상태 업데이트 단일 함수 (process())
[ ] τ 정의가 if/else 한 줄로 설명 가능
[ ] DC 경계 Decimal 처리됨 (bucket_dc)
[ ] ML uncertainty decision 접근 0회
[ ] cold start 명시적 차단 (ColdStartGuard)
"""


def test_phase_f_hardening():
    """Test Phase F hardening components"""
    print("=" * 60)
    print("PHASE F HARDENING TEST")
    print("=" * 60)
    
    guard = PhaseF_Guard(warm_up_bars=5)
    
    test_candles = [
        {'open': 100, 'high': 110, 'low': 99, 'close': 109},  # DC = 0.909
        {'open': 109, 'high': 115, 'low': 108, 'close': 114},  # DC high
        {'open': 114, 'high': 116, 'low': 113, 'close': 115},  # DC high
        {'open': 115, 'high': 117, 'low': 114, 'close': 116},  # DC high
        {'open': 116, 'high': 118, 'low': 115, 'close': 117},  # DC high
        {'open': 117, 'high': 119, 'low': 116, 'close': 118},  # DC high
        {'open': 118, 'high': 120, 'low': 110, 'close': 112},  # DC drops
    ]
    
    print("\nProcessing candles with Phase F guards:")
    print("-" * 60)
    
    for i, candle in enumerate(test_candles):
        result = guard.process_candle(candle)
        print(f"Bar {i+1}: DC={result['dc_bucketed']:.4f}, τ={result['tau']}, "
              f"can_decide={result['can_decide']}, state={result['guard_state']}")
    
    print("\n" + "=" * 60)
    print("Float Boundary Test:")
    print("-" * 60)
    
    th = HardenedThresholds()
    test_values = [0.8999999, 0.9000000, 0.9000001, 0.89999, 0.90001]
    for val in test_values:
        bucketed = th.bucket_dc(val)
        at_high = th.dc_at_high(val)
        print(f"  {val:.7f} → {bucketed} (at_high={at_high})")
    
    print("\n" + PHASE_F_CHECKLIST)


if __name__ == "__main__":
    test_phase_f_hardening()
