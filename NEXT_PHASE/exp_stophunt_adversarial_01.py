"""
EXP-STOPHUNT-ADVERSARIAL-01: Stop Hunt 가설 비틀기 실험
========================================================
목적: ER<0.25 + depth_trend 반전이 "스탑헌트" 때문인지 검증

H_SH: "이건 그냥 Stop Hunt다"

실험 A: 스탑헌트 통제 후 신호 유지 여부
실험 B: 방향성 분석
실험 C: 되돌림 시간 분석
실험 D: 채널(위치) 결합도
실험 E: 시간대/세션 분해

판정 기준:
- 스윕/스냅백 제거해도 ER low+trend flip 효과 유지 → 단순 스탑헌트 아님
- 스윕/스냅백 통제하면 효과 붕괴 → 스탑헌트가 주 원인
"""

import json
import os
import numpy as np
import pandas as pd
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

RESULT_FILE = "v7-grammar-system/results/exp_stophunt_adversarial_01.json"

# ===== DEPTH 계산 함수들 (기존과 동일) =====

def calc_depth(df: pd.DataFrame, idx: int, lookback: int = 20) -> float:
    start = max(0, idx - lookback + 1)
    window = df.iloc[start:idx + 1]
    if len(window) < 2:
        return 0.5
    high_20 = window['high'].max()
    low_20 = window['low'].min()
    range_20 = high_20 - low_20
    if range_20 < 0.01:
        return 0.5
    close = df.iloc[idx]['close']
    return (high_20 - close) / range_20

def calc_depth_slope(depths: List[float], k: int = 5) -> float:
    if len(depths) < k + 1:
        return 0.0
    recent = depths[-k:]
    if len(recent) < 2:
        return 0.0
    return (recent[-1] - recent[0]) / k

def calc_er(df: pd.DataFrame, idx: int, lookback: int = 10) -> float:
    start = max(0, idx - lookback + 1)
    window = df.iloc[start:idx + 1]
    if len(window) < 2:
        return 0.5
    price_change = abs(window.iloc[-1]['close'] - window.iloc[0]['close'])
    bar_changes = abs(window['close'].diff().dropna()).sum()
    if bar_changes < 0.01:
        return 1.0
    return min(1.0, price_change / bar_changes)

def calc_channel_pct(df: pd.DataFrame, idx: int, lookback: int = 20) -> float:
    start = max(0, idx - lookback + 1)
    window = df.iloc[start:idx + 1]
    if len(window) < 2:
        return 50.0
    high_20 = window['high'].max()
    low_20 = window['low'].min()
    rng = high_20 - low_20
    if rng < 0.01:
        return 50.0
    close = df.iloc[idx]['close']
    return (close - low_20) / rng * 100

# ===== STOP HUNT 라벨링 함수 =====

def detect_sweep(df: pd.DataFrame, idx: int, lookback: int = 10, k: float = 0.0) -> str:
    """
    Sweep 라벨 (Stop Hunt 발생)
    - sweep_high: high_t >= max(high_{t-20:t-1}) + k*range_20
    - sweep_low: low_t <= min(low_{t-20:t-1}) - k*range_20
    """
    if idx < lookback:
        return "none"
    
    window = df.iloc[idx - lookback:idx]
    high_20 = window['high'].max()
    low_20 = window['low'].min()
    range_20 = high_20 - low_20
    
    if range_20 < 0.01:
        return "none"
    
    current = df.iloc[idx]
    threshold = k * range_20
    
    if current['high'] >= high_20 + threshold:
        return "sweep_high"
    elif current['low'] <= low_20 - threshold:
        return "sweep_low"
    
    return "none"

def detect_snapback(df: pd.DataFrame, idx: int, sweep_type: str, m: float = 0.1) -> bool:
    """
    Snapback 라벨 (헌트의 본체)
    - abs(close_{t+1} - close_t) <= m*range_20 AND
    - sign(close_{t+1}-close_t)가 sweep 방향의 반대
    """
    if idx + 1 >= len(df) or sweep_type == "none":
        return False
    
    lookback = 20
    if idx < lookback:
        return False
    
    window = df.iloc[idx - lookback:idx]
    range_20 = window['high'].max() - window['low'].min()
    
    if range_20 < 0.01:
        return False
    
    current_close = df.iloc[idx]['close']
    next_close = df.iloc[idx + 1]['close']
    close_change = next_close - current_close
    
    # 작은 되돌림 체크
    if abs(close_change) > m * range_20:
        return False
    
    # 방향 반대 체크
    if sweep_type == "sweep_high" and close_change < 0:
        return True
    elif sweep_type == "sweep_low" and close_change > 0:
        return True
    
    return False

def calc_revert_time(df: pd.DataFrame, idx: int, sweep_type: str, max_bars: int = 10) -> int:
    """되돌림 시간: sweep 이전 영역으로 복귀하는 데 걸리는 바 수"""
    if idx + max_bars >= len(df) or sweep_type == "none":
        return -1
    
    lookback = 20
    if idx < lookback:
        return -1
    
    window = df.iloc[idx - lookback:idx]
    high_20 = window['high'].max()
    low_20 = window['low'].min()
    
    for tau in range(1, max_bars + 1):
        if idx + tau >= len(df):
            break
        future_close = df.iloc[idx + tau]['close']
        
        if sweep_type == "sweep_high":
            if future_close < high_20:
                return tau
        elif sweep_type == "sweep_low":
            if future_close > low_20:
                return tau
    
    return -1

# ===== TRANSITION 이벤트 감지 =====

def detect_transition_events(depth_series: List[float]) -> List[int]:
    """depth가 0.5 경계를 넘는 순간"""
    events = []
    if len(depth_series) < 10:
        return events
    
    prev_side = "LOW" if depth_series[5] < 0.5 else "HIGH"
    
    for i in range(10, len(depth_series)):
        curr_side = "LOW" if depth_series[i] < 0.5 else "HIGH"
        if curr_side != prev_side:
            events.append(i)
            prev_side = curr_side
    
    return events

# ===== 실험 실행 =====

def run_stophunt_adversarial(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-STOPHUNT-ADVERSARIAL-01: Stop Hunt 가설 비틀기")
    print("=" * 70)
    print(f"Total bars: {len(df)}")
    
    # 1. Depth 시계열 생성
    print("\n[STEP 1] Generating depth/ER time series...")
    depth_series = []
    er_series = []
    for idx in range(len(df)):
        depth_series.append(calc_depth(df, idx))
        er_series.append(calc_er(df, idx))
    
    # 2. TRANSITION 이벤트 감지
    print("\n[STEP 2] Detecting TRANSITION events...")
    transition_events = detect_transition_events(depth_series)
    print(f"  Total TRANSITION events: {len(transition_events)}")
    
    # 3. 각 이벤트에 sweep/snapback 라벨 추가
    print("\n[STEP 3] Labeling sweep/snapback...")
    
    event_data = []
    for idx in transition_events:
        if idx < 30 or idx + 5 >= len(df):
            continue
        
        sweep = detect_sweep(df, idx)
        snapback = detect_snapback(df, idx, sweep)
        revert_time = calc_revert_time(df, idx, sweep)
        
        depth_slope = calc_depth_slope(depth_series[:idx+1], k=5)
        er = er_series[idx]
        channel = calc_channel_pct(df, idx)
        
        # ER low + trend flip 조건
        er_low = er < 0.25
        trend_flip = abs(depth_slope) > 0.01  # 트렌드 변화
        
        # 다음 바 방향
        next_close_change = df.iloc[idx + 1]['close'] - df.iloc[idx]['close']
        next_depth_change = depth_series[idx + 1] - depth_series[idx] if idx + 1 < len(depth_series) else 0
        
        event_data.append({
            'idx': idx,
            'sweep': sweep,
            'snapback': snapback,
            'revert_time': revert_time,
            'er': er,
            'er_low': er_low,
            'depth_slope': depth_slope,
            'trend_flip': trend_flip,
            'channel': channel,
            'next_close_change': next_close_change,
            'next_depth_change': next_depth_change,
            'is_stophunt': sweep != "none"
        })
    
    event_df = pd.DataFrame(event_data)
    print(f"  Labeled events: {len(event_df)}")
    
    # 4. 실험 A: 스탑헌트 통제 후 효과 유지 여부
    print("\n" + "=" * 70)
    print("[EXPERIMENT A] Stop Hunt 통제 후 ER low 효과 유지 여부")
    print("=" * 70)
    
    # 전체에서 ER low 이벤트 비율
    all_er_low = event_df['er_low'].mean()
    
    # 스탑헌트 제거 후 ER low 비율
    clean_df = event_df[~event_df['is_stophunt']]
    clean_er_low = clean_df['er_low'].mean() if len(clean_df) > 0 else 0
    
    # 스탑헌트만 ER low 비율
    hunt_df = event_df[event_df['is_stophunt']]
    hunt_er_low = hunt_df['er_low'].mean() if len(hunt_df) > 0 else 0
    
    exp_a_result = {
        "all_events": len(event_df),
        "stophunt_events": len(hunt_df),
        "clean_events": len(clean_df),
        "all_er_low_rate": float(all_er_low),
        "clean_er_low_rate": float(clean_er_low),
        "hunt_er_low_rate": float(hunt_er_low),
        "effect_preserved": bool(abs(clean_er_low - all_er_low) < 0.1)
    }
    
    print(f"  All events ER_low rate: {all_er_low:.3f}")
    print(f"  Clean (no hunt) ER_low rate: {clean_er_low:.3f}")
    print(f"  Hunt only ER_low rate: {hunt_er_low:.3f}")
    print(f"  Effect preserved after removing hunts: {exp_a_result['effect_preserved']}")
    
    # 5. 실험 B: 방향성 분석
    print("\n" + "=" * 70)
    print("[EXPERIMENT B] 방향성 분석 (sweep_high vs sweep_low)")
    print("=" * 70)
    
    sweep_high_df = event_df[event_df['sweep'] == 'sweep_high']
    sweep_low_df = event_df[event_df['sweep'] == 'sweep_low']
    
    exp_b_result = {
        "sweep_high_count": len(sweep_high_df),
        "sweep_low_count": len(sweep_low_df),
        "sweep_high_avg_next_change": float(sweep_high_df['next_close_change'].mean()) if len(sweep_high_df) > 0 else 0,
        "sweep_low_avg_next_change": float(sweep_low_df['next_close_change'].mean()) if len(sweep_low_df) > 0 else 0,
        "directional_asymmetry": False
    }
    
    if len(sweep_high_df) > 5 and len(sweep_low_df) > 5:
        # 방향성이 있으면 sweep_high 후에는 하락, sweep_low 후에는 상승 예상
        high_reverses = (sweep_high_df['next_close_change'] < 0).mean()
        low_reverses = (sweep_low_df['next_close_change'] > 0).mean()
        exp_b_result['sweep_high_reverse_rate'] = float(high_reverses)
        exp_b_result['sweep_low_reverse_rate'] = float(low_reverses)
        exp_b_result['directional_asymmetry'] = bool(high_reverses > 0.55 and low_reverses > 0.55)
    
    print(f"  Sweep High events: {len(sweep_high_df)}")
    print(f"  Sweep Low events: {len(sweep_low_df)}")
    print(f"  Sweep High → next bar avg change: {exp_b_result['sweep_high_avg_next_change']:.4f}")
    print(f"  Sweep Low → next bar avg change: {exp_b_result['sweep_low_avg_next_change']:.4f}")
    print(f"  Directional asymmetry detected: {exp_b_result['directional_asymmetry']}")
    
    # 6. 실험 C: 되돌림 시간 분석
    print("\n" + "=" * 70)
    print("[EXPERIMENT C] 되돌림 시간 분석")
    print("=" * 70)
    
    hunt_with_revert = hunt_df[hunt_df['revert_time'] > 0]
    
    exp_c_result = {
        "hunts_with_revert": len(hunt_with_revert),
        "revert_time_mean": float(hunt_with_revert['revert_time'].mean()) if len(hunt_with_revert) > 0 else -1,
        "revert_time_median": float(hunt_with_revert['revert_time'].median()) if len(hunt_with_revert) > 0 else -1,
        "fast_revert_rate": 0,  # 1-2바 되돌림 비율
        "is_fast_revert_pattern": False
    }
    
    if len(hunt_with_revert) > 0:
        fast_reverts = (hunt_with_revert['revert_time'] <= 2).sum()
        exp_c_result['fast_revert_rate'] = float(fast_reverts / len(hunt_with_revert))
        exp_c_result['is_fast_revert_pattern'] = bool(exp_c_result['fast_revert_rate'] > 0.5)
    
    print(f"  Hunts with measurable revert: {len(hunt_with_revert)}")
    print(f"  Mean revert time: {exp_c_result['revert_time_mean']:.2f} bars")
    print(f"  Median revert time: {exp_c_result['revert_time_median']:.2f} bars")
    print(f"  Fast revert (1-2 bars) rate: {exp_c_result['fast_revert_rate']:.3f}")
    print(f"  Fast revert pattern: {exp_c_result['is_fast_revert_pattern']}")
    
    # 7. 실험 D: 채널(위치) 결합도
    print("\n" + "=" * 70)
    print("[EXPERIMENT D] 채널 위치 결합도")
    print("=" * 70)
    
    # 채널 극단 (상위 20% 또는 하위 20%)
    event_df['channel_extreme'] = (event_df['channel'] > 80) | (event_df['channel'] < 20)
    
    er_low_extreme = event_df[(event_df['er_low']) & (event_df['channel_extreme'])]
    er_low_mid = event_df[(event_df['er_low']) & (~event_df['channel_extreme'])]
    
    exp_d_result = {
        "er_low_at_extreme": len(er_low_extreme),
        "er_low_at_mid": len(er_low_mid),
        "extreme_concentration": 0,
        "channel_independent": False
    }
    
    if len(er_low_extreme) + len(er_low_mid) > 0:
        exp_d_result['extreme_concentration'] = float(len(er_low_extreme) / (len(er_low_extreme) + len(er_low_mid)))
        # 채널 극단에 50% 이상 몰리지 않으면 채널 독립적
        exp_d_result['channel_independent'] = bool(exp_d_result['extreme_concentration'] < 0.5)
    
    print(f"  ER_low at channel extreme (>80% or <20%): {len(er_low_extreme)}")
    print(f"  ER_low at channel mid (20-80%): {len(er_low_mid)}")
    print(f"  Extreme concentration: {exp_d_result['extreme_concentration']:.3f}")
    print(f"  Channel independent: {exp_d_result['channel_independent']}")
    
    # 8. 최종 판정
    print("\n" + "=" * 70)
    print("FINAL VERDICT")
    print("=" * 70)
    
    verdict = {
        "exp_a_effect_preserved": bool(exp_a_result['effect_preserved']),
        "exp_b_directional": bool(exp_b_result['directional_asymmetry']),
        "exp_c_fast_revert": bool(exp_c_result['is_fast_revert_pattern']),
        "exp_d_channel_independent": bool(exp_d_result['channel_independent'])
    }
    
    # 스탑헌트 가설 점수 (높을수록 스탑헌트 가능성)
    stophunt_score = 0
    if not exp_a_result['effect_preserved']:
        stophunt_score += 1  # 통제 시 효과 사라짐
    if exp_b_result['directional_asymmetry']:
        stophunt_score += 1  # 방향성 강함
    if exp_c_result['is_fast_revert_pattern']:
        stophunt_score += 1  # 빠른 되돌림
    if not exp_d_result['channel_independent']:
        stophunt_score += 1  # 채널 극단에 집중
    
    verdict['stophunt_score'] = stophunt_score
    verdict['interpretation'] = ""
    
    if stophunt_score >= 3:
        verdict['interpretation'] = "H_SH STRONG: 대부분 스탑헌트로 설명됨"
    elif stophunt_score >= 2:
        verdict['interpretation'] = "H_SH MODERATE: 스탑헌트 요소 있으나 구조적 요소도 존재"
    else:
        verdict['interpretation'] = "H_SH WEAK: 단순 스탑헌트로 설명 불가, 구조적 전이 가능성"
    
    print(f"\n  Stop Hunt Score: {stophunt_score}/4")
    print(f"  Interpretation: {verdict['interpretation']}")
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "total_transitions": len(transition_events),
            "labeled_events": len(event_df)
        },
        "experiment_a": exp_a_result,
        "experiment_b": exp_b_result,
        "experiment_c": exp_c_result,
        "experiment_d": exp_d_result,
        "verdict": verdict
    }
    
    return results

def main():
    data_paths = [
        "data/chart_combined_full.csv",
        "v7-grammar-system/data/chart_combined_full.csv",
        "attached_assets/chart_combined_full.csv"
    ]
    
    df = None
    for path in data_paths:
        if os.path.exists(path):
            df = pd.read_csv(path)
            print(f"Loaded data from: {path}")
            break
    
    if df is None:
        print("No data file found.")
        return
    
    results = run_stophunt_adversarial(df)
    
    os.makedirs(os.path.dirname(RESULT_FILE), exist_ok=True)
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {RESULT_FILE}")
    
    return results

if __name__ == "__main__":
    main()
