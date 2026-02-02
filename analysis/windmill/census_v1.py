"""
WINDMILL CENSUS V1
==================

Experiment ID: PHASE_K_CENSUS_V1
One-liner: "기존 모든 조합이 같은 세계를 반복해서 가리키는지 검증"

Purpose:
- 새 알파 ❌
- 새 규칙 ❌
- 새 임계값 ❌
- 오직 재분류만 한다

Questions for each candidate:
1. Storm-IN 비율은?
2. Bar1 이후에만 의미를 가지는가?
3. 프레임 붕괴 시 같이 죽는가?
4. VOL 레짐이 바뀌면 같이 변하는가?
5. 관측자(엔트리 정의)를 바꿔도 유지되는가?
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple, Any
import statistics

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
# WINDMILL CANDIDATES (existing combinations to census)
# ============================================================

def candidate_high_force(s: Dict) -> bool:
    """High Force ratio (>= 1.5)"""
    force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
    return force >= 1.5

def candidate_extreme_force(s: Dict) -> bool:
    """Extreme Force ratio (>= 2.0)"""
    force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
    return force >= 2.0

def candidate_dc_high(s: Dict) -> bool:
    """DC channel high (>= 0.8)"""
    dc = s.get('dc_pre', 0.5)
    return dc >= 0.8

def candidate_dc_low(s: Dict) -> bool:
    """DC channel low (<= 0.2)"""
    dc = s.get('dc_pre', 0.5)
    return dc <= 0.2

def candidate_dc_extreme(s: Dict) -> bool:
    """DC channel extreme (>= 0.9 or <= 0.1)"""
    dc = s.get('dc_pre', 0.5)
    return dc >= 0.9 or dc <= 0.1

def candidate_positive_delta(s: Dict) -> bool:
    """Positive average delta"""
    delta = s.get('avg_delta', 0)
    return delta > 0

def candidate_negative_delta(s: Dict) -> bool:
    """Negative average delta"""
    delta = s.get('avg_delta', 0)
    return delta < 0

def candidate_strong_delta(s: Dict) -> bool:
    """Strong delta (absolute > median)"""
    delta = abs(s.get('avg_delta', 0))
    return delta > 50  # Will be calibrated from data

def candidate_force_dc_combo(s: Dict) -> bool:
    """Force >= 1.3 AND DC extreme"""
    force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
    dc = s.get('dc_pre', 0.5)
    return force >= 1.3 and (dc >= 0.8 or dc <= 0.2)


# All candidates to census
WINDMILL_CANDIDATES = {
    'HIGH_FORCE': candidate_high_force,
    'EXTREME_FORCE': candidate_extreme_force,
    'DC_HIGH': candidate_dc_high,
    'DC_LOW': candidate_dc_low,
    'DC_EXTREME': candidate_dc_extreme,
    'POSITIVE_DELTA': candidate_positive_delta,
    'NEGATIVE_DELTA': candidate_negative_delta,
    'STRONG_DELTA': candidate_strong_delta,
    'FORCE_DC_COMBO': candidate_force_dc_combo,
}


# ============================================================
# CENSUS QUESTIONS
# ============================================================

def census_storm_in_ratio(signals: List[Dict], candidate_fn) -> Dict:
    """Q1: Storm-IN 비율은?"""
    storm_in_count = 0
    storm_out_count = 0
    
    for s in signals:
        if not candidate_fn(s):
            continue
        storm = classify_storm_coordinate(s)
        if storm == "STORM_IN":
            storm_in_count += 1
        else:
            storm_out_count += 1
    
    total = storm_in_count + storm_out_count
    if total == 0:
        return {'ratio': 0, 'storm_in': 0, 'storm_out': 0, 'total': 0}
    
    return {
        'ratio': storm_in_count / total,
        'storm_in': storm_in_count,
        'storm_out': storm_out_count,
        'total': total
    }


def census_bar1_meaning(signals: List[Dict], candidate_fn) -> Dict:
    """Q2: Bar1 이후에만 의미를 가지는가?"""
    # Compare loss rates: candidate in Storm-IN vs not in Storm-IN
    in_losses = []
    out_losses = []
    
    for s in signals:
        if not candidate_fn(s):
            continue
        
        storm = classify_storm_coordinate(s)
        _, is_loss = simulate_outcome(s, 
                                       WindmillState.ON if storm == "STORM_IN" else WindmillState.OFF)
        
        if storm == "STORM_IN":
            in_losses.append(is_loss)
        else:
            out_losses.append(is_loss)
    
    in_rate = sum(in_losses) / len(in_losses) if in_losses else 0
    out_rate = sum(out_losses) / len(out_losses) if out_losses else 0
    
    return {
        'storm_in_loss': in_rate,
        'storm_out_loss': out_rate,
        'diff_pp': (out_rate - in_rate) * 100,
        'n_in': len(in_losses),
        'n_out': len(out_losses)
    }


def census_frame_collapse(signals: List[Dict], candidate_fn) -> Dict:
    """Q3: 프레임 붕괴 시 같이 죽는가?"""
    frame_alive_losses = []
    frame_dead_losses = []
    
    for s in signals:
        if not candidate_fn(s):
            continue
        
        storm = classify_storm_coordinate(s)
        if storm != "STORM_IN":
            continue
        
        tau = estimate_tau(s)
        dir_count = estimate_dir_count(s)
        frame_alive = tau >= 4 and dir_count >= 3
        
        _, is_loss = simulate_outcome(s, WindmillState.ON)
        
        if frame_alive:
            frame_alive_losses.append(is_loss)
        else:
            frame_dead_losses.append(is_loss)
    
    alive_rate = sum(frame_alive_losses) / len(frame_alive_losses) if frame_alive_losses else 0
    dead_rate = sum(frame_dead_losses) / len(frame_dead_losses) if frame_dead_losses else 0
    
    return {
        'frame_alive_loss': alive_rate,
        'frame_dead_loss': dead_rate,
        'collapse_together': dead_rate > alive_rate + 0.05,
        'n_alive': len(frame_alive_losses),
        'n_dead': len(frame_dead_losses)
    }


def census_vol_regime(signals: List[Dict], candidate_fn) -> Dict:
    """Q4: VOL 레짐이 바뀌면 같이 변하는가?"""
    # Classify by force magnitude as volatility proxy
    low_losses = []
    mid_losses = []
    high_losses = []
    
    for s in signals:
        if not candidate_fn(s):
            continue
        
        storm = classify_storm_coordinate(s)
        if storm != "STORM_IN":
            continue
        
        force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
        _, is_loss = simulate_outcome(s, WindmillState.ON)
        
        if force < 1.3:
            low_losses.append(is_loss)
        elif force < 1.8:
            mid_losses.append(is_loss)
        else:
            high_losses.append(is_loss)
    
    low_rate = sum(low_losses) / len(low_losses) if low_losses else None
    mid_rate = sum(mid_losses) / len(mid_losses) if mid_losses else None
    high_rate = sum(high_losses) / len(high_losses) if high_losses else None
    
    # Check direction consistency
    directions = []
    if low_rate is not None and mid_rate is not None:
        directions.append('up' if mid_rate > low_rate else 'down')
    if mid_rate is not None and high_rate is not None:
        directions.append('up' if high_rate > mid_rate else 'down')
    
    consistent = len(set(directions)) <= 1 if directions else False
    
    return {
        'vol_low_loss': low_rate,
        'vol_mid_loss': mid_rate,
        'vol_high_loss': high_rate,
        'direction_consistent': consistent,
        'n_low': len(low_losses),
        'n_mid': len(mid_losses),
        'n_high': len(high_losses)
    }


def census_observer_invariance(signals: List[Dict], candidate_fn) -> Dict:
    """Q5: 관측자(엔트리 정의)를 바꿔도 유지되는가?"""
    # Compare with stricter entry definition
    normal_losses = []
    strict_losses = []
    
    for s in signals:
        if not candidate_fn(s):
            continue
        
        storm = classify_storm_coordinate(s)
        if storm != "STORM_IN":
            continue
        
        force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
        _, is_loss = simulate_outcome(s, WindmillState.ON)
        
        normal_losses.append(is_loss)
        
        # Stricter: force >= 1.5
        if force >= 1.5:
            strict_losses.append(is_loss)
    
    normal_rate = sum(normal_losses) / len(normal_losses) if normal_losses else 0
    strict_rate = sum(strict_losses) / len(strict_losses) if strict_losses else 0
    
    return {
        'normal_entry_loss': normal_rate,
        'strict_entry_loss': strict_rate,
        'diff_pp': abs(strict_rate - normal_rate) * 100,
        'invariant': abs(strict_rate - normal_rate) < 0.10,
        'n_normal': len(normal_losses),
        'n_strict': len(strict_losses)
    }


# ============================================================
# MAIN CENSUS
# ============================================================

def run_census():
    """Run Windmill Census V1"""
    print("="*70)
    print("WINDMILL CENSUS V1")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nPurpose: 기존 모든 조합이 같은 세계를 반복해서 가리키는지 검증")
    print("-"*70)
    
    signals = load_signals()
    print(f"\nTotal signals: {len(signals)}")
    
    # Filter Force-qualified signals
    F_THRESHOLD = 1.3
    qualified = [s for s in signals 
                 if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= F_THRESHOLD]
    print(f"Force-qualified (>= {F_THRESHOLD}): {len(qualified)}")
    
    census_results = {}
    
    for name, candidate_fn in WINDMILL_CANDIDATES.items():
        print(f"\n{'='*70}")
        print(f"CANDIDATE: {name}")
        print("="*70)
        
        result = {
            'name': name,
            'questions': {}
        }
        
        # Q1: Storm-IN ratio
        q1 = census_storm_in_ratio(qualified, candidate_fn)
        print(f"\nQ1. Storm-IN ratio: {q1['ratio']*100:.1f}%")
        print(f"    (IN={q1['storm_in']}, OUT={q1['storm_out']})")
        result['questions']['storm_in_ratio'] = q1
        
        if q1['total'] < 20:
            print("    → SKIP (insufficient data)")
            result['verdict'] = 'SKIP'
            census_results[name] = result
            continue
        
        # Q2: Bar1 meaning
        q2 = census_bar1_meaning(qualified, candidate_fn)
        print(f"\nQ2. Bar1 meaning:")
        print(f"    Storm-IN loss: {q2['storm_in_loss']*100:.1f}%")
        print(f"    Storm-OUT loss: {q2['storm_out_loss']*100:.1f}%")
        print(f"    Diff: {q2['diff_pp']:.1f}pp")
        result['questions']['bar1_meaning'] = q2
        
        # Q3: Frame collapse
        q3 = census_frame_collapse(qualified, candidate_fn)
        if q3['n_alive'] > 0 and q3['n_dead'] > 0:
            print(f"\nQ3. Frame collapse:")
            print(f"    Frame alive loss: {q3['frame_alive_loss']*100:.1f}%")
            print(f"    Frame dead loss: {q3['frame_dead_loss']*100:.1f}%")
            print(f"    Collapse together: {q3['collapse_together']}")
        result['questions']['frame_collapse'] = q3
        
        # Q4: VOL regime
        q4 = census_vol_regime(qualified, candidate_fn)
        print(f"\nQ4. VOL regime consistency:")
        if q4['vol_low_loss'] is not None:
            print(f"    LOW: {q4['vol_low_loss']*100:.1f}% (N={q4['n_low']})")
        if q4['vol_mid_loss'] is not None:
            print(f"    MID: {q4['vol_mid_loss']*100:.1f}% (N={q4['n_mid']})")
        if q4['vol_high_loss'] is not None:
            print(f"    HIGH: {q4['vol_high_loss']*100:.1f}% (N={q4['n_high']})")
        print(f"    Direction consistent: {q4['direction_consistent']}")
        result['questions']['vol_regime'] = q4
        
        # Q5: Observer invariance
        q5 = census_observer_invariance(qualified, candidate_fn)
        print(f"\nQ5. Observer invariance:")
        print(f"    Normal entry loss: {q5['normal_entry_loss']*100:.1f}%")
        print(f"    Strict entry loss: {q5['strict_entry_loss']*100:.1f}%")
        print(f"    Diff: {q5['diff_pp']:.1f}pp")
        print(f"    Invariant: {q5['invariant']}")
        result['questions']['observer_invariance'] = q5
        
        # Final verdict for this candidate
        world_score = 0
        if q2['diff_pp'] >= 20:  # Bar1 meaningful
            world_score += 1
        if q3.get('collapse_together', False):  # Frame collapse
            world_score += 1
        if q4.get('direction_consistent', False):  # VOL consistent
            world_score += 1
        if q5.get('invariant', False):  # Observer invariant
            world_score += 1
        
        if world_score >= 3:
            verdict = 'SAME_WORLD'
        elif world_score >= 2:
            verdict = 'PARTIAL'
        else:
            verdict = 'DIFFERENT_WORLD'
        
        result['world_score'] = world_score
        result['verdict'] = verdict
        
        print(f"\n→ World Score: {world_score}/4")
        print(f"→ Verdict: {verdict}")
        
        census_results[name] = result
    
    # Summary
    print("\n" + "="*70)
    print("CENSUS SUMMARY")
    print("="*70)
    
    same_world = [k for k, v in census_results.items() if v.get('verdict') == 'SAME_WORLD']
    partial = [k for k, v in census_results.items() if v.get('verdict') == 'PARTIAL']
    different = [k for k, v in census_results.items() if v.get('verdict') == 'DIFFERENT_WORLD']
    skipped = [k for k, v in census_results.items() if v.get('verdict') == 'SKIP']
    
    print(f"\n✅ SAME_WORLD ({len(same_world)}): {same_world}")
    print(f"⚠️ PARTIAL ({len(partial)}): {partial}")
    print(f"❌ DIFFERENT_WORLD ({len(different)}): {different}")
    print(f"⏭️ SKIPPED ({len(skipped)}): {skipped}")
    
    # Save
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'WINDMILL_CENSUS_V1',
        'total_signals': len(signals),
        'qualified_signals': len(qualified),
        'candidates': census_results,
        'summary': {
            'same_world': same_world,
            'partial': partial,
            'different_world': different,
            'skipped': skipped
        }
    }
    
    output_path = 'v7-grammar-system/analysis/windmill/census_v1_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_census()
