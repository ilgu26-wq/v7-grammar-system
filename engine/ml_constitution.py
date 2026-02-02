"""
V7 4D Observation Engine - ML Constitution (Phase E)
ML Usage Rules & Validation

This module enforces the ML usage constraints established in Phase A-D.
Any ML encoder MUST pass these checks before deployment.

E-AXIOM-0: ML cannot access Bar1/DC=1/τ/ENTER decisions
E-1: No future prediction
E-2: Monotonicity preservation
E-3: Rule over ML (always)
E-4: Distribution preservation
E-5: Fail-safe (works without ML)
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum
import numpy as np


class ViolationType(Enum):
    AXIOM_0 = "AXIOM_0_VIOLATION"       # Accessed forbidden zone
    E1_PREDICTION = "E1_PREDICTION"      # Future prediction detected
    E2_MONOTONICITY = "E2_MONOTONICITY"  # State discontinuity
    E3_RULE_BYPASS = "E3_RULE_BYPASS"    # Attempted to bypass rules
    E4_DISTRIBUTION = "E4_DISTRIBUTION"  # Changed ENTER distribution
    E5_FAILSAFE = "E5_FAILSAFE"          # Doesn't work without ML


@dataclass
class ConstitutionCheck:
    """Result of constitution validation"""
    passed: bool
    violations: List[ViolationType]
    details: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        return {
            'passed': self.passed,
            'violations': [v.value for v in self.violations],
            'details': self.details
        }


class MLConstitution:
    """
    ML Constitution Enforcer
    
    All ML encoders must pass these checks:
    1. Cannot increase ENTER rate
    2. Cannot bypass rule gates
    3. Must preserve state continuity
    4. Must work when disabled
    """
    
    ENTER_TOLERANCE = 0.01       # Max 1% increase allowed
    WAIT_TOLERANCE = 0.02        # Max 2% change allowed
    OBSERVE_TOLERANCE = 0.02     # Max 2% change allowed
    CONTINUITY_THRESHOLD = 0.45  # From H-C1 (P99 = 0.45)
    
    def __init__(self):
        self.baseline_distribution = None
        self.violations_log: List[Dict] = []
    
    def set_baseline(self, wait_pct: float, observe_pct: float, 
                     enter_pct: float) -> None:
        """Set baseline distribution from Phase D (no ML)"""
        self.baseline_distribution = {
            'wait': wait_pct,
            'observe': observe_pct,
            'enter': enter_pct
        }
    
    def validate_encoder(self, encoder_name: str,
                        test_results: Dict) -> ConstitutionCheck:
        """
        Validate ML encoder against constitution.
        
        Args:
            encoder_name: Name of encoder being tested
            test_results: {
                'wait_pct': float,
                'observe_pct': float,
                'enter_pct': float,
                'dc_jumps': List[float],
                'force_jumps': List[float],
                'rule_bypasses': int,
                'uncertainty_correlation': float
            }
        
        Returns:
            ConstitutionCheck with pass/fail and violations
        """
        violations = []
        details = {'encoder': encoder_name}
        
        if self.baseline_distribution is None:
            return ConstitutionCheck(
                passed=False,
                violations=[ViolationType.E5_FAILSAFE],
                details={'error': 'No baseline set'}
            )
        
        enter_change = test_results['enter_pct'] - self.baseline_distribution['enter']
        if enter_change > self.ENTER_TOLERANCE:
            violations.append(ViolationType.E4_DISTRIBUTION)
            details['enter_increase'] = enter_change
        
        if test_results.get('rule_bypasses', 0) > 0:
            violations.append(ViolationType.E3_RULE_BYPASS)
            details['rule_bypasses'] = test_results['rule_bypasses']
        
        dc_jumps = test_results.get('dc_jumps', [])
        if dc_jumps:
            extreme_rate = sum(1 for j in dc_jumps if j > self.CONTINUITY_THRESHOLD) / len(dc_jumps)
            if extreme_rate > 0.05:  # More than 5% extreme jumps
                violations.append(ViolationType.E2_MONOTONICITY)
                details['extreme_jump_rate'] = extreme_rate
        
        wait_change = abs(test_results['wait_pct'] - self.baseline_distribution['wait'])
        observe_change = abs(test_results['observe_pct'] - self.baseline_distribution['observe'])
        
        if wait_change > self.WAIT_TOLERANCE or observe_change > self.OBSERVE_TOLERANCE:
            details['distribution_drift'] = {
                'wait_change': wait_change,
                'observe_change': observe_change
            }
        
        passed = len(violations) == 0
        
        check = ConstitutionCheck(
            passed=passed,
            violations=violations,
            details=details
        )
        
        self.violations_log.append({
            'encoder': encoder_name,
            'check': check.to_dict()
        })
        
        return check
    
    def check_output_validity(self, state_estimate: Dict) -> Tuple[bool, str]:
        """
        Check if a single state estimate is valid.
        
        Returns:
            (is_valid, reason)
        """
        if 'force_hat' not in state_estimate:
            return False, "Missing force_hat"
        
        if 'uncertainty' not in state_estimate:
            return False, "Missing uncertainty (E-2 violation)"
        
        dc = state_estimate.get('dc_hat', 0.5)
        if dc < 0 or dc > 1:
            return False, f"DC out of range: {dc}"
        
        tau = state_estimate.get('tau_hat', 0)
        if tau < 0:
            return False, f"Negative tau: {tau}"
        
        return True, "Valid"
    
    def get_allowed_loss_functions(self) -> List[str]:
        """
        Return list of allowed loss function types.
        
        Allowed: State estimation loss
        Forbidden: Future prediction loss
        """
        return [
            "MSE(state_t, state_hat_t)",         # Current state error
            "SmoothL1(state_t, state_hat_t)",    # Robust state error
            "ContrastiveLoss",                   # State similarity
            "ReconstructionLoss",                # Autoencoder
            "TemporalSmoothness",                # State continuity
            "UncertaintyCalibration"             # Uncertainty accuracy
        ]
    
    def get_forbidden_loss_functions(self) -> List[str]:
        """
        Return list of forbidden loss function types.
        """
        return [
            "CrossEntropy(direction)",           # Direction prediction
            "MSE(future_price)",                 # Price prediction
            "MSE(future_delta)",                 # Delta prediction
            "PnL",                               # Profit/loss based
            "SharpeRatio",                       # Performance based
            "RewardSignal",                      # RL reward
            "Any function using t+1, t+2, ..."   # Future data
        ]


class MLEncoderValidator:
    """
    Validates ML encoder outputs in real-time.
    
    Ensures encoder never violates constitution during runtime.
    """
    
    def __init__(self, constitution: MLConstitution):
        self.constitution = constitution
        self.last_state = None
        self.violation_count = 0
    
    def validate(self, state_estimate: Dict) -> Dict:
        """
        Validate and potentially correct state estimate.
        
        Returns validated state or fallback to safe values.
        """
        is_valid, reason = self.constitution.check_output_validity(state_estimate)
        
        if not is_valid:
            self.violation_count += 1
            return self._get_safe_fallback()
        
        if self.last_state is not None:
            dc_jump = abs(state_estimate['dc_hat'] - self.last_state['dc_hat'])
            if dc_jump > self.constitution.CONTINUITY_THRESHOLD * 2:
                smoothed_dc = (state_estimate['dc_hat'] + self.last_state['dc_hat']) / 2
                state_estimate['dc_hat'] = smoothed_dc
                state_estimate['_smoothed'] = True
        
        self.last_state = state_estimate.copy()
        return state_estimate
    
    def _get_safe_fallback(self) -> Dict:
        """Return safe fallback state when ML fails"""
        if self.last_state:
            return self.last_state.copy()
        
        return {
            'force_hat': 0.0,
            'dc_hat': 0.5,
            'delta_hat': 0.0,
            'tau_hat': 0,
            'uncertainty': {
                'force_var': 1.0,
                'dc_var': 1.0,
                'delta_var': 1.0,
                'tau_var': 1.0
            },
            '_fallback': True
        }
    
    def reset(self):
        """Reset validator state"""
        self.last_state = None
        self.violation_count = 0


PHASE_E_HYPOTHESES = {
    'H-E1': {
        'name': 'Non-Invasiveness',
        'criterion': 'ENTER rate change <= 1%',
        'test': 'Compare ENTER rate with/without ML'
    },
    'H-E2': {
        'name': 'Continuity Preservation', 
        'criterion': 'State discontinuity <= Phase C threshold',
        'test': 'Check DC/Force jump rates'
    },
    'H-E3': {
        'name': 'Uncertainty Awareness',
        'criterion': 'High uncertainty => lower ENTER rate',
        'test': 'Correlate uncertainty with ENTER frequency'
    },
    'H-E4': {
        'name': 'Rule Dominance',
        'criterion': 'Rule blocks are never overridden',
        'test': 'Count rule bypass attempts = 0'
    }
}
