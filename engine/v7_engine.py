"""
V7 4D Observation Engine - Main Engine
Complete Pipeline: Raw Data → 4D State → Validation → Mediation → Action

Core Philosophy: "틀리면 바로 드러나서 안 죽는 시스템"
(Fail fast and cheap - errors become visible immediately)

State Space: (Force, DC, Delta, τ)
ML Usage: ONLY in Observation Encoder for coordinate estimation
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import json
from datetime import datetime

from observation_encoder import ObservationEncoder, State4D
from state_validator import StateValidator, ValidationResult
from state_mediator import StateMediator, Phase
from action_gate import ActionGate, Action


@dataclass
class EngineOutput:
    """Complete engine output for each candle"""
    timestamp: str
    state: Dict
    validation: Dict
    mediation: Dict
    action: Dict
    direction: str
    
    def to_dict(self):
        return asdict(self)
    
    def to_json(self):
        return json.dumps(self.to_dict(), indent=2)


class V7ObservationEngine:
    """
    V7 4D Observation Engine
    
    Pipeline:
    Raw Data → Observation Encoder (ML) → State Validator (Rule) 
    → State Mediator (Rule) → Action Gate (Rule) → Output
    
    Axioms (Immutable):
    1. Bar1 is unpredictable (50% adverse/favorable)
    2. DC=1 is the event horizon
    3. τ (hold time) determines Delta magnitude
    4. RT FAIL: Direction prediction is structurally impossible
    """
    
    def __init__(self):
        self.encoder = ObservationEncoder()
        self.validator = StateValidator()
        self.mediator = StateMediator()
        self.gate = ActionGate()
        
        self.candle_count = 0
        self.action_history: List[Dict] = []
        self.state_history: List[State4D] = []
    
    def process(self, candle: Dict) -> EngineOutput:
        """
        Process single candle through full pipeline.
        
        Args:
            candle: {open, high, low, close, volume (optional)}
        
        Returns:
            EngineOutput with complete analysis
        """
        self.candle_count += 1
        
        state = self.encoder.update(candle)
        self.state_history.append(state)
        if len(self.state_history) > 100:
            self.state_history = self.state_history[-100:]
        
        direction = self.encoder.get_direction()
        if direction == "NEUTRAL":
            direction = "HIGH"
        
        validation = self.validator.validate(state, direction)
        
        mediation = self.mediator.evaluate(state, direction)
        
        action = self.gate.decide(state, validation, mediation, direction)
        
        if action.action == Action.ENTER:
            self.gate.enter_position(state)
        elif action.action == Action.EXIT:
            self.gate.exit_position()
        
        output = EngineOutput(
            timestamp=datetime.now().isoformat(),
            state=state.to_dict(),
            validation=validation.to_dict(),
            mediation=mediation.to_dict(),
            action=action.to_dict(),
            direction=direction
        )
        
        self.action_history.append(output.to_dict())
        if len(self.action_history) > 100:
            self.action_history = self.action_history[-100:]
        
        return output
    
    def process_batch(self, candles: List[Dict]) -> List[EngineOutput]:
        """Process multiple candles"""
        return [self.process(c) for c in candles]
    
    def get_stats(self) -> Dict:
        """Get engine statistics"""
        if not self.action_history:
            return {"candles_processed": 0}
        
        action_counts = {}
        for h in self.action_history:
            act = h['action']['action']
            action_counts[act] = action_counts.get(act, 0) + 1
        
        avg_tau = sum(s.tau for s in self.state_history) / len(self.state_history) if self.state_history else 0
        
        return {
            "candles_processed": self.candle_count,
            "action_distribution": action_counts,
            "avg_tau": avg_tau,
            "in_position": self.gate.in_position
        }
    
    def reset(self):
        """Reset all engine state"""
        self.encoder.reset()
        self.mediator.reset()
        self.gate.reset()
        self.candle_count = 0
        self.action_history = []
        self.state_history = []


def test_engine():
    """Quick test of engine with sample data"""
    engine = V7ObservationEngine()
    
    sample_candles = [
        {'open': 100, 'high': 102, 'low': 99, 'close': 101},
        {'open': 101, 'high': 103, 'low': 100, 'close': 102},
        {'open': 102, 'high': 105, 'low': 101, 'close': 104},
        {'open': 104, 'high': 106, 'low': 103, 'close': 105},
        {'open': 105, 'high': 107, 'low': 104, 'close': 106},
        {'open': 106, 'high': 108, 'low': 105, 'close': 107},
        {'open': 107, 'high': 109, 'low': 106, 'close': 108},
        {'open': 108, 'high': 110, 'low': 107, 'close': 109},
    ]
    
    print("V7 4D Observation Engine Test")
    print("="*60)
    
    for i, candle in enumerate(sample_candles):
        output = engine.process(candle)
        print(f"\nCandle {i+1}: {candle}")
        print(f"  State: Force={output.state['force']:.2f}, DC={output.state['dc']:.2f}, τ={output.state['tau']}")
        print(f"  Validation: {output.validation['result']}")
        print(f"  Phase: {output.mediation['phase']}")
        print(f"  Action: {output.action['action']} - {output.action['reason']}")
    
    print("\n" + "="*60)
    print("Stats:", engine.get_stats())


if __name__ == "__main__":
    test_engine()
