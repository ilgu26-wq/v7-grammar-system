"""
EXP-ALL-LAWS-JOINT-01: Full Joint Distribution of All Laws

목적: 모든 법칙/센서/상태의 조합 분포를 만들고,
     그 조합에서 H1′ 선행성과 즉사/생존이 동시에 설명되는지 결과로 증명

데이터: chart_combined_full.csv 전체 (27,973 bars)
       필터 없이 모든 이벤트 사용

8축 조합:
1. Terminal_Time_R (Fast/Slow)
2. Depth_bin (Low/High)
3. DC_pre_bin (Compressed/Loose)
4. Delta_bin (Small/Large)
5. Force_bin (Weak/Strong)
6. ER_bin (Low/High)
7. Theta_bin (Low/High)
8. Channel_bin (Bottom/Mid/Top)
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Tuple, List
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
    """배율 = (close - low) / (high - close)"""
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
    """Depth = (high_20 - close) / range_20"""
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
    """DC = range compression (current / avg)"""
    if idx < lookback:
        return 1.0
    current_range = df.iloc[idx]['high'] - df.iloc[idx]['low']
    avg_range = np.mean([df.iloc[i]['high'] - df.iloc[i]['low'] for i in range(idx-lookback, idx)])
    if avg_range < 0.1:
        return 1.0
    return current_range / avg_range

def calc_delta(df: pd.DataFrame, idx: int, lookback: int = 5) -> float:
    """Delta = 가격 변화 / ATR"""
    if idx < lookback:
        return 0
    close_now = df.iloc[idx]['close']
    close_before = df.iloc[idx-lookback]['close']
    atr = calc_atr(df, idx)
    return (close_now - close_before) / atr if atr > 0 else 0

def calc_force_ratio(df: pd.DataFrame, idx: int, lookback: int = 10) -> float:
    """Force = sum(buyer) / sum(seller)"""
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
    """Efficiency Ratio = |net change| / sum(|changes|)"""
    if idx < lookback:
        return 0.5
    closes = [df.iloc[i]['close'] for i in range(idx-lookback, idx+1)]
    net_change = abs(closes[-1] - closes[0])
    sum_changes = sum(abs(closes[i+1] - closes[i]) for i in range(len(closes)-1))
    if sum_changes < 0.1:
        return 1.0
    return net_change / sum_changes

def calc_theta(df: pd.DataFrame, idx: int) -> int:
    """Theta = 연속 동일 방향 봉 수"""
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
    """Channel % = (close - low_20) / range_20 * 100"""
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
    """단일 이벤트의 8축 + 결과 분석"""
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
    session_high = future['high'].max()
    session_low = future['low'].min()
    session_range = session_high - session_low
    
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
    
    mae_r = mae / session_range if session_range > 0 else 0
    terminal_time_r = mae_bar / horizon if horizon > 0 else 0
    
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
    
    state_key = f"{time_bin}_{depth_bin}_{dc_bin}_{delta_bin}_{force_bin}_{er_bin}_{theta_bin}_{channel_bin}"
    
    return {
        'idx': idx,
        'state_key': state_key,
        'time_bin': time_bin,
        'depth_bin': depth_bin,
        'dc_bin': dc_bin,
        'delta_bin': delta_bin,
        'force_bin': force_bin,
        'er_bin': er_bin,
        'theta_bin': theta_bin,
        'channel_bin': channel_bin,
        'mae_r': mae_r,
        'terminal_time_r': terminal_time_r,
        'mae_bar': mae_bar,
        'e_resp_flip_bar': e_resp_flip_bar,
        'precedes': precedes,
        'session_range': session_range
    }

def run():
    print("="*70)
    print("EXP-ALL-LAWS-JOINT-01: Full Joint Distribution (ALL DATA)")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    df = load_chart_data()
    print(f"\nTotal bars: {len(df)}")
    
    sample_step = 10
    sample_indices = list(range(100, len(df) - 50, sample_step))
    print(f"Sample points: {len(sample_indices)} (every {sample_step} bars)")
    
    events = []
    for idx in sample_indices:
        result = analyze_event(df, idx)
        if result:
            events.append(result)
    
    print(f"Valid events: {len(events)}")
    
    print("\n" + "="*70)
    print("1. FAST vs SLOW DISTRIBUTION (Terminal_Time_R)")
    print("="*70)
    
    fast_events = [e for e in events if e['time_bin'] == 'Fast']
    slow_events = [e for e in events if e['time_bin'] == 'Slow']
    
    print(f"\nFast (Time_R < 0.3): N = {len(fast_events)} ({100*len(fast_events)/len(events):.1f}%)")
    print(f"Slow (Time_R >= 0.3): N = {len(slow_events)} ({100*len(slow_events)/len(events):.1f}%)")
    
    fast_precedes = sum(1 for e in fast_events if e['precedes'] and e['e_resp_flip_bar'] != -1)
    fast_valid = len([e for e in fast_events if e['e_resp_flip_bar'] != -1])
    fast_p = fast_precedes / fast_valid * 100 if fast_valid > 0 else 0
    
    slow_precedes = sum(1 for e in slow_events if e['precedes'] and e['e_resp_flip_bar'] != -1)
    slow_valid = len([e for e in slow_events if e['e_resp_flip_bar'] != -1])
    slow_p = slow_precedes / slow_valid * 100 if slow_valid > 0 else 0
    
    print(f"\nFast E_RESP Precedence: {fast_p:.1f}% (N={fast_valid})")
    print(f"Slow E_RESP Precedence: {slow_p:.1f}% (N={slow_valid})")
    
    print("\n" + "="*70)
    print("2. 8-AXIS STATE DISTRIBUTION (Top 20 by N)")
    print("="*70)
    
    state_stats = defaultdict(lambda: {
        'n': 0, 'precedes': 0, 'valid': 0, 'mae_r_sum': 0
    })
    
    for e in events:
        key = e['state_key']
        state_stats[key]['n'] += 1
        state_stats[key]['mae_r_sum'] += e['mae_r']
        if e['e_resp_flip_bar'] != -1:
            state_stats[key]['valid'] += 1
            if e['precedes']:
                state_stats[key]['precedes'] += 1
    
    sorted_states = sorted(state_stats.items(), key=lambda x: x[1]['n'], reverse=True)[:20]
    
    print(f"\n{'State Key':<55} {'N':>5} {'Lead%':>7} {'MAE_R':>7}")
    print("-" * 80)
    for key, stats in sorted_states:
        n = stats['n']
        lead_pct = stats['precedes'] / stats['valid'] * 100 if stats['valid'] > 0 else 0
        mae_r = stats['mae_r_sum'] / n if n > 0 else 0
        print(f"{key:<55} {n:>5} {lead_pct:>6.1f}% {mae_r:>7.3f}")
    
    print("\n" + "="*70)
    print("3. FAST 내부 조합별 선행성 (섬 존재 여부)")
    print("="*70)
    
    fast_states = defaultdict(lambda: {'n': 0, 'precedes': 0, 'valid': 0})
    
    for e in fast_events:
        key = f"{e['depth_bin']}_{e['dc_bin']}_{e['delta_bin']}_{e['force_bin']}_{e['er_bin']}_{e['theta_bin']}_{e['channel_bin']}"
        fast_states[key]['n'] += 1
        if e['e_resp_flip_bar'] != -1:
            fast_states[key]['valid'] += 1
            if e['precedes']:
                fast_states[key]['precedes'] += 1
    
    sorted_fast = sorted(fast_states.items(), key=lambda x: x[1]['n'], reverse=True)
    
    print(f"\n{'State (7-axis excl Time)':<50} {'N':>5} {'Valid':>6} {'Lead%':>7}")
    print("-" * 70)
    
    islands = []
    for key, stats in sorted_fast[:15]:
        n = stats['n']
        valid = stats['valid']
        lead_pct = stats['precedes'] / valid * 100 if valid > 0 else 0
        print(f"{key:<50} {n:>5} {valid:>6} {lead_pct:>6.1f}%")
        if lead_pct >= 70 and valid >= 10:
            islands.append((key, lead_pct, valid))
    
    if islands:
        print(f"\n✅ FAST 내 '판정 가능 섬' 발견: {len(islands)}개")
        for key, p, n in islands:
            print(f"   {key}: {p:.1f}% (N={n})")
    else:
        print(f"\n❌ FAST 내 '판정 가능 섬' 없음 (Lead≥70% & N≥10 조건)")
    
    print("\n" + "="*70)
    print("4. SLOW 내부 조합별 선행성 (90%+ 영역)")
    print("="*70)
    
    slow_states = defaultdict(lambda: {'n': 0, 'precedes': 0, 'valid': 0})
    
    for e in slow_events:
        key = f"{e['depth_bin']}_{e['dc_bin']}_{e['delta_bin']}_{e['force_bin']}_{e['er_bin']}_{e['theta_bin']}_{e['channel_bin']}"
        slow_states[key]['n'] += 1
        if e['e_resp_flip_bar'] != -1:
            slow_states[key]['valid'] += 1
            if e['precedes']:
                slow_states[key]['precedes'] += 1
    
    sorted_slow = sorted(slow_states.items(), key=lambda x: x[1]['n'], reverse=True)
    
    print(f"\n{'State (7-axis excl Time)':<50} {'N':>5} {'Valid':>6} {'Lead%':>7}")
    print("-" * 70)
    
    high_slow = []
    for key, stats in sorted_slow[:15]:
        n = stats['n']
        valid = stats['valid']
        lead_pct = stats['precedes'] / valid * 100 if valid > 0 else 0
        print(f"{key:<50} {n:>5} {valid:>6} {lead_pct:>6.1f}%")
        if lead_pct >= 90 and valid >= 10:
            high_slow.append((key, lead_pct, valid))
    
    if high_slow:
        print(f"\n✅ SLOW 내 '90%+ 고선행 영역' 발견: {len(high_slow)}개")
        for key, p, n in high_slow:
            print(f"   {key}: {p:.1f}% (N={n})")
    
    print("\n" + "="*70)
    print("5. 증명 결과 (Proof A vs Proof B)")
    print("="*70)
    
    proof_a = len(islands) > 0
    proof_b = not proof_a and len([s for s in fast_states.values() if s['valid'] >= 5]) > 0
    
    if proof_a:
        print("\n✅ 증명 A 성립: Fast 내부에도 판정 가능 섬이 존재")
        print("   → '조합 판정이 진짜 세계' 확정")
    elif proof_b:
        print("\n⚠️ 증명 B 성립: Fast는 전체적으로 선행 불가")
        print("   → Fast는 '리스크 정책 영역'으로 확정")
        print("   → 알파가 아니라 손실 완화만 가능")
    else:
        print("\n❌ 증명 실패: 표본 부족")
    
    print("\n" + "="*70)
    print("6. FINAL JOINT TABLE")
    print("="*70)
    
    all_fast_p = fast_precedes / fast_valid * 100 if fast_valid > 0 else 0
    all_slow_p = slow_precedes / slow_valid * 100 if slow_valid > 0 else 0
    
    print(f"""
┌───────────────────────────────────────────────────────┐
│  FULL DATA JOINT ANALYSIS                            │
├───────────────────────────────────────────────────────┤
│  Total Events: {len(events):,}                               │
│  Fast Terminal: {len(fast_events):,} ({100*len(fast_events)/len(events):.1f}%)                      │
│  Slow Terminal: {len(slow_events):,} ({100*len(slow_events)/len(events):.1f}%)                      │
├───────────────────────────────────────────────────────┤
│  Fast E_RESP Lead: {all_fast_p:.1f}%                          │
│  Slow E_RESP Lead: {all_slow_p:.1f}%                          │
├───────────────────────────────────────────────────────┤
│  Fast 내 판정 가능 섬: {'있음' if proof_a else '없음'}                       │
│  Slow 내 90%+ 영역: {len(high_slow)}개                            │
└───────────────────────────────────────────────────────┘
""")
    
    output = {
        'timestamp': datetime.now().isoformat(),
        'total_bars': len(df),
        'total_events': len(events),
        'fast_events': len(fast_events),
        'slow_events': len(slow_events),
        'fast_lead_pct': all_fast_p,
        'slow_lead_pct': all_slow_p,
        'proof_a': proof_a,
        'proof_b': proof_b,
        'fast_islands': len(islands),
        'slow_high_regions': len(high_slow)
    }
    
    with open('v7-grammar-system/results/exp_all_laws_joint_01.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"Results saved to: exp_all_laws_joint_01.json")

if __name__ == "__main__":
    run()
