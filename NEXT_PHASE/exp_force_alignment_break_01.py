"""
EXP-FORCE-ALIGNMENT-BREAK-01: 다차원 정렬 붕괴 검증
====================================================
핵심 가설:
  DEPTH 변화는 단일 축 누적 임계가 아니라
  다차원 상태 벡터의 '정렬 붕괴(alignment break)'에서 발생한다

상태 벡터:
  State_t = [depth, ER, channel_pos, range_norm, force_ratio]

검정:
  1. alignment 급락 → DEPTH change 선행?
  2. alignment 급락 → ER collapse 선행?
  3. 랜덤 시프트 시 붕괴?
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List
from scipy.spatial.distance import cosine

RESULT_FILE = "v7-grammar-system/results/exp_force_alignment_break_01.json"

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

def calc_channel_pos(df: pd.DataFrame, idx: int, lookback: int = 20) -> float:
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
    return (close - low_20) / range_20

def calc_force_ratio(df: pd.DataFrame, idx: int) -> float:
    if idx < 1:
        return 1.0
    row = df.iloc[idx]
    close = row['close']
    high = row['high']
    low = row['low']
    
    buyer = close - low
    seller = high - close
    
    if seller < 0.01:
        return 10.0
    return min(10.0, buyer / seller)

def normalize_series(series: pd.Series) -> pd.Series:
    """Min-max 정규화"""
    min_val = series.min()
    max_val = series.max()
    if max_val - min_val < 0.0001:
        return pd.Series([0.5] * len(series))
    return (series - min_val) / (max_val - min_val)

def calc_state_vector(df: pd.DataFrame, idx: int, 
                      depth_s: pd.Series, er_s: pd.Series, 
                      channel_s: pd.Series, range_s: pd.Series, 
                      force_s: pd.Series) -> np.ndarray:
    """다차원 상태 벡터"""
    return np.array([
        depth_s.iloc[idx],
        er_s.iloc[idx],
        channel_s.iloc[idx],
        range_s.iloc[idx],
        force_s.iloc[idx]
    ])

def calc_alignment(v1: np.ndarray, v2: np.ndarray) -> float:
    """두 상태 벡터 간 정렬도 (코사인 유사도)"""
    if np.linalg.norm(v1) < 0.001 or np.linalg.norm(v2) < 0.001:
        return 1.0
    return 1 - cosine(v1, v2)

def calc_state_change(v1: np.ndarray, v2: np.ndarray) -> float:
    """상태 벡터 변화량 (L2 norm)"""
    return np.linalg.norm(v2 - v1)

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

def run_experiment(df: pd.DataFrame) -> Dict:
    print("=" * 70)
    print("EXP-FORCE-ALIGNMENT-BREAK-01: 다차원 정렬 붕괴 검증")
    print("=" * 70)
    
    print("\n[1] Computing individual dimensions...")
    
    depth_raw = []
    er_raw = []
    channel_raw = []
    force_raw = []
    
    for idx in range(len(df)):
        depth_raw.append(calc_depth(df, idx))
        er_raw.append(calc_er(df, idx))
        channel_raw.append(calc_channel_pos(df, idx))
        force_raw.append(calc_force_ratio(df, idx))
    
    df['depth'] = depth_raw
    df['er'] = er_raw
    df['channel'] = channel_raw
    df['force_ratio'] = force_raw
    df['range_norm'] = df['high'] - df['low']
    
    depth_n = normalize_series(pd.Series(depth_raw))
    er_n = normalize_series(pd.Series(er_raw))
    channel_n = normalize_series(pd.Series(channel_raw))
    range_n = normalize_series(df['range_norm'])
    force_n = normalize_series(pd.Series(force_raw))
    
    print(f"  Total bars: {len(df)}")
    
    print("\n[2] Computing state vectors and alignment...")
    
    alignment_series = [1.0]
    state_change_series = [0.0]
    
    for idx in range(1, len(df)):
        v_prev = calc_state_vector(df, idx-1, depth_n, er_n, channel_n, range_n, force_n)
        v_curr = calc_state_vector(df, idx, depth_n, er_n, channel_n, range_n, force_n)
        
        alignment = calc_alignment(v_prev, v_curr)
        state_change = calc_state_change(v_prev, v_curr)
        
        alignment_series.append(alignment)
        state_change_series.append(state_change)
    
    df['alignment'] = alignment_series
    df['state_change'] = state_change_series
    
    depth_change = [0] + [abs(depth_raw[i] - depth_raw[i-1]) for i in range(1, len(depth_raw))]
    df['depth_change'] = depth_change
    
    df['zpoc'] = df['er'] < 0.25
    df['er_collapse'] = df['er'] < 0.20
    
    transitions = detect_transitions(depth_raw)
    transition_set = set(transitions)
    df['is_transition'] = df.index.isin(transition_set)
    
    print(f"  TRANSITION events: {len(transitions)}")
    
    print("\n[3] Alignment break analysis...")
    
    alignment_q10 = df['alignment'].quantile(0.10)
    df['alignment_break'] = df['alignment'] < alignment_q10
    
    state_change_q90 = df['state_change'].quantile(0.90)
    df['large_state_change'] = df['state_change'] >= state_change_q90
    
    print(f"\n  Alignment Q10 threshold: {alignment_q10:.4f}")
    print(f"  State change Q90 threshold: {state_change_q90:.4f}")
    
    print("\n[4] Comparing predictive power: alignment_break vs depth_change...")
    
    high_depth_change = df['depth_change'] >= df['depth_change'].quantile(0.90)
    
    er_collapse_given_align_break = df[df['alignment_break']]['er_collapse'].mean()
    er_collapse_given_depth_high = df[high_depth_change]['er_collapse'].mean()
    er_collapse_baseline = df['er_collapse'].mean()
    
    trans_given_align_break = df[df['alignment_break']]['is_transition'].mean()
    trans_given_depth_high = df[high_depth_change]['is_transition'].mean()
    trans_baseline = df['is_transition'].mean()
    
    align_er_lift = er_collapse_given_align_break / er_collapse_baseline if er_collapse_baseline > 0 else 0
    depth_er_lift = er_collapse_given_depth_high / er_collapse_baseline if er_collapse_baseline > 0 else 0
    
    align_trans_lift = trans_given_align_break / trans_baseline if trans_baseline > 0 else 0
    depth_trans_lift = trans_given_depth_high / trans_baseline if trans_baseline > 0 else 0
    
    print(f"\n  ER Collapse prediction:")
    print(f"    Alignment break → ER collapse: {100*er_collapse_given_align_break:.1f}% (Lift: {align_er_lift:.2f})")
    print(f"    Depth change high → ER collapse: {100*er_collapse_given_depth_high:.1f}% (Lift: {depth_er_lift:.2f})")
    
    print(f"\n  TRANSITION prediction:")
    print(f"    Alignment break → TRANSITION: {100*trans_given_align_break:.1f}% (Lift: {align_trans_lift:.2f})")
    print(f"    Depth change high → TRANSITION: {100*trans_given_depth_high:.1f}% (Lift: {depth_trans_lift:.2f})")
    
    print("\n[5] Temporal precedence test...")
    
    er_collapse_events = df[df['er_collapse'] & ~df['er_collapse'].shift(1).fillna(False)].index.tolist()
    
    align_leads_er = 0
    depth_leads_er = 0
    both_lead = 0
    
    lookback = 5
    
    for evt in er_collapse_events:
        if evt < lookback:
            continue
        
        pre_window = df.iloc[evt-lookback:evt]
        
        had_align_break = pre_window['alignment_break'].any()
        had_depth_high = (pre_window['depth_change'] >= df['depth_change'].quantile(0.90)).any()
        
        if had_align_break and had_depth_high:
            both_lead += 1
        elif had_align_break:
            align_leads_er += 1
        elif had_depth_high:
            depth_leads_er += 1
    
    total_events = len(er_collapse_events)
    print(f"\n  ER collapse events: {total_events}")
    print(f"  Alignment break leads: {align_leads_er} ({100*align_leads_er/total_events:.1f}%)")
    print(f"  Depth change leads: {depth_leads_er} ({100*depth_leads_er/total_events:.1f}%)")
    print(f"  Both lead: {both_lead} ({100*both_lead/total_events:.1f}%)")
    
    print("\n[6] Random shift test...")
    
    np.random.seed(42)
    
    original_align_at_trans = df.loc[transitions, 'alignment'].mean() if transitions else 0
    original_state_at_trans = df.loc[transitions, 'state_change'].mean() if transitions else 0
    
    shifts = np.random.randint(-50, 51, size=len(transitions))
    shifted_trans = [(t + s) % len(df) for t, s in zip(transitions, shifts)]
    
    shifted_align = df.loc[shifted_trans, 'alignment'].mean() if shifted_trans else 0
    shifted_state = df.loc[shifted_trans, 'state_change'].mean() if shifted_trans else 0
    
    align_preservation = shifted_align / original_align_at_trans if original_align_at_trans > 0 else 0
    state_preservation = shifted_state / original_state_at_trans if original_state_at_trans > 0 else 0
    
    print(f"\n  Original avg alignment at TRANSITION: {original_align_at_trans:.4f}")
    print(f"  Shifted avg alignment: {shifted_align:.4f}")
    print(f"  Preservation: {align_preservation:.2f}")
    
    print(f"\n  Original avg state_change at TRANSITION: {original_state_at_trans:.4f}")
    print(f"  Shifted avg state_change: {shifted_state:.4f}")
    print(f"  Preservation: {state_preservation:.2f}")
    
    shift_collapsed = align_preservation > 1.1 or state_preservation < 0.85
    print(f"\n  Structure collapsed under shift: {shift_collapsed}")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    alignment_stronger = align_er_lift > depth_er_lift or align_trans_lift > depth_trans_lift
    
    results = {
        "metadata": {
            "total_bars": len(df),
            "transitions": len(transitions),
            "er_collapse_events": total_events
        },
        "predictive_power": {
            "alignment_break": {
                "er_collapse_rate": float(er_collapse_given_align_break),
                "er_lift": float(align_er_lift),
                "trans_rate": float(trans_given_align_break),
                "trans_lift": float(align_trans_lift)
            },
            "depth_change": {
                "er_collapse_rate": float(er_collapse_given_depth_high),
                "er_lift": float(depth_er_lift),
                "trans_rate": float(trans_given_depth_high),
                "trans_lift": float(depth_trans_lift)
            }
        },
        "temporal_precedence": {
            "align_leads": int(align_leads_er),
            "depth_leads": int(depth_leads_er),
            "both_lead": int(both_lead),
            "total_events": int(total_events)
        },
        "random_shift": {
            "align_preservation": float(align_preservation),
            "state_preservation": float(state_preservation),
            "collapsed": bool(shift_collapsed)
        },
        "validation": {
            "alignment_stronger_than_depth": bool(alignment_stronger),
            "shift_collapsed": bool(shift_collapsed),
            "MULTIDIM_ALIGNMENT_CAUSAL": bool(alignment_stronger and shift_collapsed)
        }
    }
    
    print(f"\n  Alignment break stronger than depth alone: {alignment_stronger}")
    print(f"  Structure collapsed under shift: {shift_collapsed}")
    print(f"\n  MULTIDIMENSIONAL ALIGNMENT CAUSAL: {results['validation']['MULTIDIM_ALIGNMENT_CAUSAL']}")
    
    if results['validation']['MULTIDIM_ALIGNMENT_CAUSAL']:
        print("\n  → DEPTH = 다차원 정렬 붕괴의 투영")
    else:
        print("\n  → 다차원 정렬 구조 부분 확인")
    
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
