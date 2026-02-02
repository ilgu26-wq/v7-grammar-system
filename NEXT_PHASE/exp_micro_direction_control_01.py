"""
EXP-MICRO-DIRECTION-CONTROL-01: 붕괴 직전 미시 방향 컨트롤 가설
================================================================
핵심 가설 (H_MICRO_CTRL):
  ZPOC(ER 붕괴) 직전 구간에서,
  force_ratio velocity의 방향성을 이용해
  '붕괴가 일어나는 방향'을 미시적으로 선취할 수 있다.

판정:
  ≥58%: 미시 방향 컨트롤 가능
  55~58%: 약한 edge
  52~55%: 통계적 우연
  ≤52%: 방향 컨트롤 불가
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List

RESULT_FILE = "v7-grammar-system/results/exp_micro_direction_control_01.json"

def calc_er(close_series: pd.Series, lookback: int = 10) -> pd.Series:
    result = []
    for i in range(len(close_series)):
        start = max(0, i - lookback + 1)
        window = close_series.iloc[start:i + 1]
        if len(window) < 2:
            result.append(0.5)
            continue
        price_change = abs(window.iloc[-1] - window.iloc[0])
        bar_changes = abs(window.diff().dropna()).sum()
        if bar_changes < 0.01:
            result.append(1.0)
        else:
            result.append(min(1.0, price_change / bar_changes))
    return pd.Series(result, index=close_series.index)

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-MICRO-DIRECTION-CONTROL-01: 붕괴 직전 미시 방향 컨트롤")
    print("=" * 70)
    
    print("\n[1] Computing metrics...")
    
    df['range'] = df['high'] - df['low']
    df['buyer_power'] = df['close'] - df['low']
    df['seller_power'] = df['high'] - df['close']
    df['force_ratio'] = df['buyer_power'] / df['seller_power'].replace(0, 0.001)
    df['force_ratio'] = df['force_ratio'].clip(0.01, 100)
    
    df['force_delta'] = df['force_ratio'].diff().fillna(0)
    df['micro_dir'] = np.sign(df['force_delta'])
    
    df['er'] = calc_er(df['close'])
    
    df['zpoc_onset'] = (df['er'] < 0.25) & ~(df['er'].shift(1) < 0.25).fillna(False)
    
    zpoc_events = df[df['zpoc_onset']].index.tolist()
    print(f"  Total bars: {len(df)}")
    print(f"  ZPOC onset events: {len(zpoc_events)}")
    
    print("\n[2] Testing micro direction control...")
    
    force_q70 = df['force_delta'].abs().quantile(0.70)
    
    results_by_window = {}
    
    for lookback in [1, 2, 3]:
        for forward in [3, 5, 10]:
            matches = 0
            total = 0
            pnl_list = []
            
            for idx in zpoc_events:
                if idx < lookback or idx + forward >= len(df):
                    continue
                
                micro = df.iloc[idx - lookback]['micro_dir']
                force_strength = abs(df.iloc[idx - lookback]['force_delta'])
                
                if micro == 0:
                    continue
                
                if force_strength < force_q70:
                    continue
                
                entry_price = df.iloc[idx]['close']
                exit_price = df.iloc[idx + forward]['close']
                
                outcome_dir = np.sign(exit_price - entry_price)
                
                if outcome_dir == micro:
                    matches += 1
                    pnl = abs(exit_price - entry_price)
                else:
                    pnl = -abs(exit_price - entry_price)
                
                pnl_list.append(pnl)
                total += 1
            
            if total > 0:
                hit_rate = matches / total
                avg_pnl = np.mean(pnl_list)
                
                results_by_window[f"w-{lookback}_f+{forward}"] = {
                    'total': total,
                    'matches': matches,
                    'hit_rate': float(hit_rate),
                    'avg_pnl': float(avg_pnl)
                }
    
    print(f"\n  {'Window':<15} | {'Total':>8} | {'Hit Rate':>10} | {'Avg PnL':>10}")
    print("  " + "-" * 50)
    
    for key, data in sorted(results_by_window.items()):
        print(f"  {key:<15} | {data['total']:>8} | {100*data['hit_rate']:>9.1f}% | {data['avg_pnl']:>10.2f}")
    
    print("\n[3] Random shuffle test...")
    
    np.random.seed(42)
    
    best_window = max(results_by_window.items(), key=lambda x: x[1]['hit_rate'])
    best_key = best_window[0]
    best_hit = best_window[1]['hit_rate']
    
    parts = best_key.split('_')
    lookback = int(parts[0].split('-')[1])
    forward = int(parts[1].split('+')[1])
    
    shuffled_hits = []
    for _ in range(100):
        shuffled_dir = df['micro_dir'].sample(frac=1).reset_index(drop=True)
        
        matches = 0
        total = 0
        
        for i, idx in enumerate(zpoc_events):
            if idx < lookback or idx + forward >= len(df):
                continue
            
            if i >= len(shuffled_dir):
                continue
            
            micro = shuffled_dir.iloc[i % len(shuffled_dir)]
            force_strength = abs(df.iloc[idx - lookback]['force_delta'])
            
            if micro == 0 or force_strength < force_q70:
                continue
            
            entry_price = df.iloc[idx]['close']
            exit_price = df.iloc[idx + forward]['close']
            outcome_dir = np.sign(exit_price - entry_price)
            
            if outcome_dir == micro:
                matches += 1
            total += 1
        
        if total > 0:
            shuffled_hits.append(matches / total)
    
    shuffle_mean = np.mean(shuffled_hits)
    shuffle_std = np.std(shuffled_hits)
    z_score = (best_hit - shuffle_mean) / shuffle_std if shuffle_std > 0 else 0
    
    print(f"\n  Best window: {best_key}")
    print(f"  Original hit rate: {100*best_hit:.1f}%")
    print(f"  Shuffled mean: {100*shuffle_mean:.1f}%")
    print(f"  Z-score: {z_score:.2f}")
    
    print("\n[4] Depth-controlled test...")
    
    df['depth_vel'] = df['force_ratio'].rolling(20).mean().diff().abs().fillna(0)
    df['depth_vel_bin'] = pd.qcut(df['depth_vel'], q=5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'], duplicates='drop')
    
    controlled_results = {}
    
    for bin_label in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']:
        matches = 0
        total = 0
        
        for idx in zpoc_events:
            if idx < lookback or idx + forward >= len(df):
                continue
            
            if df.iloc[idx]['depth_vel_bin'] != bin_label:
                continue
            
            micro = df.iloc[idx - lookback]['micro_dir']
            force_strength = abs(df.iloc[idx - lookback]['force_delta'])
            
            if micro == 0 or force_strength < force_q70:
                continue
            
            entry_price = df.iloc[idx]['close']
            exit_price = df.iloc[idx + forward]['close']
            outcome_dir = np.sign(exit_price - entry_price)
            
            if outcome_dir == micro:
                matches += 1
            total += 1
        
        if total > 10:
            controlled_results[bin_label] = {
                'total': total,
                'hit_rate': float(matches / total)
            }
    
    print(f"\n  {'Depth bin':<10} | {'Total':>8} | {'Hit Rate':>10}")
    print("  " + "-" * 35)
    
    for bin_label, data in controlled_results.items():
        print(f"  {bin_label:<10} | {data['total']:>8} | {100*data['hit_rate']:>9.1f}%")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    micro_control_possible = best_hit >= 0.55
    strong_edge = best_hit >= 0.58
    statistically_valid = z_score >= 2.0
    
    if strong_edge and statistically_valid:
        verdict = "STRONG_EDGE"
    elif micro_control_possible and statistically_valid:
        verdict = "WEAK_EDGE"
    elif micro_control_possible:
        verdict = "POSSIBLE_BUT_NOISY"
    else:
        verdict = "NO_CONTROL"
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "zpoc_events": len(zpoc_events),
            "force_q70_threshold": float(force_q70)
        },
        "window_results": results_by_window,
        "best_window": {
            "key": best_key,
            "hit_rate": float(best_hit),
            "z_score": float(z_score)
        },
        "shuffle_test": {
            "mean": float(shuffle_mean),
            "std": float(shuffle_std),
            "z_score": float(z_score)
        },
        "depth_controlled": controlled_results,
        "validation": {
            "micro_control_possible": bool(micro_control_possible),
            "strong_edge": bool(strong_edge),
            "statistically_valid": bool(statistically_valid),
            "verdict": verdict
        }
    }
    
    print(f"\n  Best hit rate: {100*best_hit:.1f}%")
    print(f"  Z-score vs random: {z_score:.2f}")
    print(f"  Statistically valid: {statistically_valid}")
    print(f"\n  VERDICT: {verdict}")
    
    if verdict == "STRONG_EDGE":
        print("\n  → 미시 방향 컨트롤 가능! 붕괴 직전 방향 선취 유효")
    elif verdict == "WEAK_EDGE":
        print("\n  → 약한 edge 존재. 조건부 사용 가능")
    elif verdict == "POSSIBLE_BUT_NOISY":
        print("\n  → 신호 있으나 통계적 유의성 부족")
    else:
        print("\n  → 방향 컨트롤 불가. FORCE는 '언제'만 알려줌")
    
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
