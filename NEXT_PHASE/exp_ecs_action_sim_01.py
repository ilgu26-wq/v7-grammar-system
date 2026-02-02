"""
EXP-ECS-ACTION-SIM-01: Effective Connectivity Score + 행동 시뮬레이션
====================================================================
핵심 발견:
  - alive가 많을수록 오히려 위험 (과결속 현상)
  - (alive=3, zpoc=1, htf=0) = 40% collapse = 가장 안전

설계:
  1. ECS (Effective Connectivity Score) 계산
  2. 과결속 패널티 적용
  3. ACTION_MASK 시뮬레이션
  
ECS 가중치:
  ZPOC: +2.0 (가장 중요)
  HTF: -1.5 (살아있으면 위험)
  Range: +1.0
  Depth: +0.8
  τ: +0.5
  ER: +0.3
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
import json
from datetime import datetime
import os

RESULT_FILE = "v7-grammar-system/results/exp_ecs_action_sim_01.json"

WEIGHTS = {
    'zpoc_alive': 2.0,
    'htf_alive': -1.5,
    'range_alive': 1.0,
    'depth_alive': 0.8,
    'tau_alive': 0.5,
    'er_alive': 0.3
}

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
    rolling_high = df['high'].rolling(lookback, min_periods=1).max()
    rolling_low = df['low'].rolling(lookback, min_periods=1).min()
    depth = (df['close'] - rolling_low) / (rolling_high - rolling_low + 0.001)
    return depth

def calc_zpoc(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    vol = df['range'].replace(0, 1)
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    zpoc = (typical_price * vol).rolling(lookback, min_periods=1).sum() / vol.rolling(lookback, min_periods=1).sum()
    return zpoc

def resample_to_htf(df: pd.DataFrame, period: int) -> pd.DataFrame:
    htf = pd.DataFrame()
    groups = len(df) // period
    for i in range(groups):
        start = i * period
        end = start + period
        window = df.iloc[start:end]
        htf = pd.concat([htf, pd.DataFrame({
            'open': [window['open'].iloc[0]],
            'high': [window['high'].max()],
            'low': [window['low'].min()],
            'close': [window['close'].iloc[-1]],
            'bar_start': [start],
            'bar_end': [end - 1]
        })], ignore_index=True)
    return htf

def find_ignition_events(df: pd.DataFrame, er_threshold: float = 0.7) -> List[int]:
    events = []
    for i in range(1, len(df)):
        if df['er'].iloc[i] > er_threshold and df['er'].iloc[i-1] < er_threshold:
            events.append(i)
    return events

def check_strict_retouch(df: pd.DataFrame, ignition_idx: int, lookforward: int = 20) -> Tuple[bool, int]:
    if ignition_idx + lookforward >= len(df):
        return False, 0
    
    pre_idx = max(0, ignition_idx - 5)
    baseline_er = df['er'].iloc[pre_idx:ignition_idx].mean()
    baseline_depth = df['depth'].iloc[pre_idx:ignition_idx].mean()
    ignition_price = df['close'].iloc[ignition_idx]
    price_band = df['range'].iloc[ignition_idx] * 2
    
    for i in range(1, lookforward + 1):
        future_idx = ignition_idx + i
        price_ok = abs(df['close'].iloc[future_idx] - ignition_price) < price_band
        depth_ok = abs(df['depth'].iloc[future_idx] - baseline_depth) < 0.15
        er_ok = df['er'].iloc[future_idx] > baseline_er * 0.7
        
        if price_ok and depth_ok and er_ok:
            return True, i
    
    return False, 0

def check_hard_collapse(df: pd.DataFrame, dwell_end: int, ignition_price: float, lookforward: int = 30) -> bool:
    if dwell_end + lookforward >= len(df):
        return False
    
    future_window = df.iloc[dwell_end:dwell_end + lookforward + 1]
    
    er_min = future_window['er'].min()
    condition_1 = er_min < 0.20
    
    er_drop = future_window['er'].iloc[0] - future_window['er'].min()
    condition_2 = er_drop > 0.40
    
    price_band = df['range'].iloc[dwell_end] * 3
    no_recovery_count = sum(1 for i in range(len(future_window)) 
                           if abs(future_window['close'].iloc[i] - ignition_price) > price_band)
    condition_3 = no_recovery_count >= lookforward * 0.8
    
    return sum([condition_1, condition_2, condition_3]) >= 2

def compute_full_connectivity(df: pd.DataFrame, bar_idx: int, 
                               htf_5m_ignitions: List[Tuple[int, int]], 
                               htf_15m_ignitions: List[Tuple[int, int]],
                               er_baseline: float, depth_baseline: float,
                               range_q25: float, range_q75: float,
                               tau_q25: float, tau_q75: float,
                               dwell_time: int) -> Dict:
    
    htf_5m = any(start - 5 <= bar_idx <= end + 5 for start, end in htf_5m_ignitions)
    htf_15m = any(start - 15 <= bar_idx <= end + 15 for start, end in htf_15m_ignitions)
    htf_alive = 1 if (htf_5m or htf_15m) else 0
    
    current_zpoc = df['zpoc'].iloc[bar_idx]
    ignition_price = df['close'].iloc[bar_idx - dwell_time] if bar_idx >= dwell_time else df['close'].iloc[bar_idx]
    zpoc_distance = abs(current_zpoc - ignition_price)
    price_range = df['range'].iloc[bar_idx] if df['range'].iloc[bar_idx] > 0 else 1
    zpoc_alive = 1 if zpoc_distance < price_range * 3 else 0
    
    depth_alive = 1 if abs(df['depth'].iloc[bar_idx] - depth_baseline) < 0.2 else 0
    er_alive = 1 if df['er'].iloc[bar_idx] > er_baseline * 0.6 else 0
    range_alive = 1 if range_q25 <= df['range'].iloc[bar_idx] <= range_q75 * 1.5 else 0
    tau_alive = 1 if tau_q25 <= dwell_time <= tau_q75 * 1.5 else 0
    
    alive_count = htf_alive + zpoc_alive + depth_alive + er_alive + range_alive + tau_alive
    
    nodes = {
        'htf_alive': htf_alive,
        'zpoc_alive': zpoc_alive,
        'depth_alive': depth_alive,
        'er_alive': er_alive,
        'range_alive': range_alive,
        'tau_alive': tau_alive
    }
    
    ecs = sum(WEIGHTS[k] * v for k, v in nodes.items())
    
    penalty = 0
    if alive_count >= 5 and htf_alive == 1:
        penalty = 1.5
    elif alive_count >= 6:
        penalty = 1.0
    
    ecs_penalized = ecs - penalty
    
    return {
        'alive_count': alive_count,
        'ecs': round(ecs, 2),
        'ecs_penalized': round(ecs_penalized, 2),
        'penalty': penalty,
        **nodes
    }

def get_action_mask_v2(state: Dict) -> float:
    """ACTION_MASK v2 로직"""
    if state['zpoc_alive'] == 0:
        return 0.0
    
    if state['htf_alive'] == 1 and state['alive_count'] >= 4:
        return 0.0
    
    if state['ecs_penalized'] < 1.0:
        return 0.0
    
    if state['ecs_penalized'] < 2.0:
        return 0.5
    
    return 1.0

def run_simulation(events: List[Dict]) -> Dict:
    """ACTION_MASK 시뮬레이션"""
    
    blocked = {'total': 0, 'collapsed': 0, 'suspended': 0}
    half = {'total': 0, 'collapsed': 0, 'suspended': 0}
    passed = {'total': 0, 'collapsed': 0, 'suspended': 0}
    
    for event in events:
        mask = get_action_mask_v2(event)
        
        if mask == 0.0:
            blocked['total'] += 1
            if event['collapsed']:
                blocked['collapsed'] += 1
            else:
                blocked['suspended'] += 1
        elif mask == 0.5:
            half['total'] += 1
            if event['collapsed']:
                half['collapsed'] += 1
            else:
                half['suspended'] += 1
        else:
            passed['total'] += 1
            if event['collapsed']:
                passed['collapsed'] += 1
            else:
                passed['suspended'] += 1
    
    return {
        'blocked': blocked,
        'half_sized': half,
        'passed': passed
    }

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-ECS-ACTION-SIM-01")
    print("Effective Connectivity Score + 행동 시뮬레이션")
    print("=" * 70)
    
    print("\n[1] Computing metrics...")
    df['range'] = df['high'] - df['low']
    df['er'] = calc_er(df['close'])
    df['depth'] = calc_depth(df)
    df['zpoc'] = calc_zpoc(df)
    
    range_q25 = df['range'].quantile(0.25)
    range_q75 = df['range'].quantile(0.75)
    
    print("\n[2] Computing HTF structure...")
    htf_5m = resample_to_htf(df, 5)
    htf_15m = resample_to_htf(df, 15)
    htf_5m['er'] = calc_er(htf_5m['close'])
    htf_15m['er'] = calc_er(htf_15m['close'])
    
    ignitions_5m = [(int(htf_5m.iloc[i]['bar_start']), int(htf_5m.iloc[i]['bar_end'])) 
                   for i in find_ignition_events(htf_5m) if i < len(htf_5m)]
    ignitions_15m = [(int(htf_15m.iloc[i]['bar_start']), int(htf_15m.iloc[i]['bar_end'])) 
                    for i in find_ignition_events(htf_15m) if i < len(htf_15m)]
    
    print("\n[3] Collecting events...")
    ignitions_1m = find_ignition_events(df)
    
    strict_events = []
    for idx in ignitions_1m:
        ok, dwell = check_strict_retouch(df, idx)
        if ok:
            strict_events.append((idx, dwell))
    
    all_dwells = [d for _, d in strict_events]
    tau_q25 = np.percentile(all_dwells, 25) if all_dwells else 1
    tau_q75 = np.percentile(all_dwells, 75) if all_dwells else 10
    
    events = []
    for ignition_idx, dwell_time in strict_events:
        dwell_end = ignition_idx + dwell_time
        if dwell_end >= len(df):
            continue
        
        ignition_price = df['close'].iloc[ignition_idx]
        pre_idx = max(0, ignition_idx - 5)
        er_baseline = df['er'].iloc[pre_idx:ignition_idx].mean()
        depth_baseline = df['depth'].iloc[pre_idx:ignition_idx].mean()
        
        state = compute_full_connectivity(
            df, dwell_end, ignitions_5m, ignitions_15m,
            er_baseline, depth_baseline, range_q25, range_q75, tau_q25, tau_q75, dwell_time
        )
        
        is_collapse = check_hard_collapse(df, dwell_end, ignition_price)
        
        events.append({
            'ignition_idx': ignition_idx,
            'collapsed': is_collapse,
            **state
        })
    
    total = len(events)
    collapsed = sum(1 for e in events if e['collapsed'])
    
    print(f"  Total events: {total}")
    print(f"  Collapsed: {collapsed} ({collapsed/total:.1%})")
    
    print("\n[4] ECS 분포 분석...")
    
    print("\n" + "=" * 70)
    print("ECS DISTRIBUTION")
    print("=" * 70)
    
    ecs_buckets = {}
    for event in events:
        bucket = int(event['ecs_penalized'])
        if bucket not in ecs_buckets:
            ecs_buckets[bucket] = {'N': 0, 'collapsed': 0}
        ecs_buckets[bucket]['N'] += 1
        if event['collapsed']:
            ecs_buckets[bucket]['collapsed'] += 1
    
    print(f"\n{'ECS Bucket':<12} {'N':>6} {'CR':>8}")
    print("-" * 30)
    
    for bucket in sorted(ecs_buckets.keys()):
        data = ecs_buckets[bucket]
        cr = data['collapsed'] / data['N'] if data['N'] > 0 else 0
        print(f"{bucket:>10}   {data['N']:>6} {cr:>7.1%}")
    
    print("\n[5] ACTION_MASK v2 시뮬레이션...")
    sim = run_simulation(events)
    
    print("\n" + "=" * 70)
    print("ACTION SIMULATION RESULTS")
    print("=" * 70)
    
    b = sim['blocked']
    h = sim['half_sized']
    p = sim['passed']
    
    print(f"\n[BLOCKED (MASK=0)]")
    print(f"  Total: {b['total']} ({b['collapsed']} collapsed, {b['suspended']} suspended)")
    
    print(f"\n[HALF-SIZED (MASK=0.5)]")
    print(f"  Total: {h['total']} ({h['collapsed']} collapsed, {h['suspended']} suspended)")
    
    print(f"\n[PASSED (MASK=1.0)]")
    print(f"  Total: {p['total']} ({p['collapsed']} collapsed, {p['suspended']} suspended)")
    if p['total'] > 0:
        print(f"  Collapse rate: {p['collapsed']/p['total']:.1%}")
    
    print("\n" + "=" * 70)
    print("PERFORMANCE METRICS")
    print("=" * 70)
    
    original_cr = collapsed / total
    passed_total = p['total'] + h['total']
    passed_collapsed = p['collapsed'] + h['collapsed']
    new_cr = passed_collapsed / passed_total if passed_total > 0 else 0
    
    improvement = original_cr - new_cr
    
    collapse_blocked = b['collapsed'] / collapsed if collapsed > 0 else 0
    suspended_blocked = b['suspended'] / (total - collapsed) if (total - collapsed) > 0 else 0
    
    print(f"\n  Original collapse rate: {original_cr:.1%}")
    print(f"  After-mask collapse rate: {new_cr:.1%}")
    print(f"  Net improvement: {improvement:+.1%}")
    print(f"\n  Collapse blocked: {collapse_blocked:.1%}")
    print(f"  Suspended blocked (false positive): {suspended_blocked:.1%}")
    
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    
    if improvement >= 0.20:
        print(f"\n  ✓✓ 강력한 효과: 붕괴율 {improvement:.1%} 감소")
        verdict = "STRONG_EFFECT"
    elif improvement >= 0.10:
        print(f"\n  ✓ 효과적: 붕괴율 {improvement:.1%} 감소")
        verdict = "EFFECTIVE"
    elif improvement > 0:
        print(f"\n  ~ 약한 효과: 붕괴율 {improvement:.1%} 감소")
        verdict = "WEAK_EFFECT"
    else:
        print(f"\n  ✗ 효과 없음")
        verdict = "NO_EFFECT"
    
    if p['total'] > 0 and p['collapsed'] / p['total'] < 0.50:
        print(f"\n  🎯 통과된 이벤트 중 생존율 > 50%!")
    
    print("\n" + "=" * 70)
    
    return {
        'experiment': 'EXP-ECS-ACTION-SIM-01',
        'timestamp': datetime.now().isoformat(),
        'total_events': total,
        'original_collapse_rate': round(original_cr, 3),
        'after_mask_collapse_rate': round(new_cr, 3),
        'improvement': round(improvement, 3),
        'ecs_distribution': ecs_buckets,
        'simulation': sim,
        'verdict': verdict
    }

def main():
    data_files = ["data/mnq_december_2025.csv", "data/mnq_with_ratio.csv"]
    
    df = None
    for path in data_files:
        if os.path.exists(path):
            print(f"Loading data from: {path}")
            df = pd.read_csv(path)
            break
    
    if df is None:
        print("ERROR: No data file found")
        return
    
    df.columns = df.columns.str.lower()
    df = df.dropna(subset=['open', 'high', 'low', 'close'])
    print(f"Loaded {len(df)} bars")
    
    results = run_experiment(df)
    
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {RESULT_FILE}")

if __name__ == "__main__":
    main()
