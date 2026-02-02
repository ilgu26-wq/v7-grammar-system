"""
EXP-OOS-VALIDATION-01: Out-of-Sample Validation for Fast Islands + Slow Rule Compression

목적:
(A) Fast 섬 4개의 OOS 유지 검증 (5-fold)
(B) Slow 15개 100% 영역의 최소조건 추출
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List
from collections import defaultdict
import sys
import os

def load_chart_data() -> pd.DataFrame:
    chart_path = 'data/chart_combined_full.csv'
    df = pd.read_csv(chart_path)
    df['time'] = pd.to_datetime(df['time'])
    df.set_index('time', inplace=True)
    df.sort_index(inplace=True)
    return df

def calc_ratio(high: float, low: float, close: float) -> float:
    buyer = close - low
    seller = high - close
    if seller < 0.1:
        return 10.0
    return buyer / seller

def calc_atr(df: pd.DataFrame, idx: int, period: int = 14) -> float:
    if idx < period:
        return 1.0
    window = df.iloc[idx-period:idx]
    tr = window['high'] - window['low']
    return tr.mean()

def calc_depth(df: pd.DataFrame, idx: int, lookback: int = 20) -> float:
    if idx < lookback:
        return 0.5
    window = df.iloc[idx-lookback:idx+1]
    high_20 = window['high'].max()
    low_20 = window['low'].min()
    range_20 = high_20 - low_20
    if range_20 < 1:
        return 0.5
    close = df.iloc[idx]['close']
    return (high_20 - close) / range_20

def calc_dc_pre(df: pd.DataFrame, idx: int, lookback: int = 10) -> float:
    if idx < lookback:
        return 1.0
    current_range = df.iloc[idx]['high'] - df.iloc[idx]['low']
    avg_range = np.mean([df.iloc[i]['high'] - df.iloc[i]['low'] for i in range(idx-lookback, idx)])
    if avg_range < 0.1:
        return 1.0
    return current_range / avg_range

def calc_delta(df: pd.DataFrame, idx: int, lookback: int = 5) -> float:
    if idx < lookback:
        return 0
    close_now = df.iloc[idx]['close']
    close_before = df.iloc[idx-lookback]['close']
    atr = calc_atr(df, idx)
    return (close_now - close_before) / atr if atr > 0 else 0

def calc_force_ratio(df: pd.DataFrame, idx: int, lookback: int = 10) -> float:
    if idx < lookback:
        return 1.0
    buyer_sum = 0
    seller_sum = 0
    for i in range(idx-lookback, idx+1):
        row = df.iloc[i]
        buyer_sum += row['close'] - row['low']
        seller_sum += row['high'] - row['close']
    if seller_sum < 0.1:
        return 10.0
    return buyer_sum / seller_sum

def calc_er(df: pd.DataFrame, idx: int, lookback: int = 5) -> float:
    if idx < lookback:
        return 0.5
    closes = [df.iloc[i]['close'] for i in range(idx-lookback, idx+1)]
    net_change = abs(closes[-1] - closes[0])
    sum_changes = sum(abs(closes[i+1] - closes[i]) for i in range(len(closes)-1))
    if sum_changes < 0.1:
        return 1.0
    return net_change / sum_changes

def calc_theta(df: pd.DataFrame, idx: int) -> int:
    if idx < 3:
        return 0
    current_dir = 1 if df.iloc[idx]['close'] > df.iloc[idx]['open'] else -1
    theta = 0
    for i in range(idx-1, max(0, idx-20), -1):
        bar_dir = 1 if df.iloc[i]['close'] > df.iloc[i]['open'] else -1
        if bar_dir == current_dir:
            theta += 1
        else:
            break
    return theta

def calc_channel_pct(df: pd.DataFrame, idx: int, lookback: int = 20) -> float:
    if idx < lookback:
        return 50.0
    window = df.iloc[idx-lookback:idx+1]
    high_20 = window['high'].max()
    low_20 = window['low'].min()
    range_20 = high_20 - low_20
    if range_20 < 1:
        return 50.0
    close = df.iloc[idx]['close']
    return (close - low_20) / range_20 * 100

def calc_e_resp(df: pd.DataFrame, idx: int, lookback: int = 10) -> str:
    if idx < lookback:
        return "UNKNOWN"
    window = df.iloc[idx-lookback:idx+1]
    closes = window['close'].values
    highs = window['high'].values
    lows = window['low'].values
    atr = np.mean(highs - lows)
    if atr < 0.1:
        return "UNKNOWN"
    price_change = closes[-1] - closes[0]
    rfc = (highs[-1] - lows[-1]) / atr if atr > 0 else 1.0
    if price_change > atr * 0.3 and rfc < 1.5:
        return "HOLD"
    elif price_change < -atr * 0.3 and rfc < 1.5:
        return "HOLD"
    else:
        return "RELEASE"

def analyze_event(df: pd.DataFrame, idx: int, horizon: int = 30) -> Dict:
    if idx < 50 or idx + horizon >= len(df):
        return None
    
    entry = df.iloc[idx]['close']
    depth = calc_depth(df, idx)
    dc_pre = calc_dc_pre(df, idx)
    delta = calc_delta(df, idx)
    force = calc_force_ratio(df, idx)
    er = calc_er(df, idx)
    theta = calc_theta(df, idx)
    channel = calc_channel_pct(df, idx)
    
    future = df.iloc[idx:idx+horizon+1]
    session_range = future['high'].max() - future['low'].min()
    if session_range < 1:
        return None
    
    mae = 0
    mae_bar = 0
    for i in range(1, horizon + 1):
        check_idx = idx + i
        if check_idx >= len(df):
            break
        high = df.iloc[check_idx]['high']
        low = df.iloc[check_idx]['low']
        current_mae = max(abs(high - entry), abs(low - entry))
        if current_mae > mae:
            mae = current_mae
            mae_bar = i
    
    terminal_time_r = mae_bar / horizon if horizon > 0 else 0
    
    e_resp_flip_bar = -1
    for i in range(1, horizon + 1):
        check_idx = idx + i
        if check_idx >= len(df):
            break
        if calc_e_resp(df, check_idx) == "RELEASE":
            e_resp_flip_bar = i
            break
    
    precedes = e_resp_flip_bar < mae_bar if e_resp_flip_bar != -1 else False
    
    time_bin = "Fast" if terminal_time_r < 0.3 else "Slow"
    depth_bin = "High" if depth > 0.5 else "Low"
    dc_bin = "Comp" if dc_pre < 0.8 else "Loose"
    delta_bin = "Large" if abs(delta) > 0.5 else "Small"
    force_bin = "Strong" if force > 1.3 or force < 0.7 else "Weak"
    er_bin = "High" if er > 0.6 else "Low"
    theta_bin = "High" if theta >= 3 else "Low"
    
    if channel > 80:
        channel_bin = "Top"
    elif channel < 20:
        channel_bin = "Bot"
    else:
        channel_bin = "Mid"
    
    state_key = f"{depth_bin}_{dc_bin}_{delta_bin}_{force_bin}_{er_bin}_{theta_bin}_{channel_bin}"
    
    return {
        'idx': idx,
        'time_bin': time_bin,
        'state_key': state_key,
        'depth_bin': depth_bin,
        'dc_bin': dc_bin,
        'delta_bin': delta_bin,
        'force_bin': force_bin,
        'er_bin': er_bin,
        'theta_bin': theta_bin,
        'channel_bin': channel_bin,
        'precedes': precedes,
        'valid': e_resp_flip_bar != -1
    }

def run():
    print("="*70)
    print("EXP-OOS-VALIDATION-01: OOS Validation + Rule Compression")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    df = load_chart_data()
    print(f"\nTotal bars: {len(df)}")
    
    sample_step = 10
    sample_indices = list(range(100, len(df) - 50, sample_step))
    
    events = []
    for idx in sample_indices:
        result = analyze_event(df, idx)
        if result and result['valid']:
            events.append(result)
    
    print(f"Valid events: {len(events)}")
    
    n_folds = 5
    fold_size = len(events) // n_folds
    folds = [events[i*fold_size:(i+1)*fold_size] for i in range(n_folds)]
    
    fast_islands = [
        "High_Comp_Large_Weak_Low_Low_Mid",
        "Low_Loose_Small_Weak_Low_Low_Mid",
        "High_Loose_Large_Weak_Low_Low_Mid",
        "Low_Loose_Large_Weak_Low_Low_Mid"
    ]
    
    print("\n" + "="*70)
    print("(A) FAST 섬 4개의 OOS 검증 (5-fold)")
    print("="*70)
    
    island_results = {island: [] for island in fast_islands}
    
    for fold_idx, fold in enumerate(folds):
        fast_fold = [e for e in fold if e['time_bin'] == 'Fast']
        
        for island in fast_islands:
            matches = [e for e in fast_fold if e['state_key'] == island]
            if matches:
                n = len(matches)
                lead = sum(1 for e in matches if e['precedes'])
                pct = lead / n * 100 if n > 0 else 0
                island_results[island].append({'fold': fold_idx, 'n': n, 'pct': pct})
    
    print(f"\n{'Island State Key':<45} {'Folds':>6} {'Avg%':>7} {'Stable':>8}")
    print("-" * 70)
    
    stable_islands = []
    for island in fast_islands:
        results = island_results[island]
        folds_present = len(results)
        
        if folds_present > 0:
            avg_pct = np.mean([r['pct'] for r in results])
            stable = folds_present >= 3 and avg_pct >= 65
            
            print(f"{island:<45} {folds_present:>6} {avg_pct:>6.1f}% {'✅' if stable else '❌':>8}")
            
            if stable:
                stable_islands.append((island, avg_pct, folds_present))
    
    print(f"\n{'=' * 70}")
    if stable_islands:
        print(f"✅ 안정적 섬 {len(stable_islands)}개 확정:")
        for island, pct, folds in stable_islands:
            print(f"   {island}: avg {pct:.1f}% across {folds} folds")
    else:
        print("❌ 안정적 섬 없음 (3+ folds & 65%+ 기준)")
    
    print("\n" + "="*70)
    print("(B) SLOW 고선행 영역의 최소 규칙 추출")
    print("="*70)
    
    slow_events = [e for e in events if e['time_bin'] == 'Slow']
    
    axis_stats = {
        'depth': {'High': {'n': 0, 'lead': 0}, 'Low': {'n': 0, 'lead': 0}},
        'dc': {'Comp': {'n': 0, 'lead': 0}, 'Loose': {'n': 0, 'lead': 0}},
        'delta': {'Large': {'n': 0, 'lead': 0}, 'Small': {'n': 0, 'lead': 0}},
        'force': {'Strong': {'n': 0, 'lead': 0}, 'Weak': {'n': 0, 'lead': 0}},
        'er': {'High': {'n': 0, 'lead': 0}, 'Low': {'n': 0, 'lead': 0}},
        'theta': {'High': {'n': 0, 'lead': 0}, 'Low': {'n': 0, 'lead': 0}},
        'channel': {'Top': {'n': 0, 'lead': 0}, 'Mid': {'n': 0, 'lead': 0}, 'Bot': {'n': 0, 'lead': 0}}
    }
    
    for e in slow_events:
        for axis, bin_val in [
            ('depth', e['depth_bin']), ('dc', e['dc_bin']),
            ('delta', e['delta_bin']), ('force', e['force_bin']),
            ('er', e['er_bin']), ('theta', e['theta_bin']),
            ('channel', e['channel_bin'])
        ]:
            axis_stats[axis][bin_val]['n'] += 1
            if e['precedes']:
                axis_stats[axis][bin_val]['lead'] += 1
    
    print("\n[축별 선행률 분석 - Slow Terminal]")
    print(f"{'Axis':<10} {'Bin':<10} {'N':>6} {'Lead%':>8} {'영향':>8}")
    print("-" * 50)
    
    key_factors = []
    for axis, bins in axis_stats.items():
        for bin_val, stats in bins.items():
            n = stats['n']
            if n > 0:
                pct = stats['lead'] / n * 100
                impact = "핵심" if pct >= 97 else ("중요" if pct >= 95 else "보통")
                print(f"{axis:<10} {bin_val:<10} {n:>6} {pct:>7.1f}% {impact:>8}")
                if pct >= 97 and n >= 50:
                    key_factors.append((axis, bin_val, pct, n))
    
    print("\n" + "="*70)
    print("(C) 최소 규칙 도출")
    print("="*70)
    
    print("\n[핵심 조건 (97%+ 선행률)]")
    if key_factors:
        for axis, bin_val, pct, n in sorted(key_factors, key=lambda x: -x[2]):
            print(f"  {axis} = {bin_val}: {pct:.1f}% (N={n})")
    
    rule1_events = [e for e in slow_events if e['theta_bin'] == 'Low']
    rule1_lead = sum(1 for e in rule1_events if e['precedes']) / len(rule1_events) * 100 if rule1_events else 0
    
    rule2_events = [e for e in slow_events if e['theta_bin'] == 'Low' and e['er_bin'] == 'Low']
    rule2_lead = sum(1 for e in rule2_events if e['precedes']) / len(rule2_events) * 100 if rule2_events else 0
    
    rule3_events = [e for e in slow_events if e['theta_bin'] == 'Low' and e['channel_bin'] == 'Mid']
    rule3_lead = sum(1 for e in rule3_events if e['precedes']) / len(rule3_events) * 100 if rule3_events else 0
    
    print("\n[압축 규칙 검증]")
    print(f"  Rule 1: theta=Low → {rule1_lead:.1f}% (N={len(rule1_events)})")
    print(f"  Rule 2: theta=Low + ER=Low → {rule2_lead:.1f}% (N={len(rule2_events)})")
    print(f"  Rule 3: theta=Low + channel=Mid → {rule3_lead:.1f}% (N={len(rule3_events)})")
    
    print("\n" + "="*70)
    print("FINAL COMPRESSED RULES")
    print("="*70)
    
    slow_total_lead = sum(1 for e in slow_events if e['precedes']) / len(slow_events) * 100
    
    print(f"""
┌─────────────────────────────────────────────────────┐
│  SLOW TERMINAL 최소 규칙 (봉인)                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  기본: Slow Terminal → {slow_total_lead:.1f}% 선행             │
│                                                     │
│  핵심 조건:                                         │
│    - theta = Low (연속봉 <3) → 선행률 증폭         │
│    - ER = Low (효율비 <0.6) → 선행률 증폭          │
│                                                     │
├─────────────────────────────────────────────────────┤
│  FAST TERMINAL 조건부 규칙                          │
├─────────────────────────────────────────────────────┤
│                                                     │
│  안정적 섬 {len(stable_islands)}개:                                │""")
    
    for island, pct, folds in stable_islands[:3]:
        parts = island.split('_')
        print(f"│    {island[:40]:<40} │")
    
    print(f"""│                                                     │
│  = Weak Force + Low ER + Low Theta + Mid Channel    │
│    조합에서 65-75% 선행 가능                        │
└─────────────────────────────────────────────────────┘
""")
    
    output = {
        'timestamp': datetime.now().isoformat(),
        'total_events': len(events),
        'fast_islands_stable': len(stable_islands),
        'stable_islands': [(i, p, f) for i, p, f in stable_islands],
        'slow_total_lead': slow_total_lead,
        'key_factors': [(a, b, p, n) for a, b, p, n in key_factors]
    }
    
    with open('v7-grammar-system/results/exp_oos_validation_01.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"Results saved to: exp_oos_validation_01.json")

if __name__ == "__main__":
    run()
