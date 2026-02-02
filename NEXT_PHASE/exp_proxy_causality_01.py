"""
EXP-PROXY-CAUSALITY-01: 조건부 독립성 테스트
=============================================
질문: force_ratio velocity가 DEPTH velocity의 proxy라면,
     DEPTH velocity를 통제하면 force_ratio의 예측력은 사라져야 한다.

방법:
  동일한 depth_velocity 분위수 bin 안에서
  P(event | force_ratio high, depth_bin) vs P(event | force_ratio low, depth_bin)

판정:
  Lift_X_given_Z ≈ 1 → proxy 확정
  Lift_X_given_Z > 1.1 → 독립 원인 성분 있음
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List

RESULT_FILE = "v7-grammar-system/results/exp_proxy_causality_01.json"

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

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-PROXY-CAUSALITY-01: 조건부 독립성 테스트")
    print("=" * 70)
    
    print("\n[1] Computing velocities...")
    
    df['range'] = df['high'] - df['low']
    df['buyer_power'] = df['close'] - df['low']
    df['seller_power'] = df['high'] - df['close']
    df['force_ratio'] = df['buyer_power'] / df['seller_power'].replace(0, 0.001)
    df['force_ratio'] = df['force_ratio'].clip(0.01, 100)
    
    df['force_vel'] = df['force_ratio'].diff().abs().fillna(0)
    
    df['er'] = calc_er(df['close'])
    df['depth'] = calc_depth(df)
    df['depth_vel'] = df['depth'].diff().abs().fillna(0)
    
    df['zpoc_onset'] = (df['er'] < 0.20) & ~(df['er'].shift(1) < 0.20).fillna(False)
    
    prev_side = df['depth'].shift(1).apply(lambda x: "LOW" if x < 0.5 else "HIGH")
    curr_side = df['depth'].apply(lambda x: "LOW" if x < 0.5 else "HIGH")
    df['transition'] = prev_side != curr_side
    
    print(f"  Total bars: {len(df)}")
    print(f"  ZPOC onset events: {df['zpoc_onset'].sum()}")
    print(f"  TRANSITION events: {df['transition'].sum()}")
    
    print("\n[2] Creating depth_velocity bins...")
    
    df['depth_vel_bin'] = pd.qcut(df['depth_vel'], q=5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'], duplicates='drop')
    
    force_q90 = df['force_vel'].quantile(0.90)
    df['force_high'] = df['force_vel'] >= force_q90
    
    print(f"  force_vel Q90 threshold: {force_q90:.4f}")
    
    print("\n[3] Conditional independence test: ZPOC onset...")
    
    zpoc_results = {}
    
    print(f"\n  {'Depth bin':<10} | {'P(ZPOC|F_hi)':>12} | {'P(ZPOC|F_lo)':>12} | {'Cond Lift':>10}")
    print("  " + "-" * 50)
    
    conditional_lifts_zpoc = []
    
    for bin_label in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']:
        bin_mask = df['depth_vel_bin'] == bin_label
        bin_df = df[bin_mask]
        
        if len(bin_df) < 100:
            continue
        
        force_hi = bin_df['force_high']
        force_lo = ~bin_df['force_high']
        
        p_zpoc_hi = bin_df[force_hi]['zpoc_onset'].mean() if force_hi.sum() > 0 else 0
        p_zpoc_lo = bin_df[force_lo]['zpoc_onset'].mean() if force_lo.sum() > 0 else 0
        
        cond_lift = p_zpoc_hi / p_zpoc_lo if p_zpoc_lo > 0 else 0
        
        zpoc_results[bin_label] = {
            'p_event_force_high': float(p_zpoc_hi),
            'p_event_force_low': float(p_zpoc_lo),
            'conditional_lift': float(cond_lift)
        }
        
        conditional_lifts_zpoc.append(cond_lift)
        
        print(f"  {bin_label:<10} | {100*p_zpoc_hi:>11.2f}% | {100*p_zpoc_lo:>11.2f}% | {cond_lift:>10.2f}")
    
    avg_cond_lift_zpoc = np.mean(conditional_lifts_zpoc) if conditional_lifts_zpoc else 0
    print(f"\n  Average conditional lift (ZPOC): {avg_cond_lift_zpoc:.2f}")
    
    print("\n[4] Conditional independence test: TRANSITION...")
    
    trans_results = {}
    
    print(f"\n  {'Depth bin':<10} | {'P(TR|F_hi)':>12} | {'P(TR|F_lo)':>12} | {'Cond Lift':>10}")
    print("  " + "-" * 50)
    
    conditional_lifts_trans = []
    
    for bin_label in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']:
        bin_mask = df['depth_vel_bin'] == bin_label
        bin_df = df[bin_mask]
        
        if len(bin_df) < 100:
            continue
        
        force_hi = bin_df['force_high']
        force_lo = ~bin_df['force_high']
        
        p_trans_hi = bin_df[force_hi]['transition'].mean() if force_hi.sum() > 0 else 0
        p_trans_lo = bin_df[force_lo]['transition'].mean() if force_lo.sum() > 0 else 0
        
        cond_lift = p_trans_hi / p_trans_lo if p_trans_lo > 0 else 0
        
        trans_results[bin_label] = {
            'p_event_force_high': float(p_trans_hi),
            'p_event_force_low': float(p_trans_lo),
            'conditional_lift': float(cond_lift)
        }
        
        conditional_lifts_trans.append(cond_lift)
        
        print(f"  {bin_label:<10} | {100*p_trans_hi:>11.2f}% | {100*p_trans_lo:>11.2f}% | {cond_lift:>10.2f}")
    
    avg_cond_lift_trans = np.mean(conditional_lifts_trans) if conditional_lifts_trans else 0
    print(f"\n  Average conditional lift (TRANSITION): {avg_cond_lift_trans:.2f}")
    
    print("\n[5] Unconditional comparison...")
    
    p_zpoc_hi_uncond = df[df['force_high']]['zpoc_onset'].mean()
    p_zpoc_lo_uncond = df[~df['force_high']]['zpoc_onset'].mean()
    uncond_lift_zpoc = p_zpoc_hi_uncond / p_zpoc_lo_uncond if p_zpoc_lo_uncond > 0 else 0
    
    p_trans_hi_uncond = df[df['force_high']]['transition'].mean()
    p_trans_lo_uncond = df[~df['force_high']]['transition'].mean()
    uncond_lift_trans = p_trans_hi_uncond / p_trans_lo_uncond if p_trans_lo_uncond > 0 else 0
    
    print(f"\n  Unconditional lift (ZPOC): {uncond_lift_zpoc:.2f}")
    print(f"  Unconditional lift (TRANSITION): {uncond_lift_trans:.2f}")
    
    print(f"\n  Lift reduction after controlling depth_vel:")
    zpoc_reduction = 1 - (avg_cond_lift_zpoc / uncond_lift_zpoc) if uncond_lift_zpoc > 0 else 0
    trans_reduction = 1 - (avg_cond_lift_trans / uncond_lift_trans) if uncond_lift_trans > 0 else 0
    print(f"    ZPOC: {100*zpoc_reduction:.1f}%")
    print(f"    TRANSITION: {100*trans_reduction:.1f}%")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    zpoc_proxy = avg_cond_lift_zpoc < 1.10
    trans_proxy = avg_cond_lift_trans < 1.10
    
    zpoc_independent = avg_cond_lift_zpoc > 1.10
    trans_independent = avg_cond_lift_trans > 1.10
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "zpoc_events": int(df['zpoc_onset'].sum()),
            "transition_events": int(df['transition'].sum())
        },
        "zpoc": {
            "unconditional_lift": float(uncond_lift_zpoc),
            "conditional_lift_avg": float(avg_cond_lift_zpoc),
            "lift_reduction": float(zpoc_reduction),
            "by_bin": zpoc_results
        },
        "transition": {
            "unconditional_lift": float(uncond_lift_trans),
            "conditional_lift_avg": float(avg_cond_lift_trans),
            "lift_reduction": float(trans_reduction),
            "by_bin": trans_results
        },
        "validation": {
            "force_is_zpoc_proxy": bool(zpoc_proxy),
            "force_is_trans_proxy": bool(trans_proxy),
            "force_has_independent_zpoc_effect": bool(zpoc_independent),
            "force_has_independent_trans_effect": bool(trans_independent)
        }
    }
    
    print(f"\n  ZPOC:")
    print(f"    Unconditional lift: {uncond_lift_zpoc:.2f}")
    print(f"    Conditional lift (controlling depth_vel): {avg_cond_lift_zpoc:.2f}")
    print(f"    force_ratio is PROXY: {zpoc_proxy}")
    
    print(f"\n  TRANSITION:")
    print(f"    Unconditional lift: {uncond_lift_trans:.2f}")
    print(f"    Conditional lift (controlling depth_vel): {avg_cond_lift_trans:.2f}")
    print(f"    force_ratio is PROXY: {trans_proxy}")
    
    if zpoc_proxy and trans_proxy:
        print("\n  → force_ratio velocity = DEPTH velocity의 완전한 proxy")
        print("  → 독립적 인과 기여 없음")
    elif zpoc_independent or trans_independent:
        print("\n  → force_ratio velocity에 독립적 인과 성분 존재")
        print("  → 단순 proxy가 아닌 복합 구조")
    
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
