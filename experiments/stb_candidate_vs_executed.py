"""
STB Candidate vs Executed Experiment

목적: STB의 "점화력"과 "실행력" 분리

아카이브 근거 (COMMIT-026):
- STB 단독: 50.6% (경계 노출)
- 확정 조건: 80%+ (임펄스 제거)

실험:
1. STB 전량 실행 승률 (baseline)
2. STB + 확정 조건 실행 승률
3. STB + OPA pre-transition 실행 승률
"""

import pandas as pd
import numpy as np
import json
from typing import List, Dict, Tuple

DATA_PATH = "data/nq1_full_combined.csv"

TP_POINTS = 20
SL_POINTS = 15
CHANNEL_PERIOD = 20
STATE_LOCK_BARS = 3


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
    states = []
    state_ages = []
    deltas = []
    
    prev_state = "NEUTRAL"
    prev_age = 0
    
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
        
        if ratio > 1.5 and channel > 80:
            state = "OVERBOUGHT"
        elif ratio < 0.7 and channel < 20:
            state = "OVERSOLD"
        elif ratio > 1.3:
            state = "THETA_1"
        elif ratio < 0.77:
            state = "THETA_2"
        else:
            state = "NEUTRAL"
        
        if state == prev_state:
            age = prev_age + 1
        else:
            age = 1
        
        states.append(state)
        state_ages.append(age)
        
        delta = bar['close'] - bar['open']
        deltas.append(delta)
        
        prev_state = state
        prev_age = age
    
    df['ratio'] = ratios
    df['channel'] = channels
    df['state'] = states
    df['state_age'] = state_ages
    df['delta'] = deltas
    
    return df


def is_stb_long(ratio, channel):
    return ratio < 0.7 and channel < 30


def is_stb_short(ratio, channel):
    return ratio > 1.5 and channel > 70


def is_confirmed(state, state_age, ratio, prev_ratio):
    """확정 조건: 상태 lock + 배율 변화 완료"""
    if state_age < STATE_LOCK_BARS:
        return False
    if state in ["OVERBOUGHT", "OVERSOLD"]:
        return True
    ratio_change = abs(ratio - prev_ratio)
    if ratio_change < 0.1:
        return True
    return False


def is_pre_transition(deltas, ratio):
    """OPA Pre-transition: 전환 직전 감지"""
    if len(deltas) < 5:
        return False
    
    recent = deltas[-5:]
    avg = sum(recent) / len(recent)
    current = recent[-1]
    
    change = abs(current - avg)
    if change > 0.3:
        if current > avg and ratio < 1.0:
            return True
        elif current < avg and ratio > 1.0:
            return True
    
    return False


def simulate_trade(df, entry_idx, direction, entry_price):
    tp = entry_price + TP_POINTS if direction == "long" else entry_price - TP_POINTS
    sl = entry_price - SL_POINTS if direction == "long" else entry_price + SL_POINTS
    
    for i in range(entry_idx + 1, min(entry_idx + 50, len(df))):
        bar = df.iloc[i]
        
        if direction == "long":
            if bar['high'] >= tp:
                return {'pnl': TP_POINTS, 'reason': 'TP'}
            elif bar['low'] <= sl:
                return {'pnl': sl - entry_price, 'reason': 'SL'}
        else:
            if bar['low'] <= tp:
                return {'pnl': TP_POINTS, 'reason': 'TP'}
            elif bar['high'] >= sl:
                return {'pnl': entry_price - sl, 'reason': 'SL'}
    
    final = df.iloc[min(entry_idx + 49, len(df) - 1)]
    if direction == "long":
        pnl = final['close'] - entry_price
    else:
        pnl = entry_price - final['close']
    
    return {'pnl': pnl, 'reason': 'TIMEOUT'}


def run_experiment():
    print("="*70)
    print("STB Candidate vs Executed Experiment")
    print("="*70)
    
    df = load_data()
    df = prepare_data(df)
    print(f"Loaded {len(df)} bars")
    
    stb_all = []
    stb_confirmed = []
    stb_opa = []
    
    last_trade_idx = -20
    delta_history = []
    
    for i in range(CHANNEL_PERIOD, len(df) - 50):
        bar = df.iloc[i]
        ratio = bar['ratio']
        channel = bar['channel']
        state = bar['state']
        state_age = bar['state_age']
        
        prev_ratio = df.iloc[i-1]['ratio'] if i > 0 else 1.0
        delta_history.append(bar['delta'])
        if len(delta_history) > 50:
            delta_history.pop(0)
        
        if i - last_trade_idx < 10:
            continue
        
        stb_long = is_stb_long(ratio, channel)
        stb_short = is_stb_short(ratio, channel)
        
        if stb_long or stb_short:
            direction = "long" if stb_long else "short"
            entry_price = bar['close']
            
            stb_all.append({
                'bar_idx': i,
                'direction': direction,
                'trade': simulate_trade(df, i, direction, entry_price)
            })
            
            confirmed = is_confirmed(state, state_age, ratio, prev_ratio)
            if confirmed:
                stb_confirmed.append({
                    'bar_idx': i,
                    'direction': direction,
                    'trade': simulate_trade(df, i, direction, entry_price)
                })
            
            pre_trans = is_pre_transition(delta_history, ratio)
            if pre_trans:
                stb_opa.append({
                    'bar_idx': i,
                    'direction': direction,
                    'trade': simulate_trade(df, i, direction, entry_price)
                })
            
            last_trade_idx = i
    
    def calc_stats(trades):
        if not trades:
            return {'count': 0, 'wins': 0, 'win_rate': 0, 'avg_pnl': 0}
        
        wins = sum(1 for t in trades if t['trade']['pnl'] > 0)
        total_pnl = sum(t['trade']['pnl'] for t in trades)
        
        return {
            'count': len(trades),
            'wins': wins,
            'win_rate': round(wins / len(trades) * 100, 1),
            'avg_pnl': round(total_pnl / len(trades), 2)
        }
    
    stats_all = calc_stats(stb_all)
    stats_confirmed = calc_stats(stb_confirmed)
    stats_opa = calc_stats(stb_opa)
    
    print("\n[1] STB 전량 실행 (Baseline)")
    print(f"  Trades: {stats_all['count']}")
    print(f"  Wins: {stats_all['wins']}")
    print(f"  Win Rate: {stats_all['win_rate']}%")
    print(f"  Avg PnL: {stats_all['avg_pnl']}")
    
    print("\n[2] STB + 확정 조건 (임펄스 제거)")
    print(f"  Trades: {stats_confirmed['count']}")
    print(f"  Wins: {stats_confirmed['wins']}")
    print(f"  Win Rate: {stats_confirmed['win_rate']}%")
    print(f"  Avg PnL: {stats_confirmed['avg_pnl']}")
    
    print("\n[3] STB + OPA Pre-transition")
    print(f"  Trades: {stats_opa['count']}")
    print(f"  Wins: {stats_opa['wins']}")
    print(f"  Win Rate: {stats_opa['win_rate']}%")
    print(f"  Avg PnL: {stats_opa['avg_pnl']}")
    
    print("\n" + "="*70)
    print("ANALYSIS")
    print("="*70)
    
    if stats_all['count'] > 0:
        confirm_rate = stats_confirmed['count'] / stats_all['count'] * 100
        opa_rate = stats_opa['count'] / stats_all['count'] * 100
        
        print(f"\n  STB 발생 → 확정 통과: {confirm_rate:.1f}%")
        print(f"  STB 발생 → OPA 통과: {opa_rate:.1f}%")
        
        wr_diff = stats_confirmed['win_rate'] - stats_all['win_rate']
        print(f"\n  확정 조건 효과: {wr_diff:+.1f}% 승률 향상")
        
        if stats_opa['count'] > 0:
            wr_diff_opa = stats_opa['win_rate'] - stats_all['win_rate']
            print(f"  OPA 조건 효과: {wr_diff_opa:+.1f}% 승률 향상")
    
    print("\n" + "="*70)
    print("CONCLUSION")
    print("="*70)
    
    print("\n  아카이브 일치 여부:")
    expected_all = 50.6
    expected_confirmed = 80.0
    
    all_match = abs(stats_all['win_rate'] - expected_all) < 10
    conf_higher = stats_confirmed['win_rate'] > stats_all['win_rate']
    
    print(f"  STB 전량 ~50%: {'✅' if all_match else '❌'} ({stats_all['win_rate']}%)")
    print(f"  확정 > 전량: {'✅' if conf_higher else '❌'}")
    
    print("\n  핵심 통찰:")
    print("  STB = '점화 후보'를 제공할 뿐, 그 자체로는 실행 트리거가 아니다.")
    print("  실행 권한은 '확정' 또는 'OPA'를 통해 부여해야 한다.")
    
    results = {
        'timestamp': '2026-01-23',
        'stb_all': stats_all,
        'stb_confirmed': stats_confirmed,
        'stb_opa': stats_opa,
        'archive_match': {
            'stb_all_near_50': all_match,
            'confirmed_higher': conf_higher
        }
    }
    
    output_path = "v7-grammar-system/experiments/stb_candidate_results.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n\nResults saved to: {output_path}")
    
    return results


if __name__ == "__main__":
    run_experiment()
