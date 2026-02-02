"""
EXP-SELLER-IMPOTENCE-01: 매도자 무력화 구조 검증
=================================================
질문: 왜 어떤 시점부터 매도 체결은 '움직임'을 만들지 못하는가?

정의:
  Seller_Active = down_close OR lower_high 발생
  Seller_Effective = Seller_Active AND |Δprice| > ε

검증:
  1. Seller_Active rate vs Seller_Effective rate
  2. ER 붕괴와 Seller_Effective 감소 상관
  3. Seller_Effective → 0 직후 TRANSITION 발생 여부
"""

import json
import os
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple

RESULT_FILE = "v7-grammar-system/results/exp_seller_impotence_01.json"

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
    print("EXP-SELLER-IMPOTENCE-01: 매도자 무력화 구조")
    print("=" * 70)
    
    epsilon = df['close'].diff().abs().median() * 0.5
    print(f"\n  ε (price impact threshold): {epsilon:.2f}")
    
    print("\n[1] Computing time series...")
    
    seller_active = []
    seller_effective = []
    buyer_active = []
    buyer_effective = []
    er_series = []
    depth_series = []
    
    for idx in range(1, len(df)):
        prev = df.iloc[idx - 1]
        curr = df.iloc[idx]
        
        down_close = curr['close'] < prev['close']
        lower_high = curr['high'] < prev['high']
        up_close = curr['close'] > prev['close']
        higher_low = curr['low'] > prev['low']
        
        is_seller_active = down_close or lower_high
        is_buyer_active = up_close or higher_low
        
        delta_price = abs(curr['close'] - prev['close'])
        is_effective = delta_price > epsilon
        
        seller_active.append(is_seller_active)
        seller_effective.append(is_seller_active and is_effective)
        buyer_active.append(is_buyer_active)
        buyer_effective.append(is_buyer_active and is_effective)
        
        er_series.append(calc_er(df, idx))
        depth_series.append(calc_depth(df, idx))
    
    print(f"  Total bars: {len(seller_active)}")
    print(f"  Seller_Active rate: {100*np.mean(seller_active):.1f}%")
    print(f"  Seller_Effective rate: {100*np.mean(seller_effective):.1f}%")
    print(f"  Buyer_Active rate: {100*np.mean(buyer_active):.1f}%")
    print(f"  Buyer_Effective rate: {100*np.mean(buyer_effective):.1f}%")
    
    print("\n[2] Detecting TRANSITION events...")
    transitions = detect_transitions(depth_series)
    transition_set = set(transitions)
    print(f"  TRANSITION events: {len(transitions)}")
    
    print("\n[3] Phase analysis (ER-based segmentation)...")
    
    er_high_mask = [er > 0.35 for er in er_series]
    er_low_mask = [er < 0.25 for er in er_series]
    
    phase_a_sa = [seller_active[i] for i in range(len(er_series)) if er_high_mask[i]]
    phase_a_se = [seller_effective[i] for i in range(len(er_series)) if er_high_mask[i]]
    
    phase_b_sa = [seller_active[i] for i in range(len(er_series)) if er_low_mask[i]]
    phase_b_se = [seller_effective[i] for i in range(len(er_series)) if er_low_mask[i]]
    
    print("\n  Phase A (ER > 0.35, Normal):")
    print(f"    N: {len(phase_a_sa)}")
    print(f"    Seller_Active: {100*np.mean(phase_a_sa):.1f}%")
    print(f"    Seller_Effective: {100*np.mean(phase_a_se):.1f}%")
    print(f"    Effectiveness ratio: {np.mean(phase_a_se)/np.mean(phase_a_sa):.2f}")
    
    print("\n  Phase B (ER < 0.25, ZPOC):")
    print(f"    N: {len(phase_b_sa)}")
    print(f"    Seller_Active: {100*np.mean(phase_b_sa):.1f}%")
    print(f"    Seller_Effective: {100*np.mean(phase_b_se):.1f}%")
    print(f"    Effectiveness ratio: {np.mean(phase_b_se)/np.mean(phase_b_sa):.2f}")
    
    eff_ratio_a = np.mean(phase_a_se) / np.mean(phase_a_sa)
    eff_ratio_b = np.mean(phase_b_se) / np.mean(phase_b_sa)
    impotence_drop = 1 - (eff_ratio_b / eff_ratio_a)
    
    print(f"\n  Impotence drop: {100*impotence_drop:.1f}%")
    
    print("\n[4] Seller_Effective → 0 before TRANSITION?")
    
    se_before_transition = []
    se_random_baseline = []
    
    for t in transitions:
        if t < 10:
            continue
        window_se = seller_effective[t-10:t]
        if len(window_se) == 10:
            se_rate = sum(window_se) / len(window_se)
            se_before_transition.append(se_rate)
    
    non_transition_indices = [i for i in range(30, len(seller_effective) - 10) if i not in transition_set]
    np.random.seed(42)
    sample_indices = np.random.choice(non_transition_indices, size=min(len(se_before_transition), len(non_transition_indices)), replace=False)
    
    for t in sample_indices:
        window_se = seller_effective[t-10:t]
        if len(window_se) == 10:
            se_rate = sum(window_se) / len(window_se)
            se_random_baseline.append(se_rate)
    
    avg_se_before_transition = np.mean(se_before_transition)
    avg_se_baseline = np.mean(se_random_baseline)
    
    print(f"  Seller_Effective rate (10 bars before TRANSITION): {100*avg_se_before_transition:.1f}%")
    print(f"  Seller_Effective rate (random baseline): {100*avg_se_baseline:.1f}%")
    print(f"  Reduction: {100*(1 - avg_se_before_transition/avg_se_baseline):.1f}%")
    
    print("\n[5] Consecutive zero-effectiveness detection...")
    
    zero_eff_runs = []
    current_run = 0
    for i, se in enumerate(seller_effective):
        if not se:
            current_run += 1
        else:
            if current_run >= 3:
                zero_eff_runs.append((i - current_run, i - 1))
            current_run = 0
    
    zero_run_followed_by_transition = 0
    for start, end in zero_eff_runs:
        for offset in range(1, 6):
            if (end + offset) in transition_set:
                zero_run_followed_by_transition += 1
                break
    
    zero_run_rate = zero_run_followed_by_transition / len(zero_eff_runs) if zero_eff_runs else 0
    
    print(f"  Zero-effectiveness runs (≥3 bars): {len(zero_eff_runs)}")
    print(f"  Followed by TRANSITION within 5 bars: {zero_run_followed_by_transition} ({100*zero_run_rate:.1f}%)")
    
    np.random.seed(123)
    random_points = np.random.choice(range(30, len(seller_effective) - 10), size=len(zero_eff_runs), replace=False)
    random_followed = sum(1 for p in random_points if any((p + offset) in transition_set for offset in range(1, 6)))
    random_rate = random_followed / len(random_points) if random_points.size > 0 else 0
    
    lift = zero_run_rate / random_rate if random_rate > 0 else 0
    print(f"  Baseline rate: {100*random_rate:.1f}%")
    print(f"  Lift: {lift:.2f}")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    results = {
        "metadata": {
            "total_bars": len(seller_active),
            "epsilon": float(epsilon),
            "n_transitions": len(transitions)
        },
        "global_rates": {
            "seller_active": float(np.mean(seller_active)),
            "seller_effective": float(np.mean(seller_effective)),
            "buyer_active": float(np.mean(buyer_active)),
            "buyer_effective": float(np.mean(buyer_effective))
        },
        "phase_analysis": {
            "phase_a_n": len(phase_a_sa),
            "phase_a_seller_active": float(np.mean(phase_a_sa)),
            "phase_a_seller_effective": float(np.mean(phase_a_se)),
            "phase_a_effectiveness_ratio": float(eff_ratio_a),
            "phase_b_n": len(phase_b_sa),
            "phase_b_seller_active": float(np.mean(phase_b_sa)),
            "phase_b_seller_effective": float(np.mean(phase_b_se)),
            "phase_b_effectiveness_ratio": float(eff_ratio_b),
            "impotence_drop": float(impotence_drop)
        },
        "pre_transition": {
            "se_before_transition": float(avg_se_before_transition),
            "se_baseline": float(avg_se_baseline),
            "reduction": float(1 - avg_se_before_transition/avg_se_baseline)
        },
        "zero_effectiveness_runs": {
            "n_runs": len(zero_eff_runs),
            "followed_by_transition": zero_run_followed_by_transition,
            "rate": float(zero_run_rate),
            "baseline_rate": float(random_rate),
            "lift": float(lift)
        },
        "validation": {
            "seller_active_maintained_in_zpoc": bool(np.mean(phase_b_sa) > 0.4),
            "seller_effective_drops_in_zpoc": bool(impotence_drop > 0.3),
            "zero_eff_precedes_transition": bool(lift > 1.5),
            "impotence_theory_confirmed": bool(impotence_drop > 0.3 and lift > 1.5)
        }
    }
    
    print(f"\n  Seller_Active maintained in ZPOC: {results['validation']['seller_active_maintained_in_zpoc']}")
    print(f"  Seller_Effective drops in ZPOC: {results['validation']['seller_effective_drops_in_zpoc']}")
    print(f"  Zero-effectiveness precedes transition: {results['validation']['zero_eff_precedes_transition']}")
    print(f"\n  IMPOTENCE THEORY CONFIRMED: {results['validation']['impotence_theory_confirmed']}")
    
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
