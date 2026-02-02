"""
EXP-ZPOC-IGNITION-BOUNDARY-01: Recoverable → Collapse 외부 촉발 메커니즘 검증
============================================================================
핵심 질문:
  "회복 가능한 상태가 붕괴할 때,
   그 직전에 반드시 관측되는 '외부 기준점의 이동'이 존재하는가?"

배경:
  EXP-SUSPENSION-COLLAPSE-01에서 내부 변수(ER decay, depth curvature, τ)로
  붕괴를 설명할 수 없음이 증명됨.
  → 붕괴는 내부 피로가 아니라 기준점(reference frame) 이동에 의한 것인가?

주 가설 (H1):
  Collapsed 이벤트는 ignition 이후 ZPOC가 재중심화되지 않고
  외부로 이동한 경우에 집중된다.

보조 가설 (H2):
  가격은 재도달했지만 ZPOC 또는 depth/ER이 회복되지 않은 경우,
  이후 붕괴 확률이 유의미하게 높다.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
import json
from datetime import datetime
import os

RESULT_FILE = "v7-grammar-system/results/exp_zpoc_ignition_boundary_01.json"

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
    """ZPOC: Volume-weighted price center (유동성 중심)"""
    if 'volume' in df.columns:
        vol = df['volume'].replace(0, 1)
    else:
        vol = df['range'].replace(0, 1)
    
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    
    zpoc = (typical_price * vol).rolling(lookback, min_periods=1).sum() / vol.rolling(lookback, min_periods=1).sum()
    return zpoc

def find_ignition_events(df: pd.DataFrame, er_threshold: float = 0.7) -> List[int]:
    events = []
    for i in range(1, len(df)):
        if df['er'].iloc[i] > er_threshold and df['er'].iloc[i-1] < er_threshold:
            events.append(i)
    return events

def check_retouch(df: pd.DataFrame, ignition_idx: int, lookforward: int = 20) -> Tuple[bool, int]:
    if ignition_idx + lookforward >= len(df):
        return False, 0
    
    entry_price = df['close'].iloc[ignition_idx]
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

def analyze_zpoc_dynamics(df: pd.DataFrame, ignition_idx: int, dwell_end: int) -> Dict:
    """ZPOC 동역학 분석"""
    if dwell_end <= ignition_idx or dwell_end >= len(df):
        return None
    
    ignition_price = df['close'].iloc[ignition_idx]
    ignition_zpoc = df['zpoc'].iloc[ignition_idx]
    
    window = df.iloc[ignition_idx:dwell_end + 1]
    
    zpoc_start = window['zpoc'].iloc[0]
    zpoc_end = window['zpoc'].iloc[-1]
    zpoc_shift = zpoc_end - zpoc_start
    
    zpoc_velocity = zpoc_shift / len(window) if len(window) > 0 else 0
    
    zpoc_distance_from_price = abs(zpoc_end - ignition_price)
    price_range = df['high'].iloc[ignition_idx] - df['low'].iloc[ignition_idx]
    threshold = price_range * 2 if price_range > 0 else 5
    
    zpoc_escape = zpoc_distance_from_price > threshold
    zpoc_recenter = zpoc_distance_from_price < threshold * 0.5
    
    return {
        'zpoc_shift': float(zpoc_shift),
        'zpoc_velocity': float(zpoc_velocity),
        'zpoc_escape_flag': zpoc_escape,
        'zpoc_recenter_flag': zpoc_recenter,
        'zpoc_distance': float(zpoc_distance_from_price)
    }

def analyze_recovery_vector(df: pd.DataFrame, ignition_idx: int, dwell_end: int) -> Dict:
    """회복 벡터 분석 (price, depth, ER)"""
    if dwell_end <= ignition_idx or dwell_end >= len(df):
        return None
    
    pre_ignition_idx = max(0, ignition_idx - 5)
    
    baseline_depth = df['depth'].iloc[pre_ignition_idx:ignition_idx].mean()
    baseline_er = df['er'].iloc[pre_ignition_idx:ignition_idx].mean()
    ignition_price = df['close'].iloc[ignition_idx]
    
    end_depth = df['depth'].iloc[dwell_end]
    end_er = df['er'].iloc[dwell_end]
    end_price = df['close'].iloc[dwell_end]
    
    price_retouch = abs(end_price - ignition_price) < abs(ignition_price * 0.002)
    
    depth_retouch = abs(end_depth - baseline_depth) < 0.15
    
    er_retouch = end_er > baseline_er * 0.7
    
    recovery_score = sum([price_retouch, depth_retouch, er_retouch])
    
    if recovery_score == 3:
        recovery_type = "full"
    elif recovery_score == 2:
        recovery_type = "partial"
    elif recovery_score == 1:
        recovery_type = "weak"
    else:
        recovery_type = "failed"
    
    return {
        'price_retouch': price_retouch,
        'depth_retouch': depth_retouch,
        'er_retouch': er_retouch,
        'recovery_score': recovery_score,
        'recovery_type': recovery_type
    }

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-ZPOC-IGNITION-BOUNDARY-01")
    print("Recoverable → Collapse 외부 촉발 메커니즘 검증")
    print("=" * 70)
    
    print("\n[1] Computing metrics...")
    df['range'] = df['high'] - df['low']
    df['er'] = calc_er(df['close'])
    df['depth'] = calc_depth(df)
    df['zpoc'] = calc_zpoc(df)
    
    print("\n[2] Finding Ignition events...")
    ignitions = find_ignition_events(df, er_threshold=0.7)
    print(f"  Found {len(ignitions)} ignition events")
    
    print("\n[3] Filtering Retouch = TRUE...")
    recoverable_events = []
    for idx in ignitions:
        retouch, dwell = check_retouch(df, idx)
        if retouch:
            recoverable_events.append((idx, dwell))
    print(f"  Recoverable events: {len(recoverable_events)}")
    
    print("\n[4] Analyzing ZPOC dynamics & recovery vectors...")
    
    suspended = []
    collapsed = []
    
    for ignition_idx, dwell_time in recoverable_events:
        dwell_end = ignition_idx + dwell_time
        
        zpoc_analysis = analyze_zpoc_dynamics(df, ignition_idx, dwell_end)
        recovery_analysis = analyze_recovery_vector(df, ignition_idx, dwell_end)
        
        if zpoc_analysis is None or recovery_analysis is None:
            continue
        
        did_collapse, collapse_type = check_collapse(df, dwell_end)
        
        event = {
            'ignition_idx': ignition_idx,
            'dwell_time': dwell_time,
            'collapsed': did_collapse,
            'collapse_type': collapse_type,
            **zpoc_analysis,
            **recovery_analysis
        }
        
        if did_collapse:
            collapsed.append(event)
        else:
            suspended.append(event)
    
    print(f"  Suspended (stable): {len(suspended)}")
    print(f"  Collapsed: {len(collapsed)}")
    
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    results = {
        'experiment': 'EXP-ZPOC-IGNITION-BOUNDARY-01',
        'timestamp': datetime.now().isoformat(),
        'total_bars': len(df),
        'ignition_count': len(ignitions),
        'recoverable_count': len(recoverable_events),
        'suspended_count': len(suspended),
        'collapsed_count': len(collapsed),
        'h1_zpoc_escape': {},
        'h2_recovery_vector': {}
    }
    
    print("\n[H1] ZPOC Escape Flag 분석")
    print("-" * 50)
    
    if len(suspended) > 0 and len(collapsed) > 0:
        suspended_df = pd.DataFrame(suspended)
        collapsed_df = pd.DataFrame(collapsed)
        
        susp_escape_rate = suspended_df['zpoc_escape_flag'].mean()
        coll_escape_rate = collapsed_df['zpoc_escape_flag'].mean()
        
        print(f"  Suspended ZPOC escape rate: {susp_escape_rate:.1%}")
        print(f"  Collapsed ZPOC escape rate: {coll_escape_rate:.1%}")
        print(f"  Difference: {coll_escape_rate - susp_escape_rate:+.1%}")
        
        results['h1_zpoc_escape'] = {
            'suspended_escape_rate': float(susp_escape_rate),
            'collapsed_escape_rate': float(coll_escape_rate),
            'difference': float(coll_escape_rate - susp_escape_rate)
        }
        
        if coll_escape_rate > susp_escape_rate + 0.1:
            print("\n  ✓ H1 지지: 붕괴 시 ZPOC escape 비율이 유의미하게 높음")
            results['h1_verdict'] = "SUPPORTED"
        elif coll_escape_rate > susp_escape_rate + 0.05:
            print("\n  ~ H1 약한 지지: 차이 존재하나 통계적 유의성 검토 필요")
            results['h1_verdict'] = "WEAK_SUPPORT"
        else:
            print("\n  ✗ H1 기각: ZPOC escape와 붕괴 간 관계 없음")
            results['h1_verdict'] = "REJECTED"
        
        susp_zpoc_vel = suspended_df['zpoc_velocity'].mean()
        coll_zpoc_vel = collapsed_df['zpoc_velocity'].mean()
        print(f"\n  Suspended ZPOC velocity: {susp_zpoc_vel:.4f}")
        print(f"  Collapsed ZPOC velocity: {coll_zpoc_vel:.4f}")
        
        results['h1_zpoc_escape']['suspended_velocity'] = float(susp_zpoc_vel)
        results['h1_zpoc_escape']['collapsed_velocity'] = float(coll_zpoc_vel)
    
    print("\n[H2] Recovery Vector 분석")
    print("-" * 50)
    
    if len(suspended) > 0 and len(collapsed) > 0:
        susp_recovery = suspended_df['recovery_type'].value_counts(normalize=True).to_dict()
        coll_recovery = collapsed_df['recovery_type'].value_counts(normalize=True).to_dict()
        
        print("\n  Suspended recovery types:")
        for k, v in sorted(susp_recovery.items()):
            print(f"    {k}: {v:.1%}")
        
        print("\n  Collapsed recovery types:")
        for k, v in sorted(coll_recovery.items()):
            print(f"    {k}: {v:.1%}")
        
        results['h2_recovery_vector'] = {
            'suspended': susp_recovery,
            'collapsed': coll_recovery
        }
        
        susp_full = susp_recovery.get('full', 0)
        coll_full = coll_recovery.get('full', 0)
        
        print(f"\n  Full recovery: Suspended {susp_full:.1%} vs Collapsed {coll_full:.1%}")
        
        if susp_full > coll_full + 0.1:
            print("\n  ✓ H2 지지: 완전 회복 시 붕괴 확률 낮음")
            results['h2_verdict'] = "SUPPORTED"
        elif susp_full > coll_full + 0.05:
            print("\n  ~ H2 약한 지지: 차이 존재")
            results['h2_verdict'] = "WEAK_SUPPORT"
        else:
            print("\n  ✗ H2 기각: 회복 벡터와 붕괴 간 관계 불명확")
            results['h2_verdict'] = "REJECTED"
        
        print("\n[개별 회복 요소 분석]")
        for col in ['price_retouch', 'depth_retouch', 'er_retouch']:
            susp_rate = suspended_df[col].mean()
            coll_rate = collapsed_df[col].mean()
            diff = susp_rate - coll_rate
            print(f"  {col}: Suspended {susp_rate:.1%} vs Collapsed {coll_rate:.1%} (diff: {diff:+.1%})")
    
    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)
    
    if results.get('h1_verdict') == "SUPPORTED":
        print("\n  붕괴는 ZPOC(유동성 중심)의 이탈과 연관됨")
        print("  → 좌표계 이동 가설 지지")
    elif results.get('h2_verdict') == "SUPPORTED":
        print("\n  붕괴는 불완전 회복과 연관됨")
        print("  → 가격 회복 ≠ 구조 회복")
    else:
        print("\n  ZPOC 및 회복 벡터로도 붕괴 설명 불충분")
        print("  → 상위 타임프레임 또는 외부 레짐 변수 필요")
    
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
