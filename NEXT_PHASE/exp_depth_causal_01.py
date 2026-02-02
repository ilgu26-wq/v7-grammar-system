"""
EXP-DEPTH-CAUSAL-01: DEPTH 선행성 완전 공격
=============================================
가설 H_D0:
  DEPTH는 원인이 아니라 이미 붕괴된 상태의 후행 그림자다

질문:
  DEPTH 변화가 없는데 ER 붕괴 / ZPOC가 발생할 수 있는가?

판정:
  발생한다 → DEPTH는 원인 ❌
  발생하지 않는다 → DEPTH는 필수 원인 후보 ✅
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List

RESULT_FILE = "v7-grammar-system/results/exp_depth_causal_01.json"

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

def calc_depth_change(depths: List[float], idx: int, lookback: int = 5) -> float:
    if idx < lookback:
        return 0.0
    return abs(depths[idx] - depths[idx - lookback])

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
    print("EXP-DEPTH-CAUSAL-01: DEPTH 선행성 완전 공격")
    print("=" * 70)
    
    print("\n[1] Computing time series...")
    er_series = []
    depth_series = []
    for idx in range(len(df)):
        er_series.append(calc_er(df, idx))
        depth_series.append(calc_depth(df, idx))
    
    df['er'] = er_series
    df['depth'] = depth_series
    
    depth_change = []
    for idx in range(len(df)):
        depth_change.append(calc_depth_change(depth_series, idx, lookback=5))
    df['depth_change'] = depth_change
    
    df['zpoc'] = df['er'] < 0.25
    
    transitions = detect_transitions(depth_series)
    transition_set = set(transitions)
    
    print(f"  Total bars: {len(df)}")
    print(f"  ZPOC bars: {df['zpoc'].sum()}")
    print(f"  TRANSITION events: {len(transitions)}")
    
    print("\n[2] Defining DEPTH stability thresholds...")
    
    depth_change_median = df['depth_change'].median()
    depth_change_q25 = df['depth_change'].quantile(0.25)
    depth_change_q10 = df['depth_change'].quantile(0.10)
    
    print(f"  depth_change median: {depth_change_median:.4f}")
    print(f"  depth_change Q25: {depth_change_q25:.4f}")
    print(f"  depth_change Q10: {depth_change_q10:.4f}")
    
    thresholds = {
        'strict': depth_change_q10,
        'moderate': depth_change_q25,
        'loose': depth_change_median
    }
    
    print("\n" + "=" * 70)
    print("TEST 1: DEPTH 변화 ≈ 0 구간에서 ZPOC 발생률")
    print("=" * 70)
    
    test1_results = {}
    
    for level, threshold in thresholds.items():
        stable_mask = df['depth_change'] < threshold
        stable_df = df[stable_mask]
        unstable_df = df[~stable_mask]
        
        stable_zpoc_rate = stable_df['zpoc'].mean() if len(stable_df) > 0 else 0
        unstable_zpoc_rate = unstable_df['zpoc'].mean() if len(unstable_df) > 0 else 0
        
        ratio = stable_zpoc_rate / unstable_zpoc_rate if unstable_zpoc_rate > 0 else 0
        
        test1_results[level] = {
            'threshold': float(threshold),
            'stable_n': len(stable_df),
            'stable_zpoc_rate': float(stable_zpoc_rate),
            'unstable_n': len(unstable_df),
            'unstable_zpoc_rate': float(unstable_zpoc_rate),
            'ratio': float(ratio)
        }
        
        print(f"\n  {level.upper()} (threshold={threshold:.4f}):")
        print(f"    Stable bars: {len(stable_df)} ({100*len(stable_df)/len(df):.1f}%)")
        print(f"    Stable ZPOC rate: {100*stable_zpoc_rate:.1f}%")
        print(f"    Unstable ZPOC rate: {100*unstable_zpoc_rate:.1f}%")
        print(f"    Ratio (stable/unstable): {ratio:.2f}")
    
    print("\n" + "=" * 70)
    print("TEST 2: DEPTH 변화 없이 ER 붕괴 발생 케이스")
    print("=" * 70)
    
    strict_stable = df['depth_change'] < thresholds['strict']
    er_collapse = df['er'] < 0.20
    
    both = strict_stable & er_collapse
    only_er = er_collapse & ~strict_stable
    only_depth = ~er_collapse & ~strict_stable
    
    n_both = both.sum()
    n_only_er = only_er.sum()
    n_er_total = er_collapse.sum()
    
    er_without_depth_pct = n_both / n_er_total if n_er_total > 0 else 0
    
    print(f"\n  ER collapse (ER < 0.20) cases: {n_er_total}")
    print(f"  ER collapse WITH depth stable: {n_both} ({100*er_without_depth_pct:.1f}%)")
    print(f"  ER collapse WITH depth change: {n_only_er} ({100*(1-er_without_depth_pct):.1f}%)")
    
    test2_results = {
        'er_collapse_total': int(n_er_total),
        'er_with_depth_stable': int(n_both),
        'er_with_depth_change': int(n_only_er),
        'er_without_depth_pct': float(er_without_depth_pct)
    }
    
    print("\n" + "=" * 70)
    print("TEST 3: TRANSITION 직전 DEPTH 변화 선행성")
    print("=" * 70)
    
    W = [-1, -2, -3, -5, -10]
    
    test3_results = {}
    
    print(f"\n{'w':>4} | {'Avg depth_change':>18} | {'Baseline':>12} | {'Ratio':>8}")
    print("-" * 55)
    
    baseline_depth_change = df['depth_change'].mean()
    
    for w in W:
        changes_before_trans = []
        for t in transitions:
            obs_idx = t + w
            if 0 <= obs_idx < len(df):
                changes_before_trans.append(df.iloc[obs_idx]['depth_change'])
        
        avg_change = np.mean(changes_before_trans) if changes_before_trans else 0
        ratio = avg_change / baseline_depth_change if baseline_depth_change > 0 else 0
        
        test3_results[str(w)] = {
            'avg_depth_change': float(avg_change),
            'baseline': float(baseline_depth_change),
            'ratio': float(ratio)
        }
        
        print(f"{w:>4} | {avg_change:>18.4f} | {baseline_depth_change:>12.4f} | {ratio:>8.2f}")
    
    print("\n" + "=" * 70)
    print("TEST 4: DEPTH 변화 → ER 붕괴 vs ER 붕괴 → DEPTH 변화")
    print("=" * 70)
    
    depth_leads_er = 0
    er_leads_depth = 0
    simultaneous = 0
    
    for idx in range(10, len(df) - 1):
        if df.iloc[idx]['er'] < 0.25 and df.iloc[idx - 1]['er'] >= 0.25:
            depth_change_before = df.iloc[idx - 3:idx]['depth_change'].mean()
            depth_change_current = df.iloc[idx]['depth_change']
            
            if depth_change_before > thresholds['moderate']:
                depth_leads_er += 1
            elif depth_change_current > thresholds['moderate']:
                simultaneous += 1
            else:
                er_leads_depth += 1
    
    total_er_starts = depth_leads_er + er_leads_depth + simultaneous
    
    print(f"\n  ER collapse onset events: {total_er_starts}")
    print(f"  DEPTH change leads ER collapse: {depth_leads_er} ({100*depth_leads_er/total_er_starts:.1f}%)")
    print(f"  Simultaneous: {simultaneous} ({100*simultaneous/total_er_starts:.1f}%)")
    print(f"  ER collapse leads (no prior DEPTH change): {er_leads_depth} ({100*er_leads_depth/total_er_starts:.1f}%)")
    
    test4_results = {
        'total_events': int(total_er_starts),
        'depth_leads': int(depth_leads_er),
        'simultaneous': int(simultaneous),
        'er_leads': int(er_leads_depth),
        'depth_leads_pct': float(depth_leads_er / total_er_starts) if total_er_starts > 0 else 0
    }
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    depth_stable_zpoc_exists = test1_results['strict']['stable_zpoc_rate'] > 0.30
    er_without_depth = test2_results['er_without_depth_pct'] > 0.20
    depth_not_leading = test4_results['depth_leads_pct'] < 0.50
    
    h_d0_supported = depth_stable_zpoc_exists and er_without_depth and depth_not_leading
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "zpoc_bars": int(df['zpoc'].sum()),
            "transitions": len(transitions)
        },
        "test1_zpoc_by_depth_stability": test1_results,
        "test2_er_without_depth": test2_results,
        "test3_depth_change_before_transition": test3_results,
        "test4_lead_lag": test4_results,
        "validation": {
            "depth_stable_zpoc_exists": bool(depth_stable_zpoc_exists),
            "er_collapse_without_depth_change": bool(er_without_depth),
            "depth_not_leading": bool(depth_not_leading),
            "H_D0_supported": bool(h_d0_supported)
        }
    }
    
    print(f"\n  DEPTH stable ZPOC exists (>30%): {depth_stable_zpoc_exists} ({100*test1_results['strict']['stable_zpoc_rate']:.1f}%)")
    print(f"  ER collapse without DEPTH change (>20%): {er_without_depth} ({100*test2_results['er_without_depth_pct']:.1f}%)")
    print(f"  DEPTH not leading (<50%): {depth_not_leading} ({100*test4_results['depth_leads_pct']:.1f}%)")
    print(f"\n  H_D0 (DEPTH is shadow, not cause) SUPPORTED: {h_d0_supported}")
    
    if h_d0_supported:
        print("\n  → DEPTH는 원인이 아닌 후행 그림자일 가능성")
    else:
        print("\n  → DEPTH는 필수 원인 후보로 유지")
    
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
