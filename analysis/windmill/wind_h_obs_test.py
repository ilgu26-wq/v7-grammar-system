"""
WIND-H Stage 0-2: Observation Unit Tests
=========================================

의미 없는 관측 사실만 정의하고
World-Forced + Collapse 테스트 실행

OBS-A1: Reference level 반복 교차
OBS-B1: Volatility 감소→증가 패턴
OBS-C1: Force-Range 불일치
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
# STAGE 0: Observation Units (의미 없는 관측 사실)
# ============================================================

def obs_a1_reference_cross(s: Dict) -> Optional[bool]:
    """
    OBS_A1: 같은 reference level을 K bar 이내에 2회 이상 교차했는가?
    
    Proxy: revisit_count (재방문 횟수)
    """
    revisit = s.get('revisit_count', 0)
    if revisit is None:
        return None
    return revisit >= 2


def obs_b1_volatility_pattern(s: Dict) -> Optional[bool]:
    """
    OBS_B1: volatility가 감소 → 증가 패턴을 보였는가?
    
    Proxy: force 변화 (force가 압축 후 확장)
    - 이전 force < 현재 force (확장 중)
    - 현재 dc가 극단 (압축 흔적)
    """
    force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
    dc = s.get('dc_pre', 0.5)
    
    # 압축 후 확장: DC 극단 + Force 상승
    compressed_then_expanded = (dc <= 0.2 or dc >= 0.8) and force >= 1.5
    return compressed_then_expanded


def obs_c1_force_range_mismatch(s: Dict) -> Optional[bool]:
    """
    OBS_C1: Force proxy > threshold인데 Range expansion < threshold인가?
    
    Proxy: High force but DC not extreme (range didn't expand proportionally)
    """
    force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
    dc = s.get('dc_pre', 0.5)
    
    # Force 높은데 DC가 중간 = 레인지가 비례 확장 안 함
    high_force_mid_dc = force >= 1.5 and 0.3 <= dc <= 0.7
    return high_force_mid_dc


OBSERVATION_UNITS = {
    'OBS_A1': obs_a1_reference_cross,
    'OBS_B1': obs_b1_volatility_pattern,
    'OBS_C1': obs_c1_force_range_mismatch,
}


# ============================================================
# STAGE 1: World-Forced Test
# ============================================================

def stage1_world_forced_test(signals: List[Dict], obs_fn) -> Dict:
    """
    H0: OBS_PASS / OBS_REJECT는 결과 위험도와 무관
    H1: OBS_PASS는 일관되게 더 낮은 위험
    
    판정: Loss(REJECT) - Loss(PASS) >= 15pp → PASS
    """
    pass_losses = []
    reject_losses = []
    
    for s in signals:
        # Storm-IN only
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
    
    pass_rate = sum(pass_losses) / len(pass_losses) if pass_losses else 0
    reject_rate = sum(reject_losses) / len(reject_losses) if reject_losses else 0
    diff = reject_rate - pass_rate
    
    return {
        'pass_loss': pass_rate,
        'reject_loss': reject_rate,
        'diff_pp': diff * 100,
        'n_pass': len(pass_losses),
        'n_reject': len(reject_losses),
        'verdict': 'PASS' if diff >= 0.15 else 'FAIL'
    }


# ============================================================
# STAGE 2: Collapse Tests
# ============================================================

def stage2_collapse_tests(signals: List[Dict], obs_fn) -> Dict:
    """
    C1: Force 무시 (>= 1.0)
    C2: τ 무시
    C3: Frame 무시
    C4: VOL 무시
    
    판정: 방향 유지 >= 3/4 → World-forced 후보
    """
    results = {}
    
    # C1: Force 무시
    c1_signals = [s for s in signals 
                  if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.0]
    c1_result = _collapse_test(c1_signals, obs_fn)
    results['C1_force'] = c1_result
    
    # C2: τ 무시 (Storm 조건 완화)
    c2_result = _collapse_test(signals, obs_fn, ignore_storm=True)
    results['C2_tau'] = c2_result
    
    # C3: Frame 무시
    c3_result = _collapse_test(signals, obs_fn, ignore_frame=True)
    results['C3_frame'] = c3_result
    
    # C4: VOL 무시 (모든 Force 레벨)
    c4_low = [s for s in signals 
              if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) < 1.5]
    c4_high = [s for s in signals 
               if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.5]
    
    c4_low_result = _collapse_test(c4_low, obs_fn)
    c4_high_result = _collapse_test(c4_high, obs_fn)
    
    # VOL 무시 = 두 레짐 모두 같은 방향
    c4_survived = (c4_low_result.get('direction', 0) > 0 and 
                   c4_high_result.get('direction', 0) > 0)
    results['C4_vol'] = {
        'low_force': c4_low_result,
        'high_force': c4_high_result,
        'survived': c4_survived
    }
    
    # Count survived
    survived_count = sum([
        results['C1_force'].get('survived', False),
        results['C2_tau'].get('survived', False),
        results['C3_frame'].get('survived', False),
        results['C4_vol'].get('survived', False)
    ])
    
    results['survived_count'] = survived_count
    results['verdict'] = 'WORLD_FORCED' if survived_count >= 3 else 'DISCARD'
    
    return results


def _collapse_test(signals: List[Dict], obs_fn, 
                   ignore_storm: bool = False, 
                   ignore_frame: bool = False) -> Dict:
    """Helper for collapse tests"""
    pass_losses = []
    reject_losses = []
    
    for s in signals:
        # Storm filter
        if not ignore_storm:
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
        return {'direction': 0, 'survived': False, 'n_pass': 0, 'n_reject': 0}
    
    pass_rate = sum(pass_losses) / len(pass_losses)
    reject_rate = sum(reject_losses) / len(reject_losses)
    diff = reject_rate - pass_rate
    
    return {
        'pass_loss': pass_rate,
        'reject_loss': reject_rate,
        'diff_pp': diff * 100,
        'direction': 1 if diff > 0 else -1,
        'survived': diff >= 0.05,  # 5pp 이상 유지
        'n_pass': len(pass_losses),
        'n_reject': len(reject_losses)
    }


# ============================================================
# MAIN EXECUTION
# ============================================================

def run_wind_h_tests():
    """Run WIND-H Stage 0-2 tests"""
    print("="*70)
    print("WIND-H: Observation Unit Tests")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\n" + "="*70)
    print("STAGE 0: Observation Units (의미 없는 관측 사실)")
    print("="*70)
    
    signals = load_signals()
    print(f"\nTotal signals: {len(signals)}")
    
    # Force-qualified baseline
    qualified = [s for s in signals 
                 if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.3]
    print(f"Force-qualified (>= 1.3): {len(qualified)}")
    
    all_results = {}
    
    for obs_id, obs_fn in OBSERVATION_UNITS.items():
        print(f"\n{'='*70}")
        print(f"OBS: {obs_id}")
        print("="*70)
        
        obs_result = {
            'obs_id': obs_id
        }
        
        # Count PASS/REJECT in Storm-IN
        storm_in = [s for s in qualified if classify_storm_coordinate(s) == "STORM_IN"]
        pass_count = sum(1 for s in storm_in if obs_fn(s) == True)
        reject_count = sum(1 for s in storm_in if obs_fn(s) == False)
        
        print(f"\nStorm-IN signals: {len(storm_in)}")
        print(f"OBS PASS: {pass_count}")
        print(f"OBS REJECT: {reject_count}")
        
        # Stage 1: World-Forced Test
        print("\n--- STAGE 1: World-Forced Test ---")
        s1_result = stage1_world_forced_test(qualified, obs_fn)
        
        print(f"PASS Loss: {s1_result['pass_loss']*100:.1f}% (N={s1_result['n_pass']})")
        print(f"REJECT Loss: {s1_result['reject_loss']*100:.1f}% (N={s1_result['n_reject']})")
        print(f"Diff: {s1_result['diff_pp']:.1f}pp")
        print(f"Verdict: {s1_result['verdict']}")
        
        obs_result['stage1'] = s1_result
        
        # Stage 2: Collapse Tests (only if Stage 1 passed or close)
        print("\n--- STAGE 2: Collapse Tests ---")
        s2_result = stage2_collapse_tests(qualified, obs_fn)
        
        print(f"C1 (Force 무시): {'✅' if s2_result['C1_force'].get('survived') else '❌'}")
        print(f"C2 (τ 무시): {'✅' if s2_result['C2_tau'].get('survived') else '❌'}")
        print(f"C3 (Frame 무시): {'✅' if s2_result['C3_frame'].get('survived') else '❌'}")
        print(f"C4 (VOL 무시): {'✅' if s2_result['C4_vol'].get('survived') else '❌'}")
        print(f"\nSurvived: {s2_result['survived_count']}/4")
        print(f"Verdict: {s2_result['verdict']}")
        
        obs_result['stage2'] = s2_result
        
        # Final Status
        if s1_result['verdict'] == 'PASS' and s2_result['verdict'] == 'WORLD_FORCED':
            final_status = 'PROMOTE'
        else:
            final_status = 'DISCARD'
        
        obs_result['final_status'] = final_status
        print(f"\n→ Final Status: {final_status}")
        
        all_results[obs_id] = obs_result
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    promoted = [k for k, v in all_results.items() if v['final_status'] == 'PROMOTE']
    discarded = [k for k, v in all_results.items() if v['final_status'] == 'DISCARD']
    
    print(f"\n✅ PROMOTE: {promoted}")
    print(f"❌ DISCARD: {discarded}")
    
    # Save
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'WIND_H_STAGE_0_2',
        'total_signals': len(signals),
        'qualified_signals': len(qualified),
        'results': all_results,
        'summary': {
            'promoted': promoted,
            'discarded': discarded
        }
    }
    
    output_path = 'v7-grammar-system/analysis/windmill/wind_h_obs_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_wind_h_tests()
