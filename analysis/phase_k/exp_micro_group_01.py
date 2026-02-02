"""
EXP-MICRO-GROUP-01: 미시단위 분리 실험
======================================

목적:
  Revisit 이후 반응 불변성으로 미시단위를 분리한다.

미시단위 후보:
  - Micro-Dir: 방향 붕괴 (DOWN/UP 일관)
  - Micro-Absorb: 손실 억제 (Loss 억제)
  - Micro-Chaos: 불확정 유지 (반응 분산)

묶음 규칙:
  1. Revisit Anchor = True (필수)
  2. 반응 불변성 선택 (하나만)
  3. Regime/Force 제거 후 반응 유지 = 미시단위 성립

테스트:
  Revisit 이후 5~15바 내 반응 분석
"""

import json
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import load_signals, classify_storm_coordinate


def load_chart_data() -> pd.DataFrame:
    chart_path = 'data/chart_combined_full.csv'
    df = pd.read_csv(chart_path)
    df['time'] = pd.to_datetime(df['time'])
    df = df.drop_duplicates(subset=['time'], keep='first')
    df = df.set_index('time').sort_index()
    return df


def calc_revisit_anchor(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> bool:
    """M1: Revisit Anchor - 이전 고점/저점 재도달"""
    if idx < lookback:
        return False
    window = chart_df.iloc[idx-lookback:idx]
    current = chart_df.iloc[idx]
    
    prev_high = window['high'].max()
    prev_low = window['low'].min()
    
    revisit_high = current['high'] >= prev_high * 0.99
    revisit_low = current['low'] <= prev_low * 1.01
    
    return revisit_high or revisit_low


def get_revisit_type(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> str:
    """Revisit 유형: HIGH/LOW/BOTH"""
    if idx < lookback:
        return 'NONE'
    window = chart_df.iloc[idx-lookback:idx]
    current = chart_df.iloc[idx]
    
    prev_high = window['high'].max()
    prev_low = window['low'].min()
    
    revisit_high = current['high'] >= prev_high * 0.99
    revisit_low = current['low'] <= prev_low * 1.01
    
    if revisit_high and revisit_low:
        return 'BOTH'
    elif revisit_high:
        return 'HIGH'
    elif revisit_low:
        return 'LOW'
    return 'NONE'


def analyze_post_revisit_reaction(chart_df: pd.DataFrame, idx: int, 
                                   window_start: int = 5, window_end: int = 15) -> Dict:
    """Revisit 이후 5~15바 반응 분석"""
    if idx + window_end >= len(chart_df):
        return None
    
    entry = chart_df.iloc[idx]['close']
    window = chart_df.iloc[idx+window_start:idx+window_end+1]
    
    max_up = window['high'].max() - entry
    max_down = entry - window['low'].min()
    
    if max_up >= 15 and max_up > max_down * 1.5:
        direction = 'UP'
    elif max_down >= 15 and max_down > max_up * 1.5:
        direction = 'DOWN'
    else:
        direction = 'MIXED'
    
    closes = window['close'].values
    returns = np.diff(closes)
    consistency = np.std(returns) if len(returns) > 1 else 0
    
    if direction != 'MIXED':
        if direction == 'UP':
            dir_consistency = sum(1 for r in returns if r > 0) / len(returns)
        else:
            dir_consistency = sum(1 for r in returns if r < 0) / len(returns)
    else:
        dir_consistency = 0.5
    
    tp_hit = max_up >= 20 or max_down >= 20
    sl_hit = (max_down >= 10 and direction == 'UP') or (max_up >= 10 and direction == 'DOWN')
    
    if tp_hit and not sl_hit:
        outcome = 'WIN'
    elif sl_hit and not tp_hit:
        outcome = 'LOSS'
    elif tp_hit and sl_hit:
        first_tp_bar = None
        first_sl_bar = None
        for i, bar in enumerate(window.itertuples()):
            if first_tp_bar is None:
                if bar.high - entry >= 20 or entry - bar.low >= 20:
                    first_tp_bar = i
            if first_sl_bar is None:
                if direction == 'UP' and entry - bar.low >= 10:
                    first_sl_bar = i
                elif direction == 'DOWN' and bar.high - entry >= 10:
                    first_sl_bar = i
        if first_tp_bar is not None and (first_sl_bar is None or first_tp_bar < first_sl_bar):
            outcome = 'WIN'
        else:
            outcome = 'LOSS'
    else:
        outcome = 'NEUTRAL'
    
    return {
        'direction': direction,
        'max_up': max_up,
        'max_down': max_down,
        'consistency': consistency,
        'dir_consistency': dir_consistency,
        'outcome': outcome
    }


def classify_micro_unit(reaction: Dict, revisit_type: str) -> str:
    """미시단위 분류"""
    direction = reaction['direction']
    outcome = reaction['outcome']
    dir_consistency = reaction['dir_consistency']
    
    if direction == 'DOWN' and dir_consistency >= 0.6:
        return 'Micro-Dir-DOWN'
    elif direction == 'UP' and dir_consistency >= 0.6:
        return 'Micro-Dir-UP'
    elif outcome == 'WIN':
        return 'Micro-Absorb'
    elif direction == 'MIXED' or dir_consistency < 0.5:
        return 'Micro-Chaos'
    else:
        return 'Micro-Undefined'


def run_ablation_test(samples: List[Dict], condition_name: str, 
                      filter_fn) -> Dict:
    """조건 제거 후 반응 유지 테스트"""
    baseline = samples
    ablated = [s for s in samples if not filter_fn(s)]
    
    if len(baseline) == 0 or len(ablated) == 0:
        return {'status': 'NO_DATA'}
    
    baseline_dir = {'DOWN': 0, 'UP': 0, 'MIXED': 0}
    ablated_dir = {'DOWN': 0, 'UP': 0, 'MIXED': 0}
    
    for s in baseline:
        baseline_dir[s['reaction']['direction']] += 1
    for s in ablated:
        ablated_dir[s['reaction']['direction']] += 1
    
    baseline_n = len(baseline)
    ablated_n = len(ablated)
    
    baseline_dist = {k: v/baseline_n for k, v in baseline_dir.items()}
    ablated_dist = {k: v/ablated_n for k, v in ablated_dir.items()}
    
    max_shift = max(abs(baseline_dist[k] - ablated_dist[k]) for k in baseline_dist)
    
    maintained = max_shift < 0.2
    
    return {
        'status': 'TESTED',
        'baseline_n': baseline_n,
        'ablated_n': ablated_n,
        'baseline_dist': baseline_dist,
        'ablated_dist': ablated_dist,
        'max_shift': max_shift,
        'reaction_maintained': maintained
    }


def run_exp_micro_group_01():
    """EXP-MICRO-GROUP-01 실행"""
    print("="*70)
    print("EXP-MICRO-GROUP-01: 미시단위 분리 실험")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\n목적: Revisit 이후 반응 불변성으로 미시단위 분리")
    print("-"*70)
    
    signals = load_signals()
    chart_df = load_chart_data()
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    storm_in_signals = [s for s in signals if classify_storm_coordinate(s) == "STORM_IN"]
    print(f"Storm-IN signals: {len(storm_in_signals)}")
    
    samples = []
    
    for s in storm_in_signals:
        ts = s.get('ts')
        if not ts:
            continue
        
        parsed_ts = pd.to_datetime(ts)
        if parsed_ts.tzinfo is not None:
            parsed_ts = parsed_ts.replace(tzinfo=None)
        
        if parsed_ts < chart_start or parsed_ts > chart_end:
            continue
        
        try:
            idx = chart_df.index.get_indexer([parsed_ts], method='nearest')[0]
        except:
            continue
        
        if idx < 20 or idx + 20 >= len(chart_df):
            continue
        
        if not calc_revisit_anchor(chart_df, idx):
            continue
        
        revisit_type = get_revisit_type(chart_df, idx)
        reaction = analyze_post_revisit_reaction(chart_df, idx)
        
        if reaction is None:
            continue
        
        micro_unit = classify_micro_unit(reaction, revisit_type)
        
        current = chart_df.iloc[idx]
        window = chart_df.iloc[idx-20:idx]
        
        ratio = (current['close'] - current['low']) / (current['high'] - current['close'] + 0.01)
        channel_pct = (current['close'] - window['low'].min()) / (window['high'].max() - window['low'].min() + 0.01) * 100
        
        samples.append({
            'ts': ts,
            'idx': idx,
            'revisit_type': revisit_type,
            'reaction': reaction,
            'micro_unit': micro_unit,
            'ratio': ratio,
            'channel_pct': channel_pct
        })
    
    print(f"Revisit samples: {len(samples)}")
    
    print("\n" + "="*70)
    print("MICRO-UNIT DISTRIBUTION")
    print("="*70)
    
    unit_counts = defaultdict(list)
    for s in samples:
        unit_counts[s['micro_unit']].append(s)
    
    for unit, unit_samples in sorted(unit_counts.items()):
        n = len(unit_samples)
        pct = n / len(samples) * 100
        
        win_count = sum(1 for s in unit_samples if s['reaction']['outcome'] == 'WIN')
        loss_count = sum(1 for s in unit_samples if s['reaction']['outcome'] == 'LOSS')
        win_rate = win_count / n * 100 if n > 0 else 0
        
        avg_consistency = np.mean([s['reaction']['dir_consistency'] for s in unit_samples])
        
        print(f"\n{unit}: N={n} ({pct:.1f}%)")
        print(f"  Win Rate: {win_rate:.1f}% ({win_count}/{n})")
        print(f"  Avg Dir Consistency: {avg_consistency:.2f}")
        
        revisit_types = defaultdict(int)
        for s in unit_samples:
            revisit_types[s['revisit_type']] += 1
        print(f"  Revisit Types: {dict(revisit_types)}")
    
    print("\n" + "="*70)
    print("ABLATION TESTS (Reaction Stability)")
    print("="*70)
    
    ablation_results = {}
    
    print("\n--- Regime (Ratio) Ablation ---")
    high_ratio = run_ablation_test(
        samples, 'High Ratio',
        lambda s: s['ratio'] > 1.5
    )
    ablation_results['regime_ratio'] = high_ratio
    if high_ratio['status'] == 'TESTED':
        print(f"  Remove ratio>1.5: {high_ratio['baseline_n']} → {high_ratio['ablated_n']}")
        print(f"  Max Shift: {high_ratio['max_shift']:.2f}")
        print(f"  Reaction Maintained: {'✅' if high_ratio['reaction_maintained'] else '❌'}")
    
    print("\n--- Channel Ablation ---")
    extreme_channel = run_ablation_test(
        samples, 'Extreme Channel',
        lambda s: s['channel_pct'] > 80 or s['channel_pct'] < 20
    )
    ablation_results['channel_extreme'] = extreme_channel
    if extreme_channel['status'] == 'TESTED':
        print(f"  Remove channel extreme: {extreme_channel['baseline_n']} → {extreme_channel['ablated_n']}")
        print(f"  Max Shift: {extreme_channel['max_shift']:.2f}")
        print(f"  Reaction Maintained: {'✅' if extreme_channel['reaction_maintained'] else '❌'}")
    
    print("\n--- Revisit Type Ablation ---")
    revisit_low = run_ablation_test(
        samples, 'Revisit LOW',
        lambda s: s['revisit_type'] == 'LOW'
    )
    ablation_results['revisit_low'] = revisit_low
    if revisit_low['status'] == 'TESTED':
        print(f"  Remove revisit LOW: {revisit_low['baseline_n']} → {revisit_low['ablated_n']}")
        print(f"  Max Shift: {revisit_low['max_shift']:.2f}")
        print(f"  Reaction Maintained: {'✅' if revisit_low['reaction_maintained'] else '❌'}")
    
    print("\n" + "="*70)
    print("MICRO-UNIT VALIDATION")
    print("="*70)
    
    valid_units = []
    for unit, unit_samples in unit_counts.items():
        if len(unit_samples) < 10:
            print(f"\n{unit}: SKIP (N<10)")
            continue
        
        win_count = sum(1 for s in unit_samples if s['reaction']['outcome'] == 'WIN')
        win_rate = win_count / len(unit_samples)
        
        avg_consistency = np.mean([s['reaction']['dir_consistency'] for s in unit_samples])
        
        is_valid = (
            (avg_consistency >= 0.6) or
            (win_rate >= 0.35 and len(unit_samples) >= 15)
        )
        
        status = '✅ VALID' if is_valid else '❌ INVALID'
        print(f"\n{unit}: {status}")
        print(f"  N={len(unit_samples)}, WinRate={win_rate:.1%}, Consistency={avg_consistency:.2f}")
        
        if is_valid:
            valid_units.append({
                'unit': unit,
                'n': len(unit_samples),
                'win_rate': win_rate,
                'consistency': avg_consistency
            })
    
    print("\n" + "="*70)
    print("FINAL MICRO-UNIT REGISTRY")
    print("="*70)
    
    print(f"\nValidated Micro-Units: {len(valid_units)}")
    for vu in valid_units:
        print(f"  - {vu['unit']}: N={vu['n']}, WinRate={vu['win_rate']:.1%}")
    
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'EXP_MICRO_GROUP_01',
        'total_revisit_samples': len(samples),
        'unit_distribution': {k: len(v) for k, v in unit_counts.items()},
        'ablation_results': ablation_results,
        'valid_units': valid_units
    }
    
    output_path = 'v7-grammar-system/analysis/phase_k/exp_micro_group_01_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_exp_micro_group_01()
