"""
EXP-ZPOC-PHASE-DECOMP-01: ZPOC/POC/블랙라인 분해 검증
======================================================
질문: ZPOC 구간은 정말로 ER low가 유지되는 전이 전 위상인가?

구조 (검증 대상):
  ZPOC = ER↓ + depth 정체 (전이 전 위상)
  POC = 전이 후 안정점
  BLACK LINE = 행위 의미가 바뀌는 경계

검증:
  1. ZPOC 후보 구간 추출 (ER < 0.25 연속)
  2. ZPOC → TRANSITION 확률 측정
  3. ZPOC 구간의 depth 특성 분석
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple

RESULT_FILE = "v7-grammar-system/results/exp_zpoc_phase_decomp_01.json"

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

def calc_depth_trend(depths: List[float], idx: int, k: int = 5) -> float:
    if idx < k:
        return 0.0
    window = depths[idx - k:idx + 1]
    if len(window) < 2:
        return 0.0
    return (window[-1] - window[0]) / k

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

def detect_zpoc_zones(er_series: List[float], min_duration: int = 5, er_threshold: float = 0.25) -> List[Tuple[int, int]]:
    """ZPOC 구간 감지: ER < threshold가 min_duration 이상 연속"""
    zones = []
    start = None
    
    for i, er in enumerate(er_series):
        if er < er_threshold:
            if start is None:
                start = i
        else:
            if start is not None:
                duration = i - start
                if duration >= min_duration:
                    zones.append((start, i - 1))
                start = None
    
    if start is not None:
        duration = len(er_series) - start
        if duration >= min_duration:
            zones.append((start, len(er_series) - 1))
    
    return zones

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-ZPOC-PHASE-DECOMP-01: ZPOC/POC/블랙라인 분해")
    print("=" * 70)
    
    print("\n[1] Generating time series...")
    depth_series = []
    er_series = []
    for idx in range(len(df)):
        depth_series.append(calc_depth(df, idx))
        er_series.append(calc_er(df, idx))
    
    depth_trend_series = []
    for idx in range(len(df)):
        depth_trend_series.append(calc_depth_trend(depth_series, idx))
    
    print(f"  Total bars: {len(df)}")
    
    print("\n[2] Detecting TRANSITION events...")
    transitions = detect_transitions(depth_series)
    transition_set = set(transitions)
    print(f"  TRANSITION events: {len(transitions)}")
    
    print("\n[3] Detecting ZPOC zones (ER < 0.25, duration >= 5)...")
    zpoc_zones = detect_zpoc_zones(er_series, min_duration=5, er_threshold=0.25)
    print(f"  ZPOC zones detected: {len(zpoc_zones)}")
    
    total_zpoc_bars = sum(end - start + 1 for start, end in zpoc_zones)
    print(f"  Total ZPOC bars: {total_zpoc_bars} ({100*total_zpoc_bars/len(df):.1f}%)")
    
    print("\n[4] ZPOC → TRANSITION probability...")
    
    zpoc_with_transition = 0
    zpoc_transition_within = {5: 0, 10: 0, 20: 0}
    
    for start, end in zpoc_zones:
        has_transition = False
        for window in [5, 10, 20]:
            zone_end_window = range(end + 1, min(end + 1 + window, len(df)))
            for t in zone_end_window:
                if t in transition_set:
                    zpoc_transition_within[window] += 1
                    has_transition = True
                    break
        if has_transition:
            zpoc_with_transition += 1
    
    zpoc_transition_rate = zpoc_with_transition / len(zpoc_zones) if zpoc_zones else 0
    
    print(f"  ZPOC zones followed by TRANSITION: {zpoc_with_transition}/{len(zpoc_zones)} ({100*zpoc_transition_rate:.1f}%)")
    for window, count in zpoc_transition_within.items():
        rate = count / len(zpoc_zones) if zpoc_zones else 0
        print(f"    Within {window} bars: {count} ({100*rate:.1f}%)")
    
    print("\n[5] Baseline comparison...")
    
    zpoc_bar_set = set()
    for start, end in zpoc_zones:
        zpoc_bar_set.update(range(start, end + 1))
    
    non_zpoc_bars = [i for i in range(30, len(df) - 30) if i not in zpoc_bar_set]
    
    np.random.seed(42)
    n_baseline_zones = min(len(non_zpoc_bars) // 10, len(zpoc_zones) * 2)
    baseline_starts = np.random.choice(non_zpoc_bars, size=n_baseline_zones, replace=False)
    
    baseline_with_transition = 0
    baseline_transition_within = {5: 0, 10: 0, 20: 0}
    
    for start in baseline_starts:
        end = start + 5
        for window in [5, 10, 20]:
            zone_end_window = range(end + 1, min(end + 1 + window, len(df)))
            for t in zone_end_window:
                if t in transition_set:
                    baseline_transition_within[window] += 1
                    if window == 5:
                        baseline_with_transition += 1
                    break
    
    baseline_rate = baseline_with_transition / n_baseline_zones if n_baseline_zones > 0 else 0
    
    print(f"  Baseline zones followed by TRANSITION: {baseline_with_transition}/{n_baseline_zones} ({100*baseline_rate:.1f}%)")
    
    lift = zpoc_transition_rate / baseline_rate if baseline_rate > 0 else 0
    print(f"  Lift (ZPOC vs Baseline): {lift:.2f}")
    
    print("\n[6] ZPOC depth characteristics...")
    
    zpoc_depth_stats = []
    zpoc_depth_trend_stats = []
    
    for start, end in zpoc_zones:
        zone_depths = depth_series[start:end + 1]
        zone_trends = depth_trend_series[start:end + 1]
        
        zpoc_depth_stats.append({
            'mean': np.mean(zone_depths),
            'std': np.std(zone_depths),
            'range': max(zone_depths) - min(zone_depths)
        })
        zpoc_depth_trend_stats.append({
            'mean': np.mean(zone_trends),
            'std': np.std(zone_trends),
            'abs_mean': np.mean(np.abs(zone_trends))
        })
    
    avg_depth_mean = np.mean([s['mean'] for s in zpoc_depth_stats])
    avg_depth_std = np.mean([s['std'] for s in zpoc_depth_stats])
    avg_depth_range = np.mean([s['range'] for s in zpoc_depth_stats])
    avg_trend_abs = np.mean([s['abs_mean'] for s in zpoc_depth_trend_stats])
    
    print(f"  ZPOC avg depth: {avg_depth_mean:.3f}")
    print(f"  ZPOC depth volatility (std): {avg_depth_std:.3f}")
    print(f"  ZPOC depth range: {avg_depth_range:.3f}")
    print(f"  ZPOC depth_trend abs avg: {avg_trend_abs:.4f}")
    
    baseline_depths = [depth_series[i] for i in non_zpoc_bars[:1000]]
    baseline_depth_mean = np.mean(baseline_depths)
    baseline_depth_std = np.std(baseline_depths)
    
    print(f"  Baseline avg depth: {baseline_depth_mean:.3f}")
    print(f"  Baseline depth std: {baseline_depth_std:.3f}")
    
    print("\n[7] POC SETTLE analysis (post-transition)...")
    
    post_transition_er = []
    post_transition_depth_stability = []
    
    for t in transitions:
        if t + 10 >= len(df):
            continue
        post_er = er_series[t + 5:t + 15]
        post_depth = depth_series[t + 5:t + 15]
        
        if post_er:
            post_transition_er.append(np.mean(post_er))
        if len(post_depth) >= 2:
            post_transition_depth_stability.append(np.std(post_depth))
    
    avg_post_er = np.mean(post_transition_er) if post_transition_er else 0
    avg_post_depth_stability = np.mean(post_transition_depth_stability) if post_transition_depth_stability else 0
    
    print(f"  Post-transition ER (t+5 to t+15): {avg_post_er:.3f}")
    print(f"  Post-transition depth stability: {avg_post_depth_stability:.3f}")
    
    er_recovery = avg_post_er > 0.30
    print(f"  ER recovery (> 0.30): {er_recovery}")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "n_transitions": len(transitions),
            "n_zpoc_zones": len(zpoc_zones),
            "total_zpoc_bars": total_zpoc_bars,
            "zpoc_coverage": float(total_zpoc_bars / len(df))
        },
        "zpoc_to_transition": {
            "rate": float(zpoc_transition_rate),
            "within_5": float(zpoc_transition_within[5] / len(zpoc_zones)) if zpoc_zones else 0,
            "within_10": float(zpoc_transition_within[10] / len(zpoc_zones)) if zpoc_zones else 0,
            "within_20": float(zpoc_transition_within[20] / len(zpoc_zones)) if zpoc_zones else 0,
            "baseline_rate": float(baseline_rate),
            "lift": float(lift)
        },
        "zpoc_characteristics": {
            "avg_depth": float(avg_depth_mean),
            "depth_volatility": float(avg_depth_std),
            "depth_range": float(avg_depth_range),
            "trend_abs_avg": float(avg_trend_abs)
        },
        "poc_settle": {
            "post_transition_er": float(avg_post_er),
            "depth_stability": float(avg_post_depth_stability),
            "er_recovery": bool(er_recovery)
        },
        "validation": {
            "zpoc_is_pretransition_phase": bool(lift > 1.5),
            "poc_settles_after_transition": bool(er_recovery),
            "structure_confirmed": bool(lift > 1.5 and er_recovery)
        }
    }
    
    print(f"\n  ZPOC → TRANSITION lift: {lift:.2f}")
    print(f"  ZPOC is pre-transition phase: {results['validation']['zpoc_is_pretransition_phase']}")
    print(f"  POC settles after transition: {results['validation']['poc_settles_after_transition']}")
    print(f"\n  STRUCTURE CONFIRMED: {results['validation']['structure_confirmed']}")
    
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
