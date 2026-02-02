"""
H-WD-01: Windmill Definition Test
=================================

가설 ID: H-WD-01
목적: "Windmill을 '세계가 강제한 독립 구조'로 정의했기 때문에
       PROMOTE=0 결과가 필연적으로 나왔는지 검증한다."

H0: Windmill 정의와 무관하게 World-Forced Windmill이 존재하지 않는다
H1: Windmill 정의를 완화하면 기존 DISCARD된 OBS가 살아난다
    → PROMOTE=0은 정의의 결과다
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import (
    load_signals,
    classify_storm_coordinate,
    estimate_tau,
    estimate_dir_count,
    WindmillState,
    simulate_outcome
)


# ============================================================
# OBSERVATION UNITS (동일하게 유지)
# ============================================================

def obs_a1_reference_cross(s: Dict) -> Optional[bool]:
    revisit = s.get('revisit_count', 0)
    if revisit is None:
        return None
    return revisit >= 2

def obs_b1_volatility_pattern(s: Dict) -> Optional[bool]:
    force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
    dc = s.get('dc_pre', 0.5)
    compressed_then_expanded = (dc <= 0.2 or dc >= 0.8) and force >= 1.5
    return compressed_then_expanded

def obs_c1_force_range_mismatch(s: Dict) -> Optional[bool]:
    force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
    dc = s.get('dc_pre', 0.5)
    high_force_mid_dc = force >= 1.5 and 0.3 <= dc <= 0.7
    return high_force_mid_dc

OBSERVATION_UNITS = {
    'OBS_A1': obs_a1_reference_cross,
    'OBS_B1': obs_b1_volatility_pattern,
    'OBS_C1': obs_c1_force_range_mismatch,
}


# ============================================================
# DEFINITION LEVELS
# ============================================================

def test_level_0(signals: List[Dict], obs_fn) -> Dict:
    """
    LEVEL 0 — 현재 정의 (Baseline)
    - Collapse Test >= 3/4
    - Loss diff >= 15pp
    """
    # World-forced test
    wf_result = _world_forced_test(signals, obs_fn, diff_threshold=0.15)
    
    # Collapse tests
    collapse_result = _collapse_tests(signals, obs_fn, min_survived=3)
    
    passed = wf_result['passed'] and collapse_result['passed']
    
    return {
        'level': 0,
        'description': 'World-Forced (strict)',
        'world_forced': wf_result,
        'collapse': collapse_result,
        'verdict': 'PROMOTE' if passed else 'DISCARD'
    }


def test_level_1(signals: List[Dict], obs_fn) -> Dict:
    """
    LEVEL 1 — 독립성 완화
    - Collapse Test >= 2/4
    - Loss diff >= 15pp (유지)
    """
    wf_result = _world_forced_test(signals, obs_fn, diff_threshold=0.15)
    collapse_result = _collapse_tests(signals, obs_fn, min_survived=2)
    
    passed = wf_result['passed'] and collapse_result['passed']
    
    return {
        'level': 1,
        'description': 'Independence relaxed (2/4)',
        'world_forced': wf_result,
        'collapse': collapse_result,
        'verdict': 'PROMOTE' if passed else 'DISCARD'
    }


def test_level_2(signals: List[Dict], obs_fn) -> Dict:
    """
    LEVEL 2 — Invariance 완화
    - Collapse Test >= 1/4
    - Loss diff >= 10pp
    """
    wf_result = _world_forced_test(signals, obs_fn, diff_threshold=0.10)
    collapse_result = _collapse_tests(signals, obs_fn, min_survived=1)
    
    passed = wf_result['passed'] and collapse_result['passed']
    
    return {
        'level': 2,
        'description': 'Invariance relaxed (1/4, 10pp)',
        'world_forced': wf_result,
        'collapse': collapse_result,
        'verdict': 'PROMOTE' if passed else 'DISCARD'
    }


def test_level_3(signals: List[Dict], obs_fn) -> Dict:
    """
    LEVEL 3 — World-Forced 포기 (Operational)
    - Collapse Test 없음
    - Loss diff >= 5pp
    - Storm-IN + Bar1만 유지
    """
    wf_result = _world_forced_test(signals, obs_fn, diff_threshold=0.05)
    
    passed = wf_result['passed']
    
    return {
        'level': 3,
        'description': 'Operational (5pp, no collapse)',
        'world_forced': wf_result,
        'collapse': None,
        'verdict': 'PROMOTE' if passed else 'DISCARD'
    }


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _world_forced_test(signals: List[Dict], obs_fn, diff_threshold: float) -> Dict:
    """World-Forced Test with configurable threshold"""
    pass_losses = []
    reject_losses = []
    
    for s in signals:
        if classify_storm_coordinate(s) != "STORM_IN":
            continue
        
        obs_result = obs_fn(s)
        if obs_result is None:
            continue
        
        _, is_loss = simulate_outcome(s, WindmillState.ON)
        
        if obs_result:
            pass_losses.append(is_loss)
        else:
            reject_losses.append(is_loss)
    
    if not pass_losses or not reject_losses:
        return {
            'pass_loss': 0,
            'reject_loss': 0,
            'diff_pp': 0,
            'n_pass': len(pass_losses),
            'n_reject': len(reject_losses),
            'passed': False,
            'reason': 'insufficient_data'
        }
    
    pass_rate = sum(pass_losses) / len(pass_losses)
    reject_rate = sum(reject_losses) / len(reject_losses)
    diff = reject_rate - pass_rate
    
    return {
        'pass_loss': pass_rate,
        'reject_loss': reject_rate,
        'diff_pp': diff * 100,
        'n_pass': len(pass_losses),
        'n_reject': len(reject_losses),
        'passed': diff >= diff_threshold,
        'threshold': diff_threshold * 100
    }


def _collapse_tests(signals: List[Dict], obs_fn, min_survived: int) -> Dict:
    """Collapse tests with configurable minimum"""
    results = {}
    survived_count = 0
    
    # C1: Force 무시
    c1 = _single_collapse(signals, obs_fn, 'force')
    results['C1_force'] = c1
    if c1['survived']:
        survived_count += 1
    
    # C2: τ 무시
    c2 = _single_collapse(signals, obs_fn, 'tau')
    results['C2_tau'] = c2
    if c2['survived']:
        survived_count += 1
    
    # C3: Frame 무시
    c3 = _single_collapse(signals, obs_fn, 'frame')
    results['C3_frame'] = c3
    if c3['survived']:
        survived_count += 1
    
    # C4: VOL 무시
    c4 = _single_collapse(signals, obs_fn, 'vol')
    results['C4_vol'] = c4
    if c4['survived']:
        survived_count += 1
    
    results['survived_count'] = survived_count
    results['min_required'] = min_survived
    results['passed'] = survived_count >= min_survived
    
    return results


def _single_collapse(signals: List[Dict], obs_fn, collapse_type: str) -> Dict:
    """Single collapse test"""
    if collapse_type == 'force':
        test_signals = [s for s in signals 
                        if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.0]
    elif collapse_type == 'tau':
        test_signals = signals  # All signals, ignore tau
    elif collapse_type == 'frame':
        test_signals = signals  # All signals, ignore frame
    elif collapse_type == 'vol':
        # Test both regimes
        low = [s for s in signals 
               if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) < 1.5]
        high = [s for s in signals 
                if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.5]
        
        low_result = _direction_test(low, obs_fn)
        high_result = _direction_test(high, obs_fn)
        
        return {
            'low_force': low_result,
            'high_force': high_result,
            'survived': low_result['direction'] > 0 and high_result['direction'] > 0
        }
    else:
        test_signals = signals
    
    return _direction_test(test_signals, obs_fn)


def _direction_test(signals: List[Dict], obs_fn) -> Dict:
    """Test if direction is maintained"""
    pass_losses = []
    reject_losses = []
    
    for s in signals:
        obs_result = obs_fn(s)
        if obs_result is None:
            continue
        
        _, is_loss = simulate_outcome(s, WindmillState.ON)
        
        if obs_result:
            pass_losses.append(is_loss)
        else:
            reject_losses.append(is_loss)
    
    if not pass_losses or not reject_losses:
        return {'direction': 0, 'survived': False}
    
    pass_rate = sum(pass_losses) / len(pass_losses)
    reject_rate = sum(reject_losses) / len(reject_losses)
    diff = reject_rate - pass_rate
    
    return {
        'pass_loss': pass_rate,
        'reject_loss': reject_rate,
        'diff_pp': diff * 100,
        'direction': 1 if diff > 0 else -1,
        'survived': diff >= 0.05
    }


# ============================================================
# MAIN EXECUTION
# ============================================================

def run_definition_test():
    """Run H-WD-01: Windmill Definition Test"""
    print("="*70)
    print("H-WD-01: WINDMILL DEFINITION TEST")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nH0: Windmill 정의와 무관하게 World-Forced가 없다")
    print("H1: 정의 완화 시 DISCARD된 OBS가 살아난다")
    print("-"*70)
    
    signals = load_signals()
    print(f"\nTotal signals: {len(signals)}")
    
    qualified = [s for s in signals 
                 if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.3]
    print(f"Force-qualified: {len(qualified)}")
    
    all_results = {}
    
    for obs_id, obs_fn in OBSERVATION_UNITS.items():
        print(f"\n{'='*70}")
        print(f"OBS: {obs_id}")
        print("="*70)
        
        obs_result = {'obs_id': obs_id, 'levels': {}}
        
        # Test all levels
        for level, test_fn in enumerate([test_level_0, test_level_1, 
                                          test_level_2, test_level_3]):
            result = test_fn(qualified, obs_fn)
            obs_result['levels'][f'L{level}'] = result
            
            print(f"\nL{level} ({result['description']}):")
            print(f"  World-Forced: {result['world_forced'].get('diff_pp', 0):.1f}pp")
            if result['collapse']:
                print(f"  Collapse: {result['collapse'].get('survived_count', 0)}/{result['collapse'].get('min_required', 0)}")
            print(f"  → {result['verdict']}")
        
        all_results[obs_id] = obs_result
    
    # Summary Matrix
    print("\n" + "="*70)
    print("DECISION MATRIX")
    print("="*70)
    
    print("\n| OBS     | L0 | L1 | L2 | L3 |")
    print("|---------|----|----|----|----|")
    
    h1_evidence = False
    
    for obs_id, obs_result in all_results.items():
        row = f"| {obs_id} |"
        for level in ['L0', 'L1', 'L2', 'L3']:
            verdict = obs_result['levels'][level]['verdict']
            symbol = "✅" if verdict == 'PROMOTE' else "❌"
            row += f" {symbol} |"
            
            # Check if any level > 0 has PROMOTE
            if level != 'L0' and verdict == 'PROMOTE':
                h1_evidence = True
        
        print(row)
    
    # Final Verdict
    print("\n" + "="*70)
    print("FINAL VERDICT")
    print("="*70)
    
    if h1_evidence:
        verdict = "H1 ACCEPTED"
        interpretation = """
정의 완화 시 DISCARD된 OBS가 살아났다.
→ PROMOTE=0은 정의의 결과였다.
→ Windmill 정의가 결과를 강제했음이 증명됨.
"""
    else:
        verdict = "H0 NOT REJECTED"
        interpretation = """
정의를 완화해도 PROMOTE가 발생하지 않았다.
→ 현재 데이터에는 World-Forced Windmill이 없다.
→ 또는 OBS 정의 자체가 세계와 맞지 않는다.
"""
    
    print(f"\nVerdict: {verdict}")
    print(interpretation)
    
    # Save
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'H_WD_01',
        'hypothesis': 'Windmill Definition Test',
        'results': all_results,
        'verdict': verdict,
        'h1_evidence': h1_evidence
    }
    
    output_path = 'v7-grammar-system/analysis/windmill/h_wd_01_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_definition_test()
