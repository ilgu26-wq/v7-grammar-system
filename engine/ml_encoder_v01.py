"""
V7 4D Observation Engine - ML Encoder v0.1
First ML Encoder Candidate

Design Philosophy:
"ML does not decide. It only tells how uncertain the current coordinates are."

Allowed:
- State coordinate estimation
- Uncertainty quantification
- Temporal smoothing

Forbidden:
- Win probability
- Direction prediction
- Entry suggestion
"""

import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass

from ml_encoder_interface import MLEncoderInterface, StateEstimate


class TemporalAutoencoder:
    """
    Simple temporal autoencoder for state estimation.
    
    Architecture:
    Input (window=20) → Encoder (MLP) → Latent → Heads
    
    Heads:
    - Force_hat
    - DC_hat  
    - Delta_hat
    - tau_hat
    - uncertainty (variance)
    """
    
    def __init__(self, window_size: int = 20, latent_dim: int = 8):
        self.window_size = window_size
        self.latent_dim = latent_dim
        
        np.random.seed(42)
        self.encoder_w1 = np.random.randn(5 * window_size, 32) * 0.1
        self.encoder_w2 = np.random.randn(32, latent_dim) * 0.1
        
        self.head_force = np.random.randn(latent_dim, 1) * 0.1
        self.head_dc = np.random.randn(latent_dim, 1) * 0.1
        self.head_delta = np.random.randn(latent_dim, 1) * 0.1
        self.head_tau = np.random.randn(latent_dim, 1) * 0.1
        self.head_uncertainty = np.random.randn(latent_dim, 1) * 0.1
    
    def encode(self, features: np.ndarray) -> np.ndarray:
        """Encode features to latent space"""
        h1 = np.tanh(features @ self.encoder_w1)
        latent = np.tanh(h1 @ self.encoder_w2)
        return latent
    
    def predict(self, latent: np.ndarray) -> Dict[str, float]:
        """Predict state coordinates from latent"""
        force = float(np.tanh(latent @ self.head_force).flatten()[0])
        dc_raw = latent @ self.head_dc
        dc = float(1 / (1 + np.exp(-dc_raw.flatten()[0])))
        delta = float(np.abs(latent @ self.head_delta).flatten()[0])
        tau = int(np.clip(np.abs(latent @ self.head_tau).flatten()[0] * 10, 0, 20))
        uncertainty = float(np.abs(latent @ self.head_uncertainty).flatten()[0])
        
        return {
            'force': force,
            'dc': dc,
            'delta': delta,
            'tau': tau,
            'uncertainty': uncertainty
        }


class MLEncoderV01(MLEncoderInterface):
    """
    ML Encoder v0.1 - First candidate encoder.
    
    Features:
    - Temporal autoencoder for state estimation
    - Uncertainty quantification (mandatory)
    - Rule-based fallback for τ
    
    Loss Functions (conceptual, not trained here):
    - L_state_consistency: Match rule-based state
    - L_temporal_smoothness: Minimize state jumps
    - L_uncertainty_calibration: Uncertainty predicts error
    """
    
    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self.history: List[Dict] = []
        self.model = TemporalAutoencoder(window_size=window_size)
        
        self.dc_hold_count = 0
        self.dc_hold_count_low = 0
        
        self.last_state: Optional[StateEstimate] = None
    
    @property
    def name(self) -> str:
        return "MLEncoderV01"
    
    def encode(self, features: Dict) -> StateEstimate:
        """Encode from pre-computed features"""
        feature_vec = self._features_to_vector(features)
        latent = self.model.encode(feature_vec)
        pred = self.model.predict(latent)
        
        return StateEstimate(
            force_hat=pred['force'],
            dc_hat=pred['dc'],
            delta_hat=pred['delta'],
            tau_hat=pred['tau'],
            uncertainty={
                'force_var': pred['uncertainty'],
                'dc_var': pred['uncertainty'],
                'delta_var': pred['uncertainty'],
                'tau_var': pred['uncertainty']
            }
        )
    
    def update(self, candle: Dict) -> StateEstimate:
        """Update with new candle and return state estimate"""
        self.history.append(candle)
        if len(self.history) > 100:
            self.history = self.history[-100:]
        
        rule_force = self._calc_force()
        rule_dc = self._calc_dc()
        rule_delta = self._calc_delta(candle)
        rule_tau = self._calc_tau(rule_dc)
        
        if len(self.history) >= self.window_size:
            features = self._build_features()
            ml_estimate = self.encode(features)
            
            blended_force = 0.7 * rule_force + 0.3 * ml_estimate.force_hat
            blended_dc = 0.8 * rule_dc + 0.2 * ml_estimate.dc_hat
            
            uncertainty = self._calc_uncertainty()
            
            state = StateEstimate(
                force_hat=blended_force,
                dc_hat=blended_dc,
                delta_hat=rule_delta,
                tau_hat=rule_tau,
                uncertainty={
                    'force_var': uncertainty,
                    'dc_var': uncertainty * 0.5,
                    'delta_var': uncertainty * 0.3,
                    'tau_var': 0.0
                }
            )
        else:
            state = StateEstimate(
                force_hat=rule_force,
                dc_hat=rule_dc,
                delta_hat=rule_delta,
                tau_hat=rule_tau,
                uncertainty={
                    'force_var': 1.0,
                    'dc_var': 0.5,
                    'delta_var': 0.3,
                    'tau_var': 0.0
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
    
    def _build_features(self) -> Dict:
        """Build feature dictionary from history"""
        recent = self.history[-self.window_size:]
        
        returns = []
        volumes = []
        channel_positions = []
        
        for i, c in enumerate(recent):
            if i > 0:
                ret = (c['close'] - recent[i-1]['close']) / recent[i-1]['close']
                returns.append(ret)
            
            rng = c['high'] - c['low']
            if rng > 0:
                pos = (c['close'] - c['low']) / rng
            else:
                pos = 0.5
            channel_positions.append(pos)
        
        return {
            'returns': returns,
            'channel_positions': channel_positions,
            'force_proxy': self._calc_force()
        }
    
    def _features_to_vector(self, features: Dict) -> np.ndarray:
        """Convert features dict to numpy vector"""
        vec = []
        
        returns = features.get('returns', [0] * 19)
        vec.extend(returns[:19] + [0] * (19 - len(returns)))
        
        positions = features.get('channel_positions', [0.5] * 20)
        vec.extend(positions[:20] + [0.5] * (20 - len(positions)))
        
        force = features.get('force_proxy', 0)
        vec.extend([force] * self.window_size)
        
        vec.extend([0] * (5 * self.window_size - len(vec)))
        
        return np.array(vec[:5 * self.window_size]).reshape(1, -1)
    
    def _calc_uncertainty(self) -> float:
        """Calculate uncertainty based on recent state variance"""
        if len(self.history) < 5:
            return 1.0
        
        recent = self.history[-5:]
        dcs = []
        for i, c in enumerate(recent):
            if i > 0:
                rng = max(h['high'] for h in recent) - min(h['low'] for h in recent)
                if rng > 0:
                    dc = (c['close'] - min(h['low'] for h in recent)) / rng
                    dcs.append(dc)
        
        if len(dcs) < 2:
            return 0.5
        
        return float(np.std(dcs))
    
    def _calc_force(self) -> float:
        """Calculate Force (rule-based)"""
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
        """Calculate DC (rule-based)"""
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
        """Calculate Delta (rule-based)"""
        rng = candle['high'] - candle['low']
        if rng <= 0:
            return 0.0
        body = abs(candle['close'] - candle['open'])
        return (body / rng) * rng
    
    def _calc_tau(self, dc: float) -> int:
        """Calculate τ (rule-based, never ML)"""
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
