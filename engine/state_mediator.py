"""
V7 4D Observation Engine - State Mediator
NON-ML ZONE: Post-Event State Classification

Determines current phase after state validation.
NO prediction. Only observation of completed states.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
from observation_encoder import State4D


class Phase(Enum):
    ACCUMULATION = "ACCUMULATION"   # τ building
    VORTEX = "VORTEX"               # Energy redistribution zone
    COMMITTED = "COMMITTED"         # Direction confirmed (dir >= 3)
    RELEASE = "RELEASE"             # Delta discharge


@dataclass
class MediatorOutput:
    phase: Phase
    in_vortex: bool
    direction_committed: bool
    force_direction: str      # "BULL" or "BEAR"
    confidence: float         # 0-1
    
    def to_dict(self):
        return {
            'phase': self.phase.value,
            'in_vortex': self.in_vortex,
            'direction_committed': self.direction_committed,
            'force_direction': self.force_direction,
            'confidence': self.confidence
        }


class StateMediator:
    """
    Mediates between validated state and action.
    
    Key Concepts:
    - Vortex: Energy redistribution zone (wait, don't act)
    - Committed: Direction confirmed post-Bar1
    - dir >= 3: "Directional commitment" (Delta increases, not stabilization)
    """
    
    DIR_THRESHOLD = 3           # Bars for direction commitment
    VORTEX_FORCE_THRESHOLD = 0.3  # Force magnitude for vortex detection
    
    def __init__(self):
        self.direction_bars = 0
        self.last_direction = None
        self.force_history: List[float] = []
    
    def evaluate(self, state: State4D, direction: str) -> MediatorOutput:
        """
        Evaluate current phase based on state.
        
        Args:
            state: Validated 4D state
            direction: "HIGH" or "LOW"
        
        Returns:
            MediatorOutput with phase classification
        """
        self.force_history.append(state.force)
        if len(self.force_history) > 20:
            self.force_history = self.force_history[-20:]
        
        in_vortex = self._detect_vortex(state)
        direction_committed = self._check_direction_commitment(state, direction)
        force_dir = "BULL" if state.force > 0 else "BEAR"
        
        phase = self._determine_phase(state, in_vortex, direction_committed)
        confidence = self._calc_confidence(state, phase)
        
        return MediatorOutput(
            phase=phase,
            in_vortex=in_vortex,
            direction_committed=direction_committed,
            force_direction=force_dir,
            confidence=confidence
        )
    
    def _detect_vortex(self, state: State4D) -> bool:
        """
        Detect if in vortex (energy redistribution zone).
        Vortex = high uncertainty, force oscillating
        """
        if len(self.force_history) < 5:
            return False
        
        recent = self.force_history[-5:]
        sign_changes = sum(1 for i in range(1, len(recent)) 
                         if recent[i] * recent[i-1] < 0)
        
        if sign_changes >= 2:
            return True
        
        if state.force_var > self.VORTEX_FORCE_THRESHOLD:
            return True
        
        return False
    
    def _check_direction_commitment(self, state: State4D, direction: str) -> bool:
        """
        Check if direction is committed (dir >= 3).
        
        Note: dir >= 3 is "directional commitment" not "stabilization"
        Delta INCREASES after commitment (validated in Phase A)
        """
        current_dir = "BULL" if state.force > 0 else "BEAR"
        
        if current_dir == self.last_direction:
            self.direction_bars += 1
        else:
            self.direction_bars = 1
            self.last_direction = current_dir
        
        expected_dir = "BULL" if direction == "LOW" else "BEAR"
        if current_dir == expected_dir and self.direction_bars >= self.DIR_THRESHOLD:
            return True
        
        return False
    
    def _determine_phase(self, state: State4D, in_vortex: bool, 
                        committed: bool) -> Phase:
        """Determine current phase"""
        if state.tau < 3:
            return Phase.ACCUMULATION
        
        if in_vortex:
            return Phase.VORTEX
        
        if committed:
            return Phase.COMMITTED
        
        if state.delta > state.force * 2:
            return Phase.RELEASE
        
        return Phase.ACCUMULATION
    
    def _calc_confidence(self, state: State4D, phase: Phase) -> float:
        """Calculate confidence based on phase and uncertainty"""
        base = 0.5
        
        if phase == Phase.COMMITTED:
            base = 0.8
        elif phase == Phase.VORTEX:
            base = 0.3
        elif phase == Phase.RELEASE:
            base = 0.7
        
        uncertainty_penalty = min(0.3, state.force_var * 0.5 + state.dc_var * 0.5)
        
        tau_bonus = min(0.2, state.tau * 0.02)
        
        return max(0.1, min(1.0, base - uncertainty_penalty + tau_bonus))
    
    def reset(self):
        """Reset mediator state"""
        self.direction_bars = 0
        self.last_direction = None
        self.force_history = []
