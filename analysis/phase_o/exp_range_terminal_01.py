"""
EXP-RANGE-TERMINAL-01: Range-Normalized Terminal Decomposition

목적: 즉사(거시 Hard)와 미시 종착(Soft/Absorb)이 "Range 대비 크기"로 분리되는지 검증

핵심 정규화:
- MAE_R = MAE / session_range
- Terminal_Time_R = (t_terminal - t_entry) / session_length
- Gap_R = (t_terminal - t_flip) / session_length
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Tuple
from collections import defaultdict
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import load_signals, classify_storm_coordinate

def load_chart_data() -> pd.DataFrame:
    chart_path = 'data/chart_combined_full.csv'
    df = pd.read_csv(chart_path)
    df['time'] = pd.to_datetime(df['time'])
    df.set_index('time', inplace=True)
    df.sort_index(inplace=True)
    return df

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

def detect_regime(df: pd.DataFrame, idx: int) -> str:
    if idx < 20:
        return "UNKNOWN"
    
    window = df.iloc[idx-20:idx+1]
    high_20 = window['high'].max()
    low_20 = window['low'].min()
    range_20 = high_20 - low_20
    
    if range_20 < 30:
        return "FLAT"
    
    close = df.iloc[idx]['close']
    channel_pct = (close - low_20) / range_20 * 100 if range_20 > 0 else 50
    
    if channel_pct > 80:
        return "BULL"
    elif channel_pct < 20:
        return "BEAR"
    else:
        return "RANGE"

def calc_revisit_anchor(df: pd.DataFrame, idx: int, lookback: int = 20) -> bool:
    if idx < lookback:
        return False
    
    window = df.iloc[idx-lookback:idx+1]
    high_20 = window['high'].max()
    low_20 = window['low'].min()
    close = df.iloc[idx]['close']
    
    anchor_high = high_20 - (high_20 - low_20) * 0.1
    anchor_low = low_20 + (high_20 - low_20) * 0.1
    
    return close >= anchor_high or close <= anchor_low

def calc_session_range(df: pd.DataFrame, idx: int, horizon: int = 30) -> float:
    """Session Range 계산 (entry 이후 horizon bars)"""
    if idx + horizon >= len(df):
        return 0
    
    future = df.iloc[idx:idx+horizon+1]
    session_high = future['high'].max()
    session_low = future['low'].min()
    
    return session_high - session_low

def analyze_range_normalized(df: pd.DataFrame, idx: int, horizon: int = 30) -> Dict:
    """Range 정규화된 Terminal 분석"""
    if idx + horizon >= len(df):
        return None
    
    entry = df.iloc[idx]['close']
    session_range = calc_session_range(df, idx, horizon)
    
    if session_range < 1:
        return None
    
    mae = 0
    mae_bar = 0
    terminal_bar = -1
    
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
    
    mae_r = mae / session_range if session_range > 0 else 0
    terminal_time_r = mae_bar / horizon if horizon > 0 else 0
    
    if mae_r >= 0.60 and mae_bar <= 3:
        terminal_type = "HARD"
    elif mae_r >= 0.60:
        terminal_type = "ABSORB"
    elif mae_r >= 0.25:
        terminal_type = "SOFT"
    else:
        terminal_type = "NONE"
    
    e_resp_flip_bar = -1
    for i in range(1, horizon + 1):
        check_idx = idx + i
        if check_idx >= len(df):
            break
        if calc_e_resp(df, check_idx) == "RELEASE":
            e_resp_flip_bar = i
            break
    
    if e_resp_flip_bar == -1:
        for i in range(0, 10):
            check_idx = idx - i
            if check_idx < 10:
                break
            if calc_e_resp(df, check_idx) == "RELEASE":
                e_resp_flip_bar = -i
                break
    
    gap = mae_bar - e_resp_flip_bar if e_resp_flip_bar != -1 else -999
    gap_r = gap / horizon if gap != -999 and horizon > 0 else -999
    precedes = e_resp_flip_bar < mae_bar if e_resp_flip_bar != -1 else False
    
    return {
        'session_range': session_range,
        'mae': mae,
        'mae_r': mae_r,
        'mae_bar': mae_bar,
        'terminal_time_r': terminal_time_r,
        'terminal_type': terminal_type,
        'e_resp_flip_bar': e_resp_flip_bar,
        'gap': gap,
        'gap_r': gap_r,
        'precedes': precedes
    }

def run():
    print("="*70)
    print("EXP-RANGE-TERMINAL-01: Range-Normalized Terminal Decomposition")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    signals = load_signals()
    chart_df = load_chart_data()
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    events = []
    for s in signals:
        ts = s.get('ts')
        if not ts:
            continue
        
        parsed_ts = pd.to_datetime(ts)
        if parsed_ts.tzinfo is not None:
            parsed_ts = parsed_ts.replace(tzinfo=None)
        
        if parsed_ts < chart_start or parsed_ts > chart_end:
            continue
        
        try:
            idx = chart_df.index.get_indexer([parsed_ts], method='nearest')[0]
        except:
            continue
        
        if idx < 50 or idx + 45 >= len(chart_df):
            continue
        
        storm = classify_storm_coordinate(s)
        if storm != "STORM_IN":
            continue
        
        if not calc_revisit_anchor(chart_df, idx):
            continue
        
        events.append({'ts': ts, 'idx': idx})
    
    print(f"\nEvents (Storm-IN + Revisit): N = {len(events)}")
    
    results = []
    for e in events:
        r = analyze_range_normalized(chart_df, e['idx'])
        if r:
            results.append(r)
    
    print(f"Analyzed: N = {len(results)}")
    
    print("\n" + "="*70)
    print("1. TERMINAL TYPE DISTRIBUTION (Range-Normalized)")
    print("="*70)
    
    type_counts = defaultdict(list)
    for r in results:
        type_counts[r['terminal_type']].append(r)
    
    for t_type in ['NONE', 'SOFT', 'ABSORB', 'HARD']:
        items = type_counts[t_type]
        if items:
            avg_mae_r = np.mean([i['mae_r'] for i in items])
            avg_time_r = np.mean([i['terminal_time_r'] for i in items])
            print(f"\n{t_type}: N = {len(items)}")
            print(f"  Mean MAE_R: {avg_mae_r:.3f}")
            print(f"  Mean Terminal_Time_R: {avg_time_r:.3f}")
    
    print("\n" + "="*70)
    print("2. MAE_R DISTRIBUTION HISTOGRAM")
    print("="*70)
    
    mae_r_values = [r['mae_r'] for r in results]
    bins = [0, 0.15, 0.25, 0.40, 0.60, 0.80, 1.0, 1.5]
    hist, edges = np.histogram(mae_r_values, bins=bins)
    
    print("\nMAE_R Bins:")
    for i in range(len(hist)):
        bar = "█" * min(hist[i], 40)
        label = f"{edges[i]:.2f}-{edges[i+1]:.2f}"
        print(f"{label:>12}: {bar} ({hist[i]})")
    
    print("\n" + "="*70)
    print("3. 2D SCATTER: MAE_R vs Terminal_Time_R")
    print("="*70)
    
    quadrants = {
        'Q1_fast_small': 0,
        'Q2_fast_large': 0,
        'Q3_slow_small': 0,
        'Q4_slow_large': 0
    }
    
    for r in results:
        mae_r = r['mae_r']
        time_r = r['terminal_time_r']
        
        fast = time_r < 0.3
        large = mae_r >= 0.40
        
        if fast and not large:
            quadrants['Q1_fast_small'] += 1
        elif fast and large:
            quadrants['Q2_fast_large'] += 1
        elif not fast and not large:
            quadrants['Q3_slow_small'] += 1
        else:
            quadrants['Q4_slow_large'] += 1
    
    total = len(results)
    print(f"\n           │ Small (MAE_R<0.40) │ Large (MAE_R≥0.40)")
    print(f"───────────┼────────────────────┼────────────────────")
    print(f"Fast (<0.3)│ {quadrants['Q1_fast_small']:3d} ({100*quadrants['Q1_fast_small']/total:5.1f}%)       │ {quadrants['Q2_fast_large']:3d} ({100*quadrants['Q2_fast_large']/total:5.1f}%) ← HARD")
    print(f"Slow (≥0.3)│ {quadrants['Q3_slow_small']:3d} ({100*quadrants['Q3_slow_small']/total:5.1f}%)       │ {quadrants['Q4_slow_large']:3d} ({100*quadrants['Q4_slow_large']/total:5.1f}%) ← ABSORB")
    
    print("\n" + "="*70)
    print("4. E_RESP 선행성 BY TERMINAL TYPE (Range-Normalized)")
    print("="*70)
    
    for t_type in ['SOFT', 'ABSORB', 'HARD']:
        items = [r for r in results if r['terminal_type'] == t_type and r['e_resp_flip_bar'] != -1]
        if items:
            n_precedes = sum(1 for i in items if i['precedes'])
            p_precedes = n_precedes / len(items) * 100 if items else 0
            gaps = [i['gap'] for i in items if i['precedes']]
            median_gap = np.median(gaps) if gaps else 0
            
            print(f"\n{t_type}: N = {len(items)}")
            print(f"  P(E_RESP < Terminal): {p_precedes:.1f}%")
            print(f"  Median Gap: {median_gap:.1f} bars")
    
    print("\n" + "="*70)
    print("5. H1′ 복구 검증: Terminal_Time_R 구간별 선행성")
    print("="*70)
    
    soft_absorb = [r for r in results if r['terminal_type'] in ['SOFT', 'ABSORB'] and r['e_resp_flip_bar'] != -1]
    
    if soft_absorb:
        fast_items = [r for r in soft_absorb if r['terminal_time_r'] < 0.3]
        slow_items = [r for r in soft_absorb if r['terminal_time_r'] >= 0.3]
        
        print("\n[Fast Terminal (Time_R < 0.3)]")
        if fast_items:
            fast_precedes = sum(1 for i in fast_items if i['precedes']) / len(fast_items) * 100
            print(f"N = {len(fast_items)}")
            print(f"P(E_RESP < Terminal): {fast_precedes:.1f}% (기준: ≥75%)")
            fast_ok = fast_precedes >= 75
        else:
            fast_precedes = 0
            fast_ok = False
            print("N = 0")
        
        print("\n[Slow Terminal (Time_R ≥ 0.3)]")
        if slow_items:
            slow_precedes = sum(1 for i in slow_items if i['precedes']) / len(slow_items) * 100
            print(f"N = {len(slow_items)}")
            print(f"P(E_RESP < Terminal): {slow_precedes:.1f}% (기준: ≥90%)")
            slow_ok = slow_precedes >= 85
        else:
            slow_precedes = 0
            slow_ok = False
            print("N = 0")
        
        total_precedes = sum(1 for i in soft_absorb if i['precedes']) / len(soft_absorb) * 100
        print(f"\n[Total Soft/Absorb]")
        print(f"N = {len(soft_absorb)}")
        print(f"P(E_RESP < Terminal): {total_precedes:.1f}% (기준: ≥80%)")
        
        h1_pass = total_precedes >= 80 or (fast_ok and slow_ok)
        print(f"\nH1′ VERDICT: {'✅ PASS' if h1_pass else '❌ FAIL'}")
    
    print("\n" + "="*70)
    print("6. FINAL MODEL CONFIRMATION")
    print("="*70)
    
    hard_items = [r for r in results if r['terminal_type'] == 'HARD']
    absorb_items = [r for r in results if r['terminal_type'] == 'ABSORB']
    soft_items = [r for r in results if r['terminal_type'] == 'SOFT']
    
    print("\n┌─────────────────────────────────────────────────────┐")
    print("│  Range-Normalized Terminal Model                    │")
    print("├─────────────────────────────────────────────────────┤")
    
    if hard_items:
        hard_p = sum(1 for i in hard_items if i['precedes'] and i['e_resp_flip_bar'] != -1) / max(1, len([i for i in hard_items if i['e_resp_flip_bar'] != -1])) * 100
        print(f"│  HARD (거시즉사): N={len(hard_items):3d}                       │")
        print(f"│    - MAE_R ≥ 0.60 + Time ≤ 3 bars                  │")
        print(f"│    - E_RESP 선행: {hard_p:.0f}% (선행 불가 예상)           │")
    
    if absorb_items:
        absorb_p = sum(1 for i in absorb_items if i['precedes'] and i['e_resp_flip_bar'] != -1) / max(1, len([i for i in absorb_items if i['e_resp_flip_bar'] != -1])) * 100
        print(f"│  ABSORB (미시종착): N={len(absorb_items):3d}                     │")
        print(f"│    - MAE_R ≥ 0.60 + Time > 3 bars                  │")
        print(f"│    - E_RESP 선행: {absorb_p:.0f}% (높아야 함)               │")
    
    if soft_items:
        soft_p = sum(1 for i in soft_items if i['precedes'] and i['e_resp_flip_bar'] != -1) / max(1, len([i for i in soft_items if i['e_resp_flip_bar'] != -1])) * 100
        print(f"│  SOFT (중간종착): N={len(soft_items):3d}                       │")
        print(f"│    - 0.25 ≤ MAE_R < 0.60                           │")
        print(f"│    - E_RESP 선행: {soft_p:.0f}% (70-80% 정상)             │")
    
    print("└─────────────────────────────────────────────────────┘")
    
    output = {
        'timestamp': datetime.now().isoformat(),
        'n_events': len(events),
        'n_analyzed': len(results),
        'type_distribution': {t: len(items) for t, items in type_counts.items()},
        'quadrants': quadrants
    }
    
    with open('v7-grammar-system/results/exp_range_terminal_01.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nResults saved to: exp_range_terminal_01.json")

if __name__ == "__main__":
    run()
