"""
EXP-COUNTERFACTUAL-FORCE-01: 반사실 실험 (최종 공격)
====================================================
질문: force_ratio를 인위적으로 고정하면 붕괴는 사라지는가?

방법:
  실제 시계열에서 high/low를 조정해 force_ratio 고정
  나머지 state 유지 → synthetic counterfactual 생성

판정:
  붕괴 사라짐 → 원인 확정
  붕괴 유지 → force_ratio는 proxy
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List
from scipy.spatial.distance import cosine

RESULT_FILE = "v7-grammar-system/results/exp_counterfactual_force_01.json"

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
    return pd.Series(result)

def calc_depth(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    result = []
    for idx in range(len(df)):
        start = max(0, idx - lookback + 1)
        window = df.iloc[start:idx + 1]
        if len(window) < 2:
            result.append(0.5)
            continue
        high_20 = window['high'].max()
        low_20 = window['low'].min()
        range_20 = high_20 - low_20
        if range_20 < 0.01:
            result.append(0.5)
        else:
            result.append((high_20 - df.iloc[idx]['close']) / range_20)
    return pd.Series(result)

def normalize_series(series: pd.Series) -> pd.Series:
    min_val = series.min()
    max_val = series.max()
    if max_val - min_val < 0.0001:
        return pd.Series([0.5] * len(series))
    return (series - min_val) / (max_val - min_val)

def calc_alignment_series(state_matrix: np.ndarray) -> List[float]:
    alignment = [1.0]
    for i in range(1, len(state_matrix)):
        v1 = state_matrix[i-1]
        v2 = state_matrix[i]
        if np.linalg.norm(v1) < 0.001 or np.linalg.norm(v2) < 0.001:
            alignment.append(1.0)
        else:
            alignment.append(1 - cosine(v1, v2))
    return alignment

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-COUNTERFACTUAL-FORCE-01: 반사실 실험")
    print("=" * 70)
    
    print("\n[1] Computing original metrics...")
    
    df['range'] = df['high'] - df['low']
    df['buyer_power'] = df['close'] - df['low']
    df['seller_power'] = df['high'] - df['close']
    df['force_ratio'] = df['buyer_power'] / df['seller_power'].replace(0, 0.001)
    df['force_ratio'] = df['force_ratio'].clip(0.01, 100)
    
    df['er'] = calc_er(df['close'])
    df['depth'] = calc_depth(df)
    df['channel'] = df['buyer_power'] / df['range'].replace(0, 0.001)
    
    force_n = normalize_series(df['force_ratio'])
    er_n = normalize_series(df['er'])
    depth_n = normalize_series(df['depth'])
    channel_n = normalize_series(df['channel'])
    range_n = normalize_series(df['range'])
    
    original_state = np.column_stack([force_n, er_n, depth_n, channel_n, range_n])
    original_alignment = calc_alignment_series(original_state)
    
    df['alignment'] = original_alignment
    threshold = df['alignment'].quantile(0.10)
    original_breaks = (df['alignment'] < threshold).sum()
    original_er_collapse = (df['er'] < 0.20).sum()
    
    print(f"  Total bars: {len(df)}")
    print(f"  Original alignment breaks: {original_breaks}")
    print(f"  Original ER collapse events: {original_er_collapse}")
    
    print("\n[2] Creating counterfactual: fix force_ratio at median...")
    
    median_force = df['force_ratio'].median()
    
    df_cf = df.copy()
    
    for idx in range(len(df_cf)):
        close = df_cf.iloc[idx]['close']
        range_val = df_cf.iloc[idx]['range']
        
        target_buyer = range_val * median_force / (1 + median_force)
        target_seller = range_val - target_buyer
        
        new_low = close - target_buyer
        new_high = close + target_seller
        
        df_cf.loc[df_cf.index[idx], 'low'] = new_low
        df_cf.loc[df_cf.index[idx], 'high'] = new_high
    
    df_cf['buyer_power'] = df_cf['close'] - df_cf['low']
    df_cf['seller_power'] = df_cf['high'] - df_cf['close']
    df_cf['force_ratio'] = df_cf['buyer_power'] / df_cf['seller_power'].replace(0, 0.001)
    df_cf['force_ratio'] = df_cf['force_ratio'].clip(0.01, 100)
    
    df_cf['er'] = calc_er(df_cf['close'])
    df_cf['depth'] = calc_depth(df_cf)
    df_cf['channel'] = df_cf['buyer_power'] / df_cf['range'].replace(0, 0.001)
    
    force_cf_n = normalize_series(df_cf['force_ratio'])
    er_cf_n = normalize_series(df_cf['er'])
    depth_cf_n = normalize_series(df_cf['depth'])
    channel_cf_n = normalize_series(df_cf['channel'])
    range_cf_n = normalize_series(df_cf['range'])
    
    cf_state = np.column_stack([force_cf_n, er_cf_n, depth_cf_n, channel_cf_n, range_cf_n])
    cf_alignment = calc_alignment_series(cf_state)
    
    df_cf['alignment'] = cf_alignment
    cf_threshold = df_cf['alignment'].quantile(0.10)
    cf_breaks = (df_cf['alignment'] < cf_threshold).sum()
    cf_er_collapse = (df_cf['er'] < 0.20).sum()
    
    print(f"  Counterfactual alignment breaks: {cf_breaks}")
    print(f"  Counterfactual ER collapse events: {cf_er_collapse}")
    
    print("\n[3] Comparing original vs counterfactual...")
    
    break_reduction = 1 - (cf_breaks / original_breaks) if original_breaks > 0 else 0
    er_reduction = 1 - (cf_er_collapse / original_er_collapse) if original_er_collapse > 0 else 0
    
    print(f"\n  Alignment break reduction: {100*break_reduction:.1f}%")
    print(f"  ER collapse reduction: {100*er_reduction:.1f}%")
    
    print("\n[4] Testing alternative counterfactuals...")
    
    df_smooth = df.copy()
    df_smooth['force_ratio'] = df['force_ratio'].rolling(20, min_periods=1).mean()
    
    force_smooth_n = normalize_series(df_smooth['force_ratio'])
    smooth_state = np.column_stack([force_smooth_n, er_n, depth_n, channel_n, range_n])
    smooth_alignment = calc_alignment_series(smooth_state)
    smooth_breaks = (pd.Series(smooth_alignment) < threshold).sum()
    
    smooth_reduction = 1 - (smooth_breaks / original_breaks) if original_breaks > 0 else 0
    
    print(f"  Smoothed force_ratio breaks: {smooth_breaks} (reduction: {100*smooth_reduction:.1f}%)")
    
    df_rand = df.copy()
    np.random.seed(42)
    df_rand['force_ratio'] = np.random.permutation(df['force_ratio'].values)
    
    force_rand_n = normalize_series(df_rand['force_ratio'])
    rand_state = np.column_stack([force_rand_n, er_n, depth_n, channel_n, range_n])
    rand_alignment = calc_alignment_series(rand_state)
    rand_breaks = (pd.Series(rand_alignment) < threshold).sum()
    
    rand_reduction = 1 - (rand_breaks / original_breaks) if original_breaks > 0 else 0
    
    print(f"  Randomized force_ratio breaks: {rand_breaks} (reduction: {100*rand_reduction:.1f}%)")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    force_is_causal = break_reduction > 0.3 or smooth_reduction > 0.3
    collapse_eliminated = break_reduction > 0.5
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "median_force_ratio": float(median_force)
        },
        "original": {
            "alignment_breaks": int(original_breaks),
            "er_collapse_events": int(original_er_collapse)
        },
        "counterfactual_fixed": {
            "alignment_breaks": int(cf_breaks),
            "er_collapse_events": int(cf_er_collapse),
            "break_reduction": float(break_reduction),
            "er_reduction": float(er_reduction)
        },
        "counterfactual_smoothed": {
            "alignment_breaks": int(smooth_breaks),
            "break_reduction": float(smooth_reduction)
        },
        "counterfactual_randomized": {
            "alignment_breaks": int(rand_breaks),
            "break_reduction": float(rand_reduction)
        },
        "validation": {
            "force_is_causal": bool(force_is_causal),
            "collapse_eliminated_by_fix": bool(collapse_eliminated),
            "FORCE_RATIO_CONFIRMED_CAUSE": bool(force_is_causal)
        }
    }
    
    print(f"\n  Fix force_ratio → break reduction: {100*break_reduction:.1f}%")
    print(f"  Smooth force_ratio → break reduction: {100*smooth_reduction:.1f}%")
    print(f"  Randomize force_ratio → break reduction: {100*rand_reduction:.1f}%")
    
    print(f"\n  FORCE_RATIO IS CAUSAL: {results['validation']['FORCE_RATIO_CONFIRMED_CAUSE']}")
    
    if force_is_causal:
        print("\n  → force_ratio 제거/고정 시 붕괴 감소 = 원인 확정")
    else:
        print("\n  → force_ratio는 proxy일 가능성")
    
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
