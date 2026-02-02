"""
V7 4D Observation Engine - Phase D Production Architecture
ML-Slot Reserved Design

Architecture:
[ Raw Data ] → [ Feature Builder ] → [ ML Encoder (SLOT) ] 
→ [ State Validator ] → [ State Mediator ] → [ Action Gate ]

ML is ONLY in Observation Encoder - all other layers are frozen rules.
System works identically with or without ML (RuleBasedEncoder is default).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import json
from datetime import datetime

from ml_encoder_interface import (
    MLEncoderInterface, 
    MLEncoderRegistry, 
    StateEstimate,
    RuleBasedEncoder
)
from state_validator import StateValidator, ValidationResult
from state_mediator import StateMediator, Phase
from action_gate import ActionGate, Action
from risk_annotation import RiskAnnotationLayer, RiskAnnotation
from phase_f_hardening import ColdStartGuard, HardenedThresholds, EngineState


@dataclass
class EngineOutputD:
    """Phase D engine output with risk annotation"""
    timestamp: str
    state: Dict
    validation: Dict
    mediation: Dict
    action: Dict
    direction: str
    risk_annotation: Dict      # μ-based risk (logging only)
    encoder_name: str          # Which ML encoder was used
    
    def to_dict(self):
        return asdict(self)
    
    def to_json(self):
        return json.dumps(self.to_dict(), indent=2)


class V7EngineD:
    """
    V7 4D Observation Engine - Phase D Architecture
    
    Key Design Principles:
    1. ML is replaceable (plug-in sensor, not decision maker)
    2. Rules are frozen (validated in Phase A-C)
    3. μ is annotation only (H-MEM rejected as dimension)
    4. τ ≥ 5 is survival condition (Phase B validated)
    
    Frozen Parameters (DO NOT MODIFY):
    - DC_THRESHOLD = 0.9 / 0.1
    - TAU_MIN = 5
    - DIR_THRESHOLD = 3
    """
    
    VERSION = "D.1.0"
    
    DC_THRESHOLD_HIGH = 0.9
    DC_THRESHOLD_LOW = 0.1
    TAU_MIN = 5                  # Phase B validated
    DIR_THRESHOLD = 3            # Directional commitment
    
    def __init__(self, encoder_name: str = None):
        """
        Initialize engine with specified encoder.
        
        Args:
            encoder_name: Name of ML encoder to use.
                          None = use default (RuleBasedEncoder)
        """
        self.encoder: MLEncoderInterface = MLEncoderRegistry.get(encoder_name)
        self.validator = StateValidator()
        self.mediator = StateMediator()
        self.gate = ActionGate()
        self.risk_layer = RiskAnnotationLayer()
        
        self.cold_start = ColdStartGuard(warm_up_bars=20)
        self.thresholds = HardenedThresholds()
        
        self.candle_count = 0
        self.history: List[Dict] = []
    
    def process(self, candle: Dict) -> EngineOutputD:
        """
        Process single candle through full pipeline.
        
        Pipeline:
        1. Feature Builder (implicit in encoder)
        2. ML Encoder (replaceable slot)
        3. State Validator (frozen rules)
        4. State Mediator (frozen rules)
        5. Action Gate (frozen rules)
        6. Risk Annotation (logging only)
        """
        self.candle_count += 1
        engine_state = self.cold_start.update()
        
        state_est = self.encoder.update(candle)
        
        self.risk_layer.update(state_est.dc_hat, state_est.delta_hat)
        
        # 3. Direction determination using hardened thresholds (Decimal)
        direction = "HIGH" if state_est.dc_hat >= 0.5 else "LOW"
        if self.thresholds.dc_at_high(state_est.dc_hat):
            direction = "HIGH"
        elif self.thresholds.dc_at_low(state_est.dc_hat):
            direction = "LOW"
        
        from observation_encoder import State4D
        state_4d = State4D(
            force=state_est.force_hat,
            dc=state_est.dc_hat,
            delta=state_est.delta_hat,
            tau=state_est.tau_hat,
            force_var=state_est.uncertainty.get('force_var', 0.0),
            dc_var=state_est.uncertainty.get('dc_var', 0.0)
        )
        
        validation = self.validator.validate(state_4d, direction)
        
        mediation = self.mediator.evaluate(state_4d, direction)
        
        # Cold start protection: force WAIT if not ready
        if self.cold_start.must_wait():
            from action_gate import ActionOutput
            action = ActionOutput(
                action=Action.WAIT,
                reason=self.cold_start.get_reason(),
                risk_level="LOW",
                position_size=0.0,
                stop_condition="N/A"
            )
        else:
            action = self.gate.decide(state_4d, validation, mediation, direction)
        
        if action.action == Action.ENTER:
            self.gate.enter_position(state_4d)
        elif action.action == Action.EXIT:
            self.gate.exit_position()
        
        risk = self.risk_layer.annotate()
        
        output = EngineOutputD(
            timestamp=candle.get('close_time_utc', candle.get('timestamp', self.candle_count)),
            state=state_est.to_dict(),
            validation=validation.to_dict(),
            mediation=mediation.to_dict(),
            action=action.to_dict(),
            direction=direction,
            risk_annotation=risk.to_dict(),
            encoder_name=self.encoder.name
        )
        
        self.history.append(output.to_dict())
        if len(self.history) > 100:
            self.history = self.history[-100:]
        
        return output
    
    def swap_encoder(self, encoder_name: str) -> None:
        """
        Hot-swap ML encoder.
        
        This allows changing the observation model without restarting.
        System safety is maintained - rules are frozen.
        """
        self.encoder = MLEncoderRegistry.get(encoder_name)
        self.encoder.reset()
    
    def get_stats(self) -> Dict:
        """Get engine statistics"""
        return {
            "version": self.VERSION,
            "encoder": self.encoder.name,
            "candles_processed": self.candle_count,
            "in_position": self.gate.in_position,
            "frozen_params": {
                "DC_THRESHOLD": (self.DC_THRESHOLD_LOW, self.DC_THRESHOLD_HIGH),
                "TAU_MIN": self.TAU_MIN,
                "DIR_THRESHOLD": self.DIR_THRESHOLD
            }
        }
    
    def reset(self) -> None:
        """Reset all engine state"""
        self.encoder.reset()
        self.mediator.reset()
        self.gate.reset()
        self.risk_layer.reset()
        self.cold_start.reset()
        self.candle_count = 0
        self.history = []


def test_engine_d():
    """Test Phase D engine"""
    engine = V7EngineD()
    
    sample_candles = [
        {'open': 100, 'high': 102, 'low': 99, 'close': 101},
        {'open': 101, 'high': 103, 'low': 100, 'close': 102},
        {'open': 102, 'high': 105, 'low': 101, 'close': 104},
        {'open': 104, 'high': 106, 'low': 103, 'close': 105},
        {'open': 105, 'high': 107, 'low': 104, 'close': 106},
    ]
    
    print("V7 Engine Phase D Test")
    print("=" * 60)
    print(f"Version: {engine.VERSION}")
    print(f"Encoder: {engine.encoder.name}")
    print()
    
    for i, candle in enumerate(sample_candles):
        output = engine.process(candle)
        print(f"Candle {i+1}: Action={output.action['action']}, "
              f"τ={output.state['tau_hat']}, "
              f"Risk={output.risk_annotation['risk_level']}")
    
    print()
    print("Stats:", engine.get_stats())


if __name__ == "__main__":
    test_engine_d()
