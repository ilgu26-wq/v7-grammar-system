"""
EXP-ADVERSARIAL-VOLUME-01: Volume 통제 후 ER 붕괴 검증
========================================================
비틀기 가설 H_A1:
  "주최자 부재가 아니라 그냥 거래량 줄어서 ER 떨어진 거 아님?"

실험:
  1. Volume proxy (bar range) 분위수 계산
  2. 동일 volume 분위수 내에서 ER 분포 비교
  3. Volume 통제 후에도 ER 붕괴 패턴 유지되는지 확인

판정:
  ER 붕괴가 volume 통제 후에도 유지 → H_A1 기각 (현 구조 유지)
  붕괴 사라짐 → 현 논리 붕괴
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List

RESULT_FILE = "v7-grammar-system/results/exp_adversarial_volume_01.json"

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
    print("EXP-ADVERSARIAL-VOLUME-01: Volume 통제 후 ER 붕괴 검증")
    print("=" * 70)
    
    df['bar_range'] = df['high'] - df['low']
    df['bar_body'] = abs(df['close'] - df['open'])
    df['volume_proxy'] = df['bar_range']
    
    print(f"\n  Using bar_range as volume proxy")
    print(f"  Range stats: min={df['bar_range'].min():.2f}, max={df['bar_range'].max():.2f}, median={df['bar_range'].median():.2f}")
    
    print("\n[1] Computing ER and depth...")
    er_series = []
    depth_series = []
    for idx in range(len(df)):
        er_series.append(calc_er(df, idx))
        depth_series.append(calc_depth(df, idx))
    
    df['er'] = er_series
    df['depth'] = depth_series
    df['organizer_absent'] = df['er'] < 0.25
    
    print("\n[2] Creating volume quantiles...")
    df['volume_quantile'] = pd.qcut(df['volume_proxy'], q=5, labels=['Q1_low', 'Q2', 'Q3', 'Q4', 'Q5_high'])
    
    for q in df['volume_quantile'].unique():
        q_df = df[df['volume_quantile'] == q]
        print(f"  {q}: N={len(q_df)}, avg_range={q_df['bar_range'].mean():.2f}")
    
    print("\n[3] ER distribution by volume quantile...")
    
    quantile_stats = {}
    
    print("\n  Without control (global):")
    global_er_low_rate = (df['er'] < 0.25).mean()
    global_er_high_rate = (df['er'] > 0.35).mean()
    print(f"    ER < 0.25: {100*global_er_low_rate:.1f}%")
    print(f"    ER > 0.35: {100*global_er_high_rate:.1f}%")
    
    print("\n  By volume quantile:")
    for q in ['Q1_low', 'Q2', 'Q3', 'Q4', 'Q5_high']:
        q_df = df[df['volume_quantile'] == q]
        er_low_rate = (q_df['er'] < 0.25).mean()
        er_high_rate = (q_df['er'] > 0.35).mean()
        avg_er = q_df['er'].mean()
        
        quantile_stats[q] = {
            'n': len(q_df),
            'er_low_rate': float(er_low_rate),
            'er_high_rate': float(er_high_rate),
            'avg_er': float(avg_er)
        }
        
        print(f"    {q}: ER<0.25={100*er_low_rate:.1f}%, ER>0.35={100*er_high_rate:.1f}%, avg_ER={avg_er:.3f}")
    
    print("\n[4] ZPOC occurrence by volume quantile...")
    
    transitions = detect_transitions(depth_series)
    transition_set = set(transitions)
    
    print("\n  ZPOC → TRANSITION rate by volume:")
    zpoc_by_volume = {}
    
    for q in ['Q1_low', 'Q2', 'Q3', 'Q4', 'Q5_high']:
        q_indices = set(df[df['volume_quantile'] == q].index)
        
        q_zpoc_bars = df[(df['volume_quantile'] == q) & (df['organizer_absent'])].index
        
        zpoc_followed = 0
        for idx in q_zpoc_bars:
            for offset in range(1, 11):
                if (idx + offset) in transition_set:
                    zpoc_followed += 1
                    break
        
        zpoc_rate = zpoc_followed / len(q_zpoc_bars) if len(q_zpoc_bars) > 0 else 0
        
        zpoc_by_volume[q] = {
            'zpoc_bars': len(q_zpoc_bars),
            'followed_by_transition': zpoc_followed,
            'rate': float(zpoc_rate)
        }
        
        print(f"    {q}: ZPOC bars={len(q_zpoc_bars)}, →TRANS={zpoc_followed} ({100*zpoc_rate:.1f}%)")
    
    print("\n[5] Volume-controlled ER comparison...")
    
    er_variance_by_quantile = {}
    for q in ['Q1_low', 'Q2', 'Q3', 'Q4', 'Q5_high']:
        q_df = df[df['volume_quantile'] == q]
        er_std = q_df['er'].std()
        er_variance_by_quantile[q] = float(er_std)
        print(f"    {q}: ER std = {er_std:.3f}")
    
    print("\n[6] Critical test: Low volume vs High volume ZPOC structure...")
    
    low_vol_df = df[df['volume_quantile'].isin(['Q1_low', 'Q2'])]
    high_vol_df = df[df['volume_quantile'].isin(['Q4', 'Q5_high'])]
    
    low_vol_zpoc_rate = low_vol_df['organizer_absent'].mean()
    high_vol_zpoc_rate = high_vol_df['organizer_absent'].mean()
    
    low_vol_avg_er = low_vol_df['er'].mean()
    high_vol_avg_er = high_vol_df['er'].mean()
    
    print(f"\n  Low Volume (Q1-Q2):")
    print(f"    ZPOC rate: {100*low_vol_zpoc_rate:.1f}%")
    print(f"    Avg ER: {low_vol_avg_er:.3f}")
    
    print(f"\n  High Volume (Q4-Q5):")
    print(f"    ZPOC rate: {100*high_vol_zpoc_rate:.1f}%")
    print(f"    Avg ER: {high_vol_avg_er:.3f}")
    
    zpoc_ratio = low_vol_zpoc_rate / high_vol_zpoc_rate if high_vol_zpoc_rate > 0 else 0
    er_diff = low_vol_avg_er - high_vol_avg_er
    
    print(f"\n  ZPOC ratio (Low/High): {zpoc_ratio:.2f}")
    print(f"  ER difference: {er_diff:.3f}")
    
    print("\n[7] Within-quantile ZPOC → TRANSITION test...")
    
    within_quantile_lift = {}
    for q in ['Q1_low', 'Q3', 'Q5_high']:
        q_df = df[df['volume_quantile'] == q]
        q_indices = list(q_df.index)
        
        q_zpoc = q_df[q_df['organizer_absent']]
        q_non_zpoc = q_df[~q_df['organizer_absent']]
        
        zpoc_trans = sum(1 for idx in q_zpoc.index if any((idx + o) in transition_set for o in range(1, 11)))
        non_zpoc_trans = sum(1 for idx in q_non_zpoc.index if any((idx + o) in transition_set for o in range(1, 11)))
        
        zpoc_rate = zpoc_trans / len(q_zpoc) if len(q_zpoc) > 0 else 0
        non_zpoc_rate = non_zpoc_trans / len(q_non_zpoc) if len(q_non_zpoc) > 0 else 0
        lift = zpoc_rate / non_zpoc_rate if non_zpoc_rate > 0 else 0
        
        within_quantile_lift[q] = {
            'zpoc_rate': float(zpoc_rate),
            'non_zpoc_rate': float(non_zpoc_rate),
            'lift': float(lift)
        }
        
        print(f"    {q}: ZPOC→Trans={100*zpoc_rate:.1f}%, NonZPOC→Trans={100*non_zpoc_rate:.1f}%, Lift={lift:.2f}")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    all_lifts_significant = all(v['lift'] > 1.3 for v in within_quantile_lift.values())
    volume_explains_zpoc = zpoc_ratio > 1.5
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "volume_proxy": "bar_range"
        },
        "global": {
            "er_low_rate": float(global_er_low_rate),
            "er_high_rate": float(global_er_high_rate)
        },
        "quantile_stats": quantile_stats,
        "zpoc_by_volume": zpoc_by_volume,
        "er_variance_by_quantile": er_variance_by_quantile,
        "volume_comparison": {
            "low_vol_zpoc_rate": float(low_vol_zpoc_rate),
            "high_vol_zpoc_rate": float(high_vol_zpoc_rate),
            "zpoc_ratio": float(zpoc_ratio),
            "low_vol_avg_er": float(low_vol_avg_er),
            "high_vol_avg_er": float(high_vol_avg_er)
        },
        "within_quantile_lift": within_quantile_lift,
        "validation": {
            "volume_explains_zpoc": bool(volume_explains_zpoc),
            "zpoc_structure_survives_control": bool(all_lifts_significant),
            "H_A1_rejected": bool(all_lifts_significant and not volume_explains_zpoc)
        }
    }
    
    print(f"\n  Volume explains ZPOC?: {volume_explains_zpoc} (ratio: {zpoc_ratio:.2f})")
    print(f"  ZPOC→TRANS structure survives volume control?: {all_lifts_significant}")
    print(f"\n  H_A1 (Volume Effect) REJECTED: {results['validation']['H_A1_rejected']}")
    
    if results['validation']['H_A1_rejected']:
        print("\n  → ER 붕괴는 단순 유동성 저하가 아님. 구조적 현상 확인.")
    else:
        print("\n  → Volume이 ER 붕괴의 주요 원인일 가능성 있음.")
    
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
