"""
V7 4D Observation Engine - Risk Annotation Layer
μ (Cumulative Delta) - Logging/Analysis Only

μ was REJECTED as state dimension (H-MEM test).
Correct usage: Risk diagnostic, NOT decision input.

μ = "How violent was the accumulation process?"
High μ = High MAE risk (validated in Phase C)
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum


class RiskLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class RiskAnnotation:
    """Risk annotation for logging/analysis only"""
    mu: float                    # Cumulative |Delta| during DC hold
    mu_percentile: float         # Relative to historical distribution
    risk_level: RiskLevel
    note: str
    
    def to_dict(self) -> Dict:
        return {
            'mu': self.mu,
            'mu_percentile': self.mu_percentile,
            'risk_level': self.risk_level.value,
            'note': self.note
        }


class RiskAnnotationLayer:
    """
    Risk annotation layer - POST-DECISION only.
    
    IMPORTANT: This layer does NOT affect decisions.
    It only provides context for logging and analysis.
    
    Usage:
    - Log ENTER events with risk context
    - Post-hoc analysis of trade outcomes
    - Research: "Did high-μ trades have higher MAE?"
    """
    
    MU_P30 = 34.75   # From H-MEM test
    MU_P70 = 77.00   # From H-MEM test
    
    def __init__(self):
        self.delta_accumulator = 0.0
        self.in_dc_zone = False
        self.mu_history: List[float] = []
    
    def update(self, dc: float, delta: float) -> None:
        """Update μ accumulator based on DC zone"""
        currently_in_zone = (dc >= 0.9 or dc <= 0.1)
        
        if currently_in_zone:
            self.delta_accumulator += abs(delta)
            self.in_dc_zone = True
        else:
            if self.in_dc_zone and self.delta_accumulator > 0:
                self.mu_history.append(self.delta_accumulator)
                if len(self.mu_history) > 1000:
                    self.mu_history = self.mu_history[-1000:]
            self.delta_accumulator = 0.0
            self.in_dc_zone = False
    
    def get_current_mu(self) -> float:
        """Get current μ value"""
        return self.delta_accumulator
    
    def annotate(self) -> RiskAnnotation:
        """
        Generate risk annotation for current state.
        
        Note: This is for LOGGING only.
        DO NOT use for decision making.
        """
        mu = self.delta_accumulator
        
        if mu <= self.MU_P30:
            level = RiskLevel.LOW
            pct = 30.0
            note = "Quiet accumulation - lower MAE expected"
        elif mu <= self.MU_P70:
            level = RiskLevel.MEDIUM
            pct = 50.0
            note = "Normal accumulation"
        else:
            level = RiskLevel.HIGH
            pct = 85.0
            note = "Violent accumulation - higher MAE expected"
        
        return RiskAnnotation(
            mu=mu,
            mu_percentile=pct,
            risk_level=level,
            note=note
        )
    
    def reset(self) -> None:
        """Reset accumulator"""
        self.delta_accumulator = 0.0
        self.in_dc_zone = False
