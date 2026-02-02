"""
EXP-UNIVERSALITY-VALIDATION-01: 보편성 가설 검증
=================================================
목표: 이중 인과 구조(절대→ER 붕괴, 상대→TRANSITION)가
     시간프레임이 바뀌어도 유지되는지 검증

가설:
  H_U1: abs_velocity → ER collapse (절대 인과)
  H_U2: rel_velocity → TRANSITION (상대 인과)
  H_U3: ER에서 ABS 우세, TRANSITION에서 REL 우세 (이중 구조 분리)

판정:
  셀 PASS: 각 가설 통과
  전체 PASS: 7/9 이상 (여기선 TF만 있으므로 2/3 이상)
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple

RESULT_FILE = "v7-grammar-system/results/exp_universality_validation_01.json"

def resample_to_timeframe(df: pd.DataFrame, tf_minutes: int) -> pd.DataFrame:
    if tf_minutes == 1:
        return df.copy()
    
    df_copy = df.copy()
    df_copy['bar_group'] = df_copy.index // tf_minutes
    
    resampled = df_copy.groupby('bar_group').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).reset_index(drop=True)
    
    return resampled

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
    return pd.Series(result, index=df.index)

def detect_transitions(depth_series: pd.Series) -> List[int]:
    events = []
    if len(depth_series) < 10:
        return events
    prev_side = "LOW" if depth_series.iloc[5] < 0.5 else "HIGH"
    for i in range(10, len(depth_series)):
        curr_side = "LOW" if depth_series.iloc[i] < 0.5 else "HIGH"
        if curr_side != prev_side:
            events.append(i)
            prev_side = curr_side
    return events

def validate_cell(df: pd.DataFrame, asset: str, tf: str) -> Dict:
    """단일 셀(자산×TF) 검증"""
    
    df['range'] = df['high'] - df['low']
    df['buyer_power'] = df['close'] - df['low']
    df['seller_power'] = df['high'] - df['close']
    df['force_ratio'] = df['buyer_power'] / df['seller_power'].replace(0, 0.001)
    df['force_ratio'] = df['force_ratio'].clip(0.01, 100)
    
    df['abs_velocity'] = df['force_ratio'].diff().abs().fillna(0)
    
    lookback = 20
    df['local_mean'] = df['abs_velocity'].rolling(lookback, min_periods=5).mean()
    df['local_std'] = df['abs_velocity'].rolling(lookback, min_periods=5).std().replace(0, 0.001)
    df['rel_velocity'] = ((df['abs_velocity'] - df['local_mean']) / df['local_std']).fillna(0)
    
    df['er'] = calc_er(df['close'])
    df['depth'] = calc_depth(df)
    
    df['er_collapse'] = df['er'] < 0.20
    er_collapse_onset = df['er_collapse'] & ~df['er_collapse'].shift(1).fillna(False)
    er_events = df[er_collapse_onset].index.tolist()
    
    transitions = detect_transitions(df['depth'])
    df['is_transition'] = df.index.isin(set(transitions))
    
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
    
    lift_abs_er = abs_er / baseline_er if baseline_er > 0 else 0
    lift_rel_er = rel_er / baseline_er if baseline_er > 0 else 0
    lift_abs_tr = abs_trans / baseline_trans if baseline_trans > 0 else 0
    lift_rel_tr = rel_trans / baseline_trans if baseline_trans > 0 else 0
    
    np.random.seed(42)
    
    if er_events:
        shifts = np.random.randint(-50, 51, size=len(er_events))
        shifted_er = [(i + s) % len(df) for i, s in zip(er_events, shifts)]
        
        orig_abs_er = df.loc[er_events, 'abs_velocity'].mean()
        shift_abs_er = df.iloc[shifted_er]['abs_velocity'].mean()
        abs_preserve_er = shift_abs_er / orig_abs_er if orig_abs_er > 0 else 0
    else:
        abs_preserve_er = 0
    
    if transitions:
        shifts = np.random.randint(-50, 51, size=len(transitions))
        shifted_tr = [(i + s) % len(df) for i, s in zip(transitions, shifts)]
        
        orig_rel_tr = df.iloc[transitions]['rel_velocity'].mean()
        shift_rel_tr = df.iloc[shifted_tr]['rel_velocity'].mean()
        rel_preserve_tr = shift_rel_tr / orig_rel_tr if orig_rel_tr > 0 else 0
    else:
        rel_preserve_tr = 0
    
    h_u1_pass = lift_abs_er >= 1.10 and abs_preserve_er < 0.95
    h_u2_pass = lift_rel_tr >= 1.20 and rel_preserve_tr <= 0.50
    h_u3_pass = (lift_abs_er > lift_rel_er) and (lift_rel_tr > lift_abs_tr)
    
    cell_pass = h_u1_pass and h_u2_pass and h_u3_pass
    
    return {
        "asset": asset,
        "tf": tf,
        "bars": len(df),
        "er_events": len(er_events),
        "transitions": len(transitions),
        "metrics": {
            "lift_abs_er": float(lift_abs_er),
            "lift_rel_er": float(lift_rel_er),
            "lift_abs_tr": float(lift_abs_tr),
            "lift_rel_tr": float(lift_rel_tr),
            "abs_preserve": float(abs_preserve_er),
            "rel_preserve": float(rel_preserve_tr)
        },
        "hypotheses": {
            "H_U1": bool(h_u1_pass),
            "H_U2": bool(h_u2_pass),
            "H_U3": bool(h_u3_pass)
        },
        "verdict": "PASS" if cell_pass else "FAIL"
    }

def run_experiment(df_1m: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-UNIVERSALITY-VALIDATION-01: 보편성 가설 검증")
    print("=" * 70)
    
    timeframes = [
        ("1m", 1),
        ("5m", 5),
        ("15m", 15)
    ]
    
    asset = "NQ"
    
    results = {
        "cells": [],
        "summary": {}
    }
    
    print(f"\n{'Asset':<6} | {'TF':<4} | {'Bars':>8} | {'H_U1':>6} | {'H_U2':>6} | {'H_U3':>6} | {'Verdict':>8}")
    print("-" * 70)
    
    for tf_name, tf_mult in timeframes:
        df_tf = resample_to_timeframe(df_1m, tf_mult)
        
        cell = validate_cell(df_tf, asset, tf_name)
        results["cells"].append(cell)
        
        h1 = "PASS" if cell["hypotheses"]["H_U1"] else "FAIL"
        h2 = "PASS" if cell["hypotheses"]["H_U2"] else "FAIL"
        h3 = "PASS" if cell["hypotheses"]["H_U3"] else "FAIL"
        
        print(f"{asset:<6} | {tf_name:<4} | {cell['bars']:>8} | {h1:>6} | {h2:>6} | {h3:>6} | {cell['verdict']:>8}")
    
    print("\n" + "=" * 70)
    print("DETAILED METRICS")
    print("=" * 70)
    
    print(f"\n{'Asset/TF':<10} | {'L_abs_ER':>10} | {'L_rel_ER':>10} | {'L_abs_TR':>10} | {'L_rel_TR':>10} | {'abs_pres':>10} | {'rel_pres':>10}")
    print("-" * 85)
    
    for cell in results["cells"]:
        m = cell["metrics"]
        print(f"{cell['asset']}/{cell['tf']:<6} | {m['lift_abs_er']:>10.2f} | {m['lift_rel_er']:>10.2f} | {m['lift_abs_tr']:>10.2f} | {m['lift_rel_tr']:>10.2f} | {m['abs_preserve']:>10.2f} | {m['rel_preserve']:>10.2f}")
    
    pass_count = sum(1 for c in results["cells"] if c["verdict"] == "PASS")
    total_cells = len(results["cells"])
    universal = pass_count >= total_cells * 2 / 3
    
    results["summary"] = {
        "pass_cells": pass_count,
        "total_cells": total_cells,
        "pass_ratio": float(pass_count / total_cells),
        "UNIVERSAL_STRUCTURE": bool(universal)
    }
    
    print("\n" + "=" * 70)
    print("FINAL DECLARATION")
    print("=" * 70)
    
    print(f"\n  PASS cells: {pass_count} / {total_cells}")
    print(f"  Universal structure: {universal}")
    
    if universal:
        print("\n  → 이중 인과 구조 보편성 확정")
        print("  → 시간프레임 불변")
    else:
        print("\n  → 보편성 기각 또는 조건부 보편성")
    
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
