"""
OPA Δ Archive-Compatible Test

아카이브 원형 복원:
- TP/SL: ❌ 측정 안 함
- 수익: ❌ 측정 안 함  
- 승률: ❌ 측정 안 함
- 포지션: ❌ 없어도 됨

핵심 질문 단 하나:
"Δ는 pre-transition (t-ε) 구간에서
상태 전환을 일관되게 설명하는가?"

측정:
- 전환 발생 여부
- Δ의 부호 일관성
- Δ 크기 분포
- false transition rate
"""

import pandas as pd
import numpy as np
import json
from typing import List, Dict, Tuple

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


def get_state(ratio, channel):
    """상태 분류"""
    if ratio > 1.5 and channel > 80:
        return "OVERBOUGHT"
    elif ratio < 0.7 and channel < 20:
        return "OVERSOLD"
    elif ratio > 1.3:
        return "THETA_1"
    elif ratio < 0.77:
        return "THETA_2"
    else:
        return "NEUTRAL"


def prepare_data(df):
    """지표 계산"""
    n = len(df)
    
    highs = df['high'].rolling(CHANNEL_PERIOD).max()
    lows = df['low'].rolling(CHANNEL_PERIOD).min()
    
    ratios = []
    channels = []
    states = []
    deltas = []
    
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
        
        state = get_state(ratio, channel)
        states.append(state)
        
        delta = ratio
        deltas.append(delta)
    
    df['ratio'] = ratios
    df['channel'] = channels
    df['state'] = states
    df['delta'] = deltas
    
    return df


def detect_transitions(df):
    """상태 전환 감지"""
    transitions = []
    
    for i in range(1, len(df)):
        prev_state = df.iloc[i-1]['state']
        curr_state = df.iloc[i]['state']
        
        if prev_state != curr_state:
            if curr_state in ["OVERBOUGHT", "THETA_1"]:
                direction = "TO_SELLER"
            elif curr_state in ["OVERSOLD", "THETA_2"]:
                direction = "TO_BUYER"
            else:
                direction = "TO_NEUTRAL"
            
            transitions.append({
                'bar_idx': i,
                'from_state': prev_state,
                'to_state': curr_state,
                'direction': direction
            })
    
    return transitions


def analyze_pre_transition_delta(df, transitions):
    """
    핵심 분석: t-ε 윈도우에서 Δ의 일관성
    
    TP/SL 없음! 승률 없음! 수익 없음!
    오직 "Δ가 전환을 설명하는가"만 본다.
    """
    
    results = {
        'TO_SELLER': {'consistent': 0, 'inconsistent': 0, 'deltas': []},
        'TO_BUYER': {'consistent': 0, 'inconsistent': 0, 'deltas': []},
        'TO_NEUTRAL': {'consistent': 0, 'inconsistent': 0, 'deltas': []}
    }
    
    for trans in transitions:
        idx = trans['bar_idx']
        direction = trans['direction']
        
        if idx < PRE_TRANSITION_WINDOW:
            continue
        
        pre_deltas = [df.iloc[j]['delta'] for j in range(idx - PRE_TRANSITION_WINDOW, idx)]
        avg_delta = sum(pre_deltas) / len(pre_deltas)
        current_delta = df.iloc[idx]['delta']
        
        delta_change = current_delta - avg_delta
        
        if direction == "TO_SELLER":
            consistent = delta_change > 0.3
        elif direction == "TO_BUYER":
            consistent = delta_change < -0.3
        else:
            consistent = abs(delta_change) < 0.3
        
        if consistent:
            results[direction]['consistent'] += 1
        else:
            results[direction]['inconsistent'] += 1
        
        results[direction]['deltas'].append({
            'bar_idx': idx,
            'pre_avg': round(avg_delta, 3),
            'current': round(current_delta, 3),
            'change': round(delta_change, 3),
            'consistent': consistent
        })
    
    return results


def run_experiment():
    print("="*70)
    print("OPA Δ Archive-Compatible Test")
    print("="*70)
    print("\n❌ TP/SL 없음")
    print("❌ 승률 없음")
    print("❌ 수익 없음")
    print("✅ 질문: Δ가 t-ε에서 전환을 설명하는가?")
    print()
    
    df = load_data()
    df = prepare_data(df)
    print(f"Loaded {len(df)} bars")
    
    transitions = detect_transitions(df)
    print(f"Total transitions detected: {len(transitions)}")
    
    to_seller = sum(1 for t in transitions if t['direction'] == 'TO_SELLER')
    to_buyer = sum(1 for t in transitions if t['direction'] == 'TO_BUYER')
    to_neutral = sum(1 for t in transitions if t['direction'] == 'TO_NEUTRAL')
    
    print(f"  TO_SELLER: {to_seller}")
    print(f"  TO_BUYER: {to_buyer}")
    print(f"  TO_NEUTRAL: {to_neutral}")
    
    results = analyze_pre_transition_delta(df, transitions)
    
    print("\n" + "="*70)
    print("[1] Δ CONSISTENCY BY TRANSITION DIRECTION")
    print("="*70)
    
    summary = {}
    
    for direction in ['TO_SELLER', 'TO_BUYER', 'TO_NEUTRAL']:
        r = results[direction]
        total = r['consistent'] + r['inconsistent']
        if total > 0:
            consistency_rate = r['consistent'] / total * 100
        else:
            consistency_rate = 0
        
        print(f"\n  {direction}:")
        print(f"    Total: {total}")
        print(f"    Consistent: {r['consistent']} ({consistency_rate:.1f}%)")
        print(f"    Inconsistent: {r['inconsistent']} ({100-consistency_rate:.1f}%)")
        
        summary[direction] = {
            'total': total,
            'consistent': r['consistent'],
            'consistency_rate': round(consistency_rate, 1)
        }
    
    print("\n" + "="*70)
    print("[2] DELTA DISTRIBUTION ANALYSIS")
    print("="*70)
    
    for direction in ['TO_SELLER', 'TO_BUYER']:
        deltas = results[direction]['deltas']
        if not deltas:
            continue
        
        changes = [d['change'] for d in deltas]
        
        print(f"\n  {direction}:")
        print(f"    Mean Δ change: {np.mean(changes):.3f}")
        print(f"    Std Δ change: {np.std(changes):.3f}")
        print(f"    Min: {min(changes):.3f}")
        print(f"    Max: {max(changes):.3f}")
        
        sign_consistent = sum(1 for c in changes if (direction == 'TO_SELLER' and c > 0) or (direction == 'TO_BUYER' and c < 0))
        print(f"    Sign consistent: {sign_consistent}/{len(changes)} ({sign_consistent/len(changes)*100:.1f}%)")
        
        summary[direction]['mean_change'] = round(np.mean(changes), 3)
        summary[direction]['sign_consistent_rate'] = round(sign_consistent/len(changes)*100, 1) if len(changes) > 0 else 0
    
    print("\n" + "="*70)
    print("[3] FALSE TRANSITION RATE")
    print("="*70)
    
    false_transitions = 0
    total_checked = 0
    
    for trans in transitions:
        idx = trans['bar_idx']
        direction = trans['direction']
        
        if idx + 5 >= len(df):
            continue
        if direction == 'TO_NEUTRAL':
            continue
        
        total_checked += 1
        
        next_5_states = [df.iloc[j]['state'] for j in range(idx + 1, idx + 6)]
        
        if direction == 'TO_SELLER':
            expected = ['OVERBOUGHT', 'THETA_1']
            actual_count = sum(1 for s in next_5_states if s in expected)
        else:
            expected = ['OVERSOLD', 'THETA_2']
            actual_count = sum(1 for s in next_5_states if s in expected)
        
        if actual_count < 2:
            false_transitions += 1
    
    false_rate = false_transitions / total_checked * 100 if total_checked > 0 else 0
    
    print(f"\n  Total transitions checked: {total_checked}")
    print(f"  False transitions (state didn't persist): {false_transitions}")
    print(f"  False transition rate: {false_rate:.1f}%")
    print(f"  Valid transition rate: {100-false_rate:.1f}%")
    
    summary['false_transition_rate'] = round(false_rate, 1)
    
    print("\n" + "="*70)
    print("[4] FINAL VERDICT (아카이브 기준)")
    print("="*70)
    
    to_seller_valid = summary['TO_SELLER']['consistency_rate'] > 50
    to_buyer_valid = summary['TO_BUYER']['consistency_rate'] > 50
    false_rate_valid = false_rate < 30
    
    print(f"\n  CHECK 1: TO_SELLER Δ 일관성 > 50%")
    print(f"    {'✅' if to_seller_valid else '❌'} {summary['TO_SELLER']['consistency_rate']}%")
    
    print(f"\n  CHECK 2: TO_BUYER Δ 일관성 > 50%")
    print(f"    {'✅' if to_buyer_valid else '❌'} {summary['TO_BUYER']['consistency_rate']}%")
    
    print(f"\n  CHECK 3: False Transition < 30%")
    print(f"    {'✅' if false_rate_valid else '❌'} {false_rate:.1f}%")
    
    all_pass = to_seller_valid and to_buyer_valid and false_rate_valid
    
    print(f"\n  OVERALL: {'✅ Δ VALID' if all_pass else '⚠️ PARTIAL / ❌ INVALID'}")
    
    if all_pass:
        print("\n  결론: Δ는 pre-transition(t-ε)에서 상태 전환을 일관되게 설명한다.")
        print("       아카이브 OPA Δ 가설 유지.")
    else:
        print("\n  결론: Δ 일관성이 완벽하지 않음. 조건부 유효 가능.")
    
    final_results = {
        'timestamp': '2026-01-23',
        'experiment_type': 'archive_compatible',
        'no_tp_sl': True,
        'no_profit': True,
        'no_win_rate': True,
        'transitions_analyzed': len(transitions),
        'summary': summary,
        'false_transition_rate': false_rate,
        'verdict': {
            'to_seller_valid': to_seller_valid,
            'to_buyer_valid': to_buyer_valid,
            'false_rate_valid': false_rate_valid,
            'all_pass': all_pass
        }
    }
    
    output_path = "v7-grammar-system/experiments/opa_delta_archive_results.json"
    with open(output_path, 'w') as f:
        json.dump(final_results, f, indent=2)
    
    print(f"\n\nResults saved to: {output_path}")
    
    return final_results


if __name__ == "__main__":
    run_experiment()
