"""
V7 Grammar System - Decision Engine Demo
=========================================

This is a read-only demonstration of the V7 decision grammar.
No execution, no orders, no live trading code.

Purpose: Show the decision classification logic only.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class MarketState(Enum):
    SIDEWAYS = "sideways"
    OVERBOUGHT = "overbought"
    OVERSOLD = "oversold"
    TRENDING = "trending"


class TradeState(Enum):
    ACTIVE = "active"
    TRAILING = "trailing"
    CLOSED = "closed"


@dataclass
class CandleData:
    open: float
    high: float
    low: float
    close: float


def calculate_ratio(candle: CandleData) -> float:
    """
    Core formula: ratio = (close - low) / (high - close)
    
    Interpretation:
    - ratio > 1.5: Overbought (53% down probability)
    - ratio < 0.7: Oversold (58% up probability)
    """
    numerator = max(candle.close - candle.low, 0.01)
    denominator = max(candle.high - candle.close, 0.01)
    return numerator / denominator


def calculate_channel_percent(close: float, ch_high: float, ch_low: float) -> float:
    """
    Channel position: where is price within 20-bar range?
    
    - > 80%: Near top (short bias)
    - < 20%: Near bottom (long bias)
    """
    ch_range = ch_high - ch_low
    if ch_range < 1:
        return 50.0
    return ((close - ch_low) / ch_range) * 100


def classify_market_state(ratio: float, ch_range: float) -> MarketState:
    """
    Market state classification (priority order):
    
    1. Range < 30pt → SIDEWAYS (87.2% accuracy)
    2. Ratio > 1.3 → OVERBOUGHT
    3. Ratio < 0.7 → OVERSOLD
    4. Otherwise → TRENDING
    """
    if ch_range < 30:
        return MarketState.SIDEWAYS
    if ratio > 1.3:
        return MarketState.OVERBOUGHT
    if ratio < 0.7:
        return MarketState.OVERSOLD
    return MarketState.TRENDING


def check_stb_entry(candle: CandleData, ch_high: float, ch_low: float, 
                    body_zscore: float) -> Optional[str]:
    """
    STB Entry Conditions (no EE filter):
    
    SHORT: ratio > 1.5 + channel > 80% + body_z >= 1.0
    LONG:  ratio < 0.7 + channel < 20% + body_z >= 1.0
    
    Returns: 'LONG', 'SHORT', or None
    """
    ch_range = ch_high - ch_low
    if ch_range < 30:
        return None
    
    ratio = calculate_ratio(candle)
    channel_pct = calculate_channel_percent(candle.close, ch_high, ch_low)
    
    if abs(body_zscore) < 1.0:
        return None
    
    if ratio > 1.5 and channel_pct > 80:
        return 'SHORT'
    elif ratio < 0.7 and channel_pct < 20:
        return 'LONG'
    
    return None


class V7EnergyManager:
    """
    V7 Energy Conservation Engine (Read-Only Demo)
    
    Physics Laws (LOCKED):
    1. MFE >= 7pt = State transition (loss-free)
    2. Trail = MFE - 1.5pt (78% energy conservation)
    3. SL Defense: 4 bars + MFE < 1.5 → SL = 12pt
    """
    
    MFE_THRESHOLD = 7.0      # State transition point (LOCKED)
    TRAIL_OFFSET = 1.5       # Energy conservation (LOCKED)
    DEFAULT_SL = 30.0        # Base failure cost
    
    LWS_BARS = 4             # Loss Warning State trigger
    LWS_MFE_THRESHOLD = 1.5  # Energy failure threshold
    DEFENSE_SL = 12.0        # Reduced SL for LWS
    
    def evaluate_position(self, mfe: float, bars: int) -> dict:
        """
        Evaluate position state based on MFE and bars elapsed.
        
        Returns decision explanation (no execution).
        """
        result = {
            'mfe': mfe,
            'bars': bars,
            'state': 'ACTIVE',
            'trailing_active': False,
            'sl': self.DEFAULT_SL,
            'explanation': ''
        }
        
        if mfe >= self.MFE_THRESHOLD:
            result['state'] = 'TRAILING'
            result['trailing_active'] = True
            trail_level = mfe - self.TRAIL_OFFSET
            result['trail_level'] = trail_level
            result['explanation'] = (
                f"Energy threshold crossed (MFE={mfe:.1f} >= {self.MFE_THRESHOLD}). "
                f"Trailing active at {trail_level:.1f}pt. "
                f"Post-transition loss probability = 0."
            )
        elif bars >= self.LWS_BARS and mfe < self.LWS_MFE_THRESHOLD:
            result['sl'] = self.DEFENSE_SL
            result['explanation'] = (
                f"Loss Warning State triggered (bars={bars} >= {self.LWS_BARS}, "
                f"MFE={mfe:.1f} < {self.LWS_MFE_THRESHOLD}). "
                f"SL reduced to {self.DEFENSE_SL}pt to limit failure cost."
            )
        else:
            result['explanation'] = (
                f"Active position. MFE={mfe:.1f}, bars={bars}. "
                f"Waiting for energy threshold ({self.MFE_THRESHOLD}pt) or LWS trigger."
            )
        
        return result


def demo():
    """
    Demonstration of V7 decision grammar.
    """
    print("=" * 60)
    print("V7 Grammar System - Decision Engine Demo")
    print("=" * 60)
    
    candle = CandleData(open=21500, high=21520, low=21480, close=21515)
    ch_high, ch_low = 21550, 21450
    
    print("\n1. Market State Classification")
    print("-" * 40)
    ratio = calculate_ratio(candle)
    ch_range = ch_high - ch_low
    state = classify_market_state(ratio, ch_range)
    print(f"   Ratio: {ratio:.2f}")
    print(f"   Channel Range: {ch_range}pt")
    print(f"   Market State: {state.value}")
    
    print("\n2. Entry Check (STB)")
    print("-" * 40)
    entry = check_stb_entry(candle, ch_high, ch_low, body_zscore=1.5)
    print(f"   Entry Signal: {entry or 'None'}")
    
    print("\n3. Energy Management Examples")
    print("-" * 40)
    manager = V7EnergyManager()
    
    scenarios = [
        (8.5, 5),   # Trailing active
        (1.0, 5),   # LWS triggered
        (3.0, 2),   # Still waiting
    ]
    
    for mfe, bars in scenarios:
        result = manager.evaluate_position(mfe, bars)
        print(f"\n   MFE={mfe:.1f}, Bars={bars}")
        print(f"   State: {result['state']}")
        print(f"   SL: {result['sl']}pt")
        print(f"   → {result['explanation']}")
    
    print("\n" + "=" * 60)
    print("This is a read-only demo. No orders, no execution.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
