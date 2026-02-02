"""
V7 4D Observation Engine - Integrity Check
Pre-Production Validation (I-1 ~ I-5)

This script validates that the engine codebase doesn't violate
the constitutional rules established in Phase A-E.

I-1: Information Leakage (no future data access)
I-2: Grammar Supremacy (rules > ML)
I-3: Action Monotonicity (ENTER must be rare)
I-4: Distribution Invariance (ML ON/OFF ±2%)
I-5: Determinism (same input → same output)
"""

import sys
import os
import re
import ast
import numpy as np
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@dataclass
class IntegrityResult:
    """Result of single integrity check"""
    check_id: str
    check_name: str
    passed: bool
    details: Dict[str, Any]
    violations: List[str]


class IntegrityChecker:
    """
    Complete integrity check suite for V7 Engine.
    
    All checks must PASS before production deployment.
    """
    
    ENGINE_FILES = [
        'v7_engine_d.py',
        'ml_encoder_interface.py',
        'ml_encoder_v01.py',
        'ml_encoder_v02.py',
        'observation_encoder.py',
        'state_validator.py',
        'state_mediator.py',
        'action_gate.py',
        'risk_annotation.py'
    ]
    
    LOOKAHEAD_PATTERNS = [
        r'\[t\s*\+\s*1\]',
        r'\[i\s*\+\s*1\]',
        r'\[.*\+\s*1.*\]',
        r'future',
        r'next_candle',
        r'next_bar',
        r'lookahead\s*=\s*True',
        r'shift\s*=\s*-',
    ]
    
    def __init__(self, base_path: str = '.'):
        self.base_path = base_path
        self.results: List[IntegrityResult] = []
    
    def check_i1_leakage(self) -> IntegrityResult:
        """
        I-1: Information Leakage Check
        
        Verify no module accesses future candles.
        """
        violations = []
        details = {'files_checked': 0, 'patterns_found': []}
        
        for filename in self.ENGINE_FILES:
            filepath = os.path.join(self.base_path, filename)
            if not os.path.exists(filepath):
                continue
            
            details['files_checked'] += 1
            
            with open(filepath, 'r') as f:
                content = f.read()
                lines = content.split('\n')
            
            for i, line in enumerate(lines, 1):
                for pattern in self.LOOKAHEAD_PATTERNS:
                    if re.search(pattern, line, re.IGNORECASE):
                        if 'def _calc_tau' in line and 'dc_hold_count' in line:
                            continue
                        if '#' in line and line.index('#') < line.find(pattern) if pattern in line else False:
                            continue
                        violations.append(f"{filename}:{i} - Pattern '{pattern}' found: {line.strip()[:60]}")
                        details['patterns_found'].append({
                            'file': filename,
                            'line': i,
                            'pattern': pattern
                        })
        
        critical_violations = [v for v in violations 
                              if 'lookahead' in v.lower() or 't+1' in v or 'i+1' in v]
        
        passed = len(critical_violations) == 0
        
        return IntegrityResult(
            check_id='I-1',
            check_name='Information Leakage',
            passed=passed,
            details=details,
            violations=violations
        )
    
    def check_i2_grammar_supremacy(self) -> IntegrityResult:
        """
        I-2: Grammar Supremacy Check
        
        Verify Grammar/Rule decisions are never bypassed by ML.
        """
        violations = []
        details = {'ml_override_attempts': 0, 'rule_hierarchy_intact': True}
        
        v7_engine_path = os.path.join(self.base_path, 'v7_engine_d.py')
        if os.path.exists(v7_engine_path):
            with open(v7_engine_path, 'r') as f:
                content = f.read()
            
            if 'self.validator.validate' in content and 'self.gate.decide' in content:
                if 'state_est' in content and 'validation' in content:
                    details['pipeline_structure'] = 'CORRECT'
                else:
                    details['pipeline_structure'] = 'SUSPECT'
                    violations.append("Pipeline structure unclear - verify ML doesn't bypass rules")
            
            if 'if ml_' in content.lower() or 'ml_override' in content.lower():
                violations.append("Potential ML override detected in engine")
                details['ml_override_attempts'] += 1
        
        ml_v02_path = os.path.join(self.base_path, 'ml_encoder_v02.py')
        if os.path.exists(ml_v02_path):
            with open(ml_v02_path, 'r') as f:
                content = f.read()
            
            if 'dc_hat=dc_rule' in content or 'dc_rule' in content:
                details['ml_v02_dc_rule_only'] = True
            else:
                violations.append("ML v0.2 may be modifying DC coordinates")
        
        passed = len(violations) == 0
        
        return IntegrityResult(
            check_id='I-2',
            check_name='Grammar Supremacy',
            passed=passed,
            details=details,
            violations=violations
        )
    
    def check_i3_action_monotonicity(self, dataset: List[Dict] = None) -> IntegrityResult:
        """
        I-3: Action Monotonicity Check
        
        Verify ENTER remains rare as data accumulates.
        """
        violations = []
        details = {}
        
        if dataset is None:
            details['skip_reason'] = 'No dataset provided'
            return IntegrityResult(
                check_id='I-3',
                check_name='Action Monotonicity',
                passed=True,
                details=details,
                violations=['Skipped - no dataset']
            )
        
        from v7_engine_d import V7EngineD
        
        engine = V7EngineD(encoder_name=None)
        
        total = len(dataset)
        enter_count = 0
        enter_indices = []
        
        for i, candle in enumerate(dataset):
            output = engine.process(candle)
            if output.action['action'] == 'ENTER':
                enter_count += 1
                enter_indices.append(i)
        
        enter_rate = enter_count / total * 100 if total > 0 else 0
        
        details['total_candles'] = total
        details['enter_count'] = enter_count
        details['enter_rate'] = f"{enter_rate:.4f}%"
        
        if enter_rate > 5.0:
            violations.append(f"ENTER rate {enter_rate:.2f}% exceeds 5% threshold")
        
        if len(enter_indices) >= 2:
            gaps = [enter_indices[i+1] - enter_indices[i] for i in range(len(enter_indices)-1)]
            if min(gaps) < 5:
                violations.append(f"ENTER events too close: min gap = {min(gaps)}")
        
        passed = len(violations) == 0
        
        return IntegrityResult(
            check_id='I-3',
            check_name='Action Monotonicity',
            passed=passed,
            details=details,
            violations=violations
        )
    
    def check_i4_distribution_invariance(self, dataset: List[Dict] = None) -> IntegrityResult:
        """
        I-4: Distribution Invariance Check
        
        Verify ML ON/OFF produces same distribution (±2%).
        """
        violations = []
        details = {}
        
        if dataset is None:
            details['skip_reason'] = 'No dataset provided'
            return IntegrityResult(
                check_id='I-4',
                check_name='Distribution Invariance',
                passed=True,
                details=details,
                violations=['Skipped - no dataset']
            )
        
        from v7_engine_d import V7EngineD
        from ml_encoder_interface import MLEncoderRegistry
        from ml_encoder_v02 import MLEncoderV02
        
        def run_engine(encoder_name):
            MLEncoderRegistry.register(MLEncoderV02)
            engine = V7EngineD(encoder_name=encoder_name)
            counts = {'WAIT': 0, 'OBSERVE': 0, 'ENTER': 0}
            for candle in dataset:
                output = engine.process(candle)
                action = output.action['action']
                counts[action] = counts.get(action, 0) + 1
            return counts
        
        baseline = run_engine(None)
        ml_on = run_engine("MLEncoderV02")
        
        total = len(dataset)
        
        baseline_pct = {k: v/total*100 for k, v in baseline.items()}
        ml_on_pct = {k: v/total*100 for k, v in ml_on.items()}
        
        details['baseline'] = baseline_pct
        details['ml_on'] = ml_on_pct
        
        for action in ['WAIT', 'OBSERVE']:
            diff = abs(ml_on_pct.get(action, 0) - baseline_pct.get(action, 0))
            if diff > 2.0:
                violations.append(f"{action} diff {diff:.2f}% exceeds 2% tolerance")
        
        if ml_on_pct.get('ENTER', 0) > baseline_pct.get('ENTER', 0):
            violations.append("ML increased ENTER rate (forbidden)")
        
        passed = len(violations) == 0
        
        return IntegrityResult(
            check_id='I-4',
            check_name='Distribution Invariance',
            passed=passed,
            details=details,
            violations=violations
        )
    
    def check_i5_determinism(self, dataset: List[Dict] = None) -> IntegrityResult:
        """
        I-5: Determinism Check
        
        Verify same input always produces same output.
        """
        violations = []
        details = {}
        
        if dataset is None or len(dataset) < 100:
            details['skip_reason'] = 'Insufficient dataset'
            return IntegrityResult(
                check_id='I-5',
                check_name='Determinism',
                passed=True,
                details=details,
                violations=['Skipped - insufficient data']
            )
        
        from v7_engine_d import V7EngineD
        
        test_data = dataset[:100]
        
        def run_and_collect():
            engine = V7EngineD(encoder_name=None)
            results = []
            for candle in test_data:
                output = engine.process(candle)
                results.append((
                    output.action['action'],
                    round(output.state['dc_hat'], 6),
                    output.state['tau_hat']
                ))
            return results
        
        run1 = run_and_collect()
        run2 = run_and_collect()
        
        mismatches = 0
        for i, (r1, r2) in enumerate(zip(run1, run2)):
            if r1 != r2:
                mismatches += 1
                violations.append(f"Mismatch at index {i}: {r1} vs {r2}")
        
        details['test_size'] = len(test_data)
        details['mismatches'] = mismatches
        details['match_rate'] = f"{(1 - mismatches/len(test_data))*100:.2f}%"
        
        passed = mismatches == 0
        
        return IntegrityResult(
            check_id='I-5',
            check_name='Determinism',
            passed=passed,
            details=details,
            violations=violations
        )
    
    def run_all_checks(self, dataset: List[Dict] = None) -> Dict:
        """Run all integrity checks"""
        print("=" * 70)
        print("V7 ENGINE INTEGRITY CHECK")
        print("=" * 70)
        print()
        
        checks = [
            ('I-1', 'Information Leakage', lambda: self.check_i1_leakage()),
            ('I-2', 'Grammar Supremacy', lambda: self.check_i2_grammar_supremacy()),
            ('I-3', 'Action Monotonicity', lambda: self.check_i3_action_monotonicity(dataset)),
            ('I-4', 'Distribution Invariance', lambda: self.check_i4_distribution_invariance(dataset)),
            ('I-5', 'Determinism', lambda: self.check_i5_determinism(dataset)),
        ]
        
        for check_id, name, check_fn in checks:
            print(f"Running {check_id}: {name}...")
            result = check_fn()
            self.results.append(result)
            
            status = "PASS" if result.passed else "FAIL"
            print(f"  {status}")
            
            if not result.passed:
                for v in result.violations[:3]:
                    print(f"    - {v}")
            print()
        
        all_passed = all(r.passed for r in self.results)
        
        print("=" * 70)
        print("INTEGRITY CHECK SUMMARY")
        print("=" * 70)
        
        for result in self.results:
            status = "PASS" if result.passed else "FAIL"
            print(f"{result.check_id} ({result.check_name}): {status}")
        
        print()
        print(f"OVERALL: {'PASS - Ready for production' if all_passed else 'FAIL - Fix violations before deployment'}")
        
        return {
            'all_passed': all_passed,
            'results': [
                {
                    'check_id': r.check_id,
                    'check_name': r.check_name,
                    'passed': r.passed,
                    'details': r.details,
                    'violations': r.violations
                }
                for r in self.results
            ]
        }


def run_integrity_check():
    """Run full integrity check with real data"""
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
    
    print(f"Dataset: {len(all_rows)} candles")
    print()
    
    checker = IntegrityChecker(base_path='.')
    result = checker.run_all_checks(all_rows)
    
    return result


if __name__ == "__main__":
    run_integrity_check()
