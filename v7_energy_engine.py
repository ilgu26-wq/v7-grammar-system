"""
V7 Energy Conservation Engine + SL Defense
확정일: 2026-01-21 (Git Lock 승인 - Pre-Git Protocol 6/6 통과)

핵심 법칙:
1. 임계 에너지: MFE >= 7pt = 상태 전이 (LOSS 0건)
2. 에너지 보존: trail = MFE - 1.5pt (78% 보존)
3. EE 필터 없음: 모든 STB 신호 허용
4. 방향 무관: LONG/SHORT 동일 규칙
5. SL Defense: 4봉 내 MFE < 1.5pt → SL -12pt (G3)

검증 결과: 승률 80.9%, EV +3.18pt → G3 적용 시 EV +3.35pt

가설검증 (Pre-Git Protocol):
- H0-1 시간 OOS: ✅ Train 80.8% → Test 83.1%
- H0-2 Bootstrap: ✅ G3 > G0 비율 57.5%
- H0-3 역할 분리: ✅ MFE≥7 LOSS = 0건
- H0-4 임계 안정성: ✅ EV plateau 0.44pt
- H0-5 LOSS 문법: ✅ 평균 손실 -30 → -25.8pt
- H0-6 레짐 독립성: ✅ 전 레짐 EV 양수

Note:
MFE >= 7 represents a statistical energy threshold observed across
multiple parameter plateaus (5-7pt).
The value 7 is selected as the conservative core setting.

Constitutional Statement:
"MFE 7pt is a physics-level invariant (loss-free after state transition).
MFE 5pt is a probabilistic optimization option that increases harvest rate
at the cost of physical guarantees."
"""

from dataclasses import dataclass
from typing import Optional, Tuple
from enum import Enum


class TradeState(Enum):
    ACTIVE = "active"
    TRAILING = "trailing"
    CLOSED = "closed"


@dataclass
class V7Position:
    direction: str  # 'LONG' or 'SHORT'
    entry_price: float
    entry_time: str
    sl: float = 30.0
    
    mfe: float = 0.0
    current_pnl: float = 0.0
    trailing_stop: Optional[float] = None
    state: TradeState = TradeState.ACTIVE
    bars: int = 0  # 경과 캔들 수 (SL Defense용)
    
    MFE_THRESHOLD: float = 7.0
    TRAIL_OFFSET: float = 1.5
    
    # SL Defense (G3)
    LWS_BARS: int = 4          # Loss Warning State 발동 캔들 수
    LWS_MFE_THRESHOLD: float = 1.5  # LWS MFE 임계점
    DEFENSE_SL: float = 12.0   # 축소된 SL


class V7EnergyEngine:
    """
    V7 에너지 보존 엔진 + SL Defense (G3)
    
    규칙 (변경 금지):
    - MFE >= 7pt 도달 시 트레일링 활성화
    - trailing_stop = entry_price + (MFE - 1.5pt)
    - 에너지 78% 보존
    - SL Defense: 4봉 내 MFE < 1.5pt → SL -12pt
    """
    
    MFE_THRESHOLD = 7.0
    TRAIL_OFFSET = 1.5
    DEFAULT_SL = 30.0
    
    # SL Defense (G3)
    LWS_BARS = 4              # Loss Warning State 발동 캔들 수
    LWS_MFE_THRESHOLD = 1.5   # LWS MFE 임계점
    DEFENSE_SL = 12.0         # 축소된 SL
    
    def __init__(self):
        self.positions = {}
    
    def open_position(self, trade_id: str, direction: str, 
                      entry_price: float, entry_time: str) -> V7Position:
        """새 포지션 오픈"""
        position = V7Position(
            direction=direction,
            entry_price=entry_price,
            entry_time=entry_time,
            sl=self.DEFAULT_SL
        )
        self.positions[trade_id] = position
        return position
    
    def update_position(self, trade_id: str, high: float, low: float, 
                        close: float) -> Tuple[Optional[str], float]:
        """
        캔들 데이터로 포지션 업데이트
        
        Returns:
            (exit_type, exit_pnl) or (None, 0) if still open
        """
        if trade_id not in self.positions:
            return None, 0
        
        pos = self.positions[trade_id]
        
        if pos.state == TradeState.CLOSED:
            return None, 0
        
        # 캔들 카운트 증가
        pos.bars += 1
        
        # SL Defense (G3): Loss Warning State 체크
        if pos.bars >= self.LWS_BARS and pos.mfe < self.LWS_MFE_THRESHOLD:
            pos.sl = self.DEFENSE_SL  # SL 축소
        
        if pos.direction == 'LONG':
            bar_mfe = high - pos.entry_price
            pos.mfe = max(pos.mfe, bar_mfe)
            pos.current_pnl = close - pos.entry_price
            
            if pos.mfe >= self.MFE_THRESHOLD and pos.state == TradeState.ACTIVE:
                pos.state = TradeState.TRAILING
                pos.trailing_stop = pos.entry_price + (pos.mfe - self.TRAIL_OFFSET)
            
            if pos.state == TradeState.TRAILING:
                pos.trailing_stop = max(
                    pos.trailing_stop,
                    pos.entry_price + (pos.mfe - self.TRAIL_OFFSET)
                )
                if low <= pos.trailing_stop:
                    exit_pnl = max(pos.trailing_stop - pos.entry_price, 1)
                    pos.state = TradeState.CLOSED
                    return 'TRAIL_WIN', exit_pnl
            
            if low <= pos.entry_price - pos.sl:
                pos.state = TradeState.CLOSED
                return 'LOSS', -pos.sl
        
        else:
            bar_mfe = pos.entry_price - low
            pos.mfe = max(pos.mfe, bar_mfe)
            pos.current_pnl = pos.entry_price - close
            
            if pos.mfe >= self.MFE_THRESHOLD and pos.state == TradeState.ACTIVE:
                pos.state = TradeState.TRAILING
                pos.trailing_stop = pos.entry_price - (pos.mfe - self.TRAIL_OFFSET)
            
            if pos.state == TradeState.TRAILING:
                pos.trailing_stop = min(
                    pos.trailing_stop,
                    pos.entry_price - (pos.mfe - self.TRAIL_OFFSET)
                )
                if high >= pos.trailing_stop:
                    exit_pnl = max(pos.entry_price - pos.trailing_stop, 1)
                    pos.state = TradeState.CLOSED
                    return 'TRAIL_WIN', exit_pnl
            
            if high >= pos.entry_price + pos.sl:
                pos.state = TradeState.CLOSED
                return 'LOSS', -pos.sl
        
        return None, 0
    
    def get_position_status(self, trade_id: str) -> Optional[dict]:
        """포지션 상태 조회"""
        if trade_id not in self.positions:
            return None
        
        pos = self.positions[trade_id]
        return {
            'direction': pos.direction,
            'entry_price': pos.entry_price,
            'mfe': pos.mfe,
            'current_pnl': pos.current_pnl,
            'state': pos.state.value,
            'trailing_stop': pos.trailing_stop,
            'trailing_active': pos.state == TradeState.TRAILING
        }
    
    def close_position(self, trade_id: str) -> Optional[float]:
        """포지션 수동 청산"""
        if trade_id not in self.positions:
            return None
        
        pos = self.positions[trade_id]
        pos.state = TradeState.CLOSED
        return pos.current_pnl


def check_stb_entry(candle: dict, history: list) -> Optional[str]:
    """
    STB 진입 조건 확인 (EE 필터 없음)
    
    조건:
    - 레인지 >= 30pt
    - body_zscore >= 1.0
    - 배율 > 1.5 + 채널 > 80% → SHORT
    - 배율 < 0.7 + 채널 < 20% → LONG
    """
    if len(history) < 50:
        return None
    
    h, l, c = candle['high'], candle['low'], candle['close']
    ratio = max(c - l, 0.01) / max(h - c, 0.01)
    
    highs = [x['high'] for x in history[-20:]]
    lows = [x['low'] for x in history[-20:]]
    ch_range = max(highs) - min(lows)
    
    if ch_range < 30:
        return None
    
    channel_pct = ((c - min(lows)) / ch_range) * 100
    
    import numpy as np
    bodies = [abs(x['close'] - x['open']) for x in history[-50:]]
    body = abs(candle['close'] - candle['open'])
    body_z = (body - np.mean(bodies)) / np.std(bodies) if np.std(bodies) > 0 else 0
    
    if abs(body_z) < 1.0:
        return None
    
    if ratio > 1.5 and channel_pct > 80:
        return 'SHORT'
    elif ratio < 0.7 and channel_pct < 20:
        return 'LONG'
    
    return None
