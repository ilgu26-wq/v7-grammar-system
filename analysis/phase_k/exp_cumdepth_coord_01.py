"""
EXP-CUMDEPTH-COORD-01: Storm-IN 내부 누적 Depth 좌표계 검증
============================================================

목적:
  Storm-IN 상태 내부에서 누적 Depth 분포가
  연속적인 상태 좌표(geometry)로 작동하는지 검증

가설:
  H0: CumDepth는 의미 없는 누적 지표
  H1: CumDepth 분포는 연속적 상태 공간 형성

판정:
  3개 중 2개 이상 만족 시 H1 채택:
  1) Skew가 Q1→Q4로 단조적 변화
  2) 추가 붕괴 확률이 Q3/Q4에서 증가
  3) Q2/Q3에서 방향 불안정성(분산 최대)
"""

import json
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from phase_m.axiom_validation_tests import load_signals, classify_storm_coordinate


def load_chart_data() -> pd.DataFrame:
    chart_path = 'data/chart_combined_full.csv'
    df = pd.read_csv(chart_path)
    df['time'] = pd.to_datetime(df['time'])
    df = df.drop_duplicates(subset=['time'], keep='first')
    df = df.set_index('time').sort_index()
    return df


def calc_rfc(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> int:
    """Recovery Failure Count"""
    if idx < lookback:
        return 0
    
    window = chart_df.iloc[idx-lookback:idx]
    consecutive_fails = 0
    
    for i in range(1, len(window)):
        prev_range = window['high'].iloc[i-1] - window['low'].iloc[i-1]
        if prev_range < 2:
            continue
        
        current_close = window['close'].iloc[i]
        prev_low = window['low'].iloc[i-1]
        recovery_threshold = prev_low + prev_range * 0.5
        
        if current_close < recovery_threshold:
            consecutive_fails += 1
        else:
            consecutive_fails = 0
    
    return consecutive_fails


def calc_bcr(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> float:
    """Branch Collapse Ratio"""
    if idx < lookback * 2:
        return 1.0
    
    recent = chart_df.iloc[idx-lookback//2:idx]
    past = chart_df.iloc[idx-lookback:idx-lookback//2]
    
    recent_range = recent['high'].max() - recent['low'].min()
    past_range = past['high'].max() - past['low'].min()
    
    if past_range < 1:
        return 1.0
    
    return recent_range / past_range


def calc_eda(chart_df: pd.DataFrame, idx: int, lookback: int = 10) -> float:
    """Energy Dissipation Asymmetry"""
    if idx < lookback:
        return 1.0
    
    window = chart_df.iloc[idx-lookback:idx]
    
    recent_avg = (window['high'].iloc[-lookback//2:] - window['low'].iloc[-lookback//2:]).mean()
    past_avg = (window['high'].iloc[:lookback//2] - window['low'].iloc[:lookback//2]).mean()
    
    if past_avg < 0.1:
        return 1.0
    
    return recent_avg / past_avg


def calc_depth_score(rfc: int, bcr: float, eda: float) -> int:
    """순간 Depth 점수 (0-3)"""
    score = 0
    if rfc >= 1:
        score += 1
    if bcr <= 0.8:
        score += 1
    if eda <= 0.85:
        score += 1
    return score


def calc_cumdepth(chart_df: pd.DataFrame, idx: int, K: int = 5) -> int:
    """누적 Depth (최근 K bars)"""
    if idx < K + 10:
        return 0
    
    total = 0
    for i in range(K):
        cur_idx = idx - i
        rfc = calc_rfc(chart_df, cur_idx)
        bcr = calc_bcr(chart_df, cur_idx)
        eda = calc_eda(chart_df, cur_idx)
        total += calc_depth_score(rfc, bcr, eda)
    
    return total


def get_direction_outcome(chart_df: pd.DataFrame, idx: int, lookahead: int = 20) -> str:
    """이후 방향 결과"""
    if idx + lookahead >= len(chart_df):
        return None
    
    entry = chart_df.iloc[idx]['close']
    future = chart_df.iloc[idx+1:idx+1+lookahead]
    
    max_up = future['high'].max() - entry
    max_down = entry - future['low'].min()
    
    if max_up >= 15 and max_up > max_down:
        return 'UP'
    elif max_down >= 15 and max_down > max_up:
        return 'DOWN'
    else:
        return 'NEUTRAL'


def check_additional_collapse(chart_df: pd.DataFrame, idx: int, lookahead: int = 10) -> bool:
    """이후 추가 붕괴 발생 여부"""
    if idx + lookahead >= len(chart_df):
        return None
    
    for i in range(1, lookahead + 1):
        future_idx = idx + i
        rfc = calc_rfc(chart_df, future_idx)
        bcr = calc_bcr(chart_df, future_idx)
        eda = calc_eda(chart_df, future_idx)
        
        if rfc >= 1 and bcr <= 0.8 and eda <= 0.85:
            return True
    
    return False


def run_exp_cumdepth_coord_01():
    """EXP-CUMDEPTH-COORD-01 실행"""
    print("="*70)
    print("EXP-CUMDEPTH-COORD-01: Storm-IN 내부 좌표계 검증")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("\n가설: Storm-IN 내부에 누적 Depth 좌표계가 존재하는가?")
    print("-"*70)
    
    signals = load_signals()
    chart_df = load_chart_data()
    
    chart_start = chart_df.index.min()
    chart_end = chart_df.index.max()
    
    storm_in_signals = [s for s in signals if classify_storm_coordinate(s) == "STORM_IN"]
    print(f"Storm-IN signals: {len(storm_in_signals)}")
    
    K = 5
    
    data_points = []
    
    for s in storm_in_signals:
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
        
        if idx < K + 15 or idx + 25 >= len(chart_df):
            continue
        
        cumdepth = calc_cumdepth(chart_df, idx, K)
        direction = get_direction_outcome(chart_df, idx)
        collapse = check_additional_collapse(chart_df, idx)
        
        if direction is None or collapse is None:
            continue
        
        data_points.append({
            'ts': ts,
            'cumdepth': cumdepth,
            'direction': direction,
            'collapse': collapse
        })
    
    print(f"Valid data points: {len(data_points)}")
    
    cumdepths = [d['cumdepth'] for d in data_points]
    q1 = np.percentile(cumdepths, 25)
    q2 = np.percentile(cumdepths, 50)
    q3 = np.percentile(cumdepths, 75)
    
    print(f"\nCumDepth 분위: Q1={q1}, Q2={q2}, Q3={q3}")
    
    quartiles = {
        'Q1': [d for d in data_points if d['cumdepth'] <= q1],
        'Q2': [d for d in data_points if q1 < d['cumdepth'] <= q2],
        'Q3': [d for d in data_points if q2 < d['cumdepth'] <= q3],
        'Q4': [d for d in data_points if d['cumdepth'] > q3]
    }
    
    print("\n" + "="*70)
    print("QUARTILE ANALYSIS")
    print("="*70)
    
    results = {}
    
    for q_name, q_data in quartiles.items():
        n = len(q_data)
        if n == 0:
            continue
        
        up = sum(1 for d in q_data if d['direction'] == 'UP')
        down = sum(1 for d in q_data if d['direction'] == 'DOWN')
        neutral = sum(1 for d in q_data if d['direction'] == 'NEUTRAL')
        
        collapse_rate = sum(1 for d in q_data if d['collapse']) / n * 100
        
        skew = (down - up) / n * 100
        
        variance = (up/n - 0.5)**2 + (down/n - 0.5)**2 if n > 0 else 0
        
        results[q_name] = {
            'n': n,
            'up': up,
            'down': down,
            'neutral': neutral,
            'skew': skew,
            'collapse_rate': collapse_rate,
            'variance': variance
        }
        
        print(f"\n{q_name} (N={n}):")
        print(f"  UP: {up} ({up/n*100:.1f}%)")
        print(f"  DOWN: {down} ({down/n*100:.1f}%)")
        print(f"  NEUTRAL: {neutral} ({neutral/n*100:.1f}%)")
        print(f"  Skew (DOWN-UP): {skew:+.1f}pp")
        print(f"  Collapse Rate: {collapse_rate:.1f}%")
    
    print("\n" + "="*70)
    print("COORDINATE SYSTEM TESTS")
    print("="*70)
    
    tests_passed = 0
    
    print("\n[Test 1] Skew 단조 변화 (Q1→Q4)")
    skews = [results.get(q, {}).get('skew', 0) for q in ['Q1', 'Q2', 'Q3', 'Q4']]
    print(f"  Skews: {[f'{s:+.1f}' for s in skews]}")
    
    monotonic = all(skews[i] <= skews[i+1] for i in range(len(skews)-1)) or \
                all(skews[i] >= skews[i+1] for i in range(len(skews)-1))
    
    if monotonic and abs(skews[-1] - skews[0]) >= 10:
        tests_passed += 1
        print("  → ✅ PASS (단조적 변화 확인)")
    else:
        print("  → ❌ FAIL")
    
    print("\n[Test 2] 추가 붕괴 확률 Q3/Q4에서 증가")
    q1_collapse = results.get('Q1', {}).get('collapse_rate', 0)
    q4_collapse = results.get('Q4', {}).get('collapse_rate', 0)
    print(f"  Q1 Collapse: {q1_collapse:.1f}%")
    print(f"  Q4 Collapse: {q4_collapse:.1f}%")
    
    if q4_collapse > q1_collapse + 5:
        tests_passed += 1
        print("  → ✅ PASS (Q4에서 붕괴 증가)")
    else:
        print("  → ❌ FAIL")
    
    print("\n[Test 3] Q2/Q3에서 방향 불안정성 (분산 최대)")
    variances = {q: results.get(q, {}).get('variance', 0) for q in ['Q1', 'Q2', 'Q3', 'Q4']}
    print(f"  Variances: {variances}")
    
    mid_var = max(variances.get('Q2', 0), variances.get('Q3', 0))
    edge_var = max(variances.get('Q1', 0), variances.get('Q4', 0))
    
    if mid_var > edge_var:
        tests_passed += 1
        print("  → ✅ PASS (중간 분위 불안정)")
    else:
        print("  → ❌ FAIL")
    
    print("\n" + "="*70)
    print("VERDICT")
    print("="*70)
    
    if tests_passed >= 2:
        verdict = "✅ H1 채택: 좌표계 존재"
        interpretation = """
Storm-IN 내부에 누적 Depth 좌표계가 존재한다.

→ CumDepth 분위가 연속적 상태 공간을 형성
→ Q2-Q3 = 중간관리자 영역 (풍차 초입)
→ Q4 = 코어 붕괴 영역
"""
    else:
        verdict = "❌ H0 유지: 좌표계 미확인"
        interpretation = "현재 데이터로는 좌표계 존재 확인 불가"
    
    print(f"\nTests Passed: {tests_passed}/3")
    print(f"Verdict: {verdict}")
    print(interpretation)
    
    output = {
        'timestamp': datetime.now().isoformat(),
        'experiment': 'EXP_CUMDEPTH_COORD_01',
        'total_points': len(data_points),
        'quartiles': results,
        'tests_passed': tests_passed,
        'verdict': verdict
    }
    
    output_path = 'v7-grammar-system/analysis/phase_k/exp_cumdepth_coord_01_result.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    return output


if __name__ == "__main__":
    run_exp_cumdepth_coord_01()
