"""
OPA Δ Meta-Validation

추가 검증 2개:
1. Δ-독립 전환 라벨로 재검증 (가격/구조 기반)
2. t-ε 윈도우 ±1 bar 민감도 테스트
3. 랜덤 샘플 비교 (Sanity check)
4. 부트스트랩 CI
"""

import pandas as pd
import numpy as np
import json
from typing import List, Dict, Tuple
import random

DATA_PATH = "data/nq1_full_combined.csv"

CHANNEL_PERIOD = 20
PRE_TRANSITION_WINDOW = 5
BOOTSTRAP_ITERATIONS = 1000


def load_data():
    df = pd.read_csv(DATA_PATH)
    df.columns = [c.strip() for c in df.columns]
    return df


def calculate_ratio(high, low, close):
    if high == low:
        return 1.0
    buyer = close - low
    seller = high - close
    if seller == 0:
        return 10.0
    return buyer / seller


def prepare_data(df):
    """지표 계산"""
    n = len(df)
    
    highs = df['high'].rolling(CHANNEL_PERIOD).max()
    lows = df['low'].rolling(CHANNEL_PERIOD).min()
    
    ratios = []
    channels = []
    
    for i in range(n):
        bar = df.iloc[i]
        
        ratio = calculate_ratio(bar['high'], bar['low'], bar['close'])
        ratios.append(ratio)
        
        period_high = highs.iloc[i]
        period_low = lows.iloc[i]
        if pd.isna(period_high) or period_high == period_low:
            channel = 50.0
        else:
            channel = (bar['close'] - period_low) / (period_high - period_low) * 100
        channels.append(channel)
    
    df['ratio'] = ratios
    df['channel'] = channels
    
    return df


def detect_transitions_delta_independent(df):
    """
    Δ-독립 전환 감지 (가격/구조 기반)
    
    ratio를 사용하지 않고 오직:
    - 채널 위치 (구조적 위치)
    - 가격 방향 (close 변화)
    """
    transitions = []
    
    for i in range(5, len(df)):
        channel = df.iloc[i]['channel']
        prev_channel = df.iloc[i-1]['channel']
        
        closes = [df.iloc[j]['close'] for j in range(i-4, i+1)]
        price_direction = closes[-1] - closes[0]
        
        if channel > 85 and prev_channel <= 85:
            transitions.append({
                'bar_idx': i,
                'type': 'CHANNEL_HIGH',
                'direction': 'TO_SELLER'
            })
        elif channel < 15 and prev_channel >= 15:
            transitions.append({
                'bar_idx': i,
                'type': 'CHANNEL_LOW',
                'direction': 'TO_BUYER'
            })
        elif channel > 70 and price_direction > 20:
            transitions.append({
                'bar_idx': i,
                'type': 'BREAKOUT_HIGH',
                'direction': 'TO_SELLER'
            })
        elif channel < 30 and price_direction < -20:
            transitions.append({
                'bar_idx': i,
                'type': 'BREAKDOWN_LOW',
                'direction': 'TO_BUYER'
            })
    
    return transitions


def analyze_delta_consistency(df, transitions, window_offset=0):
    """
    Δ 일관성 분석 (윈도우 오프셋 지원)
    
    window_offset:
      0 = 기본 (t-ε to t-1)
     -1 = 한 칸 당김 (t-ε-1 to t-2)
     +1 = 한 칸 밈 (t-ε+1 to t)
    """
    
    results = {
        'TO_SELLER': {'consistent': 0, 'inconsistent': 0, 'deltas': []},
        'TO_BUYER': {'consistent': 0, 'inconsistent': 0, 'deltas': []}
    }
    
    for trans in transitions:
        idx = trans['bar_idx']
        direction = trans['direction']
        
        if direction not in ['TO_SELLER', 'TO_BUYER']:
            continue
        
        start = idx - PRE_TRANSITION_WINDOW + window_offset
        end = idx + window_offset
        
        if start < 1 or end >= len(df):
            continue
        
        pre_deltas = [df.iloc[j]['ratio'] for j in range(start, end)]
        avg_delta = sum(pre_deltas) / len(pre_deltas)
        current_delta = df.iloc[idx]['ratio']
        
        delta_change = current_delta - avg_delta
        
        if direction == "TO_SELLER":
            consistent = delta_change > 0.3
        else:
            consistent = delta_change < -0.3
        
        if consistent:
            results[direction]['consistent'] += 1
        else:
            results[direction]['inconsistent'] += 1
        
        results[direction]['deltas'].append(delta_change)
    
    return results


def bootstrap_ci(deltas, direction, n_iterations=BOOTSTRAP_ITERATIONS):
    """부트스트랩 95% 신뢰구간"""
    if len(deltas) < 10:
        return 0, 0, 0
    
    consistencies = []
    
    for _ in range(n_iterations):
        sample = random.choices(deltas, k=len(deltas))
        if direction == "TO_SELLER":
            consistent = sum(1 for d in sample if d > 0.3) / len(sample) * 100
        else:
            consistent = sum(1 for d in sample if d < -0.3) / len(sample) * 100
        consistencies.append(consistent)
    
    consistencies.sort()
    lower = consistencies[int(n_iterations * 0.025)]
    upper = consistencies[int(n_iterations * 0.975)]
    mean = sum(consistencies) / len(consistencies)
    
    return lower, mean, upper


def random_sample_consistency(df, n_samples, direction):
    """랜덤 샘플에서 동일 측정"""
    
    valid_indices = list(range(PRE_TRANSITION_WINDOW + 10, len(df) - 10))
    random_indices = random.sample(valid_indices, min(n_samples, len(valid_indices)))
    
    consistent = 0
    
    for idx in random_indices:
        pre_deltas = [df.iloc[j]['ratio'] for j in range(idx - PRE_TRANSITION_WINDOW, idx)]
        avg_delta = sum(pre_deltas) / len(pre_deltas)
        current_delta = df.iloc[idx]['ratio']
        delta_change = current_delta - avg_delta
        
        if direction == "TO_SELLER":
            if delta_change > 0.3:
                consistent += 1
        else:
            if delta_change < -0.3:
                consistent += 1
    
    return consistent / len(random_indices) * 100 if random_indices else 0


def run_meta_validation():
    print("="*70)
    print("OPA Δ Meta-Validation")
    print("="*70)
    
    df = load_data()
    df = prepare_data(df)
    print(f"Loaded {len(df)} bars")
    
    transitions = detect_transitions_delta_independent(df)
    print(f"Δ-independent transitions: {len(transitions)}")
    
    to_seller = [t for t in transitions if t['direction'] == 'TO_SELLER']
    to_buyer = [t for t in transitions if t['direction'] == 'TO_BUYER']
    
    print(f"  TO_SELLER: {len(to_seller)}")
    print(f"  TO_BUYER: {len(to_buyer)}")
    
    print("\n" + "="*70)
    print("[1] Δ-INDEPENDENT LABEL CONSISTENCY")
    print("="*70)
    
    results_base = analyze_delta_consistency(df, transitions, window_offset=0)
    
    for direction in ['TO_SELLER', 'TO_BUYER']:
        r = results_base[direction]
        total = r['consistent'] + r['inconsistent']
        if total > 0:
            rate = r['consistent'] / total * 100
        else:
            rate = 0
        
        print(f"\n  {direction}:")
        print(f"    n={total}")
        print(f"    Consistency: {rate:.1f}%")
        
        if r['deltas']:
            lower, mean, upper = bootstrap_ci(r['deltas'], direction)
            print(f"    95% CI: [{lower:.1f}%, {upper:.1f}%]")
    
    print("\n" + "="*70)
    print("[2] WINDOW OFFSET SENSITIVITY TEST")
    print("="*70)
    
    for offset in [-1, 0, +1]:
        results = analyze_delta_consistency(df, transitions, window_offset=offset)
        
        label = "기본" if offset == 0 else (f"당김 ({offset})" if offset < 0 else f"밀림 (+{offset})")
        
        print(f"\n  Offset {offset} ({label}):")
        
        for direction in ['TO_SELLER', 'TO_BUYER']:
            r = results[direction]
            total = r['consistent'] + r['inconsistent']
            if total > 0:
                rate = r['consistent'] / total * 100
            else:
                rate = 0
            print(f"    {direction}: {rate:.1f}% (n={total})")
    
    print("\n" + "="*70)
    print("[3] RANDOM SAMPLE COMPARISON")
    print("="*70)
    
    for direction in ['TO_SELLER', 'TO_BUYER']:
        r = results_base[direction]
        n = r['consistent'] + r['inconsistent']
        
        if n > 0:
            real_rate = r['consistent'] / n * 100
            random_rate = random_sample_consistency(df, n, direction)
            
            print(f"\n  {direction}:")
            print(f"    Real: {real_rate:.1f}%")
            print(f"    Random: {random_rate:.1f}%")
            print(f"    Difference: {real_rate - random_rate:+.1f}%")
    
    print("\n" + "="*70)
    print("[4] FINAL META-VALIDATION VERDICT")
    print("="*70)
    
    seller_r = results_base['TO_SELLER']
    buyer_r = results_base['TO_BUYER']
    
    seller_total = seller_r['consistent'] + seller_r['inconsistent']
    buyer_total = buyer_r['consistent'] + buyer_r['inconsistent']
    
    seller_rate = seller_r['consistent'] / seller_total * 100 if seller_total > 0 else 0
    buyer_rate = buyer_r['consistent'] / buyer_total * 100 if buyer_total > 0 else 0
    
    offset_minus1 = analyze_delta_consistency(df, transitions, window_offset=-1)
    seller_minus1 = offset_minus1['TO_SELLER']
    buyer_minus1 = offset_minus1['TO_BUYER']
    
    seller_minus1_rate = seller_minus1['consistent'] / (seller_minus1['consistent'] + seller_minus1['inconsistent']) * 100 if (seller_minus1['consistent'] + seller_minus1['inconsistent']) > 0 else 0
    
    check1_pass = seller_rate > 50 and buyer_rate > 50
    check2_pass = abs(seller_rate - seller_minus1_rate) < 20
    
    random_seller = random_sample_consistency(df, seller_total, 'TO_SELLER')
    random_buyer = random_sample_consistency(df, buyer_total, 'TO_BUYER')
    check3_pass = (seller_rate - random_seller > 10) or (buyer_rate - random_buyer > 10)
    
    print(f"\n  CHECK 1: Δ-독립 라벨 일관성 > 50%")
    print(f"    {'✅' if check1_pass else '❌'} TO_SELLER={seller_rate:.1f}%, TO_BUYER={buyer_rate:.1f}%")
    
    print(f"\n  CHECK 2: 윈도우 오프셋 민감도 < 20%")
    print(f"    {'✅' if check2_pass else '❌'} Δ={abs(seller_rate - seller_minus1_rate):.1f}%")
    
    print(f"\n  CHECK 3: Real > Random + 10%")
    print(f"    {'✅' if check3_pass else '❌'} Seller: {seller_rate - random_seller:+.1f}%, Buyer: {buyer_rate - random_buyer:+.1f}%")
    
    all_pass = check1_pass and check2_pass and check3_pass
    
    print(f"\n  OVERALL: {'✅ META-VALIDATION PASS' if all_pass else '⚠️ PARTIAL / NEEDS REVIEW'}")
    
    if check1_pass:
        print("\n  ✅ Label leakage 아님: Δ-독립 라벨에서도 일관성 유지")
    else:
        print("\n  ⚠️ Δ-독립 라벨에서 일관성 낮음: 원래 결과는 label leakage 가능성")
    
    results = {
        'timestamp': '2026-01-23',
        'delta_independent_transitions': len(transitions),
        'base_results': {
            'TO_SELLER': {'n': seller_total, 'consistency': round(seller_rate, 1)},
            'TO_BUYER': {'n': buyer_total, 'consistency': round(buyer_rate, 1)}
        },
        'window_sensitivity': {
            'offset_-1': round(seller_minus1_rate, 1),
            'offset_0': round(seller_rate, 1)
        },
        'random_comparison': {
            'TO_SELLER_real': round(seller_rate, 1),
            'TO_SELLER_random': round(random_seller, 1),
            'TO_BUYER_real': round(buyer_rate, 1),
            'TO_BUYER_random': round(random_buyer, 1)
        },
        'verdict': {
            'check1_label_independence': check1_pass,
            'check2_window_sensitivity': check2_pass,
            'check3_real_vs_random': check3_pass,
            'all_pass': all_pass
        }
    }
    
    output_path = "v7-grammar-system/experiments/opa_delta_meta_validation_results.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n\nResults saved to: {output_path}")
    
    return results


if __name__ == "__main__":
    run_meta_validation()
