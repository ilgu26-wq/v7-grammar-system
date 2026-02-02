"""
EXP-FORCE-RATIO-DECOMPOSE-01: force_ratio 내부 분해
====================================================
질문: force_ratio의 무엇이 붕괴를 유발하는가?

분해:
  force_ratio = (close - low) / (high - close)

3축:
  Position: close 위치 (channel_pos)
  Asymmetry: upper vs lower tail 비대칭
  Velocity: force_ratio 변화 속도

판정:
  하나만 살아남으면 → 진짜 원인
  전부 약하면 → force_ratio는 composite proxy
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List
from scipy.spatial.distance import cosine

RESULT_FILE = "v7-grammar-system/results/exp_force_ratio_decompose_01.json"

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

def normalize_series(series: pd.Series) -> pd.Series:
    min_val = series.min()
    max_val = series.max()
    if max_val - min_val < 0.0001:
        return pd.Series([0.5] * len(series))
    return (series - min_val) / (max_val - min_val)

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-FORCE-RATIO-DECOMPOSE-01: force_ratio 내부 분해")
    print("=" * 70)
    
    print("\n[1] Computing force_ratio components...")
    
    df['range'] = df['high'] - df['low']
    df['buyer_power'] = df['close'] - df['low']
    df['seller_power'] = df['high'] - df['close']
    
    df['force_ratio'] = df['buyer_power'] / df['seller_power'].replace(0, 0.001)
    df['force_ratio'] = df['force_ratio'].clip(0.01, 100)
    
    df['position'] = df['buyer_power'] / df['range'].replace(0, 0.001)
    df['position'] = df['position'].clip(0, 1)
    
    df['asymmetry'] = (df['buyer_power'] - df['seller_power']) / df['range'].replace(0, 0.001)
    
    df['force_velocity'] = df['force_ratio'].diff().fillna(0)
    df['force_accel'] = df['force_velocity'].diff().fillna(0)
    
    er_series = [calc_er(df, i) for i in range(len(df))]
    df['er'] = er_series
    df['er_collapse'] = df['er'] < 0.20
    
    print(f"  Total bars: {len(df)}")
    
    print("\n[2] Computing alignment breaks...")
    
    force_n = normalize_series(df['force_ratio'])
    position_n = normalize_series(df['position'])
    asymmetry_n = normalize_series(df['asymmetry'])
    velocity_n = normalize_series(df['force_velocity'].abs())
    
    alignment = [1.0]
    for i in range(1, len(df)):
        v1 = np.array([force_n.iloc[i-1], position_n.iloc[i-1], asymmetry_n.iloc[i-1], velocity_n.iloc[i-1]])
        v2 = np.array([force_n.iloc[i], position_n.iloc[i], asymmetry_n.iloc[i], velocity_n.iloc[i]])
        
        if np.linalg.norm(v1) < 0.001 or np.linalg.norm(v2) < 0.001:
            alignment.append(1.0)
        else:
            alignment.append(1 - cosine(v1, v2))
    
    df['alignment'] = alignment
    threshold = df['alignment'].quantile(0.10)
    df['alignment_break'] = df['alignment'] < threshold
    
    print(f"  Alignment breaks: {df['alignment_break'].sum()}")
    
    print("\n[3] Testing each component's predictive power...")
    
    components = {
        'force_ratio': df['force_ratio'],
        'position': df['position'],
        'asymmetry': df['asymmetry'],
        'velocity': df['force_velocity'].abs(),
        'acceleration': df['force_accel'].abs()
    }
    
    results_by_comp = {}
    
    print(f"\n  {'Component':<15} | {'ER collapse':>12} | {'Align break':>12} | {'Lift':>8}")
    print("  " + "-" * 55)
    
    for name, comp in components.items():
        high_threshold = comp.quantile(0.90)
        high_mask = comp >= high_threshold
        
        er_collapse_high = df[high_mask]['er_collapse'].mean() if high_mask.sum() > 0 else 0
        er_collapse_base = df['er_collapse'].mean()
        er_lift = er_collapse_high / er_collapse_base if er_collapse_base > 0 else 0
        
        align_break_high = df[high_mask]['alignment_break'].mean() if high_mask.sum() > 0 else 0
        align_break_base = df['alignment_break'].mean()
        align_lift = align_break_high / align_break_base if align_break_base > 0 else 0
        
        results_by_comp[name] = {
            'er_collapse_rate': float(er_collapse_high),
            'er_lift': float(er_lift),
            'align_break_rate': float(align_break_high),
            'align_lift': float(align_lift)
        }
        
        print(f"  {name:<15} | {100*er_collapse_high:>11.1f}% | {100*align_break_high:>11.1f}% | {er_lift:>8.2f}")
    
    print("\n[4] Random shift test for each component...")
    
    np.random.seed(42)
    
    alignment_breaks = df[df['alignment_break']].index.tolist()
    shifts = np.random.randint(-50, 51, size=len(alignment_breaks))
    shifted_indices = [(i + s) % len(df) for i, s in zip(alignment_breaks, shifts)]
    
    shift_results = {}
    
    print(f"\n  {'Component':<15} | {'Original':>12} | {'Shifted':>12} | {'Preserved':>10}")
    print("  " + "-" * 55)
    
    for name, comp in components.items():
        original = comp.loc[alignment_breaks].mean() if alignment_breaks else 0
        shifted = comp.iloc[shifted_indices].mean() if shifted_indices else 0
        preserved = shifted / original if original > 0 else 0
        
        shift_results[name] = {
            'original': float(original),
            'shifted': float(shifted),
            'preserved': float(preserved),
            'collapsed': preserved < 0.85 or preserved > 1.15
        }
        
        print(f"  {name:<15} | {original:>12.4f} | {shifted:>12.4f} | {preserved:>10.2f}")
    
    print("\n[5] Identifying dominant component...")
    
    sorted_comps = sorted(results_by_comp.items(), key=lambda x: x[1]['er_lift'], reverse=True)
    
    print(f"\n  Ranking by ER collapse lift:")
    for i, (name, data) in enumerate(sorted_comps):
        collapsed = shift_results[name]['collapsed']
        status = "COLLAPSED" if collapsed else "preserved"
        print(f"    {i+1}. {name}: Lift={data['er_lift']:.2f}, Shift={status}")
    
    dominant = sorted_comps[0][0]
    secondary = sorted_comps[1][0] if len(sorted_comps) > 1 else None
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    velocity_dominant = sorted_comps[0][0] == 'velocity' or sorted_comps[0][0] == 'acceleration'
    position_dominant = sorted_comps[0][0] == 'position'
    asymmetry_dominant = sorted_comps[0][0] == 'asymmetry'
    force_composite = sorted_comps[0][1]['er_lift'] < 1.5
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "alignment_breaks": int(df['alignment_break'].sum())
        },
        "component_analysis": results_by_comp,
        "shift_test": shift_results,
        "ranking": [{"name": n, **d} for n, d in sorted_comps],
        "conclusion": {
            "dominant_component": dominant,
            "secondary_component": secondary,
            "velocity_dominant": bool(velocity_dominant),
            "force_is_composite": bool(force_composite)
        }
    }
    
    print(f"\n  Dominant component: {dominant}")
    print(f"  Secondary component: {secondary}")
    print(f"\n  Velocity/Acceleration dominant: {velocity_dominant}")
    print(f"  Force is composite proxy: {force_composite}")
    
    if velocity_dominant:
        print("\n  → 붕괴 원인 = force_ratio의 '변화 속도'")
    elif position_dominant:
        print("\n  → 붕괴 원인 = close 위치")
    elif asymmetry_dominant:
        print("\n  → 붕괴 원인 = buyer/seller 비대칭")
    else:
        print("\n  → force_ratio 자체가 필요충분 원인")
    
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
