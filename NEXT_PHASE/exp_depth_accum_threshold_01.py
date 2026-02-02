"""
EXP-DEPTH-ACCUM-THRESHOLD-01: DEPTH 누적 임계 검증
=====================================================
질문: DEPTH 변화는 누적 에너지가 임계값을 넘을 때만 발생하는가?

정의:
  depth_energy_t = |depth_t - depth_{t-1}| * range_weight
  cum_depth_energy = rolling sum of depth_energy

판정:
  상위 분위수에서만 TRANSITION → DEPTH = 누적 임계 방출
  전 분위수 균등 → DEPTH = 외생적
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List

RESULT_FILE = "v7-grammar-system/results/exp_depth_accum_threshold_01.json"

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
    print("EXP-DEPTH-ACCUM-THRESHOLD-01: DEPTH 누적 임계 검증")
    print("=" * 70)
    
    print("\n[1] Computing time series...")
    er_series = []
    depth_series = []
    for idx in range(len(df)):
        er_series.append(calc_er(df, idx))
        depth_series.append(calc_depth(df, idx))
    
    df['er'] = er_series
    df['depth'] = depth_series
    df['zpoc'] = df['er'] < 0.25
    
    df['range'] = df['high'] - df['low']
    median_range = df['range'].median()
    df['range_weight'] = df['range'] / median_range
    
    depth_change = [0] + [abs(depth_series[i] - depth_series[i-1]) for i in range(1, len(depth_series))]
    df['depth_change'] = depth_change
    
    df['depth_energy'] = df['depth_change'] * df['range_weight']
    
    windows = [20, 50, 100]
    for w in windows:
        df[f'cum_depth_energy_{w}'] = df['depth_energy'].rolling(w).sum().fillna(0)
    
    transitions = detect_transitions(depth_series)
    transition_set = set(transitions)
    df['is_transition'] = df.index.isin(transition_set)
    
    print(f"  Total bars: {len(df)}")
    print(f"  TRANSITION events: {len(transitions)}")
    
    print("\n[2] Analyzing by cum_depth_energy quantiles...")
    
    results_by_window = {}
    
    for w in windows:
        col = f'cum_depth_energy_{w}'
        
        df[f'{col}_q'] = pd.qcut(df[col], q=5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'], duplicates='drop')
        
        quantile_results = {}
        
        print(f"\n  Window = {w} bars:")
        print(f"  {'Quantile':<10} | {'TRANS rate':>12} | {'ZPOC rate':>12} | {'ER collapse':>12}")
        print("  " + "-" * 55)
        
        for q in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']:
            q_df = df[df[f'{col}_q'] == q]
            
            trans_rate = q_df['is_transition'].mean() if len(q_df) > 0 else 0
            zpoc_rate = q_df['zpoc'].mean() if len(q_df) > 0 else 0
            er_collapse = (q_df['er'] < 0.20).mean() if len(q_df) > 0 else 0
            
            quantile_results[q] = {
                'n': len(q_df),
                'trans_rate': float(trans_rate),
                'zpoc_rate': float(zpoc_rate),
                'er_collapse_rate': float(er_collapse)
            }
            
            print(f"  {q:<10} | {100*trans_rate:>11.2f}% | {100*zpoc_rate:>11.2f}% | {100*er_collapse:>11.2f}%")
        
        q5_trans = quantile_results['Q5']['trans_rate']
        q1_trans = quantile_results['Q1']['trans_rate']
        lift = q5_trans / q1_trans if q1_trans > 0 else 0
        
        results_by_window[str(w)] = {
            'quantiles': quantile_results,
            'q5_q1_lift': float(lift)
        }
        
        print(f"  Q5/Q1 Lift: {lift:.2f}")
    
    print("\n[3] Threshold detection...")
    
    best_window = max(windows, key=lambda w: results_by_window[str(w)]['q5_q1_lift'])
    col = f'cum_depth_energy_{best_window}'
    
    thresholds = [0.5, 0.6, 0.7, 0.8, 0.9]
    threshold_results = {}
    
    print(f"\n  Best window: {best_window} bars")
    print(f"  {'Threshold':<12} | {'Above rate':>12} | {'Trans|Above':>12} | {'Trans|Below':>12} | {'Lift':>8}")
    print("  " + "-" * 65)
    
    for t in thresholds:
        threshold_value = df[col].quantile(t)
        above = df[col] >= threshold_value
        below = ~above
        
        trans_above = df[above]['is_transition'].mean() if above.sum() > 0 else 0
        trans_below = df[below]['is_transition'].mean() if below.sum() > 0 else 0
        lift = trans_above / trans_below if trans_below > 0 else 0
        
        threshold_results[str(t)] = {
            'value': float(threshold_value),
            'trans_above': float(trans_above),
            'trans_below': float(trans_below),
            'lift': float(lift)
        }
        
        print(f"  Q{t:<11} | {100*(1-t):>11.1f}% | {100*trans_above:>11.2f}% | {100*trans_below:>11.2f}% | {lift:>8.2f}")
    
    print("\n[4] Random shift test (반증)...")
    
    np.random.seed(42)
    shifts = np.random.randint(-50, 51, size=len(transitions))
    shifted_trans = [(t + s) % len(df) for t, s in zip(transitions, shifts)]
    
    original_cum_energy = df.loc[transitions, col].mean() if transitions else 0
    shifted_cum_energy = df.loc[shifted_trans, col].mean() if shifted_trans else 0
    
    energy_preserved = shifted_cum_energy / original_cum_energy if original_cum_energy > 0 else 0
    
    print(f"\n  Original avg cum_energy at TRANSITION: {original_cum_energy:.4f}")
    print(f"  Shifted avg cum_energy: {shifted_cum_energy:.4f}")
    print(f"  Preservation ratio: {energy_preserved:.2f}")
    
    random_shift_collapsed = energy_preserved < 0.8
    print(f"  Random shift collapsed: {random_shift_collapsed}")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    best_lift = results_by_window[str(best_window)]['q5_q1_lift']
    threshold_significant = any(v['lift'] > 1.5 for v in threshold_results.values())
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "transitions": len(transitions),
            "best_window": best_window
        },
        "by_window": results_by_window,
        "threshold_analysis": threshold_results,
        "random_shift": {
            "original_energy": float(original_cum_energy),
            "shifted_energy": float(shifted_cum_energy),
            "preservation": float(energy_preserved),
            "collapsed": bool(random_shift_collapsed)
        },
        "validation": {
            "q5_q1_lift_significant": bool(best_lift > 1.5),
            "threshold_significant": bool(threshold_significant),
            "random_shift_collapsed": bool(random_shift_collapsed),
            "DEPTH_ACCUMULATION_CAUSAL": bool(best_lift > 1.5 and random_shift_collapsed)
        }
    }
    
    print(f"\n  Q5/Q1 Lift significant (>1.5): {results['validation']['q5_q1_lift_significant']} ({best_lift:.2f})")
    print(f"  Threshold significant: {threshold_significant}")
    print(f"  Random shift collapsed: {random_shift_collapsed}")
    print(f"\n  DEPTH ACCUMULATION CAUSAL: {results['validation']['DEPTH_ACCUMULATION_CAUSAL']}")
    
    if results['validation']['DEPTH_ACCUMULATION_CAUSAL']:
        print("\n  → DEPTH = 누적 임계 방출 메커니즘")
    else:
        print("\n  → DEPTH 누적 인과성 미확정")
    
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
