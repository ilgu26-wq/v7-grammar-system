"""
V7 4D Observation Engine - Phase E Experiment Script
Official Phase E Audit System (E-SPEC v0.1)

Experiment Groups:
1. BASELINE: Phase D (no ML)
2. ML_ON: Phase D + ML Encoder
3. ML_OFF: ML loaded then disabled (hot-swap control)

All 5 hypotheses must PASS for Phase E completion.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Dict, List, Any
import json
import numpy as np
from datetime import datetime

from ml_encoder_interface import MLEncoderRegistry, RuleBasedEncoder
from ml_encoder_v01 import MLEncoderV01
from ml_encoder_v02 import MLEncoderV02
from v7_engine_d import V7EngineD
from ml_constitution import MLConstitution


class PhaseEExperiment:
    """
    Official Phase E Experiment Runner
    
    Fixed Conditions (Pre-Registered):
    - DC_THRESHOLD = 0.9 / 0.1
    - TAU_MIN = 5
    - DIR_THRESHOLD = 3
    - RULE LOGIC: No changes allowed
    """
    
    DC_THRESHOLD_HIGH = 0.9
    DC_THRESHOLD_LOW = 0.1
    TAU_MIN = 5
    DIR_THRESHOLD = 3
    
    ENTER_TOLERANCE = 0.01      # H-E1: <= 1%
    DIST_TOLERANCE = 0.02       # H-E2: <= 2%
    EXACT_TOLERANCE = 0.001     # H-E5: ~0%
    
    def __init__(self):
        self.results: Dict[str, Dict] = {}
        self.constitution = MLConstitution()
    
    def run_experiment(self, dataset: List[Dict], 
                      ml_encoder_class=None) -> Dict:
        """
        Run complete Phase E experiment.
        
        Args:
            dataset: List of candle dicts
            ml_encoder_class: ML encoder class to test
        
        Returns:
            Complete audit results
        """
        print("="*70)
        print("PHASE E EXPERIMENT")
        print("="*70)
        print(f"Dataset: {len(dataset)} candles")
        print(f"Encoder: {ml_encoder_class.__name__ if ml_encoder_class else 'None'}")
        print()
        
        print("Running BASELINE...")
        baseline = self._run_mode(dataset, "BASELINE", None)
        self.results["BASELINE"] = baseline
        print(f"  ENTER: {baseline['enter_pct']:.3f}% ({baseline['enter_count']})")
        
        self.constitution.set_baseline(
            baseline['wait_pct'],
            baseline['observe_pct'],
            baseline['enter_pct']
        )
        
        if ml_encoder_class:
            MLEncoderRegistry.register(ml_encoder_class)
            encoder_name = ml_encoder_class().name
            
            print(f"Running ML_ON ({encoder_name})...")
            ml_on = self._run_mode(dataset, "ML_ON", encoder_name)
            self.results["ML_ON"] = ml_on
            print(f"  ENTER: {ml_on['enter_pct']:.3f}% ({ml_on['enter_count']})")
            
            print("Running ML_OFF (control)...")
            ml_off = self._run_mode(dataset, "ML_OFF", encoder_name, disable=True)
            self.results["ML_OFF"] = ml_off
            print(f"  ENTER: {ml_off['enter_pct']:.3f}% ({ml_off['enter_count']})")
        
        audit = self._audit_hypotheses()
        
        return {
            'experiment_date': datetime.now().isoformat(),
            'dataset_size': len(dataset),
            'results': self.results,
            'audit': audit
        }
    
    def _run_mode(self, dataset: List[Dict], mode: str, 
                 encoder_name: str = None, disable: bool = False) -> Dict:
        """Run engine in specified mode"""
        if mode == "BASELINE" or encoder_name is None:
            engine = V7EngineD(encoder_name=None)
        else:
            engine = V7EngineD(encoder_name=encoder_name)
            if disable:
                engine.swap_encoder(None)
        
        stats = {'WAIT': 0, 'OBSERVE': 0, 'ENTER': 0, 'READY': 0, 'HOLD': 0, 'EXIT': 0}
        dc_jumps = []
        force_jumps = []
        uncertainties = []
        enter_uncertainties = []
        rule_blocks = 0
        last_dc = None
        last_force = None
        
        for candle in dataset:
            output = engine.process(candle)
            action = output.action['action']
            stats[action] = stats.get(action, 0) + 1
            
            dc = output.state['dc_hat']
            force = output.state['force_hat']
            unc = output.state.get('uncertainty', {}).get('dc_var', 0)
            
            uncertainties.append(unc)
            if action == 'ENTER':
                enter_uncertainties.append(unc)
            
            if last_dc is not None:
                dc_jumps.append(abs(dc - last_dc))
            if last_force is not None:
                force_jumps.append(abs(force - last_force))
            
            if output.validation['result'] == 'REJECT' or output.validation['result'] == 'PENDING':
                if action not in ['WAIT', 'OBSERVE']:
                    rule_blocks += 1
            
            last_dc = dc
            last_force = force
        
        total = len(dataset)
        extreme_dc_jumps = sum(1 for j in dc_jumps if j > 0.45) / len(dc_jumps) * 100 if dc_jumps else 0
        
        return {
            'mode': mode,
            'wait_pct': stats['WAIT'] / total * 100,
            'observe_pct': stats['OBSERVE'] / total * 100,
            'enter_pct': stats['ENTER'] / total * 100,
            'enter_count': stats['ENTER'],
            'extreme_dc_jump_rate': extreme_dc_jumps,
            'avg_uncertainty': np.mean(uncertainties) if uncertainties else 0,
            'avg_enter_uncertainty': np.mean(enter_uncertainties) if enter_uncertainties else 0,
            'rule_blocks_violated': rule_blocks
        }
    
    def _audit_hypotheses(self) -> Dict:
        """Audit all Phase E hypotheses"""
        baseline = self.results.get('BASELINE', {})
        ml_on = self.results.get('ML_ON', {})
        ml_off = self.results.get('ML_OFF', {})
        
        audit = {}
        
        if ml_on:
            enter_diff = ml_on['enter_pct'] - baseline['enter_pct']
            h_e1 = enter_diff <= self.ENTER_TOLERANCE * 100
            audit['H-E1'] = {
                'name': 'Non-Invasiveness',
                'passed': h_e1,
                'detail': f"ENTER change: {enter_diff:.3f}% (max: {self.ENTER_TOLERANCE*100}%)"
            }
        
        if ml_on:
            wait_diff = abs(ml_on['wait_pct'] - baseline['wait_pct'])
            observe_diff = abs(ml_on['observe_pct'] - baseline['observe_pct'])
            enter_increase = ml_on['enter_pct'] > baseline['enter_pct']
            
            h_e2 = wait_diff <= self.DIST_TOLERANCE * 100 and \
                   observe_diff <= self.DIST_TOLERANCE * 100 and \
                   not enter_increase
            
            audit['H-E2'] = {
                'name': 'Distribution Preservation',
                'passed': h_e2,
                'detail': f"WAIT diff: {wait_diff:.2f}%, OBSERVE diff: {observe_diff:.2f}%"
            }
        
        if ml_on:
            h_e3 = ml_on['rule_blocks_violated'] == 0
            audit['H-E3'] = {
                'name': 'Rule Dominance',
                'passed': h_e3,
                'detail': f"Rule violations: {ml_on['rule_blocks_violated']}"
            }
        
        if ml_on:
            h_e4 = ml_on['extreme_dc_jump_rate'] < 5.0
            audit['H-E4'] = {
                'name': 'Continuity Preservation',
                'passed': h_e4,
                'detail': f"Extreme DC jumps: {ml_on['extreme_dc_jump_rate']:.2f}%"
            }
        
        if ml_off:
            enter_exact = abs(ml_off['enter_pct'] - baseline['enter_pct']) < self.EXACT_TOLERANCE * 100
            wait_exact = abs(ml_off['wait_pct'] - baseline['wait_pct']) < self.EXACT_TOLERANCE * 100
            
            h_e5 = enter_exact and wait_exact
            audit['H-E5'] = {
                'name': 'Safe Failure',
                'passed': h_e5,
                'detail': f"ML-OFF matches BASELINE: {h_e5}"
            }
        
        all_passed = all(h.get('passed', False) for h in audit.values())
        audit['OVERALL'] = 'PASS' if all_passed else 'FAIL'
        
        return audit
    
    def generate_report(self) -> str:
        """Generate Phase E audit report"""
        lines = [
            "=" * 70,
            "PHASE E AUDIT REPORT",
            "=" * 70,
            ""
        ]
        
        for mode, result in self.results.items():
            lines.extend([
                f"{mode}:",
                f"  WAIT:    {result['wait_pct']:.1f}%",
                f"  OBSERVE: {result['observe_pct']:.1f}%",
                f"  ENTER:   {result['enter_pct']:.3f}% ({result['enter_count']})",
                ""
            ])
        
        lines.extend([
            "-" * 40,
            "HYPOTHESIS TESTS:",
            "-" * 40
        ])
        
        if hasattr(self, '_last_audit'):
            for h_id, h_result in self._last_audit.items():
                if h_id == 'OVERALL':
                    continue
                status = "PASS" if h_result['passed'] else "FAIL"
                lines.append(f"  {h_id}: {status} - {h_result['detail']}")
            
            lines.extend([
                "",
                f"OVERALL: {self._last_audit.get('OVERALL', 'N/A')}",
                ""
            ])
        
        return "\n".join(lines)


def run_phase_e():
    """Run Phase E experiment with MLEncoderV01"""
    import glob
    import pandas as pd
    
    files = glob.glob('../../attached_assets/chart_data_new/*.csv')
    all_rows = []
    
    for f in files:
        try:
            temp = pd.read_csv(f)
            temp.columns = [c.strip().lower() for c in temp.columns]
            if all(c in temp.columns for c in ['high', 'low', 'open', 'close']):
                for _, row in temp.iterrows():
                    all_rows.append({
                        'open': row['open'], 'high': row['high'],
                        'low': row['low'], 'close': row['close']
                    })
        except:
            pass
    
    if not all_rows:
        print("No data found")
        return
    
    experiment = PhaseEExperiment()
    result = experiment.run_experiment(all_rows, MLEncoderV02)
    
    experiment._last_audit = result['audit']
    print()
    print(experiment.generate_report())
    
    print("-" * 40)
    for h_id, h_result in result['audit'].items():
        if h_id == 'OVERALL':
            continue
        status = "PASS" if h_result['passed'] else "FAIL"
        print(f"{h_id}: {status} - {h_result['detail']}")
    
    print()
    print(f"OVERALL: {result['audit'].get('OVERALL', 'N/A')}")


if __name__ == "__main__":
    run_phase_e()
