"""
DC_HIGH vs DC_LOW Symmetry Analysis
====================================

Experiment ID: DC_SYMMETRY_V1
One-liner: "DC_HIGH와 DC_LOW가 같은 자리의 다른 부호인지 검증"

Question:
DC_HIGH와 DC_LOW는
- 같은 자리를 다른 부호로 본 것인가? → 하나의 풍차
- 미시적으로 다른 자리인가? → 두 개의 미시 풍차

Tests:
1. Storm-IN 비율 대칭성
2. Loss rate 대칭성
3. Frame collapse 대칭성
4. VOL regime 반응 대칭성
5. Force 분포 대칭성
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple
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


def run_dc_symmetry():
    """DC_HIGH vs DC_LOW Symmetry Analysis"""
    print("="*70)
    print("DC SYMMETRY ANALYSIS")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nQuestion: DC_HIGH와 DC_LOW는 같은 자리의 다른 부호인가?")
    print("-"*70)
    
    signals = load_signals()
    print(f"\nTotal signals: {len(signals)}")
    
    # Filter Force-qualified
    F_THRESHOLD = 1.3
    qualified = [s for s in signals 
                 if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= F_THRESHOLD]
    print(f"Force-qualified: {len(qualified)}")
    
    # Classify DC
    dc_high = [s for s in qualified if s.get('dc_pre', 0.5) >= 0.8]
    dc_low = [s for s in qualified if s.get('dc_pre', 0.5) <= 0.2]
    dc_mid = [s for s in qualified if 0.2 < s.get('dc_pre', 0.5) < 0.8]
    
    print(f"\nDC_HIGH (≥0.8): {len(dc_high)}")
    print(f"DC_LOW (≤0.2): {len(dc_low)}")
    print(f"DC_MID: {len(dc_mid)}")
    
    results = {}
    
    # ============================================================
    # TEST 1: Storm-IN ratio symmetry
    # ============================================================
    print("\n" + "="*70)
    print("TEST 1: Storm-IN Ratio Symmetry")
    print("="*70)
    
    def storm_in_ratio(subset):
        in_count = sum(1 for s in subset if classify_storm_coordinate(s) == "STORM_IN")
        return in_count / len(subset) if subset else 0
    
    high_storm_ratio = storm_in_ratio(dc_high)
    low_storm_ratio = storm_in_ratio(dc_low)
    ratio_diff = abs(high_storm_ratio - low_storm_ratio)
    
    print(f"DC_HIGH Storm-IN ratio: {high_storm_ratio*100:.1f}%")
    print(f"DC_LOW Storm-IN ratio: {low_storm_ratio*100:.1f}%")
    print(f"Difference: {ratio_diff*100:.1f}pp")
    print(f"Symmetric (diff < 10pp): {ratio_diff < 0.10}")
    
    results['storm_ratio'] = {
        'dc_high': high_storm_ratio,
        'dc_low': low_storm_ratio,
        'diff': ratio_diff,
        'symmetric': ratio_diff < 0.10
    }
    
    # ============================================================
    # TEST 2: Loss rate symmetry
    # ============================================================
    print("\n" + "="*70)
    print("TEST 2: Loss Rate Symmetry (Storm-IN only)")
    print("="*70)
    
    def get_storm_in_loss_rate(subset):
        losses = []
        for s in subset:
            if classify_storm_coordinate(s) != "STORM_IN":
                continue
            _, is_loss = simulate_outcome(s, WindmillState.ON)
            losses.append(is_loss)
        return sum(losses) / len(losses) if losses else 0, len(losses)
    
    high_loss, high_n = get_storm_in_loss_rate(dc_high)
    low_loss, low_n = get_storm_in_loss_rate(dc_low)
    loss_diff = abs(high_loss - low_loss)
    
    print(f"DC_HIGH Storm-IN loss: {high_loss*100:.1f}% (N={high_n})")
    print(f"DC_LOW Storm-IN loss: {low_loss*100:.1f}% (N={low_n})")
    print(f"Difference: {loss_diff*100:.1f}pp")
    print(f"Symmetric (diff < 10pp): {loss_diff < 0.10}")
    
    results['loss_rate'] = {
        'dc_high': high_loss,
        'dc_low': low_loss,
        'n_high': high_n,
        'n_low': low_n,
        'diff': loss_diff,
        'symmetric': loss_diff < 0.10
    }
    
    # ============================================================
    # TEST 3: Frame collapse symmetry
    # ============================================================
    print("\n" + "="*70)
    print("TEST 3: Frame Collapse Symmetry")
    print("="*70)
    
    def get_frame_collapse_pattern(subset):
        alive_losses = []
        dead_losses = []
        for s in subset:
            if classify_storm_coordinate(s) != "STORM_IN":
                continue
            tau = estimate_tau(s)
            dir_count = estimate_dir_count(s)
            frame_alive = tau >= 4 and dir_count >= 3
            _, is_loss = simulate_outcome(s, WindmillState.ON)
            if frame_alive:
                alive_losses.append(is_loss)
            else:
                dead_losses.append(is_loss)
        alive_rate = sum(alive_losses) / len(alive_losses) if alive_losses else 0
        dead_rate = sum(dead_losses) / len(dead_losses) if dead_losses else 0
        return alive_rate, dead_rate, len(alive_losses), len(dead_losses)
    
    high_alive, high_dead, high_n_alive, high_n_dead = get_frame_collapse_pattern(dc_high)
    low_alive, low_dead, low_n_alive, low_n_dead = get_frame_collapse_pattern(dc_low)
    
    high_collapse_diff = high_dead - high_alive
    low_collapse_diff = low_dead - low_alive
    
    print(f"DC_HIGH: alive={high_alive*100:.1f}%, dead={high_dead*100:.1f}%, collapse_diff={high_collapse_diff*100:.1f}pp")
    print(f"DC_LOW:  alive={low_alive*100:.1f}%, dead={low_dead*100:.1f}%, collapse_diff={low_collapse_diff*100:.1f}pp")
    
    # Same direction = symmetric
    same_direction = (high_collapse_diff > 0) == (low_collapse_diff > 0)
    print(f"Same collapse direction: {same_direction}")
    
    results['frame_collapse'] = {
        'dc_high': {'alive': high_alive, 'dead': high_dead, 'diff': high_collapse_diff},
        'dc_low': {'alive': low_alive, 'dead': low_dead, 'diff': low_collapse_diff},
        'same_direction': same_direction
    }
    
    # ============================================================
    # TEST 4: Force distribution symmetry
    # ============================================================
    print("\n" + "="*70)
    print("TEST 4: Force Distribution Symmetry")
    print("="*70)
    
    def get_force_stats(subset):
        forces = [s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) for s in subset]
        if not forces:
            return 0, 0
        return statistics.mean(forces), statistics.stdev(forces) if len(forces) > 1 else 0
    
    high_force_mean, high_force_std = get_force_stats(dc_high)
    low_force_mean, low_force_std = get_force_stats(dc_low)
    
    print(f"DC_HIGH Force: mean={high_force_mean:.2f}, std={high_force_std:.2f}")
    print(f"DC_LOW Force:  mean={low_force_mean:.2f}, std={low_force_std:.2f}")
    
    force_mean_diff = abs(high_force_mean - low_force_mean)
    print(f"Mean difference: {force_mean_diff:.2f}")
    print(f"Similar distribution (diff < 0.3): {force_mean_diff < 0.3}")
    
    results['force_dist'] = {
        'dc_high': {'mean': high_force_mean, 'std': high_force_std},
        'dc_low': {'mean': low_force_mean, 'std': low_force_std},
        'mean_diff': force_mean_diff,
        'similar': force_mean_diff < 0.3
    }
    
    # ============================================================
    # TEST 5: Delta direction symmetry
    # ============================================================
    print("\n" + "="*70)
    print("TEST 5: Delta Direction Symmetry")
    print("="*70)
    
    def get_delta_direction(subset):
        pos = sum(1 for s in subset if s.get('avg_delta', 0) > 0)
        neg = sum(1 for s in subset if s.get('avg_delta', 0) < 0)
        total = pos + neg
        return pos / total if total > 0 else 0.5
    
    high_pos_ratio = get_delta_direction(dc_high)
    low_pos_ratio = get_delta_direction(dc_low)
    
    print(f"DC_HIGH positive delta ratio: {high_pos_ratio*100:.1f}%")
    print(f"DC_LOW positive delta ratio: {low_pos_ratio*100:.1f}%")
    
    # Opposite direction = symmetric (HIGH should have more neg, LOW more pos)
    opposite = (high_pos_ratio < 0.5 and low_pos_ratio > 0.5) or \
               (high_pos_ratio > 0.5 and low_pos_ratio < 0.5)
    print(f"Opposite delta direction: {opposite}")
    
    results['delta_direction'] = {
        'dc_high_pos': high_pos_ratio,
        'dc_low_pos': low_pos_ratio,
        'opposite': opposite
    }
    
    # ============================================================
    # FINAL VERDICT
    # ============================================================
    print("\n" + "="*70)
    print("FINAL VERDICT")
    print("="*70)
    
    symmetry_score = 0
    if results['storm_ratio']['symmetric']:
        symmetry_score += 1
    if results['loss_rate']['symmetric']:
        symmetry_score += 1
    if results['frame_collapse']['same_direction']:
        symmetry_score += 1
    if results['force_dist']['similar']:
        symmetry_score += 1
    if results['delta_direction']['opposite']:
        symmetry_score += 1
    
    print(f"\nSymmetry Score: {symmetry_score}/5")
    
    if symmetry_score >= 4:
        verdict = "SAME_SEAT_OPPOSITE_SIGN"
        interpretation = """
'DC_HIGH와 DC_LOW는 같은 자리의 다른 부호다.
 하나의 풍차가 두 방향을 본다.'
→ 통합 가능
"""
    elif symmetry_score >= 2:
        verdict = "PARTIAL_SYMMETRY"
        interpretation = """
'부분적으로 대칭이지만 완전하지 않다.
 미시 구조에서 차이가 있을 수 있다.'
→ 주의 필요
"""
    else:
        verdict = "DIFFERENT_SEATS"
        interpretation = """
'DC_HIGH와 DC_LOW는 미시적으로 다른 자리다.
 두 개의 별개 풍차로 취급해야 한다.'
→ 분리 유지
"""
    
    print(f"\nVerdict: {verdict}")
    print(interpretation)
    
    results['verdict'] = verdict
    results['symmetry_score'] = symmetry_score
    
    # Save
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'DC_SYMMETRY_V1',
        'question': 'DC_HIGH vs DC_LOW: same seat opposite sign?',
        'data': {
            'dc_high_count': len(dc_high),
            'dc_low_count': len(dc_low)
        },
        'tests': results,
        'verdict': verdict,
        'symmetry_score': symmetry_score
    }
    
    output_path = 'v7-grammar-system/analysis/windmill/dc_symmetry_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_dc_symmetry()
