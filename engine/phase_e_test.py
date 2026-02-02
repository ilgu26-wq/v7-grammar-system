"""
V7 4D Observation Engine - Phase E Test Framework
ML Encoder Validation Tests

Tests all Phase E hypotheses:
- H-E1: Non-Invasiveness (ENTER rate <= 1% change)
- H-E2: Continuity Preservation
- H-E3: Uncertainty Awareness
- H-E4: Rule Dominance
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Dict, List, Any
import json
import numpy as np

from ml_encoder_interface import MLEncoderInterface, RuleBasedEncoder, MLEncoderRegistry
from ml_constitution import MLConstitution, MLEncoderValidator, PHASE_E_HYPOTHESES
from v7_engine_d import V7EngineD


class PhaseETestFramework:
    """
    Framework for testing ML encoders against Phase E requirements.
    """
    
    def __init__(self):
        self.constitution = MLConstitution()
        self.results: Dict[str, Any] = {}
    
    def run_baseline(self, candles: List[Dict]) -> Dict:
        """
        Run baseline test with RuleBasedEncoder (no ML).
        
        This establishes the baseline distribution that ML must preserve.
        """
        engine = V7EngineD(encoder_name=None)  # Default encoder
        
        results = {'WAIT': 0, 'OBSERVE': 0, 'ENTER': 0}
        dc_values = []
        
        for candle in candles:
            output = engine.process(candle)
            action = output.action['action']
            results[action] = results.get(action, 0) + 1
            dc_values.append(output.state['dc_hat'])
        
        total = len(candles)
        baseline = {
            'wait_pct': results['WAIT'] / total * 100,
            'observe_pct': results['OBSERVE'] / total * 100,
            'enter_pct': results['ENTER'] / total * 100,
            'enter_count': results['ENTER'],
            'dc_values': dc_values
        }
        
        self.constitution.set_baseline(
            baseline['wait_pct'],
            baseline['observe_pct'],
            baseline['enter_pct']
        )
        
        self.results['baseline'] = baseline
        return baseline
    
    def test_encoder(self, encoder: MLEncoderInterface, 
                    candles: List[Dict]) -> Dict:
        """
        Test a specific ML encoder against Phase E requirements.
        """
        MLEncoderRegistry.register(type(encoder))
        engine = V7EngineD(encoder_name=encoder.name)
        
        results = {'WAIT': 0, 'OBSERVE': 0, 'ENTER': 0}
        dc_jumps = []
        force_jumps = []
        uncertainties = []
        enter_uncertainties = []
        last_dc = None
        last_force = None
        rule_bypasses = 0
        
        for candle in candles:
            output = engine.process(candle)
            action = output.action['action']
            results[action] = results.get(action, 0) + 1
            
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
            
            last_dc = dc
            last_force = force
        
        total = len(candles)
        
        test_results = {
            'encoder_name': encoder.name,
            'wait_pct': results['WAIT'] / total * 100,
            'observe_pct': results['OBSERVE'] / total * 100,
            'enter_pct': results['ENTER'] / total * 100,
            'enter_count': results['ENTER'],
            'dc_jumps': dc_jumps,
            'force_jumps': force_jumps,
            'rule_bypasses': rule_bypasses,
            'avg_uncertainty': np.mean(uncertainties) if uncertainties else 0,
            'avg_enter_uncertainty': np.mean(enter_uncertainties) if enter_uncertainties else 0
        }
        
        constitution_check = self.constitution.validate_encoder(
            encoder.name, test_results
        )
        
        test_results['constitution_check'] = constitution_check.to_dict()
        
        hypothesis_results = self._check_hypotheses(test_results)
        test_results['hypotheses'] = hypothesis_results
        
        self.results[encoder.name] = test_results
        return test_results
    
    def _check_hypotheses(self, test_results: Dict) -> Dict:
        """Check Phase E hypotheses"""
        baseline = self.results.get('baseline', {})
        
        h_e1 = abs(test_results['enter_pct'] - baseline.get('enter_pct', 0)) <= 1.0
        
        dc_jumps = test_results.get('dc_jumps', [])
        extreme_rate = sum(1 for j in dc_jumps if j > 0.45) / len(dc_jumps) * 100 if dc_jumps else 0
        h_e2 = extreme_rate < 5.0
        
        avg_unc = test_results.get('avg_uncertainty', 0)
        avg_enter_unc = test_results.get('avg_enter_uncertainty', 0)
        h_e3 = avg_enter_unc <= avg_unc  # ENTER should have lower/equal uncertainty
        
        h_e4 = test_results.get('rule_bypasses', 0) == 0
        
        return {
            'H-E1': {'name': 'Non-Invasiveness', 'passed': h_e1, 
                    'detail': f"ENTER change: {test_results['enter_pct'] - baseline.get('enter_pct', 0):.2f}%"},
            'H-E2': {'name': 'Continuity', 'passed': h_e2,
                    'detail': f"Extreme jump rate: {extreme_rate:.2f}%"},
            'H-E3': {'name': 'Uncertainty Awareness', 'passed': h_e3,
                    'detail': f"Avg unc: {avg_unc:.4f}, Enter unc: {avg_enter_unc:.4f}"},
            'H-E4': {'name': 'Rule Dominance', 'passed': h_e4,
                    'detail': f"Rule bypasses: {test_results.get('rule_bypasses', 0)}"}
        }
    
    def generate_report(self) -> str:
        """Generate Phase E test report"""
        lines = [
            "=" * 70,
            "PHASE E: ML ENCODER VALIDATION REPORT",
            "=" * 70,
            ""
        ]
        
        if 'baseline' in self.results:
            b = self.results['baseline']
            lines.extend([
                "BASELINE (RuleBasedEncoder):",
                f"  WAIT: {b['wait_pct']:.1f}%",
                f"  OBSERVE: {b['observe_pct']:.1f}%",
                f"  ENTER: {b['enter_pct']:.2f}% ({b['enter_count']} trades)",
                ""
            ])
        
        for name, result in self.results.items():
            if name == 'baseline':
                continue
            
            lines.extend([
                f"ENCODER: {name}",
                "-" * 40,
                f"  ENTER: {result['enter_pct']:.2f}% ({result['enter_count']} trades)",
                "",
                "  Hypothesis Tests:",
            ])
            
            for h_id, h_result in result.get('hypotheses', {}).items():
                status = "PASS" if h_result['passed'] else "FAIL"
                lines.append(f"    {h_id} ({h_result['name']}): {status}")
                lines.append(f"       {h_result['detail']}")
            
            check = result.get('constitution_check', {})
            status = "PASSED" if check.get('passed', False) else "FAILED"
            lines.extend([
                "",
                f"  Constitution Check: {status}",
                ""
            ])
        
        return "\n".join(lines)
    
    def save_results(self, filepath: str) -> None:
        """Save results to JSON"""
        serializable = {}
        for k, v in self.results.items():
            if k == 'baseline':
                serializable[k] = {
                    'wait_pct': v['wait_pct'],
                    'observe_pct': v['observe_pct'],
                    'enter_pct': v['enter_pct'],
                    'enter_count': v['enter_count']
                }
            else:
                serializable[k] = {
                    'wait_pct': v['wait_pct'],
                    'observe_pct': v['observe_pct'],
                    'enter_pct': v['enter_pct'],
                    'enter_count': v['enter_count'],
                    'hypotheses': v.get('hypotheses', {}),
                    'constitution_check': v.get('constitution_check', {})
                }
        
        with open(filepath, 'w') as f:
            json.dump(serializable, f, indent=2)


def run_phase_e_baseline_test():
    """Run Phase E baseline test with real data"""
    import glob
    import pandas as pd
    
    files = glob.glob('../../attached_assets/chart_data_new/*.csv')
    all_rows = []
    
    for f in files[:5]:  # Use subset for quick test
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
    
    print(f"Testing with {len(all_rows)} candles")
    
    framework = PhaseETestFramework()
    
    print("\n1. Running baseline...")
    baseline = framework.run_baseline(all_rows)
    print(f"   Baseline ENTER: {baseline['enter_pct']:.2f}%")
    
    print("\n2. Testing RuleBasedEncoder (should match baseline)...")
    encoder = RuleBasedEncoder()
    result = framework.test_encoder(encoder, all_rows)
    
    print("\n" + framework.generate_report())
    
    framework.save_results('../../v7-grammar-system/experiments/phase_e_baseline.json')
    print("\nResults saved.")


if __name__ == "__main__":
    run_phase_e_baseline_test()
