"""
V7 4D Observation Engine - Action Gate
NON-ML ZONE: Final Decision Layer

Determines action based on validated, mediated state.
Philosophy: "Fail fast and cheap" (틀리면 바로 드러나서 안 죽는 시스템)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
from observation_encoder import State4D
from state_validator import ValidationOutput, ValidationResult
from state_mediator import MediatorOutput, Phase


class Action(Enum):
    WAIT = "WAIT"           # Do nothing
    OBSERVE = "OBSERVE"     # Active monitoring
    READY = "READY"         # Prepare for entry
    ENTER = "ENTER"         # Limited entry allowed
    HOLD = "HOLD"           # Maintain position
    EXIT = "EXIT"           # Exit immediately


@dataclass
class ActionOutput:
    action: Action
    reason: str
    risk_level: str         # "LOW", "MEDIUM", "HIGH"
    position_size: float    # 0.0 - 1.0
    stop_condition: str
    
    def to_dict(self):
        return {
            'action': self.action.value,
            'reason': self.reason,
            'risk_level': self.risk_level,
            'position_size': self.position_size,
            'stop_condition': self.stop_condition
        }


class ActionGate:
    """
    Final action decision gate.
    
    Core Principle: 
    "When can I wait?" not "When should I enter?"
    
    Action Rules (Frozen):
    - DC < threshold: WAIT (event not started)
    - DC at boundary, τ insufficient: OBSERVE
    - Vortex: WAIT (energy redistributing)
    - Committed + τ optimal: ENTER (limited)
    - Hold failure: EXIT immediately
    """
    
    def __init__(self):
        self.in_position = False
        self.entry_state: Optional[State4D] = None
        self.bars_in_position = 0
        self.max_adverse = 0.0
    
    def decide(self, state: State4D, validation: ValidationOutput, 
              mediation: MediatorOutput, direction: str) -> ActionOutput:
        """
        Decide action based on all inputs.
        
        Args:
            state: Current 4D state
            validation: From StateValidator
            mediation: From StateMediator
            direction: "HIGH" or "LOW"
        
        Returns:
            ActionOutput with action and reasoning
        """
        if self.in_position:
            return self._handle_position(state, mediation)
        
        if validation.result == ValidationResult.REJECT:
            return ActionOutput(
                action=Action.WAIT,
                reason=validation.reason,
                risk_level="LOW",
                position_size=0.0,
                stop_condition="N/A"
            )
        
        if validation.result == ValidationResult.PENDING:
            return ActionOutput(
                action=Action.OBSERVE,
                reason=f"Accumulating: {validation.tau_status}",
                risk_level="LOW",
                position_size=0.0,
                stop_condition="DC boundary break"
            )
        
        if mediation.in_vortex:
            return ActionOutput(
                action=Action.WAIT,
                reason="In vortex - energy redistributing",
                risk_level="HIGH",
                position_size=0.0,
                stop_condition="Vortex exit"
            )
        
        if mediation.phase == Phase.COMMITTED:
            position_size = self._calc_position_size(state, mediation)
            return ActionOutput(
                action=Action.READY if position_size < 0.5 else Action.ENTER,
                reason=f"Direction committed, τ={state.tau}",
                risk_level="MEDIUM" if position_size >= 0.5 else "HIGH",
                position_size=position_size,
                stop_condition="Bar1 adverse or direction change"
            )
        
        return ActionOutput(
            action=Action.OBSERVE,
            reason="State forming",
            risk_level="LOW",
            position_size=0.0,
            stop_condition="Phase change"
        )
    
    def _handle_position(self, state: State4D, 
                        mediation: MediatorOutput) -> ActionOutput:
        """Handle existing position"""
        self.bars_in_position += 1
        
        if self.entry_state:
            current_pnl = state.delta - self.entry_state.delta
            if current_pnl < 0:
                self.max_adverse = min(self.max_adverse, current_pnl)
        
        if mediation.in_vortex:
            return ActionOutput(
                action=Action.EXIT,
                reason="Entered vortex - exit to preserve capital",
                risk_level="HIGH",
                position_size=0.0,
                stop_condition="Immediate"
            )
        
        if not mediation.direction_committed and self.bars_in_position >= 3:
            return ActionOutput(
                action=Action.EXIT,
                reason="Direction lost after 3 bars",
                risk_level="HIGH",
                position_size=0.0,
                stop_condition="Immediate"
            )
        
        if mediation.phase == Phase.RELEASE:
            return ActionOutput(
                action=Action.HOLD,
                reason="Delta releasing - hold for target",
                risk_level="MEDIUM",
                position_size=1.0,
                stop_condition="Release complete or reversal"
            )
        
        return ActionOutput(
            action=Action.HOLD,
            reason=f"Position held {self.bars_in_position} bars",
            risk_level="MEDIUM",
            position_size=1.0,
            stop_condition="Direction change or max bars"
        )
    
    def _calc_position_size(self, state: State4D, 
                           mediation: MediatorOutput) -> float:
        """
        Calculate position size based on state quality.
        Higher τ = higher size (validated in Phase A)
        """
        base = 0.3
        
        tau_bonus = min(0.4, state.tau * 0.05)
        
        confidence_bonus = mediation.confidence * 0.3
        
        return min(1.0, base + tau_bonus + confidence_bonus)
    
    def enter_position(self, state: State4D):
        """Record position entry"""
        self.in_position = True
        self.entry_state = state
        self.bars_in_position = 0
        self.max_adverse = 0.0
    
    def exit_position(self):
        """Record position exit"""
        self.in_position = False
        self.entry_state = None
        self.bars_in_position = 0
    
    def reset(self):
        """Reset gate state"""
        self.exit_position()
