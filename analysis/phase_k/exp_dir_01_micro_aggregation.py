"""
EXP-DIR-01: Micro-Aggregation Direction Hypothesis
===================================================

목적: 동일 Seat 내부에서 관측된 미시 반응들의 집합이
      방향 분포를 비대칭으로 붕괴시키는지 검증

H0: 미시 반응 벡터 μ와 방향 분포는 독립
H1: 특정 μ-조합에서 방향 분포가 유의미하게 비대칭 붕괴

판정: Skew = |P(UP|μ) - P(DOWN|μ)| >= 20pp → Directional Bias 존재
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import (
    load_signals,
    classify_storm_coordinate,
    WindmillState,
    simulate_outcome
)


# ============================================================
# MICRO OBSERVATION FLAGS (방향값 직접 사용 금지)
# ============================================================

def get_micro_vector(s: Dict) -> Dict[str, bool]:
    """
    미시 반응 벡터 (상태 반응 서명)
    각 미시는 방향값을 직접 쓰지 않는다
    """
    force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
    dc = s.get('dc_pre', 0.5)
    delta = s.get('avg_delta', 0)
    
    return {
        'high_force': force >= 1.5,
        'extreme_force': force >= 2.0,
        'dc_low': dc <= 0.2,
        'dc_high': dc >= 0.8,
        'dc_extreme': dc <= 0.1 or dc >= 0.9,
        'delta_spike': abs(delta) > 100 if delta else False,
        'force_dc_align': (force >= 1.5 and dc <= 0.2) or (force >= 1.5 and dc >= 0.8),
    }


def get_direction_outcome(s: Dict) -> Optional[str]:
    """
    방향 결과 (결과 레이블로만 사용)
    """
    # MFE sign으로 방향 판정
    mfe = s.get('mfe', 0)
    if mfe is None:
        return None
    
    # 단순화: 양수 MFE = UP, 음수 MFE = DOWN
    if mfe > 0:
        return 'UP'
    elif mfe < 0:
        return 'DOWN'
    else:
        return None


# ============================================================
# MICRO-AGGREGATION ANALYSIS
# ============================================================

def analyze_micro_aggregation(signals: List[Dict]) -> Dict:
    """
    미시 반응 조합별 방향 분포 분석
    """
    results = {}
    
    # Storm-IN only, Force-qualified
    qualified = [s for s in signals 
                 if classify_storm_coordinate(s) == "STORM_IN"
                 and s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.3]
    
    print(f"Storm-IN qualified: {len(qualified)}")
    
    # 각 미시 플래그별 분석
    micro_flags = ['high_force', 'extreme_force', 'dc_low', 'dc_high', 
                   'dc_extreme', 'delta_spike', 'force_dc_align']
    
    for flag in micro_flags:
        flag_true_up = 0
        flag_true_down = 0
        flag_false_up = 0
        flag_false_down = 0
        
        for s in qualified:
            mv = get_micro_vector(s)
            direction = get_direction_outcome(s)
            
            if direction is None:
                continue
            
            if mv[flag]:
                if direction == 'UP':
                    flag_true_up += 1
                else:
                    flag_true_down += 1
            else:
                if direction == 'UP':
                    flag_false_up += 1
                else:
                    flag_false_down += 1
        
        # Calculate skew
        true_total = flag_true_up + flag_true_down
        false_total = flag_false_up + flag_false_down
        
        if true_total > 0:
            true_up_rate = flag_true_up / true_total
            true_skew = abs(true_up_rate - 0.5) * 2  # 0-1 scale
        else:
            true_up_rate = 0.5
            true_skew = 0
        
        if false_total > 0:
            false_up_rate = flag_false_up / false_total
            false_skew = abs(false_up_rate - 0.5) * 2
        else:
            false_up_rate = 0.5
            false_skew = 0
        
        results[flag] = {
            'true': {
                'n': true_total,
                'up_rate': true_up_rate,
                'skew': true_skew * 100
            },
            'false': {
                'n': false_total,
                'up_rate': false_up_rate,
                'skew': false_skew * 100
            },
            'differential_skew': abs(true_up_rate - false_up_rate) * 100
        }
    
    return results


def collapse_test_direction(signals: List[Dict], flag: str) -> Dict:
    """
    방향 비대칭이 착시인지 검증
    """
    results = {}
    
    # VOL regime 분리
    low_vol = [s for s in signals 
               if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) < 1.5]
    high_vol = [s for s in signals 
                if s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.5]
    
    results['vol_low'] = _calc_flag_skew(low_vol, flag)
    results['vol_high'] = _calc_flag_skew(high_vol, flag)
    
    # DC regime 분리
    dc_low = [s for s in signals if s.get('dc_pre', 0.5) <= 0.3]
    dc_high = [s for s in signals if s.get('dc_pre', 0.5) >= 0.7]
    
    results['dc_low'] = _calc_flag_skew(dc_low, flag)
    results['dc_high'] = _calc_flag_skew(dc_high, flag)
    
    # Count survived
    skew_threshold = 10  # pp
    survived = 0
    for key, val in results.items():
        if val.get('skew', 0) >= skew_threshold:
            survived += 1
    
    results['survived_count'] = survived
    results['verdict'] = 'STABLE' if survived >= 3 else 'UNSTABLE'
    
    return results


def _calc_flag_skew(signals: List[Dict], flag: str) -> Dict:
    """Calculate skew for a flag in a subset"""
    qualified = [s for s in signals 
                 if classify_storm_coordinate(s) == "STORM_IN"
                 and s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.3]
    
    up_count = 0
    down_count = 0
    
    for s in qualified:
        mv = get_micro_vector(s)
        direction = get_direction_outcome(s)
        
        if direction is None or not mv.get(flag, False):
            continue
        
        if direction == 'UP':
            up_count += 1
        else:
            down_count += 1
    
    total = up_count + down_count
    if total == 0:
        return {'n': 0, 'up_rate': 0.5, 'skew': 0}
    
    up_rate = up_count / total
    skew = abs(up_rate - 0.5) * 200  # pp scale
    
    return {
        'n': total,
        'up_rate': up_rate,
        'skew': skew
    }


# ============================================================
# MAIN EXECUTION
# ============================================================

def run_exp_dir_01():
    """Run EXP-DIR-01: Micro-Aggregation Direction Hypothesis"""
    print("="*70)
    print("EXP-DIR-01: Micro-Aggregation Direction Hypothesis")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\nH0: 미시 반응 벡터 μ와 방향 분포는 독립")
    print("H1: 특정 μ-조합에서 방향 분포가 비대칭 붕괴")
    print("-"*70)
    
    signals = load_signals()
    print(f"\nTotal signals: {len(signals)}")
    
    # Stage 1: Micro-Aggregation Analysis
    print("\n" + "="*70)
    print("STAGE 1: Micro-Aggregation Analysis")
    print("="*70)
    
    micro_results = analyze_micro_aggregation(signals)
    
    print("\n| Flag | TRUE N | TRUE Skew | FALSE N | FALSE Skew | Diff |")
    print("|------|--------|-----------|---------|------------|------|")
    
    biased_flags = []
    
    for flag, data in micro_results.items():
        true_n = data['true']['n']
        true_skew = data['true']['skew']
        false_n = data['false']['n']
        false_skew = data['false']['skew']
        diff = data['differential_skew']
        
        bias_marker = "⚡" if diff >= 20 else ""
        print(f"| {flag:15} | {true_n:5} | {true_skew:8.1f}pp | {false_n:6} | {false_skew:9.1f}pp | {diff:5.1f}pp {bias_marker} |")
        
        if diff >= 20:
            biased_flags.append(flag)
    
    print(f"\nBiased flags (Diff >= 20pp): {biased_flags}")
    
    # Stage 2: Collapse Tests for biased flags
    print("\n" + "="*70)
    print("STAGE 2: Collapse Tests")
    print("="*70)
    
    collapse_results = {}
    stable_flags = []
    
    for flag in biased_flags:
        print(f"\n--- {flag} ---")
        result = collapse_test_direction(signals, flag)
        collapse_results[flag] = result
        
        print(f"VOL_LOW: {result['vol_low'].get('skew', 0):.1f}pp (N={result['vol_low'].get('n', 0)})")
        print(f"VOL_HIGH: {result['vol_high'].get('skew', 0):.1f}pp (N={result['vol_high'].get('n', 0)})")
        print(f"DC_LOW: {result['dc_low'].get('skew', 0):.1f}pp (N={result['dc_low'].get('n', 0)})")
        print(f"DC_HIGH: {result['dc_high'].get('skew', 0):.1f}pp (N={result['dc_high'].get('n', 0)})")
        print(f"Survived: {result['survived_count']}/4 → {result['verdict']}")
        
        if result['verdict'] == 'STABLE':
            stable_flags.append(flag)
    
    # Final Verdict
    print("\n" + "="*70)
    print("FINAL VERDICT")
    print("="*70)
    
    if stable_flags:
        verdict = "H1 ACCEPTED (PARTIAL)"
        interpretation = f"""
방향 분포 비대칭이 발견됨:
- Biased flags: {biased_flags}
- Stable after collapse: {stable_flags}

→ 이 μ-조합에서는 방향이 드러나는 관측 조건이 존재
→ Conditional Bias Map 생성 가능
"""
    elif biased_flags:
        verdict = "H1 WEAK"
        interpretation = f"""
방향 분포 비대칭이 있으나 불안정:
- Biased flags: {biased_flags}
- Stable after collapse: 없음

→ 조건부 bias는 있으나 세계 강제 아님
→ Operational 수준에서만 사용 가능
"""
    else:
        verdict = "H0 NOT REJECTED"
        interpretation = """
미시 집합으로도 방향 분포가 기울지 않음.
→ 방향은 Seat 바깥 요인
→ 빗각, 미세 유동 등 추가 탐색 필요
"""
    
    print(f"\nVerdict: {verdict}")
    print(interpretation)
    
    # Save
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'EXP_DIR_01',
        'micro_results': micro_results,
        'biased_flags': biased_flags,
        'collapse_results': collapse_results,
        'stable_flags': stable_flags,
        'verdict': verdict
    }
    
    output_path = 'v7-grammar-system/analysis/phase_k/exp_dir_01_result.json'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_exp_dir_01()
