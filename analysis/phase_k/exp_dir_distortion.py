"""
EXP-DIR-DISTORTION SUITE
========================

방향 비대칭 결과에 대한 반증 실험 세트

DIST-1: 시간축 비틀기 (Temporal Scramble)
DIST-3: Micro Dropout (Blind Test)
DIST-4: Sign Flip Test (부호 반전)
"""

import json
import os
import sys
import random
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
from copy import deepcopy

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import (
    load_signals,
    classify_storm_coordinate,
)


def load_chart_data() -> pd.DataFrame:
    chart_path = 'data/chart_combined_full.csv'
    df = pd.read_csv(chart_path)
    df['time'] = pd.to_datetime(df['time'])
    df = df.drop_duplicates(subset=['time'], keep='first')
    df = df.set_index('time').sort_index()
    return df


def get_direction_from_chart(chart_df, entry_ts, entry_price, lookahead=5):
    try:
        ts = pd.to_datetime(entry_ts)
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
    except:
        return None
    
    try:
        idx = chart_df.index.get_indexer([ts], method='nearest')[0]
        if idx < 0 or idx + lookahead >= len(chart_df):
            return None
        
        future = chart_df.iloc[idx+1:idx+1+lookahead]
        if len(future) < lookahead:
            return None
        
        max_up = future['high'].max() - entry_price
        max_down = entry_price - future['low'].min()
        
        if max_up > max_down and max_up > 5:
            return 'UP'
        elif max_down > max_up and max_down > 5:
            return 'DOWN'
        else:
            return 'NEUTRAL'
    except:
        return None


def get_micro_vector(s: Dict, exclude_flags: List[str] = None) -> Dict[str, bool]:
    force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
    dc = s.get('dc_pre', 0.5)
    delta = s.get('avg_delta', 0)
    
    mv = {
        'high_force': force >= 1.5,
        'extreme_force': force >= 2.0,
        'dc_low': dc <= 0.2,
        'dc_high': dc >= 0.8,
        'delta_positive': delta > 0 if delta else False,
        'delta_spike': abs(delta) > 50 if delta else False,
        'force_dc_align': (force >= 1.5 and dc <= 0.2) or (force >= 1.5 and dc >= 0.8),
    }
    
    if exclude_flags:
        for f in exclude_flags:
            if f in mv:
                del mv[f]
    
    return mv


def calc_skew(directions: List[str]) -> float:
    up = sum(1 for d in directions if d == 'UP')
    down = sum(1 for d in directions if d == 'DOWN')
    total = up + down
    if total == 0:
        return 0
    return (up / total - 0.5) * 200


def run_dist_1(matched_data: List[Dict]) -> Dict:
    """DIST-1: 시간축 비틀기 (방향 레이블 셔플)"""
    print("\n" + "="*60)
    print("DIST-1: Temporal Scramble")
    print("="*60)
    
    original_directions = [m['direction'] for m in matched_data if m['direction'] != 'NEUTRAL']
    original_skew = calc_skew(original_directions)
    print(f"Original Skew: {original_skew:+.1f}pp (N={len(original_directions)})")
    
    n_trials = 100
    shuffled_skews = []
    
    for _ in range(n_trials):
        shuffled = original_directions.copy()
        random.shuffle(shuffled)
        shuffled_skews.append(calc_skew(shuffled))
    
    avg_shuffled = sum(shuffled_skews) / len(shuffled_skews)
    max_shuffled = max(shuffled_skews)
    min_shuffled = min(shuffled_skews)
    
    print(f"Shuffled Skew (avg of {n_trials}): {avg_shuffled:+.1f}pp")
    print(f"Shuffled range: [{min_shuffled:+.1f}, {max_shuffled:+.1f}]pp")
    
    collapsed = abs(avg_shuffled) < abs(original_skew) * 0.3
    verdict = "✅ PASS (Skew collapsed)" if collapsed else "❌ FAIL (Skew persisted)"
    print(f"Verdict: {verdict}")
    
    return {
        'original_skew': original_skew,
        'shuffled_avg': avg_shuffled,
        'shuffled_range': [min_shuffled, max_shuffled],
        'collapsed': collapsed,
        'verdict': 'PASS' if collapsed else 'FAIL'
    }


def run_dist_3(matched_data: List[Dict], signals_map: Dict) -> Dict:
    """DIST-3: Micro Dropout (하나씩 제거 후 Skew 변화)"""
    print("\n" + "="*60)
    print("DIST-3: Micro Dropout")
    print("="*60)
    
    flags_to_test = ['delta_positive', 'extreme_force', 'high_force', 'force_dc_align', 'dc_low']
    
    base_skew = calc_skew([m['direction'] for m in matched_data if m['direction'] != 'NEUTRAL'])
    print(f"Base Skew (all flags): {base_skew:+.1f}pp")
    
    results = {}
    
    for flag in flags_to_test:
        # Recalculate with flag excluded
        flag_true_dirs = []
        flag_false_dirs = []
        
        for m in matched_data:
            if m['direction'] == 'NEUTRAL':
                continue
            
            s = signals_map.get(m['ts'])
            if not s:
                continue
            
            mv = get_micro_vector(s, exclude_flags=[flag])
            
            # Check if any remaining flag is True
            any_true = any(mv.values())
            
            if any_true:
                flag_true_dirs.append(m['direction'])
            else:
                flag_false_dirs.append(m['direction'])
        
        new_skew = calc_skew(flag_true_dirs) if flag_true_dirs else 0
        diff = base_skew - new_skew
        
        print(f"  Without {flag:20}: Skew={new_skew:+.1f}pp (Δ={diff:+.1f}pp)")
        
        results[flag] = {
            'skew_without': new_skew,
            'delta': diff,
            'critical': abs(diff) > abs(base_skew) * 0.5
        }
    
    gradual = sum(1 for r in results.values() if not r['critical']) >= 3
    verdict = "✅ PASS (Gradual reduction)" if gradual else "❌ FAIL (Single flag dominance)"
    print(f"\nVerdict: {verdict}")
    
    return {
        'base_skew': base_skew,
        'dropout_results': results,
        'gradual': gradual,
        'verdict': 'PASS' if gradual else 'FAIL'
    }


def run_dist_4(matched_data: List[Dict], signals_map: Dict) -> Dict:
    """DIST-4: Sign Flip Test (delta_positive → delta_negative)"""
    print("\n" + "="*60)
    print("DIST-4: Sign Flip Test")
    print("="*60)
    
    pos_dirs = []
    neg_dirs = []
    
    for m in matched_data:
        if m['direction'] == 'NEUTRAL':
            continue
        
        s = signals_map.get(m['ts'])
        if not s:
            continue
        
        delta = s.get('avg_delta', 0)
        
        if delta and delta > 0:
            pos_dirs.append(m['direction'])
        elif delta and delta < 0:
            neg_dirs.append(m['direction'])
    
    pos_skew = calc_skew(pos_dirs)
    neg_skew = calc_skew(neg_dirs)
    
    print(f"delta_positive Skew: {pos_skew:+.1f}pp (N={len(pos_dirs)})")
    print(f"delta_negative Skew: {neg_skew:+.1f}pp (N={len(neg_dirs)})")
    
    flipped = (pos_skew > 0 and neg_skew < 0) or (pos_skew < 0 and neg_skew > 0)
    verdict = "✅ PASS (Skew flipped)" if flipped else "⚠️ PARTIAL (No clear flip)"
    print(f"Verdict: {verdict}")
    
    return {
        'pos_skew': pos_skew,
        'neg_skew': neg_skew,
        'n_pos': len(pos_dirs),
        'n_neg': len(neg_dirs),
        'flipped': flipped,
        'verdict': 'PASS' if flipped else 'PARTIAL'
    }


def run_distortion_suite():
    """Run DIST-1, DIST-3, DIST-4"""
    print("="*70)
    print("EXP-DIR-DISTORTION SUITE")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\n목적: 방향 비대칭 결과에 대한 반증 실험")
    print("-"*70)
    
    # Load data
    signals = load_signals()
    chart_df = load_chart_data()
    
    qualified = [s for s in signals 
                 if classify_storm_coordinate(s) == "STORM_IN"
                 and s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.3]
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    # Match with chart
    matched_data = []
    signals_map = {}
    
    for s in qualified:
        ts = s.get('ts')
        entry_price = s.get('entry_price')
        
        if not ts or not entry_price:
            continue
        
        parsed_ts = pd.to_datetime(ts)
        if parsed_ts.tzinfo is not None:
            parsed_ts = parsed_ts.replace(tzinfo=None)
        
        if parsed_ts < chart_start or parsed_ts > chart_end:
            continue
        
        direction = get_direction_from_chart(chart_df, ts, entry_price)
        if direction:
            matched_data.append({'ts': ts, 'direction': direction})
            signals_map[ts] = s
    
    print(f"\nMatched data: {len(matched_data)}")
    
    if len(matched_data) < 20:
        print("Insufficient data for distortion tests")
        return None
    
    results = {}
    
    # DIST-1
    results['DIST_1'] = run_dist_1(matched_data)
    
    # DIST-3
    results['DIST_3'] = run_dist_3(matched_data, signals_map)
    
    # DIST-4
    results['DIST_4'] = run_dist_4(matched_data, signals_map)
    
    # Summary
    print("\n" + "="*70)
    print("DISTORTION SUMMARY")
    print("="*70)
    
    print("\n| Test | Result | Interpretation |")
    print("|------|--------|----------------|")
    print(f"| DIST-1 | {results['DIST_1']['verdict']} | {'정상 (착시 제거)' if results['DIST_1']['verdict'] == 'PASS' else '데이터 누수 의심'} |")
    print(f"| DIST-3 | {results['DIST_3']['verdict']} | {'집합 효과' if results['DIST_3']['verdict'] == 'PASS' else '단일 신호 착시'} |")
    print(f"| DIST-4 | {results['DIST_4']['verdict']} | {'방향 정보' if results['DIST_4']['verdict'] == 'PASS' else '에너지 크기 효과'} |")
    
    all_pass = all(r['verdict'] == 'PASS' for r in results.values())
    
    if all_pass:
        final = "✅ 방향 비대칭은 착시가 아닌 실제 현상"
    else:
        final = "⚠️ 일부 반증 테스트 실패 — 추가 검증 필요"
    
    print(f"\n{final}")
    
    # Save
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'EXP_DIR_DISTORTION',
        'matched_count': len(matched_data),
        'results': results,
        'all_pass': all_pass
    }
    
    output_path = 'v7-grammar-system/analysis/phase_k/exp_dir_distortion_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_distortion_suite()
