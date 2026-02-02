"""
EXP-DIR-01′: Micro-Aggregation Direction Hypothesis (Chart-Based)
==================================================================

차트 데이터에서 Bar1 이후 가격 궤적을 사후 관측하여 방향 판정

목적: Storm-IN 조건에서 방향 비대칭이 생기는지 검증

방향 정의:
- Bar1 이후 N bars (3, 5, 10)
- max_up_move > max_down_move → UP
- max_down_move > max_up_move → DOWN
- 둘 다 작음 → NEUTRAL
"""

import json
import os
import sys
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import (
    load_signals,
    classify_storm_coordinate,
)


def load_chart_data() -> pd.DataFrame:
    """Load cleaned NQ 1-min chart data"""
    chart_path = 'data/nq1_clean.csv'
    df = pd.read_csv(chart_path)
    df['time'] = pd.to_datetime(df['time'])
    df = df.set_index('time')
    df = df.sort_index()
    return df


def get_direction_from_chart(chart_df: pd.DataFrame, 
                              entry_ts: str, 
                              entry_price: float,
                              lookahead: int = 5) -> Optional[Dict]:
    """
    Bar1 이후 N bars의 가격 변화로 방향 판정
    """
    try:
        ts = pd.to_datetime(entry_ts)
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
    except:
        return None
    
    try:
        # Find nearest bar
        idx = chart_df.index.get_indexer([ts], method='nearest')[0]
        
        if idx < 0 or idx + lookahead >= len(chart_df):
            return None
        
        future_bars = chart_df.iloc[idx+1:idx+1+lookahead]
        
        if len(future_bars) < lookahead:
            return None
        
        max_high = future_bars['high'].max()
        min_low = future_bars['low'].min()
        
        max_up_move = max_high - entry_price
        max_down_move = entry_price - min_low
        
        threshold = 5
        if max_up_move > max_down_move and max_up_move > threshold:
            direction = 'UP'
        elif max_down_move > max_up_move and max_down_move > threshold:
            direction = 'DOWN'
        else:
            direction = 'NEUTRAL'
        
        return {
            'direction': direction,
            'max_up': max_up_move,
            'max_down': max_down_move,
            'net_move': max_up_move - max_down_move
        }
    except:
        return None


def get_micro_vector(s: Dict) -> Dict[str, bool]:
    """미시 반응 벡터"""
    force = s.get('force_ratio_30', s.get('force_ratio_20', 1.0))
    dc = s.get('dc_pre', 0.5)
    delta = s.get('avg_delta', 0)
    
    return {
        'high_force': force >= 1.5,
        'extreme_force': force >= 2.0,
        'dc_low': dc <= 0.2,
        'dc_high': dc >= 0.8,
        'dc_extreme': dc <= 0.1 or dc >= 0.9,
        'delta_positive': delta > 0 if delta else False,
        'delta_spike': abs(delta) > 50 if delta else False,
        'force_dc_align': (force >= 1.5 and dc <= 0.2) or (force >= 1.5 and dc >= 0.8),
    }


def run_exp_dir_01_prime():
    """Run EXP-DIR-01′: Chart-Based Direction Analysis"""
    print("="*70)
    print("EXP-DIR-01′: Micro-Aggregation Direction (Chart-Based)")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\n차트 데이터에서 Bar1 이후 가격 궤적으로 방향 판정")
    print("-"*70)
    
    # Load data
    signals = load_signals()
    print(f"\nTotal signals: {len(signals)}")
    
    try:
        chart_df = load_chart_data()
        print(f"Chart data loaded: {len(chart_df)} bars")
        print(f"Chart range: {chart_df.index.min()} to {chart_df.index.max()}")
    except Exception as e:
        print(f"Error loading chart: {e}")
        return None
    
    # Filter Storm-IN, Force-qualified
    qualified = [s for s in signals 
                 if classify_storm_coordinate(s) == "STORM_IN"
                 and s.get('force_ratio_30', s.get('force_ratio_20', 1.0)) >= 1.3]
    print(f"Storm-IN qualified: {len(qualified)}")
    
    # Match with chart and get directions
    matched = []
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    for s in qualified:
        ts = s.get('ts')
        entry_price = s.get('entry_price')
        
        if not ts or not entry_price:
            continue
        
        # Parse and check range
        try:
            parsed_ts = pd.to_datetime(ts)
            if parsed_ts.tzinfo is not None:
                parsed_ts = parsed_ts.replace(tzinfo=None)
            
            if parsed_ts < chart_start or parsed_ts > chart_end:
                continue
        except:
            continue
        
        dir_result = get_direction_from_chart(chart_df, ts, entry_price, lookahead=5)
        if dir_result:
            matched.append({
                'signal': s,
                'direction': dir_result
            })
    
    print(f"Matched with chart: {len(matched)}")
    
    if len(matched) < 10:
        print("\n⚠️ Insufficient matched data for analysis")
        return None
    
    # Analyze micro flags vs direction
    print("\n" + "="*70)
    print("MICRO FLAG vs DIRECTION ANALYSIS")
    print("="*70)
    
    micro_flags = ['high_force', 'extreme_force', 'dc_low', 'dc_high', 
                   'delta_positive', 'delta_spike', 'force_dc_align']
    
    results = {}
    
    print("\n| Flag | TRUE→UP | TRUE→DOWN | Skew | FALSE→UP | FALSE→DOWN | Skew |")
    print("|------|---------|-----------|------|----------|------------|------|")
    
    biased_flags = []
    
    for flag in micro_flags:
        true_up = 0
        true_down = 0
        false_up = 0
        false_down = 0
        
        for m in matched:
            mv = get_micro_vector(m['signal'])
            direction = m['direction']['direction']
            
            if direction == 'NEUTRAL':
                continue
            
            if mv.get(flag, False):
                if direction == 'UP':
                    true_up += 1
                else:
                    true_down += 1
            else:
                if direction == 'UP':
                    false_up += 1
                else:
                    false_down += 1
        
        # Calculate skew
        true_total = true_up + true_down
        false_total = false_up + false_down
        
        if true_total > 0:
            true_up_rate = true_up / true_total
            true_skew = (true_up_rate - 0.5) * 200
        else:
            true_skew = 0
        
        if false_total > 0:
            false_up_rate = false_up / false_total
            false_skew = (false_up_rate - 0.5) * 200
        else:
            false_skew = 0
        
        diff_skew = abs(true_skew - false_skew)
        
        bias_marker = "⚡" if diff_skew >= 20 else ""
        print(f"| {flag:15} | {true_up:3}/{true_total:3} | {true_down:3}/{true_total:3} | {true_skew:+5.1f}pp | {false_up:3}/{false_total:3} | {false_down:3}/{false_total:3} | {false_skew:+5.1f}pp | {bias_marker}")
        
        results[flag] = {
            'true_up': true_up,
            'true_down': true_down,
            'true_total': true_total,
            'true_skew': true_skew,
            'false_up': false_up,
            'false_down': false_down,
            'false_total': false_total,
            'false_skew': false_skew,
            'diff_skew': diff_skew
        }
        
        if diff_skew >= 20:
            biased_flags.append(flag)
    
    # Overall direction distribution
    print("\n" + "="*70)
    print("OVERALL DIRECTION DISTRIBUTION")
    print("="*70)
    
    up_count = sum(1 for m in matched if m['direction']['direction'] == 'UP')
    down_count = sum(1 for m in matched if m['direction']['direction'] == 'DOWN')
    neutral_count = sum(1 for m in matched if m['direction']['direction'] == 'NEUTRAL')
    
    total_directional = up_count + down_count
    if total_directional > 0:
        up_rate = up_count / total_directional
        overall_skew = (up_rate - 0.5) * 200
    else:
        overall_skew = 0
    
    print(f"\nUP: {up_count} ({up_count/(up_count+down_count+neutral_count)*100:.1f}%)")
    print(f"DOWN: {down_count} ({down_count/(up_count+down_count+neutral_count)*100:.1f}%)")
    print(f"NEUTRAL: {neutral_count} ({neutral_count/(up_count+down_count+neutral_count)*100:.1f}%)")
    print(f"\nOverall Skew (UP bias): {overall_skew:+.1f}pp")
    
    # Final Verdict
    print("\n" + "="*70)
    print("FINAL VERDICT")
    print("="*70)
    
    if biased_flags:
        verdict = "H1 ACCEPTED"
        interpretation = f"""
방향 분포 비대칭 발견:
- Biased flags: {biased_flags}
- Overall skew: {overall_skew:+.1f}pp

→ 특정 μ-조합에서 방향이 드러나는 조건 존재
→ Conditional Bias Map 생성 가능
"""
    else:
        verdict = "H0 NOT REJECTED"
        interpretation = """
미시 집합으로도 유의미한 방향 비대칭 없음.
→ 방향은 Seat 내부 변수로 결정되지 않음
→ 외부 요인 (빗각, 미세 유동 등) 탐색 필요
"""
    
    print(f"\nVerdict: {verdict}")
    print(interpretation)
    
    # Save
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'EXP_DIR_01_PRIME',
        'matched_count': len(matched),
        'direction_distribution': {
            'up': up_count,
            'down': down_count,
            'neutral': neutral_count,
            'overall_skew': overall_skew
        },
        'micro_results': results,
        'biased_flags': biased_flags,
        'verdict': verdict
    }
    
    output_path = 'v7-grammar-system/analysis/phase_k/exp_dir_01_prime_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_exp_dir_01_prime()
