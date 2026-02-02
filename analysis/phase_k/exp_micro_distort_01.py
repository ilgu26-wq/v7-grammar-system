"""
EXP-MICRO-DISTORT-01: 미시단위 비틀기 실험
==========================================

목적:
  같은 Dir 미시단위를 비틀어서 더 세분화된 법칙 분리

비틀기 축:
  1. 시간(Latency): 몇 바 만에 반응 확정?
  2. 경로(Path): 단조 vs V형 vs 계단
  3. 임계(Threshold): Force ±10% 변화 시 반응 유지?

대상: Micro-Dir-DOWN, Micro-Dir-UP
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
    if idx < lookback:
        return False
    window = chart_df.iloc[idx-lookback:idx]
    current = chart_df.iloc[idx]
    prev_high = window['high'].max()
    prev_low = window['low'].min()
    revisit_high = current['high'] >= prev_high * 0.99
    revisit_low = current['low'] <= prev_low * 1.01
    return revisit_high or revisit_low


def analyze_reaction_latency(chart_df: pd.DataFrame, idx: int, 
                              direction: str, threshold: float = 15) -> Dict:
    """DIST-M1: 시간 비틀기 - 반응 확정까지 몇 바?"""
    if idx + 20 >= len(chart_df):
        return None
    
    entry = chart_df.iloc[idx]['close']
    
    for i in range(1, 21):
        bar = chart_df.iloc[idx + i]
        if direction == 'DOWN':
            if entry - bar['low'] >= threshold:
                return {'latency': i, 'category': 'FAST' if i <= 5 else 'DELAYED'}
        else:
            if bar['high'] - entry >= threshold:
                return {'latency': i, 'category': 'FAST' if i <= 5 else 'DELAYED'}
    
    return {'latency': None, 'category': 'NONE'}


def analyze_path_shape(chart_df: pd.DataFrame, idx: int, 
                        direction: str, window: int = 15) -> Dict:
    """DIST-M2: 경로 비틀기 - 단조/V형/계단"""
    if idx + window >= len(chart_df):
        return None
    
    entry = chart_df.iloc[idx]['close']
    bars = chart_df.iloc[idx+1:idx+1+window]
    
    if direction == 'DOWN':
        prices = [entry - bars.iloc[i]['close'] for i in range(len(bars))]
    else:
        prices = [bars.iloc[i]['close'] - entry for i in range(len(bars))]
    
    reversals = 0
    for i in range(1, len(prices)):
        if (prices[i] - prices[i-1]) * (prices[i-1] - prices[max(0, i-2)]) < 0:
            reversals += 1
    
    max_drawdown = 0
    peak = prices[0]
    for p in prices:
        if p > peak:
            peak = p
        drawdown = peak - p
        max_drawdown = max(max_drawdown, drawdown)
    
    if reversals <= 2 and max_drawdown < 5:
        shape = 'MONOTONIC'
    elif max_drawdown >= 10:
        shape = 'V_SHAPE'
    else:
        shape = 'STAIRCASE'
    
    return {
        'reversals': reversals,
        'max_drawdown': max_drawdown,
        'shape': shape
    }


def analyze_threshold_sensitivity(chart_df: pd.DataFrame, idx: int, 
                                   base_force: float, perturbation: float = 0.1) -> Dict:
    """DIST-M3: 임계 비틀기 - Force ±10% 시 반응 유지?"""
    if idx + 15 >= len(chart_df):
        return None
    
    entry = chart_df.iloc[idx]['close']
    future = chart_df.iloc[idx+1:idx+16]
    
    max_up = future['high'].max() - entry
    max_down = entry - future['low'].min()
    
    base_direction = 'UP' if max_up > max_down else 'DOWN'
    
    threshold_high = base_force * (1 + perturbation)
    threshold_low = base_force * (1 - perturbation)
    
    if base_direction == 'UP':
        maintained_high = max_up >= threshold_high
        maintained_low = max_up >= threshold_low
    else:
        maintained_high = max_down >= threshold_high
        maintained_low = max_down >= threshold_low
    
    if maintained_high and maintained_low:
        sensitivity = 'ROBUST'
    elif maintained_low and not maintained_high:
        sensitivity = 'MARGINAL'
    else:
        sensitivity = 'FRAGILE'
    
    return {
        'base_force': base_force,
        'max_move': max(max_up, max_down),
        'sensitivity': sensitivity
    }


def get_direction_and_consistency(chart_df: pd.DataFrame, idx: int, 
                                   window: int = 15) -> Tuple[str, float]:
    """방향과 일관성"""
    if idx + window >= len(chart_df):
        return None, 0
    
    entry = chart_df.iloc[idx]['close']
    future = chart_df.iloc[idx+1:idx+1+window]
    
    max_up = future['high'].max() - entry
    max_down = entry - future['low'].min()
    
    closes = future['close'].values
    returns = np.diff(closes)
    
    if max_up >= 15 and max_up > max_down * 1.5:
        direction = 'UP'
        consistency = sum(1 for r in returns if r > 0) / len(returns)
    elif max_down >= 15 and max_down > max_up * 1.5:
        direction = 'DOWN'
        consistency = sum(1 for r in returns if r < 0) / len(returns)
    else:
        direction = 'MIXED'
        consistency = 0.5
    
    return direction, consistency


def run_exp_micro_distort_01():
    """EXP-MICRO-DISTORT-01 실행"""
    print("="*70)
    print("EXP-MICRO-DISTORT-01: 미시단위 비틀기 실험")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("-"*70)
    
    signals = load_signals()
    chart_df = load_chart_data()
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    storm_in_signals = [s for s in signals if classify_storm_coordinate(s) == "STORM_IN"]
    
    dir_samples = {'DOWN': [], 'UP': []}
    
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
        
        if idx < 20 or idx + 25 >= len(chart_df):
            continue
        
        if not calc_revisit_anchor(chart_df, idx):
            continue
        
        direction, consistency = get_direction_and_consistency(chart_df, idx)
        
        if direction in ['DOWN', 'UP'] and consistency >= 0.6:
            current = chart_df.iloc[idx]
            force = abs(current['close'] - current['open'])
            
            dir_samples[direction].append({
                'ts': ts,
                'idx': idx,
                'consistency': consistency,
                'force': force
            })
    
    print(f"Micro-Dir-DOWN samples: {len(dir_samples['DOWN'])}")
    print(f"Micro-Dir-UP samples: {len(dir_samples['UP'])}")
    
    results = {'DOWN': {}, 'UP': {}}
    
    for direction in ['DOWN', 'UP']:
        samples = dir_samples[direction]
        if len(samples) == 0:
            continue
        
        print(f"\n{'='*70}")
        print(f"DISTORTION ANALYSIS: Micro-Dir-{direction}")
        print(f"{'='*70}")
        
        print("\n--- DIST-M1: Latency (시간 비틀기) ---")
        latency_groups = {'FAST': [], 'DELAYED': [], 'NONE': []}
        
        for s in samples:
            lat = analyze_reaction_latency(chart_df, s['idx'], direction)
            if lat:
                latency_groups[lat['category']].append({
                    **s,
                    'latency': lat['latency']
                })
        
        for cat, group in latency_groups.items():
            if len(group) > 0:
                avg_lat = np.mean([g['latency'] for g in group if g['latency']])
                print(f"  {cat}: N={len(group)}, Avg Latency={avg_lat:.1f} bars")
        
        results[direction]['latency'] = {k: len(v) for k, v in latency_groups.items()}
        
        print("\n--- DIST-M2: Path Shape (경로 비틀기) ---")
        path_groups = {'MONOTONIC': [], 'V_SHAPE': [], 'STAIRCASE': []}
        
        for s in samples:
            path = analyze_path_shape(chart_df, s['idx'], direction)
            if path:
                path_groups[path['shape']].append({
                    **s,
                    'reversals': path['reversals'],
                    'max_drawdown': path['max_drawdown']
                })
        
        for shape, group in path_groups.items():
            if len(group) > 0:
                avg_rev = np.mean([g['reversals'] for g in group])
                avg_dd = np.mean([g['max_drawdown'] for g in group])
                print(f"  {shape}: N={len(group)}, Avg Reversals={avg_rev:.1f}, Avg Drawdown={avg_dd:.1f}pt")
        
        results[direction]['path'] = {k: len(v) for k, v in path_groups.items()}
        
        print("\n--- DIST-M3: Threshold (임계 비틀기) ---")
        sensitivity_groups = {'ROBUST': [], 'MARGINAL': [], 'FRAGILE': []}
        
        for s in samples:
            sens = analyze_threshold_sensitivity(chart_df, s['idx'], 15)
            if sens:
                sensitivity_groups[sens['sensitivity']].append({
                    **s,
                    'max_move': sens['max_move']
                })
        
        for sens, group in sensitivity_groups.items():
            if len(group) > 0:
                avg_move = np.mean([g['max_move'] for g in group])
                print(f"  {sens}: N={len(group)}, Avg Move={avg_move:.1f}pt")
        
        results[direction]['sensitivity'] = {k: len(v) for k, v in sensitivity_groups.items()}
    
    print("\n" + "="*70)
    print("REFINED MICRO-UNIT TAXONOMY")
    print("="*70)
    
    refined_units = []
    
    for direction in ['DOWN', 'UP']:
        samples = dir_samples[direction]
        
        for s in samples:
            lat = analyze_reaction_latency(chart_df, s['idx'], direction)
            path = analyze_path_shape(chart_df, s['idx'], direction)
            sens = analyze_threshold_sensitivity(chart_df, s['idx'], 15)
            
            if lat and path and sens:
                unit_name = f"Micro-{lat['category']}-{direction}"
                if path['shape'] == 'V_SHAPE':
                    unit_name += "-V"
                if sens['sensitivity'] == 'ROBUST':
                    unit_name += "-R"
                
                refined_units.append({
                    'unit': unit_name,
                    'direction': direction,
                    'latency': lat['category'],
                    'path': path['shape'],
                    'sensitivity': sens['sensitivity']
                })
    
    unit_counts = defaultdict(int)
    for u in refined_units:
        unit_counts[u['unit']] += 1
    
    print("\nRefined Units (N≥3):")
    for unit, count in sorted(unit_counts.items(), key=lambda x: -x[1]):
        if count >= 3:
            print(f"  {unit}: N={count}")
            
    stable_units = [u for u, c in unit_counts.items() if c >= 5]
    
    print("\n" + "="*70)
    print("FINAL DISTORTED MICRO-UNITS")
    print("="*70)
    
    print(f"\nStable Units (N≥5): {len(stable_units)}")
    for unit in stable_units:
        print(f"  - {unit}: N={unit_counts[unit]}")
    
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'EXP_MICRO_DISTORT_01',
        'sample_counts': {
            'DOWN': len(dir_samples['DOWN']),
            'UP': len(dir_samples['UP'])
        },
        'distortion_results': results,
        'refined_unit_counts': dict(unit_counts),
        'stable_units': stable_units
    }
    
    output_path = 'v7-grammar-system/analysis/phase_k/exp_micro_distort_01_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_exp_micro_distort_01()
