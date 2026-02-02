"""
G1: BUYER ≫ SELLER 비대칭성 원인 분해 실험

관측:
  TO_BUYER: 84.4%
  TO_SELLER: 62.1%
  차이: 22.3%

가능한 원인 가설:
1. 시장 구조 (상승 편향)
2. 임펄스 노출 차이
3. 채널 정의 비대칭
4. 레짐 혼합 효과

테스트:
1. 상승/하락 레짐 분리
2. 임펄스 proximity 제거 후 재측정
3. 채널 정의 대칭화
"""

import pandas as pd
import numpy as np
import json
from typing import List, Dict

DATA_PATH = "data/nq1_full_combined.csv"

CHANNEL_PERIOD = 20
PRE_TRANSITION_WINDOW = 5


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
    
    ma50 = df['close'].rolling(50).mean()
    df['regime'] = ['BULL' if df.iloc[i]['close'] > ma50.iloc[i] else 'BEAR' if pd.notna(ma50.iloc[i]) else 'UNKNOWN' 
                    for i in range(n)]
    
    return df


def detect_transitions_symmetric(df):
    """대칭적 전환 감지 (채널 기반만)"""
    transitions = []
    
    for i in range(5, len(df)):
        channel = df.iloc[i]['channel']
        prev_channel = df.iloc[i-1]['channel']
        
        if channel > 85 and prev_channel <= 85:
            transitions.append({
                'bar_idx': i,
                'direction': 'TO_SELLER',
                'regime': df.iloc[i]['regime']
            })
        elif channel < 15 and prev_channel >= 15:
            transitions.append({
                'bar_idx': i,
                'direction': 'TO_BUYER',
                'regime': df.iloc[i]['regime']
            })
    
    return transitions


def is_impulse_proximal(df, idx, lookback=3):
    """최근 n봉 내 임펄스 발생 여부"""
    if idx < lookback:
        return False
    
    for j in range(idx - lookback, idx):
        bar = df.iloc[j]
        delta = abs(bar['close'] - bar['open'])
        if delta > 15:
            return True
    
    return False


def analyze_consistency(df, transitions):
    """Δ 일관성 분석"""
    results = {
        'TO_SELLER': {'consistent': 0, 'total': 0, 'deltas': []},
        'TO_BUYER': {'consistent': 0, 'total': 0, 'deltas': []}
    }
    
    for trans in transitions:
        idx = trans['bar_idx']
        direction = trans['direction']
        
        if idx < PRE_TRANSITION_WINDOW + 1:
            continue
        
        pre_deltas = [df.iloc[j]['ratio'] for j in range(idx - PRE_TRANSITION_WINDOW, idx)]
        avg_delta = sum(pre_deltas) / len(pre_deltas)
        current_delta = df.iloc[idx]['ratio']
        delta_change = current_delta - avg_delta
        
        if direction == "TO_SELLER":
            consistent = delta_change > 0.3
        else:
            consistent = delta_change < -0.3
        
        results[direction]['total'] += 1
        if consistent:
            results[direction]['consistent'] += 1
        results[direction]['deltas'].append(delta_change)
    
    return results


def run_asymmetry_analysis():
    print("="*70)
    print("G1: BUYER ≫ SELLER 비대칭성 원인 분해")
    print("="*70)
    
    df = load_data()
    df = prepare_data(df)
    print(f"Loaded {len(df)} bars")
    
    transitions = detect_transitions_symmetric(df)
    print(f"Total transitions: {len(transitions)}")
    
    print("\n" + "="*70)
    print("[1] 기본 비대칭성 확인")
    print("="*70)
    
    base_results = analyze_consistency(df, transitions)
    
    for direction in ['TO_SELLER', 'TO_BUYER']:
        r = base_results[direction]
        rate = r['consistent'] / r['total'] * 100 if r['total'] > 0 else 0
        print(f"  {direction}: {rate:.1f}% (n={r['total']})")
    
    print("\n" + "="*70)
    print("[2] 가설1: 레짐 분리 (상승장 vs 하락장)")
    print("="*70)
    
    for regime in ['BULL', 'BEAR']:
        regime_trans = [t for t in transitions if t['regime'] == regime]
        regime_results = analyze_consistency(df, regime_trans)
        
        print(f"\n  {regime} REGIME (n={len(regime_trans)}):")
        
        for direction in ['TO_SELLER', 'TO_BUYER']:
            r = regime_results[direction]
            rate = r['consistent'] / r['total'] * 100 if r['total'] > 0 else 0
            print(f"    {direction}: {rate:.1f}% (n={r['total']})")
    
    print("\n" + "="*70)
    print("[3] 가설2: 임펄스 proximity 제거")
    print("="*70)
    
    non_impulse_trans = [t for t in transitions if not is_impulse_proximal(df, t['bar_idx'])]
    impulse_trans = [t for t in transitions if is_impulse_proximal(df, t['bar_idx'])]
    
    print(f"\n  Non-Impulse Transitions (n={len(non_impulse_trans)}):")
    non_impulse_results = analyze_consistency(df, non_impulse_trans)
    
    for direction in ['TO_SELLER', 'TO_BUYER']:
        r = non_impulse_results[direction]
        rate = r['consistent'] / r['total'] * 100 if r['total'] > 0 else 0
        print(f"    {direction}: {rate:.1f}% (n={r['total']})")
    
    print(f"\n  Impulse-Proximal Transitions (n={len(impulse_trans)}):")
    impulse_results = analyze_consistency(df, impulse_trans)
    
    for direction in ['TO_SELLER', 'TO_BUYER']:
        r = impulse_results[direction]
        rate = r['consistent'] / r['total'] * 100 if r['total'] > 0 else 0
        print(f"    {direction}: {rate:.1f}% (n={r['total']})")
    
    print("\n" + "="*70)
    print("[4] 가설3: 채널 대칭화 (85/15 → 80/20)")
    print("="*70)
    
    sym_transitions = []
    for i in range(5, len(df)):
        channel = df.iloc[i]['channel']
        prev_channel = df.iloc[i-1]['channel']
        
        if channel > 80 and prev_channel <= 80:
            sym_transitions.append({
                'bar_idx': i,
                'direction': 'TO_SELLER',
                'regime': df.iloc[i]['regime']
            })
        elif channel < 20 and prev_channel >= 20:
            sym_transitions.append({
                'bar_idx': i,
                'direction': 'TO_BUYER',
                'regime': df.iloc[i]['regime']
            })
    
    sym_results = analyze_consistency(df, sym_transitions)
    
    print(f"\n  Symmetric 80/20 Threshold (n={len(sym_transitions)}):")
    for direction in ['TO_SELLER', 'TO_BUYER']:
        r = sym_results[direction]
        rate = r['consistent'] / r['total'] * 100 if r['total'] > 0 else 0
        print(f"    {direction}: {rate:.1f}% (n={r['total']})")
    
    print("\n" + "="*70)
    print("[5] 가설4: Δ 분포 비교")
    print("="*70)
    
    for direction in ['TO_SELLER', 'TO_BUYER']:
        deltas = base_results[direction]['deltas']
        if deltas:
            print(f"\n  {direction} Δ Distribution:")
            print(f"    Mean: {np.mean(deltas):.3f}")
            print(f"    Std: {np.std(deltas):.3f}")
            print(f"    Min: {min(deltas):.3f}")
            print(f"    Max: {max(deltas):.3f}")
            print(f"    % > 0: {sum(1 for d in deltas if d > 0)/len(deltas)*100:.1f}%")
            print(f"    % < 0: {sum(1 for d in deltas if d < 0)/len(deltas)*100:.1f}%")
    
    print("\n" + "="*70)
    print("[6] 결론: 비대칭성 원인 판정")
    print("="*70)
    
    base_seller = base_results['TO_SELLER']['consistent'] / base_results['TO_SELLER']['total'] * 100 if base_results['TO_SELLER']['total'] > 0 else 0
    base_buyer = base_results['TO_BUYER']['consistent'] / base_results['TO_BUYER']['total'] * 100 if base_results['TO_BUYER']['total'] > 0 else 0
    
    non_imp_seller = non_impulse_results['TO_SELLER']['consistent'] / non_impulse_results['TO_SELLER']['total'] * 100 if non_impulse_results['TO_SELLER']['total'] > 0 else 0
    non_imp_buyer = non_impulse_results['TO_BUYER']['consistent'] / non_impulse_results['TO_BUYER']['total'] * 100 if non_impulse_results['TO_BUYER']['total'] > 0 else 0
    
    impulse_effect_seller = non_imp_seller - base_seller
    impulse_effect_buyer = non_imp_buyer - base_buyer
    
    print(f"\n  기본 비대칭: BUYER {base_buyer:.1f}% vs SELLER {base_seller:.1f}% (Δ={base_buyer-base_seller:.1f}%)")
    print(f"\n  임펄스 제거 효과:")
    print(f"    TO_SELLER: {base_seller:.1f}% → {non_imp_seller:.1f}% ({impulse_effect_seller:+.1f}%)")
    print(f"    TO_BUYER: {base_buyer:.1f}% → {non_imp_buyer:.1f}% ({impulse_effect_buyer:+.1f}%)")
    
    asymmetry_after = non_imp_buyer - non_imp_seller
    
    print(f"\n  임펄스 제거 후 비대칭: {asymmetry_after:.1f}%")
    
    if asymmetry_after < base_buyer - base_seller - 5:
        print("\n  ✅ 가설2 지지: 임펄스가 SELLER 쪽 일관성을 더 많이 훼손")
    else:
        print("\n  ⚠️ 임펄스만으로는 설명 불충분, 구조적 비대칭 존재")
    
    results = {
        'timestamp': '2026-01-23',
        'base_asymmetry': round(base_buyer - base_seller, 1),
        'base': {
            'TO_SELLER': round(base_seller, 1),
            'TO_BUYER': round(base_buyer, 1)
        },
        'non_impulse': {
            'TO_SELLER': round(non_imp_seller, 1),
            'TO_BUYER': round(non_imp_buyer, 1)
        },
        'impulse_effect': {
            'TO_SELLER': round(impulse_effect_seller, 1),
            'TO_BUYER': round(impulse_effect_buyer, 1)
        },
        'asymmetry_after_impulse_removal': round(asymmetry_after, 1)
    }
    
    output_path = "v7-grammar-system/experiments/g1_asymmetry_results.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n\nResults saved to: {output_path}")
    
    return results


if __name__ == "__main__":
    run_asymmetry_analysis()
