"""
EXP-HTF-SYNC-01: 상위 타임프레임 동기화 검증
============================================
핵심 질문:
  "1분봉 collapse는 상위 TF(5분/15분) ignition과 시간적으로 더 겹치는가?"

배경:
  EXP-01, EXP-02에서 1분봉 내부 메커니즘으로 붕괴 설명 불가.
  → Collapse가 상위 프레임에서 '결정'된 뒤 1분봉이 표현하는 것인지 검증.

가설:
  Collapsed 이벤트는 Suspended보다 상위 TF ignition과 더 자주 동기화된다.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
import json
from datetime import datetime
import os

RESULT_FILE = "v7-grammar-system/results/exp_htf_sync_01.json"

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

def resample_to_htf(df: pd.DataFrame, period: int) -> pd.DataFrame:
    """1분봉을 N분봉으로 리샘플링"""
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

def check_retouch(df: pd.DataFrame, ignition_idx: int, lookforward: int = 20) -> Tuple[bool, int]:
    if ignition_idx + lookforward >= len(df):
        return False, 0
    
    entry_er = df['er'].iloc[ignition_idx]
    
    for i in range(1, lookforward + 1):
        future_idx = ignition_idx + i
        future_er = df['er'].iloc[future_idx]
        
        if future_er > entry_er * 0.8:
            return True, i
    
    return False, 0

def check_collapse(df: pd.DataFrame, dwell_end: int, lookforward: int = 10) -> Tuple[bool, str]:
    if dwell_end + lookforward >= len(df):
        return False, "insufficient_data"
    
    future_window = df.iloc[dwell_end:dwell_end + lookforward + 1]
    
    min_er = future_window['er'].min()
    if min_er < 0.25:
        return True, "er_collapse"
    
    er_drop = future_window['er'].iloc[0] - future_window['er'].iloc[-1]
    if er_drop > 0.3:
        return True, "er_degradation"
    
    return False, "stable"

def check_htf_ignition_sync(htf_ignitions: List[Tuple[int, int]], bar_idx: int, window: int = 0) -> bool:
    """1분봉 bar_idx가 HTF ignition 윈도우 내에 있는지 확인"""
    for htf_start, htf_end in htf_ignitions:
        if htf_start - window <= bar_idx <= htf_end + window:
            return True
    return False

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-HTF-SYNC-01")
    print("상위 타임프레임 동기화 검증")
    print("=" * 70)
    
    print("\n[1] Computing 1-min ER...")
    df['er'] = calc_er(df['close'])
    
    print("\n[2] Resampling to 5-min and 15-min...")
    htf_5m = resample_to_htf(df, 5)
    htf_15m = resample_to_htf(df, 15)
    
    htf_5m['er'] = calc_er(htf_5m['close'])
    htf_15m['er'] = calc_er(htf_15m['close'])
    
    print(f"  5-min bars: {len(htf_5m)}")
    print(f"  15-min bars: {len(htf_15m)}")
    
    print("\n[3] Finding HTF ignition events...")
    
    ignitions_5m_idx = find_ignition_events(htf_5m, er_threshold=0.7)
    ignitions_15m_idx = find_ignition_events(htf_15m, er_threshold=0.7)
    
    ignitions_5m = [(int(htf_5m.iloc[i]['bar_start']), int(htf_5m.iloc[i]['bar_end'])) 
                    for i in ignitions_5m_idx if i < len(htf_5m)]
    ignitions_15m = [(int(htf_15m.iloc[i]['bar_start']), int(htf_15m.iloc[i]['bar_end'])) 
                     for i in ignitions_15m_idx if i < len(htf_15m)]
    
    print(f"  5-min ignitions: {len(ignitions_5m)}")
    print(f"  15-min ignitions: {len(ignitions_15m)}")
    
    print("\n[4] Finding 1-min ignition events and classifying...")
    ignitions_1m = find_ignition_events(df, er_threshold=0.7)
    
    recoverable_events = []
    for idx in ignitions_1m:
        retouch, dwell = check_retouch(df, idx)
        if retouch:
            recoverable_events.append((idx, dwell))
    
    suspended = []
    collapsed = []
    
    for ignition_idx, dwell_time in recoverable_events:
        dwell_end = ignition_idx + dwell_time
        did_collapse, collapse_type = check_collapse(df, dwell_end)
        
        event = {
            'ignition_idx': ignition_idx,
            'dwell_end': dwell_end,
            'collapsed': did_collapse
        }
        
        if did_collapse:
            collapsed.append(event)
        else:
            suspended.append(event)
    
    print(f"  1-min ignitions: {len(ignitions_1m)}")
    print(f"  Recoverable: {len(recoverable_events)}")
    print(f"  Suspended: {len(suspended)}")
    print(f"  Collapsed: {len(collapsed)}")
    
    print("\n[5] Checking HTF sync at different windows...")
    
    results = {
        'experiment': 'EXP-HTF-SYNC-01',
        'timestamp': datetime.now().isoformat(),
        'total_bars': len(df),
        'htf_5m_ignitions': len(ignitions_5m),
        'htf_15m_ignitions': len(ignitions_15m),
        'suspended_count': len(suspended),
        'collapsed_count': len(collapsed),
        'sync_analysis': {}
    }
    
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    for window in [0, 5, 15]:
        print(f"\n[Window = ±{window} bars]")
        print("-" * 50)
        
        susp_5m_sync = sum(1 for e in suspended if check_htf_ignition_sync(ignitions_5m, e['ignition_idx'], window))
        coll_5m_sync = sum(1 for e in collapsed if check_htf_ignition_sync(ignitions_5m, e['ignition_idx'], window))
        
        susp_15m_sync = sum(1 for e in suspended if check_htf_ignition_sync(ignitions_15m, e['ignition_idx'], window))
        coll_15m_sync = sum(1 for e in collapsed if check_htf_ignition_sync(ignitions_15m, e['ignition_idx'], window))
        
        susp_5m_rate = susp_5m_sync / len(suspended) if len(suspended) > 0 else 0
        coll_5m_rate = coll_5m_sync / len(collapsed) if len(collapsed) > 0 else 0
        
        susp_15m_rate = susp_15m_sync / len(suspended) if len(suspended) > 0 else 0
        coll_15m_rate = coll_15m_sync / len(collapsed) if len(collapsed) > 0 else 0
        
        print(f"  5-min sync:")
        print(f"    Suspended: {susp_5m_rate:.1%} ({susp_5m_sync}/{len(suspended)})")
        print(f"    Collapsed: {coll_5m_rate:.1%} ({coll_5m_sync}/{len(collapsed)})")
        print(f"    Difference: {coll_5m_rate - susp_5m_rate:+.1%}")
        
        print(f"\n  15-min sync:")
        print(f"    Suspended: {susp_15m_rate:.1%} ({susp_15m_sync}/{len(suspended)})")
        print(f"    Collapsed: {coll_15m_rate:.1%} ({coll_15m_sync}/{len(collapsed)})")
        print(f"    Difference: {coll_15m_rate - susp_15m_rate:+.1%}")
        
        results['sync_analysis'][f'window_{window}'] = {
            '5m': {
                'suspended_rate': float(susp_5m_rate),
                'collapsed_rate': float(coll_5m_rate),
                'difference': float(coll_5m_rate - susp_5m_rate)
            },
            '15m': {
                'suspended_rate': float(susp_15m_rate),
                'collapsed_rate': float(coll_15m_rate),
                'difference': float(coll_15m_rate - susp_15m_rate)
            }
        }
    
    print("\n" + "=" * 70)
    print("HYPOTHESIS CHECK")
    print("=" * 70)
    
    best_diff = 0
    best_tf = None
    best_window = None
    
    for window_key, data in results['sync_analysis'].items():
        for tf, values in data.items():
            if values['difference'] > best_diff:
                best_diff = values['difference']
                best_tf = tf
                best_window = window_key
    
    if best_diff > 0.10:
        print(f"\n  ✓ 가설 지지: {best_tf} @ {best_window}")
        print(f"    Collapsed가 HTF ignition과 {best_diff:.1%} 더 동기화됨")
        print("    → 붕괴는 상위 TF에서 촉발되어 1분봉에서 표현됨")
        results['verdict'] = "SUPPORTED"
        results['best_sync'] = {'tf': best_tf, 'window': best_window, 'diff': float(best_diff)}
    elif best_diff > 0.05:
        print(f"\n  ~ 약한 지지: {best_tf} @ {best_window}")
        print(f"    차이 {best_diff:.1%}는 유의미할 수 있음")
        results['verdict'] = "WEAK_SUPPORT"
        results['best_sync'] = {'tf': best_tf, 'window': best_window, 'diff': float(best_diff)}
    else:
        print("\n  ✗ 가설 기각: HTF 동기화 차이 없음")
        print("    → 붕괴는 상위 TF ignition과 무관")
        results['verdict'] = "REJECTED"
    
    print("\n" + "=" * 70)
    
    return results

def main():
    data_files = [
        "data/mnq_december_2025.csv",
        "data/mnq_with_ratio.csv",
        "attached_assets/nq_10min_64days.csv"
    ]
    
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
