"""
EXP-PHASE-CAUSAL-COMPARE-01: 구조별 원인 데이터 비교 실험
=========================================================
목표: 구조(Phase)가 다르면 원인 데이터의 분포/선행성/반응이 달라지는가?

구조:
  P0: ZPOC (ER collapse, organizer absent)
  P1: TRANSITION (state change)
  P2: SPS (energy release)
  P3: NORMAL (stable regime)

검증:
  1. 분포 차이 (정적)
  2. 선행성 (동적)
  3. 반사실 반응 (인과)
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from scipy import stats

RESULT_FILE = "v7-grammar-system/results/exp_phase_causal_compare_01.json"

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

def detect_phases(df: pd.DataFrame) -> pd.Series:
    phases = []
    for i in range(len(df)):
        er = df.iloc[i]['er']
        depth = df.iloc[i]['depth']
        
        is_transition = False
        if i >= 1:
            prev_side = "LOW" if df.iloc[i-1]['depth'] < 0.5 else "HIGH"
            curr_side = "LOW" if depth < 0.5 else "HIGH"
            is_transition = prev_side != curr_side
        
        is_sps = (depth < 0.15 or depth > 0.85) and er > 0.3
        
        if er < 0.20:
            phases.append("ZPOC")
        elif is_transition:
            phases.append("TRANSITION")
        elif is_sps:
            phases.append("SPS")
        else:
            phases.append("NORMAL")
    
    return pd.Series(phases, index=df.index)

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-PHASE-CAUSAL-COMPARE-01: 구조별 원인 데이터 비교")
    print("=" * 70)
    
    print("\n[1] Computing base metrics and phases...")
    
    df['range'] = df['high'] - df['low']
    df['buyer_power'] = df['close'] - df['low']
    df['seller_power'] = df['high'] - df['close']
    df['force_ratio'] = df['buyer_power'] / df['seller_power'].replace(0, 0.001)
    df['force_ratio'] = df['force_ratio'].clip(0.01, 100)
    df['channel_pos'] = df['buyer_power'] / df['range'].replace(0, 0.001)
    
    df['abs_vel_force'] = df['force_ratio'].diff().abs().fillna(0)
    df['abs_vel_depth_raw'] = df['depth'].diff().abs().fillna(0) if 'depth' in df else 0
    
    lookback = 20
    df['local_mean'] = df['abs_vel_force'].rolling(lookback, min_periods=5).mean()
    df['local_std'] = df['abs_vel_force'].rolling(lookback, min_periods=5).std().replace(0, 0.001)
    df['rel_vel_force'] = ((df['abs_vel_force'] - df['local_mean']) / df['local_std']).fillna(0)
    
    df['er'] = calc_er(df['close'])
    df['depth'] = calc_depth(df)
    
    df['abs_vel_depth'] = df['depth'].diff().abs().fillna(0)
    df['rel_vel_depth'] = ((df['abs_vel_depth'] - df['abs_vel_depth'].rolling(20, min_periods=5).mean()) / 
                           df['abs_vel_depth'].rolling(20, min_periods=5).std().replace(0, 0.001)).fillna(0)
    
    df['phase'] = detect_phases(df)
    
    phase_counts = df['phase'].value_counts()
    print(f"\n  Phase distribution:")
    for phase, count in phase_counts.items():
        print(f"    {phase}: {count} ({100*count/len(df):.1f}%)")
    
    print("\n[2] Extracting causal vectors by phase...")
    
    causal_cols = ['abs_vel_force', 'rel_vel_force', 'abs_vel_depth', 'rel_vel_depth',
                   'force_ratio', 'depth', 'er', 'channel_pos', 'range']
    
    phase_data = {}
    for phase in ['ZPOC', 'TRANSITION', 'SPS', 'NORMAL']:
        mask = df['phase'] == phase
        if mask.sum() > 0:
            phase_data[phase] = df[mask][causal_cols].copy()
    
    print("\n[3] Distribution comparison (KS-test)...")
    
    dist_results = {}
    
    print(f"\n  {'Variable':<15} | {'ZPOC vs NORM':>12} | {'TRANS vs NORM':>12} | {'SPS vs NORM':>12}")
    print("  " + "-" * 60)
    
    baseline = phase_data.get('NORMAL')
    if baseline is None or len(baseline) < 100:
        print("  Not enough NORMAL data for comparison")
        return {"error": "insufficient_normal_data"}
    
    for col in causal_cols:
        dist_results[col] = {}
        row = f"  {col:<15}"
        
        for phase in ['ZPOC', 'TRANSITION', 'SPS']:
            if phase in phase_data and len(phase_data[phase]) > 50:
                ks_stat, p_val = stats.ks_2samp(
                    phase_data[phase][col].dropna(),
                    baseline[col].dropna()
                )
                dist_results[col][phase] = {
                    'ks_stat': float(ks_stat),
                    'significant': p_val < 0.01
                }
                sig = "*" if p_val < 0.01 else " "
                row += f" | {ks_stat:>10.3f}{sig}"
            else:
                row += f" | {'N/A':>12}"
        
        print(row)
    
    print("\n[4] Leading variable analysis...")
    
    lead_results = {}
    
    transitions = df[df['phase'] == 'TRANSITION'].index.tolist()
    zpoc_events = df[df['phase'] == 'ZPOC'].index.tolist()
    
    if transitions:
        print(f"\n  TRANSITION preceding variables (k=-3):")
        lead_results['TRANSITION'] = {}
        
        for col in ['abs_vel_force', 'rel_vel_force', 'abs_vel_depth', 'rel_vel_depth']:
            preceding_vals = []
            for idx in transitions:
                if idx >= 3:
                    preceding_vals.append(df.iloc[idx - 3][col])
            
            if preceding_vals:
                mean_val = np.mean(preceding_vals)
                baseline_mean = df[col].mean()
                lift = mean_val / baseline_mean if baseline_mean > 0 else 0
                
                lead_results['TRANSITION'][col] = {
                    'mean': float(mean_val),
                    'baseline': float(baseline_mean),
                    'lift': float(lift)
                }
                print(f"    {col}: lift = {lift:.2f}")
    
    if zpoc_events:
        print(f"\n  ZPOC preceding variables (k=-3):")
        lead_results['ZPOC'] = {}
        
        for col in ['abs_vel_force', 'rel_vel_force', 'abs_vel_depth', 'rel_vel_depth']:
            preceding_vals = []
            for idx in zpoc_events:
                if idx >= 3:
                    preceding_vals.append(df.iloc[idx - 3][col])
            
            if preceding_vals:
                mean_val = np.mean(preceding_vals)
                baseline_mean = df[col].mean()
                lift = mean_val / baseline_mean if baseline_mean > 0 else 0
                
                lead_results['ZPOC'][col] = {
                    'mean': float(mean_val),
                    'baseline': float(baseline_mean),
                    'lift': float(lift)
                }
                print(f"    {col}: lift = {lift:.2f}")
    
    print("\n[5] Counterfactual response by phase...")
    
    cf_results = {}
    
    df_smooth = df.copy()
    df_smooth['rel_vel_force'] = df['rel_vel_force'].rolling(10, min_periods=1).mean()
    df_smooth['phase_cf'] = detect_phases(df_smooth)
    
    print(f"\n  Phase shift after smoothing rel_vel_force:")
    
    for phase in ['ZPOC', 'TRANSITION', 'SPS', 'NORMAL']:
        orig_count = (df['phase'] == phase).sum()
        cf_count = (df_smooth['phase_cf'] == phase).sum()
        change = (cf_count - orig_count) / orig_count * 100 if orig_count > 0 else 0
        
        cf_results[phase] = {
            'original': int(orig_count),
            'after_smooth': int(cf_count),
            'change_pct': float(change)
        }
        
        print(f"    {phase}: {orig_count} → {cf_count} ({change:+.1f}%)")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    zpoc_abs_dom = (dist_results.get('abs_vel_force', {}).get('ZPOC', {}).get('ks_stat', 0) >
                    dist_results.get('rel_vel_force', {}).get('ZPOC', {}).get('ks_stat', 0))
    
    trans_rel_dom = (dist_results.get('rel_vel_force', {}).get('TRANSITION', {}).get('ks_stat', 0) >
                     dist_results.get('abs_vel_force', {}).get('TRANSITION', {}).get('ks_stat', 0))
    
    zpoc_lead_abs = (lead_results.get('ZPOC', {}).get('abs_vel_force', {}).get('lift', 0) >
                     lead_results.get('ZPOC', {}).get('rel_vel_force', {}).get('lift', 0))
    
    trans_lead_rel = (lead_results.get('TRANSITION', {}).get('rel_vel_force', {}).get('lift', 0) >
                      lead_results.get('TRANSITION', {}).get('abs_vel_force', {}).get('lift', 0))
    
    trans_cf_response = cf_results.get('TRANSITION', {}).get('change_pct', 0) < -10
    
    structure_confirmed = (zpoc_abs_dom or zpoc_lead_abs) and (trans_rel_dom or trans_lead_rel)
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "phase_counts": {k: int(v) for k, v in phase_counts.items()}
        },
        "distribution": dist_results,
        "leading": lead_results,
        "counterfactual": cf_results,
        "validation": {
            "zpoc_abs_dominant": bool(zpoc_abs_dom),
            "trans_rel_dominant": bool(trans_rel_dom),
            "zpoc_lead_abs": bool(zpoc_lead_abs),
            "trans_lead_rel": bool(trans_lead_rel),
            "trans_cf_response": bool(trans_cf_response),
            "PHASE_CAUSAL_STRUCTURE_CONFIRMED": bool(structure_confirmed)
        }
    }
    
    print(f"\n  ZPOC: abs_velocity dominant = {zpoc_abs_dom or zpoc_lead_abs}")
    print(f"  TRANSITION: rel_velocity dominant = {trans_rel_dom or trans_lead_rel}")
    print(f"  Counterfactual response: {trans_cf_response}")
    print(f"\n  PHASE-CONDITIONAL CAUSAL STRUCTURE: {structure_confirmed}")
    
    if structure_confirmed:
        print("\n  → 구조별로 원인 좌표가 다름 = 조건부 인과 체계 확정")
    else:
        print("\n  → 단일 원인 또는 구조 독립 상관")
    
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
