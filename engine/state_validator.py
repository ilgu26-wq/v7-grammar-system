"""
V7 4D Observation Engine - State Validator
NON-ML ZONE: Axiom Layer (Frozen Rules)

Validates if state has crossed irreversible boundaries.
NO prediction. NO optimization. Pure observation checkpoint.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
from observation_encoder import State4D


class ValidationResult(Enum):
    REJECT = "REJECT"           # State not complete
    PENDING = "PENDING"         # State forming, wait
    VALIDATED = "VALIDATED"     # State complete, proceed


@dataclass
class ValidationOutput:
    result: ValidationResult
    reason: str
    dc_status: str
    tau_status: str
    
    def to_dict(self):
        return {
            'result': self.result.value,
            'reason': self.reason,
            'dc_status': self.dc_status,
            'tau_status': self.tau_status
        }


class StateValidator:
    """
    Validates state completeness based on frozen axioms.
    
    Axioms (Immutable):
    1. DC=1 is the event horizon (irreversible)
    2. τ >= τ_min required for energy release
    3. Bar1 is unpredictable (50% adverse/favorable)
    """
    
    DC_THRESHOLD_HIGH = 0.9
    DC_THRESHOLD_LOW = 0.1
    # Phase B Frozen: τ ≥ 5 is SURVIVAL condition (not performance parameter)
    TAU_MIN_HIGH = 5      # Minimum hold for DC high
    TAU_MIN_LOW = 5       # Minimum hold for DC low (FROZEN - was 4, Phase B requires 5)
    TAU_OPTIMAL_HIGH = 7  # Optimal for maximum Delta
    TAU_OPTIMAL_LOW = 7   # Optimal for LOW (aligned with HIGH)
    
    def validate(self, state: State4D, direction: str = "HIGH") -> ValidationOutput:
        """
        Validate if state is complete.
        
        Args:
            state: Current 4D state
            direction: "HIGH" or "LOW"
        
        Returns:
            ValidationOutput with result and reasons
        """
        dc_status = self._check_dc(state, direction)
        tau_status = self._check_tau(state, direction)
        
        if dc_status == "NOT_AT_BOUNDARY":
            return ValidationOutput(
                result=ValidationResult.REJECT,
                reason="DC not at boundary - event not started",
                dc_status=dc_status,
                tau_status=tau_status
            )
        
        if tau_status == "INSUFFICIENT":
            return ValidationOutput(
                result=ValidationResult.PENDING,
                reason=f"τ insufficient - accumulation in progress",
                dc_status=dc_status,
                tau_status=tau_status
            )
        
        if tau_status == "MINIMAL":
            return ValidationOutput(
                result=ValidationResult.PENDING,
                reason="τ minimal - wait for optimal accumulation",
                dc_status=dc_status,
                tau_status=tau_status
            )
        
        return ValidationOutput(
            result=ValidationResult.VALIDATED,
            reason="State complete - τ optimal",
            dc_status=dc_status,
            tau_status=tau_status
        )
    
    def _check_dc(self, state: State4D, direction: str) -> str:
        """Check DC boundary status"""
        if direction == "HIGH":
            if state.dc >= self.DC_THRESHOLD_HIGH:
                return "AT_HIGH_BOUNDARY"
            return "NOT_AT_BOUNDARY"
        else:
            if state.dc <= self.DC_THRESHOLD_LOW:
                return "AT_LOW_BOUNDARY"
            return "NOT_AT_BOUNDARY"
    
    def _check_tau(self, state: State4D, direction: str) -> str:
        """Check τ accumulation status"""
        if direction == "HIGH":
            tau_min = self.TAU_MIN_HIGH
            tau_opt = self.TAU_OPTIMAL_HIGH
        else:
            tau_min = self.TAU_MIN_LOW
            tau_opt = self.TAU_OPTIMAL_LOW
        
        if state.tau < tau_min:
            return "INSUFFICIENT"
        elif state.tau < tau_opt:
            return "MINIMAL"
        else:
            return "OPTIMAL"
    
    def get_expected_delta_multiplier(self, state: State4D, direction: str) -> float:
        """
        Get expected Delta multiplier based on τ.
        From Phase A validation:
        - τ <= 2: baseline (1.0x)
        - τ >= 7: 1.4x (HIGH) or varies (LOW)
        """
        if direction == "HIGH":
            if state.tau <= 2:
                return 1.0
            elif state.tau <= 4:
                return 0.92  # 11.67/12.75
            elif state.tau <= 6:
                return 0.91  # 11.55/12.75
            else:
                return 1.40  # 17.81/12.75
        else:
            if state.tau <= 2:
                return 1.0
            elif state.tau <= 4:
                return 1.08  # 16.29/15.09
            elif state.tau <= 6:
                return 1.20  # 18.16/15.09
            else:
                return 0.84  # 12.69/15.09 (decreases at high τ for LOW)
