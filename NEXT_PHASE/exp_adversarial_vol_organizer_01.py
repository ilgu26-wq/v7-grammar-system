"""
EXP-ADVERSARIAL-VOL-ORGANIZER-01: 비방향 주최자 (변동성/감마) 검증
====================================================================
가설 H_A3:
  Directional organizer는 부재해도
  Volatility organizer(변동성 주체)는 존재할 수 있다.

검증:
  Test 1: ZPOC는 변동성이 줄어드는가?
  Test 2: ZPOC에서 꼬리(진폭)만 남는가?
  Test 3: TRANSITION 직전 변동성이 사전 상승하나?
  Test 4: Range 통제 후에도 구조가 남나?
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List

RESULT_FILE = "v7-grammar-system/results/exp_adversarial_vol_organizer_01.json"

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
    print("EXP-ADVERSARIAL-VOL-ORGANIZER-01: 비방향 주최자 검증")
    print("=" * 70)
    
    print("\n[0] Computing volatility metrics...")
    
    df['range'] = df['high'] - df['low']
    df['abs_ret'] = abs(df['close'] - df['close'].shift(1))
    df['body'] = abs(df['close'] - df['open'])
    
    df['prev_close'] = df['close'].shift(1)
    df['tr'] = df.apply(lambda r: max(
        r['high'] - r['low'],
        abs(r['high'] - r['prev_close']) if pd.notna(r['prev_close']) else r['high'] - r['low'],
        abs(r['low'] - r['prev_close']) if pd.notna(r['prev_close']) else r['high'] - r['low']
    ), axis=1)
    
    df['dirless_vol'] = df['tr'] - df['body']
    df['churn'] = df['tr'] / (df['abs_ret'] + 0.01)
    
    range_20 = df['range'].rolling(20).max() - df['range'].rolling(20).min()
    range_20 = range_20.replace(0, 1)
    df['nr'] = df['range'] / (range_20 + 0.01)
    
    print("\n[1] Computing ER, depth, ZPOC...")
    er_series = []
    depth_series = []
    for idx in range(len(df)):
        er_series.append(calc_er(df, idx))
        depth_series.append(calc_depth(df, idx))
    
    df['er'] = er_series
    df['depth'] = depth_series
    df['zpoc'] = df['er'] < 0.25
    
    transitions = detect_transitions(depth_series)
    transition_set = set(transitions)
    print(f"  ZPOC bars: {df['zpoc'].sum()} ({100*df['zpoc'].mean():.1f}%)")
    print(f"  TRANSITION events: {len(transitions)}")
    
    df_clean = df.dropna().copy()
    
    print("\n" + "=" * 70)
    print("TEST 1: ZPOC에서 변동성이 줄어드는가?")
    print("=" * 70)
    
    zpoc_df = df_clean[df_clean['zpoc']]
    normal_df = df_clean[~df_clean['zpoc']]
    
    metrics = ['range', 'tr', 'abs_ret', 'dirless_vol', 'churn', 'nr']
    test1_results = {}
    
    print(f"\n{'Metric':<15} | {'ZPOC mean':>12} | {'Normal mean':>12} | {'Ratio':>8} | {'Effect':>10}")
    print("-" * 70)
    
    for metric in metrics:
        zpoc_mean = zpoc_df[metric].mean()
        normal_mean = normal_df[metric].mean()
        ratio = zpoc_mean / normal_mean if normal_mean > 0 else 0
        
        if ratio > 1.1:
            effect = "INCREASE"
        elif ratio < 0.9:
            effect = "DECREASE"
        else:
            effect = "STABLE"
        
        test1_results[metric] = {
            'zpoc_mean': float(zpoc_mean),
            'normal_mean': float(normal_mean),
            'ratio': float(ratio),
            'effect': effect
        }
        
        print(f"{metric:<15} | {zpoc_mean:>12.3f} | {normal_mean:>12.3f} | {ratio:>8.2f} | {effect:>10}")
    
    print("\n" + "=" * 70)
    print("TEST 2: ZPOC에서 꼬리(진폭)만 남는가?")
    print("=" * 70)
    
    dirless_increase = test1_results['dirless_vol']['ratio'] > 1.05
    churn_increase = test1_results['churn']['ratio'] > 1.05
    abs_ret_decrease = test1_results['abs_ret']['ratio'] < 0.95
    
    tail_pattern = dirless_increase and churn_increase
    
    print(f"\n  dirless_vol increase: {dirless_increase} (ratio: {test1_results['dirless_vol']['ratio']:.2f})")
    print(f"  churn increase: {churn_increase} (ratio: {test1_results['churn']['ratio']:.2f})")
    print(f"  abs_ret decrease: {abs_ret_decrease} (ratio: {test1_results['abs_ret']['ratio']:.2f})")
    print(f"\n  TAIL PATTERN (꼬리만 남음): {tail_pattern}")
    
    print("\n" + "=" * 70)
    print("TEST 3: TRANSITION 직전 변동성 사전 상승?")
    print("=" * 70)
    
    W = [-1, -2, -3, -5, -10]
    vol_metrics = ['churn', 'dirless_vol', 'tr']
    q_threshold = 0.7
    
    test3_results = {}
    
    for metric in vol_metrics:
        threshold = df_clean[metric].quantile(q_threshold)
        test3_results[metric] = []
        
        for w in W:
            event_count = 0
            event_high = 0
            
            for t in transitions:
                obs_idx = t + w
                if obs_idx < 0 or obs_idx >= len(df_clean):
                    continue
                if obs_idx not in df_clean.index:
                    continue
                
                event_count += 1
                if df_clean.loc[obs_idx, metric] > threshold:
                    event_high += 1
            
            base_rate = (df_clean[metric] > threshold).mean()
            event_rate = event_high / event_count if event_count > 0 else 0
            lift = event_rate / base_rate if base_rate > 0 else 0
            
            test3_results[metric].append({
                'w': w,
                'event_rate': float(event_rate),
                'base_rate': float(base_rate),
                'lift': float(lift)
            })
    
    print(f"\n{'w':>4} | {'Lift_churn':>12} | {'Lift_dirless':>12} | {'Lift_tr':>12}")
    print("-" * 55)
    for i, w in enumerate(W):
        l_churn = test3_results['churn'][i]['lift']
        l_dirless = test3_results['dirless_vol'][i]['lift']
        l_tr = test3_results['tr'][i]['lift']
        print(f"{w:>4} | {l_churn:>12.2f} | {l_dirless:>12.2f} | {l_tr:>12.2f}")
    
    vol_precedence = any(test3_results['churn'][i]['lift'] > 1.2 for i in range(len(W)) if W[i] <= -3)
    
    print("\n" + "=" * 70)
    print("TEST 4: Range 통제 후에도 구조가 남나?")
    print("=" * 70)
    
    df_clean['nr_quantile'] = pd.qcut(df_clean['nr'], q=3, labels=['Low', 'Mid', 'High'], duplicates='drop')
    
    test4_results = {}
    
    for q in ['Low', 'Mid', 'High']:
        q_df = df_clean[df_clean['nr_quantile'] == q]
        
        q_zpoc = q_df[q_df['zpoc']]
        q_normal = q_df[~q_df['zpoc']]
        
        if len(q_zpoc) > 0 and len(q_normal) > 0:
            delta_churn = q_zpoc['churn'].mean() - q_normal['churn'].mean()
            delta_dirless = q_zpoc['dirless_vol'].mean() - q_normal['dirless_vol'].mean()
        else:
            delta_churn = 0
            delta_dirless = 0
        
        test4_results[q] = {
            'n_zpoc': len(q_zpoc),
            'n_normal': len(q_normal),
            'delta_churn': float(delta_churn),
            'delta_dirless': float(delta_dirless)
        }
        
        print(f"  {q}: ZPOC={len(q_zpoc)}, Normal={len(q_normal)}, Δchurn={delta_churn:.2f}, Δdirless={delta_dirless:.2f}")
    
    structure_survives = all(v['delta_churn'] > 0 or v['delta_dirless'] > 0 for v in test4_results.values())
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    h_a3_supported = tail_pattern or vol_precedence
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "zpoc_bars": int(df['zpoc'].sum()),
            "transitions": len(transitions)
        },
        "test1_vol_by_state": test1_results,
        "test2_tail_pattern": {
            "dirless_increase": bool(dirless_increase),
            "churn_increase": bool(churn_increase),
            "tail_pattern_detected": bool(tail_pattern)
        },
        "test3_vol_precedence": test3_results,
        "test4_controlled": test4_results,
        "validation": {
            "tail_pattern": bool(tail_pattern),
            "vol_precedence": bool(vol_precedence),
            "structure_survives_control": bool(structure_survives),
            "H_A3_supported": bool(h_a3_supported)
        }
    }
    
    print(f"\n  Tail pattern (꼬리만 남음): {tail_pattern}")
    print(f"  Vol precedence (변동성 선행): {vol_precedence}")
    print(f"  Structure survives NR control: {structure_survives}")
    print(f"\n  H_A3 (Volatility Organizer) SUPPORTED: {h_a3_supported}")
    
    if h_a3_supported:
        print("\n  → 방향 주최자는 부재하지만, 변동성/감마 주최자는 존재 가능성 있음")
    else:
        print("\n  → ZPOC는 완전한 결정 불능 상태 (방향/변동성 모두 붕괴)")
    
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
