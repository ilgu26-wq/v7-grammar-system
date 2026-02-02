"""
EXP-ORGANIZER-ABSENCE-TIMING-01: 델타 주최자 부재 시간 분석
============================================================
가설:
  H1: ZPOC(ER<0.25)는 옵션 만기 인접 구간에서 유의미하게 증가
  H2: 만기 구간에서 ZPOC 지속 시간이 길다
  H3: 만기 구간에서 ER 회복 속도가 느리다

정의:
  Organizer_Absent := ER < 0.25 (ZPOC 조건)
  만기 인접: 옵션 만기일 ±2 trading days
"""

import json
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

RESULT_FILE = "v7-grammar-system/results/exp_organizer_absence_timing_01.json"

def get_option_expiry_dates(start_date: datetime, end_date: datetime) -> List[datetime]:
    """NQ 옵션 만기일 (매월 3주차 금요일) 계산"""
    expiry_dates = []
    current = datetime(start_date.year, start_date.month, 1)
    
    while current <= end_date:
        first_day = datetime(current.year, current.month, 1)
        first_friday = first_day + timedelta(days=(4 - first_day.weekday() + 7) % 7)
        third_friday = first_friday + timedelta(weeks=2)
        
        if start_date <= third_friday <= end_date:
            expiry_dates.append(third_friday)
        
        if current.month == 12:
            current = datetime(current.year + 1, 1, 1)
        else:
            current = datetime(current.year, current.month + 1, 1)
    
    return expiry_dates

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
    print("EXP-ORGANIZER-ABSENCE-TIMING-01: 델타 주최자 부재 시간 분석")
    print("=" * 70)
    
    df['time'] = pd.to_datetime(df['time'])
    df['date'] = df['time'].dt.date
    
    start_date = df['time'].min()
    end_date = df['time'].max()
    print(f"\n  Data range: {start_date} to {end_date}")
    
    expiry_dates = get_option_expiry_dates(start_date, end_date)
    print(f"  Option expiry dates found: {len(expiry_dates)}")
    for exp in expiry_dates:
        print(f"    {exp.strftime('%Y-%m-%d')}")
    
    expiry_window = 2
    expiry_dates_set = set()
    for exp in expiry_dates:
        for offset in range(-expiry_window, expiry_window + 1):
            d = (exp + timedelta(days=offset)).date()
            expiry_dates_set.add(d)
    
    df['is_expiry_zone'] = df['date'].apply(lambda x: x in expiry_dates_set)
    
    print(f"\n  Bars in expiry zone: {df['is_expiry_zone'].sum()} ({100*df['is_expiry_zone'].mean():.1f}%)")
    
    print("\n[1] Computing ER and depth...")
    er_series = []
    depth_series = []
    for idx in range(len(df)):
        er_series.append(calc_er(df, idx))
        depth_series.append(calc_depth(df, idx))
    
    df['er'] = er_series
    df['depth'] = depth_series
    df['organizer_absent'] = df['er'] < 0.25
    
    print(f"  Total Organizer_Absent bars: {df['organizer_absent'].sum()} ({100*df['organizer_absent'].mean():.1f}%)")
    
    print("\n[2] Comparing expiry zone vs normal zone...")
    
    expiry_df = df[df['is_expiry_zone']]
    normal_df = df[~df['is_expiry_zone']]
    
    expiry_absent_rate = expiry_df['organizer_absent'].mean()
    normal_absent_rate = normal_df['organizer_absent'].mean()
    lift = expiry_absent_rate / normal_absent_rate if normal_absent_rate > 0 else 0
    
    print(f"\n  Expiry Zone:")
    print(f"    N: {len(expiry_df)}")
    print(f"    Organizer_Absent rate: {100*expiry_absent_rate:.1f}%")
    print(f"    Avg ER: {expiry_df['er'].mean():.3f}")
    
    print(f"\n  Normal Zone:")
    print(f"    N: {len(normal_df)}")
    print(f"    Organizer_Absent rate: {100*normal_absent_rate:.1f}%")
    print(f"    Avg ER: {normal_df['er'].mean():.3f}")
    
    print(f"\n  Lift (Expiry/Normal): {lift:.2f}")
    
    print("\n[3] ZPOC duration analysis...")
    
    def calc_zpoc_durations(sub_df):
        durations = []
        current_run = 0
        for absent in sub_df['organizer_absent']:
            if absent:
                current_run += 1
            else:
                if current_run >= 3:
                    durations.append(current_run)
                current_run = 0
        if current_run >= 3:
            durations.append(current_run)
        return durations
    
    expiry_durations = calc_zpoc_durations(expiry_df)
    normal_durations = calc_zpoc_durations(normal_df)
    
    avg_expiry_duration = np.mean(expiry_durations) if expiry_durations else 0
    avg_normal_duration = np.mean(normal_durations) if normal_durations else 0
    
    print(f"\n  Expiry Zone ZPOC runs: {len(expiry_durations)}")
    print(f"    Avg duration: {avg_expiry_duration:.1f} bars")
    
    print(f"\n  Normal Zone ZPOC runs: {len(normal_durations)}")
    print(f"    Avg duration: {avg_normal_duration:.1f} bars")
    
    duration_ratio = avg_expiry_duration / avg_normal_duration if avg_normal_duration > 0 else 0
    print(f"\n  Duration ratio (Expiry/Normal): {duration_ratio:.2f}")
    
    print("\n[4] ER recovery analysis...")
    
    transitions = detect_transitions(depth_series)
    transition_set = set(transitions)
    
    def calc_recovery_slope(sub_df, transitions_in_zone):
        slopes = []
        for t in transitions_in_zone:
            if t + 20 >= len(sub_df):
                continue
            idx_in_sub = sub_df.index.get_loc(t) if t in sub_df.index else None
            if idx_in_sub is None:
                continue
            
            post_er = sub_df.iloc[idx_in_sub:idx_in_sub+20]['er'].values
            if len(post_er) >= 10:
                slope = (post_er[-1] - post_er[0]) / len(post_er)
                slopes.append(slope)
        return slopes
    
    expiry_indices = set(expiry_df.index)
    normal_indices = set(normal_df.index)
    
    expiry_transitions = [t for t in transitions if t in expiry_indices]
    normal_transitions = [t for t in transitions if t in normal_indices]
    
    expiry_recovery = []
    normal_recovery = []
    
    for t in transitions:
        if t + 20 >= len(df):
            continue
        post_er = df.iloc[t:t+20]['er'].values
        if len(post_er) >= 10:
            slope = (post_er[-1] - post_er[0]) / len(post_er)
            if df.iloc[t]['is_expiry_zone']:
                expiry_recovery.append(slope)
            else:
                normal_recovery.append(slope)
    
    avg_expiry_recovery = np.mean(expiry_recovery) if expiry_recovery else 0
    avg_normal_recovery = np.mean(normal_recovery) if normal_recovery else 0
    
    print(f"\n  Expiry Zone transitions: {len(expiry_recovery)}")
    print(f"    Avg ER recovery slope: {avg_expiry_recovery:.4f}")
    
    print(f"\n  Normal Zone transitions: {len(normal_recovery)}")
    print(f"    Avg ER recovery slope: {avg_normal_recovery:.4f}")
    
    recovery_ratio = avg_expiry_recovery / avg_normal_recovery if avg_normal_recovery != 0 else 0
    print(f"\n  Recovery ratio (Expiry/Normal): {recovery_ratio:.2f}")
    
    print("\n[5] Hour-of-day analysis...")
    
    df['hour'] = df['time'].dt.hour
    hourly_absent = df.groupby('hour')['organizer_absent'].mean()
    
    print("\n  Organizer_Absent rate by hour (top 5):")
    top_hours = hourly_absent.nlargest(5)
    for hour, rate in top_hours.items():
        print(f"    {hour:02d}:00 - {100*rate:.1f}%")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "expiry_dates": [exp.strftime('%Y-%m-%d') for exp in expiry_dates],
            "expiry_window_days": expiry_window
        },
        "zone_comparison": {
            "expiry_n": len(expiry_df),
            "expiry_absent_rate": float(expiry_absent_rate),
            "expiry_avg_er": float(expiry_df['er'].mean()),
            "normal_n": len(normal_df),
            "normal_absent_rate": float(normal_absent_rate),
            "normal_avg_er": float(normal_df['er'].mean()),
            "lift": float(lift)
        },
        "duration": {
            "expiry_zpoc_runs": len(expiry_durations),
            "expiry_avg_duration": float(avg_expiry_duration),
            "normal_zpoc_runs": len(normal_durations),
            "normal_avg_duration": float(avg_normal_duration),
            "duration_ratio": float(duration_ratio)
        },
        "recovery": {
            "expiry_transitions": len(expiry_recovery),
            "expiry_avg_slope": float(avg_expiry_recovery),
            "normal_transitions": len(normal_recovery),
            "normal_avg_slope": float(avg_normal_recovery),
            "recovery_ratio": float(recovery_ratio)
        },
        "hourly": {h: float(r) for h, r in hourly_absent.items()},
        "validation": {
            "H1_expiry_increases_zpoc": bool(lift > 1.1),
            "H2_expiry_longer_duration": bool(duration_ratio > 1.1),
            "H3_expiry_slower_recovery": bool(recovery_ratio < 0.9),
            "timing_hypothesis_supported": bool(lift > 1.1 or duration_ratio > 1.1)
        }
    }
    
    print(f"\n  H1 (Expiry increases ZPOC): {results['validation']['H1_expiry_increases_zpoc']} (Lift: {lift:.2f})")
    print(f"  H2 (Expiry longer duration): {results['validation']['H2_expiry_longer_duration']} (Ratio: {duration_ratio:.2f})")
    print(f"  H3 (Expiry slower recovery): {results['validation']['H3_expiry_slower_recovery']} (Ratio: {recovery_ratio:.2f})")
    print(f"\n  TIMING HYPOTHESIS SUPPORTED: {results['validation']['timing_hypothesis_supported']}")
    
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
