"""
V7 4D Observation Engine - ML Encoder v0.2
Distribution-Aligned, Non-Invasive

Core Principle:
"ML does not modify coordinates. ML only tells coordinate reliability."

Changes from v0.1:
- DC blending REMOVED (DC_final = DC_rule always)
- ML outputs only: uncertainty, noise_flag
- Gate uses uncertainty filter only

Allowed:
- uncertainty: float [0,1] - higher = less reliable
- noise_flag: bool - True if DC extremity is noisy
- confidence: float - 1 - uncertainty

Forbidden:
- Force/DC/Delta/τ modification
- Threshold involvement (0.9/0.1/τ≥5/dir≥3)
- Prediction/direction/timing
"""

import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass

from ml_encoder_interface import MLEncoderInterface, StateEstimate


class UncertaintyEstimator:
    """
    Lightweight model for uncertainty estimation only.
    
    Input: Recent price/volatility features
    Output: uncertainty (0-1), noise_flag (bool)
    
    Does NOT output state coordinates.
    """
    
    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        np.random.seed(42)
        self.w_unc = np.random.randn(4, 1) * 0.1
    
    def estimate(self, features: Dict) -> Dict:
        """
        Estimate uncertainty from features.
        
        Features used (minimal, non-semantic):
        - price_volatility: |ΔP| normalized
        - dc_slope: DC rate of change
        - dc_variance: DC short-term variance
        - consistency: Force consistency
        """
        vol = features.get('price_volatility', 0.5)
        dc_slope = features.get('dc_slope', 0.0)
        dc_var = features.get('dc_variance', 0.0)
        consistency = features.get('force_consistency', 1.0)
        
        x = np.array([[vol, abs(dc_slope), dc_var, 1 - consistency]])
        raw = float(np.tanh(x @ self.w_unc).flatten()[0])
        uncertainty = (raw + 1) / 2  # Scale to 0-1
        
        noise_flag = uncertainty > 0.7 and dc_var > 0.1
        
        return {
            'uncertainty': uncertainty,
            'noise_flag': noise_flag,
            'confidence': 1.0 - uncertainty
        }


class MLEncoderV02(MLEncoderInterface):
    """
    ML Encoder v0.2 - Distribution-Aligned
    
    Core Changes:
    1. DC_final = DC_rule (NEVER modified by ML)
    2. ML outputs uncertainty/noise_flag ONLY
    3. All state coordinates from Rule-based calculation
    
    Gate Integration:
    IF Rule says ENTER AND uncertainty <= U_MAX → ENTER
    ELSE → OBSERVE
    
    U_MAX = 0.6 (frozen, no tuning)
    """
    
    U_MAX = 0.6  # Frozen threshold
    
    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self.history: List[Dict] = []
        self.uncertainty_model = UncertaintyEstimator(window_size=10)
        
        self.dc_hold_count = 0
        self.dc_hold_count_low = 0
        self.last_state: Optional[StateEstimate] = None
    
    @property
    def name(self) -> str:
        return "MLEncoderV02"
    
    def encode(self, features: Dict) -> StateEstimate:
        """
        v0.2: Only estimate uncertainty, NOT coordinates.
        Coordinates come from rule-based calculation.
        """
        ml_output = self.uncertainty_model.estimate(features)
        
        return StateEstimate(
            force_hat=features.get('force_rule', 0.0),
            dc_hat=features.get('dc_rule', 0.5),
            delta_hat=features.get('delta_rule', 0.0),
            tau_hat=features.get('tau_rule', 0),
            uncertainty={
                'force_var': ml_output['uncertainty'],
                'dc_var': ml_output['uncertainty'],
                'delta_var': ml_output['uncertainty'],
                'tau_var': 0.0,
                'noise_flag': ml_output['noise_flag'],
                'confidence': ml_output['confidence']
            }
        )
    
    def update(self, candle: Dict) -> StateEstimate:
        """Update with new candle and return state estimate"""
        self.history.append(candle)
        if len(self.history) > 100:
            self.history = self.history[-100:]
        
        force_rule = self._calc_force()
        dc_rule = self._calc_dc()
        delta_rule = self._calc_delta(candle)
        tau_rule = self._calc_tau(dc_rule)
        
        features = {
            'force_rule': force_rule,
            'dc_rule': dc_rule,
            'delta_rule': delta_rule,
            'tau_rule': tau_rule,
            'price_volatility': self._calc_volatility(),
            'dc_slope': self._calc_dc_slope(),
            'dc_variance': self._calc_dc_variance(),
            'force_consistency': self._calc_force_consistency()
        }
        
        ml_output = self.uncertainty_model.estimate(features)
        
        state = StateEstimate(
            force_hat=force_rule,
            dc_hat=dc_rule,
            delta_hat=delta_rule,
            tau_hat=tau_rule,
            uncertainty={
                'force_var': ml_output['uncertainty'],
                'dc_var': ml_output['uncertainty'],
                'delta_var': ml_output['uncertainty'],
                'tau_var': 0.0,
                'noise_flag': ml_output['noise_flag'],
                'confidence': ml_output['confidence']
            }
        )
        
        self.last_state = state
        return state
    
    def reset(self) -> None:
        """Reset encoder state"""
        self.history = []
        self.dc_hold_count = 0
        self.dc_hold_count_low = 0
        self.last_state = None
    
    def _calc_volatility(self) -> float:
        """Calculate normalized price volatility"""
        if len(self.history) < 5:
            return 0.5
        
        recent = self.history[-5:]
        returns = []
        for i in range(1, len(recent)):
            ret = abs(recent[i]['close'] - recent[i-1]['close'])
            returns.append(ret)
        
        if not returns:
            return 0.5
        
        avg_range = np.mean([c['high'] - c['low'] for c in recent])
        if avg_range <= 0:
            return 0.5
        
        return min(1.0, np.mean(returns) / avg_range)
    
    def _calc_dc_slope(self) -> float:
        """Calculate DC rate of change"""
        if len(self.history) < 3:
            return 0.0
        
        recent = self.history[-3:]
        dcs = []
        for c in recent:
            lookback = self.history[-20:] if len(self.history) >= 20 else self.history
            high_max = max(h['high'] for h in lookback)
            low_min = min(h['low'] for h in lookback)
            rng = high_max - low_min
            if rng > 0:
                dcs.append((c['close'] - low_min) / rng)
            else:
                dcs.append(0.5)
        
        if len(dcs) < 2:
            return 0.0
        
        return dcs[-1] - dcs[0]
    
    def _calc_dc_variance(self) -> float:
        """Calculate DC short-term variance"""
        if len(self.history) < 5:
            return 0.0
        
        recent = self.history[-5:]
        dcs = []
        for c in recent:
            lookback = self.history[-20:] if len(self.history) >= 20 else self.history
            high_max = max(h['high'] for h in lookback)
            low_min = min(h['low'] for h in lookback)
            rng = high_max - low_min
            if rng > 0:
                dcs.append((c['close'] - low_min) / rng)
            else:
                dcs.append(0.5)
        
        return float(np.var(dcs))
    
    def _calc_force_consistency(self) -> float:
        """Calculate Force direction consistency"""
        if len(self.history) < 5:
            return 1.0
        
        recent = self.history[-5:]
        directions = []
        for c in recent:
            if c['close'] > c['open']:
                directions.append(1)
            elif c['close'] < c['open']:
                directions.append(-1)
            else:
                directions.append(0)
        
        if not directions:
            return 1.0
        
        dominant = max(set(directions), key=directions.count)
        consistency = directions.count(dominant) / len(directions)
        return consistency
    
    def _calc_force(self) -> float:
        """Calculate Force (rule-based, unchanged)"""
        window = 5
        if len(self.history) < window:
            return 0.0
        
        recent = self.history[-window:]
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
        """Calculate DC (rule-based, unchanged)"""
        lookback = 20
        if len(self.history) < 2:
            return 0.5
        
        lookback_data = self.history[-lookback:]
        high_max = max(c['high'] for c in lookback_data)
        low_min = min(c['low'] for c in lookback_data)
        ch_range = high_max - low_min
        
        if ch_range <= 0:
            return 0.5
        
        current_close = self.history[-1]['close']
        return (current_close - low_min) / ch_range
    
    def _calc_delta(self, candle: Dict) -> float:
        """Calculate Delta (rule-based, unchanged)"""
        rng = candle['high'] - candle['low']
        if rng <= 0:
            return 0.0
        body = abs(candle['close'] - candle['open'])
        return (body / rng) * rng
    
    def _calc_tau(self, dc: float) -> int:
        """Calculate τ (rule-based, unchanged)"""
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
    
    @staticmethod
    def get_uncertainty_warning(action: str, uncertainty: float) -> str:
        """
        Get uncertainty warning (LOGGING ONLY - does NOT modify action).
        
        ML Constitutional Rule:
        - ML only reports uncertainty
        - ML does NOT modify actions
        - Action changes are FORBIDDEN in ML layer
        
        Returns:
            Warning message for logging (empty if no warning)
        """
        if action == 'ENTER' and uncertainty > MLEncoderV02.U_MAX:
            return f"WARNING: High uncertainty ({uncertainty:.3f}) on ENTER signal"
        return ""
