"""
EXP-E_RESP-SPEED-01: E_RESP 전이 속도 측정

목표: "전이가 빠른가?"를 숫자로 고정

정의:
- t1 = E_RESP flip 시점
- t2 = Absorb 확정 시점  
- gap = t2 - t1 (bars)

산출물:
- gap 분포 히스토그램
- median gap, 90% gap
- 레짐별 gap 분포

판정:
- median gap ≤ 3 bars: 전이 초고속
- median gap 5~15 bars: 전이 중속 (운용 가능)
- gap 넓게 퍼짐: 정의 재검토 필요
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

def detect_absorb(df: pd.DataFrame, idx: int, horizon: int = 30) -> Tuple[bool, int]:
    """Absorb 발생 여부 및 시점 감지"""
    if idx + horizon >= len(df):
        return False, -1
    
    entry = df.iloc[idx]['close']
    atr = np.mean(df.iloc[idx-10:idx+1]['high'] - df.iloc[idx-10:idx+1]['low'])
    
    threshold = atr * 2.5
    
    for i in range(1, horizon + 1):
        if idx + i >= len(df):
            break
        
        future_close = df.iloc[idx + i]['close']
        mae = abs(future_close - entry)
        
        if mae > threshold:
            return True, i
    
    return False, -1

def find_e_resp_flip(df: pd.DataFrame, idx: int, lookback: int = 20) -> Tuple[int, str]:
    """E_RESP flip 시점 찾기 (idx 이전에서 HOLD→RELEASE 전환점)"""
    prev_state = None
    flip_idx = -1
    
    for i in range(max(0, idx - lookback), idx + 1):
        state = calc_e_resp(df, i)
        if prev_state == "HOLD" and state == "RELEASE":
            flip_idx = i
        prev_state = state
    
    return flip_idx, calc_e_resp(df, idx)

def measure_transition_gap(df: pd.DataFrame, events: List[Dict]) -> Dict:
    """전이 속도 측정"""
    gaps = []
    regime_gaps = defaultdict(list)
    details = []
    
    for e in events:
        idx = e['idx']
        regime = detect_regime(df, idx)
        
        absorb_occurred, absorb_bar = detect_absorb(df, idx)
        
        if not absorb_occurred:
            continue
        
        current_state = calc_e_resp(df, idx)
        
        flip_found = False
        flip_gap = None
        
        for look_ahead in range(1, absorb_bar + 1):
            check_idx = idx + look_ahead
            if check_idx >= len(df):
                break
            
            state = calc_e_resp(df, check_idx)
            if state == "RELEASE":
                flip_gap = absorb_bar - look_ahead
                flip_found = True
                break
        
        if not flip_found:
            for look_back in range(0, 15):
                check_idx = idx - look_back
                if check_idx < 10:
                    break
                
                state = calc_e_resp(df, check_idx)
                if state == "RELEASE":
                    flip_gap = absorb_bar + look_back
                    flip_found = True
                    break
        
        if flip_found and flip_gap is not None:
            gaps.append(flip_gap)
            regime_gaps[regime].append(flip_gap)
            details.append({
                'idx': idx,
                'regime': regime,
                'absorb_bar': absorb_bar,
                'flip_gap': flip_gap
            })
    
    return {
        'gaps': gaps,
        'regime_gaps': dict(regime_gaps),
        'details': details
    }

def analyze_gap_distribution(gaps: List[int]) -> Dict:
    """Gap 분포 분석"""
    if not gaps:
        return {'error': 'No gaps to analyze'}
    
    arr = np.array(gaps)
    
    return {
        'n': len(gaps),
        'min': int(np.min(arr)),
        'max': int(np.max(arr)),
        'mean': float(np.mean(arr)),
        'median': float(np.median(arr)),
        'std': float(np.std(arr)),
        'p10': float(np.percentile(arr, 10)),
        'p25': float(np.percentile(arr, 25)),
        'p75': float(np.percentile(arr, 75)),
        'p90': float(np.percentile(arr, 90)),
        'p95': float(np.percentile(arr, 95))
    }

def create_histogram(gaps: List[int], bins: int = 10) -> Dict:
    """히스토그램 생성"""
    if not gaps:
        return {}
    
    arr = np.array(gaps)
    hist, edges = np.histogram(arr, bins=bins)
    
    return {
        'counts': hist.tolist(),
        'edges': edges.tolist(),
        'bin_labels': [f"{int(edges[i])}-{int(edges[i+1])}" for i in range(len(edges)-1)]
    }

def run():
    print("="*70)
    print("EXP-E_RESP-SPEED-01: E_RESP 전이 속도 측정")
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
        
        if idx < 50 or idx + 35 >= len(chart_df):
            continue
        
        events.append({'ts': ts, 'idx': idx})
    
    events = events[:500]
    print(f"\nEvents: N = {len(events)}")
    
    print("\n" + "="*70)
    print("TRANSITION GAP MEASUREMENT")
    print("="*70)
    
    result = measure_transition_gap(chart_df, events)
    gaps = result['gaps']
    regime_gaps = result['regime_gaps']
    
    print(f"\nAbsorb Events with E_RESP Flip: N = {len(gaps)}")
    
    if gaps:
        stats = analyze_gap_distribution(gaps)
        
        print("\n" + "-"*50)
        print("GAP DISTRIBUTION (E_RESP Flip → Absorb)")
        print("-"*50)
        print(f"N: {stats['n']}")
        print(f"Min: {stats['min']} bars")
        print(f"Max: {stats['max']} bars")
        print(f"Mean: {stats['mean']:.1f} bars")
        print(f"Median: {stats['median']:.1f} bars")
        print(f"Std: {stats['std']:.1f} bars")
        print(f"P10: {stats['p10']:.1f} bars")
        print(f"P25: {stats['p25']:.1f} bars")
        print(f"P75: {stats['p75']:.1f} bars")
        print(f"P90: {stats['p90']:.1f} bars")
        print(f"P95: {stats['p95']:.1f} bars")
        
        hist = create_histogram(gaps, bins=8)
        print("\n" + "-"*50)
        print("HISTOGRAM")
        print("-"*50)
        for label, count in zip(hist['bin_labels'], hist['counts']):
            bar = "█" * min(count, 40)
            print(f"{label:>10}: {bar} ({count})")
        
        print("\n" + "-"*50)
        print("VERDICT")
        print("-"*50)
        
        median = stats['median']
        if median <= 3:
            verdict = "ULTRA-FAST"
            desc = "전이 초고속: EXIT 시점 매우 타이트"
        elif median <= 7:
            verdict = "FAST"
            desc = "전이 고속: EXIT 여유 있음"
        elif median <= 15:
            verdict = "MODERATE"
            desc = "전이 중속: 운용 가능"
        else:
            verdict = "SLOW"
            desc = "전이 저속: 정의 재검토 필요"
        
        print(f"Median Gap: {median:.1f} bars")
        print(f"Verdict: {verdict}")
        print(f"Description: {desc}")
        
        print("\n" + "-"*50)
        print("BY REGIME")
        print("-"*50)
        
        for regime, rgaps in sorted(regime_gaps.items()):
            if len(rgaps) >= 5:
                rstats = analyze_gap_distribution(rgaps)
                print(f"\n{regime} (N={len(rgaps)}):")
                print(f"  Median: {rstats['median']:.1f} bars")
                print(f"  P90: {rstats['p90']:.1f} bars")
    
    output = {
        'timestamp': datetime.now().isoformat(),
        'n_events': len(events),
        'n_with_absorb': len(gaps),
        'gap_stats': stats if gaps else None,
        'regime_stats': {r: analyze_gap_distribution(g) for r, g in regime_gaps.items() if len(g) >= 5}
    }
    
    with open('v7-grammar-system/results/exp_e_resp_speed_01.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nResults saved to: exp_e_resp_speed_01.json")

if __name__ == "__main__":
    run()
