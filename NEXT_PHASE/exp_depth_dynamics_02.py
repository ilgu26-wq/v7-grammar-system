"""
EXP-DEPTH-DYNAMICS-02: 전이의 사전성 측정
==========================================
연구 질문: Depth 상태 전이는 무엇에 의해 발생하는가?

조건 정의 (고정):
  C1: ER < 0.25
  C2: sign(depth_trend_t) != sign(depth_trend_{t-1})
  C_joint = C1 AND C2

관측 윈도우: W = {-1, -2, -3, -5, -10}

판정:
  w=-1,-2만 높음 → 관측은 거의 동시적
  w=-3,-5까지 유지 → 약한 사전성 존재
  w=-10까지 유지 → 사전 조건으로 간주 가능
  전 구간 무의미 → 사후 인식만 가능
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List

RESULT_FILE = "v7-grammar-system/results/exp_depth_dynamics_02.json"

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

def calc_depth_trend(depths: List[float], idx: int, k: int = 5) -> float:
    if idx < k:
        return 0.0
    window = depths[idx - k:idx + 1]
    if len(window) < 2:
        return 0.0
    return (window[-1] - window[0]) / k

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

def detect_transitions(depth_series: List[float]) -> List[int]:
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

def check_condition(er: float, depth_trend: float, prev_depth_trend: float) -> Dict[str, bool]:
    c1 = er < 0.25
    c2 = (depth_trend * prev_depth_trend) < 0 if prev_depth_trend != 0 else False
    return {
        "C1_er_low": c1,
        "C2_trend_flip": c2,
        "C_joint": c1 and c2
    }

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-DEPTH-DYNAMICS-02: 전이의 사전성 측정")
    print("=" * 70)
    
    print("\n[1] Generating time series...")
    depth_series = []
    er_series = []
    for idx in range(len(df)):
        depth_series.append(calc_depth(df, idx))
        er_series.append(calc_er(df, idx))
    
    depth_trend_series = []
    for idx in range(len(df)):
        depth_trend_series.append(calc_depth_trend(depth_series, idx))
    
    print(f"  Total bars: {len(df)}")
    
    print("\n[2] Detecting TRANSITION events...")
    transitions = detect_transitions(depth_series)
    transitions = [t for t in transitions if t >= 30 and t + 10 < len(df)]
    print(f"  TRANSITION events: {len(transitions)}")
    
    print("\n[3] Sampling NON-EVENT baseline...")
    transition_set = set(transitions)
    for t in transitions:
        for offset in range(-15, 16):
            transition_set.add(t + offset)
    
    non_event_candidates = [i for i in range(30, len(df) - 10) if i not in transition_set]
    np.random.seed(42)
    n_samples = min(len(non_event_candidates), len(transitions) * 3)
    baseline_indices = np.random.choice(non_event_candidates, size=n_samples, replace=False)
    print(f"  Baseline samples: {len(baseline_indices)}")
    
    W = [-1, -2, -3, -5, -10]
    
    print("\n[4] Computing condition rates per lookback...")
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "n_transitions": len(transitions),
            "n_baseline": len(baseline_indices)
        },
        "table": [],
        "decomposition": {"C1_only": [], "C2_only": [], "C_joint": []}
    }
    
    print("\n" + "=" * 70)
    print("Table 1 — Lift vs Lookback")
    print("=" * 70)
    print(f"{'w':>4} | {'P(C|Event)':>12} | {'P(C|Base)':>12} | {'Lift':>8} | {'N_event':>8}")
    print("-" * 70)
    
    for w in W:
        event_c1 = 0
        event_c2 = 0
        event_joint = 0
        event_n = 0
        
        for t0 in transitions:
            obs_idx = t0 + w
            if obs_idx < 5 or obs_idx >= len(df) - 1:
                continue
            
            er = er_series[obs_idx]
            depth_trend = depth_trend_series[obs_idx]
            prev_depth_trend = depth_trend_series[obs_idx - 1]
            
            cond = check_condition(er, depth_trend, prev_depth_trend)
            if cond["C1_er_low"]:
                event_c1 += 1
            if cond["C2_trend_flip"]:
                event_c2 += 1
            if cond["C_joint"]:
                event_joint += 1
            event_n += 1
        
        base_c1 = 0
        base_c2 = 0
        base_joint = 0
        base_n = 0
        
        for t0 in baseline_indices:
            obs_idx = t0 + w
            if obs_idx < 5 or obs_idx >= len(df) - 1:
                continue
            
            er = er_series[obs_idx]
            depth_trend = depth_trend_series[obs_idx]
            prev_depth_trend = depth_trend_series[obs_idx - 1]
            
            cond = check_condition(er, depth_trend, prev_depth_trend)
            if cond["C1_er_low"]:
                base_c1 += 1
            if cond["C2_trend_flip"]:
                base_c2 += 1
            if cond["C_joint"]:
                base_joint += 1
            base_n += 1
        
        p_event = event_joint / event_n if event_n > 0 else 0
        p_base = base_joint / base_n if base_n > 0 else 0
        lift = p_event / p_base if p_base > 0 else 0
        
        p_event_c1 = event_c1 / event_n if event_n > 0 else 0
        p_base_c1 = base_c1 / base_n if base_n > 0 else 0
        lift_c1 = p_event_c1 / p_base_c1 if p_base_c1 > 0 else 0
        
        p_event_c2 = event_c2 / event_n if event_n > 0 else 0
        p_base_c2 = base_c2 / base_n if base_n > 0 else 0
        lift_c2 = p_event_c2 / p_base_c2 if p_base_c2 > 0 else 0
        
        print(f"{w:>4} | {p_event:>12.4f} | {p_base:>12.4f} | {lift:>8.2f} | {event_n:>8}")
        
        results["table"].append({
            "w": w,
            "P_event": float(p_event),
            "P_base": float(p_base),
            "Lift": float(lift),
            "N_event": event_n
        })
        
        results["decomposition"]["C1_only"].append({"w": w, "Lift": float(lift_c1)})
        results["decomposition"]["C2_only"].append({"w": w, "Lift": float(lift_c2)})
        results["decomposition"]["C_joint"].append({"w": w, "Lift": float(lift)})
    
    print("\n" + "=" * 70)
    print("Condition Decomposition (Lift)")
    print("=" * 70)
    print(f"{'w':>4} | {'C1_only':>10} | {'C2_only':>10} | {'C_joint':>10}")
    print("-" * 50)
    for i, w in enumerate(W):
        c1 = results["decomposition"]["C1_only"][i]["Lift"]
        c2 = results["decomposition"]["C2_only"][i]["Lift"]
        cj = results["decomposition"]["C_joint"][i]["Lift"]
        print(f"{w:>4} | {c1:>10.2f} | {c2:>10.2f} | {cj:>10.2f}")
    
    print("\n" + "=" * 70)
    print("RANDOM SHIFT TEST")
    print("=" * 70)
    
    np.random.seed(123)
    random_shifts = np.random.randint(-20, 21, size=len(transitions))
    shifted_transitions = [t + s for t, s in zip(transitions, random_shifts)]
    shifted_transitions = [t for t in shifted_transitions if 30 <= t < len(df) - 10]
    
    shifted_joint = 0
    shifted_n = 0
    for t0 in shifted_transitions:
        obs_idx = t0 - 1
        if obs_idx < 5 or obs_idx >= len(df) - 1:
            continue
        er = er_series[obs_idx]
        depth_trend = depth_trend_series[obs_idx]
        prev_depth_trend = depth_trend_series[obs_idx - 1]
        cond = check_condition(er, depth_trend, prev_depth_trend)
        if cond["C_joint"]:
            shifted_joint += 1
        shifted_n += 1
    
    p_shifted = shifted_joint / shifted_n if shifted_n > 0 else 0
    original_p = results["table"][0]["P_event"]
    
    results["random_shift_test"] = {
        "original_P": float(original_p),
        "shifted_P": float(p_shifted),
        "collapsed": p_shifted < original_p * 0.5
    }
    
    print(f"  Original P(C_joint|TRANSITION, w=-1): {original_p:.4f}")
    print(f"  Shifted P(C_joint|RANDOM, w=-1): {p_shifted:.4f}")
    print(f"  Collapsed: {results['random_shift_test']['collapsed']}")
    
    print("\n" + "=" * 70)
    print("INTERPRETATION")
    print("=" * 70)
    
    lifts = [r["Lift"] for r in results["table"]]
    
    if lifts[0] > 1.5 and lifts[1] > 1.5 and lifts[2] < 1.2:
        interpretation = "SIMULTANEOUS: 관측은 거의 동시적 (w=-1,-2만 유의미)"
    elif lifts[0] > 1.5 and lifts[2] > 1.3 and lifts[3] < 1.2:
        interpretation = "WEAK_PRECEDENCE: 약한 사전성 존재 (w=-3까지)"
    elif lifts[4] > 1.3:
        interpretation = "STRONG_PRECEDENCE: 사전 조건으로 간주 가능 (w=-10까지 유지)"
    elif max(lifts) < 1.3:
        interpretation = "POST_HOC: 사후 인식만 가능 (전 구간 무의미)"
    else:
        interpretation = "MIXED: 혼합 패턴 (추가 분석 필요)"
    
    results["interpretation"] = interpretation
    print(f"\n  {interpretation}")
    
    return results

def main():
    data_paths = [
        "data/chart_combined_full.csv",
        "v7-grammar-system/data/chart_combined_full.csv"
    ]
    
    df = None
    for path in data_paths:
        if os.path.exists(path):
            df = pd.read_csv(path)
            print(f"Loaded: {path}")
            break
    
    if df is None:
        print("No data file found.")
        return
    
    results = run_experiment(df)
    
    os.makedirs(os.path.dirname(RESULT_FILE), exist_ok=True)
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {RESULT_FILE}")
    
    return results

if __name__ == "__main__":
    main()
