"""
EXP-STB-PHASE-DECOMP-01: STB 점 위상 분해
==========================================
질문: STB는 어느 위상에서 의미가 있는가?

Phase 정의:
  P0: ZPOC (ER<0.25)
  P1: TRANSITION ±3
  P2: SPS cluster (high depth_energy + ER recovery)
  P3: Normal

분석:
  - STB 발생률
  - STB 이후 ER 변화
  - STB 이후 방향 지속성
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List

RESULT_FILE = "v7-grammar-system/results/exp_stb_phase_decomp_01.json"

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

def detect_stb(df: pd.DataFrame) -> pd.Series:
    """STB 점 탐지 (Strong Turn Bar)"""
    body = abs(df['close'] - df['open'])
    range_hl = df['high'] - df['low']
    body_ratio = body / range_hl.replace(0, np.nan)
    
    sps_raw = body_ratio * range_hl
    sps_mean = sps_raw.rolling(10).mean()
    sps_std = sps_raw.rolling(10).std()
    zscore = (sps_raw - sps_mean) / sps_std.replace(0, np.nan)
    
    is_strong = zscore >= 1.5
    
    bullish = df['close'] > df['open']
    bearish = df['close'] < df['open']
    
    prev_bearish = bearish.shift(1).fillna(False)
    prev_bullish = bullish.shift(1).fillna(False)
    
    stb_long = is_strong & bullish & prev_bearish
    stb_short = is_strong & bearish & prev_bullish
    
    stb = stb_long | stb_short
    
    return stb.fillna(False), stb_long.fillna(False), stb_short.fillna(False)

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-STB-PHASE-DECOMP-01: STB 점 위상 분해")
    print("=" * 70)
    
    print("\n[1] Computing time series...")
    er_series = []
    depth_series = []
    for idx in range(len(df)):
        er_series.append(calc_er(df, idx))
        depth_series.append(calc_depth(df, idx))
    
    df['er'] = er_series
    df['depth'] = depth_series
    
    depth_change = [0] + [abs(depth_series[i] - depth_series[i-1]) for i in range(1, len(depth_series))]
    df['depth_change'] = depth_change
    df['depth_energy'] = pd.Series(depth_change).rolling(10).sum().fillna(0)
    
    transitions = detect_transitions(depth_series)
    transition_set = set(transitions)
    
    transition_zone = set()
    for t in transitions:
        for offset in range(-3, 4):
            if 0 <= t + offset < len(df):
                transition_zone.add(t + offset)
    
    print(f"  Total bars: {len(df)}")
    print(f"  TRANSITION events: {len(transitions)}")
    
    print("\n[2] Detecting STB points...")
    stb, stb_long, stb_short = detect_stb(df)
    df['stb'] = stb
    df['stb_long'] = stb_long
    df['stb_short'] = stb_short
    
    n_stb = stb.sum()
    print(f"  STB points: {n_stb} ({100*n_stb/len(df):.2f}%)")
    print(f"  STB Long: {stb_long.sum()}, STB Short: {stb_short.sum()}")
    
    print("\n[3] Assigning phases...")
    
    def assign_phase(idx):
        if idx in transition_zone:
            return 'P1_TRANSITION'
        if df.iloc[idx]['er'] < 0.25:
            return 'P0_ZPOC'
        if df.iloc[idx]['depth_energy'] > df['depth_energy'].quantile(0.75) and df.iloc[idx]['er'] > 0.35:
            return 'P2_SPS'
        return 'P3_NORMAL'
    
    df['phase'] = [assign_phase(i) for i in range(len(df))]
    
    phase_counts = df['phase'].value_counts()
    print("\n  Phase distribution:")
    for phase in ['P0_ZPOC', 'P1_TRANSITION', 'P2_SPS', 'P3_NORMAL']:
        count = phase_counts.get(phase, 0)
        print(f"    {phase}: {count} ({100*count/len(df):.1f}%)")
    
    print("\n[4] STB analysis by phase...")
    
    phases = ['P0_ZPOC', 'P1_TRANSITION', 'P2_SPS', 'P3_NORMAL']
    phase_results = {}
    
    print(f"\n  {'Phase':<15} | {'STB rate':>10} | {'ER after':>10} | {'Dir persist':>12}")
    print("  " + "-" * 55)
    
    for phase in phases:
        phase_df = df[df['phase'] == phase]
        stb_in_phase = phase_df[phase_df['stb']]
        
        stb_rate = len(stb_in_phase) / len(phase_df) if len(phase_df) > 0 else 0
        
        er_after = []
        dir_persist = []
        
        for idx in stb_in_phase.index:
            if idx + 10 >= len(df):
                continue
            
            er_change = df.iloc[idx + 5]['er'] - df.iloc[idx]['er']
            er_after.append(er_change)
            
            stb_dir = 1 if df.iloc[idx]['stb_long'] else -1
            future_move = df.iloc[idx + 5]['close'] - df.iloc[idx]['close']
            persisted = (stb_dir * future_move) > 0
            dir_persist.append(persisted)
        
        avg_er_after = np.mean(er_after) if er_after else 0
        persist_rate = np.mean(dir_persist) if dir_persist else 0
        
        phase_results[phase] = {
            'n_bars': len(phase_df),
            'n_stb': len(stb_in_phase),
            'stb_rate': float(stb_rate),
            'er_change_after': float(avg_er_after),
            'direction_persist': float(persist_rate)
        }
        
        print(f"  {phase:<15} | {100*stb_rate:>9.2f}% | {avg_er_after:>+10.3f} | {100*persist_rate:>11.1f}%")
    
    print("\n[5] STB quality comparison...")
    
    p2_persist = phase_results['P2_SPS']['direction_persist']
    p0_persist = phase_results['P0_ZPOC']['direction_persist']
    p3_persist = phase_results['P3_NORMAL']['direction_persist']
    
    p2_er = phase_results['P2_SPS']['er_change_after']
    p0_er = phase_results['P0_ZPOC']['er_change_after']
    
    print(f"\n  P2_SPS direction persist: {100*p2_persist:.1f}%")
    print(f"  P0_ZPOC direction persist: {100*p0_persist:.1f}%")
    print(f"  P3_NORMAL direction persist: {100*p3_persist:.1f}%")
    
    p2_advantage = p2_persist > p0_persist and p2_persist > 0.55
    
    print(f"\n  P2_SPS has advantage: {p2_advantage}")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    stb_phase_dependent = p2_persist > 0.55 and p0_persist < 0.50
    stb_in_zpoc_dangerous = p0_persist < 0.45
    stb_in_sps_valuable = p2_persist > 0.55
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "n_stb": int(n_stb),
            "n_transitions": len(transitions)
        },
        "phase_distribution": {p: int(phase_counts.get(p, 0)) for p in phases},
        "stb_by_phase": phase_results,
        "validation": {
            "stb_phase_dependent": bool(stb_phase_dependent),
            "stb_in_zpoc_dangerous": bool(stb_in_zpoc_dangerous),
            "stb_in_sps_valuable": bool(stb_in_sps_valuable),
            "STB_REQUIRES_PHASE_FILTER": bool(stb_phase_dependent)
        }
    }
    
    print(f"\n  STB is phase-dependent: {stb_phase_dependent}")
    print(f"  STB in ZPOC dangerous: {stb_in_zpoc_dangerous} ({100*p0_persist:.1f}%)")
    print(f"  STB in SPS valuable: {stb_in_sps_valuable} ({100*p2_persist:.1f}%)")
    print(f"\n  STB REQUIRES PHASE FILTER: {results['validation']['STB_REQUIRES_PHASE_FILTER']}")
    
    if stb_phase_dependent:
        print("\n  → STB는 위상에 따라 의미가 완전히 다름")
        print("  → ZPOC에서 STB = 노이즈")
        print("  → SPS에서 STB = 확인점")
    
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
