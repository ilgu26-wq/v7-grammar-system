"""
V7 4D Observation Engine - Observation Encoder
ML ALLOWED ZONE: 2D → 4D State Estimation

State = (Force, DC, Delta, τ)

This module estimates the current 4D state from raw market data.
ML is ONLY used here for coordinate estimation, NEVER for prediction.
"""

import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class State4D:
    """4D State Space coordinates"""
    force: float      # Compression/direction/energy density
    dc: float         # Channel position (0-1)
    delta: float      # Body ratio * range (energy release)
    tau: int          # DC hold time (consecutive bars)
    
    force_var: float = 0.0  # Uncertainty
    dc_var: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'force': self.force,
            'dc': self.dc,
            'delta': self.delta,
            'tau': self.tau,
            'uncertainty': {
                'force_var': self.force_var,
                'dc_var': self.dc_var
            }
        }


class ObservationEncoder:
    """
    Encodes raw market data into 4D State Space.
    
    ML Usage: ONLY for 2D→3D coordinate estimation
    NOT for: Prediction, direction guessing, outcome forecasting
    """
    
    def __init__(self, lookback: int = 20, force_window: int = 5):
        self.lookback = lookback
        self.force_window = force_window
        self.history: List[Dict] = []
        self.dc_hold_count = 0
        self.dc_hold_count_low = 0
        
    def update(self, candle: Dict) -> State4D:
        """
        Process new candle and return current 4D state.
        
        Args:
            candle: {open, high, low, close, volume (optional)}
        
        Returns:
            State4D with current coordinates
        """
        self.history.append(candle)
        if len(self.history) > 100:
            self.history = self.history[-100:]
        
        force = self._calc_force()
        dc = self._calc_dc()
        delta = self._calc_delta(candle)
        tau = self._calc_tau(dc)
        
        return State4D(
            force=force,
            dc=dc,
            delta=delta,
            tau=tau,
            force_var=self._estimate_force_var(),
            dc_var=self._estimate_dc_var()
        )
    
    def _calc_force(self) -> float:
        """Calculate Force = Bull accumulation - Bear accumulation"""
        if len(self.history) < self.force_window:
            return 0.0
        
        recent = self.history[-self.force_window:]
        bull_sum = 0.0
        bear_sum = 0.0
        
        for c in recent:
            rng = c['high'] - c['low']
            if rng <= 0:
                continue
            body = abs(c['close'] - c['open'])
            body_ratio = body / rng
            
            if c['close'] > c['open']:
                bull_sum += body_ratio
            else:
                bear_sum += body_ratio
        
        return bull_sum - bear_sum
    
    def _calc_dc(self) -> float:
        """Calculate DC (Donchian Channel position)"""
        if len(self.history) < 2:
            return 0.5
        
        lookback_data = self.history[-self.lookback:]
        high_max = max(c['high'] for c in lookback_data)
        low_min = min(c['low'] for c in lookback_data)
        ch_range = high_max - low_min
        
        if ch_range <= 0:
            return 0.5
        
        current_close = self.history[-1]['close']
        return (current_close - low_min) / ch_range
    
    def _calc_delta(self, candle: Dict) -> float:
        """Calculate Delta = body_ratio * range"""
        rng = candle['high'] - candle['low']
        if rng <= 0:
            return 0.0
        body = abs(candle['close'] - candle['open'])
        return (body / rng) * rng
    
    def _calc_tau(self, dc: float) -> int:
        """Calculate τ (DC hold time)"""
        if dc >= 0.9:
            self.dc_hold_count += 1
            self.dc_hold_count_low = 0
        elif dc <= 0.1:
            self.dc_hold_count_low += 1
            self.dc_hold_count = 0
        else:
            self.dc_hold_count = 0
            self.dc_hold_count_low = 0
        
        return max(self.dc_hold_count, self.dc_hold_count_low)
    
    def _estimate_force_var(self) -> float:
        """Estimate Force uncertainty"""
        if len(self.history) < 10:
            return 1.0
        
        forces = []
        for i in range(len(self.history) - self.force_window, len(self.history)):
            if i < self.force_window:
                continue
            window = self.history[i-self.force_window:i]
            bull = sum(abs(c['close']-c['open'])/(c['high']-c['low']) 
                      for c in window if c['high'] > c['low'] and c['close'] > c['open'])
            bear = sum(abs(c['close']-c['open'])/(c['high']-c['low']) 
                      for c in window if c['high'] > c['low'] and c['close'] <= c['open'])
            forces.append(bull - bear)
        
        return np.std(forces) if forces else 1.0
    
    def _estimate_dc_var(self) -> float:
        """Estimate DC uncertainty"""
        if len(self.history) < 10:
            return 0.1
        
        dcs = []
        for i in range(-10, 0):
            if abs(i) >= len(self.history):
                continue
            lookback_end = len(self.history) + i
            lookback_start = max(0, lookback_end - self.lookback)
            window = self.history[lookback_start:lookback_end]
            if not window:
                continue
            high_max = max(c['high'] for c in window)
            low_min = min(c['low'] for c in window)
            ch_range = high_max - low_min
            if ch_range > 0:
                dcs.append((self.history[i]['close'] - low_min) / ch_range)
        
        return np.std(dcs) if dcs else 0.1
    
    def get_direction(self) -> str:
        """Get current direction based on DC hold"""
        if self.dc_hold_count > 0:
            return "HIGH"
        elif self.dc_hold_count_low > 0:
            return "LOW"
        return "NEUTRAL"
    
    def reset(self):
        """Reset encoder state"""
        self.history = []
        self.dc_hold_count = 0
        self.dc_hold_count_low = 0
