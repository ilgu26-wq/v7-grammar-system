"""
EXP-SUSPENSION-COLLAPSE-01: 방향성 불확정 상태의 지속성과 붕괴 촉발 조건
=====================================================================
핵심 질문:
  "회복 가능한 세계가 스스로 유지되는 메커니즘은 무엇이고,
   그 메커니즘이 언제 실패하는가?"

관측 변수:
  1. ER 분해 속도 (ER_decay_rate) - 유지력
  2. Depth 곡률 (Depth_curvature) - 구조 피로도
  3. 체류 시간 τ (dwell_time) - 붕괴 촉발 인자

표본 정의:
  - Ignition 발생 (ER 급등)
  - Retouch = TRUE (회복 가능한 세계만)

판정 기준:
  - 붕괴는 "큰 충격" 때문이 아니라 "내부 조정 실패 + 시간 누적"
  - 오래 가는 상태는 "변동성 낮음"이 아니라 "회복 메커니즘 작동 중"
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
import json
from datetime import datetime

RESULT_FILE = "v7-grammar-system/results/exp_suspension_collapse_01.json"

def calc_er(close_series: pd.Series, lookback: int = 10) -> pd.Series:
    """Efficiency Ratio: 방향성 대비 총 이동량"""
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
    """Depth: 현재가가 최근 범위 내 어디에 위치하는지"""
    rolling_high = df['high'].rolling(lookback, min_periods=1).max()
    rolling_low = df['low'].rolling(lookback, min_periods=1).min()
    depth = (df['close'] - rolling_low) / (rolling_high - rolling_low + 0.001)
    return depth

def calc_depth_curvature(depth: pd.Series, window: int = 5) -> pd.Series:
    """Depth의 2차 미분 (곡률)"""
    d1 = depth.diff()
    d2 = d1.diff()
    curvature = d2.rolling(window, min_periods=1).mean()
    return curvature

def find_ignition_events(df: pd.DataFrame, er_threshold: float = 0.7) -> List[int]:
    """Ignition 이벤트 탐지: ER 급등"""
    events = []
    for i in range(1, len(df)):
        if df['er'].iloc[i] > er_threshold and df['er'].iloc[i-1] < er_threshold:
            events.append(i)
    return events

def check_retouch(df: pd.DataFrame, ignition_idx: int, lookforward: int = 20) -> Tuple[bool, int]:
    """회복 가능한 상태인지 확인 (Retouch)"""
    if ignition_idx + lookforward >= len(df):
        return False, 0
    
    entry_price = df['close'].iloc[ignition_idx]
    entry_er = df['er'].iloc[ignition_idx]
    
    for i in range(1, lookforward + 1):
        future_idx = ignition_idx + i
        future_er = df['er'].iloc[future_idx]
        future_price = df['close'].iloc[future_idx]
        
        if future_er > entry_er * 0.8:
            return True, i
    
    return False, 0

def analyze_suspension(df: pd.DataFrame, ignition_idx: int, dwell_end: int) -> Dict:
    """지속 상태 분석"""
    if dwell_end <= ignition_idx:
        return None
    
    window = df.iloc[ignition_idx:dwell_end + 1]
    
    er_values = window['er'].values
    if len(er_values) < 2:
        return None
    
    er_decay_rate = (er_values[0] - er_values[-1]) / len(er_values) if len(er_values) > 1 else 0
    
    er_diffs = np.diff(er_values)
    if len(er_diffs) < 2:
        decay_shape = "unknown"
    else:
        variance = np.var(er_diffs)
        if variance < 0.001:
            decay_shape = "linear"
        elif np.all(er_diffs <= 0):
            decay_shape = "exponential"
        else:
            decay_shape = "stepped"
    
    depth_curv = window['depth_curvature'].mean()
    
    dwell_time = dwell_end - ignition_idx
    
    return {
        'er_decay_rate': float(er_decay_rate),
        'decay_shape': decay_shape,
        'depth_curvature': float(depth_curv),
        'dwell_time': int(dwell_time),
        'er_residual': float(er_values[-1])
    }

def check_collapse(df: pd.DataFrame, dwell_end: int, lookforward: int = 10) -> Tuple[bool, str]:
    """붕괴 여부 확인"""
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

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-SUSPENSION-COLLAPSE-01")
    print("방향성 불확정 상태의 지속성과 붕괴 촉발 조건")
    print("=" * 70)
    
    print("\n[1] Computing metrics...")
    df['er'] = calc_er(df['close'])
    df['depth'] = calc_depth(df)
    df['depth_curvature'] = calc_depth_curvature(df['depth'])
    
    print("\n[2] Finding Ignition events (ER > 0.7)...")
    ignitions = find_ignition_events(df, er_threshold=0.7)
    print(f"  Found {len(ignitions)} ignition events")
    
    print("\n[3] Filtering Retouch = TRUE (recoverable world)...")
    recoverable_events = []
    for idx in ignitions:
        retouch, dwell = check_retouch(df, idx)
        if retouch:
            recoverable_events.append((idx, dwell))
    print(f"  Recoverable events: {len(recoverable_events)}")
    
    print("\n[4] Analyzing suspension characteristics...")
    
    suspended = []
    collapsed = []
    
    for ignition_idx, dwell_time in recoverable_events:
        dwell_end = ignition_idx + dwell_time
        
        analysis = analyze_suspension(df, ignition_idx, dwell_end)
        if analysis is None:
            continue
        
        did_collapse, collapse_type = check_collapse(df, dwell_end)
        analysis['collapsed'] = did_collapse
        analysis['collapse_type'] = collapse_type
        analysis['ignition_idx'] = ignition_idx
        
        if did_collapse:
            collapsed.append(analysis)
        else:
            suspended.append(analysis)
    
    print(f"  Suspended (stable): {len(suspended)}")
    print(f"  Collapsed: {len(collapsed)}")
    
    print("\n[5] Computing pattern differences...")
    
    results = {
        'experiment': 'EXP-SUSPENSION-COLLAPSE-01',
        'timestamp': datetime.now().isoformat(),
        'total_bars': len(df),
        'ignition_count': len(ignitions),
        'recoverable_count': len(recoverable_events),
        'suspended_count': len(suspended),
        'collapsed_count': len(collapsed),
        'patterns': {}
    }
    
    if len(suspended) > 0:
        suspended_df = pd.DataFrame(suspended)
        pattern = {
            'avg_er_decay_rate': float(suspended_df['er_decay_rate'].mean()),
            'avg_depth_curvature': float(suspended_df['depth_curvature'].mean()),
            'avg_dwell_time': float(suspended_df['dwell_time'].mean()),
            'avg_er_residual': float(suspended_df['er_residual'].mean()),
        }
        if 'decay_shape' in suspended_df.columns:
            pattern['decay_shapes'] = suspended_df['decay_shape'].value_counts().to_dict()
        results['patterns']['suspended'] = pattern
    
    if len(collapsed) > 0:
        collapsed_df = pd.DataFrame(collapsed)
        pattern = {
            'avg_er_decay_rate': float(collapsed_df['er_decay_rate'].mean()),
            'avg_depth_curvature': float(collapsed_df['depth_curvature'].mean()),
            'avg_dwell_time': float(collapsed_df['dwell_time'].mean()),
            'avg_er_residual': float(collapsed_df['er_residual'].mean()),
        }
        if 'decay_shape' in collapsed_df.columns:
            pattern['decay_shapes'] = collapsed_df['decay_shape'].value_counts().to_dict()
        results['patterns']['collapsed'] = pattern
    
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    if 'suspended' in results['patterns'] and 'collapsed' in results['patterns']:
        s = results['patterns']['suspended']
        c = results['patterns']['collapsed']
        
        print("\n[A] 오래 지속된 상태 (Suspended):")
        print(f"    ER 분해 속도: {s['avg_er_decay_rate']:.4f}")
        print(f"    Depth 곡률: {s['avg_depth_curvature']:.4f}")
        print(f"    평균 체류시간: {s['avg_dwell_time']:.1f} bars")
        print(f"    ER 잔여: {s['avg_er_residual']:.3f}")
        print(f"    분해 형태: {s['decay_shapes']}")
        
        print("\n[B] 붕괴된 상태 (Collapsed):")
        print(f"    ER 분해 속도: {c['avg_er_decay_rate']:.4f}")
        print(f"    Depth 곡률: {c['avg_depth_curvature']:.4f}")
        print(f"    평균 체류시간: {c['avg_dwell_time']:.1f} bars")
        print(f"    ER 잔여: {c['avg_er_residual']:.3f}")
        print(f"    분해 형태: {c['decay_shapes']}")
        
        print("\n[C] 패턴 차이 분석:")
        decay_diff = s['avg_er_decay_rate'] - c['avg_er_decay_rate']
        curv_diff = abs(s['avg_depth_curvature']) - abs(c['avg_depth_curvature'])
        dwell_diff = c['avg_dwell_time'] - s['avg_dwell_time']
        
        print(f"    ER 분해 속도 차이: {decay_diff:+.4f} (suspended - collapsed)")
        print(f"    Depth 곡률 차이: {curv_diff:+.4f}")
        print(f"    체류시간 차이: {dwell_diff:+.1f} bars (collapsed - suspended)")
        
        results['conclusion'] = {
            'er_decay_difference': float(decay_diff),
            'depth_curvature_difference': float(curv_diff),
            'dwell_time_difference': float(dwell_diff)
        }
        
        print("\n" + "-" * 70)
        print("HYPOTHESIS CHECK:")
        
        if dwell_diff > 2:
            print("  ✓ 체류시간이 길수록 붕괴 확률 증가 → τ 임계 초과 가설 지지")
        else:
            print("  ✗ 체류시간과 붕괴 간 명확한 관계 없음")
        
        if decay_diff < -0.01:
            print("  ✓ 붕괴 전 ER 분해 속도가 느림 → 소산 실패 가설 지지")
        else:
            print("  ✗ ER 분해 속도와 붕괴 간 명확한 관계 없음")
        
        if abs(c['avg_depth_curvature']) > abs(s['avg_depth_curvature']) * 1.2:
            print("  ✓ 붕괴 전 Depth 곡률 증가 → 구조 피로 가설 지지")
        else:
            print("  ✗ Depth 곡률과 붕괴 간 명확한 관계 없음")
        
    else:
        print("\n  Insufficient data for pattern comparison")
    
    print("\n" + "=" * 70)
    
    return results

def main():
    import os
    
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
    
    required_cols = {'open', 'high', 'low', 'close'}
    df.columns = df.columns.str.lower()
    
    if not required_cols.issubset(set(df.columns)):
        print(f"ERROR: Missing required columns. Found: {df.columns.tolist()}")
        return
    
    df = df.dropna(subset=['open', 'high', 'low', 'close'])
    print(f"Loaded {len(df)} bars")
    
    results = run_experiment(df)
    
    os.makedirs("v7-grammar-system/results", exist_ok=True)
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {RESULT_FILE}")

if __name__ == "__main__":
    main()
