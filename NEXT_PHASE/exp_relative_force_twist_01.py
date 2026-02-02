"""
EXP-RELATIVE-FORCE-TWIST-01: 아인슈타인식 상대 인과 공격
=========================================================
질문: force_ratio velocity는 절대적 원인인가,
     아니면 상대적 기준에서만 의미를 갖는가?

정의:
  absolute_velocity = |d(force_ratio)/dt|
  relative_velocity = (velocity - μ_v) / σ_v  (local z-score)

판정:
  상대 기준만 구조 유지 → 상대성 원인 확정
  절대 기준만 유지 → 뉴턴적 원인
  둘 다 유지 → 혼합 인과
  둘 다 붕괴 → 원인 재정의 필요
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List
from scipy.spatial.distance import cosine

RESULT_FILE = "v7-grammar-system/results/exp_relative_force_twist_01.json"

def calc_er(df: pd.DataFrame, idx: int, lookback: int = 10) -> float:
    start = max(0, idx - lookback + 1)
    window = df.iloc[start:idx + 1]
    if len(window) < 2:
        return 0.5
    price_change = abs(window.iloc[-1]['close'] - window.iloc[0]['close'])
    bar_changes = abs(window['close'].diff().dropna()).sum()
    if bar_changes < 0.01:
        return 1.0
    return min(1.0, price_change / bar_changes)

def calc_depth(df: pd.DataFrame, idx: int, lookback: int = 20) -> float:
    start = max(0, idx - lookback + 1)
    window = df.iloc[start:idx + 1]
    if len(window) < 2:
        return 0.5
    high_20 = window['high'].max()
    low_20 = window['low'].min()
    range_20 = high_20 - low_20
    if range_20 < 0.01:
        return 0.5
    close = df.iloc[idx]['close']
    return (high_20 - close) / range_20

def normalize_series(series: pd.Series) -> pd.Series:
    min_val = series.min()
    max_val = series.max()
    if max_val - min_val < 0.0001:
        return pd.Series([0.5] * len(series))
    return (series - min_val) / (max_val - min_val)

def detect_transitions(depth_series: List[float]) -> List[int]:
    events = []
    if len(depth_series) < 10:
        return events
    prev_side = "LOW" if depth_series[5] < 0.5 else "HIGH"
    for i in range(10, len(depth_series)):
        curr_side = "LOW" if depth_series[i] < 0.5 else "HIGH"
        if curr_side != prev_side:
            events.append(i)
            prev_side = curr_side
    return events

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-RELATIVE-FORCE-TWIST-01: 상대성 인과 검증")
    print("=" * 70)
    
    print("\n[1] Computing base metrics...")
    
    df['range'] = df['high'] - df['low']
    df['buyer_power'] = df['close'] - df['low']
    df['seller_power'] = df['high'] - df['close']
    df['force_ratio'] = df['buyer_power'] / df['seller_power'].replace(0, 0.001)
    df['force_ratio'] = df['force_ratio'].clip(0.01, 100)
    
    df['abs_velocity'] = df['force_ratio'].diff().abs().fillna(0)
    
    lookback = 20
    df['local_mean'] = df['abs_velocity'].rolling(lookback, min_periods=5).mean()
    df['local_std'] = df['abs_velocity'].rolling(lookback, min_periods=5).std()
    df['local_std'] = df['local_std'].replace(0, 0.001)
    
    df['rel_velocity'] = (df['abs_velocity'] - df['local_mean']) / df['local_std']
    df['rel_velocity'] = df['rel_velocity'].fillna(0)
    
    er_series = [calc_er(df, i) for i in range(len(df))]
    depth_series = [calc_depth(df, i) for i in range(len(df))]
    
    df['er'] = er_series
    df['depth'] = depth_series
    df['er_collapse'] = df['er'] < 0.20
    
    transitions = detect_transitions(depth_series)
    df['is_transition'] = df.index.isin(set(transitions))
    
    print(f"  Total bars: {len(df)}")
    print(f"  TRANSITION events: {len(transitions)}")
    
    print("\n[2] Comparing absolute vs relative velocity...")
    
    abs_q90 = df['abs_velocity'].quantile(0.90)
    rel_q90 = df['rel_velocity'].quantile(0.90)
    
    abs_high = df['abs_velocity'] >= abs_q90
    rel_high = df['rel_velocity'] >= rel_q90
    
    baseline_er = df['er_collapse'].mean()
    baseline_trans = df['is_transition'].mean()
    
    abs_er = df[abs_high]['er_collapse'].mean() if abs_high.sum() > 0 else 0
    rel_er = df[rel_high]['er_collapse'].mean() if rel_high.sum() > 0 else 0
    
    abs_trans = df[abs_high]['is_transition'].mean() if abs_high.sum() > 0 else 0
    rel_trans = df[rel_high]['is_transition'].mean() if rel_high.sum() > 0 else 0
    
    abs_er_lift = abs_er / baseline_er if baseline_er > 0 else 0
    rel_er_lift = rel_er / baseline_er if baseline_er > 0 else 0
    abs_trans_lift = abs_trans / baseline_trans if baseline_trans > 0 else 0
    rel_trans_lift = rel_trans / baseline_trans if baseline_trans > 0 else 0
    
    print(f"\n  {'Metric':<15} | {'Absolute':>12} | {'Relative':>12} | {'Winner':>10}")
    print("  " + "-" * 55)
    print(f"  {'ER collapse':<15} | {abs_er_lift:>11.2f}x | {rel_er_lift:>11.2f}x | {'REL' if rel_er_lift > abs_er_lift else 'ABS':>10}")
    print(f"  {'TRANSITION':<15} | {abs_trans_lift:>11.2f}x | {rel_trans_lift:>11.2f}x | {'REL' if rel_trans_lift > abs_trans_lift else 'ABS':>10}")
    
    print("\n[3] Random shift test (frame invariance)...")
    
    np.random.seed(42)
    
    er_collapse_events = df[df['er_collapse'] & ~df['er_collapse'].shift(1).fillna(False)].index.tolist()
    
    shifts = np.random.randint(-50, 51, size=len(er_collapse_events))
    shifted_indices = [(i + s) % len(df) for i, s in zip(er_collapse_events, shifts)]
    
    orig_abs = df.loc[er_collapse_events, 'abs_velocity'].mean() if er_collapse_events else 0
    orig_rel = df.loc[er_collapse_events, 'rel_velocity'].mean() if er_collapse_events else 0
    
    shift_abs = df.iloc[shifted_indices]['abs_velocity'].mean() if shifted_indices else 0
    shift_rel = df.iloc[shifted_indices]['rel_velocity'].mean() if shifted_indices else 0
    
    abs_preserved = shift_abs / orig_abs if orig_abs > 0 else 0
    rel_preserved = shift_rel / orig_rel if orig_rel > 0 else 0
    
    abs_collapsed = abs_preserved < 0.85 or abs_preserved > 1.15
    rel_collapsed = rel_preserved < 0.85 or rel_preserved > 1.15
    
    print(f"\n  {'Metric':<20} | {'Original':>10} | {'Shifted':>10} | {'Preserved':>10} | {'Collapsed':>10}")
    print("  " + "-" * 70)
    print(f"  {'abs_velocity':<20} | {orig_abs:>10.4f} | {shift_abs:>10.4f} | {abs_preserved:>10.2f} | {str(abs_collapsed):>10}")
    print(f"  {'rel_velocity':<20} | {orig_rel:>10.4f} | {shift_rel:>10.4f} | {rel_preserved:>10.2f} | {str(rel_collapsed):>10}")
    
    print("\n[4] Frame shift test (temporal displacement)...")
    
    frame_shifts = [5, 10, 20, 50]
    frame_results = {}
    
    for fs in frame_shifts:
        df[f'rel_velocity_shift{fs}'] = df['rel_velocity'].shift(fs).fillna(0)
        
        shifted_rel_high = df[f'rel_velocity_shift{fs}'] >= rel_q90
        shifted_rel_er = df[shifted_rel_high]['er_collapse'].mean() if shifted_rel_high.sum() > 0 else 0
        shifted_rel_lift = shifted_rel_er / baseline_er if baseline_er > 0 else 0
        
        frame_results[fs] = {
            'lift': float(shifted_rel_lift),
            'preserved': shifted_rel_lift > rel_er_lift * 0.7
        }
    
    print(f"\n  {'Frame shift':<15} | {'Lift':>10} | {'Preserved':>10}")
    print("  " + "-" * 40)
    for fs, data in frame_results.items():
        print(f"  {fs:<15} | {data['lift']:>10.2f} | {str(data['preserved']):>10}")
    
    print("\n[5] State-conditional relative velocity...")
    
    df['depth_zone'] = pd.cut(df['depth'], bins=[0, 0.3, 0.7, 1.0], labels=['LOW', 'MID', 'HIGH'])
    df['er_zone'] = pd.cut(df['er'], bins=[0, 0.25, 0.5, 1.0], labels=['COLLAPSE', 'WEAK', 'STRONG'])
    
    state_results = {}
    
    print(f"\n  {'State':<20} | {'Rel lift':>10} | {'Abs lift':>10} | {'Winner':>10}")
    print("  " + "-" * 55)
    
    for depth_z in ['LOW', 'MID', 'HIGH']:
        state_mask = df['depth_zone'] == depth_z
        if state_mask.sum() < 100:
            continue
        
        state_df = df[state_mask]
        state_baseline = state_df['er_collapse'].mean()
        
        state_abs_high = state_df['abs_velocity'] >= abs_q90
        state_rel_high = state_df['rel_velocity'] >= rel_q90
        
        state_abs_er = state_df[state_abs_high]['er_collapse'].mean() if state_abs_high.sum() > 0 else 0
        state_rel_er = state_df[state_rel_high]['er_collapse'].mean() if state_rel_high.sum() > 0 else 0
        
        state_abs_lift = state_abs_er / state_baseline if state_baseline > 0 else 0
        state_rel_lift = state_rel_er / state_baseline if state_baseline > 0 else 0
        
        state_results[f'depth_{depth_z}'] = {
            'abs_lift': float(state_abs_lift),
            'rel_lift': float(state_rel_lift),
            'winner': 'REL' if state_rel_lift > state_abs_lift else 'ABS'
        }
        
        print(f"  {'depth_' + depth_z:<20} | {state_rel_lift:>10.2f} | {state_abs_lift:>10.2f} | {state_results[f'depth_{depth_z}']['winner']:>10}")
    
    print("\n" + "=" * 70)
    print("SUMMARY: RELATIVITY TEST")
    print("=" * 70)
    
    rel_wins_er = rel_er_lift > abs_er_lift
    rel_wins_trans = rel_trans_lift > abs_trans_lift
    rel_more_stable = not rel_collapsed or (not rel_collapsed and abs_collapsed)
    rel_state_invariant = sum(1 for s in state_results.values() if s['winner'] == 'REL') > len(state_results) / 2
    
    relativity_confirmed = (rel_wins_er or rel_wins_trans) and rel_more_stable
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "transitions": len(transitions),
            "er_collapse_events": len(er_collapse_events)
        },
        "predictive_power": {
            "absolute": {
                "er_lift": float(abs_er_lift),
                "trans_lift": float(abs_trans_lift)
            },
            "relative": {
                "er_lift": float(rel_er_lift),
                "trans_lift": float(rel_trans_lift)
            }
        },
        "random_shift": {
            "absolute": {
                "preserved": float(abs_preserved),
                "collapsed": bool(abs_collapsed)
            },
            "relative": {
                "preserved": float(rel_preserved),
                "collapsed": bool(rel_collapsed)
            }
        },
        "frame_shift": frame_results,
        "state_conditional": state_results,
        "validation": {
            "rel_wins_er": bool(rel_wins_er),
            "rel_wins_trans": bool(rel_wins_trans),
            "rel_more_stable": bool(rel_more_stable),
            "rel_state_invariant": bool(rel_state_invariant),
            "RELATIVITY_CONFIRMED": bool(relativity_confirmed)
        }
    }
    
    print(f"\n  Relative wins ER prediction: {rel_wins_er}")
    print(f"  Relative wins TRANSITION prediction: {rel_wins_trans}")
    print(f"  Relative more stable under shift: {rel_more_stable}")
    print(f"  Relative state-invariant: {rel_state_invariant}")
    print(f"\n  RELATIVITY CONFIRMED: {relativity_confirmed}")
    
    if relativity_confirmed:
        print("\n  → 원인은 절대 크기가 아닌 '평균 대비 상대적 이탈'")
        print("  → 아인슈타인식 상대성 인과 확정")
    else:
        print("\n  → 혼합 인과 또는 절대 인과")
    
    return results

def main():
    data_paths = [
        "data/chart_combined_full.csv",
        "v7-grammar-system/data/chart_combined_full.csv"
    ]
    
    df = None
    for path in data_paths:
        if os.path.exists(path):
            df = pd.read_csv(path)
            print(f"Loaded: {path}")
            break
    
    if df is None:
        print("No data file found.")
        return
    
    results = run_experiment(df)
    
    os.makedirs(os.path.dirname(RESULT_FILE), exist_ok=True)
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {RESULT_FILE}")
    
    return results

if __name__ == "__main__":
    main()
