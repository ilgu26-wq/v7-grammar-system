"""
V7 4D Observation Engine - ML Encoder Interface
★ ML SLOT: Replaceable observation encoder

This defines the interface for ML-based state estimation.
ML is ONLY allowed here - all other layers are rule-based and frozen.

Constraints:
- Input: 2D observable features
- Output: 4D state coordinates (Force, DC, Delta, τ)
- NO prediction of future states
- NO direction guessing
- ONLY current state estimation
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
import numpy as np


@dataclass
class StateEstimate:
    """Output interface for ML encoder (FIXED, do not modify)"""
    force_hat: float      # Estimated Force
    dc_hat: float         # Estimated DC (0-1)
    delta_hat: float      # Estimated Delta
    tau_hat: int          # Estimated τ (hold time)
    
    uncertainty: Dict[str, float] = None  # Optional uncertainty estimates
    
    def __post_init__(self):
        if self.uncertainty is None:
            self.uncertainty = {
                'force_var': 0.0,
                'dc_var': 0.0,
                'delta_var': 0.0,
                'tau_var': 0.0
            }
    
    def to_dict(self) -> Dict:
        return {
            'force_hat': self.force_hat,
            'dc_hat': self.dc_hat,
            'delta_hat': self.delta_hat,
            'tau_hat': self.tau_hat,
            'uncertainty': self.uncertainty
        }


class MLEncoderInterface(ABC):
    """
    Abstract interface for ML-based observation encoders.
    
    Any ML model must implement this interface.
    The model is replaceable - system safety does not depend on it.
    
    Allowed:
    - CNN, Transformer, GNN, etc.
    - Any architecture for coordinate estimation
    
    Forbidden:
    - Prediction of future states
    - Direction probability output
    - TP/SL estimation
    """
    
    @abstractmethod
    def encode(self, features: Dict[str, Any]) -> StateEstimate:
        """
        Encode 2D features into 4D state estimate.
        
        Args:
            features: Dictionary containing observable features
                - price: current price
                - ohlc_history: list of recent OHLC dicts
                - volume: current volume (optional)
                - channel_pct: channel percentile
                - ratio: buyer/seller ratio
                - etc.
        
        Returns:
            StateEstimate with 4D coordinates
        """
        pass
    
    @abstractmethod
    def update(self, candle: Dict) -> StateEstimate:
        """
        Update internal state and return new estimate.
        
        Args:
            candle: {open, high, low, close, volume (optional)}
        
        Returns:
            StateEstimate with updated 4D coordinates
        """
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """Reset encoder state"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Model identifier"""
        pass


class RuleBasedEncoder(MLEncoderInterface):
    """
    Default rule-based encoder (non-ML baseline).
    
    This is the fallback encoder when ML is not available.
    System works identically with or without ML.
    """
    
    def __init__(self, lookback: int = 20, force_window: int = 5):
        self.lookback = lookback
        self.force_window = force_window
        self.history: List[Dict] = []
        self.dc_hold_count = 0
        self.dc_hold_count_low = 0
    
    @property
    def name(self) -> str:
        return "RuleBasedEncoder_v1"
    
    def encode(self, features: Dict[str, Any]) -> StateEstimate:
        """Encode from pre-computed features"""
        return StateEstimate(
            force_hat=features.get('force', 0.0),
            dc_hat=features.get('dc', 0.5),
            delta_hat=features.get('delta', 0.0),
            tau_hat=features.get('tau', 0)
        )
    
    def update(self, candle: Dict) -> StateEstimate:
        """Update from new candle"""
        self.history.append(candle)
        if len(self.history) > 100:
            self.history = self.history[-100:]
        
        force = self._calc_force()
        dc = self._calc_dc()
        delta = self._calc_delta(candle)
        tau = self._calc_tau(dc)
        
        return StateEstimate(
            force_hat=force,
            dc_hat=dc,
            delta_hat=delta,
            tau_hat=tau
        )
    
    def reset(self) -> None:
        self.history = []
        self.dc_hold_count = 0
        self.dc_hold_count_low = 0
    
    def _calc_force(self) -> float:
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
        rng = candle['high'] - candle['low']
        if rng <= 0:
            return 0.0
        body = abs(candle['close'] - candle['open'])
        return (body / rng) * rng
    
    def _calc_tau(self, dc: float) -> int:
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


class MLEncoderRegistry:
    """
    Registry for ML encoder implementations.
    
    Allows hot-swapping of ML models without system restart.
    """
    
    _encoders: Dict[str, type] = {}
    _default: str = "RuleBasedEncoder_v1"
    
    @classmethod
    def register(cls, encoder_class: type) -> None:
        """Register an encoder implementation"""
        instance = encoder_class()
        cls._encoders[instance.name] = encoder_class
    
    @classmethod
    def get(cls, name: str = None) -> MLEncoderInterface:
        """Get encoder by name, or default if not specified"""
        if name is None:
            name = cls._default
        
        if name not in cls._encoders:
            return RuleBasedEncoder()
        
        return cls._encoders[name]()
    
    @classmethod
    def list_encoders(cls) -> List[str]:
        """List all registered encoders"""
        return list(cls._encoders.keys())
    
    @classmethod
    def set_default(cls, name: str) -> None:
        """Set default encoder"""
        if name in cls._encoders:
            cls._default = name


MLEncoderRegistry.register(RuleBasedEncoder)
