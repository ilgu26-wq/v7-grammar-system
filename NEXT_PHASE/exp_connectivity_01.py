"""
EXP-CONNECTIVITY-01: 연결성 붕괴 지표 (Connectivity Collapse Index)
==================================================================
핵심 발견 (EXP-HTF-SYNC-01에서):
  "붕괴는 '무언가가 있어서' 발생하는 게 아니라
   '아무 것도 연결되지 않았을 때' 발생한다."

핵심 질문:
  Collapse 직전, 풍차 노드 간 연결 신호가 동시에 사라지는가?

노드 정의 (6개):
  1. HTF ignition alive - 상위 TF 구조 연결
  2. ZPOC recenter alive - 유동성 중심 복귀
  3. Depth recovery alive - 깊이 구조 유지
  4. ER dissipation alive - 에너지 정상 소산
  5. Range normal alive - 변동성 정상 범위
  6. τ normal alive - 체류시간 정상 범위

가설:
  - Suspended: 항상 ≥2~3 노드 alive
  - Collapsed: 짧은 시간에 다수 노드 동시 off
  → Collapse = "고립 사건"
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
import json
from datetime import datetime
import os

RESULT_FILE = "v7-grammar-system/results/exp_connectivity_01.json"

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

def compute_connectivity_nodes(df: pd.DataFrame, bar_idx: int, htf_5m_ignitions: List[Tuple[int, int]], 
                                htf_15m_ignitions: List[Tuple[int, int]], 
                                er_baseline: float, depth_baseline: float,
                                range_q25: float, range_q75: float,
                                tau_q25: float, tau_q75: float,
                                dwell_time: int) -> Dict:
    """각 노드의 alive 상태 계산"""
    
    htf_5m_alive = any(start - 5 <= bar_idx <= end + 5 for start, end in htf_5m_ignitions)
    htf_15m_alive = any(start - 15 <= bar_idx <= end + 15 for start, end in htf_15m_ignitions)
    htf_alive = htf_5m_alive or htf_15m_alive
    
    current_zpoc = df['zpoc'].iloc[bar_idx]
    ignition_price = df['close'].iloc[bar_idx - dwell_time] if bar_idx >= dwell_time else df['close'].iloc[bar_idx]
    zpoc_distance = abs(current_zpoc - ignition_price)
    price_range = df['range'].iloc[bar_idx] if df['range'].iloc[bar_idx] > 0 else 1
    zpoc_alive = zpoc_distance < price_range * 3
    
    current_depth = df['depth'].iloc[bar_idx]
    depth_alive = abs(current_depth - depth_baseline) < 0.2
    
    current_er = df['er'].iloc[bar_idx]
    er_alive = current_er > er_baseline * 0.6
    
    current_range = df['range'].iloc[bar_idx]
    range_alive = range_q25 <= current_range <= range_q75 * 1.5
    
    tau_alive = tau_q25 <= dwell_time <= tau_q75 * 1.5
    
    nodes = {
        'htf_alive': htf_alive,
        'zpoc_alive': zpoc_alive,
        'depth_alive': depth_alive,
        'er_alive': er_alive,
        'range_alive': range_alive,
        'tau_alive': tau_alive
    }
    
    alive_count = sum(nodes.values())
    
    return {
        'nodes': nodes,
        'alive_count': alive_count
    }

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-CONNECTIVITY-01")
    print("연결성 붕괴 지표 (Connectivity Collapse Index)")
    print("=" * 70)
    
    print("\n[1] Computing metrics...")
    df['range'] = df['high'] - df['low']
    df['er'] = calc_er(df['close'])
    df['depth'] = calc_depth(df)
    df['zpoc'] = calc_zpoc(df)
    
    range_q25 = df['range'].quantile(0.25)
    range_q75 = df['range'].quantile(0.75)
    
    print("\n[2] Computing HTF ignitions...")
    htf_5m = resample_to_htf(df, 5)
    htf_15m = resample_to_htf(df, 15)
    htf_5m['er'] = calc_er(htf_5m['close'])
    htf_15m['er'] = calc_er(htf_15m['close'])
    
    ignitions_5m_idx = find_ignition_events(htf_5m, er_threshold=0.7)
    ignitions_15m_idx = find_ignition_events(htf_15m, er_threshold=0.7)
    
    htf_5m_ignitions = [(int(htf_5m.iloc[i]['bar_start']), int(htf_5m.iloc[i]['bar_end'])) 
                        for i in ignitions_5m_idx if i < len(htf_5m)]
    htf_15m_ignitions = [(int(htf_15m.iloc[i]['bar_start']), int(htf_15m.iloc[i]['bar_end'])) 
                         for i in ignitions_15m_idx if i < len(htf_15m)]
    
    print("\n[3] Finding 1-min events and computing connectivity...")
    ignitions_1m = find_ignition_events(df, er_threshold=0.7)
    
    recoverable_events = []
    for idx in ignitions_1m:
        retouch, dwell = check_retouch(df, idx)
        if retouch:
            recoverable_events.append((idx, dwell))
    
    all_dwells = [d for _, d in recoverable_events]
    tau_q25 = np.percentile(all_dwells, 25) if all_dwells else 1
    tau_q75 = np.percentile(all_dwells, 75) if all_dwells else 10
    
    suspended = []
    collapsed = []
    
    for ignition_idx, dwell_time in recoverable_events:
        dwell_end = ignition_idx + dwell_time
        
        if dwell_end >= len(df):
            continue
        
        pre_ignition_idx = max(0, ignition_idx - 5)
        er_baseline = df['er'].iloc[pre_ignition_idx:ignition_idx].mean()
        depth_baseline = df['depth'].iloc[pre_ignition_idx:ignition_idx].mean()
        
        connectivity = compute_connectivity_nodes(
            df, dwell_end, htf_5m_ignitions, htf_15m_ignitions,
            er_baseline, depth_baseline, range_q25, range_q75, tau_q25, tau_q75, dwell_time
        )
        
        did_collapse, collapse_type = check_collapse(df, dwell_end)
        
        event = {
            'ignition_idx': ignition_idx,
            'dwell_end': dwell_end,
            'dwell_time': dwell_time,
            'collapsed': did_collapse,
            'alive_count': connectivity['alive_count'],
            **connectivity['nodes']
        }
        
        if did_collapse:
            collapsed.append(event)
        else:
            suspended.append(event)
    
    print(f"  Suspended: {len(suspended)}")
    print(f"  Collapsed: {len(collapsed)}")
    
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    results = {
        'experiment': 'EXP-CONNECTIVITY-01',
        'timestamp': datetime.now().isoformat(),
        'suspended_count': len(suspended),
        'collapsed_count': len(collapsed),
        'connectivity_analysis': {}
    }
    
    if len(suspended) > 0 and len(collapsed) > 0:
        susp_df = pd.DataFrame(suspended)
        coll_df = pd.DataFrame(collapsed)
        
        print("\n[A] Alive Count 분포")
        print("-" * 50)
        
        susp_alive_mean = susp_df['alive_count'].mean()
        coll_alive_mean = coll_df['alive_count'].mean()
        
        print(f"  Suspended 평균 alive nodes: {susp_alive_mean:.2f}")
        print(f"  Collapsed 평균 alive nodes: {coll_alive_mean:.2f}")
        print(f"  차이: {susp_alive_mean - coll_alive_mean:+.2f}")
        
        results['connectivity_analysis']['alive_count'] = {
            'suspended_mean': float(susp_alive_mean),
            'collapsed_mean': float(coll_alive_mean),
            'difference': float(susp_alive_mean - coll_alive_mean)
        }
        
        print("\n  Alive Count 분포:")
        for count in range(7):
            susp_pct = (susp_df['alive_count'] == count).mean()
            coll_pct = (coll_df['alive_count'] == count).mean()
            print(f"    {count} nodes: Suspended {susp_pct:.1%} | Collapsed {coll_pct:.1%}")
        
        print("\n[B] 개별 노드 분석")
        print("-" * 50)
        
        node_cols = ['htf_alive', 'zpoc_alive', 'depth_alive', 'er_alive', 'range_alive', 'tau_alive']
        node_analysis = {}
        
        for col in node_cols:
            susp_rate = susp_df[col].mean()
            coll_rate = coll_df[col].mean()
            diff = susp_rate - coll_rate
            print(f"  {col:15s}: Suspended {susp_rate:.1%} | Collapsed {coll_rate:.1%} | diff {diff:+.1%}")
            node_analysis[col] = {
                'suspended': float(susp_rate),
                'collapsed': float(coll_rate),
                'difference': float(diff)
            }
        
        results['connectivity_analysis']['nodes'] = node_analysis
        
        print("\n[C] 고립 상태 분석 (alive_count ≤ 2)")
        print("-" * 50)
        
        susp_isolated = (susp_df['alive_count'] <= 2).mean()
        coll_isolated = (coll_df['alive_count'] <= 2).mean()
        
        print(f"  Suspended 고립률: {susp_isolated:.1%}")
        print(f"  Collapsed 고립률: {coll_isolated:.1%}")
        print(f"  차이: {coll_isolated - susp_isolated:+.1%}")
        
        results['connectivity_analysis']['isolation'] = {
            'suspended_rate': float(susp_isolated),
            'collapsed_rate': float(coll_isolated),
            'difference': float(coll_isolated - susp_isolated)
        }
        
        print("\n" + "=" * 70)
        print("HYPOTHESIS CHECK")
        print("=" * 70)
        
        if susp_alive_mean - coll_alive_mean >= 0.5:
            print("\n  ✓ 가설 강하게 지지:")
            print(f"    Suspended가 평균 {susp_alive_mean - coll_alive_mean:.2f}개 더 많은 노드 연결")
            print("    → Collapse = 연결 단절 상태")
            results['verdict'] = "STRONGLY_SUPPORTED"
        elif susp_alive_mean - coll_alive_mean >= 0.2:
            print("\n  ~ 가설 약하게 지지:")
            print(f"    차이 {susp_alive_mean - coll_alive_mean:.2f}개")
            results['verdict'] = "WEAKLY_SUPPORTED"
        else:
            print("\n  ✗ 가설 기각:")
            print("    Alive count 차이 미미")
            results['verdict'] = "REJECTED"
        
        if coll_isolated - susp_isolated >= 0.1:
            print(f"\n  ✓ 고립 가설 지지:")
            print(f"    Collapsed가 {coll_isolated - susp_isolated:.1%} 더 고립 상태")
            results['isolation_verdict'] = "SUPPORTED"
        else:
            results['isolation_verdict'] = "NOT_SUPPORTED"
    
    print("\n" + "=" * 70)
    
    return results

def main():
    data_files = [
        "data/mnq_december_2025.csv",
        "data/mnq_with_ratio.csv"
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
